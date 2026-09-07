"""Crea los grupos de rol canónicos del proyecto. Idempotente.

    python manage.py seed_roles

Los permisos por sección se resuelven en código (permissions.has_role /
apps.api.permissions.HasAnyRole), así que estos grupos solo necesitan existir y
tener miembros. No se asignan Permissions de Django a los grupos.
"""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

ROLES = [
    "Administrador",
    "Supervisor",
    "Asesor de Ventas",
    "Conductor",
    "Ayudante",
]


class Command(BaseCommand):
    help = "Crea los grupos de rol canónicos (idempotente)."

    def handle(self, *args, **options):
        creados = []
        for nombre in ROLES:
            _group, created = Group.objects.get_or_create(name=nombre)
            if created:
                creados.append(nombre)
        if creados:
            self.stdout.write(self.style.SUCCESS(f"Creados: {', '.join(creados)}"))
        else:
            self.stdout.write("Todos los grupos ya existían.")
        self.stdout.write(f"Grupos actuales: {sorted(Group.objects.values_list('name', flat=True))}")
