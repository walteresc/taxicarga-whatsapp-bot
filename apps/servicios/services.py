from .models import Servicio, SERVICIO_PENDIENTE


def crear_servicio_desde_lead(lead, usuario=None):
    if hasattr(lead, "servicio_generado") and lead.servicio_generado:
        return lead.servicio_generado, False

    servicio = Servicio.objects.create(
        lead_origen=lead,
        cliente=lead.cliente,
        whatsapp_channel=lead.whatsapp_channel,
        asesor=usuario or lead.vendedor_asignado,
        estado=SERVICIO_PENDIENTE,
        tipo_servicio=lead.tipo_servicio,
        distrito_origen=lead.distrito_origen,
        distrito_destino=lead.distrito_destino,
        direccion_origen=lead.direccion_origen,
        direccion_destino=lead.direccion_destino,
        piso_origen=lead.piso_origen,
        piso_destino=lead.piso_destino,
        acceso_origen=lead.acceso_origen,
        acceso_destino=lead.acceso_destino,
        lista_objetos=lead.lista_objetos,
        objetos_pesados=lead.objetos_pesados,
        incluye_personal_carga=lead.incluye_personal_carga,
        requiere_desarmado=lead.requiere_desarmado,
        peso_carga_kg=lead.peso_carga_kg,
        volumen_carga_m3=lead.volumen_carga_m3,
        fecha_servicio=lead.fecha_servicio,
        horario_servicio=lead.horario_servicio,
        precio_cotizado=lead.precio_cotizado,
        precio_final=lead.precio_final,
        dni_ruc=lead.dni_reserva,
        observaciones=lead.observaciones,
    )
    return servicio, True
