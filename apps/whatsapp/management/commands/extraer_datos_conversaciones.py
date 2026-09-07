"""Barrido de extracción NLU de datos de servicio de las conversaciones.

FASE 2. Se ejecuta A MANO primero (para validar calidad); luego se automatiza.
NUNCA toca el hot path del webhook. Capturar datos != responder al cliente:
funciona con el bot global PAUSADO.

    python manage.py extraer_datos_conversaciones --dry-run
    python manage.py extraer_datos_conversaciones --dry-run --todas
    python manage.py extraer_datos_conversaciones --dry-run --conv 28
    python manage.py extraer_datos_conversaciones --todas          # ejecución real
"""
import json as _json

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.whatsapp.models import ConversacionWhatsApp
from apps.whatsapp.services_extraccion import (
    conversaciones_pendientes,
    extraer_datos_conversacion,
)


class Command(BaseCommand):
    help = "Extrae datos de servicio de las conversaciones (barrido NLU)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="No escribe nada — solo muestra qué detectaría.")
        parser.add_argument("--todas", action="store_true",
                            help="Procesa TODAS las conversaciones (reproceso retroactivo), "
                                 "no solo las que tienen mensajes nuevos.")
        parser.add_argument("--conv", type=int, default=None,
                            help="Procesa solo la conversación con este id.")
        parser.add_argument("--limit", type=int, default=None,
                            help="Máximo de conversaciones a procesar en esta corrida.")
        parser.add_argument("--json", action="store_true",
                            help="Salida JSON (una línea por conversación).")

    def handle(self, *args, **o):
        dry = o["dry_run"]
        if o["conv"]:
            qs = ConversacionWhatsApp.objects.select_related(
                "cliente", "lead", "channel"
            ).filter(pk=o["conv"])
        else:
            qs = conversaciones_pendientes(todas=o["todas"], limite=o["limit"])

        conversaciones = list(qs)
        if not conversaciones:
            self.stdout.write("Sin conversaciones que procesar.")
            return

        modo = "DRY-RUN (no escribe)" if dry else "EJECUCIÓN REAL"
        self.stdout.write(self.style.WARNING(
            f"== {modo} — {len(conversaciones)} conversación(es) =="
        ))

        resumen = {"con_datos": 0, "alcanzan_umbral": 0, "leads_creados": 0,
                   "leads_actualizados": 0, "errores": 0}

        for conv in conversaciones:
            close_old_connections()
            rep = extraer_datos_conversacion(conv, dry_run=dry)

            if o["json"]:
                self.stdout.write(_json.dumps(rep, ensure_ascii=False, default=str))
            else:
                self._print_report(rep)

            if rep["error"]:
                resumen["errores"] += 1
            if rep["detectado"]:
                resumen["con_datos"] += 1
            if rep["alcanza_umbral"]:
                resumen["alcanzan_umbral"] += 1
            if "creado" in rep["lead_accion"] or "crearía" in rep["lead_accion"]:
                resumen["leads_creados"] += 1
            elif "actualiz" in rep["lead_accion"]:
                resumen["leads_actualizados"] += 1

        self.stdout.write(self.style.SUCCESS(
            "\n== RESUMEN ==\n"
            f"  con datos detectados ....... {resumen['con_datos']}\n"
            f"  alcanzan umbral (cotizable). {resumen['alcanzan_umbral']}\n"
            f"  leads {'que se crearían' if dry else 'creados'} ...... {resumen['leads_creados']}\n"
            f"  leads actualizados ......... {resumen['leads_actualizados']}\n"
            f"  errores ................... {resumen['errores']}"
        ))
        if dry:
            self.stdout.write(self.style.WARNING(
                "\nDRY-RUN: no se escribió nada. Repite sin --dry-run para aplicar."
            ))

    def _print_report(self, r):
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(
            f"── conv {r['conversacion_id']}  ·  {r['cliente']}  {r['telefono']}  "
            f"({r['mensajes_analizados']} msgs)"
        ))
        if r["error"]:
            self.stdout.write(self.style.NOTICE(f"   ! {r['error']}"))
            return
        if not r["detectado"]:
            self.stdout.write("   (nada detectado)")
        for k, v in r["detectado"].items():
            nuevo = " *nuevo*" if k in r["aplicado"] else ""
            self.stdout.write(f"   {k:22} = {v!r}{nuevo}")
        det = r["detectado"]
        if det.get("solo_personal"):
            self.stdout.write(self.style.NOTICE(
                "   (solo personal / estiba — sin traslado: no genera Lead)"))
        if det.get("ruta_interprovincial"):
            self.stdout.write(self.style.WARNING(
                "   ⚠ ruta FUERA DE LIMA — el cotizador automático no la cubre, "
                "el lead se marcará 'requiere asesor'"))
        if r.get("requiere_intervencion"):
            self.stdout.write(self.style.WARNING(
                "   ⚠ requiere intervención humana — va a 'Para revisión' aunque "
                "no se complete el umbral"))
        if r.get("intencion_cotizar"):
            self.stdout.write(self.style.SUCCESS(
                "   ✓ intención de cotizar — crea Lead y va a 'Oportunidades' "
                "aunque falten datos"))
        umbral = (self.style.SUCCESS("SÍ — cotizable")
                  if r["alcanza_umbral"] else self.style.NOTICE("no (falta tipo o algún distrito)"))
        self.stdout.write(f"   {'umbral para Lead':22} : {umbral}")
        self.stdout.write(f"   {'lead':22} : {r['lead_accion']}"
                          + (f" (id {r['lead_id']})" if r["lead_id"] else ""))
        if r.get("cotizacion_chat"):
            self.stdout.write(self.style.SUCCESS(
                f"   {'cotización (chat)':22} : {r['cotizacion_chat']}"))
