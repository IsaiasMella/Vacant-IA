"""Los motivos de descarte: cuáles hay, cómo se reconocen y cuáles enseñan.

Vivía en `ui/data.py`, pero desde el 17/9/2026 el motor también lo necesita:
el scoring le muestra al modelo tus descartes como ejemplos, y tiene que saber
cuáles NO van (`MOTIVOS_QUE_NO_ENSENIAN`). El motor no puede importar la
pantalla, así que esto pasó a su propio módulo. `ui.data` lo reexporta con los
mismos nombres.
"""

import re


# --- por qué no apliqué -----------------------------------------------------
#
# El campo era un texto libre y obligatorio, y con 60 descartes se vio en qué se
# convierte: 46 veces la misma frase escrita a mano ("Estaba en ingles, osea que
# necesito ingles para aplicar"), 4 veces "era presencial en Buenos Aires", y 6
# veces un guion, que es lo que se escribe cuando el motivo no se puede resumir
# y encima uno no quiere que el sistema saque conclusiones de ahí.
#
# El texto libre sigue estando —hay descartes que sólo se explican escribiendo—
# pero deja de ser el camino principal.

#: (clave, etiqueta, qué significa). El orden es el del desplegable.
#:
#: Los tres del medio se sumaron el 13/9/2026, cuando Métricas empezó a mostrar
#: lo escrito a mano: eran 16 descartes de Isaías tipeados de siete formas
#: ("No es una oferta laboral", "No era una oferta", "No rea mi puesto", "Me
#: pide tecnologias con las que no trabajo"...). Lo mismo que había pasado con
#: el inglés: si se repite, va a la lista.
MOTIVOS = (
    ("ingles", "Piden inglés",
     "Suma al contador de ofertas que se pierden por el idioma."),
    ("presencial", "Es presencial y no puedo ir",
     "El aviso exige estar en un lugar al que no vas."),
    ("no_es_oferta", "No es una oferta de trabajo",
     "Un posteo que habla de otra cosa y no busca a nadie."),
    ("no_mi_puesto", "No era mi puesto",
     "Es un trabajo de otra cosa, aunque haya coincidido con la búsqueda."),
    ("tecnologias", "Pide tecnologías con las que no trabajo",
     "El puesto es de lo tuyo, pero con otras herramientas."),
    ("especial", "Caso especial (que no aprenda de esto)",
     "Se guarda el descarte, pero no cuenta como preferencia tuya."),
)

#: Los dos caminos para descartar, y alcanza con cualquiera de los dos: elegir
#: uno de arriba, o escribirlo. **No hay una opción "Otro motivo" en la lista**,
#: y es a propósito: obligaba a abrir el desplegable, bajar hasta "Otro" y recién
#: ahí escribir, o sea tres pasos de más para el caso en que ya tenías la mano en
#: el teclado. El campo está siempre a la vista y es opcional.

#: Las que NO son una preferencia sobre el puesto y por lo tanto no tienen que
#: enseñarle nada al scoring (ver `aprendizaje.decisiones_para_el_prompt`).
#:
#: "Piden inglés" y "es presencial" son restricciones tuyas que los filtros ya
#: aplican solos y mejor: meterlas al prompt como ejemplos negativos sería
#: enseñarle dos veces lo mismo, y por el lado impreciso. Y "razón especial" lo
#: pediste explícitamente.
#:
#: Los otros tres SÍ enseñan: "no era mi puesto" y "otras tecnologías" dicen
#: qué no te sirve, y "no es una oferta" es justo lo que el puntaje tendría que
#: aprender a mandar al cero.
MOTIVOS_QUE_NO_ENSENIAN = frozenset({"ingles", "presencial", "especial"})

_ETIQUETAS_MOTIVO = dict((clave, etiqueta) for clave, etiqueta, _ in MOTIVOS)

#: Para los descartes viejos, escritos a mano antes de que existiera el
#: desplegable. Sin esto, los 46 "estaba en ingles" que ya tenía Isaías no
#: sumarían al contador de inglés y el número arrancaría mintiendo.
#:
#: Los patrones de los motivos nuevos salen de las redacciones reales, errores
#: de tipeo incluidos ("No rea mi puesto"), y son angostos a propósito: "no es
#: una oferta" y no "no es", porque una frase mal clasificada desaparece de la
#: lista de lo escrito a mano y ya no hay forma de verla.
_MOTIVO_VIEJO = (
    ("ingles", re.compile(r"\bingl[eé]s\b|\bingles\b", re.I)),
    ("presencial", re.compile(r"\bpresencial\b|\bh[ií]brid", re.I)),
    ("no_es_oferta", re.compile(r"\bno\s+(?:es|era)\s+(?:una?\s+)?(?:oferta|empleo)\b",
                                re.I)),
    ("no_mi_puesto", re.compile(r"\bno\s+(?:es|era|rea)\s+mi\s+puesto\b", re.I)),
    ("tecnologias", re.compile(
        r"\bno\s+trabajo\s+con\s+(?:esas?\s+)?tecnolog"
        r"|\btecnolog[ií]as?\s+con\s+(?:las?\s+)?que\s+no\s+trabajo\b", re.I)),
    ("especial", re.compile(r"^[-–—\s]*$")),
)


def clave_de_motivo(oferta: dict) -> str:
    """Qué motivo tiene este descarte, sea del desplegable o escrito a mano.

    Devuelve "" para un texto libre que no encaja en ninguna categoría — que es
    exactamente el descarte valioso: el que dice algo del puesto y no de una
    restricción que los filtros ya conocen.
    """
    if clave := (oferta.get("motivo_clave") or "").strip():
        return clave if clave in _ETIQUETAS_MOTIVO else ""
    texto = (oferta.get("motivo_descarte") or "").strip()
    if not texto:
        return ""
    for clave, patron in _MOTIVO_VIEJO:
        if patron.search(texto):
            return clave
    return ""
