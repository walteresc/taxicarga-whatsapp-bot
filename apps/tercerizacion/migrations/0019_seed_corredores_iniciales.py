"""Corredores de carga nacional iniciales (coordenadas aproximadas — a
validar/ajustar desde Configuración → Corredores; el `trazado` queda vacío
hasta que alguien apriete "Calcular trazado" una vez por corredor desde esa
pantalla). El matcheo por radio de parada ya funciona sin trazado."""
from decimal import Decimal

from django.db import migrations

# (nombre, [(parada, lat, lng, radio_km), ...])
CORREDORES = [
    ("Lima - Ica - Tacna", [
        ("Cañete", Decimal("-13.0836"), Decimal("-76.3897"), Decimal("2")),
        ("Chincha", Decimal("-13.4059"), Decimal("-76.1333"), Decimal("1")),
        ("Ica", Decimal("-14.0678"), Decimal("-75.7286"), Decimal("2")),
        ("Nazca", Decimal("-14.8281"), Decimal("-74.9372"), Decimal("1")),
        ("Tacna", Decimal("-18.0146"), Decimal("-70.2534"), Decimal("3")),
    ]),
    ("Lima - Arequipa", [
        ("Ica", Decimal("-14.0678"), Decimal("-75.7286"), Decimal("2")),
        ("Nazca", Decimal("-14.8281"), Decimal("-74.9372"), Decimal("1")),
        ("Camaná", Decimal("-16.6229"), Decimal("-72.7114"), Decimal("1")),
        ("Arequipa", Decimal("-16.4090"), Decimal("-71.5375"), Decimal("3")),
    ]),
    ("Lima - Trujillo - Chiclayo", [
        ("Barranca", Decimal("-10.7500"), Decimal("-77.7667"), Decimal("1")),
        ("Chimbote", Decimal("-9.0853"), Decimal("-78.5783"), Decimal("1.5")),
        ("Trujillo", Decimal("-8.1116"), Decimal("-79.0290"), Decimal("3")),
        ("Chiclayo", Decimal("-6.7714"), Decimal("-79.8409"), Decimal("3")),
    ]),
]


def seed(apps, schema_editor):
    Corredor = apps.get_model("tercerizacion", "Corredor")
    CorredorParada = apps.get_model("tercerizacion", "CorredorParada")

    for nombre, paradas in CORREDORES:
        corredor, _ = Corredor.objects.get_or_create(nombre=nombre, defaults={"origen_nombre": "Lima"})
        for i, (parada_nombre, lat, lng, radio_km) in enumerate(paradas):
            CorredorParada.objects.get_or_create(
                corredor=corredor, nombre=parada_nombre,
                defaults={"orden": i, "lat": lat, "lng": lng, "radio_km": radio_km},
            )


def unseed(apps, schema_editor):
    Corredor = apps.get_model("tercerizacion", "Corredor")
    Corredor.objects.filter(nombre__in=[n for n, _ in CORREDORES]).delete()


class Migration(migrations.Migration):
    dependencies = [("tercerizacion", "0018_corredor_corredorparada")]
    operations = [migrations.RunPython(seed, unseed)]
