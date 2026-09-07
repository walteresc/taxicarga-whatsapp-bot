# Patrón de referencia — API v2 + panel Vue

Establecido con **Personal (conductores / ayudantes)**. Se replica igual en cada
sección que se migre del panel Django al panel Vue/Materio.
Ver el plan completo: `docs/` → artifact "Migración al panel Vue".

Regla de oro: **ningún string en español cruza la frontera de la API**. La API
habla inglés canónico; la traducción vive en un único sitio por módulo.

---

## 1. Estructura de ficheros

### Backend

```
apps/api/                     # infraestructura compartida (NO es app Django)
  pagination.py               # StandardPagination -> {results,page,pageSize,total,pages}
  permissions.py              # HasAnyRole(*roles), role_names(user)
  exceptions.py               # api_exception_handler -> {error, fields:{campo:[msg]}}
  filters.py                  # apply_search / apply_active_filter / apply_ordering
  views.py                    # V2ModelViewSet (base de todo viewset v2)
  urls.py                     # incluye apps/<app>/api/urls.py de cada módulo

apps/<app>/api/
  mappers.py                  # ÚNICA fuente de verdad EN<->ES (campos y enums)
  serializers.py              # DRF, claves inglés vía source=, validaciones
  urls.py                     # router DRF -> /api/v2/<recurso>/
  views.py                    # viewsets finos: permisos + serializer + servicio

apps/<app>/services.py        # querysets con filtro/búsqueda/orden (los comparte
                              # también el panel Django viejo)
```

Montaje en `config/urls.py`: `path("api/v2/", include("apps.api.urls"))`.

### Frontend

```
src/services/
  apiClient.js                # fetch base: CSRF, credentials, {error,fields}, 401->/login
  createResource.js           # fábrica list/get/create/update/remove/action
  <modulo>Service.js          # p.ej. personnelService.js: driversService, assistantsService

src/stores/authStore.js       # user + roles, ensureLoaded(), hasRole/hasAnyRole
src/plugins/router/index.js   # guard beforeEach (sesión + meta.roles)
src/plugins/router/routes.js  # rutas con meta.public / meta.roles
src/components/crud/CrudResourcePage.vue   # página CRUD reutilizable config-driven
src/pages/<...>/<recurso>.vue # thin: solo columns + fields + service
src/layouts/components/NavItems.vue        # menú declarativo con ready + roles
```

---

## 2. El contrato

### Nombres
- Recurso: inglés, plural, kebab si hace falta → `/api/v2/drivers/`, `/api/v2/quote-requests/`.
- Claves JSON: inglés, **camelCase** → `licenseExpiresOn`, no `license_expires_on`.
- Acciones no-CRUD: sub-ruta en kebab → `POST /api/v2/drivers/{id}/toggle-active/`.

### Respuesta de lista
```json
{ "results": [ ... ], "page": 1, "pageSize": 20, "total": 42, "pages": 3 }
```
Query params estándar: `?search=&status=active|inactive&ordering=name|-createdAt&page=&pageSize=` (pageSize máx. 100).

### Respuesta de error (siempre esta forma)
```json
{ "error": "Revisa los datos del formulario.", "fields": { "documentId": ["Ya existe…"] } }
```
- 400 validación → `error` genérico + `fields` por campo.
- 401/403/404/409/5xx → `error` con el mensaje, `fields` vacío.
- 401 → el `apiClient` redirige a `/login?next=` automáticamente.

### Enums
Diccionario bidireccional en `mappers.py`. El serializer expone el valor inglés;
al escribir valida contra el inverso. Añadir/renombrar un valor = un cambio en un
sitio.

---

## 3. Mapeo EN↔ES — `apps/<app>/api/mappers.py`

```python
DRIVER_FIELDS = {                    # clave API (canónica)  ->  campo modelo (BD)
    "name": "nombre",
    "documentId": "dni",
    "phone": "telefono",
    "licenseNumber": "numero_licencia",
    "licenseCategory": "categoria_licencia",
    "licenseExpiresOn": "fecha_vencimiento_licencia",
    "active": "activo",
    "notes": "observaciones",
}
LICENSE_CATEGORY = {v: v for v, _l in Conductor.LICENCIA_CATEGORIAS}  # enum

def api_to_model(mapping, data):  # renombra claves API -> modelo
    return {mapping[k]: v for k, v in data.items() if k in mapping}
def model_to_api(mapping, data):  # renombra claves modelo -> API
    inv = {v: k for k, v in mapping.items()}
    return {inv[k]: v for k, v in data.items() if k in inv}
```

**Prueba de ida y vuelta obligatoria** (`tests_api.py`):
`model_to_api(FIELDS, api_to_model(FIELDS, x)) == x`, y
`set(Serializer().fields) - {"id"} == set(FIELDS)` — así serializer y mapa no se
desincronizan.

---

## 4. Serializer — claves inglesas vía `source=`

```python
class DriverSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nombre", max_length=160)
    documentId = serializers.CharField(source="dni", max_length=20)
    licenseExpiresOn = serializers.DateField(
        source="fecha_vencimiento_licencia", required=False, allow_null=True, default=None,
    )
    active = serializers.BooleanField(source="activo", required=False, default=True)
    # …

    class Meta:
        model = Conductor
        fields = ("id", "name", "documentId", "phone", "licenseNumber",
                  "licenseCategory", "licenseExpiresOn", "active", "notes")

    def validate_documentId(self, value):
        qs = Conductor.objects.filter(dni=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un conductor con este documento.")
        return value
```

Las reglas de negocio (unicidad, coherencia entre campos) van aquí o en un
servicio — **nunca** en el viewset ni en el componente Vue.

---

## 5. Viewset — fino

```python
class _PersonnelViewSet(V2ModelViewSet):          # V2ModelViewSet: paginación + formato de error v2
    permission_classes = [HasAnyRole("Administrador", "Supervisor", "Asesor de Ventas")]

    def get_queryset(self):
        return self._queryset_fn(self.request.query_params)   # -> apps/campo/services.py

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object(); obj.activo = not obj.activo
        obj.save(update_fields=["activo"])
        return Response(self.get_serializer(obj).data)

class DriverViewSet(_PersonnelViewSet):
    serializer_class = DriverSerializer
    _queryset_fn = staticmethod(drivers_queryset)
```

`V2ModelViewSet` (en `apps/api/views.py`) fija `pagination_class`,
`http_method_names` (sin PUT) y `get_exception_handler` **solo para v2** — no
toca el `EXCEPTION_HANDLER` global, así las APIs legacy y la de la bandeja no
cambian.

---

## 6. RBAC

- Grupos canónicos: `Administrador`, `Supervisor`, `Asesor de Ventas`,
  `Conductor`, `Ayudante`. Se crean con `python manage.py seed_roles` (idempotente).
- `/dashboard/api/auth/user/` y `/check/` devuelven `roles: [...]`. Un superusuario
  recibe `"Administrador"` implícito.
- Backend: `permission_classes = [HasAnyRole(...)]` en el viewset. Superusuario
  siempre pasa.
- Frontend:
  - `authStore.ensureLoaded()` carga la sesión una vez (el guard la invoca).
  - `routes.js`: `meta: { roles: [...] }` en la ruta.
  - `router/index.js` `beforeEach`: sin sesión → `/login?next=`; sesión en ruta
    pública → bandeja; `meta.roles` sin match → `/forbidden`.
  - `NavItems.vue`: cada entrada con `ready` (¿migrada?) + `roles`. Se oculta lo
    que no está listo o el usuario no puede ver.

---

## 7. Frontend — página CRUD

`CrudResourcePage.vue` hace todo (búsqueda con debounce, filtro de estado,
ordenación por columna, paginación, alta/edición con errores por campo, borrado
con confirmación, activar/desactivar, estados carga/error/vacío, permiso de
escritura por rol). La página del recurso solo la configura:

```vue
<script setup>
import CrudResourcePage from '@/components/crud/CrudResourcePage.vue'
import { driversService, LICENSE_CATEGORIES } from '@/services/personnelService'

const columns = [
  { key: 'name', label: 'Nombre' },
  { key: 'licenseExpiresOn', label: 'Vence', format: r => r.licenseExpiresOn || '—' },
]
const fields = [
  { key: 'name', label: 'Nombre completo', type: 'text', required: true },
  { key: 'licenseCategory', label: 'Categoría', type: 'select', options: LICENSE_CATEGORIES, cols: 6 },
  { key: 'licenseExpiresOn', label: 'Vencimiento', type: 'date', cols: 6 },
  { key: 'active', label: 'Activo', type: 'switch', cols: 6 },
  { key: 'notes', label: 'Observaciones', type: 'textarea' },
]
</script>
<template>
  <CrudResourcePage title="Conductores" singular="conductor"
    :service="driversService" :columns="columns" :fields="fields" />
</template>
```

`apiClient.js` normaliza el error a `ApiError { message, status, fields }`;
`CrudResourcePage` pinta `fields` bajo cada input y el resto en un snackbar.

---

## 8. Checklist para migrar una sección

1. `apps/<app>/api/mappers.py` — campos + enums, con prueba de ida y vuelta.
2. `apps/<app>/services.py` — queryset(s) con filtro/búsqueda/orden.
3. `apps/<app>/api/serializers.py` — claves inglesas, validaciones.
4. `apps/<app>/api/views.py` + `urls.py` — viewset fino + router.
5. Registrar el include en `apps/api/urls.py`.
6. `apps/<app>/tests_api.py` — roundtrip, CRUD, RBAC, formato de error.
7. Frontend: `src/services/<modulo>Service.js` (createResource), página thin con
   `CrudResourcePage` (o componente propio si no es un CRUD).
8. `routes.js` (+ `meta.roles`), `NavItems.vue` (`ready: true` + `roles`).
9. **Extraer a servicio** cualquier efecto secundario que la vista Django vieja
   haga al escribir, y apuntar esa vista vieja al mismo servicio (para que ambos
   paneles ejecuten el mismo código mientras coexisten).
10. `npm run build` en `frontend_materio`, `cp -r dist/. static_build/` (o
    `rm -rf static_build && cp -r frontend_materio/dist static_build`), verificar
    el hash de `index.html` dentro del contenedor nginx.
11. Panel Django: **se queda intacto** hasta que el usuario dé el visto bueno de retirada.

---

## 9. Qué NO copiar

- `campo/views_personal_api.py` — API JSON en español, `setattr` directo del
  payload. Es el anti-patrón que este documento reemplaza. Quedó **huérfana**
  (nada la usa); se borra cuando se dé luz verde a limpiar el panel viejo.
- Las APIs DRF legacy `/api/leads/`, `/api/clientes/`, `/api/cotizador/`
  (`fields="__all__"`, español). No se amplían; se retiran cuando nada las use.
- El estilo del serializador de la bandeja (`_serialize_*` disperso en
  `views_whatsapp.py`). La bandeja **no se toca**; lo nuevo sigue este patrón.
