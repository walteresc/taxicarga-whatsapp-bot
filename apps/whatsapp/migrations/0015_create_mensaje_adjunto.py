# Generated: 2026-08-20 - Phase B: Attachment tracking model

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0014_extend_mensaje_multimedia'),
    ]

    operations = [
        migrations.CreateModel(
            name='MensajeAdjunto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ycloud_media_id', models.CharField(db_index=True, help_text='YCloud unique media identifier', max_length=255, unique=True)),
                ('formato', models.CharField(choices=[('imagen', 'Imagen'), ('video', 'Video'), ('audio', 'Audio'), ('documento', 'Documento')], max_length=20)),
                ('mime_type', models.CharField(max_length=100)),
                ('filename', models.CharField(max_length=255)),
                ('file_size', models.BigIntegerField()),
                ('sha256', models.CharField(db_index=True, max_length=64)),
                ('storage_location', models.CharField(choices=[('ycloud', 'YCloud (temporary)'), ('local', 'Local MEDIA_ROOT')], default='local', max_length=20)),
                ('archivo', models.FileField(blank=True, help_text='Stored multimedia file in MEDIA_ROOT', upload_to='whatsapp/multimedia/%Y/%m/')),
                ('downloaded_at', models.DateTimeField(blank=True, null=True)),
                ('download_attempts', models.PositiveSmallIntegerField(default=0)),
                ('last_download_error', models.TextField(blank=True)),
                ('retention_policy', models.CharField(choices=[('default', 'Default (30 days)'), ('quote', 'Quote-linked (60 days)'), ('service', 'Service-linked (90 days)'), ('claim', 'Claim (no limit)'), ('none', 'No cleanup')], default='default', max_length=20)),
                ('retain_until', models.DateTimeField(db_index=True)),
                ('protected_from_cleanup', models.BooleanField(db_index=True, default=False)),
                ('ia_analysis_result', models.JSONField(blank=True, default=dict, help_text='Result of IA/vision analysis (persists even if file deleted)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('mensaje', models.ForeignKey(limit_choices_to={'tipo__in': ['imagen', 'audio', 'video', 'documento']}, on_delete=django.db.models.deletion.CASCADE, related_name='adjuntos', to='whatsapp.mensajewhatsapp')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='mensajeadjunto',
            index=models.Index(fields=['mensaje', '-created_at'], name='whatsapp_me_mensaje_48c9f7_idx'),
        ),
        migrations.AddIndex(
            model_name='mensajeadjunto',
            index=models.Index(fields=['retain_until', 'protected_from_cleanup'], name='whatsapp_me_retain__50e2d4_idx'),
        ),
    ]
