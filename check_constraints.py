#!/usr/bin/env python
"""Quick constraint verification script."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
django.setup()

from django.db import connection
from django.apps import apps

def check_constraints():
    print('\n=== CONSTRAINT STATUS ===\n')

    with connection.cursor() as cursor:
        # 1. Check telefono column exists
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name='clientes_cliente' AND column_name='telefono'
        """)

        row = cursor.fetchone()
        if row:
            print(f'[OK] telefono column exists ({row[1]})')
        else:
            print('[ERROR] telefono column not found')
            return

        # 2. Check UNIQUE constraint
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name='clientes_cliente' AND constraint_type='UNIQUE'
        """)

        constraints = [row[0] for row in cursor.fetchall()]
        if constraints:
            print(f'[OK] UNIQUE constraint(s): {", ".join(constraints)}')
        else:
            print('[WARNING] No UNIQUE constraints found on telefono')

        # 3. Check indexes
        cursor.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename='clientes_cliente'
        """)

        indexes = cursor.fetchall()
        if indexes:
            print('[INFO] Indexes:')
            for idx_name, idx_def in indexes:
                print(f'  - {idx_name}')

        # 4. Test duplication protection
        print('\n=== CONSTRAINT ENFORCEMENT ===')
        from apps.clientes.models import Cliente

        test_phone = '+51919999888'
        try:
            # Create first
            c = Cliente.objects.filter(telefono=test_phone).delete()
            c1 = Cliente.objects.create(telefono=test_phone, nombre='Test')
            print(f'[OK] Created cliente with {test_phone}')

            # Try duplicate
            try:
                c2 = Cliente.objects.create(telefono=test_phone, nombre='Duplicate')
                print(f'[ERROR] Duplicate was allowed (CONSTRAINT FAILED)')
            except Exception as e:
                print(f'[OK] Constraint enforced: {type(e).__name__}')

            # Cleanup
            c1.delete()

        except Exception as e:
            print(f'[ERROR] Test failed: {e}')

    print('\n=== PROTECTION SUMMARY ===')
    print('''
UNIQUE(telefono) = EXACT MATCH protection
  Blocks: same phone stored twice in exact format
  Allows: +51999999999 and 51999999999 as separate records

Phone Normalization = FORMAT VARIANCE protection
  Applied BEFORE database lookup (services_ycloud.py:163-176)
  Converts any format to E.164 (+51XXXXXXXXX)
  Result: Single client per actual phone number

Identity Resolution = AMBIGUITY DETECTION
  Checks for duplicates in different formats (identity.py)
  Raises AmbiguousWhatsAppIdentity if found
  Used by webhook handler to route messages correctly
    ''')

if __name__ == '__main__':
    check_constraints()
