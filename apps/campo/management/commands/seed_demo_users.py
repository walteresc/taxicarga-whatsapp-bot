from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


class Command(BaseCommand):
    help = "Crea o actualiza usuarios demo y grupos con roles"

    def handle(self, *args, **options):
        grupos = ["Administrador", "Supervisor", "Asesor de Ventas", "Conductor", "Ayudante"]

        for nombre_grupo in grupos:
            grupo, created = Group.objects.get_or_create(name=nombre_grupo)
            if created:
                self.stdout.write(f"Grupo creado: {nombre_grupo}")

        usuarios_demo = [
            {"username": "admin", "password": "Admin123*", "grupo": "Administrador"},
            {"username": "supervisor", "password": "Supervisor123*", "grupo": "Supervisor"},
            {"username": "demo_vendedor", "password": "Demo123*", "grupo": "Asesor de Ventas"},
            {"username": "conductor_demo", "password": "Conductor123*", "grupo": "Conductor"},
            {"username": "ayudante_demo", "password": "Ayudante123*", "grupo": "Ayudante"},
        ]

        for user_data in usuarios_demo:
            try:
                user = User.objects.get(username=user_data["username"])
                user.set_password(user_data["password"])
                user.groups.clear()
                grupo = Group.objects.get(name=user_data["grupo"])
                user.groups.add(grupo)
                user.save()
                self.stdout.write(f"Actualizada contraseña y grupo usuario: {user.username}")
            except User.DoesNotExist:
                user = User.objects.create_user(username=user_data["username"], password=user_data["password"])
                grupo = Group.objects.get(name=user_data["grupo"])
                user.groups.add(grupo)
                user.save()
                self.stdout.write(f"Usuario creado: {user.username} con grupo {user_data['grupo']}")

        self.stdout.write("Usuarios demo procesados correctamente.")
