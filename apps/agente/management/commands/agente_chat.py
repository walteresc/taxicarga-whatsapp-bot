"""Conversar con el orquestador del agente por consola (para tantear el loop).

    python manage.py agente_chat --principal walter --mensaje "resumime la negociación de CRG-42"
    python manage.py agente_chat --principal sistema --mensaje "..." --conversacion 7
    python manage.py agente_chat --principal walter --interactivo
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.agente.models import ConversacionAgente
from apps.agente.orquestador import Orquestador
from apps.agente.principal import PrincipalNoResoluble, principal_desde_usuario, principal_sistema

User = get_user_model()


class Command(BaseCommand):
    help = "Conversa con el orquestador del agente."

    def add_arguments(self, parser):
        parser.add_argument("--principal", required=True, help="username o 'sistema'.")
        parser.add_argument("--mensaje", help="Un mensaje (one-shot).")
        parser.add_argument("--conversacion", type=int, help="ID de conversación a continuar.")
        parser.add_argument("--interactivo", action="store_true", help="REPL; línea vacía para salir.")

    def handle(self, *a, **o):
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
        self.stdout.write(self.style.WARNING(f"principal: {principal}"))

        conv = None
        if o["conversacion"]:
            conv = ConversacionAgente.objects.filter(pk=o["conversacion"]).first()
            if conv is None:
                raise CommandError("Conversación no encontrada.")

        if o["interactivo"]:
            while True:
                try:
                    linea = input("> ").strip()
                except EOFError:
                    break
                if not linea:
                    break
                conv = self._turno(principal, conv, linea)
        elif o["mensaje"]:
            self._turno(principal, conv, o["mensaje"])
        else:
            raise CommandError("Pasá --mensaje o --interactivo.")

    def _turno(self, principal, conv, mensaje):
        r = Orquestador(principal, conversacion=conv).responder(mensaje)
        self.stdout.write(self.style.SUCCESS(f"\n{r.texto}\n"))
        if r.ejecutadas:
            self.stdout.write(f"  ejecutadas: {json.dumps(r.ejecutadas, ensure_ascii=False)}")
        if r.propuestas:
            self.stdout.write(f"  propuestas: {json.dumps(r.propuestas, ensure_ascii=False)}")
        self.stdout.write(self.style.HTTP_INFO(
            f"  (conv {r.conversacion_id}, {r.iteraciones} iteraciones)"))
        return ConversacionAgente.objects.get(pk=r.conversacion_id)
