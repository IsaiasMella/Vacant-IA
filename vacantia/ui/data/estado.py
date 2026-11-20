"""El estado del sistema, para el pie de la barra lateral.

Vivía en `ui/data.py`; se separó sin cambiar nada (ver `ui/data/__init__.py`).
"""

from datetime import date, datetime

from vacantia.state import State

from vacantia.ui.data.configuracion import perfiles
from vacantia.ui.data.historial import contar_ofertas, filtros_del_perfil, marca_de_cambio


# --- el estado del sistema, para el pie de la barra lateral -----------------


def _hace_cuanto(momento: datetime) -> str:
    """"hoy 16:30", "ayer 23:59" o "el 3/9 a las 12:00".

    En lenguaje humano y relativo, como se lo diría una persona. Nada de
    "hace 2 min" ni de contadores que corran: es texto quieto que cambia
    cuando cambia el dato.
    """
    local = momento.astimezone()
    dias = (date.today() - local.date()).days
    hora = local.strftime("%H:%M")
    if dias <= 0:
        return f"hoy {hora}"
    if dias == 1:
        return f"ayer {hora}"
    return f"el {local.day}/{local.month} a las {hora}"


def _proxima_corrida(nombre_perfil: str) -> str:
    """El próximo horario de este perfil, como "hoy 23:59" o "mañana 12:00".

    Los horarios los reparte `agenda` para que dos personas de la misma casa no
    busquen al mismo tiempo, así que hay que preguntárselos a ella y no
    escribirlos acá.
    """
    from vacantia import agenda

    horarios = agenda.plan(perfiles()).get(nombre_perfil) or []
    if not horarios:
        return ""
    ahora = datetime.now().strftime("%H:%M")
    for hora in sorted(horarios):
        if hora > ahora:
            return f"hoy {hora}"
    return f"mañana {sorted(horarios)[0]}"


def estado_del_sistema(nombre_perfil: str) -> dict:
    """{ultima, proxima, ventana} para el pie de la barra lateral.

    Es la información que contesta "¿esto es todo lo que hay?", que es de donde
    sale la mayor parte de la ansiedad de buscar trabajo. Por eso tiene un lugar
    fijo en la pantalla y no un tooltip.
    """
    ultima = ""
    crudo = State(nombre_perfil).ultima_corrida
    if crudo:
        try:
            ultima = _hace_cuanto(datetime.fromisoformat(crudo))
        except ValueError:
            ultima = ""
    from vacantia.ui import corrida

    ventana = (filtros_del_perfil(nombre_perfil) or {}).get("max_age_days")
    return {"ultima": ultima,
            "proxima": _proxima_corrida(nombre_perfil),
            "ventana": ventana,
            # Para que el botón "Buscar ahora" del pie no deje arrancar dos
            # búsquedas encimadas: los límites del plan gratis son de la cuenta.
            "corriendo": corrida.esta_corriendo(),
            # En qué etapa va la búsqueda, para el cartel que se refresca solo.
            "paso": corrida.progreso(),
            # Cómo está el historial AHORA. La pantalla se lo guarda al abrir y
            # después compara contra esto para saber si entraron ofertas
            # mientras la persona miraba.
            "marca": marca_de_cambio(nombre_perfil),
            "pendientes": contar_ofertas(nombre_perfil).get("pendientes", 0)}
