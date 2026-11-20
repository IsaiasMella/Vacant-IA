"""Las ofertas del historial: listarlas, filtrarlas, marcarlas y archivarlas.

Lo que alimenta la pestaña Trabajos: qué ofertas se muestran y en qué orden,
cuáles ya sacó el filtro automático y por qué, el feedback de la persona
(apliqué, descarté y por qué), la auditoría del filtro, y el CV y los textos
del modelo para una oferta. Vivía en `ui/data.py`; se separó sin cambiar nada
(ver `ui/data/__init__.py`).
"""

import json
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone

from vacantia.config import cvs_con_texto, cvs_del_perfil, load_profile
from vacantia.fechas import dias_desde, fecha_de
from vacantia.filters import passes_language
from vacantia.models import Job
from vacantia.state import State

from vacantia.ui.data.configuracion import leer_perfil


# --- ofertas ----------------------------------------------------------------

#: Cuántas mostrar en la pestaña Trabajos. Con 3 corridas por día y ~25 ofertas
#: nuevas diarias, 300 son unas dos semanas de historial.
#: Cuántas ofertas por página. Con 267 en el historial, una sola página larga
#: no se puede recorrer: se scrollea sin llegar nunca al final.
POR_PAGINA = 20

#: Para ordenar: las que no tienen fecha van al fondo, no arriba de todo.
_SIN_FECHA = date.min

#: Hasta cuántos días una oferta cuenta como "recién publicada" y sube arriba de
#: todo, por encima del puntaje.
#:
#: **Por qué existe.** Ordenar sólo por puntaje contesta "cuál encaja mejor con
#: mi CV", que no es la misma pregunta que "a cuál me conviene postularme
#: ahora": una de 92 puntos de hace seis días ya tiene cien postulantes y una de
#: 88 de esta mañana no tiene ninguno. Entre esas dos, la segunda.
#:
#: **Por qué 2 y no 1.** El buscador tarda en indexar: un post de ayer puede
#: aparecer recién pasado mañana. Con un día, lo verdaderamente nuevo se
#: perdería la banda por la demora del índice y no por su fecha.
#:
#: Una oferta **sin fecha no entra acá**: no sabemos que sea nueva y ponerla
#: arriba sería inventarlo. Se ordena por puntaje como siempre.
DIAS_RECIEN = 2

def es_recien_publicada(oferta: dict, min_score: int, hoy: date | None = None) -> bool:
    """¿Va en la banda de arriba? Recién publicada **y** que valga la pena.

    Dos condiciones, y las dos hacen falta:

    1. **Que el aviso diga que es de hace poco.** Se exige que la fecha sea de
       publicación y no la de cuándo lo vimos: `found_at` es de hoy para todo lo
       que entró en la corrida de hoy, y usarlo metería en "recién publicadas"
       un aviso de hace tres meses que encontramos esta mañana.

    2. **Que llegue al puntaje que la persona pidió** (`min_score` del perfil,
       el mismo número que decide si le avisamos por Telegram). Ésta es la
       lección ya aprendida que subir lo reciente reintroducía: las que puntúan
       0 son las que directamente no son para uno, y si entraron hoy quedaban
       arriba de todo — tres avisos de Lima en 0 antes que 29 ofertas de 80 para
       arriba. Ser de hoy no vuelve buena a una oferta mala; la frescura sólo
       ordena entre las que ya sirven.
    """
    if (oferta.get("score") or 0) < min_score:
        return False
    momento, es_de_publicacion = fecha_de(oferta, hoy)
    if not es_de_publicacion:
        return False
    dias = dias_desde(momento, hoy)
    return dias is not None and dias <= DIAS_RECIEN


#: Antigüedad máxima en días de cada rango. None = sin límite.
#: Un aviso del mes pasado casi siempre está cubierto: se sigue pudiendo ver,
#: pero deja de ser lo primero que aparece.
RANGOS: dict[str, int | None] = {"hoy": 0, "7d": 7, "30d": 30, "todo": None}


def _entra_por_fecha(oferta: dict, desde: str, hoy=None) -> bool:
    tope = RANGOS.get(desde)
    if tope is None:
        return True
    momento, _ = fecha_de(oferta, hoy)
    dias = dias_desde(momento, hoy)
    # Sin fecha no se descarta: el aviso puede ser de hoy y no tenemos con qué
    # decir que no. Esconderlo sería peor que mostrarlo de más.
    return dias is None or dias <= tope


# --- por qué no apliqué -----------------------------------------------------
#
# Los motivos viven en `vacantia/motivos.py`, porque el scoring también los usa.
# Se reexportan acá con los mismos nombres: la pantalla y los tests los buscan
# en `data`.
from vacantia.motivos import (  # noqa: E402,F401
    _ETIQUETAS_MOTIVO,
    _MOTIVO_VIEJO,
    MOTIVOS,
    MOTIVOS_QUE_NO_ENSENIAN,
    clave_de_motivo,
)


#: Cómo se muestra un descarte sin motivo elegido ni escrito. El formulario ya
#: no deja guardarlo así, pero en el historial viejo los hay.
SIN_ESCRIBIR = "(no escribiste nada)"


def escritos_a_mano(descartadas) -> list[tuple[str, int]]:
    """Las frases de la barra "Escrito a mano", agrupadas y de más a menos.

    La barra sola decía cuántas y no qué eran. Isaías sospechaba que se estaban
    colando posteos de LinkedIn que no son ofertas, y eso no se podía confirmar
    sin leer lo que había escrito en cada descarte.

    Se agrupa ignorando mayúsculas, tildes, espacios de más y el punto final:
    "No es una oferta" y "no es una oferta." son la misma frase tipeada dos
    veces, y separadas ninguna parece repetirse. Más allá de eso no se
    interpreta nada: dos frases distintas que dicen lo mismo quedan en dos
    filas, porque adivinar sinónimos es la clase de cosa que termina contando mal.
    Cuando una idea se repite con varias redacciones, su lugar es el desplegable:
    así entraron "No es una oferta de trabajo" y los otros dos.

    Las que salieron del desplegable no van, aunque además tengan algo escrito:
    ya tienen su propia barra y acá se contarían dos veces. De cada frase se
    muestra la versión más reciente, y a igual cantidad va primero la última.
    """
    grupos: dict[str, list] = {}
    for h in sorted(descartadas, key=lambda h: h.get("fecha_feedback") or "",
                    reverse=True):
        if clave_de_motivo(h):
            continue
        texto = " ".join((h.get("motivo_descarte") or "").split())
        sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto.casefold())
                             if not unicodedata.combining(c))
        clave = sin_tildes.rstrip(" .,;:!?¡¿")
        if clave in grupos:
            grupos[clave][1] += 1
        else:
            grupos[clave] = [texto or SIN_ESCRIBIR, 1]
    return sorted(((t, n) for t, n in grupos.values()), key=lambda f: -f[1])


def partes_del_motivo(oferta: dict) -> tuple[str, str]:
    """(etiqueta, escrito a mano). Cualquiera de los dos puede venir vacío.

    Los dos caminos se pueden combinar: elegir "Piden inglés" y además escribir
    algo. Cuando pasa, se muestran los dos, pero cada uno en su propio elemento:
    la tarjeta no une datos con puntos medios.
    """
    escrito = (oferta.get("motivo_descarte") or "").strip()
    clave = clave_de_motivo(oferta)
    if not clave:
        return "", escrito
    # El guion que venías escribiendo para el caso especial no dice nada solo,
    # así que no se repite al lado de la etiqueta.
    etiqueta = "caso especial" if clave == "especial" else _ETIQUETAS_MOTIVO[clave]
    return etiqueta, (escrito if len(escrito) > 3 else "")


def texto_del_motivo(oferta: dict) -> str:
    """El motivo en una sola línea de texto plano, para donde no hay marcado."""
    etiqueta, escrito = partes_del_motivo(oferta)
    if etiqueta and escrito:
        return f"{etiqueta} · {escrito}"
    return etiqueta or escrito or "sin motivo"


# --- lo que el filtro ya había rechazado ------------------------------------


def motivos_del_sistema(oferta: dict, filtros: dict) -> list[tuple[str, str]]:
    """**Todos** los filtros que la sacan, no el primero. [(clave, explicación)]

    Devolvía sólo el primero, y eso hacía mentir a la pantalla de auditoría. Una
    oferta puede caer por idioma **y** por lugar a la vez: medido sobre el
    historial de Isaías el 11/9/2026, 28 de 204. En ésas se mostraba el lugar y
    se callaba el idioma, así que si el lugar estaba mal atribuido la respuesta
    honesta era "mal descartada" — y la oferta volvía a la lista aunque el
    idioma la sacara con todo derecho.

    **El idioma va primero porque es el motivo más firme.** Es el idioma en que
    está escrito el aviso, que se puede verificar leyéndolo, y además tiene una
    red de seguridad determinista que busca la exigencia en el texto. El lugar
    sale de lo que el modelo extrajo, y ahí hay deducciones: el caso que
    disparó esto fue un aviso sin ninguna ubicación al que el modelo le puso
    "Estados Unidos", que es la sede de la empresa. El prompt lo prohíbe
    explícitamente y el modelo lo hizo igual.

    **Se calcula al leer, no se guarda.** Es a propósito: el nivel de inglés y
    las ciudades se cambian desde *Mi perfil*, y una oferta rechazada hoy por
    pedir B2 tiene que volver a aparecer sola el día que subas tu nivel. Un
    campo guardado congelaría la decisión que se tomó con la configuración de
    aquel día.

    El motor ya aplica estos mismos filtros para decidir a qué avisarte; lo que
    guarda en el historial es **todo lo puntuado**, incluso lo rechazado. Eso
    estaba bien para poder contar lo que se pierde por idioma, pero llenaba la
    lista de "Sin marcar" con avisos sobre los que el sistema ya había decidido:
    medido el 8/9/2026, 31 de 41.
    """
    from vacantia.filters import (
        passes_offer, passes_place, passes_seniority, passes_tech, passes_titulo,
    )

    job = Job.from_dict(oferta)
    motivos = []
    # "No es una oferta" va primero: si no busca a nadie, el idioma o el lugar
    # del posteo no son el problema.
    ok, why = passes_offer(job)
    if not ok:
        motivos.append(("no_es_oferta", why))
    # El motor también lo aplica después de puntuar (ver `filters.passes_titulo`):
    # sin esto, lo que no llegó al Telegram por el título seguía en Sin marcar.
    ok, why = passes_titulo(job, filtros)
    if not ok:
        motivos.append(("titulo", why))
    ok, why = passes_language(job, filtros.get("language") or {})
    if not ok:
        motivos.append(("idioma", why))
    ok, why, _ = passes_place(job, filtros.get("location") or {},
                              filtros.get("work_modes"))
    if not ok:
        motivos.append(("lugar", why))
    ok, why = passes_tech(job, filtros)
    if not ok:
        motivos.append(("tecnologias", why))
    ok, why = passes_seniority(job, filtros)
    if not ok:
        motivos.append(("nivel", why))
    return motivos


def motivo_del_sistema(oferta: dict, filtros: dict) -> tuple[str, str]:
    """El motivo más firme de los que la sacan, o ("", "") si no la saca ninguno.

    Para quien sólo necesita saber si el filtro la sacó. La pantalla de
    auditoría usa `motivos_del_sistema`, que los devuelve todos.
    """
    motivos = motivos_del_sistema(oferta, filtros)
    return motivos[0] if motivos else ("", "")


def filtros_del_perfil(nombre_perfil: str) -> dict:
    """Los filtros del perfil, o {} si no hay perfil.

    Tolerante a propósito: el historial se puede leer sin que exista el archivo
    del perfil (pasa en los tests y pasaría con un perfil borrado a mano), y ahí
    la respuesta correcta es "no hay filtros", no reventar la pantalla.
    """
    try:
        return leer_perfil(nombre_perfil).get("filters") or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _lo_saco_el_sistema(oferta: dict, filtros: dict) -> bool:
    """¿El filtro automático la descartó, y todavía nadie lo revisó?

    Una marcada **mal descartada** deja de contar como sacada por el sistema:
    ése es el punto de marcarla, que vuelva a la fila para poder aplicar.
    """
    if oferta.get("revision_filtro") == "mal":
        return False
    return bool(motivo_del_sistema(oferta, filtros)[0])


def _sin_marcar(historial: list[dict], filtros: dict) -> list[dict]:
    """Las que de verdad esperan una decisión tuya.

    Quedan afuera las que el sistema ya descartó por idioma o por lugar: sobre
    ésas ya hay un veredicto y ponerlas en la fila es pedirte que hagas a mano
    el trabajo que el filtro hizo. Viven en **Filtradas**, se cuentan en
    Métricas, y vuelven solas si cambiás el filtro que las sacó.

    La excepción es la que revisaste y marcaste **mal descartada**: ésa vuelve
    acá aunque el filtro la siga sacando, porque el filtro se equivocó y la
    oferta sigue estando.
    """
    return [h for h in historial
            if h.get("aplicado") is None and not h.get("archivada")
            and not _lo_saco_el_sistema(h, filtros)]


#: De qué puntaje para arriba vale la pena revisar si el filtro acertó.
#:
#: Una de 20 mal descartada no cambia nada: aunque el filtro se haya equivocado,
#: esa oferta no te iba a servir igual. Las que importan son las que te habrían
#: llamado, y ahí abajo de 50 no hay ninguna. Revisar las 43 que puntúan menos
#: es gastar la atención en el tramo donde el error no tiene consecuencia.
PUNTAJE_PARA_REVISAR = 50

#: Cuántas hay que revisar para poder decir algo del filtro. Con 40 revisadas y
#: ningún error, el filtro acierta arriba del 90% y no hay nada que tocar; con
#: 4 o más errores hay un patrón que mirar. Menos que eso es anécdota.
META_REVISION = 40


def _vale_revisarla(oferta: dict) -> bool:
    """¿Puntúa lo suficiente como para que importe si el filtro se equivocó?"""
    score = oferta.get("score")
    return (score if score is not None else -1) >= PUNTAJE_PARA_REVISAR


def _saco_el_sistema_sin_revisar(historial: list[dict], filtros: dict) -> list[dict]:
    """Todo lo que sacó el filtro y nadie revisó, sin mirar el puntaje."""
    return [h for h in historial
            if h.get("aplicado") is None and not h.get("archivada")
            and not h.get("revision_filtro")
            and motivo_del_sistema(h, filtros)[0]]


def _filtradas(historial: list[dict], filtros: dict) -> list[dict]:
    """Las que descartó el sistema solo, todavía no revisaste, y vale revisar.

    Es la pestaña para auditar el filtro en la primera semana: se lee el aviso,
    se lo compara con el motivo que dio el sistema, y se contesta si acertó. Las
    ya revisadas salen de acá, para las dos respuestas: la lista se vacía a
    medida que se revisa y no hay que acordarse de dónde se quedó uno.

    Las que puntúan menos de `PUNTAJE_PARA_REVISAR` no entran: ver el porqué
    arriba de esa constante.
    """
    return [h for h in _saco_el_sistema_sin_revisar(historial, filtros)
            if _vale_revisarla(h)]


#: De qué puntaje para arriba se muestra una oferta en la pantalla.
#:
#: Pedido explícito: "menores a 50 no quiero ver nada". En el historial de
#: isaias eran 1044 de las 1179 sin marcar, y tapaban las 135 que sí servían.
#: No se borran del historial: siguen ahí para el dedupe (que no se vuelvan a
#: puntuar) y para los gráficos, sólo no se listan.
#:
#: **Apliqué es la excepción**: si mandaste el CV a una de 40, tenés que poder
#: encontrarla igual. Esa lista es para hacer seguimiento, no para elegir.
PUNTAJE_PARA_MOSTRAR = 50


def _se_muestra(oferta: dict) -> bool:
    """¿Puntúa lo suficiente como para aparecer en la pantalla?

    Sin puntaje se muestra: no se sabe si está debajo de 50, y esconderla sería
    perder una oferta por un dato que falta. Hoy no pasa (si el modelo falla
    puntúa la heurística), pero el corte es para las que puntúan bajo, no para
    las que no puntuaron.
    """
    score = oferta.get("score")
    return score is None or score >= PUNTAJE_PARA_MOSTRAR


def _por_estado(historial: list[dict], ver: str, filtros: dict) -> list[dict]:
    if ver == "aplicadas":
        return [h for h in historial if h.get("aplicado") is True]
    historial = [h for h in historial if _se_muestra(h)]
    if ver == "descartadas":
        return [h for h in historial if h.get("aplicado") is False]
    if ver == "archivadas":
        return [h for h in historial if h.get("archivada")]
    if ver == "filtradas":
        return _filtradas(historial, filtros)
    if ver == "pendientes":
        # Las archivadas salen de acá: es el punto de archivarlas.
        return _sin_marcar(historial, filtros)
    return historial


def ofertas(nombre_perfil: str, ver: str = "pendientes", desde: str = "todo",
            pagina: int = 1) -> tuple[list[dict], int, int]:
    """Una página de ofertas: (las de esta página, número de página, páginas).

    `ver`:   pendientes (sin marcar) | aplicadas | descartadas | todas.
    `desde`: hoy | 7d | 30d | todo, por antigüedad del aviso.

    En **Sin marcar** y **Todas** se ordena por puntaje, no por fecha. Ordenar por fecha ponía arriba las
    que acababan de entrar, y como el puntaje 0 lo sacan las que directamente no
    son para uno, la lista abría con lo peor: tres avisos de Lima puntuados 0
    antes que 29 ofertas de 80 para arriba. A igual puntaje manda la fecha del
    aviso, que ahí sí importa: entre dos que encajan igual, primero la más nueva.

    **Con una excepción arriba de todo**: las publicadas hace `DIAS_RECIEN` días
    o menos van primero, ordenadas entre ellas por puntaje. No es lo mismo "cuál
    encaja mejor" que "a cuál me conviene postularme ahora", y cuanto más
    reciente el aviso, menos gente se postuló. El puntaje que se muestra no se
    toca: significa qué tan bien encaja con el CV y mezclarle la fecha lo
    arruinaría. Lo único que cambia es el orden.
    """
    filtros = filtros_del_perfil(nombre_perfil)
    historial = _por_estado(State(nombre_perfil).load_history(), ver, filtros)
    historial = [h for h in historial if _entra_por_fecha(h, desde)]
    if ver in ("aplicadas", "archivadas"):
        # Estas dos pestañas no son para elegir, son para revisar: "¿a quién le
        # mandé el CV esta semana?", "¿qué archivé?". Lo último que hiciste
        # primero. Ordenarlas por puntaje dejaba lo de ayer mezclado con lo de
        # hace tres semanas.
        historial.sort(
            key=lambda h: h.get("fecha_archivada") or h.get("fecha_feedback") or "",
            reverse=True,
        )
    elif ver == "descartadas":
        # Descarté también es para revisar, pero la pregunta es otra: no es
        # "¿qué hice ayer?" sino **"¿me equivoqué al descartar algo bueno?"**, y
        # eso se contesta mirando primero las de más puntaje. Por fecha, una de
        # 90 quedaba quinta, abajo de dos de 0, y las que hay que auditar son
        # justamente las de arriba. A igual puntaje manda lo último que marcaste.
        historial.sort(
            key=lambda h: (h.get("score") if h.get("score") is not None else -1,
                           h.get("fecha_feedback") or ""),
            reverse=True,
        )
    elif ver == "filtradas":
        # Primero las de más puntaje: son las que más duele perder si el filtro
        # se equivocó, y son las que hay que mirar con más atención. Sin la
        # banda de recientes, que acá no ayuda: la pregunta no es "¿a cuál me
        # postulo?" sino "¿el filtro acertó?".
        #
        # El motivo que dio el sistema viaja pegado a cada oferta: es el dato
        # que hay que auditar, y calcularlo acá evita que la pantalla tenga que
        # volver a abrir el perfil por cada tarjeta.
        historial = [{**h, "_motivos_sistema": motivos_del_sistema(h, filtros)}
                     for h in historial]
        historial.sort(
            key=lambda h: (h.get("score") if h.get("score") is not None else -1,
                           h.get("found_at", "")),
            reverse=True,
        )
    else:
        # El puntaje que pidió la persona es el que decide qué entra a la banda
        # de recientes. Se lee una vez acá y viaja pegado a cada oferta en
        # `_recien`, para que la pantalla no tenga que volver a abrir el perfil
        # ni repetir la regla.
        try:
            min_score = int(leer_perfil(nombre_perfil).get("min_score", 60) or 0)
        except (FileNotFoundError, json.JSONDecodeError):
            min_score = 60
        historial = [{**h, "_recien": es_recien_publicada(h, min_score)}
                     for h in historial]
        historial.sort(
            key=lambda h: (
                h["_recien"],
                h.get("score") if h.get("score") is not None else -1,
                fecha_de(h)[0] or _SIN_FECHA,
                h.get("found_at", ""),
            ),
            reverse=True,
        )

    paginas = max(1, -(-len(historial) // POR_PAGINA))   # división para arriba
    pagina = min(max(1, pagina), paginas)
    arranca = (pagina - 1) * POR_PAGINA
    return (_con_cv_para_mandar(nombre_perfil, historial[arranca : arranca + POR_PAGINA]),
            pagina, paginas)


def _con_cv_para_mandar(nombre_perfil: str, ofertas: list[dict]) -> list[dict]:
    """Qué CV mandar a cada oferta de esta página. Viaja pegado en `_cv`.

    `_cv` es {id, nombre, estimado}. Así la tarjeta sólo tiene que dibujarlo:
    no necesita abrir el perfil ni saber cómo se llama cada CV, igual que con
    `_recien` y `_motivos_sistema`.

    Las que se puntuaron antes de que el perfil tuviera varios CV no traen
    recomendación del modelo. No se re-puntúan, que serían decenas de llamadas:
    se estima gratis por palabras con `consejo.cv_que_mejor_encaja`, y queda
    marcado como estimado para que la tarjeta lo diga. Lo mismo si recomendaba
    un CV que después se borró: dejarla sin nada sería tirar un dato que se
    puede calcular.

    **Sólo la página que se va a dibujar**, 20 como mucho, y **sólo con dos o
    más CV escritos**: con uno no hay nada que recomendar. No se guarda en el
    historial: se recalcula en cada carga, así si cambiás un CV la
    recomendación se acomoda sola.
    """
    try:
        perfil = leer_perfil(nombre_perfil)
    except (FileNotFoundError, json.JSONDecodeError):
        return ofertas
    if len(cvs_del_perfil(perfil)) < 2:
        return ofertas                  # ni siquiera se leen los archivos
    cvs = cvs_con_texto(perfil)
    if len(cvs) < 2:
        return ofertas

    from vacantia.consejo import cv_que_mejor_encaja

    por_id = {cv["id"]: cv for cv in cvs}
    salida = []
    for oferta in ofertas:
        elegido = oferta.get("cv_recomendado")
        estimado = elegido not in por_id
        if estimado:
            elegido = cv_que_mejor_encaja(Job.from_dict(oferta), cvs)
        salida.append({**oferta, "_cv": {"id": elegido,
                                         "nombre": por_id[elegido]["nombre"],
                                         "estimado": estimado}})
    return salida


def contar_ofertas(nombre_perfil: str, desde: str = "todo") -> dict[str, int]:
    """Cuántas hay de cada estado, dentro del rango de fechas elegido."""
    historial = [h for h in State(nombre_perfil).load_history()
                 if _entra_por_fecha(h, desde)]
    filtros = filtros_del_perfil(nombre_perfil)
    # El mismo criterio que usa la lista: si el número dijera 41 y la lista
    # mostrara 10, el número estaría mintiendo. Por eso el corte de puntaje va
    # en todos menos en Apliqué, igual que en `_por_estado`.
    visibles = [h for h in historial if _se_muestra(h)]
    return {
        "todas": len(visibles),
        "pendientes": len(_sin_marcar(visibles, filtros)),
        "aplicadas": sum(1 for h in historial if h.get("aplicado") is True),
        "descartadas": sum(1 for h in visibles if h.get("aplicado") is False),
        "filtradas": len(_filtradas(visibles, filtros)),
        "archivadas": sum(1 for h in visibles if h.get("archivada")),
    }


def resumen_revision(nombre_perfil: str) -> dict[str, int]:
    """El marcador de la auditoría del filtro.

    {bien, mal, sin_revisar, meta, faltan, bajo_puntaje}.

    **Es acumulativo y no se resetea con el rango de fechas.** La pregunta que
    contesta es "en toda la semana, ¿cuántas veces acertó el filtro?", y con
    dos días de muestra un porcentaje sobre lo de hoy no dice nada. Por eso se
    cuenta contra el historial entero, no contra la página que se está viendo.
    """
    historial = State(nombre_perfil).load_history()
    filtros = filtros_del_perfil(nombre_perfil)
    revisiones = Counter(h.get("revision_filtro") for h in historial)
    bien = revisiones.get("bien", 0)
    mal = revisiones.get("mal", 0)
    # "Bien sacada, pero el motivo estaba mal". Cuenta como acierto del filtro
    # —la oferta no tenía que llegarte— y como error de la explicación, que es
    # otra cosa y se arregla en otro lado.
    motivo_errado = revisiones.get("motivo", 0)
    sin_revisar = _saco_el_sistema_sin_revisar(historial, filtros)
    return {
        "bien": bien + motivo_errado,
        "mal": mal,
        "motivo_errado": motivo_errado,
        "sin_revisar": sum(1 for h in sin_revisar if _vale_revisarla(h)),
        # Las que el filtro sacó y no se revisan porque puntúan poco. Se cuentan
        # aparte para poder decir por qué la lista está vacía en vez de dejar
        # pensando que se terminaron las ofertas.
        "bajo_puntaje": sum(1 for h in sin_revisar if not _vale_revisarla(h)),
        "meta": META_REVISION,
        "faltan": max(0, META_REVISION - (bien + motivo_errado + mal)),
    }


def revisar_filtro(nombre_perfil: str, url: str, revision: str) -> int:
    """Anota si el filtro acertó con esa oferta. Ver `State.revisar_filtro`."""
    return State(nombre_perfil).revisar_filtro([url], revision)


def contar_por_fecha(nombre_perfil: str, ver: str = "pendientes") -> dict[str, int]:
    """Cuántas hay en cada rango, dentro del estado elegido.

    Los dos contadores se cruzan a propósito: el número de cada botón dice qué
    va a pasar si se lo aprieta, no cuántas hay en total.
    """
    filtros = filtros_del_perfil(nombre_perfil)
    historial = _por_estado(State(nombre_perfil).load_history(), ver, filtros)
    return {rango: sum(1 for h in historial if _entra_por_fecha(h, rango))
            for rango in RANGOS}


def guardar_feedback(nombre_perfil: str, url: str, aplicado: bool, motivo: str,
                     motivo_clave: str = "") -> bool:
    return State(nombre_perfil).record_feedback(
        url, aplicado=aplicado, motivo_descarte=motivo, motivo_clave=motivo_clave,
        fecha_feedback=datetime.now(timezone.utc).isoformat(),
    )


def buscar_oferta(nombre_perfil: str, url: str) -> dict | None:
    """La oferta del historial con esa URL, o None."""
    from vacantia.models import clave_de_url

    clave = clave_de_url(url)
    for entrada in State(nombre_perfil).load_history():
        if clave_de_url(entrada.get("url", "")) == clave:
            return entrada
    return None


def como_job(oferta: dict) -> Job:
    return Job.from_dict(oferta)


def cv_para_oferta(nombre_perfil: str, oferta: dict, perfil: dict | None = None) -> dict:
    """El CV con el que conviene postularse a esta oferta.

    {id, nombre, path, palabras_clave, texto, estimado}. El que recomendó el
    modelo si sigue existiendo y tiene texto; si no, el estimado por palabras;
    con un solo CV, ése. Es lo que usan Consejo y Mensajes: aconsejar sobre el
    CV de AI para una oferta de Full Stack sería aconsejar sobre el equivocado.

    `perfil` se pasa cuando quien llama ya lo tiene cargado, para no leerlo dos
    veces; puede venir con los secretos resueltos o no, los CV son iguales.
    """
    cvs = cvs_con_texto(perfil if perfil is not None else leer_perfil(nombre_perfil))
    if len(cvs) == 1:
        return {**cvs[0], "estimado": False}
    por_id = {cv["id"]: cv for cv in cvs}
    elegido = str(oferta.get("cv_recomendado") or "")
    if elegido in por_id:
        return {**por_id[elegido], "estimado": False}

    from vacantia.consejo import cv_que_mejor_encaja

    estimado = cv_que_mejor_encaja(Job.from_dict(oferta), cvs)
    return {**por_id[estimado], "estimado": True}


def mensajes_con_llm(nombre_perfil: str, job: Job) -> tuple[dict[str, str], bool]:
    """Los dos mensajes escritos por el modelo. (textos, los escribió el modelo).

    Usa `load_profile` y no `leer_perfil` porque acá sí hacen falta los secretos
    resueltos: es el único lugar de la UI que llama a una API.
    """
    from vacantia import mensajes as mensajes_mod

    perfil = load_profile(nombre_perfil)
    cv = cv_para_oferta(nombre_perfil, job.to_dict(), perfil)["texto"]
    textos, escritos = {}, []
    for tipo in mensajes_mod.TIPOS:
        texto, ok = mensajes_mod.generar(job, cv, perfil, tipo)
        textos[tipo] = texto
        escritos.append(ok)
    return textos, all(escritos)


def consejo_con_llm(nombre_perfil: str, job: Job) -> tuple[str, bool]:
    """El consejo escrito por el modelo. Necesita los secretos resueltos, así
    que va por `load_profile` y no por `leer_perfil`."""
    from vacantia import consejo as consejo_mod

    perfil = load_profile(nombre_perfil)
    cv = cv_para_oferta(nombre_perfil, job.to_dict(), perfil)["texto"]
    return consejo_mod.consejo_con_llm(job, cv, perfil)


def marca_de_cambio(nombre_perfil: str) -> str:
    """Un valor que cambia cuando entran ofertas nuevas, y sólo entonces.

    Es la fecha de modificación del historial más su tamaño. Alcanza para que la
    pantalla se entere de que hubo una corrida sin leer el archivo entero cada
    veinte segundos: el historial son 207 ofertas y crece.
    """
    archivo = State(nombre_perfil).history_file
    try:
        st = archivo.stat()
    except OSError:
        return ""
    return f"{st.st_mtime_ns}-{st.st_size}"


def archivar(nombre_perfil: str, urls: list[str], archivada: bool = True) -> int:
    return State(nombre_perfil).archivar(urls, archivada)


def viejas_sin_marcar(nombre_perfil: str, dias: int) -> list[str]:
    """Las URLs sin marcar cuyo aviso tiene más de `dias`, para archivar de una.

    Las que no dicen cuándo se publicaron quedan afuera: no se sabe si están
    viejas, y archivar por las dudas es tirar una oferta que puede ser de ayer.
    """
    filtros = filtros_del_perfil(nombre_perfil)
    historial = _por_estado(State(nombre_perfil).load_history(), "pendientes", filtros)
    salida = []
    for h in historial:
        antiguedad = dias_desde(fecha_de(h)[0])
        if antiguedad is not None and antiguedad > dias:
            salida.append(h.get("url", ""))
    return [u for u in salida if u]
