"""Serialización ES→EN del chat de equipo interno. Ver docs/PATRON-API-VUE.md."""
MANAGE_ROLES = ("Administrador", "Supervisor")


def is_manager(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=MANAGE_ROLES).exists()


def _user_name(user):
    if user is None:
        return "Usuario eliminado"
    return user.get_full_name() or user.username


def user_item(user):
    return {
        "id": user.id,
        "name": _user_name(user),
        "username": user.username,
    }


def _preview_text(mensaje):
    if mensaje is None:
        return None
    if mensaje.tipo == "texto":
        return mensaje.contenido or ""
    return {
        "imagen": "📷 Foto", "video": "🎥 Video",
        "audio": "🎤 Audio", "documento": "📄 Documento",
    }.get(mensaje.tipo, "Mensaje")


def group_item(grupo, viewer):
    members = list(grupo.membresias.select_related("usuario").order_by("usuario__first_name", "usuario__username"))
    ultimo = grupo.mensajes.select_related("autor").order_by("-creado_en").first()
    return {
        "id": grupo.id,
        "name": grupo.nombre,
        "createdBy": _user_name(grupo.creado_por),
        "createdAt": grupo.creado_en.isoformat(),
        "memberCount": len(members),
        "members": [user_item(m.usuario) for m in members if m.usuario_id],
        "canManage": is_manager(viewer),
        "archived": grupo.archivado,
        "lastMessagePreview": _preview_text(ultimo),
        "lastMessageAt": ultimo.creado_en.isoformat() if ultimo else grupo.creado_en.isoformat(),
        "lastMessageAuthor": _user_name(ultimo.autor) if ultimo else None,
    }


def message_item(mensaje):
    return {
        "id": mensaje.id,
        "groupId": mensaje.grupo_id,
        "authorId": mensaje.autor_id,
        "authorName": _user_name(mensaje.autor),
        "type": mensaje.tipo,
        "text": mensaje.contenido or None,
        "fileUrl": f"/media/grupos/{mensaje.id}/" if mensaje.archivo else None,
        "fileName": mensaje.filename or None,
        "fileSize": mensaje.file_size or None,
        "mimeType": mensaje.mime_type or None,
        "createdAt": mensaje.creado_en.isoformat(),
    }
