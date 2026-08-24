/**
 * ESTRATEGIA ALTERNATIVA: Crear sesión directamente via Django backend
 * (sin pasar por formulario HTML/Vuetify)
 *
 * Usa Django's internal login session creation, imitando lo que hacen los tests.
 */

import { chromium } from '@playwright/test'
import { execSync } from 'child_process'
import * as fs from 'fs'

const VITE_URL = 'http://localhost:5177'
const DJANGO_URL = 'http://localhost:8001'

export default async function globalAuthSetup() {
  console.log('[AUTH] ESTRATEGIA DIRECTA: Crear sesión via Django\n')

  // Step 1: Crear sesión en Django via Python script
  console.log('[1] Crear sesión en Django backend\n')

  const pythonScript = `
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
`

  try {
    const output = execSync(`cd ../.. && DJANGO_SETTINGS_MODULE=config.settings_test python << 'PYEOF'
${pythonScript}
PYEOF
`, { encoding: 'utf-8' })

    console.log(output)

    // Extraer sessionid del output
    const sessionMatch = output.match(/SESSION_ID=([^\n]+)/)
    const sessionId = sessionMatch ? sessionMatch[1].trim() : null

    if (!sessionId) {
      console.log('[ERROR] No session ID created\n')
      throw new Error('Failed to create session')
    }

    console.log(`[OK] Session created: ${sessionId.substring(0, 20)}...\n`)

    // Step 2: Crear archivo .auth.json con sessionid
    console.log('[2] Guardar sesión en .auth.json\n')

    const authState = {
      cookies: [
        {
          name: 'sessionid',
          value: sessionId,
          domain: 'localhost',
          path: '/',
          httpOnly: true,
          secure: false,
          sameSite: 'Lax',
        },
      ],
      timestamp: new Date().toISOString(),
      user: 'e2e_test',
      method: 'django-direct',
    }

    fs.writeFileSync('.auth.json', JSON.stringify(authState, null, 2))
    console.log('[OK] Auth state saved\n')

    // Step 3: Verificar acceso con sesión
    console.log('[3] Verificar acceso con sessionid\n')

    const browser = await chromium.launch()
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      httpCredentials: undefined,
    })

    // Añadir sessionid cookie
    await context.addCookies([
      {
        name: 'sessionid',
        value: sessionId,
        domain: 'localhost',
        path: '/',
        httpOnly: false,
        secure: false,
        sameSite: 'Lax',
      },
    ])

    const page = await context.newPage()

    // Probar acceso a página protegida
    const resp = await page.goto(`${VITE_URL}/atencion/bandeja-entrada`, {
      waitUntil: 'load',
      timeout: 5000,
    }).catch(() => null)

    if (resp) {
      console.log(`[OK] Acceso permitido (status ${resp.status()})\n`)
    } else {
      console.log(`[WARN] No response, pero sesión está en cookies\n`)
    }

    await browser.close()

    console.log('[AUTH] Setup complete\n')
  } catch (error) {
    console.error('[ERROR]', error.message)
    throw error
  }
}
