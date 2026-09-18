"""Mueve CompatibilidadCarroceria de TipoVehiculo (genérico) a
CategoriaVehiculo (tonelaje puntual) — antes un "Camión" de 2 ton y uno de
15 ton compartían exactamente la misma lista de carrocerías compatibles.

Paso 1/3: solo schema (agrega la columna nueva, afloja la vieja). El índice
que Django crea para la FK nueva queda diferido al final de ESTA
migración/transacción — si el RunPython de migración de datos (0006)
estuviera en la misma migración, Postgres tira "pending trigger events" al
intentar crear ese índice después de un DELETE/INSERT masivo en la misma
tabla dentro de la misma transacción. Por eso va en un paso aparte.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0004_tipovehiculo_visible_cotizador_publico"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="compatibilidadcarroceria",
            name="catalogo_compat_unica",
        ),
        migrations.AddField(
            model_name="compatibilidadcarroceria",
            name="categoria_vehiculo",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="compatibilidades", to="catalogo.categoriavehiculo",
            ),
        ),
        # Nullable temporalmente: las filas NUEVAS que crea la migración de
        # datos (0006) no tienen tipo_vehiculo (se borra en la 0007).
        migrations.AlterField(
            model_name="compatibilidadcarroceria",
            name="tipo_vehiculo",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="compatibilidades", to="catalogo.tipovehiculo",
            ),
        ),
    ]
