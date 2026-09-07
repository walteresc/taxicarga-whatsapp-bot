"""Carga inicial del catálogo de vehículos (mismos datos que la app de origen).
Todo es editable desde Configuración → Catálogo de vehículos."""
from django.db import migrations

TIPOS_VEHICULO = [
    ("moto", "Moto", "ri-motorbike-line", 1),
    ("auto", "Auto", "ri-car-line", 2),
    ("minivan", "Minivan", "ri-caravan-line", 3),
    ("camioneta", "Camioneta", "ri-roadster-line", 4),
    ("camion", "Camión", "ri-truck-line", 5),
    ("semitrailer", "Semitrailer", "ri-truck-line", 6),
    ("camion_remolque", "Camión Remolque", "ri-truck-line", 7),
]

TIPOS_CARROCERIA = [
    ("pickup", "Pickup", "ri-roadster-line", 1),
    ("furgon_cerrado", "Furgón Cerrado", "ri-box-3-line", 2),
    ("furgon_frigorifico", "Furgón Frigorífico", "ri-snowy-line", 3),
    ("furgon_isotermico", "Furgón Isotérmico", "ri-temp-cold-line", 4),
    ("plataforma", "Plataforma", "ri-stack-line", 5),
    ("plataforma_portacontenedor", "Plataforma Portacontenedor", "ri-instance-line", 6),
    ("rebatible", "Rebatible", "ri-loop-left-line", 7),
    ("baranda_tolva", "Baranda / Tolva", "ri-layout-grid-line", 8),
    ("baranda_jaula", "Baranda / Jaula", "ri-grid-line", 9),
    ("grua_telescopica", "Grúa Telescópica", "ri-tools-line", 10),
    ("cisterna_tanque", "Cisterna / Tanque", "ri-drop-line", 11),
    ("volquete", "Volquete", "ri-truck-line", 12),
    ("cama_baja", "Cama Baja", "ri-truck-line", 13),
    ("cama_cuna", "Cama Cuna", "ri-truck-line", 14),
]

COMPATIBILIDADES = {
    "camioneta": ["pickup", "furgon_cerrado", "baranda_tolva", "baranda_jaula"],
    "camion": [
        "furgon_cerrado", "furgon_frigorifico", "furgon_isotermico", "plataforma",
        "rebatible", "baranda_tolva", "baranda_jaula", "grua_telescopica",
        "cisterna_tanque", "volquete",
    ],
    "semitrailer": [
        "plataforma", "plataforma_portacontenedor", "baranda_jaula", "furgon_cerrado",
        "furgon_frigorifico", "cama_baja", "cama_cuna",
    ],
}

# (tipo_vehiculo, nombre, categoria, min_ton, max_ton, orden)
CATEGORIAS = [
    ("moto", "Moto", "livianos", None, None, 1),
    ("auto", "Auto", "livianos", None, None, 2),
    ("minivan", "Minivan", "livianos", None, None, 3),
    ("camioneta", "Camioneta", "livianos", 0, 1, 4),
    ("camion", "Camión 2 ton", "livianos", 1, 2, 5),
    ("camion", "Camión 3 ton", "livianos", 3, 4, 6),
    ("camion", "Camión 4 ton", "livianos", 4, 5, 7),
    ("camion", "Camión 5 ton", "livianos", 5, 6, 8),
    ("camion", "Camión 6 ton", "medianos", 6, 7, 9),
    ("camion", "Camión 7 ton", "medianos", 7, 8, 10),
    ("camion", "Camión 8 ton", "medianos", 8, 10, 11),
    ("camion", "Camión 10 ton", "medianos", 10, 12, 12),
    ("camion", "Camión 12 ton", "medianos", 12, 15, 13),
    ("camion", "Camión 15 ton", "medianos", 15, 18, 14),
    ("camion", "Camión 18 ton", "pesados", 18, 20, 15),
    ("camion", "Camión 20 ton", "pesados", 20, 22, 16),
    ("camion", "Camión 22 ton", "pesados", 22, 25, 17),
    ("camion", "Camión 25 ton", "pesados", 25, 30, 18),
    ("semitrailer", "Camión 30 ton", "pesados", 30, 35, 19),
    ("semitrailer", "Camión 35 ton", "pesados", 35, 40, 20),
    ("semitrailer", "Camión 40 ton", "pesados", 40, 45, 21),
    ("semitrailer", "Camión 45 ton", "pesados", 45, 50, 22),
    ("semitrailer", "Camión 50 ton", "pesados", 50, 60, 23),
]


def seed(apps, schema_editor):
    TipoVehiculo = apps.get_model("catalogo", "TipoVehiculo")
    TipoCarroceria = apps.get_model("catalogo", "TipoCarroceria")
    CompatibilidadCarroceria = apps.get_model("catalogo", "CompatibilidadCarroceria")
    CategoriaVehiculo = apps.get_model("catalogo", "CategoriaVehiculo")

    tv = {}
    for codigo, nombre, icono, orden in TIPOS_VEHICULO:
        tv[codigo] = TipoVehiculo.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre, "icono": icono, "orden": orden},
        )[0]

    tc = {}
    for codigo, nombre, icono, orden in TIPOS_CARROCERIA:
        tc[codigo] = TipoCarroceria.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre, "icono": icono, "orden": orden},
        )[0]

    for veh_cod, carr_cods in COMPATIBILIDADES.items():
        for carr_cod in carr_cods:
            CompatibilidadCarroceria.objects.get_or_create(
                tipo_vehiculo=tv[veh_cod], tipo_carroceria=tc[carr_cod],
            )

    for veh_cod, nombre, categoria, min_ton, max_ton, orden in CATEGORIAS:
        CategoriaVehiculo.objects.get_or_create(
            tipo_vehiculo=tv[veh_cod], nombre=nombre,
            defaults={"categoria": categoria, "min_ton": min_ton, "max_ton": max_ton, "orden": orden},
        )


def unseed(apps, schema_editor):
    for m in ("CompatibilidadCarroceria", "CategoriaVehiculo", "TipoCarroceria", "TipoVehiculo"):
        apps.get_model("catalogo", m).objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
