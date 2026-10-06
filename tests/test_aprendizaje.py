"""Que el sistema aprenda de lo que marcás, y los dos filtros que salieron de ahí.

El 17/9/2026 Isaías preguntó por qué el sistema no aprendía. No aprendía: 113
descartes guardados con su motivo y el modelo que puntúa no leía ninguno. Lo
que más se repetía eran dos cosas que ningún filtro sacaba:

* **Posteos que no son ofertas** (10 descartes, todos de `google_posts`):
  LinkedIn hablando de AI Engineering, o de baloncesto, sin buscar a nadie.
* **Ofertas que exigen Java o .NET** y pasaban porque además pedían React. El
  filtro de títulos no las veía: la tecnología estaba en la descripción.
"""

import json

from vacantia import engine, scoring
from vacantia.aprendizaje import MAX_DESCARTADAS, decisiones_para_el_prompt
from vacantia.filters import apply_filters, passes_offer, passes_tech
from vacantia.models import Job
from vacantia.ui import data

from tests.test_ui import HOY_ISO, _con_historial, get, post, sitio  # noqa: F401


def marcada(titulo, aplicado, cuando="2026-09-10T10:00:00+00:00", **extra):
    return {"url": f"https://e/{titulo}", "title": titulo, "company": "ACME",
            "aplicado": aplicado, "fecha_feedback": cuando,
            "description": f"Texto del aviso {titulo}", **extra}


# --- qué decisiones le llegan al modelo ---------------------------------------

def test_sin_nada_marcado_no_hay_bloque():
    assert decisiones_para_el_prompt([]) == ""
    assert decisiones_para_el_prompt([{"url": "https://e/1", "title": "Sin marcar"}]) == ""


def test_entran_los_descartes_que_dicen_algo_del_puesto():
    bloque = decisiones_para_el_prompt([
        marcada("Posteo", False, motivo_clave="no_es_oferta"),
        marcada("Backend Java", False, motivo_clave="tecnologias"),
        marcada("Libre", False, motivo_descarte="Es de call center, no de desarrollo"),
        marcada("Aplicada", True),
    ])
    assert "REJECTED:" in bloque and "APPLIED:" in bloque
    assert "No es una oferta de trabajo" in bloque
    assert "Pide tecnologías con las que no trabajo" in bloque
    assert "Es de call center, no de desarrollo" in bloque
    assert '"Aplicada"' in bloque


def test_no_entran_ingles_presencial_ni_el_caso_especial():
    """Inglés y presencial ya los sacan los filtros, mejor y sin gastar prompt.
    El caso especial la persona pidió que no enseñe. Incluye los viejos, escritos
    a mano antes del desplegable ("Estaba en ingles...")."""
    bloque = decisiones_para_el_prompt([
        marcada("Ingles", False, motivo_descarte="Estaba en ingles, osea que necesito ingles"),
        marcada("Presencial", False, motivo_clave="presencial"),
        marcada("Especial", False, motivo_descarte="-"),
    ])
    assert bloque == ""


def test_van_las_mas_recientes_y_con_tope():
    """Cada ejemplo viaja en cada lote: sin tope, 113 descartes serían ~10.000
    tokens por lote."""
    muchas = [marcada(f"Puesto {i:03d}", False, cuando=f"2026-09-{1 + i % 28:02d}T{i % 24:02d}:00:00+00:00",
                      motivo_clave="no_mi_puesto") for i in range(40)]
    bloque = decisiones_para_el_prompt(muchas)
    assert bloque.count("| reason:") == MAX_DESCARTADAS
    la_ultima = max(muchas, key=lambda h: h["fecha_feedback"])["title"]
    assert la_ultima in bloque


def test_un_aviso_republicado_cuenta_una_sola_vez():
    bloque = decisiones_para_el_prompt([
        marcada("Engineering Manager", False, motivo_clave="tecnologias"),
        {**marcada("Engineering Manager", False, motivo_clave="tecnologias"),
         "url": "https://e/otra-copia"},
    ])
    assert bloque.count('"Engineering Manager"') == 1


def test_el_bloque_llega_al_prompt(monkeypatch):
    capturas = []
    monkeypatch.setattr(scoring, "chat_with_llm",
                        lambda cfg, messages, **_: capturas.append(messages[0]["content"])
                        or '[{"job_number": 1, "score": 50}]')
    bloque = decisiones_para_el_prompt([marcada("Posteo", False, motivo_clave="no_es_oferta")])
    scoring._score_batch_with_llm([Job(url="https://e/1", title="Dev")],
                                  [{"id": "principal", "texto": "CV"}], {}, 60, bloque)
    assert "PAST DECISIONS" in capturas[-1]
    assert capturas[-1].index("PAST DECISIONS") < capturas[-1].index("JOBS TO SCORE")


def test_la_corrida_le_pasa_al_scoring_lo_que_marcaste(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state" / "test").mkdir(parents=True)
    (tmp_path / "state" / "test" / "job_history.json").write_text(
        json.dumps([marcada("Posteo de opinión", False, motivo_clave="no_es_oferta")]),
        encoding="utf-8")
    (tmp_path / "cv.md").write_text("# CV\nPython", encoding="utf-8")

    recibido = {}

    def score_falso(jobs, cvs, profile, decisiones=""):
        recibido["decisiones"] = decisiones
        return jobs

    monkeypatch.setattr(engine, "collect",
                        lambda sources, result: [Job(url="https://e/nueva", title="Dev")])
    monkeypatch.setattr(engine, "score_jobs", score_falso)
    engine.run({"name": "test", "cv_path": "cv.md", "min_score": 0,
                "sources": [], "notifiers": []}, dry_run=True)
    assert "Posteo de opinión" in recibido["decisiones"]


# --- lo que el modelo contesta -------------------------------------------------

def _puntuar(monkeypatch, respuesta, profile=None):
    capturas = []
    monkeypatch.setattr(scoring, "chat_with_llm",
                        lambda cfg, messages, **_: capturas.append(messages[0]["content"])
                        or respuesta)
    job = Job(url="https://e/1", title="Dev", description="texto")
    scoring._score_batch_with_llm([job], [{"id": "principal", "texto": "CV"}],
                                  profile or {}, 60)
    return job, capturas[-1]


def test_un_posteo_que_no_es_oferta_queda_en_cero_aunque_el_modelo_lo_puntue(monkeypatch):
    """El prompt pide 0, pero no se confía en que lo cumpla: con 70 llegaba al
    Telegram."""
    job, _ = _puntuar(monkeypatch, '[{"job_number": 1, "score": 70, '
                                   '"worth_applying": true, "is_job_offer": false}]')
    assert (job.score, job.worth_applying, job.is_job_offer) == (0, False, False)


def test_la_tecnologia_exigida_se_guarda(monkeypatch):
    job, _ = _puntuar(monkeypatch, '[{"job_number": 1, "score": 30, '
                                   '"is_job_offer": true, "unwanted_tech": "Java, .NET"}]')
    assert job.unwanted_tech == "Java, .NET" and job.is_job_offer is True


def test_sin_juicio_del_modelo_no_se_inventa_nada(monkeypatch):
    job, _ = _puntuar(monkeypatch, '[{"job_number": 1, "score": 80, "unwanted_tech": "N/A"}]')
    assert job.is_job_offer is None and job.unwanted_tech == ""


def test_el_modelo_ve_las_tecnologias_que_no_usas(monkeypatch):
    perfil = {"filters": {"tecnologias_que_no_uso": [".NET", "Java", "C#"]}}
    _, prompt = _puntuar(monkeypatch, '[{"job_number": 1, "score": 1}]', perfil)
    assert "- DOES NOT USE (technologies): .NET, Java, C#" in prompt


def test_sin_lista_el_perfil_del_candidato_no_cambia():
    assert "DOES NOT USE" not in scoring.build_candidate_profile({"keywords": ["Python"]})


# --- los filtros ---------------------------------------------------------------

FILTROS = {"tecnologias_que_no_uso": [".NET", "Java", "C#"]}


def test_no_es_oferta_se_filtra_y_sin_juicio_pasa():
    assert passes_offer(Job(url="u", title="t", is_job_offer=False))[0] is False
    assert passes_offer(Job(url="u", title="t", is_job_offer=None))[0] is True
    assert passes_offer(Job(url="u", title="t", is_job_offer=True))[0] is True


def test_java_o_net_sin_alternativa_se_filtra():
    ok, why = passes_tech(Job(url="u", title="Full Stack", unwanted_tech="Java, .NET"), FILTROS)
    assert ok is False and "Java" in why and ".NET" in why


def test_sacar_la_tecnologia_de_la_lista_devuelve_la_oferta():
    """Se calcula al leer: el modelo dijo "Java", pero si Java ya no está en tu
    lista, la oferta vuelve sola."""
    job = Job(url="u", title="t", unwanted_tech="Java")
    assert passes_tech(job, FILTROS)[0] is False
    assert passes_tech(job, {"tecnologias_que_no_uso": [".NET"]})[0] is True
    assert passes_tech(job, {})[0] is True


def test_las_mayusculas_y_la_lista_como_texto_no_importan():
    job = Job(url="u", title="t", unwanted_tech="JAVA")
    assert passes_tech(job, {"tecnologias_que_no_uso": ".net, java"})[0] is False


def test_la_corrida_no_avisa_ni_posteos_ni_java():
    jobs = [Job(url="https://e/1", title="Posteo", is_job_offer=False),
            Job(url="https://e/2", title="Backend", unwanted_tech="Java"),
            Job(url="https://e/3", title="Python o Java", unwanted_tech="")]
    quedan, stats = apply_filters(jobs, {"filters": FILTROS})
    assert [j.title for j in quedan] == ["Python o Java"]
    assert stats.by_reason["no_es_oferta"] == 1 and stats.by_reason["tecnologias"] == 1


def test_un_perfil_sin_filtros_igual_saca_lo_que_no_es_oferta():
    quedan, _ = apply_filters([Job(url="u", title="t", is_job_offer=False)], {})
    assert quedan == []


# --- la pantalla -----------------------------------------------------------------

def test_no_aparecen_en_sin_marcar_y_se_ven_en_filtradas(sitio):
    base, tmp = sitio
    ruta = tmp / "profiles" / "test.json"
    perfil = json.loads(ruta.read_text(encoding="utf-8"))
    perfil.setdefault("filters", {})["tecnologias_que_no_uso"] = ["Java"]
    ruta.write_text(json.dumps(perfil), encoding="utf-8")
    base_oferta = {"company": "ACME", "aplicado": None, "score": 70, "found_at": HOY_ISO,
                   "posting_language": "es", "country": "Argentina", "work_mode": "remote"}
    _con_historial(tmp, [
        {**base_oferta, "url": "https://e/posteo", "title": "Tu hijo y el baloncesto",
         "is_job_offer": False},
        {**base_oferta, "url": "https://e/java", "title": "Backend Java", "unwanted_tech": "Java"},
        {**base_oferta, "url": "https://e/buena", "title": "Full Stack Python"},
    ])
    _, pendientes, _ = get(base, "/trabajos?perfil=test&ver=pendientes")
    assert "Full Stack Python" in pendientes
    assert "baloncesto" not in pendientes and "Backend Java" not in pendientes

    _, filtradas, _ = get(base, "/trabajos?perfil=test&ver=filtradas")
    assert "Pide tecnologías que no usás, sin alternativa" in filtradas
    assert data.motivos_del_sistema(
        {**base_oferta, "url": "u", "title": "t", "is_job_offer": False}, {}
    )[0][0] == "no_es_oferta"


def test_las_tecnologias_se_editan_desde_mi_perfil(sitio):
    base, tmp = sitio
    post(base, "/datos", {
        "perfil": "test", "keywords": "Python", "pais": "Argentina", "ciudad": "",
        "max_english_level": "A2", "excluir_titulos": "",
        "tecnologias_que_no_uso": "Java, .NET , C#",
        "empresas": "", "rrhh": "", "cand_name": "Test", "cand_headline": "",
        "cand_profile": "", "cand_seeking": "", "cand_not_suitable": "",
    })
    perfil = json.loads((tmp / "profiles" / "test.json").read_text(encoding="utf-8"))
    assert perfil["filters"]["tecnologias_que_no_uso"] == ["Java", ".NET", "C#"]
    _, html, _ = get(base, "/datos?perfil=test")
    assert 'name="tecnologias_que_no_uso"' in html and "Java, .NET, C#" in html
