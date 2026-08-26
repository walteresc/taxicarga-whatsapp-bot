"""Diagnose SSE authentication redirect issue."""
import subprocess
import json


def test_sse_unauthenticated():
    """Test SSE endpoint without authentication."""
    print("\n[TEST 1] SSE endpoint without auth")
    print("-" * 80)

    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        '''
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_e2e")
import django
django.setup()

from django.test import RequestFactory
from apps.dashboard.views_sse import sse_events_stream
from django.http import StreamingHttpResponse

factory = RequestFactory()
request = factory.get('/dashboard/whatsapp/api/events/stream/')
# No user - simulate anonymous access

try:
    response = sse_events_stream(request)
    print(f"Status: {response.status_code if hasattr(response, 'status_code') else 'unknown'}")
    print(f"Content-Type: {response.get('Content-Type', 'not set')}")
    print(f"Location: {response.get('Location', 'none')}")

    if hasattr(response, 'content'):
        content = response.content.decode('utf-8', errors='ignore')[:200]
        print(f"Body preview: {content}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)[:100]}")
    print("(Expected: PermissionDenied or 401 response)")
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:300])


def test_sse_authenticated():
    """Test SSE endpoint with authenticated user."""
    print("\n[TEST 2] SSE endpoint with auth")
    print("-" * 80)

    cmd = [
        'docker', 'exec', 'taxicarga-api',
        'python', 'manage.py', 'shell', '-c',
        '''
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_e2e")
import django
django.setup()

from django.test import RequestFactory, Client
from django.contrib.auth.models import User
from apps.dashboard.views_sse import sse_events_stream

# Create or get test user with WhatsApp permission
try:
    user = User.objects.get(username='e2e_test')
except User.DoesNotExist:
    user = User.objects.create_user('e2e_test', 'e2e@test.com', 'e2e_password')
    user.is_staff = True
    user.save()

# Add to group with WhatsApp permission
from django.contrib.auth.models import Group
try:
    admin_group = Group.objects.get(name='Administrador')
    user.groups.add(admin_group)
except:
    pass

factory = RequestFactory()
request = factory.get('/dashboard/whatsapp/api/events/stream/')
request.user = user

try:
    response = sse_events_stream(request)
    print(f"Status: {response.status_code if hasattr(response, 'status_code') else 200}")
    print(f"Content-Type: {response.get('Content-Type', 'not set')}")

    # Try to get first chunk
    if hasattr(response, 'streaming_content'):
        try:
            first_chunk = next(response.streaming_content)
            print(f"First chunk: {first_chunk[:100]}")
        except:
            print("Could not get first chunk")
except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)[:100]}")
'''
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:300])


def test_nginx_sse_route():
    """Test SSE through Nginx."""
    print("\n[TEST 3] SSE through Nginx (anon)")
    print("-" * 80)

    cmd = [
        'docker', 'exec', 'taxicarga-nginx',
        'curl', '-v', 'http://localhost:8001/dashboard/whatsapp/api/events/stream/',
        '--max-time', '3'
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    print("Response:")
    for line in result.stderr.split('\n'):
        if 'HTTP/' in line or 'Content-Type' in line or 'Location' in line:
            print(line)

    if result.stdout:
        print("Body preview:", result.stdout[:200])


if __name__ == '__main__':
    print("="*80)
    print("SSE AUTHENTICATION DIAGNOSIS")
    print("="*80)

    test_sse_unauthenticated()
    test_sse_authenticated()
    test_nginx_sse_route()

    print("\n" + "="*80)
    print("DIAGNOSIS COMPLETE")
    print("="*80)
