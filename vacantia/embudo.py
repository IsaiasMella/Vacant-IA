"""El embudo de cada corrida: cuántas ofertas trajo cada fuente y dónde se cayeron.

**Por qué existe.** Hasta el 16/10/2026 la única forma de saber qué rendía cada
fuente era leer `vacantia.log`, de 13 MB y con los perfiles mezclados. Lo que se
descartaba antes del modelo quedaba ahí sin decir de qué fuente venía, y qué
oferta se había avisado no estaba guardado en ningún lado. Al medirlo a mano
apareció que el filtro de títulos tiraba justo los "Senior Backend Python" que
la persona buscaba, sin que nada lo mostrara.

Se prende por perfil con `"registro_embudo": true`. Escribe dos archivos en
`state/<perfil>/`:

* `embudo.jsonl`: una línea por corrida, con el conteo por fuente y por etapa.
* `descartadas.jsonl`: una línea por oferta descartada, con URL, título,
  fuente, etapa y motivo. **La misma oferta con el mismo motivo se anota una
  sola vez**: lo que se descarta antes del modelo no se marca como visto y
  vuelve en cada corrida (medido: 1.846 descartes en el log eran 225 ofertas).

Las etapas cierran como sumas, y por eso se cuentan todas aunque algunas no se
anoten como descarte:

    trajo        = ya_vista + duplicada + cubierta + antes_del_llm + diferida + puntuada
    puntuada     = (filtros: no_es_oferta, titulo … idioma) + bajo_umbral + supera_umbral
    supera_umbral = avisada + fuera_del_top + sin_avisar

`descartada_en_fuente` va aparte de `trajo`: es lo que la fuente encontró y
tiró ella misma (avisos viejos, posteos que no son ofertas) antes de devolverlo.
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from vacantia.log import get_logger
from vacantia.models import Job, clave_de_url

logger = get_logger()

#: El orden en que se recorren las etapas. Es el orden del motor, y el que se
#: usa para escribir el conteo, así el archivo se lee de arriba abajo.
ETAPAS = (
    "descartada_en_fuente",
    "trajo",
    "ya_vista",
    "duplicada",
    "cubierta",
    "antes_del_llm",
    "diferida",
    "puntuada",
    "no_es_oferta",
    "titulo",
    "tecnologias",
    "nivel",
    "ubicacion",
    "modalidad",
    "idioma",
    "bajo_umbral",
    "supera_umbral",
    "fuera_del_top",
    "sin_avisar",
    "avisada",
)

#: La etiqueta que usa `FilterStats` y la etapa del embudo. Allá están en
#: inglés por historia; acá van como las lee la persona.
ETAPA_DEL_FILTRO = {
    "no_es_oferta": "no_es_oferta",
    "titulo": "titulo",
    "tecnologias": "tecnologias",
    "nivel": "nivel",
    "location": "ubicacion",
    "work_mode": "modalidad",
    "language": "idioma",
}

ARCHIVO_EMBUDO = "embudo.jsonl"
ARCHIVO_DESCARTADAS = "descartadas.jsonl"


def esta_prendido(profile: dict) -> bool:
    return bool(profile.get("registro_embudo", False))


def _clave_url(url: str) -> str:
    """La misma clave que `Job.key`, que conserva el id de Indeed (`?jk=`).

    Hasta que `Job.key` lo conservó, acá se usaba la URL entera: cortando en
    el `?`, los 23 avisos sin detalle de Indeed de una corrida quedaban
    anotados como uno solo.
    """
    return clave_de_url(url)


class Embudo:
    def __init__(self, perfil: str, dry_run: bool = False):
        self.perfil = perfil
        self.dry_run = dry_run
        self.corrida = datetime.now(timezone.utc).isoformat()
        self.conteo: dict[str, Counter] = defaultdict(Counter)
        self.descartes: list[dict] = []
        self.fallas: list[str] = []

    # --- contar ---------------------------------------------------------

    def contar(self, fuente: str, etapa: str, n: int = 1) -> None:
        if n:
            self.conteo[fuente or "?"][etapa] += n

    def contar_jobs(self, etapa: str, jobs: list[Job]) -> None:
        for job in jobs:
            self.contar(job.source, etapa)

    def descartar(self, fuente: str, etapa: str, motivo: str, url: str,
                  titulo: str = "", empresa: str = "", puntaje: int | None = None) -> None:
        """Cuenta la etapa y anota la oferta con su motivo."""
        self.contar(fuente, etapa)
        self.descartes.append({
            "fecha": datetime.now(timezone.utc).isoformat(),
            "corrida": self.corrida,
            "fuente": fuente or "?",
            "etapa": etapa,
            "motivo": motivo,
            "url": url,
            "titulo": " ".join(str(titulo or "").split())[:140],
            "empresa": empresa or "",
            "puntaje": puntaje,
        })

    def descartar_job(self, etapa: str, job: Job, motivo: str) -> None:
        self.descartar(job.source, etapa, motivo, job.url, job.display_title,
                       job.company, job.score)

    # --- guardar --------------------------------------------------------

    def resumen(self) -> dict:
        fuentes = {
            fuente: {e: c[e] for e in ETAPAS if c[e]}
            for fuente, c in sorted(self.conteo.items())
        }
        totales = Counter()
        for c in self.conteo.values():
            totales.update(c)
        return {
            "corrida": self.corrida,
            "perfil": self.perfil,
            "dry_run": self.dry_run,
            "fuentes": fuentes,
            "totales": {e: totales[e] for e in ETAPAS if totales[e]},
            "fallas": self.fallas,
        }

    def guardar(self, carpeta: Path, segundos: float = 0.0) -> int:
        """Agrega la corrida y los descartes nuevos. Devuelve cuántos anotó.

        Nunca levanta: un disco lleno no puede tumbar una corrida que ya
        avisó por Telegram.
        """
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            linea = {**self.resumen(), "segundos": round(segundos, 1)}
            with (carpeta / ARCHIVO_EMBUDO).open("a", encoding="utf-8") as f:
                f.write(json.dumps(linea, ensure_ascii=False) + "\n")

            ruta = carpeta / ARCHIVO_DESCARTADAS
            ya = _claves_anotadas(ruta)
            nuevos = []
            for d in self.descartes:
                clave = (_clave_url(d["url"]), d["motivo"])
                if clave in ya:
                    continue
                ya.add(clave)
                nuevos.append(d)
            if nuevos:
                with ruta.open("a", encoding="utf-8") as f:
                    for d in nuevos:
                        f.write(json.dumps(d, ensure_ascii=False) + "\n")
            logger.info(f"Embudo guardado en {carpeta / ARCHIVO_EMBUDO} "
                        f"(+{len(nuevos)} descartada(s) nuevas en {ARCHIVO_DESCARTADAS})")
            return len(nuevos)
        except OSError as e:
            logger.warning(f"No pude guardar el embudo: {e}")
            return 0


def _claves_anotadas(ruta: Path) -> set[tuple[str, str]]:
    """(url, motivo) de lo que ya está en el archivo. Una línea rota se saltea."""
    if not ruta.exists():
        return set()
    claves = set()
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(linea)
        except json.JSONDecodeError:
            continue
        claves.add((_clave_url(d.get("url", "")), d.get("motivo", "")))
    return claves


def leer_embudo(carpeta: Path) -> list[dict]:
    """Las corridas anotadas, de la más vieja a la más nueva."""
    ruta = carpeta / ARCHIVO_EMBUDO
    if not ruta.exists():
        return []
    salida = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            salida.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    return salida
