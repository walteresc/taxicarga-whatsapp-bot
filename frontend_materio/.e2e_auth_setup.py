
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
sys.path.insert(0, '.')
django.setup()

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.contrib.auth import login
from django.test import RequestFactory
from datetime import datetime, timedelta

# Crear usuario si no existe
user, _ = User.objects.get_or_create(username='e2e_test', defaults={'is_active': True, 'is_staff': True})
user.set_password('e2e_test_pass')
user.save()

# Crear sesión Django (imitando login real)
factory = RequestFactory()
request = factory.get('/')
from django.middleware.csrf import CsrfViewMiddleware
middleware = CsrfViewMiddleware(lambda r: None)
middleware.process_request(request)
request.session.create()

# Simular login
request.user = user
login(request, user)

# Guardar sessionid
session_key = request.session.session_key
print(f"SESSION_ID={session_key}")
print(f"USER_ID={user.id}")
