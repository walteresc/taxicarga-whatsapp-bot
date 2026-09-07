from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0015_lead_piso_permite_sotano"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="persona_contacto",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="lead",
            name="telefono_contacto",
            field=models.CharField(blank=True, max_length=30),
        ),
    ]
