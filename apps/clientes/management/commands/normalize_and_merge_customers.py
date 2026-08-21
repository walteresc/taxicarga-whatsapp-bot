"""
Normalize phone numbers and safely merge duplicate customers.

Usage:
    python manage.py normalize_and_merge_customers --dry-run
    python manage.py normalize_and_merge_customers --only-phone +51995403320 --dry-run
    python manage.py normalize_and_merge_customers --only-phone +51995403320
    python manage.py normalize_and_merge_customers --create-backup
"""

import json
from collections import defaultdict
from decimal import Decimal
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.clientes.models import Cliente
from apps.clientes.phone_normalizer import normalize_phone, phones_are_equivalent
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from apps.leads.models import Lead


class PhoneNormalizationAudit:
    """Audit phone numbers and find duplicates."""

    def __init__(self):
        self.total_clientes = 0
        self.valid_phones = []
        self.invalid_phones = []
        self.duplicates = defaultdict(list)
        self.phone_variants = defaultdict(set)

    def run(self):
        """Run audit on all clientes."""
        self.total_clientes = Cliente.objects.count()

        for cliente in Cliente.objects.all():
            result = normalize_phone(cliente.telefono)
            raw = cliente.telefono

            if result["is_valid"]:
                normalized = result["normalized_e164"]
                self.valid_phones.append({
                    "id": cliente.id,
                    "raw": raw,
                    "normalized": normalized,
                    "nombre": cliente.nombre or "",
                    "fecha_creacion": cliente.fecha_creacion,
                    "ultima_interaccion": cliente.ultima_interaccion,
                })
                self.duplicates[normalized].append(cliente.id)
                self.phone_variants[normalized].add(raw)
            else:
                self.invalid_phones.append({
                    "id": cliente.id,
                    "raw": raw,
                    "error": result["error"],
                    "nombre": cliente.nombre or "",
                })

    def get_duplicate_groups(self):
        """Get groups of duplicates (2+ clientes with same normalized phone)."""
        return {
            phone: ids for phone, ids in self.duplicates.items()
            if len(ids) > 1
        }

    def get_report(self):
        """Generate audit report."""
        duplicate_groups = self.get_duplicate_groups()

        return {
            "timestamp": timezone.now().isoformat(),
            "total_clientes": self.total_clientes,
            "valid_phones": len(self.valid_phones),
            "invalid_phones": len(self.invalid_phones),
            "duplicate_groups": len(duplicate_groups),
            "invalid_details": self.invalid_phones,
            "duplicate_details": {
                phone: {
                    "count": len(duplicate_groups[phone]),
                    "cliente_ids": duplicate_groups[phone],
                    "variants": sorted(self.phone_variants[phone]),
                    "clientes": [
                        {
                            "id": cid,
                            "nombre": Cliente.objects.get(id=cid).nombre or "",
                            "fecha_creacion": str(Cliente.objects.get(id=cid).fecha_creacion),
                            "ultima_interaccion": str(Cliente.objects.get(id=cid).ultima_interaccion),
                        }
                        for cid in duplicate_groups[phone]
                    ]
                }
                for phone in sorted(duplicate_groups.keys())
            }
        }


class MergeAnalyzer:
    """Analyze relationships before merge."""

    @staticmethod
    def analyze_cliente(cliente_id):
        """Analyze all relationships for a cliente."""
        cliente = Cliente.objects.get(id=cliente_id)

        # Try to get counts from other models, fallback to 0 if not available
        try:
            from apps.servicios.models import Servicio
            servicios_count = Servicio.objects.filter(cliente=cliente).count()
        except:
            servicios_count = 0

        return {
            "cliente_id": cliente_id,
            "nombre": cliente.nombre or "",
            "telefono": cliente.telefono,
            "conversaciones": ConversacionWhatsApp.objects.filter(
                cliente=cliente
            ).count(),
            "mensajes": MensajeWhatsApp.objects.filter(
                conversacion__cliente=cliente
            ).count(),
            "leads": Lead.objects.filter(cliente=cliente).count(),
            "servicios": servicios_count,
        }

    @staticmethod
    def analyze_merge_conflicts(duplicate_ids):
        """Analyze conflicts before merge."""
        clientes = Cliente.objects.filter(id__in=duplicate_ids)

        conflicts = {
            "nombre_conflict": len(set(c.nombre for c in clientes if c.nombre)) > 1,
            "correo_conflict": len(set(c.correo for c in clientes if c.correo)) > 1,
            "documento_conflict": len(
                set(c.documento for c in clientes if c.documento)
            ) > 1,
            "nombres": list(set(c.nombre for c in clientes if c.nombre)),
            "correos": list(set(c.correo for c in clientes if c.correo)),
            "documentos": list(
                set(c.documento for c in clientes if c.documento)
            ),
        }

        return conflicts

    @staticmethod
    def score_canonical(cliente_ids):
        """Score each cliente as candidate for canonical merge target."""
        scores = {}

        for cid in cliente_ids:
            cliente = Cliente.objects.get(id=cid)
            score = 0

            # Factor 1: Has manual name (> 80% confidence)
            if cliente.nombre and len(cliente.nombre) > 3:
                if cliente.nombre not in ["TEST", "TEST Stage 7", "test"]:
                    score += 100

            # Factor 2: Has correo
            if cliente.correo:
                score += 50

            # Factor 3: Has documento
            if cliente.documento:
                score += 50

            # Factor 4: More recent activity
            if cliente.ultima_interaccion:
                days_ago = (timezone.now() - cliente.ultima_interaccion).days
                score += max(0, 50 - (days_ago // 10))

            # Factor 5: Older fecha_creacion (more stable)
            if cliente.fecha_creacion:
                days_old = (timezone.now() - cliente.fecha_creacion).days
                score += min(30, days_old // 10)

            scores[cid] = score

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class Command(BaseCommand):
    help = "Normalize phone numbers and merge duplicate customers (safe, with dry-run)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without modifying data"
        )
        parser.add_argument(
            "--only-phone",
            type=str,
            help="Only merge this specific phone (e.g., +51995403320)"
        )
        parser.add_argument(
            "--create-backup",
            action="store_true",
            help="Create database backup before merge (not implemented yet)"
        )
        parser.add_argument(
            "--output",
            type=str,
            help="Save audit report to file (JSON)"
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", True)
        only_phone = options.get("only_phone")
        output_file = options.get("output")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n🔍 CUSTOMER PHONE NORMALIZATION AUDIT {'(DRY-RUN)' if dry_run else '(EXECUTION)'}"
            )
        )

        # Step 1: Audit
        self.stdout.write("\n1️⃣  Scanning all customers...")
        audit = PhoneNormalizationAudit()
        audit.run()

        report = audit.get_report()
        self.stdout.write(
            f"   Total: {report['total_clientes']}, "
            f"Valid: {report['valid_phones']}, "
            f"Invalid: {report['invalid_phones']}, "
            f"Duplicate groups: {report['duplicate_groups']}"
        )

        # Step 2: Filter duplicates
        duplicate_groups = audit.get_duplicate_groups()

        if only_phone:
            normalized = normalize_phone(only_phone)
            if not normalized["is_valid"]:
                raise CommandError(f"Invalid phone: {only_phone}")
            phone_key = normalized["normalized_e164"]
            if phone_key not in duplicate_groups:
                self.stdout.write(self.style.WARNING(
                    f"   No duplicates for {phone_key}"
                ))
                return
            duplicate_groups = {phone_key: duplicate_groups[phone_key]}

        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS("\n✅ No duplicates found"))
            return

        # Step 3: Analyze each group
        self.stdout.write(
            f"\n2️⃣  Analyzing {len(duplicate_groups)} duplicate groups...\n"
        )

        merge_plan = {}
        for phone, cliente_ids in sorted(duplicate_groups.items()):
            self.stdout.write(self.style.WARNING(f"\n📞 {phone}"))
            self.stdout.write(f"   Variants: {sorted(audit.phone_variants[phone])}")

            # Analyze each cliente
            analyses = [
                MergeAnalyzer.analyze_cliente(cid)
                for cid in cliente_ids
            ]

            for analysis in analyses:
                self.stdout.write(
                    f"   ID={analysis['cliente_id']}: "
                    f"'{analysis['nombre']}' "
                    f"(conv={analysis['conversaciones']}, "
                    f"msg={analysis['mensajes']}, "
                    f"leads={analysis['leads']})"
                )

            # Analyze conflicts
            conflicts = MergeAnalyzer.analyze_merge_conflicts(cliente_ids)
            if conflicts["nombre_conflict"]:
                self.stdout.write(self.style.WARNING(
                    f"   ⚠️  Nombre conflict: {conflicts['nombres']}"
                ))
            if conflicts["correo_conflict"]:
                self.stdout.write(self.style.WARNING(
                    f"   ⚠️  Correo conflict: {conflicts['correos']}"
                ))

            # Score canonical target
            scores = MergeAnalyzer.score_canonical(cliente_ids)
            canonical_id = scores[0][0]
            canonical_cliente = Cliente.objects.get(id=canonical_id)

            self.stdout.write(self.style.SUCCESS(
                f"   ✅ Canonical: ID={canonical_id} "
                f"'{canonical_cliente.nombre or '(no name)'}' "
                f"(score={scores[0][1]})"
            ))

            merge_targets = [s[0] for s in scores[1:]]
            self.stdout.write(f"   Merge into canonical: {merge_targets}")

            merge_plan[phone] = {
                "canonical_id": canonical_id,
                "merge_into_canonical": merge_targets,
                "conflicts": conflicts,
            }

        # Step 4: Count impact
        self.stdout.write("\n3️⃣  Impact analysis...\n")

        total_conv = 0
        total_msg = 0
        total_leads = 0
        total_servicios = 0

        for phone, plan in merge_plan.items():
            canonical_id = plan["canonical_id"]
            targets = plan["merge_into_canonical"]

            for target_id in targets:
                total_conv += ConversacionWhatsApp.objects.filter(
                    cliente=target_id
                ).count()
                total_msg += MensajeWhatsApp.objects.filter(
                    conversacion__cliente=target_id
                ).count()
                total_leads += Lead.objects.filter(cliente=target_id).count()

                try:
                    from apps.servicios.models import Servicio
                    total_servicios += Servicio.objects.filter(cliente=target_id).count()
                except:
                    pass

        self.stdout.write(f"   Will reassign:")
        self.stdout.write(f"   - {total_conv} conversations")
        self.stdout.write(f"   - {total_msg} messages")
        self.stdout.write(f"   - {total_leads} leads")
        self.stdout.write(f"   - {total_servicios} servicios")
        total_duplicates = sum(len(plan['merge_into_canonical']) for plan in merge_plan.values())
        self.stdout.write(f"   - Will deactivate {total_duplicates} duplicate customers")

        # Step 5: Save report
        if output_file:
            report["merge_plan"] = {
                str(k): v for k, v in merge_plan.items()
            }
            with open(output_file, "w") as f:
                json.dump(report, f, indent=2, default=str)
            self.stdout.write(self.style.SUCCESS(
                f"   Report saved: {output_file}"
            ))

        # Step 6: Dry-run summary
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                "\n✅ DRY-RUN COMPLETE. No changes made."
            ))
            self.stdout.write("   To execute: remove --dry-run flag\n")
            return

        # Step 7: Execute merge (REAL)
        self.stdout.write(self.style.WARNING(
            "\n⚠️  EXECUTING MERGE (this cannot be undone easily)\n"
        ))

        with transaction.atomic():
            for phone, plan in merge_plan.items():
                canonical_id = plan["canonical_id"]
                merge_into_canonical = plan["merge_into_canonical"]

                canonical = Cliente.objects.get(id=canonical_id)
                self.stdout.write(f"\n🔄 Merging {phone}...")
                self.stdout.write(f"   Canonical: ID={canonical_id}")

                for target_id in merge_into_canonical:
                    target = Cliente.objects.get(id=target_id)
                    self.stdout.write(f"   → Merging ID={target_id} into {canonical_id}")

                    # Reassign conversaciones
                    ConversacionWhatsApp.objects.filter(
                        cliente=target
                    ).update(cliente=canonical)

                    # Reassign leads
                    Lead.objects.filter(cliente=target).update(cliente=canonical)

                    # Reassign servicios (if model exists)
                    try:
                        from apps.servicios.models import Servicio
                        Servicio.objects.filter(cliente=target).update(cliente=canonical)
                    except:
                        pass

                    # Mark as merged
                    target.merged_into = canonical
                    target.is_active = False
                    target.save()

                    self.stdout.write(self.style.SUCCESS(f"      ✅ Merged"))

        self.stdout.write(self.style.SUCCESS("\n✅ MERGE COMPLETE\n"))
