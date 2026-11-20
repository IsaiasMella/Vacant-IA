"""Los números de Estadísticas y de los gráficos.

Cuántas apliqué y cuándo, por qué descarté, cuántas entran por día, qué
habilidades piden los avisos, cómo se reparten los puntajes, y lo que se pierde
por no saber inglés. Todo se calcula al leer, sobre el historial. Vivía en
`ui/data.py`; se separó sin cambiar nada (ver `ui/data/__init__.py`). Después,
el 20/11/2026, los períodos de Apliqué y Descarté pasaron a semanas de lunes a
domingo (ver `ui/semanas.py`).
"""

import json
import re
from collections import Counter
from datetime import date, datetime, timedelta

from vacantia.filters import passes_language
from vacantia.models import Job
from vacantia.motivos import MOTIVOS, clave_de_motivo
from vacantia.state import State

from vacantia.ui import semanas
from vacantia.ui.data.configuracion import leer_perfil
from vacantia.ui.data.historial import (_entra_por_fecha, _sin_marcar, escritos_a_mano,
                                        filtros_del_perfil, motivos_del_sistema)


def pena_de_ingles(nombre_perfil: str, desde: str = "todo") -> dict:
    """Qué se perdió por no saber inglés: cuántas y cuánto puntuaba la mejor.

    Existe por pedido explícito, y el pedido incluía que incomode: ver sólo las
    ofertas en español da la impresión de que el mercado es así, cuando lo que
    se ve es el recorte que deja el filtro. El número adelante lo desarma.

    Se recalcula sobre el historial en vez de guardarse: el nivel de inglés del
    perfil se puede cambiar desde la pantalla, y el cartel tiene que responder a
    lo que dice el perfil hoy, no a lo que decía cuando corrió la búsqueda.
    """
    cfg = filtros_del_perfil(nombre_perfil).get("language") or {}
    historial = [h for h in State(nombre_perfil).load_history()
                 if _entra_por_fecha(h, desde)]

    # Dos fuentes, y la segunda la pediste vos: lo que el filtro detecta solo,
    # más lo que marcaste a mano como "piden inglés". El LLM no siempre pone
    # `requires_english` —de tus 46 descartes por idioma, varios no lo tenían—
    # así que sin esto el número se quedaba corto justo donde vos ya sabías la
    # respuesta. Marcar una como "piden inglés" ahora hace subir el número.
    perdidas = [h for h in historial
                if not passes_language(Job.from_dict(h), cfg)[0]
                or clave_de_motivo(h) == "ingles"]
    if not perdidas:
        return {"cuantas": 0, "mejor": None, "mejor_titulo": ""}

    mejor = max(perdidas, key=lambda h: h.get("score") or 0)
    return {
        "cuantas": len(perdidas),
        "mejor": mejor.get("score"),
        "mejor_titulo": mejor.get("scored_title") or mejor.get("title") or "",
    }


def estadisticas(nombre_perfil: str, desde: str = "todo") -> dict:
    """Los números de la pestaña Estadísticas.

    Existe porque los contadores estaban repartidos en los botones de arriba, y
    ahí compiten con el único número que importa mientras uno trabaja: cuántas
    quedan por mirar. Los botones se quedan con ése; el resto vive acá.
    """
    historial = [h for h in State(nombre_perfil).load_history()
                 if _entra_por_fecha(h, desde)]
    filtros = filtros_del_perfil(nombre_perfil)

    # Se cuenta por CADA filtro que la saca, no por el primero: una oferta que
    # cae por idioma y por lugar aparece en las dos filas. Por eso las filas
    # suman más que `sistema_total`, que son ofertas distintas.
    sistema: Counter = Counter()
    sacadas = 0
    for h in historial:
        if h.get("aplicado") is None and not h.get("archivada"):
            claves = [c for c, _ in motivos_del_sistema(h, filtros)]
            sacadas += bool(claves)
            for clave in claves:
                sistema[clave] += 1

    descartadas = [h for h in historial if h.get("aplicado") is False]
    motivos: Counter = Counter()
    for h in descartadas:
        motivos[clave_de_motivo(h) or "otro"] += 1

    por_fuente: Counter = Counter(h.get("source") or "?" for h in historial)

    return {
        "total": len(historial),
        "sin_marcar": len(_sin_marcar(historial, filtros)),
        "aplicadas": sum(1 for h in historial if h.get("aplicado") is True),
        "descartadas": len(descartadas),
        "archivadas": sum(1 for h in historial if h.get("archivada")),
        "sistema": dict(sistema),
        "sistema_total": sacadas,
        "sistema_solapadas": sum(sistema.values()) - sacadas,
        "motivos": dict(motivos),
        "escritos": escritos_a_mano(descartadas),
        "por_fuente": dict(por_fuente.most_common()),
        "ingles": pena_de_ingles(nombre_perfil, desde),
        "max_age_days": filtros.get("max_age_days"),
    }


# --- cuántas apliqué, y cuándo ---------------------------------------------
#
# El número que contesta "¿estoy haciendo algo o no?". Es lo único de la app que
# mide el trabajo de la persona y no el del sistema, y por eso va grande y arriba
# de la lista: los otros contadores dicen cuántas ofertas hay, éste dice cuántas
# veces te postulaste.

#: Los períodos del selector. Son semanas de calendario, de lunes a domingo: ver
#: `vacantia/ui/semanas.py`, que explica por qué dejaron de ser "últimos N días".
PERIODOS = semanas.PERIODOS

PERIODO_POR_DEFECTO = semanas.PERIODO_POR_DEFECTO


def _dia_local(marca) -> date | None:
    """El día local de una marca de tiempo guardada en UTC.

    Igual que en la tarjeta: hay que pasar a la hora de acá **antes** de quedarse
    con el día, porque entre las 21:00 y la medianoche el UTC ya es de mañana y
    una postulación de hoy contaría para el día siguiente.
    """
    crudo = str(marca or "").strip()
    if not crudo:
        return None
    try:
        momento = datetime.fromisoformat(crudo.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (momento.astimezone().date() if momento.tzinfo else momento.date())


def aplicadas_en(nombre_perfil: str, periodo: str = PERIODO_POR_DEFECTO,
                 solo_de_la_lista: bool = False) -> dict:
    """Cuántas postulaciones en ese período, y qué días.

    {cuantas, a_mano, periodo, etiqueta, desde, hasta, unidad,
     reparto: [(etiqueta, cuantas)], dias: [...] (una semana),
     grilla: [...] (varias semanas)}

    **Semanas de lunes a domingo** (20/11/2026). Antes eran ventanas para atrás
    desde hoy, y una "semana" arrancaba cualquier día: las barras salían
    rotuladas "24/10" y no se sabía qué día era. Isaías pidió ver qué días manda.

    * **Una semana** (esta o la pasada): siete barras con el nombre del día,
      `Lun 16 … Dom 22`. Los días que todavía no pasaron van marcados como
      `futuro`, para mostrarlos apagados y no como días en blanco.
    * **Varias semanas**: la grilla, una fila por semana y una columna por día,
      la de hoy arriba. Contesta las dos preguntas a la vez: qué días mandás y
      qué semanas aflojaste.

    El `reparto` sigue: con una semana son los siete días, con varias el total
    de cada semana de la más vieja a la más nueva. Es lo que suma igual que
    `cuantas`, y lo usan los tests que cuidan que las barras y el número no se
    contradigan.

    Con `solo_de_la_lista` quedan afuera las que se contaron a mano desde un
    posteo de LinkedIn. Es lo que se muestra parado en la pestaña **Apliqué**:
    ahí la lista de abajo son las ofertas marcadas una por una, y un número de
    arriba más grande que la lista de abajo se lee como un error.
    """
    from vacantia.ui import linkedin_urls

    periodo = semanas.periodo_valido(periodo)
    hoy = date.today()

    todas: list[date] = []
    for h in State(nombre_perfil).load_history():
        if h.get("aplicado") is not True:
            continue
        if (cuando := _dia_local(h.get("fecha_feedback"))) is not None:
            todas.append(cuando)

    # Y las que se aplicaron desde un posteo de LinkedIn, que no pasaron por
    # ninguna oferta de la lista y por lo tanto no están en el historial. Se
    # cuentan aparte para poder decirlo en la pantalla: si el total sube y no
    # hay ninguna tarjeta marcada, hay que poder explicar de dónde salió.
    a_mano_todas = [c for m in linkedin_urls.postulaciones(nombre_perfil)
                    if (c := _dia_local(m)) is not None]
    if not solo_de_la_lista:
        todas += a_mano_todas

    desde, hasta = semanas.rango(periodo, hoy, primera=min(todas, default=None))
    fechas = [f for f in todas if desde <= f <= hasta]
    a_mano = 0 if solo_de_la_lista else sum(1 for f in a_mano_todas if desde <= f <= hasta)

    salida = {
        "cuantas": len(fechas),
        "a_mano": a_mano,
        "periodo": periodo,
        "etiqueta": semanas.etiqueta(periodo),
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
    }
    if (hasta - desde).days < 7:
        dias = semanas.dias(fechas, desde, hoy)
        salida.update(unidad="día", dias=dias, grilla=[],
                      reparto=[(d["etiqueta"], d["cuantas"]) for d in dias])
    else:
        grilla = semanas.grilla(fechas, desde, hasta, hoy)
        salida.update(unidad="semana", dias=[], grilla=grilla,
                      reparto=[(f["rotulo"], f["total"]) for f in reversed(grilla)])
    return salida


def descartadas_en(nombre_perfil: str, periodo: str = PERIODO_POR_DEFECTO) -> dict:
    """Por qué descartaste, en ese período. {cuantas, periodo, etiqueta, motivos}.

    Es el equivalente de `aplicadas_en` para la pestaña **Descarté**, y contesta
    otra pregunta: no cuántas descartaste sino **por qué**. El total solo no
    sirve para nada; lo que sirve es ver que de 78 descartes 46 fueron por
    inglés, porque eso es una perilla de Mi perfil esperando que la muevan.

    Por eso el reparto es por motivo y no por semana: el ritmo importa cuando
    mandás CVs, porque medís tu trabajo. Descartar no es trabajo que quieras
    sostener, y saber que descartaste parejo a lo largo del mes no te dice nada.

    `motivos` viene ordenado de mayor a menor y con las etiquetas ya en
    castellano, listo para el gráfico de barras.
    """
    periodo = semanas.periodo_valido(periodo)
    # Las mismas semanas de lunes a domingo que Apliqué: el selector es uno solo.
    # "Desde que empecé" no necesita la primera fecha: acá no hay grilla que armar.
    desde, hasta = semanas.rango(periodo, date.today())
    if periodo == "todo":
        desde = None

    motivos: Counter = Counter()
    for h in State(nombre_perfil).load_history():
        if h.get("aplicado") is not False:
            continue
        # Se filtra por cuándo LA DESCARTASTE, no por cuándo se publicó el
        # aviso: la pregunta es qué venís rechazando últimamente.
        cuando = _dia_local(h.get("fecha_feedback"))
        if desde is not None and (cuando is None or not desde <= cuando <= hasta):
            continue
        motivos[clave_de_motivo(h) or "otro"] += 1

    etiquetas = {c: t for c, t, _ in MOTIVOS}
    # "Escrito a mano" y no "Otro": es el descarte que dice algo del puesto, que
    # es justamente el valioso, y llamarlo "otro" lo manda al cajón de sobras.
    etiquetas["otro"] = "Escrito a mano"
    filas = [(etiquetas.get(clave, clave), cuantas)
             for clave, cuantas in motivos.most_common()]

    return {
        "cuantas": sum(motivos.values()),
        "periodo": periodo,
        "etiqueta": semanas.etiqueta(periodo),
        "motivos": filas,
        "desde": desde.isoformat() if desde else "",
    }


#: Cuántos días muestra el gráfico de Cómo viene funcionando. Dos semanas: con
#: una sola, un fin de semana tranquilo parece una rotura.
DIAS_DE_ENTRADAS = 14


def entradas_por_dia(nombre_perfil: str, dias: int = DIAS_DE_ENTRADAS) -> list[dict]:
    """Cuántas ofertas nuevas entraron cada día, de la más vieja a hoy.

    Es el gráfico de Cómo viene funcionando, y contesta la pregunta de esa
    sección mejor que la tabla de la última búsqueda: una búsqueda en cero puede
    ser un mal día, varios días seguidos en cero es que algo dejó de andar.

    **Sale del historial y no del registro.** El registro rota a mano y lo
    comparten todos los perfiles y los tests: el 13/9/2026 tenía una sola
    corrida real y media docena de corridas de juguete del perfil "test". El
    historial es por perfil, es el archivo durable, y `found_at` es exactamente
    cuándo entró cada oferta.

    Los días sin nada van igual, con valor cero: acá el cero es el dato.
    """
    hoy = date.today()
    arranque = hoy - timedelta(days=dias - 1)
    cuantas: Counter = Counter()
    for h in State(nombre_perfil).load_history():
        dia = _dia_local(h.get("found_at"))
        if dia is not None and arranque <= dia <= hoy:
            cuantas[dia] += 1
    return [{"etiqueta": f"{d.day}/{d.month}", "cuantas": cuantas[d]}
            for d in (arranque + timedelta(days=i) for i in range(dias))]


# --- qué te están pidiendo -------------------------------------------------
#
# La lista de habilidades sale del campo `stack`, que el modelo ya venía
# devolviendo por cada oferta cuando la puntúa. **No cuesta ninguna llamada
# extra**: ya le estamos pasando el aviso entero para que lo puntúe, y pedirle
# de paso qué piden son unos pocos tokens más de respuesta.
#
# Eso es también lo que la hace servir para cualquier oficio. No hay ninguna
# lista de tecnologías escrita en el código, que es lo que habría que mantener
# para siempre y aun así nunca cubriría marketing ni seguridad e higiene. El
# modelo lee el aviso y devuelve lo que ese aviso pide, sea LangChain, Google
# Analytics o la ISO 45001.

#: Con qué se corta un `stack` en habilidades sueltas. La barra está porque el
#: modelo agrupa alternativas ("AWS/Azure/GCP" es una sola entrada suya y son
#: tres cosas distintas para contar), y el punto y coma porque a veces cambia de
#: separador a mitad de la lista.
_CORTES = re.compile(r"[,;/|]| \+ |\band\b|\bo\b|\by\b", re.I)

#: Lo que no es una habilidad aunque venga en la lista. Son las muletillas con
#: las que el modelo rellena cuando el aviso no dice nada concreto: no nombran
#: nada que se pueda ir a aprender, que es para lo que sirve este gráfico.
_NO_ES_HABILIDAD = frozenset({
    "", "n/a", "na", "none", "null", "-", "?", "varios", "otros", "etc",
    "no especificado", "not specified", "unknown", "experiencia", "experience",
    "conocimientos", "skills", "habilidades", "tecnologias", "tecnologías",
})

#: Cuántas habilidades distintas se muestran. Con más, el gráfico deja de ser un
#: "qué me piden" y pasa a ser un inventario: la cola larga son las que
#: aparecieron una sola vez, y una sola vez no es una tendencia.
TOPE_HABILIDADES = 15


def _habilidades_de(texto: str) -> list[str]:
    """Un campo `stack` cortado en habilidades sueltas, sin normalizar todavía."""
    salida = []
    for parte in _CORTES.split(texto or ""):
        limpia = " ".join(parte.split()).strip(" .-•·")
        if limpia.lower() in _NO_ES_HABILIDAD:
            continue
        # Una "habilidad" de 40 caracteres es una frase que el modelo metió
        # donde iba un nombre; contarla ensucia el gráfico con una barra única.
        if 1 < len(limpia) <= 32:
            salida.append(limpia)
    return salida


def _mismo_nombre(conteo: Counter) -> dict[str, str]:
    """Qué escrituras distintas son en realidad la misma habilidad.

    Devuelve {como vino: nombre canónico}. Resuelve dos cosas y **sólo** dos, a
    propósito: mezclar de más es peor que no mezclar, porque inventa una
    tendencia que no existe.

    1. **Mayúsculas.** "python" y "Python" son la misma. Gana la escritura más
       frecuente, que es la que usa el mercado: así sale "PostgreSQL" y no
       "postgresql", sin tener una tabla de nombres propios.
    2. **Plurales, pero sólo cuando las dos formas aparecen de verdad.** "LLMs"
       se une a "LLM" porque en los avisos están las dos. "Kubernetes" y
       "Analytics" no se tocan, porque el singular no existe en ningún lado.
       Es lo que hace que esto ande igual en marketing o en seguridad e higiene
       sin saber nada del rubro: la regla la ponen los datos, no una lista.
    """
    # Paso 1: agrupar por minúsculas y quedarse con la escritura más usada.
    por_minuscula: dict[str, Counter] = {}
    for nombre, cuantas in conteo.items():
        por_minuscula.setdefault(nombre.lower(), Counter())[nombre] += cuantas
    canonico = {clave: variantes.most_common(1)[0][0]
                for clave, variantes in por_minuscula.items()}

    # Paso 2: el plural cae en el singular, si el singular existe en los datos.
    for clave in list(canonico):
        singular = clave[:-1] if clave.endswith("s") else ""
        if singular and singular in canonico:
            canonico[clave] = canonico[singular]

    return {nombre: canonico[nombre.lower()] for nombre in conteo}


def habilidades_pedidas(nombre_perfil: str, desde: str = "todo",
                        tope: int = TOPE_HABILIDADES) -> dict:
    """Qué piden los avisos que entraron. {cuantas, ofertas, filas, sin_datos}.

    `filas` es [(habilidad, en cuántas ofertas)] de mayor a menor, lista para el
    gráfico de barras. `sin_datos` son las ofertas que todavía no pasaron por el
    modelo y por lo tanto no tienen nada que aportar: se dice en pantalla, para
    que un número bajo no se lea como "nadie pide nada".

    Se cuenta **una vez por oferta**: si un aviso nombra Python cuatro veces,
    sigue siendo un solo trabajo que pide Python. Lo que contesta el gráfico es
    en cuántas búsquedas te lo van a pedir, no cuánto insisten.

    Son dos pasadas y tienen que ser dos: primero se ve qué nombres hay para
    poder unificarlos, y recién después se cuenta. Al revés, un aviso que dice
    "Python, python" cuenta dos.
    """
    historial = [h for h in State(nombre_perfil).load_history()
                 if _entra_por_fecha(h, desde)]

    # Primera pasada: qué nombres aparecen y con qué frecuencia. Es lo que
    # necesita `_mismo_nombre` para decidir cuál escritura gana y qué plurales
    # tienen singular de verdad.
    por_oferta: list[list[str]] = []
    crudo: Counter = Counter()
    for h in historial:
        habilidades = _habilidades_de(h.get("stack") or "")
        if not habilidades:
            continue
        por_oferta.append(habilidades)
        crudo.update(habilidades)

    canonico = _mismo_nombre(crudo)

    # Segunda pasada: recién ACÁ se cuenta, y se cuenta una vez por oferta.
    #
    # El orden importa y fue un bug: deduplicando antes de unificar los nombres,
    # un aviso que decía "Python, python" contaba dos, y uno que decía "LLM" y
    # "LLMs" también. Son un solo trabajo pidiendo una sola cosa. Unificar
    # primero y deduplicar después es lo que lo arregla de raíz.
    unidas: Counter = Counter()
    for habilidades in por_oferta:
        unidas.update({canonico[n] for n in habilidades})

    return {
        "filas": unidas.most_common(tope),
        "distintas": len(unidas),
        "ofertas": len(por_oferta),
        "sin_datos": len(historial) - len(por_oferta),
    }


#: Los tramos del histograma de puntajes. Son los que usa la persona para
#: decidir: 0 es "esto no es para vos", y de `min_score` para arriba es lo que
#: el sistema considera digno de avisar por Telegram.
TRAMOS_PUNTAJE = ((0, 0), (1, 19), (20, 39), (40, 59), (60, 79), (80, 100))


def distribucion_de_puntajes(nombre_perfil: str) -> list[dict]:
    """Cuántas ofertas hay en cada tramo de puntaje.

    Es el gráfico que contesta "¿el sistema me está trayendo cosas buenas?" sin
    tener que abrir la lista. Una montaña pegada al cero significa que las
    búsquedas están mal apuntadas; una repartida significa que el problema es
    otro.
    """
    historial = State(nombre_perfil).load_history()
    try:
        minimo = int(leer_perfil(nombre_perfil).get("min_score", 60) or 0)
    except (FileNotFoundError, json.JSONDecodeError):
        minimo = 60

    salida = []
    for desde_p, hasta_p in TRAMOS_PUNTAJE:
        cuantas = sum(1 for h in historial
                      if h.get("score") is not None
                      and desde_p <= h["score"] <= hasta_p)
        salida.append({
            "etiqueta": "0" if hasta_p == 0 else f"{desde_p} a {hasta_p}",
            "cuantas": cuantas,
            # De acá para arriba el sistema te avisa. Es el único tramo que
            # lleva color de estado, y lo lleva porque significa algo.
            "avisa": desde_p >= minimo,
        })
    return salida
