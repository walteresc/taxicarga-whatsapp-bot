<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { authService } from '@/services/authService'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const router = useRouter()
const drawer = ref(true)

const NAV = [
  { title: 'Cargas disponibles', icon: 'ri-inbox-line', to: '/portal/cargas' },
  { title: 'Mis ofertas', icon: 'ri-price-tag-3-line', to: '/portal/ofertas' },
  { title: 'Mis asignaciones', icon: 'ri-calendar-check-line', to: '/portal/asignaciones' },
  { title: 'Negociaciones', icon: 'ri-discuss-line', to: '/portal/negociaciones' },
]

const logout = async () => {
  await authService.logout()
  auth.clear()
  router.push('/login')
}
</script>

<template>
  <VApp>
    <VNavigationDrawer v-model="drawer" :width="248">
      <div class="pa-4">
        <div class="text-h6 font-weight-bold">Portal Transportista</div>
        <div class="text-caption text-medium-emphasis">{{ auth.user?.carrierName || auth.user?.full_name }}</div>
      </div>
      <VDivider />
      <VList nav density="comfortable">
        <VListItem
          v-for="item in NAV" :key="item.to" :to="item.to"
          :prepend-icon="item.icon" :title="item.title"
        />
      </VList>
      <template #append>
        <div class="pa-3">
          <VBtn block variant="tonal" prepend-icon="ri-logout-box-line" @click="logout">Salir</VBtn>
        </div>
      </template>
    </VNavigationDrawer>

    <VAppBar flat border density="comfortable">
      <VAppBarNavIcon @click="drawer = !drawer" />
      <VAppBarTitle>Lima Express · Transportistas</VAppBarTitle>
    </VAppBar>

    <VMain>
      <VContainer fluid class="pa-4 pa-md-6" style="max-width: 1200px;">
        <RouterView />
      </VContainer>
    </VMain>
  </VApp>
</template>
