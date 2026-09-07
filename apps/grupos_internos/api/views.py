"""API v2 del chat de equipo interno.

Cualquier usuario autenticado que sea miembro de un grupo (o Administrador/
Supervisor, para poder administrar) puede ver y mandar mensajes en ese grupo.
Crear grupos y agregar/quitar miembros está restringido a Administrador/
Supervisor. Ver apps/grupos_internos/models.py para el porqué de que esto sea
100% interno (WhatsApp Business API no permite grupos reales por API).
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exceptions import api_exception_handler

from ..models import GrupoInterno, GrupoMiembro, MensajeGrupoInterno
from . import shapes

User = get_user_model()

TIPOS_MEDIA = {
    "imagen": MensajeGrupoInterno.IMAGEN,
    "video": MensajeGrupoInterno.VIDEO,
    "audio": MensajeGrupoInterno.AUDIO,
    "documento": MensajeGrupoInterno.DOCUMENTO,
}


def _requerir_gestor(user):
    if not shapes.is_manager(user):
        raise PermissionDenied("Solo Administrador o Supervisor pueden hacer esto.")


def _grupo_visible_o_404(user, pk):
    grupo = get_object_or_404(GrupoInterno.objects.filter(activo=True), pk=pk)
    if shapes.is_manager(user) or grupo.membresias.filter(usuario=user).exists():
        return grupo
    raise PermissionDenied("No eres miembro de este grupo.")


class _Base(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return api_exception_handler


class GroupListView(_Base):
    def get(self, request):
        user = request.user
        if shapes.is_manager(user):
            qs = GrupoInterno.objects.filter(activo=True)
        else:
            qs = GrupoInterno.objects.filter(activo=True, membresias__usuario=user)
        qs = qs.distinct().order_by("nombre")
        return Response([shapes.group_item(g, user) for g in qs])

    def post(self, request):
        _requerir_gestor(request.user)
        nombre = (request.data.get("name") or "").strip()
        if not nombre:
            raise ValidationError({"name": "Ingresa un nombre para el grupo."})
        grupo = GrupoInterno.objects.create(nombre=nombre, creado_por=request.user)
        GrupoMiembro.objects.create(grupo=grupo, usuario=request.user, agregado_por=request.user)
        return Response(shapes.group_item(grupo, request.user), status=201)


class GroupDetailView(_Base):
    def get(self, request, pk):
        grupo = _grupo_visible_o_404(request.user, pk)
        return Response(shapes.group_item(grupo, request.user))

    def patch(self, request, pk):
        # Archivar es una preferencia de vista compartida por el equipo (igual
        # que archivar una conversación de cliente) — cualquier miembro puede
        # hacerlo. Renombrar / activar-desactivar el grupo sí requiere gestor.
        if set(request.data.keys()) - {"archived"}:
            _requerir_gestor(request.user)
            grupo = get_object_or_404(GrupoInterno, pk=pk)
        else:
            grupo = _grupo_visible_o_404(request.user, pk)

        update_fields = []
        if "name" in request.data:
            nombre = (request.data.get("name") or "").strip()
            if not nombre:
                raise ValidationError({"name": "Ingresa un nombre para el grupo."})
            grupo.nombre = nombre
            update_fields.append("nombre")
        if "active" in request.data:
            grupo.activo = bool(request.data.get("active"))
            update_fields.append("activo")
        if "archived" in request.data:
            grupo.archivado = bool(request.data.get("archived"))
            update_fields.append("archivado")
        if update_fields:
            grupo.save(update_fields=update_fields)
        return Response(shapes.group_item(grupo, request.user))


class GroupMembersView(_Base):
    def post(self, request, pk):
        _requerir_gestor(request.user)
        grupo = get_object_or_404(GrupoInterno, pk=pk)
        user_id = request.data.get("userId")
        member = get_object_or_404(User, pk=user_id)
        GrupoMiembro.objects.get_or_create(
            grupo=grupo, usuario=member, defaults={"agregado_por": request.user},
        )
        return Response(shapes.group_item(grupo, request.user), status=201)


class GroupMemberDetailView(_Base):
    def delete(self, request, pk, user_id):
        _requerir_gestor(request.user)
        grupo = get_object_or_404(GrupoInterno, pk=pk)
        GrupoMiembro.objects.filter(grupo=grupo, usuario_id=user_id).delete()
        return Response(shapes.group_item(grupo, request.user))


class AvailableUsersView(_Base):
    def get(self, request):
        _requerir_gestor(request.user)
        qs = User.objects.filter(is_active=True).order_by("first_name", "username")
        return Response([shapes.user_item(u) for u in qs])


class GroupMessageListView(_Base):
    def get(self, request, pk):
        grupo = _grupo_visible_o_404(request.user, pk)
        qs = grupo.mensajes.select_related("autor").order_by("creado_en")
        after_id = request.query_params.get("afterId")
        if after_id:
            qs = qs.filter(id__gt=after_id)
        else:
            qs = qs.order_by("-creado_en")[:50]
            qs = reversed(list(qs))
        return Response([shapes.message_item(m) for m in qs])

    def post(self, request, pk):
        grupo = _grupo_visible_o_404(request.user, pk)
        texto = (request.data.get("text") or "").strip()
        if not texto:
            raise ValidationError({"text": "Escribe un mensaje."})
        mensaje = MensajeGrupoInterno.objects.create(
            grupo=grupo, autor=request.user, tipo=MensajeGrupoInterno.TEXTO, contenido=texto,
        )
        return Response(shapes.message_item(mensaje), status=201)


class GroupMessageMediaView(_Base):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk):
        grupo = _grupo_visible_o_404(request.user, pk)
        archivo = request.FILES.get("file")
        if not archivo:
            raise ValidationError({"file": "Selecciona un archivo."})
        tipo = TIPOS_MEDIA.get(request.data.get("type"), MensajeGrupoInterno.DOCUMENTO)
        mensaje = MensajeGrupoInterno.objects.create(
            grupo=grupo, autor=request.user, tipo=tipo,
            archivo=archivo, mime_type=archivo.content_type or "",
            filename=archivo.name, file_size=archivo.size,
        )
        return Response(shapes.message_item(mensaje), status=201)
