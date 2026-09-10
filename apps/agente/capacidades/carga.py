"""Capacidades sobre una carga: notas, datos faltantes, reserva, cierre de precio,
derivación a tercerización."""
from apps.agente.registro import EFECTO_CRITICO, EFECTO_LECTURA, EFECTO_REVERSIBLE, capacidad

from . import _alcance


@capacidad("dejar_nota", perfiles=["asesor", "sistema"], efecto=EFECTO_REVERSIBLE, params={
    "codigo": {"description": "Código de la carga."},
    "texto": {"description": "Contenido de la nota."},
})
def dejar_nota(principal, codigo, texto):
    """Agrega una nota interna a la carga (queda en el historial del lead)."""
    from apps.cotizador.pipeline import _auditar

    texto = (texto or "").strip()
    if not texto:
        from apps.agente.errores import ArgInvalido
        raise ArgInvalido("La nota está vacía.")
    lead = _alcance.carga_para(principal, codigo)
    _auditar(lead, principal.user, "nota_agente", {"texto": texto})
    return {"ok": True, "_lead": lead}


@capacidad("marcar_datos_faltantes", perfiles=["asesor", "transportista", "cliente", "sistema"],
           efecto=EFECTO_LECTURA, params={"codigo": {"description": "Código de la carga."}})
def marcar_datos_faltantes(principal, codigo):
    """Qué le falta a una carga para poder reservarla."""
    from apps.ia.conversation_policy import booking_missing_fields

    _ETIQUETAS = {
        "cliente_nombre": "nombre del cliente",
        "direccion_origen": "dirección de origen",
        "direccion_destino": "dirección de destino",
        "fecha_servicio": "fecha del servicio",
        "horario_servicio": "horario del servicio",
    }
    if principal.tipo == "transportista":
        svc = _alcance.reserva_para(principal, codigo)
        lead = svc.lead_origen
    else:
        lead = _alcance.carga_para(principal, codigo)
    faltan = booking_missing_fields(lead)
    legibles = [_ETIQUETAS.get(f, f.replace("_", " ")) for f in faltan]
    return {"completa": not faltan, "faltan": faltan, "faltan_legible": legibles, "_lead": lead}


@capacidad("crear_reserva", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO,
           params={"codigo": {"description": "Código de la carga."}})
def crear_reserva(principal, codigo):
    """Crea la reserva (servicio) de una carga. Falla si faltan datos obligatorios."""
    from apps.servicios.services import crear_servicio_desde_lead

    lead = _alcance.carga_para(principal, codigo)
    servicio, creado = crear_servicio_desde_lead(lead, usuario=principal.user)
    return {"reserva": servicio.codigo, "creada": creado, "_lead": lead, "_servicio": servicio}


@capacidad("cerrar_precio", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO, params={
    "codigo": {"description": "Código de la carga."},
    "monto": {"type": "number", "description": "Precio de venta acordado (S/)."},
    "nota": {"description": "Condiciones / nota opcional."},
})
def cerrar_precio(principal, codigo, monto, nota=""):
    """Cierra el precio de venta con el cliente y crea la reserva. Si el monto
    difiere de la última oferta, manda una revisión a ese precio."""
    from apps.cotizador.commercial import cerrar_precio_de_cotizacion

    lead = _alcance.carga_para(principal, codigo)
    cot = lead.cotizaciones_comerciales.order_by("-actualizada_en").first()
    if cot is None:
        from apps.agente.errores import NoEncontrado
        raise NoEncontrado("La carga no tiene una cotización comercial para cerrar.")
    servicio, creada = cerrar_precio_de_cotizacion(cot, monto, usuario=principal.user, nota=nota)
    return {"reserva": servicio.codigo, "creada": creada, "_lead": lead, "_servicio": servicio}


@capacidad("derivar_a_tercerizacion", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO, params={
    "codigo": {"description": "Código de la carga."},
    "modo_precio": {"enum": ["fijo", "referencial", "abierto"]},
    "precio_ref": {"type": "number", "description": "Costo objetivo hacia el transportista (si fijo/referencial)."},
})
def derivar_a_tercerizacion(principal, codigo, modo_precio="abierto", precio_ref=None):
    """Marca la carga como tercerizada y crea la publicación en borrador (la
    publica el Despacho). `modo_precio`: fijo | referencial | abierto."""
    from apps.cotizador.commercial import derivar_cotizacion_a_tercerizacion

    lead = _alcance.carga_para(principal, codigo)
    cot = lead.cotizaciones_comerciales.order_by("-actualizada_en").first()
    if cot is None:
        from apps.agente.errores import NoEncontrado
        raise NoEncontrado("La carga no tiene una cotización comercial para derivar.")
    pub, creada = derivar_cotizacion_a_tercerizacion(
        cot, modo_precio=modo_precio, usuario=principal.user, precio_ref=precio_ref,
    )
    return {"publicacion": pub.codigo, "creada": creada, "_lead": lead}
