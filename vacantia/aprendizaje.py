"""Lo que la persona ya decidió, convertido en ejemplos para el scoring.

**Por qué existe.** Hasta el 17/9/2026 el sistema no aprendía nada: los
descartes se guardaban con su motivo, se contaban en Métricas, y el modelo que
puntúa nunca los veía. Isaías llevaba 113 descartes marcados, 10 de ellos "no es
una oferta", y los posteos de LinkedIn que no buscan a nadie seguían entrando
igual, puntuados como si fueran vacantes.

**Cómo aprende.** No hay entrenamiento: en cada lote, el prompt lleva las
últimas decisiones de la persona como ejemplos, con el motivo escrito con sus
palabras. El modelo puntúa lo parecido de la misma forma.

**Qué entra y qué no.**
- Los descartes cuyo motivo dice algo del puesto: "no es una oferta", "no era
  mi puesto", "pide tecnologías con las que no trabajo" y el texto libre.
- **No** entran inglés, presencial ni el caso especial
  (`motivos.MOTIVOS_QUE_NO_ENSENIAN`): los dos primeros ya los aplican los
  filtros, mejor y sin gastar prompt, y el tercero la persona pidió que no
  enseñe.
- Las aplicadas, como ejemplo de lo que sí sirve.

**Por qué con tope.** Cada ejemplo viaja en cada lote de 6 ofertas. Con 12
descartes y 6 aplicadas el bloque ronda los 1.500 tokens por lote; con los 113
descartes serían 10.000, y en el plan gratis eso es cuota que se va en repetir
lo mismo. Se eligen los más recientes, que son los que reflejan lo que la
persona busca hoy.
"""

from vacantia.motivos import MOTIVOS_QUE_NO_ENSENIAN, _ETIQUETAS_MOTIVO, clave_de_motivo

MAX_DESCARTADAS = 12
MAX_APLICADAS = 6
#: Lo que se muestra de cada aviso. El título solo no alcanza para "no es una
#: oferta": el de un posteo de Google es "42 comentarios - LinkedIn", y lo que
#: delata que no busca a nadie está en las primeras líneas del texto.
LARGO_DEL_EXTRACTO = 160


def _una_linea(texto: str, largo: int) -> str:
    plano = " ".join(str(texto or "").split())
    return plano if len(plano) <= largo else plano[: largo - 1].rstrip() + "…"


def _motivo(oferta: dict) -> str:
    clave = clave_de_motivo(oferta)
    escrito = (oferta.get("motivo_descarte") or "").strip()
    etiqueta = _ETIQUETAS_MOTIVO.get(clave, "")
    partes = [p for p in (etiqueta, escrito if len(escrito) > 3 else "") if p]
    return " — ".join(dict.fromkeys(partes))


def _renglon(oferta: dict) -> str:
    titulo = _una_linea(oferta.get("scored_title") or oferta.get("title"), 80)
    empresa = _una_linea(oferta.get("company"), 40)
    extracto = _una_linea(oferta.get("description"), LARGO_DEL_EXTRACTO)
    renglon = f'- "{titulo}"' + (f" ({empresa})" if empresa else "")
    # El stack que extrajo el modelo. Sin esto "pide tecnologías con las que no
    # trabajo" no decía CUÁLES: Isaías tenía 11 descartes así y el modelo sólo
    # veía el título ("Software Engineer Backend") y el motivo genérico.
    if stack := _una_linea(oferta.get("stack"), 80):
        renglon += f' | stack: "{stack}"'
    if extracto:
        renglon += f' | starts with: "{extracto}"'
    return renglon


def decisiones_para_el_prompt(historial: list[dict]) -> str:
    """El bloque de ejemplos listo para el prompt, o "" si no hay ninguno.

    Vacío cuando la persona todavía no marcó nada que enseñe: así un perfil
    nuevo manda exactamente el mismo prompt que antes de que esto existiera.
    """
    recientes = sorted(
        (h for h in historial if h.get("fecha_feedback")),
        key=lambda h: h.get("fecha_feedback") or "",
        reverse=True,
    )
    descartadas, aplicadas, vistos = [], [], set()
    for h in recientes:
        # El mismo aviso republicado (Computrabajo, LinkedIn) no cuenta dos
        # veces: dos ejemplos iguales gastan lugar y no enseñan más.
        titulo = " ".join(str(h.get("scored_title") or h.get("title") or "").lower().split())
        if titulo in vistos:
            continue
        if h.get("aplicado") is True and len(aplicadas) < MAX_APLICADAS:
            aplicadas.append(h)
            vistos.add(titulo)
        elif (h.get("aplicado") is False and len(descartadas) < MAX_DESCARTADAS
              and clave_de_motivo(h) not in MOTIVOS_QUE_NO_ENSENIAN
              and (motivo := _motivo(h))):
            descartadas.append((h, motivo))
            vistos.add(titulo)

    if not descartadas and not aplicadas:
        return ""

    lineas = [
        "PAST DECISIONS — postings this candidate already reviewed by hand. They are",
        "the best evidence of what the candidate wants: score similar postings the",
        "same way. Rejection reasons are the candidate's own words, in Spanish.",
    ]
    if descartadas:
        lineas.append("REJECTED:")
        lineas += [f"{_renglon(h)} | reason: \"{_una_linea(m, 120)}\"" for h, m in descartadas]
    if aplicadas:
        lineas.append("APPLIED:")
        lineas += [_renglon(h) for h in aplicadas]
    return "\n".join(lineas) + "\n\n"
