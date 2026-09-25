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
    <input ref="input" type="file" accept="image/*" multiple class="d-none" @change="onPick">

    <!-- Sin fotos: fila ícono + texto (clicable entera), no una caja grande
         vacía ocupando espacio de entrada. Con fotos: miniaturas chicas en
         fila + un "+" al final para seguir agregando — todo el bloque se ve
         y se usa como una tira de adjuntos, no como un formulario aparte. -->
    <template v-if="!modelValue.length">
      <div class="d-flex align-center ga-3" style="cursor: pointer;" @click="openPicker">
        <VAvatar size="44" variant="tonal" color="primary" rounded="lg">
          <VIcon icon="ri-camera-line" size="22" />
        </VAvatar>
        <div>
          <div class="text-body-2 font-weight-bold">
            Agregar fotos <span class="text-medium-emphasis font-weight-regular">(opcional)</span>
          </div>
          <div class="text-caption text-medium-emphasis">Hasta {{ MAX }} fotos de tu carga. Formatos: JPG, PNG.</div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="d-flex ga-2 flex-wrap">
        <div v-for="(file, i) in modelValue" :key="file.name + file.lastModified" class="position-relative">
          <VImg :src="urlFor(file)" width="56" height="56" cover class="rounded-lg" />
          <VBtn
            icon size="x-small" variant="flat"
            style="position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; min-width: 18px; background: rgba(33, 33, 33, 0.75);"
            @click="remove(i)"
          >
            <VIcon icon="ri-close-line" size="12" color="white" />
          </VBtn>
        </div>
        <VCard
          v-if="modelValue.length < MAX" variant="outlined"
          class="d-flex align-center justify-center" style="width: 56px; height: 56px; cursor: pointer;"
          @click="openPicker"
        >
          <VIcon icon="ri-add-line" size="20" />
        </VCard>
      </div>
      <p class="text-caption text-medium-emphasis mt-1 mb-0">{{ modelValue.length }}/{{ MAX }} fotos</p>
    </template>
  </div>
</template>
