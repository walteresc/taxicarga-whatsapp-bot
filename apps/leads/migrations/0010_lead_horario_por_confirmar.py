from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0009_lead_esperando_motivo_no_reserva"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="horario_por_confirmar",
            field=models.BooleanField(default=False),
        ),
    ]
