<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authService } from '@/services/authService'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')

// Destino tras el login: ?next= si es una ruta interna segura, si no la bandeja.
const resolveNext = () => {
  const next = route.query.next
  if (typeof next === 'string' && next.startsWith('/') && !next.startsWith('//')) {
    return next
  }

  return '/atencion/bandeja-entrada'
}

const form = ref({
  username: '',
  password: '',
})

const isPasswordVisible = ref(false)

const handleLogin = async () => {
  error.value = ''
  loading.value = true

  try {
    const response = await authService.login(form.value.username, form.value.password)
    if (response.status === 'ok') {
      // La sesión ya cambió en el servidor: refresca el store (user + roles)
      // ANTES de navegar, si no el guard del router ve el estado anónimo viejo
      // y rebota a /login.
      await auth.reload()
      await router.replace(resolveNext())
    }
  } catch (err) {
    error.value = err.message || 'Error al iniciar sesión'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-container">
      <VCard class="login-box">
        <VCardText>
          <div class="login-header">
            <h1>TaxiCarga</h1>
            <p>Bandeja de entrada</p>
          </div>

          <!-- Error message -->
          <VAlert
            v-if="error"
            type="error"
            class="mb-6"
          >
            {{ error }}
          </VAlert>

          <VForm @submit.prevent="handleLogin">
            <!-- Username field -->
            <VTextField
              v-model="form.username"
              label="Usuario"
              placeholder="Ingresa tu usuario"
              :disabled="loading"
              autocomplete="username"
              prepend-inner-icon="ri-user-line"
              class="mb-4"
              required
            />

            <!-- Password field -->
            <VTextField
              v-model="form.password"
              label="Contraseña"
              placeholder="Ingresa tu contraseña"
              :type="isPasswordVisible ? 'text' : 'password'"
              :disabled="loading"
              autocomplete="current-password"
              prepend-inner-icon="ri-lock-line"
              :append-inner-icon="isPasswordVisible ? 'ri-eye-off-line' : 'ri-eye-line'"
              class="mb-4"
              required
              @click:append-inner="isPasswordVisible = !isPasswordVisible"
            />

            <!-- Submit button -->
            <VBtn
              block
              type="submit"
              :disabled="loading"
              class="mb-4"
            >
              <VIcon
                v-if="loading"
                icon="ri-loader-4-line"
                class="spinner"
              />
              <span v-if="!loading">Iniciar sesión</span>
              <span v-else>Iniciando sesión...</span>
            </VBtn>
          </VForm>
          <div class="text-center text-body-2">
            ¿Sos cliente nuevo?
            <RouterLink to="/cotizar">Cotizá tu carga sin registrarte</RouterLink>
          </div>
        </VCardText>
      </VCard>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-container {
  width: 100%;
  max-width: 400px;
  padding: 20px;
}

.login-box {
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-header h1 {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
}

.login-header p {
  margin: 0;
  font-size: 14px;
  color: #999;
}

.spinner {
  animation: spin 1s linear infinite;
  margin-right: 8px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
