"""Utilidades de servicios: parseo del horario libre + regla de modalidad."""
import re
from datetime import datetime


def parse_horario(texto):
    """`horario_servicio` es texto libre ('9:30 am', '17:00', 'por confirmar').
    Devuelve un `time` o None."""
    t = (texto or "").strip().lower()
    if not t:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I %p", "%I%p", "%I:%M%p"):
        try:
            return datetime.strptime(t, fmt).time()
        except ValueError:
            continue
    # "9am", "9 am", "9:30am", "9.30 pm", "9 y 30"
    m = re.search(r"(\d{1,2})(?:[:.h ](\d{2}))?\s*(a\.?m\.?|p\.?m\.?|hs?|horas?)?", t)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    suf = (m.group(3) or "").replace(".", "")
    if suf.startswith("p") and hh < 12:
        hh += 12
    if suf.startswith("a") and hh == 12:
        hh = 0
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        from datetime import time
        return time(hh, mm)
    return None


def modalidad_por_horario(horario_texto):
    """Devuelve 'propio' | 'tercerizado' según la ventana nocturna configurada.
    Sin hora reconocible → 'propio' (el asesor decide)."""
    from apps.servicios.models import ConfiguracionOperaciones, Servicio

    hora = parse_horario(horario_texto)
    if hora is None:
        return Servicio.MODALIDAD_PROPIO
    cfg = ConfiguracionOperaciones.get_solo()
    return (
        Servicio.MODALIDAD_TERCERIZADO if cfg.es_nocturno(hora)
        else Servicio.MODALIDAD_PROPIO
    )
