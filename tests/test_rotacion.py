"""La rotación de términos sigue de corrida en corrida, no de día en día.

Antes la tanda salía de la fecha, y las tres corridas del día (12:00, 16:30 y
23:59) repetían las mismas búsquedas: el 18/11/2026 dos corridas seguidas de
LinkedIn trajeron unas 50 ofertas cada una y 31 ya estaban vistas. Lo que se
fija acá es que la segunda corrida del mismo día busque otra cosa, que se den
vuelta todos los términos, y que un --dry-run no mueva nada.
"""

import json

import pytest

from vacantia import engine, rotacion
from vacantia import state as state_mod
from vacantia.sources.base import Source
from vacantia.sources.getonbrd import GetOnBoardSource
from vacantia.sources.google_posts import build_queries
from vacantia.sources.linkedin_jobs import build_searches
from vacantia.sources.portales_ar import ComputrabajoSource

TERMINOS = ["AI Engineer", "LLM Engineer", "Backend Python", "Full Stack Developer",
            "Python Developer"]


@pytest.fixture
def raiz(monkeypatch, tmp_path):
    """El estado va a una carpeta temporal, nunca a `state/` del repo."""
    monkeypatch.setattr(state_mod, "STATE_ROOT", tmp_path)
    return tmp_path


def _perfil(nombre="test"):
    return {"name": nombre, "keywords": list(TERMINOS)}


def _correr(perfil, fuente, cuantos):
    """Una corrida: pide la tanda y, como hace el motor al final, la guarda."""
    tanda, siguiente = rotacion.elegir(perfil, fuente, TERMINOS, cuantos)
    if siguiente is not None:
        rotacion.guardar(perfil["name"], {fuente: siguiente})
    return tanda


# --- el núcleo --------------------------------------------------------------

def test_la_segunda_corrida_del_dia_busca_otros_terminos(raiz):
    perfil = _perfil()
    primera = _correr(perfil, "linkedin", 2)
    segunda = _correr(perfil, "linkedin", 2)
    assert primera == ["AI Engineer", "LLM Engineer"]
    assert segunda == ["Backend Python", "Full Stack Developer"]


def test_en_pocas_corridas_se_buscan_todos_y_vuelve_a_empezar(raiz):
    perfil = _perfil()
    vistos = []
    for _ in range(3):              # 5 términos de a 2: tres corridas
        vistos += _correr(perfil, "linkedin", 2)
    assert set(vistos) == set(TERMINOS)
    # Dio la vuelta: la sexta posición es otra vez la primera.
    assert vistos[5] == "AI Engineer"


def test_leer_no_avanza(raiz):
    """`is_available` y `fetch` arman la lista cada uno: pedirla dos veces no
    puede comerse dos tandas."""
    perfil = _perfil()
    assert rotacion.elegir(perfil, "linkedin", TERMINOS, 2) == \
        rotacion.elegir(perfil, "linkedin", TERMINOS, 2)


def test_cada_fuente_tiene_su_propia_posicion(raiz):
    perfil = _perfil()
    _correr(perfil, "linkedin", 2)
    assert _correr(perfil, "getonbrd", 2) == ["AI Engineer", "LLM Engineer"]
    datos = json.loads((raiz / "test" / "rotacion.json").read_text(encoding="utf-8"))
    assert datos == {"linkedin": 2, "getonbrd": 2}


def test_si_el_tope_alcanza_para_todos_no_rota_ni_guarda(raiz):
    perfil = _perfil()
    tanda, siguiente = rotacion.elegir(perfil, "linkedin", TERMINOS, 10)
    assert tanda == TERMINOS and siguiente is None
    tanda, siguiente = rotacion.elegir(perfil, "linkedin", TERMINOS, 0)
    assert tanda == TERMINOS and siguiente is None


def test_sacar_terminos_del_perfil_no_rompe_la_posicion(raiz):
    """La posición guardada puede quedar más allá del final si la lista se
    achica: se toma módulo el largo de hoy."""
    rotacion.guardar("test", {"linkedin": 4})
    tanda, _ = rotacion.elegir(_perfil(), "linkedin", TERMINOS[:3], 2)
    assert tanda == ["LLM Engineer", "Backend Python"]


def test_un_archivo_roto_arranca_de_cero(raiz):
    (raiz / "test").mkdir()
    (raiz / "test" / "rotacion.json").write_text("{no es json", encoding="utf-8")
    assert rotacion.elegir(_perfil(), "linkedin", TERMINOS, 2)[0] == TERMINOS[:2]


def test_cada_perfil_rota_por_su_lado(raiz):
    _correr(_perfil("ana"), "linkedin", 2)
    assert rotacion.elegir(_perfil("zoe"), "linkedin", TERMINOS, 2)[0] == TERMINOS[:2]


# --- las fuentes la usan ------------------------------------------------------

def test_linkedin_arma_sus_busquedas_desde_la_posicion_guardada(raiz):
    rotacion.guardar("test", {"linkedin": 2})
    config = {"locations": ["Argentina"], "max_searches": 2}
    assert build_searches(_perfil(), config) == [
        ("Backend Python", "Argentina"), ("Full Stack Developer", "Argentina")]


def test_google_posts_arma_sus_queries_desde_la_posicion_guardada(raiz):
    rotacion.guardar("test", {"google_posts": 3})
    queries = build_queries(_perfil(), {"max_queries": 1})
    assert len(queries) == 1 and '"Full Stack Developer"' in queries[0]


def test_los_portales_y_getonbrd_anotan_desde_donde_sigue(raiz):
    portal = ComputrabajoSource({"max_queries": 2}, _perfil())
    assert portal.terminos() == TERMINOS[:2]
    assert portal.siguiente_en_rotacion == 2

    rotacion.guardar("test", {"getonbrd": 4})
    gob = GetOnBoardSource({"max_queries": 2}, _perfil())
    assert gob.terminos() == ["Python Developer", "AI Engineer"]
    assert gob.siguiente_en_rotacion == 1


# --- el motor guarda, y sólo en una corrida de verdad -------------------------

class _FuenteQueRota(Source):
    name = "linkedin"

    def fetch(self):
        self.siguiente_en_rotacion = 3
        return []


@pytest.fixture
def motor_sin_red(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for var in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(engine, "_usable_sources",
                        lambda profile, result: [_FuenteQueRota({}, profile)])
    return tmp_path


PERFIL_MOTOR = {"name": "test", "min_score": 0, "cv_path": "resume/x.md",
                "llm": {"provider": "gemini"}, "sources": [],
                "notifiers": [{"type": "console", "enabled": True}]}


def test_la_corrida_de_verdad_guarda_la_posicion(motor_sin_red):
    engine.run(dict(PERFIL_MOTOR))
    ruta = motor_sin_red / "state" / "test" / "rotacion.json"
    assert json.loads(ruta.read_text(encoding="utf-8")) == {"linkedin": 3}


def test_un_dry_run_no_mueve_la_rotacion(motor_sin_red):
    engine.run(dict(PERFIL_MOTOR), dry_run=True)
    assert not (motor_sin_red / "state" / "test" / "rotacion.json").exists()
