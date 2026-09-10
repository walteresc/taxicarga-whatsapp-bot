import re

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


def derivar_interprovincial_si_corresponde(lead, usuario=None):
    """Si la carga es interprovincial y el flag de Configuración está activo,
    la publica sola a los transportistas (precio abierto: ellos proponen) en
    cuanto tiene los datos completos, sin que el asesor la cotice. Idempotente
    y sin efectos si falta algún dato. Devuelve la `PublicacionCarga` o None.

    Se llama desde `pipeline.sync_review_request` (que corre en cada save de un
    lead con `requiere_asesor`), así se dispara sola al completarse los datos.
    """
    if not getattr(lead, "es_interprovincial", False):
        return None

    from apps.servicios.models import ConfiguracionOperaciones, Servicio
    if not ConfiguracionOperaciones.get_solo().derivar_interprovincial_auto:
        return None

    servicio = Servicio.objects.filter(lead_origen=lead).first()
    if servicio:
        existente = servicio.publicaciones_tercerizacion.filter(
            estado__in=_ESTADOS_PUBLICACION_ACTIVA,
        ).first()
        if existente:
            return existente

    from apps.ia.conversation_policy import booking_missing_fields
    if booking_missing_fields(lead):
        return None

    from apps.cotizador.pipeline import _auditar
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
        neg.abrir_hilo(
            lead, neg.HiloNegociacion.TIPO_COMPRA, usuario=usuario, publicacion=pub,
        )
        _auditar(lead, usuario, "derivada_interprovincial_auto",
                 {"publicacion": pub.codigo})
    return pub


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
        codigo=codigo, estado=PublicacionCarga.ESTADO_ABIERTA,
    ).first()

    if not publicacion:
        _registrar_codigo_no_encontrado(conversacion, mensaje, codigo)
        return False

    marcar_transportista(cliente, usuario=None)

    from apps.whatsapp.signals import publish_transportista_state_change
    publish_transportista_state_change(conversacion)

    return True
