#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
client = Client()
response = client.get('/dashboard/whatsapp/api/debug-redis/')
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("Response OK")
else:
    print(f"404 - URL not found")
