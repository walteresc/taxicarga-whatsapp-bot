"""Paso 3/3 (ver 0005 y 0006): ya con los datos migrados, borra la columna
vieja (tipo_vehiculo), hace obligatoria la nueva (categoria_vehiculo) y
agrega la constraint única definitiva."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0006_compatibilidad_por_categoria_datos"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="compatibilidadcarroceria",
            name="tipo_vehiculo",
        ),
        migrations.AlterField(
            model_name="compatibilidadcarroceria",
            name="categoria_vehiculo",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="compatibilidades", to="catalogo.categoriavehiculo",
            ),
        ),
        migrations.AddConstraint(
            model_name="compatibilidadcarroceria",
            constraint=models.UniqueConstraint(
                fields=("categoria_vehiculo", "tipo_carroceria"), name="catalogo_compat_unica",
            ),
        ),
    ]
