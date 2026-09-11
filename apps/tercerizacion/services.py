import re
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.whatsapp.models import WhatsAppChannel

from .models import PublicacionCarga

# Sin I, O, L — evita confundirse con 1/0 al leerse o dictarse por teléfono.
_LETRAS_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ"


def generar_codigo(publicacion_id):
    """Código corto y legible a partir del PK autoincremental — nunca se
    repite, nunca colisiona entre publicaciones activas simultáneas."""
    letra = _LETRAS_CODIGO[(publicacion_id // 100) % len(_LETRAS_CODIGO)]
    return f"{letra}{publicacion_id % 100:02d}"


def _solo_digitos(numero):
    return re.sub(r"\D", "", numero or "")


def generar_link_wa(codigo, channel=None):
    """Link wa.me con el texto 'OFERTA-<codigo>' precargado. Al pulsarlo el
    transportista solo confirma envío — ese mensaje es lo que el pipeline
    reconoce como identificación (Fase 2)."""
    channel = channel or WhatsAppChannel.objects.filter(activo=True).first()
    numero = _solo_digitos(channel.phone_number_id if channel else "")
    texto = f"OFERTA-{codigo}"
    return f"https://wa.me/{numero}?text={texto}"


def lineas_detalle_permitido(servicio):
    """Lista blanca de privacidad, en un solo lugar: lo único que puede verse
    fuera del CRM (texto publicado en grupos, y respuestas del bot de
    transportistas) sobre una carga. NUNCA incluir aquí teléfono, nombre,
    dirección exacta, documentos del cliente, ni precio_cotizado/precio_final
    (para no anclar la negociación del transportista)."""
    partes = []

    if servicio.tipo_servicio:
        partes.append(f"Tipo: {servicio.tipo_servicio}")

    origen = servicio.distrito_origen or "-"
    destino = servicio.distrito_destino or "-"
    partes.append(f"Origen: {origen}")
    partes.append(f"Destino: {destino}")

    if servicio.piso_origen:
        partes.append(f"Piso origen: {servicio.piso_origen}")
    if servicio.piso_destino:
        partes.append(f"Piso destino: {servicio.piso_destino}")
    if servicio.acceso_origen:
        partes.append(f"Acceso origen: {servicio.acceso_origen}")
    if servicio.acceso_destino:
        partes.append(f"Acceso destino: {servicio.acceso_destino}")

    if servicio.detalle_carga:
        partes.append(f"Carga: {servicio.detalle_carga}")
    if servicio.peso_carga_kg:
        partes.append(f"Peso aprox: {servicio.peso_carga_kg} kg")
    if servicio.volumen_carga_m3:
        partes.append(f"Volumen aprox: {servicio.volumen_carga_m3} m3")
    if servicio.cantidad_operarios:
        partes.append(f"Operarios requeridos: {servicio.cantidad_operarios}")
    if servicio.requisitos_especiales:
        partes.append(f"Requisitos: {', '.join(servicio.requisitos_especiales)}")

    if servicio.fecha_servicio:
        fecha = servicio.fecha_servicio.strftime("%d/%m/%Y")
        if servicio.horario_servicio:
            fecha = f"{fecha} ({servicio.horario_servicio})"
        partes.append(f"Fecha: {fecha}")

    partes.append("Forma de pago: a coordinar con el asesor")
    return partes


def generar_texto_publicacion(servicio, codigo, channel=None):
    """Texto listo para copiar/pegar en los grupos de transportistas."""
    partes = [f"🚚 OFERTA-{codigo}", *lineas_detalle_permitido(servicio)]

    link = generar_link_wa(codigo, channel=channel)
    partes.append("")
    partes.append(f"Si te interesa, responde aquí: {link}")

    return "\n".join(partes)


_ESTADOS_PUBLICACION_ACTIVA = (
    PublicacionCarga.ESTADO_BORRADOR,
    PublicacionCarga.ESTADO_ABIERTA,
    PublicacionCarga.ESTADO_PUBLICADA,
    PublicacionCarga.ESTADO_CON_OFERTAS,
)


# ---------------------------------------------------------------------------
# Rentabilidad de la tercerización: cómo la plataforma gana en una carga que
# ejecuta un transportista. El modelo es el spread venta − costo; estas
# funciones fijan ese precio de venta cuando no hay una cotización propia y
# vigilan que no caiga por debajo del piso de margen del negocio.
# ---------------------------------------------------------------------------

def _dec(v):
    if v is None or v == "":
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _categoria_de(servicio):
    """Categoría de carga del servicio (viene del lead que lo originó)."""
    lead = getattr(servicio, "lead_origen", None)
    return (getattr(lead, "categoria_carga", "") or "") if lead else ""


def comision_pct(monto, categoria=""):
    """% de comisión de la plataforma para un servicio de `monto` soles y (opc.)
    esa categoría de carga. Busca en `TramoComision`: primero un tramo activo de
    la categoría; si no hay, el tramo general (categoria=""). Si no hay tabla
    cargada, cae al markup plano de Configuración expresado como comisión.
    """
    from apps.tercerizacion.models import TramoComision

    monto = _dec(monto) or Decimal(0)
    activos = list(TramoComision.objects.filter(activo=True))
    for cat in (categoria, TramoComision.CATEGORIA_GENERAL) if categoria else (TramoComision.CATEGORIA_GENERAL,):
        tramos = sorted((t for t in activos if t.categoria == cat), key=lambda t: t.monto_desde)
        for t in tramos:
            if monto >= t.monto_desde and (t.monto_hasta is None or monto < t.monto_hasta):
                return _dec(t.porcentaje)
        if tramos:  # hay tabla para esta categoría pero el monto no cayó en ningún tramo → el último
            return _dec(tramos[-1].porcentaje)

    from apps.servicios.models import ConfiguracionOperaciones
    markup = _dec(ConfiguracionOperaciones.get_solo().markup_tercerizacion_porcentaje)
    # markup m sobre el costo ≡ comisión c sobre la venta con c = m / (1 + m)
    return (markup / (Decimal(100) + markup) * Decimal(100)).quantize(Decimal("0.01"))


def precio_cliente_sugerido(costo, categoria="", *, markup_pct=None):
    """Precio de venta al cliente a partir del costo del transportista y la
    tabla de comisiones: `precio = costo / (1 - comision%)`, donde la comisión
    depende del propio precio (tabla por tramos), así que se itera hasta que
    estabiliza. Redondeado a soles. None si no hay costo.

    `markup_pct` fuerza un markup plano sobre el costo (evita la tabla) — se usa
    para retrocompatibilidad de tests.
    """
    costo = _dec(costo)
    if costo is None or costo <= 0:
        return None
    if markup_pct is not None:
        factor = Decimal(1) + _dec(markup_pct) / Decimal(100)
        return (costo * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    precio = costo
    for _ in range(6):
        pct = comision_pct(precio, categoria)
        if pct >= Decimal(100):
            pct = Decimal("90")
        nuevo = (costo / (Decimal(1) - pct / Decimal(100))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if nuevo == precio:
            break
        precio = nuevo
    return precio


def resolver_tarifa_parcial(destino, peso_kg):
    """Busca en `TarifaCargaParcial` el tramo activo para `destino` (o el
    general) cuyo rango de peso contiene `peso_kg`. Devuelve
    `{precio, dias_estimados}` o None si no hay tramo que cubra ese
    destino/peso (→ el llamador debe derivar a un asesor, misma salvaguarda
    de siempre)."""
    from apps.tercerizacion.models import TarifaCargaParcial

    peso = _dec(peso_kg)
    if peso is None or peso <= 0:
        return None
    destino_norm = (destino or "").strip().lower()
    activos = list(TarifaCargaParcial.objects.filter(activo=True))

    for candidato in (destino_norm, TarifaCargaParcial.DESTINO_GENERAL) if destino_norm else (TarifaCargaParcial.DESTINO_GENERAL,):
        tramos = sorted(
            (t for t in activos if t.destino.strip().lower() == candidato),
            key=lambda t: t.peso_desde_kg,
        )
        for t in tramos:
            if peso >= t.peso_desde_kg and (t.peso_hasta_kg is None or peso < t.peso_hasta_kg):
                precio = max(_dec(t.monto_minimo), (_dec(t.precio_por_kg) * peso).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                return {"precio": precio, "dias_estimados": t.dias_estimados}
        if tramos:  # hay tabla para este destino pero el peso excede todos los tramos → el último (sin tope)
            ultimo = tramos[-1]
            if ultimo.peso_hasta_kg is None:
                precio = max(_dec(ultimo.monto_minimo), (_dec(ultimo.precio_por_kg) * peso).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                return {"precio": precio, "dias_estimados": ultimo.dias_estimados}
    return None


def desglose_comision(precio_servicio, costo=None, categoria=""):
    """{'servicePrice','commissionPct','commission','carrierPayout','cost'} —
    cómo se reparte el precio del servicio: comisión de la plataforma y lo que
    cobra el transportista. `cost` (si se pasa) es lo pactado con el transportista.
    """
    precio = _dec(precio_servicio)
    out = {
        "servicePrice": float(precio) if precio is not None else None,
        "commissionPct": None, "commission": None,
        "carrierPayout": None, "cost": float(_dec(costo)) if costo not in (None, "") else None,
    }
    if precio is None or precio <= 0:
        return out
    pct = comision_pct(precio, categoria)
    comision = (precio * pct / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    out["commissionPct"] = float(pct)
    out["commission"] = float(comision)
    out["carrierPayout"] = float(precio - comision)
    return out


def _piso_margen_pct():
    """Piso de margen del negocio (%). Reusa el que ya configura el bot."""
    try:
        from apps.whatsapp.models import ConfiguracionBot
        cfg = ConfiguracionBot.objects.first()
        if cfg and cfg.margen_minimo_porcentaje is not None:
            return _dec(cfg.margen_minimo_porcentaje)
    except Exception:
        pass
    return Decimal(20)


def evaluar_margen_tercerizacion(venta, costo):
    """{'sale','cost','margin','pct','floorPct','meetsFloor'} — pct sobre la venta.

    `meetsFloor` compara contra costo × (1 + piso%): es el mismo criterio que el
    gate de margen de las cotizaciones manuales.
    """
    venta, costo = _dec(venta), _dec(costo)
    piso = _piso_margen_pct()
    out = {
        "sale": float(venta) if venta is not None else None,
        "cost": float(costo) if costo is not None else None,
        "margin": None, "pct": None,
        "floorPct": float(piso), "meetsFloor": None,
    }
    if venta is None or costo is None:
        return out
    margin = venta - costo
    out["margin"] = float(margin)
    out["pct"] = round(float(margin) / float(venta) * 100, 1) if venta else None
    minimo = costo * (Decimal(1) + piso / Decimal(100))
    out["meetsFloor"] = venta >= minimo
    return out


def tercerizar_carga(servicio, usuario, *, modo_precio=None, precio_publicado=None,
                     estado=PublicacionCarga.ESTADO_ABIERTA):
    """Crea (o reutiliza, si ya hay una activa) la publicación de una carga.
    Nunca crea una segunda publicación activa para el mismo servicio —
    evita códigos duplicados para la misma carga.

    modo_precio / precio_publicado / estado permiten crearla como borrador
    (F1: el asesor la deriva pero la publica el Despacho en F3)."""
    existente = servicio.publicaciones_tercerizacion.filter(
        estado__in=_ESTADOS_PUBLICACION_ACTIVA,
    ).first()
    if existente:
        return existente, False

    with transaction.atomic():
        # select_for_update serializa la asignación de código bajo concurrencia
        # — mismo patrón que Servicio.save() usa para su propio "codigo".
        last = (
            PublicacionCarga.objects.select_for_update().order_by("-id").first()
        )
        next_id = (last.id + 1) if last else 1
        codigo = generar_codigo(next_id)

        publicacion = PublicacionCarga.objects.create(
            servicio=servicio,
            codigo=codigo,
            texto_publicado=generar_texto_publicacion(servicio, codigo),
            creado_por=usuario,
            estado=estado,
            modo_precio=modo_precio or PublicacionCarga.PRECIO_ABIERTO,
            precio_publicado=precio_publicado,
        )

    return publicacion, True


def _en_horario_atencion():
    """True si ahora estamos dentro del horario de atención configurado en el bot."""
    try:
        from django.utils import timezone

        from apps.whatsapp.models import ConfiguracionBot
        from apps.whatsapp.utils import _check_legacy_schedule
        conf = ConfiguracionBot.objects.first()
        if not conf:
            return True
        dentro, _ = _check_legacy_schedule(conf, timezone.localtime())
        return dentro
    except Exception:
        return True


def _publicacion_activa_de(lead):
    from apps.servicios.models import Servicio
    servicio = Servicio.objects.filter(lead_origen=lead).first()
    if not servicio:
        return None
    return servicio.publicaciones_tercerizacion.filter(estado__in=_ESTADOS_PUBLICACION_ACTIVA).first()


def _publicar_a_transportistas(lead, usuario, motivo):
    """Crea la reserva tercerizada + publicación abierta + hilo de compra.
    Devuelve la `PublicacionCarga` o None si faltan datos."""
    from apps.ia.conversation_policy import booking_missing_fields
    if booking_missing_fields(lead):
        return None

    ya = _publicacion_activa_de(lead)
    if ya:
        return ya

    from apps.cotizador.pipeline import _auditar
    from apps.servicios.models import Servicio
    from apps.servicios.services import crear_servicio_desde_lead
    from apps.tercerizacion import negociacion as neg

    with transaction.atomic():
        servicio, _creado = crear_servicio_desde_lead(lead, usuario=usuario)
        if servicio.modalidad_ejecucion != Servicio.MODALIDAD_TERCERIZADO:
            servicio.modalidad_ejecucion = Servicio.MODALIDAD_TERCERIZADO
            servicio.save(update_fields=["modalidad_ejecucion"])
        pub, _pub_creada = tercerizar_carga(
            servicio, usuario,
            modo_precio=PublicacionCarga.PRECIO_ABIERTO,
            estado=PublicacionCarga.ESTADO_ABIERTA,
        )
        neg.abrir_hilo(lead, neg.HiloNegociacion.TIPO_COMPRA, usuario=usuario, publicacion=pub)
        _auditar(lead, usuario, motivo, {"publicacion": pub.codigo})
    return pub


def derivar_interprovincial_si_corresponde(lead, usuario=None):
    """La carga nacional se publica sola a los transportistas cuando:
      - `derivar_interprovincial_auto` está activo, o
      - `derivar_fuera_horario` está activo y ahora no hay asesor (fuera de horario).
    Idempotente. Se llama desde `pipeline.sync_review_request`.
    """
    if not getattr(lead, "es_interprovincial", False):
        return None

    from apps.servicios.models import ConfiguracionOperaciones
    cfg = ConfiguracionOperaciones.get_solo()
    ya = _publicacion_activa_de(lead)
    if ya:
        return ya
    if cfg.derivar_interprovincial_auto:
        return _publicar_a_transportistas(lead, usuario, "derivada_interprovincial_auto")
    if cfg.derivar_fuera_horario and not _en_horario_atencion():
        return _publicar_a_transportistas(lead, usuario, "derivada_fuera_horario")
    return None


def derivar_por_rechazo_de_precio(lead, usuario=None):
    """El cliente rechazó el precio de una carga nacional y `derivar_al_rechazar_precio`
    está activo → se publica a transportistas para que oferten. Devuelve la
    `PublicacionCarga`, o None (y el caller abre la negociación con el asesor)."""
    if not getattr(lead, "es_interprovincial", False):
        return None
    from apps.servicios.models import ConfiguracionOperaciones
    if not ConfiguracionOperaciones.get_solo().derivar_al_rechazar_precio:
        return None
    return _publicar_a_transportistas(lead, usuario, "derivada_por_rechazo_cliente")


# ---------------------------------------------------------------------------
# Fase 2: identificación de transportistas — sin bot todavía, solo detecta y
# enruta. El bot de clientes NUNCA debe ver estos mensajes.
# ---------------------------------------------------------------------------

# Exige el prefijo OFERTA junto al código — un código suelto (p.ej. "A47" sin
# "OFERTA") NUNCA activa nada. Tolerante a mayúsculas/minúsculas y a guion,
# dos puntos o espacios entre "OFERTA" y el código.
_OFERTA_RE = re.compile(r"OFERTA[\s\-:]*([A-Za-z]\d{1,3})", re.IGNORECASE)


def extraer_codigo_oferta(texto):
    """Código normalizado (ej. 'A47') si el texto trae el prefijo OFERTA
    junto a un código con esa forma, o None si no lo trae. Normaliza
    variantes de dígitos (p.ej. 'OFERTA A5' -> 'A05') para tolerar errores
    de tipeo menores, pero NUNCA marca nada sin el prefijo — el umbral para
    activar es_transportista es alto a propósito (ver marcar_transportista)."""
    if not texto:
        return None
    match = _OFERTA_RE.search(texto)
    if not match:
        return None
    crudo = match.group(1).upper()
    letra, digitos = crudo[0], crudo[1:]
    return f"{letra}{int(digitos):02d}"


def marcar_transportista(cliente, usuario=None):
    """Marca es_transportista=True. usuario=None significa detección
    automática (Fase 2 marcando por una OFERTA-<código> válida); un usuario
    real significa que un asesor lo marcó a mano desde la ficha del
    contacto. Idempotente — no reescribe la auditoría si ya estaba marcado."""
    if cliente.es_transportista:
        return
    cliente.es_transportista = True
    cliente.es_transportista_marcado_por = usuario
    cliente.es_transportista_marcado_en = timezone.now()
    cliente.save(update_fields=[
        "es_transportista",
        "es_transportista_marcado_por",
        "es_transportista_marcado_en",
    ])


def desmarcar_transportista(cliente, usuario):
    """Reversión manual — SIEMPRE la hace un humano (nunca automática). Es
    la vía de escape obligatoria si un cliente real quedó marcado por
    error: sin esto, es_transportista siendo pegajoso lo dejaría atrapado
    en el bot equivocado sin salida."""
    cliente.es_transportista = False
    cliente.es_transportista_marcado_por = usuario
    cliente.es_transportista_marcado_en = timezone.now()
    cliente.save(update_fields=[
        "es_transportista",
        "es_transportista_marcado_por",
        "es_transportista_marcado_en",
    ])


def _registrar_codigo_no_encontrado(conversacion, mensaje, codigo):
    """El mensaje traía 'OFERTA-<código>' pero el código no corresponde a
    ninguna publicación abierta (typo, publicación ya cerrada, o código
    inventado). No se marca nada — se deja registro para que un asesor lo
    revise, reutilizando AuditoriaWhatsApp (ya existe, no hace falta modelo
    nuevo)."""
    from apps.whatsapp.models import AuditoriaWhatsApp

    AuditoriaWhatsApp.objects.create(
        conversacion=conversacion,
        evento="tercerizacion_codigo_no_encontrado",
        detalle={
            "codigo": codigo,
            "mensaje_id": mensaje.id,
            "contenido": (mensaje.contenido or "")[:200],
        },
    )


def identificar_posible_transportista(conversacion, mensaje):
    """Punto de enganche llamado desde el pipeline de bot ANTES de decidir
    si el mensaje va al bot de clientes (Fase 2: solo identifica y enruta,
    no responde nada — eso es Fase 3).

    Devuelve True si esta conversación debe tratarse como transportista
    (ya lo era, o se acaba de identificar con este mensaje) — en ese caso
    el caller NUNCA debe dejar pasar el mensaje al bot de clientes."""
    cliente = conversacion.cliente
    if not cliente:
        return False
    if cliente.es_transportista:
        return True

    codigo = extraer_codigo_oferta(mensaje.contenido)
    if not codigo:
        return False

    publicacion = PublicacionCarga.objects.filter(
        codigo=codigo,
        estado__in=(
            PublicacionCarga.ESTADO_ABIERTA,
            PublicacionCarga.ESTADO_PUBLICADA,
            PublicacionCarga.ESTADO_CON_OFERTAS,
        ),
    ).first()

    if not publicacion:
        _registrar_codigo_no_encontrado(conversacion, mensaje, codigo)
        return False

    marcar_transportista(cliente, usuario=None)

    from apps.whatsapp.signals import publish_transportista_state_change
    publish_transportista_state_change(conversacion)

    return True
