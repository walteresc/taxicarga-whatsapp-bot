import subprocess
import re

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Mata procesos duplicados de runserver escuchando en un puerto."

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            type=int,
            default=8000,
            help="Puerto a liberar (default: 8000)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo mostrar que procesos se matarian sin hacerlo.",
        )

    def handle(self, *args, **options):
        port = options["port"]
        dry_run = options["dry_run"]

        try:
            netstat = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, check=True,
            )
        except FileNotFoundError:
            self.stderr.write("netstat no encontrado. Este comando solo funciona en Windows.")
            return

        pids = set()
        for line in netstat.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        pids.add(pid)

        if not pids:
            self.stdout.write(self.style.SUCCESS(f"No hay procesos escuchando en el puerto {port}."))
            return

        for pid in sorted(pids):
            try:
                proc = subprocess.run(
                    ["tasklist", "//FI", f"PID eq {pid}"],
                    capture_output=True, text=True, check=True,
                )
                name_line = [l for l in proc.stdout.splitlines() if str(pid) in l]
                proc_name = name_line[0].strip() if name_line else "(desconocido)"
            except subprocess.CalledProcessError:
                proc_name = "(desconocido)"

            if dry_run:
                self.stdout.write(f"[DRY-RUN] Se mataria PID {pid} ({proc_name})")
            else:
                try:
                    subprocess.run(["taskkill", "//F", "//PID", pid], check=True, capture_output=True)
                    self.stdout.write(self.style.SUCCESS(f"Matado PID {pid} ({proc_name})"))
                except subprocess.CalledProcessError as e:
                    self.stderr.write(f"Error matando PID {pid}: {e.stderr.decode() if e.stderr else e}")
