"""La clave de un aviso con el id en el query, y excluir_titulos después del modelo.

Medido el 16/10/2026: `Job.key` cortaba la URL en el `?`, y en Indeed el id va
ahí (`viewjob?jk=<id>`). Todos los avisos de Indeed eran la misma URL, y en cinco
semanas entró uno solo al historial.
"""

import json

from vacantia.embudo import Embudo
from vacantia.filters import apply_filters, passes_titulo
from vacantia.models import Job, clave_de_url
from vacantia.state import VERSION_CLAVES, State
from vacantia.ui.data import motivos_del_sistema


# --- la clave ---------------------------------------------------------------

def test_dos_avisos_de_indeed_tienen_claves_distintas():
    a = Job(url="https://ar.indeed.com/viewjob?jk=8e392070a5839baa", title="t")
    b = Job(url="https://ar.indeed.com/viewjob?jk=1234567890abcdef", title="t")
    assert a.key != b.key
    assert a.key == "https://ar.indeed.com/viewjob?jk=8e392070a5839baa"


def test_el_tracking_sigue_sin_cambiar_la_clave():
    """Lo que la clave cortaba a propósito: `utm`, `ref`, `trk` hacían pasar el
    mismo aviso por nuevo en cada corrida."""
    base = "https://career.globant.com/job/AI-Engineer/547157717"
    assert clave_de_url(f"{base}?ref=levels.fyi&src=") == clave_de_url(base + "/")
    assert clave_de_url("https://ar.indeed.com/viewjob?jk=ABC&from=serp&utm_x=1") \
        == "https://ar.indeed.com/viewjob?jk=abc"


def test_greenhouse_embebido_tambien_conserva_el_id():
    a = "https://empresa.com/jobs/abiertas?gh_jid=111"
    b = "https://empresa.com/jobs/abiertas?gh_jid=222&utm_source=x"
    assert clave_de_url(a) != clave_de_url(b)


def test_el_hash_de_rrhh_sigue_siendo_identidad():
    """Para `rrhh` el `#hash` separa una publicación de otra en la misma página."""
    assert clave_de_url("https://consultora.com/busquedas#aa11") \
        != clave_de_url("https://consultora.com/busquedas#bb22")


# --- la migración -----------------------------------------------------------

def _estado_viejo(tmp_path, historial):
    carpeta = tmp_path / "ana"
    carpeta.mkdir()
    (carpeta / "seen_jobs.json").write_text(json.dumps({
        "seen_keys": ["https://ar.indeed.com/viewjob", "https://x.com/jobs/1"],
        "seen_alt_keys": [], "last_run": None,
    }), encoding="utf-8")
    (carpeta / "job_history.json").write_text(json.dumps(historial), encoding="utf-8")
    return carpeta


def test_lo_que_ya_estaba_en_el_historial_no_vuelve_como_nuevo(tmp_path):
    vista = "https://ar.indeed.com/viewjob?jk=8e392070a5839baa"
    carpeta = _estado_viejo(tmp_path, [{"url": vista}, {"url": "https://x.com/jobs/1"}])

    st = State("ana", root=tmp_path)
    nuevas = st.filter_new([Job(url=vista, title="AI Engineer", source="indeed"),
                            Job(url="https://ar.indeed.com/viewjob?jk=ffff0000ffff0000",
                                title="Otro", source="indeed")])
    assert [j.url for j in nuevas] == ["https://ar.indeed.com/viewjob?jk=ffff0000ffff0000"]

    st.save([])
    guardado = json.loads((carpeta / "seen_jobs.json").read_text(encoding="utf-8"))
    assert guardado["version_claves"] == VERSION_CLAVES
    assert "https://ar.indeed.com/viewjob?jk=8e392070a5839baa" in guardado["seen_keys"]


def test_abrir_el_estado_no_escribe_nada(tmp_path):
    """La pantalla abre el estado de cualquier perfil sólo para mirarlo."""
    carpeta = _estado_viejo(tmp_path, [{"url": "https://ar.indeed.com/viewjob?jk=aa"}])
    antes = (carpeta / "seen_jobs.json").read_bytes()
    State("ana", root=tmp_path)
    assert (carpeta / "seen_jobs.json").read_bytes() == antes


def test_la_migracion_corre_una_sola_vez(tmp_path, monkeypatch):
    _estado_viejo(tmp_path, [{"url": "https://ar.indeed.com/viewjob?jk=aa"}])
    State("ana", root=tmp_path).save([])
    leidas = []
    monkeypatch.setattr(State, "load_history", lambda self: leidas.append(1) or [])
    State("ana", root=tmp_path)
    assert leidas == []


def test_un_perfil_nuevo_no_crea_su_carpeta(tmp_path):
    State("nuevo", root=tmp_path)
    assert not (tmp_path / "nuevo").exists()


def test_el_embudo_no_junta_avisos_de_indeed(tmp_path):
    e = Embudo("x")
    for jk in ("aaa111", "bbb222"):
        e.descartar("indeed", "descartada_en_fuente", "sin detalle",
                    f"https://ar.indeed.com/viewjob?jk={jk}&from=serp")
    assert e.guardar(tmp_path) == 2


# --- excluir_titulos con el título del modelo -------------------------------

FILTROS = {"excluir_titulos": ["Lead", "Machine Learning"]}


def test_el_titulo_del_modelo_tambien_se_filtra():
    """El título de la fuente era el comienzo del post; el puesto lo dijo el
    modelo al leerlo."""
    j = Job(url="https://x/1", title="Publicación de Fulana", source="google_posts",
            scored_title="TECH LEAD | SENIOR FULL STACK e AI ENGINEER", score=80)
    ok, why = passes_titulo(j, FILTROS)
    assert not ok and "Lead" in why

    quedan, stats = apply_filters([j], {"filters": FILTROS})
    assert quedan == [] and stats.by_reason["titulo"] == 1


def test_sin_terminos_excluidos_no_saca_nada():
    j = Job(url="https://x/1", title="AI Engineer", scored_title="Senior AI Engineer")
    assert passes_titulo(j, {})[0]
    assert passes_titulo(j, FILTROS)[0]


def test_la_pantalla_lo_muestra_como_filtrada():
    oferta = Job(url="https://x/1", title="Post", scored_title="Team Lead Python").to_dict()
    assert motivos_del_sistema(oferta, FILTROS)[0][0] == "titulo"
