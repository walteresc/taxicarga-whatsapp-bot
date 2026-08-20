# Generated: 2026-08-20 - Phase A: Multimedia support fields

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0013_request_lifecycle_observability'),
    ]

    operations = [
        # Phase A: Extend MensajeWhatsApp with multimedia fields
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='ycloud_media_id',
            field=models.CharField(
                blank=True,
                max_length=255,
                db_index=True,
                help_text="YCloud media ID for tracking downloads"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='mime_type',
            field=models.CharField(
                blank=True,
                max_length=100,
                help_text="Validated MIME type (not client-provided)"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='filename',
            field=models.CharField(
                blank=True,
                max_length=255,
                help_text="Safe filename generated server-side"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='file_size',
            field=models.BigIntegerField(
                null=True,
                blank=True,
                help_text="File size in bytes"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='sha256',
            field=models.CharField(
                blank=True,
                max_length=64,
                db_index=True,
                help_text="SHA256 hash for integrity verification"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='caption',
            field=models.TextField(
                blank=True,
                help_text="User caption for images, videos, documents"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='media_status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('pending', 'Pending download'),
                    ('downloading', 'Downloading'),
                    ('ready', 'Ready (file saved)'),
                    ('failed', 'Download failed'),
                    ('expired', 'URL expired'),
                ],
                default='pending',
                blank=True,
                help_text="Media download and availability status"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='sender_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('customer', 'Customer'),
                    ('bot', 'Bot'),
                    ('advisor', 'Advisor'),
                    ('system', 'System'),
                ],
                default='customer',
                help_text="Who sent the message (for filtering/display)"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='source',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('whatsapp_api', 'WhatsApp API'),
                    ('whatsapp_web', 'WhatsApp Web'),
                    ('crm', 'Manual CRM entry'),
                    ('webhook', 'Webhook'),
                ],
                default='whatsapp_api',
                help_text="Where the message originated"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='retain_until',
            field=models.DateTimeField(
                null=True,
                blank=True,
                db_index=True,
                help_text="Expiration date for retention policy"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='retention_policy',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('default', 'Default (30 days)'),
                    ('quote', 'Quote-linked (60 days)'),
                    ('service', 'Service-linked (90 days)'),
                    ('claim', 'Claim (no limit)'),
                    ('none', 'No cleanup'),
                ],
                default='default',
                help_text="Retention policy for this message"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='protected_from_cleanup',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text="Manual protection from automatic cleanup"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='protection_reason',
            field=models.CharField(
                blank=True,
                max_length=255,
                help_text="Reason for manual protection"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='protected_by',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='mensajes_protegidos',
                to='auth.user',
                help_text="User who manually protected this message"
            ),
        ),
        migrations.AddField(
            model_name='mensajewhatsapp',
            name='protection_date',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="When protection was applied"
            ),
        ),
    ]
