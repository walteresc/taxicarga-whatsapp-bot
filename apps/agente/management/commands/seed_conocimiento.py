"""Carga inicial del conocimiento del agente. Idempotente (upsert por slug).

    python manage.py seed_conocimiento

Es un punto de partida — el negocio lo edita después desde el admin.
"""
from django.core.management.base import BaseCommand

from apps.agente.models import DocumentoConocimiento as D

DOCS = [
    # -- empresa --
    ("empresa", "publico", "quienes-somos", "Quiénes somos", """\
Lima Express es un servicio de mudanzas y transporte de carga en Lima
Metropolitana. Coordina el servicio con equipo propio o con transportistas
afiliados, según disponibilidad y tipo de carga."""),

    ("empresa", "publico", "cobertura", "Cobertura", """\
Cobertura estándar: Lima Metropolitana y Callao. Las rutas fuera de Lima
(interprovinciales / de provincia) se atienden, pero el precio siempre lo
confirma un asesor o se negocia con transportistas — el sistema no cotiza esas
rutas automáticamente."""),

    ("empresa", "publico", "canales-y-horario", "Canales y horario", """\
Atención por WhatsApp y por el portal web. Un asesor revisa cada solicitud en
horario de oficina. Fuera de ese horario la solicitud queda registrada y se
responde al reabrir."""),

    ("empresa", "publico", "formas-de-pago", "Formas de pago", """\
Se coordina con el asesor. Métodos habituales: Yape, Plin y transferencia
bancaria (BCP). Puede pedirse un adelanto para confirmar la reserva."""),

    # -- servicios --
    ("servicios", "publico", "catalogo", "Catálogo de servicios", """\
- Mudanza residencial: casas y departamentos, con o sin operarios de carga.
- Mudanza de oficina.
- Carga general: mercadería, equipos, materiales.
- Carga tercerizada: cuando el servicio lo ejecuta un transportista afiliado.
Cada servicio puede incluir operarios, según lo que pida el cliente."""),

    ("servicios", "publico", "que-no-incluye", "Qué no incluye", """\
Salvo acuerdo explícito, el servicio no incluye: embalaje de objetos frágiles,
desarmado/armado de muebles, ni permisos municipales. Se cotizan aparte."""),

    # -- logistica --
    ("logistica", "interno", "propio-vs-tercerizado", "Propio vs. tercerizado", """\
`modalidad_ejecucion` de un Servicio: `propio` (equipo de Lima Express),
`tercerizado` (transportista afiliado) o `por_definir`. Un servicio en la
ventana nocturna se marca tercerizado al crearse porque el equipo propio no
trabaja de noche. El asesor puede cambiar la modalidad mientras no esté
asignado."""),

    ("logistica", "interno", "tipos-de-vehiculo", "Tipos de vehículo", """\
Categorías por capacidad útil: livianos, medianos, pesados. El sistema asigna la
categoría automáticamente según la capacidad en toneladas del vehículo. Para
mudanzas chicas alcanza un furgón; para carga voluminosa, camión."""),

    # -- precios --
    ("precios", "interno", "que-cotiza-el-motor", "Qué cotiza el motor automático", """\
El motor determinista solo cotiza con confianza mudanzas dentro de Lima con
historial similar. Para el resto (interprovincial, carga que no es mudanza, sin
historial) devuelve `modo=manual`: lo confirma un asesor. Nunca se le da al
cliente un número que el motor marcó como manual."""),

    ("precios", "interno", "negociacion", "Política de negociación", """\
La negociación con el cliente es controlada: el asesor ve todo y puede pausarla.
El margen (venta − costo de tercerización) solo lo ven Gerencia, Supervisor,
Despacho y Finanzas. El Asesor de Ventas ve la venta pero no el costo de compra."""),

    ("precios", "interno", "interprovincial-a-transportistas", "Interprovinciales a transportistas", """\
Para cargas interprovinciales, el asesor puede derivarlas directo a los
transportistas para que ellos propongan el precio (modo de precio "abierto"), o
cotizarlas él mismo. Si la derivación automática de interprovinciales está
activada en Configuración, el sistema las publica solo a transportistas sin
esperar que el asesor ponga precio."""),

    # -- politicas --
    ("politicas", "publico", "cancelaciones", "Cancelaciones y reprogramación", """\
Una reserva se puede reprogramar coordinando con el asesor con anticipación
razonable. Las cancelaciones sobre la hora pueden tener costo si ya se movilizó
una unidad."""),

    ("politicas", "interno", "privacidad-transportistas", "Qué ve un transportista", """\
Un transportista afiliado NUNCA ve datos del cliente: ni nombre, ni teléfono, ni
dirección exacta, ni el precio de venta. Solo ve: tipo de servicio, distritos de
origen y destino, piso, acceso, detalle de la carga, peso/volumen aproximado,
operarios requeridos, fecha/horario, y el costo objetivo publicado."""),

    ("politicas", "interno", "que-hace-el-agente", "Qué puede y no puede el agente", """\
El asistente ejecuta consultas y acciones reversibles (abrir una negociación,
mandar un mensaje, dejar una nota). Las acciones que cuestan plata o son
irreversibles (cerrar un precio, crear una reserva, adjudicar, registrar un
pago, mandar un WhatsApp) las propone y las confirma una persona."""),

    # -- procedimientos --
    ("procedimientos", "interno", "derivar-a-tercerizacion", "Cómo se deriva a tercerización", """\
1. El asesor deriva la carga (crea la reserva marcada `tercerizado` y una
   publicación en borrador).
2. El Despacho publica la carga a los transportistas, con precio fijo (solo
   aceptan), referencial (pueden ofertar) o abierto (proponen).
3. Se registran las ofertas; el Despacho adjudica a una → se crea la programación
   con ese transportista."""),

    ("procedimientos", "interno", "escalar-a-humano", "Escalar a un humano", """\
Si el asistente no puede resolver algo con sus herramientas, debe decirlo y
ofrecer que un asesor tome el caso. Nunca inventar una respuesta para tapar la
falta de una herramienta."""),

    # -- glosario --
    ("glosario", "interno", "codigos", "Códigos: CRG y SVC", """\
`CRG-NNNN` es el código de la carga; nace en el Lead y lo adopta el Servicio.
`SVC-NNNN` es el código de un servicio sin carga de origen. `OFERTA-<código>`
es lo que un transportista responde por WhatsApp para engancharse a una
publicación."""),

    ("glosario", "interno", "estados", "Estados de una carga", """\
Lead → Cotización (técnica) → Cotización comercial (borrador/enviada/entregada/
en negociación/aceptada) → Servicio (reserva) → programado/en ruta/finalizado.
Una publicación a transportistas: borrador → abierta → con ofertas → adjudicada."""),
]


class Command(BaseCommand):
    help = "Carga inicial del conocimiento del agente (upsert por slug)."

    def handle(self, *a, **o):
        creados = actualizados = 0
        for categoria, vis, slug, titulo, contenido in DOCS:
            obj, creado = D.objects.update_or_create(
                slug=slug,
                defaults={
                    "categoria": categoria, "visibilidad": vis,
                    "titulo": titulo, "contenido": contenido.strip(), "activo": True,
                },
            )
            creados += creado
            actualizados += not creado
        self.stdout.write(self.style.SUCCESS(
            f"Conocimiento: {creados} creados, {actualizados} actualizados "
            f"({D.objects.count()} en total)."))
