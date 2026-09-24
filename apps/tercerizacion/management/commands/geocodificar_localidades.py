"""Geocodifica las localidades del catálogo de 40 corredores nacionales
(`apps/tercerizacion/fixtures/corredores_40.json`) contra GeoNames — fuente
pública, gratuita, sin límite de uso (https://www.geonames.org, datos bajo
licencia CC-BY 4.0; atribución: "Geographical data © GeoNames.org").

No se usa Mapbox para esto (ver `calcular_tramos_corredores.py` para la
geometría de tramos, que sí usa Mapbox Directions) — GeoNames ya trae
lat/lng verificado por localidad, sin costo ni token.

Algoritmo (validado a mano en la sesión de diseño contra los 106 nombres del
catálogo real, 104/106 resueltos): normaliza el nombre buscado, busca por
`name`/`asciiname`/cada `alternatename` entre las localidades pobladas
(`feature class = P`) de Perú, y **filtra por el departamento esperado**
(tabla `DEPARTAMENTO_ESPERADO`, derivada de en qué corredor/posición
aparece cada nombre) antes de decidir por población — sin ese filtro, el
criterio ingenuo "mayor población" falla silenciosamente en pueblos
costeros con población=0 en GeoNames (ej. "Ocoña" resolvía a Puno en vez de
Arequipa). Si ningún candidato cae en el departamento esperado, o el nombre
no tiene hint de departamento y hay más de un candidato poblado, la
localidad queda `AMBIGUO` — nunca se adivina.

    python manage.py geocodificar_localidades [--force]

--force reintenta localidades que ya están RESUELTO/AMBIGUO (nunca toca una
con `modificado_manualmente=True`, eso ni con --force).

Exporta dos CSV (pedido explícito del negocio) en el directorio del comando:
    apps/tercerizacion/data/localidades.csv
    apps/tercerizacion/data/corredores_localidades.csv
"""
import csv
import json
import os
import unicodedata
import zipfile
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand

from apps.tercerizacion.models import Localidad

GEONAMES_URL = "https://download.geonames.org/export/dump/PE.zip"
ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures" / "corredores_40.json"

# Departamento esperado por localidad (normalizado sin tildes) — derivado de
# en qué corredor/posición aparece cada nombre en el catálogo de 40
# corredores. Evita que el geocoder "adivine" un homónimo en otro
# departamento (mismo problema que ya causó el bug de "Surco" con Mapbox).
DEPARTAMENTO_ESPERADO = {
    "lima": ["Lima region"], "chancay": ["Lima region"], "huacho": ["Lima region"],
    "barranca": ["Lima region"], "pativilca": ["Lima region"], "huarmey": ["Ancash"],
    "casma": ["Ancash"], "chimbote": ["Ancash"], "chao": ["La Libertad"], "viru": ["La Libertad"],
    "trujillo": ["La Libertad"], "paijan": ["La Libertad"], "pacasmayo": ["La Libertad"],
    "guadalupe": ["La Libertad"], "chepen": ["La Libertad"], "chiclayo": ["Lambayeque"],
    "lambayeque": ["Lambayeque"], "morrope": ["Lambayeque"], "piura": ["Piura"],
    "sullana": ["Piura"], "talara": ["Piura"], "los organos": ["Piura"], "mancora": ["Piura"],
    "zorritos": ["Tumbes"], "tumbes": ["Tumbes"], "paita": ["Piura"],
    "tembladera": ["Cajamarca"], "chilete": ["Cajamarca"], "cajamarca": ["Cajamarca"],
    "olmos": ["Lambayeque"], "pucara": ["Cajamarca", "Lambayeque"], "chamaya": ["Cajamarca"],
    "jaen": ["Cajamarca"], "corral quemado": ["Amazonas", "Cajamarca"], "bagua grande": ["Amazonas"],
    "pedro ruiz": ["Amazonas"], "chachapoyas": ["Amazonas"],
    "nueva cajamarca": ["San Martin"], "rioja": ["San Martin"], "moyobamba": ["San Martin"],
    "tarapoto": ["San Martin"], "pongo de caynarachi": ["San Martin", "Loreto"], "yurimaguas": ["Loreto"],
    "chongoyape": ["Lambayeque"], "llama": ["Cajamarca"], "cochabamba": ["Cajamarca"],
    "chota": ["Cajamarca"], "hualgayoc": ["Cajamarca"],
    "asia": ["Lima region"], "cerro azul": ["Lima region"], "san vicente de canete": ["Lima region"],
    "chincha alta": ["Ica"], "pisco": ["Ica"], "ica": ["Ica"], "palpa": ["Ica"], "nazca": ["Ica"],
    "chala": ["Arequipa"], "atico": ["Arequipa"], "ocona": ["Arequipa"], "camana": ["Arequipa"],
    "arequipa": ["Arequipa"], "matarani": ["Arequipa"], "la joya": ["Arequipa"],
    "moquegua": ["Moquegua"], "locumba": ["Tacna"], "tacna": ["Tacna"], "ilo": ["Moquegua"],
    "chosica": ["Lima region"], "matucana": ["Lima region"], "san mateo": ["Lima region"],
    "conococha": ["Ancash"], "catac": ["Ancash"], "recuay": ["Ancash"], "huaraz": ["Ancash"],
    "la oroya": ["Junin"], "jauja": ["Junin"], "concepcion": ["Junin"], "huancayo": ["Junin"],
    "junin": ["Junin"], "cerro de pasco": ["Pasco"], "ambo": ["Huanuco"],
    "huanuco": ["Huanuco"], "tingo maria": ["Huanuco"], "aguaytia": ["Ucayali"],
    "pucallpa": ["Ucayali"], "huaytara": ["Huancavelica"], "ayacucho": ["Ayacucho"],
    "puquio": ["Ayacucho"], "chalhuanca": ["Apurimac"], "abancay": ["Apurimac"],
    "cusco": ["Cuzco"], "urcos": ["Cuzco"], "quincemil": ["Cuzco"],
    "mazuko": ["Madre de Dios"], "puerto maldonado": ["Madre de Dios"], "yura": ["Arequipa"],
    "imata": ["Arequipa"], "santa lucia": ["Puno"], "juliaca": ["Puno"], "puno": ["Puno"],
    "espinar": ["Cuzco"], "sicuani": ["Cuzco"], "izcuchaca": ["Huancavelica"],
    "huancavelica": ["Huancavelica"], "aucayacu": ["Huanuco"], "tocache": ["San Martin"],
    "juanjui": ["San Martin"], "bellavista": ["San Martin"], "picota": ["San Martin"],
    "el cruce": ["Lambayeque", "Piura"],
}


def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


class Command(BaseCommand):
    help = "Geocodifica las localidades del catálogo de 40 corredores contra GeoNames."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Reintenta localidades RESUELTO/AMBIGUO (nunca las modificadas a mano).")

    def handle(self, *args, **opts):
        force = opts["force"]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        pe_txt = DATA_DIR / "PE.txt"
        admin1_txt = DATA_DIR / "admin1CodesASCII.txt"
        self._descargar_si_falta(pe_txt, GEONAMES_URL)
        self._descargar_si_falta(admin1_txt, ADMIN1_URL)

        admin1 = self._cargar_admin1(admin1_txt)
        admin1_rev = {}
        for code, name in admin1.items():
            short = name.replace(" Department", "").replace(" region", "").replace(" Province", "")
            admin1_rev.setdefault(_norm(short), []).append(code)

        indice = self._cargar_indice(pe_txt)
        nombres = self._extraer_nombres_del_fixture()

        filas_localidades = []
        filas_corredores = []
        n_resuelto, n_ambiguo, n_sin = 0, 0, 0

        for nombre in nombres:
            existente = Localidad.objects.filter(nombre_normalizado=_norm(nombre)).first()
            if existente and (existente.modificado_manualmente or (not force and existente.estado_validacion != Localidad.ESTADO_PENDIENTE)):
                estado = "resuelto" if existente.estado_validacion == Localidad.ESTADO_RESUELTO else "sin_tocar"
                filas_localidades.append([nombre, existente.nombre, existente.departamento, existente.lat, existente.lng, existente.geonames_id, estado, "ya existía"])
                if existente.estado_validacion == Localidad.ESTADO_RESUELTO:
                    n_resuelto += 1
                continue

            resultado = self._resolver(nombre, indice, admin1, admin1_rev)
            if resultado is None:
                n_sin += 1
                filas_localidades.append([nombre, "", "", "", "", "", "sin_coincidencia", "no existe en GeoNames"])
                Localidad.objects.update_or_create(
                    nombre_normalizado=_norm(nombre), departamento="",
                    defaults={"nombre": nombre, "estado_validacion": Localidad.ESTADO_AMBIGUO, "fuente_geografica": ""},
                )
                continue
            if resultado.get("ambiguo"):
                n_ambiguo += 1
                filas_localidades.append([nombre, "", "", "", "", "", "ambiguo", resultado["observacion"]])
                Localidad.objects.update_or_create(
                    nombre_normalizado=_norm(nombre), departamento="",
                    defaults={"nombre": nombre, "estado_validacion": Localidad.ESTADO_AMBIGUO, "fuente_geografica": ""},
                )
                continue

            n_resuelto += 1
            r = resultado
            filas_localidades.append([nombre, r["nombre"], r["departamento"], r["lat"], r["lng"], r["geonames_id"], "resuelto", ""])
            # Clave de búsqueda = geonames_id (identificador estable del lugar
            # real), no el nombre buscado: el nombre resuelto puede diferir
            # del término de búsqueda (p. ej. "Chala" -> "Chala Viejo"), y
            # `Localidad.save()` recalcula `nombre_normalizado` a partir del
            # nombre RESUELTO — usar el término buscado como clave chocaría
            # contra esa fila ya guardada bajo su propio nombre.
            Localidad.objects.update_or_create(
                geonames_id=r["geonames_id"],
                defaults={
                    "nombre": r["nombre"], "lat": r["lat"], "lng": r["lng"],
                    "fuente_geografica": "geonames", "estado_validacion": Localidad.ESTADO_RESUELTO,
                    "departamento": r["departamento"], "provincia": r.get("provincia", ""),
                },
            )

        self._exportar_csv(filas_localidades, filas_corredores)

        total = len(nombres)
        self.stdout.write(self.style.SUCCESS(
            f"Localidades únicas: {total} · resueltas: {n_resuelto} · ambiguas: {n_ambiguo} · sin coincidencia: {n_sin}",
        ))
        self.stdout.write(f"CSV exportados en {DATA_DIR}")

    # -- helpers -------------------------------------------------------

    def _descargar_si_falta(self, destino, url):
        if destino.exists():
            return
        self.stdout.write(f"Descargando {url} ...")
        with httpx.Client(timeout=60) as client:
            r = client.get(url)
            r.raise_for_status()
        if url.endswith(".zip"):
            tmp_zip = destino.with_suffix(".zip")
            tmp_zip.write_bytes(r.content)
            with zipfile.ZipFile(tmp_zip) as zf:
                zf.extract(destino.name, DATA_DIR)
        else:
            destino.write_bytes(r.content)

    def _cargar_admin1(self, path):
        out = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].startswith("PE."):
                out[parts[0]] = parts[1]
        return out

    def _cargar_indice(self, path):
        indice = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            p = line.split("\t")
            if len(p) < 19:
                continue
            rec = {
                "id": p[0], "name": p[1], "ascii": p[2],
                "alt": [a for a in p[3].split(",") if a],
                "lat": p[4], "lng": p[5], "fclass": p[6], "fcode": p[7],
                "admin1": p[10], "admin2": p[11], "pop": int(p[14] or 0),
            }
            for key in {_norm(rec["name"]), _norm(rec["ascii"])} | {_norm(a) for a in rec["alt"]}:
                if key:
                    indice.setdefault(key, []).append(rec)
        return indice

    def _extraer_nombres_del_fixture(self):
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        vistos, out = set(), []
        for corredor in data:
            for nombre in corredor["secuencia"]:
                k = _norm(nombre)
                if k not in vistos:
                    vistos.add(k)
                    out.append(nombre)
        return out

    def _resolver(self, nombre, indice, admin1, admin1_rev):
        cands = indice.get(_norm(nombre), [])
        pop_cands = [c for c in cands if c["fclass"] == "P"]
        if not cands:
            return None
        deptos = DEPARTAMENTO_ESPERADO.get(_norm(nombre), [])
        depto_codes = set()
        for d in deptos:
            d_short = d.replace(" Department", "").replace(" region", "").replace(" Province", "")
            depto_codes |= set(admin1_rev.get(_norm(d_short), []))
        depto_short = {c.split(".")[1] for c in depto_codes}
        en_depto = [c for c in pop_cands if c["admin1"] in depto_short]
        if en_depto:
            en_depto.sort(key=lambda r: -r["pop"])
            best = en_depto[0]
            return {
                "nombre": best["name"], "departamento": admin1.get("PE." + best["admin1"], ""),
                "lat": best["lat"], "lng": best["lng"], "geonames_id": best["id"],
            }
        return {"ambiguo": True, "observacion": "ningún candidato poblado cae en el departamento esperado" if deptos else "sin hint de departamento y con candidatos ambiguos"}

    def _exportar_csv(self, filas_localidades, filas_corredores):
        with open(DATA_DIR / "localidades.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["nombre_buscado", "nombre_geonames", "departamento", "lat", "lng", "geonames_id", "estado", "observaciones"])
            w.writerows(filas_localidades)

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        with open(DATA_DIR / "corredores_localidades.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["codigo_corredor", "nombre_corredor", "localidad", "orden", "tipo_punto", "estado_validacion"])
            for corredor in data:
                for i, nombre in enumerate(corredor["secuencia"]):
                    tipo = "origen" if i == 0 else "destino" if i == len(corredor["secuencia"]) - 1 else "intermedio"
                    loc = Localidad.objects.filter(nombre_normalizado=_norm(nombre)).first()
                    estado = loc.estado_validacion if loc else "sin_registrar"
                    w.writerow([corredor["codigo"], corredor["nombre"], nombre, i, tipo, estado])
