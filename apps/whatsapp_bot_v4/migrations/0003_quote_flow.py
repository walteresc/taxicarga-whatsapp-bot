from django.db import migrations, models


def normalize_ready_status(apps, schema_editor):
    apps.get_model("whatsapp_bot_v4", "BotConversationState").objects.filter(
        status="ready_for_quote"
    ).update(status="ready_to_quote")


class Migration(migrations.Migration):
    dependencies = [("whatsapp_bot_v4", "0002_v4channelroute")]

    operations = [
        migrations.AlterField(
            model_name="botconversationstate",
            name="status",
            field=models.CharField(
                choices=[
                    ("collecting", "Recolectando datos"),
                    ("ready_to_quote", "Lista para cotizar"),
                    ("quoted", "Cotizada"),
                    ("pending_human_quote", "Pendiente de cotización humana"),
                ],
                default="collecting",
                max_length=24,
            ),
        ),
        migrations.AddField(model_name="botconversationstate", name="quote_input_hash", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="botconversationstate", name="quote_mode", field=models.CharField(blank=True, max_length=16)),
        migrations.AddField(model_name="botconversationstate", name="quote_price", field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
        migrations.RunPython(normalize_ready_status, migrations.RunPython.noop),
    ]
