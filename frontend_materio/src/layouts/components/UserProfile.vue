<script setup>
import { computed, ref } from 'vue'
import avatar1 from '@images/avatars/avatar-1.png'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const isLoggingOut = ref(false)

const displayName = computed(() => auth.user?.full_name || auth.user?.username || '')
const displayRole = computed(() => auth.roles[0] || '')

const handleLogout = async () => {
  if (isLoggingOut.value) return
  isLoggingOut.value = true

  try {
    await fetch('/dashboard/api/auth/logout/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
      credentials: 'include',
    })
  } catch (error) {
    console.error('Logout error:', error)
  }

  // Recarga completa a /login: deja limpios el store de sesión y los de la
  // bandeja (SSE, conversaciones), que si no seguirían con una sesión muerta.
  auth.clear()
  window.location.assign('/login')
}

function getCsrfToken() {
  const name = 'csrftoken'
  let cookieValue = null
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';')
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim()
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
        break
      }
    }
  }
  
  return cookieValue
}
</script>

<template>
  <VBadge
    dot
    location="bottom right"
    offset-x="3"
    offset-y="3"
    color="success"
    bordered
  >
    <VAvatar
      class="cursor-pointer"
      color="primary"
      variant="tonal"
    >
      <VImg :src="avatar1" />

      <!-- SECTION Menu -->
      <VMenu
        activator="parent"
        width="230"
        location="bottom end"
        offset="14px"
      >
        <VList>
          <!-- 👉 User Avatar & Name -->
          <VListItem>
            <template #prepend>
              <VListItemAction start>
                <VBadge
                  dot
                  location="bottom right"
                  offset-x="3"
                  offset-y="3"
                  color="success"
                >
                  <VAvatar
                    color="primary"
                    variant="tonal"
                  >
                    <VImg :src="avatar1" />
                  </VAvatar>
                </VBadge>
              </VListItemAction>
            </template>

            <VListItemTitle class="font-weight-semibold">
              {{ displayName }}
            </VListItemTitle>
            <VListItemSubtitle>{{ displayRole }}</VListItemSubtitle>
          </VListItem>
          <VDivider class="my-2" />

          <!-- 👉 Mi perfil -->
          <VListItem link to="/perfil">
            <template #prepend>
              <VIcon
                class="me-2"
                icon="ri-user-line"
                size="22"
              />
            </template>

            <VListItemTitle>Mi perfil</VListItemTitle>
          </VListItem>

          <!-- Divider -->
          <VDivider class="my-2" />

          <!-- 👉 Logout -->
          <VListItem
            :disabled="isLoggingOut"
            @click="handleLogout"
          >
            <template #prepend>
              <VIcon
                class="me-2"
                icon="ri-logout-box-r-line"
                size="22"
              />
            </template>

            <VListItemTitle>{{ isLoggingOut ? 'Saliendo...' : 'Salir' }}</VListItemTitle>
          </VListItem>
        </VList>
      </VMenu>
      <!-- !SECTION -->
    </VAvatar>
  </VBadge>
</template>
