// Marca (nombre + logo) vista por el cliente — dato de negocio editable
// desde Configuración → Marca (ver apps/dashboard/models.py::ConfiguracionMarca),
// sin redeploy. Se carga una sola vez al abrir la app (App.vue) y sirve para
// TODAS las sesiones (autenticadas o no), porque login/sidebar/cotizador de
// invitado la necesitan antes de que exista sesión.
//
// Si todavía no se configuró nada (name === null), cada componente cae al
// valor por default fijado en el build (BRAND_NAME de utils/brand.js).
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { publicBrand } from '@/services/brandService'
import { BRAND_NAME as DEFAULT_BRAND_NAME } from '@/utils/brand'

export const useBrandStore = defineStore('brand', () => {
  const name = ref(null)
  const logoUrl = ref(null)
  const loaded = ref(false)

  const displayName = computed(() => name.value || DEFAULT_BRAND_NAME)

  const load = async () => {
    if (loaded.value) return
    try {
      const res = await publicBrand()
      name.value = res.name
      logoUrl.value = res.logoUrl
    } catch {
      // Sin conexión o error — se queda con el default, no rompe la pantalla.
    } finally {
      loaded.value = true
    }
  }

  // Tras guardar en Configuración → Marca, para que el resto de la sesión
  // (sidebar incluido) refleje el cambio sin recargar la página.
  const setFromConfig = payload => {
    name.value = payload.name
    logoUrl.value = payload.logoUrl
  }

  return { name, logoUrl, displayName, loaded, load, setFromConfig }
})
