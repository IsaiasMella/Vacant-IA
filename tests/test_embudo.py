"""El embudo por fuente y el remoto abierto a LATAM.

El embudo existe porque, al medir a mano el 16/10/2026, el filtro de títulos
tiraba los "Senior Backend Python" que Isaías buscaba sin que nada lo mostrara:
lo descartado antes del modelo quedaba en el log sin decir de qué fuente venía.
"""

import json

import pytest

from vacantia import engine
from vacantia import state as state_mod
from vacantia.embudo import ARCHIVO_DESCARTADAS, ARCHIVO_EMBUDO, Embudo, leer_embudo
from vacantia.filters import abierta_a_latam, descartar_antes_de_puntuar, passes_place
from vacantia.models import Job
from vacantia.notifiers.base import Notifier
from vacantia.sources.base import Source

PERFIL = {
    "name": "embudo",
    "min_score": 0,
    "keywords": ["Python"],
    "registro_embudo": True,
    "filters": {
        "location": {"country": "Argentina"},
        "work_modes": ["remote"],
        "language": {"allow_english": True},
        "excluir_titulos": ["Java"],
    },
    "llm": {"provider": "gemini"},
    "sources": [],
    "notifiers": [],
}


class FuenteFalsa(Source):
    name = "falsa"

    def __init__(self, jobs, descartes=()):
        super().__init__({}, PERFIL)
        self._jobs = jobs
        for url, motivo in descartes:
            self.descartar(url, "viejo", motivo)

    def fetch(self):
        return list(self._jobs)


class Telegram(Notifier):
    name = "telegram"

    def send(self, jobs, notes=None) -> bool:
        return True


def job(url, title="AI Engineer Python", **kw):
    return Job(url=url, title=title, company=kw.pop("company", "ACME"),
               source=kw.pop("source", "falsa"), description="Python remoto", **kw)


@pytest.fixture
def corrida(monkeypatch, tmp_path):
    """Corre el motor sin red ni LLM, con el estado en una carpeta temporal."""
    for var in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(state_mod, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(engine, "_usable_notifiers", lambda p, r: [Telegram({}, p)])
    cv = tmp_path / "cv.md"
    cv.write_text("AI Engineer. Python, FastAPI, RAG.", encoding="utf-8")

    def correr(fuente, dry_run=False, **cambios):
        perfil = {**PERFIL, "cv_path": str(cv), **cambios}
        monkeypatch.setattr(engine, "_usable_sources", lambda p, r: [fuente])
        engine.run(perfil, dry_run=dry_run)
        return tmp_path / perfil["name"]

    return correr


def test_las_etapas_cierran_como_sumas(corrida):
    fuente = FuenteFalsa(
        [job("https://x/1"), job("https://x/2", title="Senior Java Developer"),
         job("https://x/3", title="Backend Python"),
         job("https://x/3", title="Backend Python")],   # la última, repetida en el lote
        descartes=[("https://x/viejo", "publicado hace más de 7 días")],
    )
    carpeta = corrida(fuente)
    [linea] = leer_embudo(carpeta)
    c = linea["fuentes"]["falsa"]

    assert c["descartada_en_fuente"] == 1
    assert c["trajo"] == 4
    assert c["trajo"] == sum(c.get(e, 0) for e in (
        "ya_vista", "duplicada", "cubierta", "antes_del_llm", "diferida", "puntuada"))
    assert c["antes_del_llm"] == 1 and c["ya_vista"] == 1 and c["puntuada"] == 2
    assert c["supera_umbral"] == c.get("avisada", 0) + c.get("fuera_del_top", 0) \
        + c.get("sin_avisar", 0)
    assert linea["dry_run"] is False


def test_las_descartadas_se_anotan_una_sola_vez(corrida):
    """Lo descartado antes del modelo no se marca como visto y vuelve en cada
    corrida: anotarlo cada vez llenaba el archivo de la misma oferta."""
    def fuente():
        return FuenteFalsa([job("https://x/j", title="Java Developer")],
                           descartes=[("https://x/viejo", "publicado hace más de 7 días")])

    carpeta = corrida(fuente())
    corrida(fuente())
    lineas = (carpeta / ARCHIVO_DESCARTADAS).read_text(encoding="utf-8").splitlines()
    descartes = [json.loads(l) for l in lineas]
    assert sorted((d["etapa"], d["url"]) for d in descartes) == [
        ("antes_del_llm", "https://x/j"),
        ("descartada_en_fuente", "https://x/viejo"),
    ]
    assert all(d["fuente"] == "falsa" and d["motivo"] for d in descartes)
    assert len(leer_embudo(carpeta)) == 2


def test_los_avisos_de_indeed_no_se_pisan_entre_si(tmp_path):
    """En Indeed el id del aviso va en el query string: cortándolo, 23 avisos
    distintos quedaban anotados como uno solo."""
    e = Embudo("x")
    for jk in ("aaa111", "bbb222"):
        e.descartar("indeed", "descartada_en_fuente", "sin detalle",
                    f"https://ar.indeed.com/viewjob?jk={jk}")
    assert e.guardar(tmp_path) == 2


def test_lo_avisado_queda_con_notificada_en(corrida):
    carpeta = corrida(FuenteFalsa([job("https://x/1")]))
    historial = json.loads((carpeta / "job_history.json").read_text(encoding="utf-8"))
    assert historial[0]["notificada_en"]
    assert leer_embudo(carpeta)[0]["fuentes"]["falsa"]["avisada"] == 1


def test_en_dry_run_se_anota_marcado_y_no_se_avisa(corrida):
    carpeta = corrida(FuenteFalsa([job("https://x/1")]), dry_run=True)
    [linea] = leer_embudo(carpeta)
    assert linea["dry_run"] is True
    assert linea["fuentes"]["falsa"]["sin_avisar"] == 1
    assert not (carpeta / "job_history.json").exists()


def test_apagado_por_defecto_no_escribe_nada(corrida):
    carpeta = corrida(FuenteFalsa([job("https://x/1")]),
                      name="sin_embudo", registro_embudo=False)
    assert not (carpeta / ARCHIVO_EMBUDO).exists()
    assert not (carpeta / ARCHIVO_DESCARTADAS).exists()
    historial = json.loads((carpeta / "job_history.json").read_text(encoding="utf-8"))
    assert "notificada_en" not in historial[0]


def test_la_duplicada_entre_fuentes_se_anota_con_la_que_gano(tmp_path):
    e = Embudo("x")
    st = state_mod.State("x", root=tmp_path)
    linkedin = Job(url="https://l/1", title="AI Engineer", company="ACME",
                   source="linkedin", work_mode="remote", description="largo" * 50)
    careers = Job(url="https://c/1", title="AI Engineer", company="ACME", source="careers")
    st.filter_new([careers, linkedin])
    [(perdio, etapa, motivo)] = st.ultimos_descartes
    assert perdio.source == "careers" and etapa == "duplicada" and "linkedin" in motivo
    assert e.resumen()["fuentes"] == {}


# --- remoto abierto a LATAM -------------------------------------------------

BB = {"country": "Argentina", "city": "Bahía Blanca"}
LATAM = {**BB, "remoto_abierto_a_latam": True}


def remoto(**kw) -> Job:
    return Job(**{"url": "https://x/1", "title": "LLM Engineer", "work_mode": "remote",
                  "country": "Estados Unidos", **kw})


def test_remoto_de_afuera_abierto_a_latam_entra_con_la_opcion():
    j = remoto(description="Fully remote, hiring contractors across LATAM. Paid in USD.")
    assert passes_place(j, LATAM, ["remote"])[0]
    assert not passes_place(j, BB, ["remote"])[0], "sin la opción sigue afuera"


def test_remoto_abierto_al_mundo_tambien_entra():
    j = remoto(description="We hire from anywhere in the world.")
    assert passes_place(j, LATAM, ["remote"])[0]


def test_remoto_para_colombia_sigue_afuera_aunque_este_la_opcion():
    """La regla de país existe para esto: un remoto de Colombia suele ser
    remoto PARA Colombia."""
    j = remoto(country="Colombia", description="Remoto para residentes en Colombia.")
    ok, why, etiqueta = passes_place(j, LATAM, ["remote"])
    assert not ok and etiqueta == "location"


def test_la_opcion_no_salva_a_un_presencial_de_afuera():
    j = remoto(work_mode="onsite", city="Austin", description="LATAM team")
    assert not passes_place(j, LATAM, ["remote"])[0]


def test_anywhere_acotado_a_un_pais_no_cuenta():
    assert not abierta_a_latam(remoto(description="Work from anywhere in the US."))
    assert abierta_a_latam(remoto(location="Remote, LATAM")) == "latam"
    assert abierta_a_latam(remoto(description="Trabajo remoto desde Latinoamérica"))


def test_el_prefiltro_de_pais_respeta_la_opcion():
    perfil = {"filters": {"location": LATAM}}
    j = Job(url="https://x/1", title="AI Engineer", country="Mexico",
            description="Remote position open to Latin America")
    quedan, fuera = descartar_antes_de_puntuar([j], perfil)
    assert quedan == [j] and not fuera
    quedan, fuera = descartar_antes_de_puntuar([j], {"filters": {"location": BB}})
    assert not quedan and "Mexico" in fuera[0][1]
