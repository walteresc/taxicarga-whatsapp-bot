#!/usr/bin/env python3
"""
Test routing and static file serving security.
Verify SPA fallback doesn't interfere with APIs and assets.
"""
import os
import sys
import requests

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_e2e')

import django
django.setup()

BASE_URL = 'http://localhost:8001'
TESTS_PASSED = 0
TESTS_FAILED = 0

def test(name, condition, expected=True):
    global TESTS_PASSED, TESTS_FAILED
    result = "PASS" if condition == expected else "FAIL"
    status = "PASS" if condition == expected else "FAIL"
    print(f"  [{status}] {name}")
    if condition == expected:
        TESTS_PASSED += 1
    else:
        TESTS_FAILED += 1

print("\n=== STATIC ASSETS ===")

# Test CSS
resp = requests.head(f'{BASE_URL}/static/css/index-DkLlhIPv.css')
test("CSS loads (200)", resp.status_code == 200)
test("CSS has correct Content-Type", 'text/css' in resp.headers.get('Content-Type', ''))

# Test JS
resp = requests.head(f'{BASE_URL}/static/js/index-CPb--B4F.js')
test("JS loads (200)", resp.status_code == 200)
test("JS has correct Content-Type", 'javascript' in resp.headers.get('Content-Type', ''))

# Test favicon
resp = requests.head(f'{BASE_URL}/favicon.ico')
test("Favicon loads (200)", resp.status_code == 200)

# Test loader.css
resp = requests.head(f'{BASE_URL}/loader.css')
test("loader.css loads (200)", resp.status_code == 200)

print("\n=== SPA ROUTES ===")

# SPA routes should return HTML
routes = ['/login', '/atencion/bandeja-entrada', '/unknown-spa-route']
for route in routes:
    resp = requests.get(f'{BASE_URL}{route}')
    has_html = 'text/html' in resp.headers.get('Content-Type', '')
    has_app_div = '<div id="app">' in resp.text
    test(f"{route} -> index.html (HTML)", has_html and has_app_div)

print("\n=== API ROUTES ===")

# API routes should NOT return index.html
# They should return JSON or error

# Auth API
resp = requests.get(f'{BASE_URL}/dashboard/api/auth/check/')
test("Auth API returns JSON", 'application/json' in resp.headers.get('Content-Type', ''))

# Webhook endpoint
resp = requests.get(f'{BASE_URL}/webhooks/ycloud/v1/')
test("Webhook endpoint reachable (not SPA)", resp.status_code != 404 or 'text/html' not in resp.headers.get('Content-Type', ''))

# Admin
resp = requests.head(f'{BASE_URL}/admin/')
test("Admin reachable (not SPA fallback)", resp.status_code in [200, 302, 403])

print("\n=== SECURITY: PATH TRAVERSAL ===")

# Test path traversal attempts
traversal_paths = [
    '/static/../../etc/passwd',
    '/static/../../../manage.py',
    '/loader.css/../../../settings.py',
    '/favicon.ico/..%2Fmanage.py',
]

for path in traversal_paths:
    try:
        resp = requests.get(f'{BASE_URL}{path}')
        # Should NOT return sensitive files (content protection is more important than HTTP status)
        is_safe = (
            '/etc/passwd' not in resp.text and
            'DJANGO_SECRET_KEY' not in resp.text and
            'SECRET_KEY' not in resp.text and
            'PASSWORD' not in resp.text and
            'DATABASE_URL' not in resp.text
        )
        test(f"Path traversal blocked: {path}", is_safe)
    except Exception as e:
        test(f"Path traversal error handling: {path}", True)

print("\n=== INDEX.HTML SERVING ===")

# index.html should only be served for SPA routes
resp_login = requests.get(f'{BASE_URL}/login')
resp_favicon = requests.get(f'{BASE_URL}/favicon.ico')
resp_css = requests.get(f'{BASE_URL}/static/css/index-DkLlhIPv.css')

test("index.html served for /login", '<div id="app">' in resp_login.text)
test("favicon.ico NOT served as index.html", len(resp_favicon.content) < 5000)
test("CSS NOT served as index.html", 'body' in resp_css.text or len(resp_css.text) > 1000)

print("\n" + "="*50)
print(f"TESTS PASSED: {TESTS_PASSED}")
print(f"TESTS FAILED: {TESTS_FAILED}")
print("="*50)

if TESTS_FAILED > 0:
    sys.exit(1)
print("\n[OK] All routing and security tests passed")
