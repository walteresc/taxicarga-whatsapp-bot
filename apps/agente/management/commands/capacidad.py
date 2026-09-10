"""Ejecutar una capacidad del agente a mano (para probar / tantear).

    python manage.py capacidad --list
    python manage.py capacidad ver_carga --principal walter --params '{"codigo": "CRG-0042"}'
    python manage.py capacidad calcular_precio --principal sistema --params '{"codigo": "CRG-0042"}'
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.agente.principal import PrincipalNoResoluble, principal_desde_usuario, principal_sistema
from apps.agente.registro import catalogo, ejecutar

User = get_user_model()


class Command(BaseCommand):
    help = "Ejecuta una capacidad del agente (o --list para ver el catálogo)."

    def add_arguments(self, parser):
        parser.add_argument("nombre", nargs="?", help="Nombre de la capacidad.")
        parser.add_argument("--principal", help="username, o 'sistema'.")
        parser.add_argument("--params", default="{}", help="JSON con los argumentos.")
        parser.add_argument("--list", action="store_true", help="Lista el catálogo.")

    def handle(self, *args, **o):
        if o["list"] or not o["nombre"]:
            for c in catalogo():
                perfiles = ", ".join(sorted(c.perfiles))
                self.stdout.write(f"{c.efecto:20} {c.nombre:26} [{perfiles}]")
                if c.descripcion:
                    self.stdout.write(f"{'':20} {c.descripcion}")
            self.stdout.write(f"\n{len(catalogo())} capacidades.")
            return

        if not o["principal"]:
            raise CommandError("Falta --principal (username o 'sistema').")
        if o["principal"] == "sistema":
            principal = principal_sistema()
        else:
            user = User.objects.filter(username=o["principal"]).first()
            if user is None:
                raise CommandError(f"No existe el usuario '{o['principal']}'.")
            try:
                principal = principal_desde_usuario(user)
            except PrincipalNoResoluble as e:
                raise CommandError(str(e))

        try:
            cap_args = json.loads(o["params"])
        except json.JSONDecodeError as e:
            raise CommandError(f"--params no es JSON válido: {e}")

        res = ejecutar(o["nombre"], principal, **cap_args)
        self.stdout.write(f"principal: {principal}")
        self.stdout.write(json.dumps(res.as_dict(), ensure_ascii=False, indent=2, default=str))
