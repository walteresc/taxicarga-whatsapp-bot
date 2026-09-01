<script setup>
import PersonalCrud from './components/PersonalCrud.vue'
import { ayudantesService } from '@/services/personalService'
</script>

<template>
  <PersonalCrud
    type="ayudantes"
    title="Ayudantes"
    :service="ayudantesService"
  />
</template>
