"""Semanas de lunes a domingo (`vacantia/ui/semanas.py`).

Antes el selector contaba para atrás desde hoy, y una "semana" arrancaba
cualquier día: las barras quedaban rotuladas "24/10" sin decir qué día era.
"""

from datetime import date

from vacantia.ui import semanas

JUEVES = date(2026, 11, 20)          # el 20/11/2026 fue jueves... es viernes: se verifica abajo


def test_la_fecha_de_prueba_es_la_que_dice():
    assert JUEVES.weekday() == 4     # viernes
    assert semanas.lunes_de(JUEVES) == date(2026, 11, 16)


def test_esta_semana_va_de_lunes_a_domingo_aunque_hoy_sea_viernes():
    assert semanas.rango("semana", JUEVES) == (date(2026, 11, 16), date(2026, 11, 22))


def test_la_semana_pasada_es_la_de_calendario_anterior():
    assert semanas.rango("semana-pasada", JUEVES) == (date(2026, 11, 9), date(2026, 11, 15))


def test_cuatro_semanas_terminan_en_la_de_hoy():
    assert semanas.rango("4-semanas", JUEVES) == (date(2026, 10, 26), date(2026, 11, 22))
    desde, hasta = semanas.rango("3-meses", JUEVES)
    assert desde.weekday() == 0 and hasta.weekday() == 6
    assert (hasta - desde).days + 1 == 13 * 7


def test_desde_que_empece_arranca_el_lunes_de_la_primera_postulacion():
    desde, _ = semanas.rango("todo", JUEVES, primera=date(2026, 9, 7))
    assert desde == date(2026, 9, 7)               # 7/9/2026 fue lunes
    # Sin postulaciones, sólo la semana de hoy.
    assert semanas.rango("todo", JUEVES) == semanas.rango("semana", JUEVES)
    # Una fecha rota no arma una grilla de mil filas.
    desde, hasta = semanas.rango("todo", JUEVES, primera=date(1970, 1, 1))
    assert ((hasta - desde).days + 1) // 7 == semanas.MAX_SEMANAS


def test_un_periodo_desconocido_cae_en_el_de_siempre():
    """Un link viejo guardado con "?periodo=30d" no tiene que romper la pantalla."""
    assert semanas.periodo_valido("30d") == semanas.PERIODO_POR_DEFECTO
    assert semanas.etiqueta("30d") == "Esta semana"


def test_la_semana_sola_muestra_el_nombre_de_cada_dia():
    fechas = [date(2026, 11, 17), date(2026, 11, 17), date(2026, 11, 19)]
    semana = semanas.dias(fechas, date(2026, 11, 16), JUEVES)
    assert [d["etiqueta"] for d in semana] == [
        "Lun 16", "Mar 17", "Mié 18", "Jue 19", "Vie 20", "Sáb 21", "Dom 22"]
    assert [d["cuantas"] for d in semana] == [0, 2, 0, 1, 0, 0, 0]
    assert [d["hoy"] for d in semana].index(True) == 4
    # Sábado y domingo todavía no pasaron: no son días "en blanco".
    assert [d["futuro"] for d in semana] == [False] * 5 + [True] * 2


def test_la_grilla_tiene_la_semana_de_hoy_arriba():
    fechas = [date(2026, 11, 3), date(2026, 11, 17)]
    filas = semanas.grilla(fechas, date(2026, 11, 2), date(2026, 11, 22), JUEVES)
    assert [f["rotulo"] for f in filas] == [
        "Semana del 16/11", "Semana del 9/11", "Semana del 2/11"]
    assert [f["total"] for f in filas] == [1, 0, 1]
    assert filas[2]["dias"][1]["cuantas"] == 1     # martes 3/11


def test_la_fecha_corta_dice_el_dia():
    assert semanas.dia_corto(date(2026, 11, 17)) == "mar 17/11"
