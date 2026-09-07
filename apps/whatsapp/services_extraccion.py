"""Extracción NLU de datos de servicio a partir de las conversaciones de WhatsApp.

FASE 2. Barrido periódico (comando `extraer_datos_conversaciones`), NUNCA en el
hot path del webhook. Capturar datos != responder al cliente: esto funciona con
el bot global PAUSADO.

Flujo:
  1. Se lee el historial de mensajes de la conversación y se manda a OpenAI.
  2. El JSON resultante se normaliza (tipos, fechas, sinónimos) y se acumula en
     `ConversacionWhatsApp.datos_extraidos` — solo se rellena lo que estaba vacío
     o llega un valor más específico; nunca se pisa una edición del asesor.
  3. Cuando `datos_extraidos` alcanza el mínimo para cotizar
     (tipo_servicio + AMBOS distritos), se crea el Lead vía la capa de servicio
     (`apps.whatsapp.domain._obtener_o_crear_lead_para_conversacion`) y a partir
     de ahí la extracción llena el Lead directamente (update_fields acotados).
"""
import json
import logging
import re
from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

logger = logging.getLogger(__name__)

# --- Contrato de campos --------------------------------------------------------

# Campos de texto que se copian tal cual (con recorte de longitud).
_MAX_LEN = {
    "distrito_origen": 120, "distrito_destino": 120,
    "direccion_origen": 255, "direccion_destino": 255,
    "lista_objetos": 500, "objetos_pesados": 500,
    "horario_servicio": 80, "tipo_servicio": 50,
}

TIPOS_VALIDOS = {"carga", "mudanza", "oficina", "corporativo", "traslado pequeno"}
_SINONIMOS_TIPO = {
    "mudanza": "mudanza", "mudanzas": "mudanza", "trasteo": "mudanza",
    "carga": "carga", "flete": "carga", "transporte": "carga",
    "envio": "carga", "envío": "carga", "encomienda": "carga",
    "oficina": "oficina", "mudanza de oficina": "oficina",
    "corporativo": "corporativo",
}

_DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}

_VERDADERO = {"si", "sí", "true", "1", "yes", "y", "verdadero"}

# Conectores que van en minúscula al normalizar nombres de lugar ("La Matanza",
# "San Juan de Lurigancho").
_CONECTORES_LUGAR = {"de", "del", "la", "las", "los", "y", "el", "en", "al"}

# Ciudades/regiones del Perú fuera de Lima Metropolitana + Callao. Se usa como
# respaldo del campo `ambito` del modelo para marcar rutas interprovinciales
# (el cotizador automático solo cubre rutas dentro de Lima).
_CIUDADES_NO_LIMA = {
    "piura", "castilla", "catacaos", "tambogrande", "sullana", "paita", "talara",
    "sechura", "chulucanas", "la matanza", "tumbes", "trujillo", "chiclayo",
    "lambayeque", "chimbote", "arequipa", "cusco", "cuzco", "puno", "juliaca",
    "pucallpa", "iquitos", "tarapoto", "moyobamba", "jaen", "jaén", "bagua",
    "yurimaguas", "huancayo", "huanuco", "huánuco", "huaraz", "cajamarca",
    "ayacucho", "abancay", "tacna", "moquegua", "ilo", "ica", "nazca", "nasca",
    "pisco", "chincha", "cañete", "canete", "mala", "asia", "huaral", "huacho",
    "barranca", "chancay", "satipo", "la merced", "tingo maria", "tingo maría",
}

PROMPT_SISTEMA = (
    "Eres un extractor de datos para Lima Express, empresa peruana de mudanzas y "
    "transporte de carga. Operan DENTRO de Lima Metropolitana y también en RUTAS "
    "INTERPROVINCIALES a cualquier ciudad o región del Perú (Piura, Tumbes, "
    "Trujillo, Chiclayo, Arequipa, Cusco, Pucallpa, Nazca, Ica, Cañete, Huaral, "
    "etc.).\n"
    "Lees una conversación de WhatsApp entre el cliente (C) y la empresa (E) y "
    "devuelves SOLO un JSON con los datos del servicio que el CLIENTE ha "
    "mencionado.\n"
    "Reglas:\n"
    "- No inventes nada. Si un dato no aparece, omite esa clave del JSON.\n"
    "- Si el cliente corrige un dato, usa el último valor.\n"
    "- El origen y el destino pueden ser un distrito de Lima, una ciudad o una "
    "región del Perú. Ponlos igual en distrito_origen / distrito_destino (sin las "
    "palabras 'distrito' ni 'provincia'). Marca ambito='interprovincial' cuando "
    "origen y destino estén en ciudades o regiones distintas del Perú "
    "(p. ej. Lima <-> Piura); ambito='local' si ambos están en Lima Metropolitana "
    "o Callao.\n"
    "- tipo_servicio:\n"
    "    * 'mudanza' = traslado de los enseres de un hogar u oficina completa "
    "(muebles, electrodomésticos, cajas, ropa, camas).\n"
    "    * 'carga' = mercadería, producto o un bien concreto (toneladas de aceite, "
    "una cabina industrial, cerámica paletizada, maquinaria, una sola "
    "refrigeradora, mercadería paletizada).\n"
    "    * 'oficina' = mudanza de una oficina o local comercial completo.\n"
    "  Clasifica SOLO por lo que describe el CLIENTE. IGNORA el saludo de la "
    "empresa aunque diga 'tu mudanza'.\n"
    "- Si el cliente solo pide PERSONAL (estibadores, cargadores, ayudantes para "
    "cargar o descargar) SIN traslado de un punto a otro, pon solo_personal=true y "
    "NO pongas tipo_servicio.\n"
    "- Peso siempre en kilos. Si el cliente habla en toneladas, conviértelo "
    "(1 Tn = 1000 kg).\n"
    "- PRECIO NEGOCIADO EN EL CHAT: si la empresa (E) llegó a dar un precio y hubo "
    "negociación, devuélvelo como referencia para el asesor (NO es un dato del "
    "servicio, va en sus propias claves):\n"
    "    * precio_acordado: el ÚLTIMO monto en soles que la empresa (E) ofreció EN "
    "FIRME, o —si el cliente (C) aceptó explícitamente un monto— el que aceptó. Un "
    "solo número, sin 'S/'. Si E solo tiró rangos o precios de tanteo y nunca "
    "cerró uno, omítelo.\n"
    "    * precio_aceptado_por_cliente: true SOLO si C aceptó ese monto de forma "
    "clara ('ya', 'de acuerdo', 'hecho', 'ok cerramos'). Si C sigue regateando o "
    "no contestó, omítelo.\n"
    "    * precio_incluye: en pocas palabras qué cubre ese precio (transporte, "
    "personal de carga, embalaje, etc.), tal como se dijo.\n"
    "    * precio_condiciones: forma/condiciones de pago mencionadas (p. ej. "
    "'50% al inicio y 50% al final', 'Yape', 'adelanto').\n"
    "  Si hubo VARIOS precios por distintos alcances, quédate con el que corresponde "
    "al servicio que el cliente finalmente quiere, y descríbelo en precio_incluye.\n"
    "Además, marca estas 4 señales (true SOLO si aplica claramente; por defecto "
    "omítelas) — sirven para mandar la conversación a revisión humana:\n"
    "  * quiere_hablar_con_asesor: el cliente pide explícitamente hablar con una "
    "persona, un asesor, un humano, o dice que no quiere seguir con el bot.\n"
    "  * pide_precio_sin_dar_datos: el cliente pregunta el precio o cuánto cuesta, "
    "insistiendo, sin haber dado los datos mínimos que la empresa (E) le pidió "
    "(tipo de servicio, origen, destino).\n"
    "  * no_responde_preguntas_del_bot: la empresa (E) hizo una pregunta concreta "
    "(origen, destino, fecha, qué se traslada, etc.) DOS O MÁS VECES de forma clara "
    "y el cliente (C) respondió algo sin relación, cambió de tema, o dejó de "
    "responder. NO marques esto solo porque el cliente tardó o dio los datos en "
    "otro orden.\n"
    "  * carga_dificil_de_cotizar: lo que describe el cliente no encaja bien en "
    "mudanza/carga/oficina estándar — maquinaria industrial, algo muy específico o "
    "fuera de lo común, o una mezcla de servicios muy distintos entre sí — y un "
    "asesor humano debería mirarlo antes de dar cualquier precio.\n"
    "Por último, marca quiere_cotizar=true cuando el cliente (C) muestra que quiere "
    "contratar el servicio: pide una cotización o un precio, o dice que quiere una "
    "mudanza / un flete / trasladar o mover algo concreto — aunque todavía no haya "
    "dado todos los datos. NO la marques si C solo saluda, hace una consulta "
    "general, o es la empresa (E) quien ofrece; y si C está insistiendo por el "
    "precio sin cooperar con las preguntas, esa señal es pide_precio_sin_dar_datos, "
    "no esta."
)

PROMPT_USUARIO = """Conversación:
{historial}

Devuelve SOLO este JSON (omite las claves cuyo dato no aparezca):
{{
  "tipo_servicio": "mudanza | carga | oficina",
  "solo_personal": true,
  "ambito": "local | interprovincial",
  "distrito_origen": "distrito de Lima, ciudad o región de donde se recoge",
  "distrito_destino": "distrito de Lima, ciudad o región a donde se lleva",
  "direccion_origen": "direccion exacta de origen si la dio",
  "direccion_destino": "direccion exacta de destino si la dio",
  "piso_origen": 0,
  "piso_destino": 0,
  "ascensor_origen": true,
  "ascensor_destino": true,
  "lista_objetos": "que se traslada, tal como lo describio el cliente",
  "objetos_pesados": "piano, caja fuerte, maquinaria, etc. solo si los menciono",
  "peso_kg": 0,
  "volumen_m3": 0,
  "embalaje": true,
  "fecha": "YYYY-MM-DD, o 'manana', o el texto tal cual",
  "horario": "hora o franja horaria mencionada",
  "precio_acordado": 0,
  "precio_aceptado_por_cliente": true,
  "precio_incluye": "qué cubre ese precio",
  "precio_condiciones": "forma de pago mencionada",
  "quiere_cotizar": true,
  "quiere_hablar_con_asesor": true,
  "pide_precio_sin_dar_datos": true,
  "no_responde_preguntas_del_bot": true,
  "carga_dificil_de_cotizar": true
}}"""


# --- Historial ---------------------------------------------------------------

def _historial_para_prompt(conversacion, limite=60):
    msgs = list(
        MensajeWhatsApp.objects
        .filter(conversacion=conversacion, oculto_en_crm=False)
        .order_by("-fecha_mensaje")
        .values("origen", "contenido")[:limite]
    )
    msgs.reverse()
    lineas = []
    for m in msgs:
        texto = (m["contenido"] or "").strip()
        if not texto:
            continue
        marca = "C" if m["origen"] == MensajeWhatsApp.ORIGEN_CLIENTE else "E"
        lineas.append(f"{marca}: {texto}")
    return "\n".join(lineas)


# --- Llamada a OpenAI ------------------------------------------------------------

def _llamar_openai(historial):
    """Devuelve dict crudo del modelo o None. NUNCA lanza."""
    key = getattr(settings, "OPENAI_API_KEY", "")
    if not key:
        logger.warning("[Extraccion] OPENAI_API_KEY no configurada — sin extracción")
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, timeout=20)
        modelo = getattr(settings, "OPENAI_EXTRACTION_MODEL", None) or settings.OPENAI_MODEL
        resp = client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": PROMPT_USUARIO.format(historial=historial)},
            ],
            temperature=0.2,
            max_tokens=550,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning("[Extraccion] Llamada/parseo OpenAI falló: %s", e)
        return None


# --- Normalización -------------------------------------------------------------

def _a_int(valor):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        m = re.search(r"\d+", str(valor or ""))
        return int(m.group()) if m else None


def _a_bool(valor):
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in _VERDADERO if valor is not None else None


def _a_num(valor):
    """Primer número (float) que aparezca en el valor, o None."""
    if valor is None:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(valor))
    return float(m.group().replace(",", ".")) if m else None


def _peso_a_kg(valor):
    """Normaliza un peso a kilos. Convierte toneladas si el texto lo indica."""
    num = _a_num(valor)
    if num is None:
        return None
    s = str(valor).lower()
    if re.search(r"\b(t|tn|ton|tonelada|toneladas)\b", s) or "tonel" in s:
        num *= 1000
    return round(num, 2) if 0 < num <= 100000 else None


def _title_lugar(texto):
    """'san miguel' -> 'San Miguel'; '26 de octubre - piura' -> '26 de Octubre - Piura'.
    Deja intactos los conectores y las palabras que ya traen mayúsculas internas."""
    palabras = str(texto).split()
    salida = []
    for i, p in enumerate(palabras):
        bajo = p.lower()
        if i and bajo in _CONECTORES_LUGAR:
            salida.append(bajo)
        elif p[:1].isalpha() and p == p.lower():
            salida.append(p[:1].upper() + p[1:])
        else:
            salida.append(p)
    return " ".join(salida)


def _menciona_ciudad_no_lima(texto):
    t = (texto or "").lower()
    return any(re.search(r"\b" + re.escape(c) + r"\b", t) for c in _CIUDADES_NO_LIMA)


def _parsear_fecha(texto):
    """Devuelve (date | None, texto_original_si_no_parsea)."""
    if not texto:
        return None, ""
    t = str(texto).strip().lower()
    hoy = timezone.localdate()
    if t in ("hoy",):
        return hoy, ""
    if t in ("mañana", "manana"):
        return hoy + timedelta(days=1), ""
    if t in ("pasado mañana", "pasado manana"):
        return hoy + timedelta(days=2), ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(t, fmt).date(), ""
        except ValueError:
            pass
    for dia, idx in _DIAS_SEMANA.items():
        if dia in t:
            delta = (idx - hoy.weekday()) % 7
            return hoy + timedelta(days=delta or 7), ""
    return None, str(texto)[:80]


def _normalizar_extraccion(raw):
    """dict crudo del modelo -> dict limpio y tipado. Descarta lo que no parsea."""
    if not isinstance(raw, dict):
        return {}
    # Tolerar variantes de nombre de clave del modelo
    raw = dict(raw)
    if "objetos" in raw and "lista_objetos" not in raw:
        raw["lista_objetos"] = raw["objetos"]
    if "tipo" in raw and "tipo_servicio" not in raw:
        raw["tipo_servicio"] = raw["tipo"]
    out = {}

    tipo = (raw.get("tipo_servicio") or "").strip().lower()
    if tipo:
        out["tipo_servicio"] = _SINONIMOS_TIPO.get(tipo, tipo if tipo in TIPOS_VALIDOS else "")
        if not out["tipo_servicio"]:
            out.pop("tipo_servicio")

    for campo in ("distrito_origen", "distrito_destino", "direccion_origen",
                  "direccion_destino", "lista_objetos", "objetos_pesados"):
        val = (raw.get(campo) or "").strip()
        if val and val.lower() not in ("null", "none", "-", "n/a"):
            if campo in ("distrito_origen", "distrito_destino"):
                val = _title_lugar(val)
            out[campo] = val[: _MAX_LEN.get(campo, 255)]

    for campo, origen in (("piso_origen", "piso_origen"), ("piso_destino", "piso_destino")):
        if origen in raw:
            n = _a_int(raw[origen])
            if n is not None and -10 <= n <= 60:  # negativos = sótanos
                out[campo] = n

    for campo in ("ascensor_origen", "ascensor_destino"):
        if campo in raw:
            b = _a_bool(raw[campo])
            if b is not None:
                out[campo] = b

    if "embalaje" in raw:
        b = _a_bool(raw["embalaje"])
        if b is not None:
            out["modalidad_servicio"] = "embalaje basico" if b else "sin embalaje"

    if raw.get("fecha"):
        f, texto = _parsear_fecha(raw["fecha"])
        if f:
            out["fecha_servicio"] = f.isoformat()
        elif texto:
            out["fecha_texto"] = texto

    if raw.get("horario"):
        out["horario_servicio"] = str(raw["horario"]).strip()[:80]

    # Precio negociado en el chat — REFERENCIA para el asesor, no se vuelca al
    # Lead ni mueve el pipeline. El asesor lo confirma/edita desde "Cotizar".
    precio_chat = _a_num(raw.get("precio_acordado"))
    if precio_chat and 0 < precio_chat <= 100000:
        out["precio_chat"] = round(precio_chat, 2)
        if _a_bool(raw.get("precio_aceptado_por_cliente")):
            out["precio_chat_aceptado"] = True
        inc = str(raw.get("precio_incluye") or "").strip()
        if inc and inc.lower() not in ("null", "none", "-", "n/a"):
            out["precio_chat_incluye"] = inc[:200]
        cond = str(raw.get("precio_condiciones") or "").strip()
        if cond and cond.lower() not in ("null", "none", "-", "n/a"):
            out["precio_chat_condiciones"] = cond[:200]

    kg = _peso_a_kg(raw.get("peso_kg"))
    if kg:
        out["peso_carga_kg"] = kg
    vol = _a_num(raw.get("volumen_m3"))
    if vol and 0 < vol <= 500:
        out["volumen_carga_m3"] = round(vol, 2)

    # Servicio de solo personal (estiba / cargadores) sin traslado: no lleva
    # tipo_servicio y por tanto nunca alcanza el umbral de Lead.
    if _a_bool(raw.get("solo_personal")):
        out.pop("tipo_servicio", None)
        out["solo_personal"] = True
        out["incluye_personal_carga"] = True

    # Ámbito de la ruta. El campo del modelo manda; si dice 'local' pero aparece
    # una ciudad de provincia, gana la provincia (evita falsos 'local').
    ambito = str(raw.get("ambito") or "").strip().lower()
    lugares = f"{out.get('distrito_origen', '')} {out.get('distrito_destino', '')}"
    if out.get("distrito_origen") or out.get("distrito_destino"):
        if ambito == "interprovincial" or _menciona_ciudad_no_lima(lugares):
            out["ruta_interprovincial"] = True
        elif ambito == "local":
            out["ruta_interprovincial"] = False

    # Señales de "esto lo tiene que ver un humano", aunque el bot no haya
    # logrado completar tipo_servicio + distritos todavía.
    for campo_raw, campo_out in (
        ("quiere_hablar_con_asesor", "quiere_asesor"),
        ("pide_precio_sin_dar_datos", "pide_precio_sin_datos"),
        ("no_responde_preguntas_del_bot", "no_responde_preguntas"),
        ("carga_dificil_de_cotizar", "carga_compleja"),
    ):
        if _a_bool(raw.get(campo_raw)):
            out[campo_out] = True

    # Intención de cotizar: el cliente quiere contratar/cotizar (aunque falten
    # datos). NO es una señal de intervención — sirve para crear el Lead antes y
    # dejarlo en "Oportunidades".
    if _a_bool(raw.get("quiere_cotizar")):
        out["quiere_cotizar"] = True

    return out


# Señal -> motivo legible que verá el asesor en "Para revisión".
MOTIVOS_INTERVENCION_HUMANA = (
    ("quiere_asesor", "Cliente pide hablar con un asesor"),
    ("pide_precio_sin_datos", "Cliente pide precio sin haber dado los datos mínimos"),
    ("no_responde_preguntas", "El cliente no responde lo que el bot pregunta"),
    ("carga_compleja", "Carga atípica, difícil de cotizar automáticamente"),
)


def hay_intencion_de_cotizar(datos):
    """True si el cliente mostró que quiere contratar/cotizar el servicio, aunque
    falten datos. Crea el Lead antes de completar tipo_servicio + distritos y lo
    deja en "Oportunidades" (a diferencia de las señales de intervención, que
    marcan requiere_asesor y mandan a "Para revisión")."""
    return bool(datos.get("quiere_cotizar"))


def requiere_intervencion_humana(datos):
    """True si alguna señal de las de arriba está marcada en `datos`
    (datos_extraidos acumulado). Se usa para escalar la conversación a "Para
    revisión" aunque el bot NUNCA haya llegado a completar tipo_servicio +
    ambos distritos (el caso típico: el cliente solo quiere un asesor o el
    precio, y no coopera con las preguntas del bot)."""
    return any(datos.get(campo) for campo, _texto in MOTIVOS_INTERVENCION_HUMANA)


# --- Umbral -------------------------------------------------------------------

def alcanza_minimo_para_cotizar(datos):
    """Mínimo para que la conversación se convierta en Lead comercial:
    tipo_servicio + AMBOS distritos. Con menos, el cotizador cae al fallback de
    precios genéricos; con los dos distritos usa el histórico real."""
    return bool(
        datos.get("tipo_servicio")
        and datos.get("distrito_origen")
        and datos.get("distrito_destino")
    )


# --- Volcado a Lead -----------------------------------------------------------

_CAMPOS_LEAD_DIRECTOS = (
    "tipo_servicio", "distrito_origen", "distrito_destino",
    "direccion_origen", "direccion_destino",
    "piso_origen", "piso_destino", "ascensor_origen", "ascensor_destino",
    "lista_objetos", "objetos_pesados", "modalidad_servicio", "horario_servicio",
    "peso_carga_kg", "volumen_carga_m3",
)

def volcar_datos_extraidos_al_lead(lead, datos, *, solo_vacios=True):
    """Copia `datos` (dict de datos_extraidos) a los campos del Lead.

    solo_vacios=True: solo rellena campos actualmente vacíos/None — NUNCA pisa un
    valor que ya está (puede ser una edición del asesor).
    Devuelve la lista de campos realmente modificados.
    """
    cambios = []

    def _vacio(actual):
        return actual in (None, "", 0) or actual is False

    for campo in _CAMPOS_LEAD_DIRECTOS:
        if campo not in datos:
            continue
        nuevo = datos[campo]
        actual = getattr(lead, campo)
        if solo_vacios and not _vacio(actual):
            continue
        if actual == nuevo:
            continue
        setattr(lead, campo, nuevo)
        cambios.append(campo)

    if datos.get("incluye_personal_carga") is True and lead.incluye_personal_carga is None:
        lead.incluye_personal_carga = True
        cambios.append("incluye_personal_carga")

    if datos.get("ruta_interprovincial") is True:
        # Marca estructurada (para reportes y para el cotizador).
        if not lead.es_interprovincial:
            lead.es_interprovincial = True
            cambios.append("es_interprovincial")
        # Salvaguarda del cotizador: no auto-cotizar rutas fuera de Lima.
        if not lead.requiere_asesor:
            lead.requiere_asesor = True
            cambios.append("requiere_asesor")

    for campo, texto in MOTIVOS_INTERVENCION_HUMANA:
        if datos.get(campo) is not True:
            continue
        if not lead.requiere_asesor:
            lead.requiere_asesor = True
            cambios.append("requiere_asesor")
        detalle_actual = lead.motivo_derivacion or ""
        if texto not in detalle_actual:
            lead.motivo_derivacion = (
                f"{detalle_actual} · {texto}".strip(" ·") if detalle_actual else texto
            )
            if "motivo_derivacion" not in cambios:
                cambios.append("motivo_derivacion")

    if "fecha_servicio" in datos and (not solo_vacios or lead.fecha_servicio is None):
        try:
            f = date.fromisoformat(datos["fecha_servicio"])
            if lead.fecha_servicio != f:
                lead.fecha_servicio = f
                cambios.append("fecha_servicio")
        except (ValueError, TypeError):
            pass
    elif datos.get("fecha_texto") and not lead.fecha_servicio and not lead.fecha_por_confirmar:
        lead.fecha_por_confirmar = True
        cambios.append("fecha_por_confirmar")

    if cambios:
        lead.save(update_fields=cambios)
    return cambios


# --- Orquestador por conversación --------------------------------------------

def extraer_datos_conversacion(conversacion, *, dry_run=False):
    """Procesa UNA conversación. Devuelve un reporte (dict). Nunca lanza.

    dry_run=True: no escribe nada (ni datos_extraidos, ni Lead, ni la marca de
    tiempo) — solo devuelve qué haría.
    """
    reporte = {
        "conversacion_id": conversacion.id,
        "cliente": (conversacion.cliente.profile_name if conversacion.cliente else "?"),
        "telefono": (conversacion.cliente.contact_phone if conversacion.cliente else ""),
        "mensajes_analizados": 0,
        "detectado": {},
        "aplicado": {},
        "alcanza_umbral": False,
        "intencion_cotizar": False,
        "lead_id": conversacion.lead_id,
        "lead_accion": "ninguna",
        "error": None,
    }

    if conversacion.cliente and conversacion.cliente.es_transportista:
        reporte["error"] = "transportista — se omite"
        return reporte

    from apps.whatsapp_bot_v4.models import BotGlobalConfig
    bot_config = BotGlobalConfig.objects.first()
    if bot_config and bot_config.operativo_paused:
        reporte["error"] = "bot operativo pausado — barrido detenido"
        return reporte

    historial = _historial_para_prompt(conversacion)
    reporte["mensajes_analizados"] = historial.count("\n") + 1 if historial else 0
    if not historial:
        total = MensajeWhatsApp.objects.filter(
            conversacion=conversacion, oculto_en_crm=False
        ).count()
        reporte["error"] = (
            f"sin texto que analizar ({total} mensaje(s), solo imagen/audio/ubicación)"
            if total else "sin mensajes"
        )
        return reporte

    crudo = _llamar_openai(historial)
    if crudo is None:
        reporte["error"] = "OpenAI no disponible o falló"
        return reporte

    detectado = _normalizar_extraccion(crudo)
    reporte["detectado"] = detectado

    # Fusión con lo ya acumulado. Cada barrido ve TODO el historial (60 msgs), así
    # que la última extracción es la mejor estimación: para las claves que devuelve
    # el modelo, gana el valor nuevo. Las que el modelo omite se conservan.
    acumulado = dict(conversacion.datos_extraidos or {})
    aplicado = {}
    # Reclasificación a 'solo personal': se retira un tipo_servicio previo.
    if detectado.get("solo_personal") and acumulado.get("tipo_servicio"):
        acumulado.pop("tipo_servicio", None)
        aplicado["tipo_servicio"] = None
    for k, v in detectado.items():
        if acumulado.get(k) != v:
            acumulado[k] = v
            aplicado[k] = v
    reporte["aplicado"] = aplicado
    reporte["alcanza_umbral"] = alcanza_minimo_para_cotizar(acumulado)
    reporte["requiere_intervencion"] = requiere_intervencion_humana(acumulado)
    reporte["intencion_cotizar"] = hay_intencion_de_cotizar(acumulado)

    if dry_run:
        if (reporte["alcanza_umbral"] or reporte["requiere_intervencion"]
                or reporte["intencion_cotizar"]) and not conversacion.lead_id:
            reporte["lead_accion"] = "crearía"
        elif conversacion.lead_id:
            reporte["lead_accion"] = "actualizaría lead existente"
        if acumulado.get("precio_chat"):
            reporte["cotizacion_chat"] = f"registraría cotización S/ {acumulado['precio_chat']}"
        return reporte

    with transaction.atomic():
        conv = ConversacionWhatsApp.objects.select_for_update().get(pk=conversacion.pk)
        conv.datos_extraidos = acumulado
        conv.ultima_extraccion_en = timezone.now()
        conv.save(update_fields=["datos_extraidos", "ultima_extraccion_en", "actualizada_en"])

        lead = None
        if conv.lead_id:
            lead = type(conv.lead).objects.select_for_update().get(pk=conv.lead_id)
            cambios = volcar_datos_extraidos_al_lead(lead, acumulado, solo_vacios=True)
            reporte["lead_id"] = lead.id
            reporte["lead_accion"] = f"lead actualizado ({', '.join(cambios)})" if cambios else "lead sin cambios"
        elif (reporte["alcanza_umbral"] or reporte["requiere_intervencion"]
              or reporte["intencion_cotizar"]):
            from apps.whatsapp.domain import _obtener_o_crear_lead_para_conversacion
            lead = _obtener_o_crear_lead_para_conversacion(conv)
            if lead:
                reporte["lead_id"] = lead.id
                solo_intencion = (
                    reporte["intencion_cotizar"]
                    and not reporte["alcanza_umbral"]
                    and not reporte["requiere_intervencion"]
                )
                if solo_intencion:
                    _marcar_intencion_cotizar(lead)
                    reporte["lead_accion"] = "lead creado (intención de cotizar)"
                else:
                    reporte["lead_accion"] = "lead creado"
            else:
                reporte["lead_accion"] = "no se pudo crear lead"

        # Precio negociado en el chat -> queda registrado como cotización enviada
        # (sin mandar mensaje: el asesor ya lo habló). Así el lead entra a
        # "Cotizaciones" con su precio. El asesor lo ajusta desde "Cotizar".
        if lead and acumulado.get("precio_chat"):
            _registrar_precio_chat(conv, lead, acumulado, reporte)

    return reporte


def _marcar_intencion_cotizar(lead):
    """Traza de que el Lead nació porque el bot detectó intención de cotizar, con
    los datos aún incompletos. NO toca requiere_asesor: el lead queda en
    'Oportunidades', no en 'Para revisión'."""
    sello = timezone.localtime().strftime("%Y-%m-%d %H:%M")
    linea = f"[{sello}] intencion_cotizar: el bot detectó interés de cotizar (datos incompletos)"
    lead.nota_interna = f"{lead.nota_interna}\n{linea}".strip() if lead.nota_interna else linea
    lead.save(update_fields=["nota_interna"])


def _registrar_precio_chat(conv, lead, datos, reporte):
    precio = datos.get("precio_chat")
    try:
        from apps.cotizador.commercial import registrar_cotizacion_desde_chat
        rev = registrar_cotizacion_desde_chat(
            conv, precio,
            condiciones=datos.get("precio_chat_condiciones", ""),
            observacion=(
                "Precio detectado por la IA en el chat"
                + (" (aceptado por el cliente)" if datos.get("precio_chat_aceptado") else "")
                + (f". Incluye: {datos['precio_chat_incluye']}" if datos.get("precio_chat_incluye") else "")
            ),
            source_key=f"chat-ia:{lead.id}:{precio}",
        )
        if rev is not None:
            reporte["cotizacion_chat"] = f"S/ {precio} (rev {rev.numero})"
    except Exception as e:  # nunca romper el barrido por esto
        logger.warning("[Extraccion] No se pudo registrar precio de chat (lead %s): %s", lead.id, e)
        reporte["cotizacion_chat"] = f"error: {e}"


# --- Selección de conversaciones para el barrido -----------------------------

def conversaciones_pendientes(*, todas=False, limite=None):
    """Conversaciones a procesar en un ciclo de barrido.

    Por defecto: las que tienen un mensaje ENTRANTE más nuevo que su última
    extracción. `todas=True`: todas las no-transportista no cerradas (para el
    reproceso retroactivo).
    """
    qs = (
        ConversacionWhatsApp.objects
        .select_related("cliente", "lead", "channel")
        .filter(cliente__es_transportista=False)
        .exclude(estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA)
    )
    if not todas:
        qs = qs.filter(
            ultimo_mensaje_cliente__isnull=False,
        ).filter(
            models.Q(ultima_extraccion_en__isnull=True)
            | models.Q(ultimo_mensaje_cliente__gt=models.F("ultima_extraccion_en"))
        )
    qs = qs.order_by("-ultima_actividad")
    if limite:
        qs = qs[:limite]
    return qs
