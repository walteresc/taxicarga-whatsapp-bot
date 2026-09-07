<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="d-flex flex-column align-center justify-center text-center pa-10" style="min-height: 60vh;">
    <VIcon icon="ri-lock-2-line" size="56" class="mb-4 text-medium-emphasis" />
    <h1 class="text-h5 font-weight-bold mb-2">
      Sin acceso
    </h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Tu usuario no tiene permiso para ver esta sección.
    </p>
    <VBtn variant="tonal" @click="router.push('/atencion/bandeja-entrada')">
      Ir a la bandeja
    </VBtn>
  </div>
</template>
