from apps.whatsapp.models import WhatsAppChannel


def user_roles(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    is_admin = user.groups.filter(name="Administrador").exists()
    is_supervisor = user.groups.filter(name="Supervisor").exists()
    is_asesor = user.groups.filter(name="Asesor de Ventas").exists()
    is_conductor = user.groups.filter(name="Conductor").exists()
    is_ayudante = user.groups.filter(name="Ayudante").exists()
    canales = list(WhatsAppChannel.objects.filter(activo=True).values('id', 'nombre'))
    channel_id = request.GET.get('channel')
    header_channel_id = int(channel_id) if channel_id and channel_id.isdigit() else None
    return {
        "is_admin": is_admin,
        "is_supervisor": is_supervisor,
        "is_asesor": is_asesor,
        "is_conductor": is_conductor,
        "is_ayudante": is_ayudante,
        "header_canales": canales,
        "header_channel_id": header_channel_id,
    }

