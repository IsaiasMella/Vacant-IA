"""Fuente: Get on Board (getonbrd.com), por su API pública.

**Es la única fuente que no scrapea nada y no gasta una sola credencial.**
Get on Board publica una API REST abierta, sin token, y devuelve el aviso ya
estructurado: título, descripción, modalidad, países y fecha de publicación. Se
lee con `urllib`, que ya viene con Python.

Eso la hace la fuente más barata y la más confiable que tiene el sistema, y por
eso conviene tenerla prendida aunque falte `TINYFISH_API_KEY`: cuando las demás
se saltean por falta de credencial, ésta sigue trayendo.

Verificado contra la API real el 9/9/2026:

    GET /api/v0/search/jobs?query=AI%20Engineer&country_code=AR&per_page=30
    -> 200, {"data": [...], "meta": {"page":1,"per_page":30,"total_pages":2}}

**El portal es sobre todo chileno**, así que sin `country_code` la mitad de lo
que trae son avisos presenciales en Santiago. Con `country_code=AR` devuelve los
que aplican a la Argentina, que en los hechos son casi todos remotos: en la
prueba, 60 de 60. Es exactamente el recorte que sirve acá.

El nombre de la empresa no viene en el listado salvo que se pida con
`expand=["company"]` (así, como arreglo JSON: `expand=company` devuelve 422).
Verificado el 19/11/2026. Sin eso había que pedir `/companies/{id}` aparte por
cada empresa; queda como respaldo, con caché por corrida, porque sin el nombre
el dedupe por empresa+título no corre (ver `Job.dedupe_key`).

**Dos maneras de leerla.**

* **Por categoría** (`"categorias": ["programming", "machine-learning-ai"]`):
  trae **todas** las ofertas activas de esas categorías en cada corrida, sin
  términos y sin rotación. Es la que conviene cuando el puesto cae en una
  categoría de Get on Board, que es todo lo que sea tecnología.
* **Por términos** (sin `categorias`): la búsqueda de siempre, con los puestos
  del perfil rotados por corrida. Queda para perfiles que no son de tecnología.

**Por qué existe el modo por categoría (19/11/2026).** El mercado entero es
chico: con `country_code=AR` había **101 ofertas activas en todo el portal**, 29
en *programming* y 14 en *machine-learning-ai*. Pero Isaías lo recorría con 17
términos de a 3 por corrida, y hasta el 18/11 la rotación era por día: dar la
vuelta llevaba unos 6 días. Medido contra su historial:

* De las 113 ofertas de Get on Board que tenía, 25 entraron **entre 4 y 7 días**
  después de publicadas, cuando se corre tres veces por día.
* De las 89 que se tiraron por "más de 7 días", **42 nunca se habían visto**:
  se publicaron, estuvieron frescas y ningún término de la tanda las trajo.

Leyendo las dos categorías enteras son 2 pedidos por corrida (la API devuelve
hasta 100 por página), gratis, y no se escapa ninguna. El tope de páginas
(`max_paginas`) está para que un perfil sin `country_code` no se baje las 300
de programación del portal entero.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape

from vacantia import rotacion
from vacantia.config import terminos_de_busqueda
from vacantia.log import get_logger
from vacantia.models import Job
from vacantia.sources.base import Source

logger = get_logger()

API = "https://www.getonbrd.com/api/v0"

#: Sin User-Agent de navegador el borde de Cloudflare que tiene delante contesta
#: 403, igual que a cualquier cliente que se anuncia como script.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

#: Cómo se llama la modalidad en la API y cómo la llama `filters.py`.
_MODALIDAD = {"fully_remote": "remote", "remote": "remote",
              "hybrid": "hybrid", "no_remote": "onsite", "onsite": "onsite"}

_ETIQUETAS = re.compile(r"<[^>]+>")

#: Para que el nombre de la empresa venga adentro del aviso. Tiene que ir como
#: arreglo JSON: `expand=company` devuelve 422 (probado el 19/11/2026).
_EXPANDIR = '["company"]'


def _texto(html: str) -> str:
    """El HTML del aviso como texto plano, que es lo que puntúa el modelo."""
    plano = re.sub(r"<(br|/p|/div|/li|/h\d)[^>]*>", "\n", str(html or ""),
                   flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", unescape(_ETIQUETAS.sub("", plano))).strip()


class GetOnBoardSource(Source):
    name = "getonbrd"

    def __init__(self, config: dict, profile: dict):
        super().__init__(config, profile)
        self.api = str(config.get("api_url") or API).rstrip("/")
        # El portal es chileno: sin esto, la mitad de lo que trae son
        # presenciales en Santiago. "" apaga el recorte a propósito.
        self.country_code = str(config.get("country_code", "AR") or "")
        self.results_wanted = int(config.get("results_wanted", 30))
        self.max_queries = int(config.get("max_queries", 3))
        self.timeout = int(config.get("timeout", 25))
        #: Las categorías a leer enteras. Vacío = buscar por términos.
        self.categorias = [str(c).strip() for c in (config.get("categorias") or [])
                           if str(c).strip()]
        self.max_paginas = max(1, int(config.get("max_paginas", 3) or 3))
        self._empresas: dict[int, str] = {}

    # --- qué buscar -----------------------------------------------------

    def terminos(self) -> list[str]:
        """Los términos, rotados por corrida como en las otras fuentes.

        Sin rotación, con `max_queries` chico los últimos términos del perfil no
        se consultarían nunca. Deja anotado desde dónde sigue la próxima
        corrida, que el motor guarda al final (ver `rotacion`).
        """
        crudos = terminos_de_busqueda(self.profile, self.config.get("search_terms"))
        terminos = [str(t).strip() for t in crudos if str(t).strip()]
        tanda, self.siguiente_en_rotacion = rotacion.elegir(
            self.profile, self.name, terminos, self.max_queries)
        return tanda

    def is_available(self) -> tuple[bool, str]:
        # No pide credenciales: lo único que puede faltar es qué buscar.
        if self.categorias:
            return True, ""
        if not self.terminos():
            return False, "el perfil no tiene keywords ni search_terms"
        return True, ""

    # --- red ------------------------------------------------------------

    def _get(self, ruta: str, **params) -> dict:
        """Un GET a la API. {} si falla: una consulta caída no tumba la corrida."""
        url = f"{self.api}/{ruta.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v not in ("", None)})
        pedido = urllib.request.Request(
            url, headers={"User-Agent": _UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            logger.warning(f"[{self.name}] {e.code} en {ruta}")
        except Exception as e:
            logger.warning(f"[{self.name}] No pude leer {ruta}: {e}")
        return {}

    def _empresa(self, datos: dict) -> str:
        """El nombre de la empresa: el que vino en el listado, o pedido por id.

        Con `expand=["company"]` el nombre ya viene adentro del aviso. Si no
        vino, se pide aparte y se cachea por corrida: varios avisos comparten
        empresa, y sin el nombre `Job.dedupe_key` devuelve "" y el dedupe por
        empresa+título no corre.
        """
        relacion = (datos.get("company") or {}).get("data") or {}
        if nombre := str((relacion.get("attributes") or {}).get("name") or "").strip():
            return nombre
        rel = relacion.get("id")
        if not rel:
            return ""
        if rel not in self._empresas:
            cuerpo = self._get(f"companies/{rel}")
            self._empresas[rel] = str(
                ((cuerpo.get("data") or {}).get("attributes") or {}).get("name") or "")
        return self._empresas[rel]

    # --- armado ---------------------------------------------------------

    def _a_job(self, crudo: dict, termino: str) -> Job | None:
        datos = crudo.get("attributes") or {}
        url = ((crudo.get("links") or {}).get("public_url") or "").strip()
        titulo = str(datos.get("title") or "").strip()
        if not url or not titulo:
            return None

        # La descripción del aviso está partida en cuatro campos de HTML, y los
        # cuatro dicen algo que el modelo necesita para puntuar: qué piden, qué
        # vas a hacer, qué es deseable y de qué va la empresa.
        cuerpo = "\n\n".join(
            filter(None, (_texto(datos.get(c)) for c in
                          ("description", "functions", "desirable", "projects"))))

        paises = [str(p) for p in (datos.get("countries") or []) if p]
        # "Remote" en la lista de países no es un país: es la modalidad, y
        # ponerlo en `country` haría que el filtro de ubicación lo compare
        # contra "Argentina" y lo tire.
        reales = [p for p in paises if p.lower() != "remote"]
        remoto = bool(datos.get("remote")) or "remote" in [p.lower() for p in paises]

        publicado = ""
        if sello := datos.get("published_at"):
            try:
                publicado = datetime.fromtimestamp(
                    int(sello), tz=timezone.utc).date().isoformat()
            except (ValueError, OSError, TypeError):
                publicado = ""

        modalidad = _MODALIDAD.get(str(datos.get("remote_modality") or "").lower(), "")
        return Job(
            url=url,
            title=titulo,
            company=self._empresa(datos),
            source=self.name,
            location=", ".join(paises),
            description=cuerpo[:3000],
            descripcion_completa=cuerpo,
            posted_at=publicado,
            country=reales[0] if reales else ("Argentina" if self.country_code == "AR" else ""),
            work_mode=modalidad or ("remote" if remoto else ""),
            raw={"portal": "Get on Board", "busqueda": termino,
                 "categoria": datos.get("category_name") or "",
                 "postulantes": datos.get("applications_count"),
                 "sueldo_min": datos.get("min_salary"),
                 "sueldo_max": datos.get("max_salary")},
        )

    # --- interfaz Source ------------------------------------------------

    def _por_categoria(self) -> list[Job]:
        """Todas las ofertas activas de cada categoría, página por página."""
        pais = f" (país {self.country_code})" if self.country_code else ""
        logger.info(f"[{self.name}] {len(self.categorias)} categoría(s) en Get on Board{pais}")

        jobs: list[Job] = []
        vistos: set[str] = set()
        for categoria in self.categorias:
            leidos = nuevos = 0
            for pagina in range(1, self.max_paginas + 1):
                cuerpo = self._get(f"categories/{categoria}/jobs",
                                   country_code=self.country_code, per_page=100,
                                   page=pagina, expand=_EXPANDIR)
                crudos = cuerpo.get("data") or []
                leidos += len(crudos)
                for uno in crudos:
                    job = self._a_job(uno, categoria)
                    if job is None or job.url.lower() in vistos:
                        continue
                    vistos.add(job.url.lower())
                    jobs.append(job)
                    nuevos += 1
                total = int((cuerpo.get("meta") or {}).get("total_pages") or 1)
                if not crudos or pagina >= total:
                    break
            logger.info(f"[{self.name}]   '{categoria}': {leidos} aviso(s), {nuevos} nuevos")
        return jobs

    def _por_terminos(self) -> list[Job]:
        """La búsqueda por los puestos del perfil, rotados por corrida."""
        terminos = self.terminos()
        logger.info(f"[{self.name}] {len(terminos)} búsqueda(s) en Get on Board"
                    f"{f' (país {self.country_code})' if self.country_code else ''}")

        # El cupo se reparte entre los términos. Pidiendo `results_wanted` de
        # cada uno, el primero lo llenaba solo y el segundo no aportaba nunca:
        # medido, 'Backend' devolvía 30 y 'AI Engineer' 0 nuevos.
        por_termino = max(10, self.results_wanted // max(1, len(terminos)))

        jobs: list[Job] = []
        vistos: set[str] = set()
        for termino in terminos:
            cuerpo = self._get("search/jobs", query=termino,
                               country_code=self.country_code,
                               per_page=min(por_termino, 50), expand=_EXPANDIR)
            crudos = cuerpo.get("data") or []
            nuevos = 0
            for uno in crudos:
                if len(jobs) >= self.results_wanted:
                    break
                job = self._a_job(uno, termino)
                if job is None or job.url.lower() in vistos:
                    continue
                vistos.add(job.url.lower())
                jobs.append(job)
                nuevos += 1
            logger.info(f"[{self.name}]   '{termino}': {len(crudos)} aviso(s), {nuevos} nuevos")
        return jobs

    def fetch(self) -> list[Job]:
        jobs = self._por_categoria() if self.categorias else self._por_terminos()

        # La ventana se aplica acá y no en la consulta porque la API no tiene
        # parámetro de antigüedad. Sale gratis: la fecha ya vino en el listado,
        # así que no hay que bajar ningún detalle para saberla.
        if self.max_age_days > 0:
            from vacantia.sources.google_posts import es_reciente

            quedan = [j for j in jobs if es_reciente(j.posted_at, self.max_age_days)]
            for j in jobs:
                if j not in quedan:
                    self.descartar(j.url, j.title, f"publicado hace más de "
                                   f"{self.max_age_days} días", j.company)
            if viejos := len(jobs) - len(quedan):
                logger.info(f"[{self.name}] {viejos} aviso(s) de más de "
                            f"{self.max_age_days} días, afuera")
            jobs = quedan

        logger.info(f"[{self.name}] {len(jobs)} aviso(s) en total")
        return jobs
