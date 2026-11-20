"""El inglés se detecta antes de pagar la puntuación, leyendo el aviso entero.

Dos incidentes:

- El 19/11/2026, de 11 ofertas de LinkedIn que se puntuaron, 9 se cayeron
  después por idioma: se pagaba el modelo para descartarlas. En el historial,
  17 de esos descartes eran "aviso en 'en'" y el resto un requisito explícito.
- Se pasó una oferta que pedía inglés al final de la descripción. Las fuentes
  cortan la descripción en 3.000 caracteres, y el requisito quedaba del otro
  lado del corte.
"""

import pandas as pd
import pytest

from vacantia import engine
from vacantia.filters import (
    descartar_antes_de_puntuar, idioma_del_texto, passes_language,
    pide_ingles_sin_puntuar,
)
from vacantia.models import Job
from vacantia.sources.linkedin_jobs import LinkedInJobsSource

SIN_INGLES = {"allow_english": False, "max_english_level": "A2", "scan_description": True}

#: Un aviso en castellano, con la jerga en inglés de siempre. Se repite para
#: superar los 3.000 caracteres que se guardan.
CUERPO_ES = (
    "Somos una empresa de tecnología y buscamos un AI Engineer para sumarse al "
    "equipo de producto. Vas a trabajar con LLMs, RAG, function calling y agentes, "
    "con Python, FastAPI y Machine Learning Ops. Ofrecemos trabajo remoto, horario "
    "flexible y un equipo con mucha experiencia en la construcción de productos. "
)
CUERPO_EN = (
    "We are looking for an AI Engineer to join our product team. You will work "
    "with LLMs and agents, and you will own the integration of our models with "
    "the platform. Our team is distributed and we value ownership. This is a "
    "remote role for candidates who have shipped products to production. "
)


def _aviso(descripcion: str, completa: str = "", titulo="AI Engineer") -> Job:
    return Job(url="https://x.com/jobs/1", title=titulo, company="ACME",
               source="linkedin", description=descripcion[:3000],
               descripcion_completa=completa or descripcion)


def _perfil(idioma=None):
    return {"filters": {"language": idioma if idioma is not None else dict(SIN_INGLES)}}


# --- el requisito al final de un texto largo ----------------------------------

def test_el_requisito_al_final_de_un_aviso_largo_se_detecta():
    """El caso que se pasó: el requisito cae después del corte de 3.000."""
    texto = CUERPO_ES * 15 + "Requisitos excluyentes: inglés avanzado para hablar con clientes."
    assert len(texto) > 3000
    job = _aviso(texto)
    assert "ingles avanzado" not in job.description.lower().replace("é", "e")
    motivo = pide_ingles_sin_puntuar(job, SIN_INGLES)
    assert "pide inglés" in motivo


def test_la_segunda_capa_tambien_lee_el_aviso_entero():
    """`passes_language` corre después del modelo: si el modelo no lo vio
    (vio sólo los primeros 2.500 caracteres), la red determinista sí."""
    texto = CUERPO_ES * 15 + "Must have: fluent English, C1."
    ok, motivo = passes_language(_aviso(texto), SIN_INGLES)
    assert not ok and "pide inglés" in motivo


def test_linkedin_guarda_el_texto_entero_en_memoria_y_no_en_el_historial():
    texto = CUERPO_ES * 15 + "Inglés C1 excluyente."
    fila = pd.Series({"job_url": "https://www.linkedin.com/jobs/view/123",
                      "title": "AI Engineer", "company": "ACME",
                      "location": "Argentina", "description": texto})
    fuente = LinkedInJobsSource({"type": "linkedin"}, {"name": "test", "keywords": ["x"]})
    job = fuente._to_job(fila)
    assert len(job.description) == 3000
    assert job.descripcion_completa.endswith("Inglés C1 excluyente.")
    # 6 MB pesa el historial con la descripción recortada: el texto entero no
    # se guarda.
    assert "descripcion_completa" not in job.to_dict()
    assert Job.from_dict(job.to_dict()).descripcion_completa == ""


# --- el idioma del aviso ------------------------------------------------------

def test_un_aviso_escrito_en_ingles_se_descarta_sin_puntuar():
    assert pide_ingles_sin_puntuar(_aviso(CUERPO_EN * 2), SIN_INGLES) == \
        "el aviso está escrito en inglés"


def test_un_aviso_en_castellano_con_mucha_jerga_en_ingles_pasa():
    assert idioma_del_texto(CUERPO_ES * 2) == "es"
    assert pide_ingles_sin_puntuar(_aviso(CUERPO_ES * 2), SIN_INGLES) == ""


def test_un_aviso_bilingue_no_se_descarta():
    """Mitad en cada idioma: no hay una diferencia clara y decide el modelo."""
    assert idioma_del_texto(CUERPO_ES + CUERPO_EN) == ""


def test_un_texto_corto_no_alcanza_para_opinar():
    """Los snippets de google_posts son de dos renglones: ahí no se opina."""
    assert idioma_del_texto("We are hiring an AI Engineer to join the team.") == ""


# --- lo que no tiene que descartar --------------------------------------------

def test_el_ingles_deseable_no_descarta():
    texto = CUERPO_ES * 2 + "Inglés avanzado deseable, no excluyente."
    assert pide_ingles_sin_puntuar(_aviso(texto), SIN_INGLES) == ""


def test_con_el_ingles_permitido_no_descarta_nada():
    con_ingles = {**SIN_INGLES, "allow_english": True}
    assert pide_ingles_sin_puntuar(_aviso(CUERPO_EN * 2), con_ingles) == ""


def test_sin_leer_la_descripcion_no_descarta_nada():
    """`scan_description: false` apaga la lectura del texto, toda."""
    apagado = {**SIN_INGLES, "scan_description": False}
    assert pide_ingles_sin_puntuar(_aviso(CUERPO_EN * 2), apagado) == ""


def test_sin_texto_completo_usa_la_descripcion():
    """Las fuentes que no cortan (google_posts, rrhh) no llenan el texto entero."""
    job = Job(url="https://x.com/1", title="AI Engineer", description=CUERPO_EN * 2)
    assert pide_ingles_sin_puntuar(job, SIN_INGLES) == "el aviso está escrito en inglés"


# --- en el motor ---------------------------------------------------------------

def test_el_prefiltro_saca_las_de_ingles_y_deja_las_demas():
    ingles, castellano = _aviso(CUERPO_EN * 2), _aviso(CUERPO_ES * 2)
    castellano.url = "https://x.com/jobs/2"
    quedan, fuera = descartar_antes_de_puntuar([ingles, castellano], _perfil())
    assert quedan == [castellano]
    assert fuera == [(ingles, "el aviso está escrito en inglés")]


@pytest.fixture
def sin_llm(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for var in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_la_corrida_no_puntua_lo_que_pide_ingles(sin_llm, monkeypatch):
    ingles, castellano = _aviso(CUERPO_EN * 2), _aviso(CUERPO_ES * 2)
    castellano.url = "https://x.com/jobs/2"
    monkeypatch.setattr(engine, "collect", lambda sources, result: [ingles, castellano])
    perfil = {"name": "test", "min_score": 0, "cv_path": "resume/x.md",
              "llm": {"provider": "gemini"}, "sources": [],
              "notifiers": [{"type": "console", "enabled": True}],
              "filters": {"language": dict(SIN_INGLES)}}
    result = engine.run(perfil, dry_run=True)
    assert (result.fetched, result.new, result.scored) == (2, 1, 1)
