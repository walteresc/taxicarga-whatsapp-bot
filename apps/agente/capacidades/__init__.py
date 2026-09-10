"""Importar cada módulo hace que sus @capacidad se registren.

`AgenteConfig.ready()` importa este paquete al arrancar.
"""
from . import (  # noqa: F401
    carga, conocimiento, lectura, mensajeria, negociacion, operacion, precio, tercerizacion,
)
