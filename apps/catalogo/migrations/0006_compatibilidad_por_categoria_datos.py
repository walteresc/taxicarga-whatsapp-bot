"""Paso 2/3 (ver 0005): migración de datos. Cada compatibilidad existente
(tipo_vehiculo -> tipo_carroceria) se copia a TODAS las categorías
(tonelajes) de ese tipo de vehículo, como punto de partida — nada se
pierde ni queda vacío al desplegar; los admins afinan cada tonelaje por
separado desde el panel después."""
from django.db import migrations


def _expandir_por_categoria(apps, schema_editor):
    CompatibilidadCarroceria = apps.get_model("catalogo", "CompatibilidadCarroceria")
    CategoriaVehiculo = apps.get_model("catalogo", "CategoriaVehiculo")

    pares = list(
        CompatibilidadCarroceria.objects.values_list("tipo_vehiculo_id", "tipo_carroceria_id")
    )
    if not pares:
        return

    por_tipo = {}
    for tipo_vehiculo_id, tipo_carroceria_id in pares:
        por_tipo.setdefault(tipo_vehiculo_id, set()).add(tipo_carroceria_id)

    CompatibilidadCarroceria.objects.all().delete()

    nuevas = []
    for tipo_vehiculo_id, tipo_carroceria_ids in por_tipo.items():
        categorias = CategoriaVehiculo.objects.filter(tipo_vehiculo_id=tipo_vehiculo_id)
        for categoria in categorias:
            for tipo_carroceria_id in tipo_carroceria_ids:
                nuevas.append(CompatibilidadCarroceria(
                    categoria_vehiculo_id=categoria.id, tipo_carroceria_id=tipo_carroceria_id,
                ))
    CompatibilidadCarroceria.objects.bulk_create(nuevas)


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0005_compatibilidad_por_categoria"),
    ]

    operations = [
        migrations.RunPython(_expandir_por_categoria, _noop),
    ]
