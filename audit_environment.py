#!/usr/bin/env python
"""
CRITICAL AUDIT: Identify every process and its database configuration.
Do NOT modify any data. Only report facts.
"""
import os
import sys
import django
import subprocess
import hashlib

print("="*70)
print("ENVIRONMENT AUDIT - NO MODIFICATIONS")
print("="*70)

# ============================================================
# 1. THIS PROCESS (audit_environment.py)
# ============================================================

print("\n[AUDIT] This process info:")
print(f"  PID: {os.getpid()}")
print(f"  Command: {sys.argv[0]}")

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django.conf import settings

print(f"\n[AUDIT] Django configuration (THIS PROCESS):")
print(f"  DJANGO_SETTINGS_MODULE: {os.environ.get('DJANGO_SETTINGS_MODULE')}")
print(f"  DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}")
print(f"  connection.vendor: {connection.vendor}")
print(f"  connection.NAME: {connection.settings_dict.get('NAME')}")
print(f"  connection.HOST: {connection.settings_dict.get('HOST', 'default')}")
print(f"  connection.PORT: {connection.settings_dict.get('PORT', 'default')}")
print(f"  connection.USER: {connection.settings_dict.get('USER', 'N/A')}")

# Verify database
try:
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute("SELECT current_database();")
            db_name = cursor.fetchone()[0]
            print(f"  ✓ PostgreSQL current_database(): {db_name}")
        else:
            print(f"  ! SQLite detected (not PostgreSQL)")
except Exception as e:
    print(f"  ERROR querying DB: {e}")

# ============================================================
# 2. CHECK SQLite BASELINE
# ============================================================

print("\n[AUDIT] SQLite baseline verification:")

sqlite_path = "db.sqlite3"
if os.path.exists(sqlite_path):
    stat = os.stat(sqlite_path)
    size = stat.st_size
    mtime = stat.st_mtime

    # Calculate hash
    with open(sqlite_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    print(f"  File: {sqlite_path}")
    print(f"  Size: {size} bytes")
    print(f"  Last modified: {mtime} (2026-08-23 or earlier?)")
    print(f"  SHA256: {file_hash}")
    print(f"  Status: EXISTS (CHECK IF FROZEN OR MODIFIED)")
else:
    print(f"  File: {sqlite_path} NOT FOUND")

# ============================================================
# 3. CHECK POSTGRESQL REAL
# ============================================================

print("\n[AUDIT] PostgreSQL real database check:")

from apps.clientes.models import Cliente
from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

try:
    max_cliente = Cliente.objects.aggregate(__import__('django.db.models', fromlist=['Max']).Max('id'))['__0']
    max_conv = ConversacionWhatsApp.objects.aggregate(__import__('django.db.models', fromlist=['Max']).Max('id'))['__0']
    max_msg = MensajeWhatsApp.objects.aggregate(__import__('django.db.models', fromlist=['Max']).Max('id'))['__0']

    print(f"  MAX Cliente: {max_cliente}")
    print(f"  MAX ConversacionWhatsApp: {max_conv}")
    print(f"  MAX MensajeWhatsApp: {max_msg}")
except Exception as e:
    print(f"  ERROR querying tables: {e}")

# Search for test data
print("\n[AUDIT] Search for test identifiers:")

for test_id_prefix in ['F5B-', 'CANONICAL-', 'FASE5B-LOCAL-']:
    try:
        count = Cliente.objects.filter(nombre__icontains=test_id_prefix).count()
        if count > 0:
            print(f"  {test_id_prefix}: {count} cliente(s) found")
            for c in Cliente.objects.filter(nombre__icontains=test_id_prefix)[:3]:
                print(f"    - id={c.id}, nombre={c.nombre}")
    except Exception as e:
        print(f"  {test_id_prefix}: ERROR - {e}")

# Search for specific IDs
print("\n[AUDIT] Search for specific IDs (168, 169, 170):")

for client_id in [168, 169, 170]:
    try:
        c = Cliente.objects.get(id=client_id)
        print(f"  Cliente {client_id}: FOUND - {c.nombre}")
    except Cliente.DoesNotExist:
        print(f"  Cliente {client_id}: NOT FOUND")
    except Exception as e:
        print(f"  Cliente {client_id}: ERROR - {e}")

# ============================================================
# 4. SETTINGS INSPECTION
# ============================================================

print("\n[AUDIT] Settings inspection:")
print(f"  INSTALLED_APPS contains: {'django.contrib.auth', 'django.contrib.contenttypes', ...}")
print(f"  DATABASES keys: {list(settings.DATABASES.keys()) if hasattr(settings, 'DATABASES') else 'N/A'}")

for db_name, db_config in settings.DATABASES.items():
    print(f"\n  Database '{db_name}':")
    print(f"    ENGINE: {db_config.get('ENGINE')}")
    print(f"    NAME: {db_config.get('NAME')}")
    if db_config.get('ENGINE') == 'django.db.backends.postgresql':
        print(f"    HOST: {db_config.get('HOST', 'default')}")
        print(f"    PORT: {db_config.get('PORT', 5432)}")
        print(f"    USER: {db_config.get('USER', 'N/A')}")

# ============================================================
# 5. RUNSERVER EXPECTED CONFIG
# ============================================================

print("\n[AUDIT] Expected runserver configuration:")
print(f"  (Based on .env or settings, runserver should use:)")

if 'DATABASE_URL' in os.environ:
    db_url = os.environ['DATABASE_URL']
    if 'postgresql' in db_url.lower():
        print(f"    PostgreSQL: Yes (DATABASE_URL contains 'postgresql')")
    else:
        print(f"    PostgreSQL: Unclear (DATABASE_URL present but format unknown)")
else:
    print(f"    WARNING: DATABASE_URL not set - may default to SQLite!")

print("\n" + "="*70)
print("AUDIT COMPLETE - NO DATA MODIFIED")
print("="*70)
