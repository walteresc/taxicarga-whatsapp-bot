<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { useAuthStore } from '@/stores/authStore'
import { changePassword, getProfile, updateProfile } from '@/services/profileService'

const auth = useAuthStore()

const loading = ref(true)
const profile = ref(null)
const snack = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snack, { show: true, text: t, color: c })

const load = async () => {
  loading.value = true
  try {
    profile.value = await getProfile()
    resetAccountForm()
  } catch (e) { notify(e.message || 'No se pudo cargar tu perfil.', 'error') }
  finally { loading.value = false }
}
onMounted(load)

const initials = computed(() => {
  const name = profile.value?.fullName || profile.value?.username || '?'

  return name.trim().split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase()).join('')
})

const avatarColors = ['primary', 'success', 'warning', 'info', 'error', 'secondary']
const avatarColor = computed(() => {
  const key = profile.value?.username || ''
  const hash = [...key].reduce((a, c) => a + c.charCodeAt(0), 0)

  return avatarColors[hash % avatarColors.length]
})

const fmtDate = iso => {
  if (!iso) return '—'

  return new Date(iso).toLocaleDateString('es-PE', { day: 'numeric', month: 'long', year: 'numeric' })
}

// -- Datos de la cuenta --------------------------------------------------
const accountForm = reactive({ fullName: '', email: '' })
const accountDirty = ref(false)
const savingAccount = ref(false)
const accountErrors = reactive({})

const resetAccountForm = () => {
  accountForm.fullName = profile.value?.fullName || ''
  accountForm.email = profile.value?.email || ''
  accountDirty.value = false
}

const saveAccount = async () => {
  savingAccount.value = true
  Object.keys(accountErrors).forEach(k => delete accountErrors[k])
  try {
    profile.value = await updateProfile({ fullName: accountForm.fullName, email: accountForm.email })
    accountDirty.value = false
    auth.reload()
    notify('Datos guardados.')
  } catch (e) {
    Object.assign(accountErrors, e.fields || {})
    notify(e.message || 'No se pudo guardar.', 'error')
  } finally {
    savingAccount.value = false
  }
}

// -- Seguridad: cambiar contraseña ---------------------------------------
const pwdForm = reactive({ currentPassword: '', newPassword: '', confirmPassword: '' })
const pwdErrors = reactive({})
const savingPwd = ref(false)
const showPwd = reactive({ current: false, next: false, confirm: false })

const confirmMismatch = computed(() =>
  pwdForm.confirmPassword.length > 0 && pwdForm.newPassword !== pwdForm.confirmPassword,
)

const savePassword = async () => {
  Object.keys(pwdErrors).forEach(k => delete pwdErrors[k])
  if (confirmMismatch.value) return
  if (!pwdForm.currentPassword || !pwdForm.newPassword) return

  savingPwd.value = true
  try {
    await changePassword({ currentPassword: pwdForm.currentPassword, newPassword: pwdForm.newPassword })
    pwdForm.currentPassword = ''
    pwdForm.newPassword = ''
    pwdForm.confirmPassword = ''
    notify('Contraseña actualizada.')
  } catch (e) {
    Object.assign(pwdErrors, e.fields || {})
    notify(e.message || 'No se pudo cambiar la contraseña.', 'error')
  } finally {
    savingPwd.value = false
  }
}

const roleLabels = {
  'Administrador': 'Administrador',
  'Gerencia': 'Gerencia',
  'Admin de sistema': 'Admin de sistema',
  'Supervisor': 'Supervisor',
  'Asesor de Ventas': 'Asesor de Ventas',
  'Despacho': 'Despacho',
  'Finanzas': 'Finanzas',
}
</script>

<template>
  <section style="max-width: 720px;">
    <h1 class="text-h5 font-weight-bold mb-1">Mi perfil</h1>
    <p class="text-body-2 text-medium-emphasis mb-6">
      Tus datos de cuenta y acceso a Lima Express.
    </p>

    <VProgressLinear v-if="loading" indeterminate class="mb-4" />

    <template v-else-if="profile">
      <!-- Encabezado de identidad -->
      <div class="d-flex align-center ga-4 mb-6 flex-wrap">
        <VAvatar :color="avatarColor" variant="tonal" size="64">
          <span class="text-h6 font-weight-bold">{{ initials }}</span>
        </VAvatar>
        <div>
          <div class="text-h6 font-weight-bold">{{ profile.fullName }}</div>
          <div class="text-body-2 text-medium-emphasis">@{{ profile.username }}</div>
          <div class="d-flex flex-wrap ga-1 mt-2">
            <VChip v-for="r in profile.roles" :key="r" size="small" color="primary" variant="tonal">
              {{ roleLabels[r] || r }}
            </VChip>
            <VChip v-if="!profile.roles.length" size="small" variant="tonal">Sin rol asignado</VChip>
          </div>
        </div>
      </div>

      <VRow class="mb-1">
        <VCol cols="12" sm="6">
          <span class="text-caption text-medium-emphasis">Miembro desde</span>
          <div class="text-body-2">{{ fmtDate(profile.dateJoined) }}</div>
        </VCol>
        <VCol cols="12" sm="6">
          <span class="text-caption text-medium-emphasis">Último acceso</span>
          <div class="text-body-2">{{ fmtDate(profile.lastLogin) }}</div>
        </VCol>
      </VRow>

      <!-- Datos de la cuenta -->
      <VCard class="mt-6">
        <VCardTitle class="text-subtitle-1 font-weight-bold">Datos de la cuenta</VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12" sm="6">
              <VTextField label="Usuario" :model-value="profile.username" disabled hint="No se puede cambiar" persistent-hint />
            </VCol>
            <VCol cols="12" sm="6">
              <VTextField
                v-model="accountForm.fullName" label="Nombre completo"
                :error-messages="accountErrors.fullName" @update:model-value="accountDirty = true"
              />
            </VCol>
            <VCol cols="12">
              <VTextField
                v-model="accountForm.email" label="Correo electrónico" type="email"
                :error-messages="accountErrors.email" @update:model-value="accountDirty = true"
              />
            </VCol>
          </VRow>
        </VCardText>
        <VCardActions class="px-4 pb-4">
          <VSpacer />
          <VBtn variant="text" :disabled="!accountDirty || savingAccount" @click="resetAccountForm">
            Descartar
          </VBtn>
          <VBtn color="primary" :loading="savingAccount" :disabled="!accountDirty" @click="saveAccount">
            Guardar
          </VBtn>
        </VCardActions>
      </VCard>

      <!-- Roles y accesos -->
      <VCard class="mt-6">
        <VCardTitle class="text-subtitle-1 font-weight-bold">Roles y accesos</VCardTitle>
        <VCardText>
          <div class="d-flex flex-wrap ga-2 mb-2">
            <VChip v-for="r in profile.roles" :key="r" color="primary" variant="tonal">
              {{ roleLabels[r] || r }}
            </VChip>
          </div>
          <p class="text-caption text-medium-emphasis mb-0">
            Tus roles definen qué secciones ves y podés usar. Para cambiarlos, pedile a un
            <strong>Admin de sistema</strong> que te actualice desde Configuración → Usuarios y permisos.
          </p>
        </VCardText>
      </VCard>

      <!-- Seguridad -->
      <VCard class="mt-6 mb-6">
        <VCardTitle class="text-subtitle-1 font-weight-bold">Seguridad</VCardTitle>
        <VCardText>
          <VRow>
            <VCol cols="12">
              <VTextField
                v-model="pwdForm.currentPassword" label="Contraseña actual"
                :type="showPwd.current ? 'text' : 'password'"
                :append-inner-icon="showPwd.current ? 'ri-eye-off-line' : 'ri-eye-line'"
                @click:append-inner="showPwd.current = !showPwd.current"
                :error-messages="pwdErrors.currentPassword" autocomplete="current-password"
              />
            </VCol>
            <VCol cols="12" sm="6">
              <VTextField
                v-model="pwdForm.newPassword" label="Contraseña nueva"
                :type="showPwd.next ? 'text' : 'password'"
                :append-inner-icon="showPwd.next ? 'ri-eye-off-line' : 'ri-eye-line'"
                @click:append-inner="showPwd.next = !showPwd.next"
                :error-messages="pwdErrors.newPassword" autocomplete="new-password"
              />
            </VCol>
            <VCol cols="12" sm="6">
              <VTextField
                v-model="pwdForm.confirmPassword" label="Confirmar contraseña nueva"
                :type="showPwd.confirm ? 'text' : 'password'"
                :append-inner-icon="showPwd.confirm ? 'ri-eye-off-line' : 'ri-eye-line'"
                @click:append-inner="showPwd.confirm = !showPwd.confirm"
                :error-messages="confirmMismatch ? ['No coincide con la contraseña nueva.'] : []"
                autocomplete="new-password"
              />
            </VCol>
          </VRow>
        </VCardText>
        <VCardActions class="px-4 pb-4">
          <VSpacer />
          <VBtn
            color="primary" :loading="savingPwd"
            :disabled="!pwdForm.currentPassword || !pwdForm.newPassword || confirmMismatch"
            @click="savePassword"
          >
            Cambiar contraseña
          </VBtn>
        </VCardActions>
      </VCard>
    </template>

    <VSnackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</VSnackbar>
  </section>
</template>
