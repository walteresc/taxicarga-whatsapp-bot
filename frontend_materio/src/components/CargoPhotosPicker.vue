<script setup>
// "Agregar fotos (opcional)" — hasta 5, se suben recién al publicar (junto
// con el resto del formulario, en un solo POST multipart). No hay upload
// previo: mientras se arma la solicitud son solo File[] en memoria.
import { onBeforeUnmount, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, required: true },   // File[]
})
const emit = defineEmits(['update:modelValue'])

const MAX = 5
const input = ref(null)
const previews = ref({})   // File -> object URL, para no recrearla en cada render

const urlFor = file => {
  if (!previews.value[file.name + file.lastModified]) {
    previews.value[file.name + file.lastModified] = URL.createObjectURL(file)
  }

  return previews.value[file.name + file.lastModified]
}

const openPicker = () => input.value?.click()
const onPick = e => {
  const chosen = Array.from(e.target.files || [])
  e.target.value = ''
  if (!chosen.length) return
  const next = [...props.modelValue, ...chosen].slice(0, MAX)
  emit('update:modelValue', next)
}
const remove = index => emit('update:modelValue', props.modelValue.filter((_, i) => i !== index))

onBeforeUnmount(() => { Object.values(previews.value).forEach(url => URL.revokeObjectURL(url)) })
</script>

<template>
  <div>
    <div class="text-subtitle-2 mb-1">Agregar fotos (opcional)</div>
    <p class="text-caption text-medium-emphasis mb-2">Hasta {{ MAX }} fotos — ayudan a que te coticen mejor.</p>
    <input ref="input" type="file" accept="image/*" multiple class="d-none" @change="onPick">
    <div class="d-flex ga-2 flex-wrap">
      <div v-for="(file, i) in modelValue" :key="file.name + file.lastModified" class="position-relative">
        <VImg :src="urlFor(file)" width="88" height="88" cover class="rounded" />
        <VBtn
          icon size="x-small" variant="flat"
          style="position: absolute; top: -8px; right: -8px; background: rgba(33, 33, 33, 0.75);"
          @click="remove(i)"
        >
          <VIcon icon="ri-close-line" size="16" color="white" />
        </VBtn>
      </div>
      <VCard
        v-if="modelValue.length < MAX" variant="outlined"
        class="d-flex flex-column align-center justify-center" style="width: 88px; height: 88px; cursor: pointer;"
        @click="openPicker"
      >
        <VIcon icon="ri-add-line" size="22" />
        <span class="text-caption">Agregar</span>
      </VCard>
    </div>
  </div>
</template>
