"""Infraestructura compartida de la API v2 (panel Vue).

Contrato (ver docs/PATRON-API-VUE.md):
  - Recursos en inglés bajo /api/v2/.
  - El cuerpo JSON usa claves canónicas en inglés (camelCase). La traducción
    inglés↔español vive en un único sitio por módulo: apps/<app>/api/mappers.py.
  - Respuesta de lista: {results, page, pageSize, total, pages}.
  - Errores de validación: {error, fields: {campo: [mensajes]}}.
  - Ningún string en español cruza la frontera de la API.

Este paquete NO es una app Django (no tiene modelos); solo clases reutilizables.
"""
