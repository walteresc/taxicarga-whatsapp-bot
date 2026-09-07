from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0014_lead_es_interprovincial_lead_motivo_perdida_detalle_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lead",
            name="piso_origen",
            field=models.SmallIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="lead",
            name="piso_destino",
            field=models.SmallIntegerField(blank=True, null=True),
        ),
    ]
