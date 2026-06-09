# TaxiCarga WhatsApp Bot

Aplicacion Django para atender clientes de TaxiCarga por WhatsApp, registrar leads y generar cotizaciones preliminares usando historicos o reglas base.

## Requisitos

- Python 3.12 o superior
- PostgreSQL para produccion o despliegue futuro
- Credenciales de Meta WhatsApp Cloud API
- API key de OpenAI

## Instalacion en Windows

Desde la carpeta del proyecto:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Crear un archivo `.env` basado en `.env.example` y completar las variables disponibles. Para desarrollo local se puede dejar `DATABASE_URL` vacio y Django usara SQLite.

## Comandos esperados

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Datos historicos de ejemplo

Para cargar una muestra inicial de servicios historicos:

```powershell
python manage.py importar_historicos
```

Para limpiar e importar nuevamente:

```powershell
python manage.py importar_historicos --clear
```

Tambien puedes pasar un CSV propio con las mismas columnas:

```powershell
python manage.py importar_historicos ruta\al\archivo.csv
```

El importador acepta tambien columnas operativas opcionales para mejorar la
precision: `objetos_pesados`, `modalidad_servicio`, `requiere_desarmado`,
`acceso_origen`, `acceso_destino`, `distancia_carga_origen_m`,
`distancia_carga_destino_m`, `peso_carga_kg`, `volumen_carga_m3`,
`camion_llega_origen`, `camion_llega_destino`, `camion_usado` y
`capacidad_camion`. Los historicos antiguos siguen siendo
validos aunque no tengan estas columnas.

Para importar un dump local de Wally sin copiar nombres, telefonos, correos,
DNI ni usuarios:

```powershell
python manage.py importar_wally_sql ..\mudanzas_bdtaxiccarga.sql --clear-wally
```

Las exportaciones privadas de WhatsApp pueden colocarse localmente en
`datos_privados/`. Esa carpeta esta excluida de Git.

Para convertir una exportacion en ejemplos anonimizados:

```powershell
python manage.py importar_chats_whatsapp datos_privados\conversaciones.txt --clear
```

Los ejemplos sin indicadores de datos personales pueden recuperarse como
contexto de estilo para la IA. Los ejemplos marcados para revision no se usan
automaticamente.

Las fotos nuevas recibidas por WhatsApp se descargan desde Meta y se guardan
en `datos_privados/media/`, una ruta local excluida de Git y no publicada por
las URLs de Django. Si la foto no tiene descripcion, el bot solicita una breve
aclaracion antes de continuar la cotizacion.

## Simular WhatsApp en local

Para probar el motor conversacional sin Meta:

```powershell
python manage.py simular_whatsapp "Hola, quiero una mudanza de Miraflores a Surco con cama, refrigeradora y cajas"
```

Ejemplo con mas datos:

```powershell
python manage.py simular_whatsapp "Soy Carlos Vega, quiero mudanza de Miraflores a Surco con cama queen, refrigeradora, sofa, mesa y cajas. Origen 2do piso con ascensor, destino 1er piso con ascensor, manana 9am"
```

Con un telefono especifico:

```powershell
python manage.py simular_whatsapp "Quiero cotizar una carga" --phone 51988887777
```

## Webhook de WhatsApp

- Validacion Meta: `GET /webhook/whatsapp/`
- Recepcion de mensajes: `POST /webhook/whatsapp/`

El token de validacion debe coincidir con `WHATSAPP_VERIFY_TOKEN`.

## Conexion real con Meta WhatsApp Cloud API

Completa `.env` con los valores de Meta:

```env
WHATSAPP_VERIFY_TOKEN=taxicarga-local-verify-token
WHATSAPP_ACCESS_TOKEN=token_de_meta
WHATSAPP_PHONE_NUMBER_ID=id_del_numero
WHATSAPP_API_VERSION=v25.0
```

Levanta Django:

```powershell
python manage.py runserver 127.0.0.1:8001
```

Abre un tunel publico para el webhook local:

```powershell
ngrok http 8001
```

En Meta Developers configura:

```text
Callback URL: https://TU-NGROK.ngrok-free.app/webhook/whatsapp/
Verify token: taxicarga-local-verify-token
Webhook field: messages
```

Revisa la configuracion local:

```powershell
python manage.py diagnosticar_whatsapp --public-url https://TU-NGROK.ngrok-free.app
```

Si ya tienes token y numero autorizado, prueba envio:

```powershell
python manage.py diagnosticar_whatsapp --send-to 51999999999 --message "Prueba TaxiCarga"
```

## Apps

- `clientes`: clientes y conversaciones.
- `leads`: datos comerciales recopilados para cotizar.
- `cotizador`: servicios historicos y cotizaciones preliminares.
- `ia`: prompt, extraccion basica y motor conversacional.
- `whatsapp`: webhook y envio mediante WhatsApp Cloud API.

## API operativa para vendedores

Resumen de leads pendientes:

```text
GET /api/leads/leads/pendientes/
```

Resumen de leads cotizados:

```text
GET /api/leads/leads/cotizados/
```

Acciones sobre un lead:

```text
POST /api/leads/leads/{id}/asignarme/
POST /api/leads/leads/{id}/registrar_nota/
POST /api/leads/leads/{id}/cambiar_estado/
POST /api/leads/leads/{id}/registrar_seguimiento/
POST /api/leads/leads/{id}/registrar_cotizacion/
```

Ejemplo para registrar una nota:

```json
{
  "nota": "Cliente pidio llamada a las 5pm"
}
```

Ejemplo para cambiar estado:

```json
{
  "estado": "cerrado"
}
```

Ejemplo para registrar y enviar una cotizacion:

```json
{
  "precio_cotizado": "510.00",
  "mensaje": "La cotizacion queda en S/ 510."
}
```

## Admin comercial

El panel de Django Admin permite:

- Filtrar leads por estado, prioridad, tipo de servicio, vendedor y fecha.
- Asignarte leads seleccionados.
- Marcar leads como cotizados, cerrados o perdidos.
- Registrar seguimiento.
- Subir prioridad.
- Ver la conversacion reciente del cliente dentro del lead.
- Revisar conversaciones desde la ficha del cliente.

## Dashboard comercial

Pantalla operativa para vendedores desarrollada con Vue 3 y Vuetify:

```text
GET /dashboard/login/
GET /dashboard/
GET /dashboard/leads/{id}/
POST /dashboard/leads/nuevo/
GET /dashboard/exportar/leads.csv
```

Requiere iniciar sesion en `/dashboard/login/`. Desde el dashboard se puede:

- Ver metricas por estado.
- Ver ingresos cerrados, ticket promedio y tasa de conversion.
- Buscar leads por cliente, telefono, ruta o servicio.
- Filtrar por prioridad.
- Filtrar seguimientos vencidos, para hoy o programados.
- Crear un lead manual desde el boton `Nuevo lead`.
- Exportar leads a CSV con precios, cierre y motivo de perdida desde el boton `Exportar`.
- Revisar leads pendientes, cotizados, asignados y cerrados/perdidos.
- Abrir el detalle de un lead.
- Ver el avance de datos necesarios para cotizar y los campos faltantes.
- Completar datos comerciales del lead desde el dashboard.
- Recalcular precio recomendado desde el cotizador interno.
- Asignarse un lead.
- Usar respuestas rapidas para WhatsApp y cotizaciones.
- Tomar una conversacion para pausar la respuesta automatica.
- Liberar una conversacion para volver al flujo automatico.
- Enviar una respuesta manual por WhatsApp desde el dashboard.
- Enviar una cotizacion manual y guardar el precio cotizado.
- Cerrar ventas con precio final o marcar leads perdidos con motivo.
- Registrar seguimiento.
- Programar el proximo seguimiento con fecha y hora.
- Cambiar estado y prioridad.
- Guardar notas internas.
- Leer la conversacion reciente como historial tipo chat.

La pantalla usa la sesion de Django, por lo que no requiere configurar CORS ni
un login separado para el frontend.

Exportacion CSV:

```text
GET /dashboard/exportar/leads.csv?estado=todos
GET /dashboard/exportar/leads.csv?estado=pendientes
GET /dashboard/exportar/leads.csv?estado=cotizados
GET /dashboard/exportar/leads.csv?estado=asignados
GET /dashboard/exportar/leads.csv?estado=cerrados
```

Cuando un lead esta en `atencion_humana`, el webhook guarda los mensajes entrantes
pero no genera ni envia respuestas automaticas. Esto permite que un vendedor tome
la conversacion sin que el motor conversacional intervenga.

## MVP actual

- Proyecto Django funcionando.
- Apps creadas y registradas.
- Modelos principales creados.
- Admin configurado.
- Webhook GET/POST de WhatsApp.
- Guardado de clientes y conversaciones.
- Motor IA basico con fallback local si no hay API key.
- Motor cotizador basico por historicos o reglas.
- Conversacion por etapas: cotizacion y reserva.
- Factores operativos de precio: pisos, ascensores, accesos, distancia de
  carga, embalaje, armado, objetos pesados, peso y volumen.

## Verificacion

```powershell
python manage.py check
python manage.py test
```
