"""API v2 del chat de equipo interno. Cubre: crear grupo, agregar/quitar
miembros, mandar/leer mensajes (texto y archivo), y los permisos (miembro vs
gestor vs nadie)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from .models import GrupoInterno, GrupoMiembro, MensajeGrupoInterno

User = get_user_model()


def _user(username, role=None):
    u = User.objects.create_user(username, password="x")
    if role:
        g, _ = Group.objects.get_or_create(name=role)
        u.groups.add(g)
    return u


class GroupCrudTests(APITestCase):
    def setUp(self):
        self.admin = _user("admin1", "Administrador")
        self.asesor = _user("asesor1", "Asesor de Ventas")
        self.conductor = _user("conductor1", "Conductor")
        self.client.force_login(self.admin)

    def test_admin_crea_grupo_y_queda_como_miembro(self):
        r = self.client.post("/api/v2/groups/", {"name": "Ventas"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["name"], "Ventas")
        self.assertEqual(r.data["memberCount"], 1)
        self.assertTrue(GrupoMiembro.objects.filter(usuario=self.admin).exists())

    def test_sin_rol_no_puede_crear_grupo(self):
        self.client.force_login(self.conductor)
        r = self.client.post("/api/v2/groups/", {"name": "Ventas"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_nombre_vacio_rechaza(self):
        r = self.client.post("/api/v2/groups/", {"name": "  "}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_agregar_y_quitar_miembro(self):
        grupo = GrupoInterno.objects.create(nombre="Oficina", creado_por=self.admin)
        r = self.client.post(f"/api/v2/groups/{grupo.id}/members", {"userId": self.conductor.id}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(GrupoMiembro.objects.filter(grupo=grupo, usuario=self.conductor).exists())

        r2 = self.client.delete(f"/api/v2/groups/{grupo.id}/members/{self.conductor.id}")
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertFalse(GrupoMiembro.objects.filter(grupo=grupo, usuario=self.conductor).exists())

    def test_agregar_miembro_dos_veces_no_duplica(self):
        grupo = GrupoInterno.objects.create(nombre="Oficina", creado_por=self.admin)
        self.client.post(f"/api/v2/groups/{grupo.id}/members", {"userId": self.conductor.id}, format="json")
        self.client.post(f"/api/v2/groups/{grupo.id}/members", {"userId": self.conductor.id}, format="json")
        self.assertEqual(GrupoMiembro.objects.filter(grupo=grupo, usuario=self.conductor).count(), 1)

    def test_conductor_no_puede_agregar_miembros(self):
        grupo = GrupoInterno.objects.create(nombre="Oficina", creado_por=self.admin)
        self.client.force_login(self.conductor)
        r = self.client.post(f"/api/v2/groups/{grupo.id}/members", {"userId": self.asesor.id}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_miembro_puede_archivar_sin_ser_gestor(self):
        grupo = GrupoInterno.objects.create(nombre="Oficina", creado_por=self.admin)
        GrupoMiembro.objects.create(grupo=grupo, usuario=self.conductor, agregado_por=self.admin)
        self.client.force_login(self.conductor)
        r = self.client.patch(f"/api/v2/groups/{grupo.id}/", {"archived": True}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        grupo.refresh_from_db()
        self.assertTrue(grupo.archivado)

    def test_miembro_no_puede_renombrar(self):
        grupo = GrupoInterno.objects.create(nombre="Oficina", creado_por=self.admin)
        GrupoMiembro.objects.create(grupo=grupo, usuario=self.conductor, agregado_por=self.admin)
        self.client.force_login(self.conductor)
        r = self.client.patch(f"/api/v2/groups/{grupo.id}/", {"name": "Otro nombre"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_gestor_puede_renombrar(self):
        grupo = GrupoInterno.objects.create(nombre="Ventas", creado_por=self.admin)
        r = self.client.patch(f"/api/v2/groups/{grupo.id}/", {"name": "Ventas Lima"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["name"], "Ventas Lima")
        grupo.refresh_from_db()
        self.assertEqual(grupo.nombre, "Ventas Lima")

    def test_renombrar_con_nombre_vacio_rechaza(self):
        grupo = GrupoInterno.objects.create(nombre="Ventas", creado_por=self.admin)
        r = self.client.patch(f"/api/v2/groups/{grupo.id}/", {"name": "   "}, format="json")
        self.assertEqual(r.status_code, 400)
        grupo.refresh_from_db()
        self.assertEqual(grupo.nombre, "Ventas")

    def test_lista_incluye_preview_del_ultimo_mensaje(self):
        grupo = GrupoInterno.objects.create(nombre="Oficina", creado_por=self.admin)
        GrupoMiembro.objects.create(grupo=grupo, usuario=self.admin, agregado_por=self.admin)
        MensajeGrupoInterno.objects.create(grupo=grupo, autor=self.admin, tipo="texto", contenido="reunión a las 3pm")
        r = self.client.get("/api/v2/groups/")
        item = next(g for g in r.data if g["id"] == grupo.id)
        self.assertEqual(item["lastMessagePreview"], "reunión a las 3pm")
        self.assertFalse(item["archived"])

    def test_available_users_solo_gestor(self):
        r = self.client.get("/api/v2/groups/users")
        self.assertEqual(r.status_code, 200)
        usernames = [u["username"] for u in r.data]
        self.assertIn("conductor1", usernames)

        self.client.force_login(self.conductor)
        r2 = self.client.get("/api/v2/groups/users")
        self.assertEqual(r2.status_code, 403)


class GroupVisibilityTests(APITestCase):
    def setUp(self):
        self.admin = _user("admin2", "Administrador")
        self.miembro = _user("miembro1", "Asesor de Ventas")
        self.ajeno = _user("ajeno1", "Asesor de Ventas")
        self.grupo = GrupoInterno.objects.create(nombre="Ventas", creado_por=self.admin)
        GrupoMiembro.objects.create(grupo=self.grupo, usuario=self.miembro, agregado_por=self.admin)

    def test_lista_solo_muestra_mis_grupos(self):
        self.client.force_login(self.miembro)
        r = self.client.get("/api/v2/groups/")
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["id"], self.grupo.id)

    def test_ajeno_no_ve_el_grupo_en_la_lista(self):
        self.client.force_login(self.ajeno)
        r = self.client.get("/api/v2/groups/")
        self.assertEqual(r.data, [])

    def test_ajeno_no_puede_ver_detalle_ni_mensajes(self):
        self.client.force_login(self.ajeno)
        r = self.client.get(f"/api/v2/groups/{self.grupo.id}/")
        self.assertEqual(r.status_code, 403)
        r2 = self.client.get(f"/api/v2/groups/{self.grupo.id}/messages")
        self.assertEqual(r2.status_code, 403)

    def test_gestor_ve_todos_los_grupos_aunque_no_sea_miembro(self):
        self.client.force_login(self.admin)
        r = self.client.get("/api/v2/groups/")
        ids = [g["id"] for g in r.data]
        self.assertIn(self.grupo.id, ids)


class GroupMessagingTests(APITestCase):
    def setUp(self):
        self.admin = _user("admin3", "Administrador")
        self.miembro = _user("miembro2", "Asesor de Ventas")
        self.ajeno = _user("ajeno2", "Asesor de Ventas")
        self.grupo = GrupoInterno.objects.create(nombre="Ventas", creado_por=self.admin)
        GrupoMiembro.objects.create(grupo=self.grupo, usuario=self.miembro, agregado_por=self.admin)
        self.client.force_login(self.miembro)

    def test_mandar_texto(self):
        r = self.client.post(f"/api/v2/groups/{self.grupo.id}/messages", {"text": "hola equipo"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["text"], "hola equipo")
        self.assertEqual(r.data["authorName"], self.miembro.username)

    def test_texto_vacio_rechaza(self):
        r = self.client.post(f"/api/v2/groups/{self.grupo.id}/messages", {"text": "  "}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_ajeno_no_puede_mandar_mensaje(self):
        self.client.force_login(self.ajeno)
        r = self.client.post(f"/api/v2/groups/{self.grupo.id}/messages", {"text": "hola"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_leer_mensajes_en_orden(self):
        MensajeGrupoInterno.objects.create(grupo=self.grupo, autor=self.admin, tipo="texto", contenido="uno")
        MensajeGrupoInterno.objects.create(grupo=self.grupo, autor=self.miembro, tipo="texto", contenido="dos")
        r = self.client.get(f"/api/v2/groups/{self.grupo.id}/messages")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([m["text"] for m in r.data], ["uno", "dos"])

    def test_leer_mensajes_despues_de_un_id(self):
        m1 = MensajeGrupoInterno.objects.create(grupo=self.grupo, autor=self.admin, tipo="texto", contenido="uno")
        MensajeGrupoInterno.objects.create(grupo=self.grupo, autor=self.miembro, tipo="texto", contenido="dos")
        r = self.client.get(f"/api/v2/groups/{self.grupo.id}/messages", {"afterId": m1.id})
        self.assertEqual([m["text"] for m in r.data], ["dos"])

    def test_mandar_imagen(self):
        archivo = SimpleUploadedFile("foto.jpg", b"contenido-fake-jpg", content_type="image/jpeg")
        r = self.client.post(
            f"/api/v2/groups/{self.grupo.id}/messages/media",
            {"file": archivo, "type": "imagen"},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["type"], "imagen")
        self.assertTrue(r.data["fileUrl"].startswith("/media/grupos/"))

    def test_media_proxy_bloquea_a_quien_no_es_miembro(self):
        archivo = SimpleUploadedFile("foto.jpg", b"contenido-fake-jpg", content_type="image/jpeg")
        r = self.client.post(
            f"/api/v2/groups/{self.grupo.id}/messages/media",
            {"file": archivo, "type": "imagen"},
            format="multipart",
        )
        url = r.data["fileUrl"]
        self.client.force_login(self.ajeno)
        r2 = self.client.get(url)
        self.assertEqual(r2.status_code, 404)

    def test_media_proxy_sirve_el_archivo_a_un_miembro(self):
        archivo = SimpleUploadedFile("foto.jpg", b"contenido-fake-jpg", content_type="image/jpeg")
        r = self.client.post(
            f"/api/v2/groups/{self.grupo.id}/messages/media",
            {"file": archivo, "type": "imagen"},
            format="multipart",
        )
        url = r.data["fileUrl"]
        r2 = self.client.get(url)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(b"".join(r2.streaming_content), b"contenido-fake-jpg")
