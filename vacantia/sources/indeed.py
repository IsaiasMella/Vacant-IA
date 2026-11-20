"""Fuente: Indeed Argentina, por la API de la app de Indeed (vía JobSpy).

**Por qué cambió (19/11/2026).** Hasta acá Indeed se leía como un portal más:
TinyFish bajaba la página de resultados y después la de cada aviso. Cloudflare
deja pasar el listado pero no el aviso, y la tasa de avisos legibles se fue
cayendo: 38-50% el 9/9, y en noviembre corridas de **2 avisos de 25**. En la
semana del 12 al 19/11 la fuente trajo 48 avisos y llegaron 3 al modelo; en
`descartadas.jsonl` quedaron 161 avisos distintos con "Indeed no dejó leer el
aviso". Encima cada corrida gastaba búsquedas de TinyFish.

**Lo que se usa ahora.** JobSpy, el mismo paquete de la fuente `linkedin`,
también lee Indeed, pero no por la página web: le pega a la API GraphQL que usa
la app (`apis.indeed.com/graphql`), que no pasa por Cloudflare. Probado contra
el sitio real el 19/11/2026, "Python", Argentina, últimos 7 días:

    30 de 30 avisos completos en 0,8 s: título, empresa, ubicación, fecha de
    publicación, si es remoto y la descripción entera en Markdown.

Y de paso se caen las tres limitaciones de antes:

* **La fecha viene.** Antes Indeed no la decía en ningún lado y la ventana
  dependía de `fromage`. Ahora la ventana se la pide igual al portal
  (`hours_old`) y además se vuelve a chequear acá con la fecha del aviso.
* **No hay techo de 16 avisos por búsqueda.** La segunda página de la web pedía
  cuenta; la API pagina con cursor y devuelve hasta 100 por pedido.
* **No gasta TinyFish.** No necesita ninguna credencial.

**La URL es la misma de siempre**, `https://ar.indeed.com/viewjob?jk=<id>`: lo
que ya está en `seen_jobs.json` y en el historial se sigue reconociendo como
visto y no vuelve a entrar.

**Lo que JobSpy no deja combinar en Indeed:** la ventana de días y "sólo
remoto" van por el mismo campo de filtros, y si está la ventana el remoto se
ignora. Se pide la ventana, que es la que importa para no traer avisos viejos;
la modalidad la filtra `filters.py` después, como en todas las fuentes.

**Topes.** Sigue rotando los términos por corrida con `max_queries` (ver
`rotacion`). Es una API sin login y que no se bloquee depende de no abusar,
igual que LinkedIn: el tope no se sube sin medir.
"""

import re
import time
import unicodedata
from datetime import date, datetime, timedelta

from vacantia import rotacion
from vacantia.config import terminos_de_busqueda
from vacantia.log import get_logger
from vacantia.models import Job
from vacantia.sources.base import Source
from vacantia.sources.linkedin_jobs import _sin_stderr, _val

logger = get_logger()

#: El país, como lo nombra JobSpy (`Country` en `jobspy/model.py`). Decide el
#: dominio (`ar.indeed.com`) y el encabezado `indeed-co` de la API.
PAIS_POR_DEFECTO = "argentina"

#: Cuántos avisos pedir por búsqueda. La API devuelve hasta 100 por pedido, así
#: que hasta 100 sigue siendo una sola request: subirlo no multiplica pedidos,
#: sólo trae más de la misma búsqueda.
RESULTADOS_POR_DEFECTO = 50

#: Pausa entre búsquedas, como en LinkedIn: sin login, que no se bloquee
#: depende de no pedir todo de golpe.
PAUSA_POR_DEFECTO = 2.0

#: El id del aviso dentro de cualquiera de sus URLs.
_JK = re.compile(r"[?&]v?jk=([0-9a-f]{8,20})", re.IGNORECASE)

#: Cómo dice Indeed "remoto" en el lugar de la ciudad. Visto el 19/11/2026: la
#: API marca `is_remote` en unos y en otros no, pero la ubicación dice igual
#: "Desde casa, AR" (DonWeb, "Cloud SysAdmin", venía con `is_remote` en falso).
_REMOTO = {"desde casa", "remoto", "remote", "teletrabajo", "home office"}


def _canonica(url: str) -> str:
    """`...?jk=ABC&from=serp` -> `https://ar.indeed.com/viewjob?jk=abc`.

    Es la identidad del aviso. JobSpy ya la devuelve así, pero se normaliza
    igual: es la clave contra la que se compara todo el historial de Indeed, y
    un parámetro de tracking colado haría que el mismo aviso entre dos veces.
    """
    m = _JK.search(url or "")
    if not m:
        return ""
    dominio = re.match(r"https?://([^/?#]+)", url or "")
    host = dominio.group(1).lower() if dominio else "ar.indeed.com"
    return f"https://{host}/viewjob?jk={m.group(1).lower()}"


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn").strip()


def ubicacion(texto: str, pais: str) -> tuple[str, str, str, bool]:
    """'Buenos Aires, B, AR' -> ('Argentina', 'Buenos Aires', 'B', False).

    Devuelve (país, ciudad, provincia, remoto). Así la arma JobSpy: ciudad,
    código de provincia y código de país, cualquiera de los tres puede faltar.
    Formas vistas el 19/11/2026:

        "Buenos Aires, B, AR"   ciudad, provincia, país
        "B, AR"                 sólo provincia: no hay ciudad
        "Desde casa, AR"        remoto
        "Córdoba, X, AR"

    El código de país de dos letras se cambia por el nombre (`pais`), que es lo
    que compara el filtro de ubicación. Un segmento de una o dos letras en el
    medio es la provincia, no una ciudad: tomarlo como ciudad haría que el
    filtro de ciudad compare "Bahía Blanca" contra "B".
    """
    partes = [p.strip() for p in (texto or "").split(",") if p.strip()]
    pais_ok = ""
    if partes and len(partes[-1]) == 2 and partes[-1].isalpha() and partes[-1].isupper():
        pais_ok = pais
        partes = partes[:-1]

    remoto = bool(partes) and _sin_tildes(partes[0]) in _REMOTO
    if remoto:
        partes = partes[1:]

    ciudad = provincia = ""
    if len(partes) >= 2:
        ciudad, provincia = partes[0], ", ".join(partes[1:])
    elif len(partes) == 1:
        if len(partes[0]) <= 2:
            provincia = partes[0]
        else:
            ciudad = partes[0]
    return pais_ok, ciudad, provincia, remoto


class IndeedSource(Source):
    name = "indeed"

    def __init__(self, config: dict, profile: dict):
        super().__init__(config, profile)
        self.pais = str(config.get("country") or PAIS_POR_DEFECTO).strip().lower()
        #: "" = todo el país. Con una ciudad, la API busca en un radio alrededor.
        self.location = str(config.get("location") or "").strip()
        self.results_wanted = int(config.get("results_wanted") or RESULTADOS_POR_DEFECTO)
        self.max_queries = int(config.get("max_queries", 4) or 4)
        self.delay = float(config.get("delay_between_searches", PAUSA_POR_DEFECTO))
        self.proxies = config.get("proxies") or None

    # --- qué buscar -----------------------------------------------------

    def terminos(self) -> list[str]:
        """Los términos de esta corrida, rotados como en las otras fuentes."""
        crudos = terminos_de_busqueda(self.profile, self.config.get("search_terms"))
        terminos = [str(t).strip() for t in crudos if str(t).strip()]
        tanda, self.siguiente_en_rotacion = rotacion.elegir(
            self.profile, self.name, terminos, self.max_queries)
        return tanda

    def is_available(self) -> tuple[bool, str]:
        try:
            import jobspy  # noqa: F401
        except ImportError:
            return False, "falta el paquete 'python-jobspy' (ver README: necesita --no-deps)"
        if not self.terminos():
            return False, "el perfil no tiene keywords ni search_terms"
        return True, ""

    # --- red ------------------------------------------------------------

    def _scrape(self, termino: str):
        """Una búsqueda. Es el único punto que sale a la red."""
        from jobspy import scrape_jobs

        kwargs = {
            "site_name": ["indeed"],
            "search_term": termino,
            "country_indeed": self.pais,
            "results_wanted": self.results_wanted,
            "description_format": "markdown",
            "verbose": 0,
        }
        if self.location:
            kwargs["location"] = self.location
        if self.max_age_days > 0:
            kwargs["hours_old"] = self.max_age_days * 24
        if self.proxies:
            kwargs["proxies"] = self.proxies
        with _sin_stderr("indeed"):
            return scrape_jobs(**kwargs)

    # --- armado ---------------------------------------------------------

    def _a_job(self, fila, termino: str) -> Job | None:
        url = _canonica(_val(fila, "job_url"))
        titulo = _val(fila, "title")
        if not url or not titulo:
            return None

        lugar = _val(fila, "location")
        pais, ciudad, provincia, remoto = ubicacion(lugar, self.pais.title())
        # Como en LinkedIn: que Indeed no lo marque como remoto NO quiere decir
        # que sea presencial, así que en ese caso queda vacío y no filtra.
        marcado = _val(fila, "is_remote").lower() in ("true", "1", "yes")
        modo = "remote" if (remoto or marcado) else ""

        descripcion = _val(fila, "description")
        return Job(
            url=url,
            title=titulo,
            company=_val(fila, "company"),
            source=self.name,
            location=lugar,
            description=descripcion[:3000],
            descripcion_completa=descripcion,
            posted_at=_val(fila, "date_posted")[:10],
            country=pais,
            city=ciudad,
            region=provincia,
            work_mode=modo,
            raw={"portal": "Indeed", "busqueda": termino,
                 "job_url_direct": _val(fila, "job_url_direct")},
        )

    def _es_reciente(self, job: Job) -> bool:
        """La API ya aplica la ventana; esto es la red de seguridad.

        Sin fecha entra: no hay con qué decir que es viejo.
        """
        if self.max_age_days <= 0 or not job.posted_at:
            return True
        try:
            publicado = datetime.fromisoformat(job.posted_at).date()
        except ValueError:
            return True
        return publicado >= date.today() - timedelta(days=self.max_age_days)

    # --- interfaz Source ------------------------------------------------

    def fetch(self) -> list[Job]:
        terminos = self.terminos()
        logger.info(f"[{self.name}] {len(terminos)} búsqueda(s) en Indeed "
                    f"({self.pais}, últimos {self.max_age_days or '∞'} días, "
                    f"hasta {self.results_wanted} por búsqueda)")

        jobs: list[Job] = []
        vistos: set[str] = set()
        for i, termino in enumerate(terminos):
            if i:
                time.sleep(self.delay)
            try:
                tabla = self._scrape(termino)
            except Exception as e:
                # Un cambio en la API o un corte: se pierde esta búsqueda, no la
                # corrida.
                logger.error(f"[{self.name}]   falló '{termino}': {e}")
                continue

            nuevos = 0
            for _, fila in tabla.iterrows():
                job = self._a_job(fila, termino)
                if job is None or job.url in vistos:
                    continue
                vistos.add(job.url)
                if not self._es_reciente(job):
                    self.descartar(job.url, job.title, f"publicado hace más de "
                                   f"{self.max_age_days} días", job.company)
                    continue
                jobs.append(job)
                nuevos += 1
            logger.info(f"[{self.name}]   '{termino}': {len(tabla)} aviso(s), {nuevos} nuevos")

        logger.info(f"[{self.name}] {len(jobs)} aviso(s) en total")
        return jobs
