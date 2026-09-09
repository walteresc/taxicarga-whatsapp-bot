"""Aditivo e idempotente: a cada usuario que hoy está en el grupo
'Administrador' le agrega también 'Gerencia' y 'Admin de sistema'.

    python manage.py split_admin
    python manage.py split_admin --dry-run

NO quita a nadie de 'Administrador' — ese grupo se mantiene como superrol de
compatibilidad mientras las pantallas migran a roles granulares (F4+).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Da Gerencia + Admin de sistema a los administradores actuales (aditivo)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué haría.")

    def handle(self, *args, **options):
        try:
            admin_g = Group.objects.get(name="Administrador")
        except Group.DoesNotExist:
            self.stderr.write("No existe el grupo 'Administrador'. Corré primero: manage.py seed_roles")
            return

        gerencia = Group.objects.get_or_create(name="Gerencia")[0]
        sistema = Group.objects.get_or_create(name="Admin de sistema")[0]

        usuarios = list(User.objects.filter(groups=admin_g))
        if not usuarios:
            self.stdout.write("Ningún usuario en 'Administrador'.")
            return

        for u in usuarios:
            faltan = [g.name for g in (gerencia, sistema) if not u.groups.filter(pk=g.pk).exists()]
            etiqueta = f"  {u.username}: +{', +'.join(faltan)}" if faltan else f"  {u.username}: ya tenía ambos"
            self.stdout.write(etiqueta)
            if not options["dry_run"] and faltan:
                u.groups.add(gerencia, sistema)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run: no se guardó nada."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Listo. {len(usuarios)} administrador(es) revisados. 'Administrador' intacto."))
