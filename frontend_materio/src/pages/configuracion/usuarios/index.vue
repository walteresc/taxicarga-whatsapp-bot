<script setup>
import { onMounted, reactive, ref } from 'vue'

import { roleList, userList, userUpdate } from '@/services/usersService'

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const rows = ref([])
const roles = ref([])
const loading = ref(true)
const search = ref('')
const roleFilter = ref('')
let searchTimer

const load = async () => {
  loading.value = true
  try {
    rows.value = (await userList({
      search: search.value || undefined,
      role: roleFilter.value || undefined,
    })).results
  } catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }

onMounted(async () => {
  roles.value = await roleList()
  await load()
})

const editing = ref(null)
const form = reactive({ roles: [], active: true, fullName: '', email: '' })
const busy = ref(false)

const openEdit = u => {
  editing.value = u
  Object.assign(form, { roles: [...u.roles], active: u.active, fullName: u.fullName, email: u.email })
}
const save = async () => {
  busy.value = true
  try {
    const updated = await userUpdate(editing.value.id, {
      roles: form.roles, active: form.active, fullName: form.fullName, email: form.email,
    })
    const i = rows.value.findIndex(r => r.id === updated.id)
    if (i >= 0) rows.value[i] = updated
    editing.value = null
    notify('Usuario actualizado.')
  } catch (e) { notify(e.message || 'No se pudo guardar.', 'error') } finally { busy.value = false }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Usuarios y permisos</h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Un usuario puede tener varios roles. Los permisos de cada pantalla se resuelven por rol (cualquiera alcanza).
      "Administrador" es el superrol de compatibilidad — asigná roles granulares cuando puedas.
    </p>

    <VCard>
      <VCardText class="d-flex flex-wrap ga-3">
        <VTextField
          v-model="search" prepend-inner-icon="ri-search-line" label="Buscar usuario, nombre, correo"
          density="compact" hide-details clearable style="max-width: 320px;" @update:model-value="onSearch"
        />
        <VSelect
          v-model="roleFilter" label="Rol" density="compact" hide-details clearable style="max-width: 220px;"
          :items="roles.map(r => ({ title: r.name, value: r.name }))" @update:model-value="load"
        />
      </VCardText>
      <VDivider />
      <VTable>
        <thead>
          <tr><th>Usuario</th><th>Nombre</th><th>Correo</th><th>Roles</th><th>Estado</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="6" class="text-center py-8"><VProgressCircular indeterminate /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="6" class="text-center text-medium-emphasis py-10">Sin usuarios.</td></tr>
          <tr v-for="u in rows" v-else :key="u.id">
            <td class="font-weight-medium">
              {{ u.username }}
              <VChip v-if="u.isSuperuser" size="x-small" color="error" class="ms-1">superuser</VChip>
            </td>
            <td>{{ u.fullName || '—' }}</td>
            <td class="text-body-2">{{ u.email || '—' }}</td>
            <td>
              <VChip v-for="r in u.roles" :key="r" size="x-small" class="me-1 mb-1" variant="tonal">{{ r }}</VChip>
              <span v-if="!u.roles.length" class="text-caption text-medium-emphasis">sin rol</span>
            </td>
            <td><VChip size="small" :color="u.active ? 'success' : 'default'">{{ u.active ? 'Activo' : 'Inactivo' }}</VChip></td>
            <td class="text-right"><VBtn size="small" variant="tonal" @click="openEdit(u)">Editar</VBtn></td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <VDialog :model-value="!!editing" max-width="520" @update:model-value="v => { if (!v) editing = null }">
      <VCard v-if="editing">
        <VCardTitle>{{ editing.username }}</VCardTitle>
        <VCardText>
          <VTextField v-model="form.fullName" label="Nombre completo" class="mb-2" />
          <VTextField v-model="form.email" label="Correo" type="email" class="mb-3" />
          <div class="text-overline mb-1">Roles</div>
          <VCheckbox
            v-for="r in roles" :key="r.name" v-model="form.roles" :value="r.name"
            :label="r.name" :hint="r.description" persistent-hint density="compact" hide-details="auto"
          />
          <VSwitch v-model="form.active" label="Cuenta activa" color="success" class="mt-3" hide-details />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="editing = null">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" @click="save">Guardar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
