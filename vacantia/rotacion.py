"""Qué términos le tocan a cada fuente en esta corrida.

Las fuentes tienen más términos que búsquedas por corrida (LinkedIn: 16
términos y 3 búsquedas), así que en cada corrida buscan una tanda y la próxima
sigue desde donde quedó.

**Antes la tanda salía de la fecha** (`date.today().toordinal()`), y eso tenía
un agujero que no se veía: el perfil corre tres veces por día (12:00, 16:30 y
23:59, ver `agenda`), y las tres corridas del mismo día hacían exactamente las
mismas búsquedas. Se vio en el embudo del 18/11/2026: dos corridas seguidas de
LinkedIn trajeron unas 50 ofertas cada una, y 31 ya estaban vistas. Con 16
términos se tardaba unos 5 días en dar la vuelta; rotando por corrida, menos
de 2.

Ahora la posición se guarda en `state/<perfil>/rotacion.json`, una por fuente:

    {"linkedin": 6, "google_posts": 8, "getonbrd": 3}

**Leer no avanza.** Las fuentes preguntan por su tanda las veces que quieran
(`is_available` y `fetch` arman la lista cada una), y la posición recién se
mueve cuando el motor guarda el estado al final de una corrida de verdad. Así un
`--dry-run` no se come la tanda de nadie, y una corrida que se cae a la mitad
vuelve a buscar lo mismo la próxima vez.
"""

import json

from vacantia import state as _state
from vacantia.log import get_logger

logger = get_logger()

ARCHIVO = "rotacion.json"


def _ruta(nombre_perfil: str, root=None):
    # `_state.STATE_ROOT` se lee acá y no al importar: los tests lo cambian.
    return (root or _state.STATE_ROOT) / nombre_perfil / ARCHIVO


def _leer(nombre_perfil: str, root=None) -> dict:
    """Las posiciones guardadas. {} si no hay archivo o está roto."""
    if not nombre_perfil:
        return {}
    ruta = _ruta(nombre_perfil, root)
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning(f"{ruta} corrupto — la rotación arranca de cero")
        return {}
    return datos if isinstance(datos, dict) else {}


def elegir(profile: dict, fuente: str, items: list, cuantos: int) -> tuple[list, int | None]:
    """(la tanda de esta corrida, desde dónde sigue la próxima).

    Sin tope, o con un tope que alcanza para todos, devuelve todos y `None`:
    no hay nada que rotar ni que guardar.

    La posición guardada se toma módulo la cantidad de términos de hoy, así que
    agregar o sacar términos en el perfil no rompe nada: la rotación sigue desde
    un lugar válido.
    """
    items = list(items)
    if not items or cuantos <= 0 or cuantos >= len(items):
        return items, None
    try:
        desde = int(_leer(profile.get("name", "")).get(fuente, 0))
    except (TypeError, ValueError):
        desde = 0
    desde %= len(items)
    tanda = [items[(desde + i) % len(items)] for i in range(cuantos)]
    return tanda, (desde + cuantos) % len(items)


def guardar(nombre_perfil: str, avances: dict[str, int], root=None) -> None:
    """Anota desde dónde sigue cada fuente. Lo llama el motor, nunca una fuente."""
    if not nombre_perfil or not avances:
        return
    from vacantia.ui.data import _escribir_atomico

    datos = _leer(nombre_perfil, root)
    datos.update(avances)
    ruta = _ruta(nombre_perfil, root)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(ruta, json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    logger.debug(f"Rotación guardada: {datos}")
