from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0003_external_message_local_identity"),
        ("whatsapp", "0011_configuracionbot_asesor_predeterminado_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChannelIntegrationPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False)),
                ("live_sync", models.BooleanField(default=False)),
                ("human_takeover", models.BooleanField(default=False)),
                ("return_to_bot", models.BooleanField(default=False)),
                ("agent_outbound", models.BooleanField(default=False)),
                ("commercial_labels", models.BooleanField(default=False)),
                ("meta_outbox", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "channel",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="integration_policy",
                        to="whatsapp.whatsappchannel",
                    ),
                ),
            ],
        ),
    ]
