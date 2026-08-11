from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("whatsapp", "0011_configuracionbot_asesor_predeterminado_and_more")]
    operations = [
        migrations.AddField(
            model_name="mensajewhatsapp",
            name="question_targets",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
