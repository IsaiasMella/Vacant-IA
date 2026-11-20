"""Semanas de calendario, de lunes a domingo, para contar postulaciones.

**Por qué existe (20/11/2026).** El selector de Apliqué tenía "Últimos 7 días",
"Últimas 2 semanas", "Último mes": ventanas que se cuentan para atrás desde hoy.
Así una "semana" arrancaba cualquier día (si hoy es jueves, de viernes a jueves)
y las barras quedaban rotuladas con fechas sueltas como "24/10", sin decir qué
día era. Isaías lo pidió así: que la semana arranque el lunes y que se vea el
nombre de cada día, para saber qué días manda y qué días se le pasan en blanco.

Todo es aritmética de fechas, sin disco: lo que cuenta lo decide quien llama.
"""

from datetime import date, timedelta

#: Los períodos del selector: (clave, etiqueta, semanas). `0` = desde la primera
#: postulación. "Semana pasada" es la única que no termina en la de hoy.
PERIODOS = (
    ("semana", "Esta semana", 1),
    ("semana-pasada", "Semana pasada", 1),
    ("4-semanas", "Últimas 4 semanas", 4),
    ("3-meses", "Últimos 3 meses", 13),
    ("todo", "Desde que empecé", 0),
)

PERIODO_POR_DEFECTO = "semana"

#: Tope de filas de la grilla con "Desde que empecé": un año. Más que eso no se
#: lee, y protege de una fecha rota en el historial (un 1970 haría miles de filas).
MAX_SEMANAS = 52

DIAS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
_DIAS_MINUSCULA = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def lunes_de(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def periodo_valido(periodo: str) -> str:
    return periodo if periodo in {c for c, _, _ in PERIODOS} else PERIODO_POR_DEFECTO


def etiqueta(periodo: str) -> str:
    return dict((c, e) for c, e, _ in PERIODOS)[periodo_valido(periodo)]


def rango(periodo: str, hoy: date, primera: date | None = None) -> tuple[date, date]:
    """(lunes del arranque, domingo del final) del período.

    `primera` es la fecha de la primera postulación, para "Desde que empecé".
    Sin postulaciones, esa opción muestra sólo la semana de hoy.
    """
    periodo = periodo_valido(periodo)
    este_lunes = lunes_de(hoy)
    if periodo == "semana-pasada":
        lunes = este_lunes - timedelta(days=7)
        return lunes, lunes + timedelta(days=6)
    semanas = dict((c, s) for c, _, s in PERIODOS)[periodo]
    if not semanas:
        desde = lunes_de(primera) if primera and primera <= hoy else este_lunes
        semanas = min(MAX_SEMANAS, (este_lunes - desde).days // 7 + 1)
    return este_lunes - timedelta(days=7 * (semanas - 1)), este_lunes + timedelta(days=6)


def dia_corto(dia: date) -> str:
    """"lun 17/11": la fecha con el día, como va en la lista de Apliqué."""
    return f"{_DIAS_MINUSCULA[dia.weekday()]} {dia.day}/{dia.month}"


def dias(fechas: list[date], lunes: date, hoy: date) -> list[dict]:
    """Los 7 días de una semana: {etiqueta, cuantas, hoy, futuro}.

    Es lo que se muestra con una semana sola: siete barras con el nombre del día.
    Los que todavía no pasaron van marcados para mostrarlos apagados, y no como
    días en los que no se mandó nada.
    """
    salida = []
    for i in range(7):
        dia = lunes + timedelta(days=i)
        salida.append({"etiqueta": f"{DIAS[i]} {dia.day}",
                       "fecha": dia,
                       "cuantas": sum(1 for f in fechas if f == dia),
                       "hoy": dia == hoy,
                       "futuro": dia > hoy})
    return salida


def grilla(fechas: list[date], desde: date, hasta: date, hoy: date) -> list[dict]:
    """Una fila por semana, de la más reciente a la más vieja.

    {lunes, rotulo, dias: [{cuantas, hoy, futuro} × 7], total}

    La más reciente arriba porque es la que se mira primero: "¿cómo voy esta
    semana?". Abajo queda el ritmo de las anteriores.
    """
    filas = []
    lunes = lunes_de(hasta)
    while lunes >= desde:
        semana = dias(fechas, lunes, hoy)
        filas.append({"lunes": lunes,
                      "rotulo": f"Semana del {lunes.day}/{lunes.month}",
                      "dias": semana,
                      "total": sum(d["cuantas"] for d in semana)})
        lunes -= timedelta(days=7)
    return filas
