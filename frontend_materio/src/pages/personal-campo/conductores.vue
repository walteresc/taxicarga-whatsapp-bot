<script setup>
import PersonalCrud from './components/PersonalCrud.vue'
import { conductoresService } from '@/services/personalService'
</script>

<template>
  <PersonalCrud
    type="conductores"
    title="Conductores"
    :service="conductoresService"
  />
</template>
