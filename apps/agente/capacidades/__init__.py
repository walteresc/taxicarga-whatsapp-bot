"""Importar cada módulo hace que sus @capacidad se registren.

`AgenteConfig.ready()` importa este paquete al arrancar.
"""
from . import carga, lectura, mensajeria, negociacion, operacion, precio, tercerizacion  # noqa: F401
