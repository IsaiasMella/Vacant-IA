"""El nivel mínimo, el botón de archivar a la vista y el Enter que aplicaba.

El 25/9/2026 Isaías dijo que el sistema seguía sin aprender: le llegaban
puestos Semi Senior y ofertas que ni quería descartar. Mirando su historial
salieron tres cosas:

* **El nivel no lo sabía nadie.** "No busco posiciones que no sean SR" estaba
  escrito en un descarte, y como ejemplo suelto en el prompt no alcanzaba.
* **"Semi senior no acepto" quedó guardada como aplicada.** Enter en el campo
  del motivo manda el formulario con el primer botón, que es "Apliqué": el
  sistema aprendió justo al revés.
* **Archivar estaba escondido** en el menú de tres puntos, y para sacar de la
  lista lo que no quería ver usaba "Caso especial", que no enseña nada.
"""

import json
import re

from vacantia import scoring
from vacantia.aprendizaje import decisiones_para_el_prompt
from vacantia.filters import apply_filters, nivel_del_titulo, passes_seniority
from vacantia.models import Job
from vacantia.state import State
from vacantia.ui import data

from tests.test_aprendizaje import _puntuar, marcada
from tests.test_ui import HOY_ISO, _con_historial, get, post, sitio  # noqa: F401

SENIOR = {"seniority_minima": "senior"}


# --- el nivel del aviso ----------------------------------------------------------

def test_el_titulo_dice_el_nivel():
    assert nivel_del_titulo("Semi-Senior Full-Stack Developer") == "semi-senior"
    assert nivel_del_titulo("Full Stack SSR - Payment Experience") == "semi-senior"
    assert nivel_del_titulo("Desarrollador Semi Senior") == "semi-senior"
    assert nivel_del_titulo("Sr. Software Engineer") == "senior"
    assert nivel_del_titulo("Buscamos Practicante de Investigaciones") == "junior"
    assert nivel_del_titulo("Tech Lead") == "lead"
    assert nivel_del_titulo("Product Engineer") == ""


def test_si_acepta_tu_nivel_entra_aunque_nombre_otro():
    """"SSr/Sr" nombra semi senior, pero también te acepta a vos."""
    assert nivel_del_titulo("Desarrollador SSr/Sr Python") == "senior"
    assert nivel_del_titulo("Semi Senior / Senior Backend") == "senior"


def test_semi_senior_sale_si_buscas_senior():
    ok, why = passes_seniority(Job(url="u", title="Desarrollador Semi Senior"), SENIOR)
    assert ok is False and "Semi Senior" in why


def test_sin_minimo_o_sin_nivel_pasa():
    assert passes_seniority(Job(url="u", title="Desarrollador Semi Senior"), {})[0]
    assert passes_seniority(Job(url="u", title="Product Engineer"), SENIOR)[0]


def test_sin_nivel_en_el_titulo_decide_el_modelo():
    job = Job(url="u", title="Product Engineer", seniority="semi-senior")
    assert passes_seniority(job, SENIOR)[0] is False
    assert passes_seniority(Job(url="u", title="Product Engineer", seniority="lead"),
                            SENIOR)[0] is True


def test_la_corrida_no_avisa_las_de_menor_nivel():
    jobs = [Job(url="https://e/1", title="Semi Senior Dev"),
            Job(url="https://e/2", title="Senior Dev")]
    quedan, stats = apply_filters(jobs, {"filters": SENIOR})
    assert [j.title for j in quedan] == ["Senior Dev"]
    assert stats.by_reason["nivel"] == 1


def test_el_modelo_sabe_tu_minimo_y_devuelve_el_nivel(monkeypatch):
    job, prompt = _puntuar(monkeypatch, '[{"job_number": 1, "score": 30, '
                                        '"seniority": "Semi-Senior"}]',
                           {"filters": SENIOR})
    assert "- MINIMUM SENIORITY: senior" in prompt
    assert job.seniority == "semi-senior"


def test_sin_minimo_el_perfil_del_candidato_no_cambia():
    assert "SENIORITY" not in scoring.build_candidate_profile({"keywords": ["Python"]})


def test_las_de_menor_nivel_salen_de_sin_marcar(sitio):
    base, tmp = sitio
    ruta = tmp / "profiles" / "test.json"
    perfil = json.loads(ruta.read_text(encoding="utf-8"))
    perfil["filters"].update(SENIOR)
    ruta.write_text(json.dumps(perfil), encoding="utf-8")
    comun = {"company": "ACME", "aplicado": None, "score": 80, "found_at": HOY_ISO,
             "posting_language": "es", "country": "Argentina", "work_mode": "remote"}
    _con_historial(tmp, [
        {**comun, "url": "https://e/ssr", "title": "Full Stack SSR"},
        {**comun, "url": "https://e/sr", "title": "Full Stack Sr"},
    ])
    _, pendientes, _ = get(base, "/trabajos?perfil=test&ver=pendientes")
    assert "Full Stack Sr" in pendientes and "Full Stack SSR" not in pendientes
    _, filtradas, _ = get(base, "/trabajos?perfil=test&ver=filtradas")
    assert "Es para un nivel menor al que buscás" in filtradas
    assert data.motivo_del_sistema({**comun, "url": "u", "title": "Jr Dev"},
                                   SENIOR)[0] == "nivel"


def test_el_nivel_se_elige_en_mi_perfil(sitio):
    base, tmp = sitio
    post(base, "/datos", {
        "perfil": "test", "keywords": "Python", "pais": "Argentina", "ciudad": "",
        "max_english_level": "A2", "excluir_titulos": "", "seniority_minima": "senior",
        "empresas": "", "rrhh": "", "cand_name": "Test", "cand_headline": "",
        "cand_profile": "", "cand_seeking": "", "cand_not_suitable": "",
    })
    perfil = json.loads((tmp / "profiles" / "test.json").read_text(encoding="utf-8"))
    assert perfil["filters"]["seniority_minima"] == "senior"
    _, html, _ = get(base, "/datos?perfil=test")
    assert '<option value="senior" selected>' in html


# --- el Enter en el campo del motivo ---------------------------------------------

def test_apliqué_con_un_motivo_escrito_se_guarda_como_descarte(sitio):
    """Es lo que manda el navegador cuando apretás Enter en el campo del motivo."""
    base, _ = sitio
    post(base, "/feedback", {"perfil": "test", "ver": "pendientes",
                             "url": "https://empresa.com/jobs/1", "aplicado": "si",
                             "motivo": "semi senior no acepto"})
    guardada = {h["url"]: h for h in State("test").load_history()}["https://empresa.com/jobs/1"]
    assert guardada["aplicado"] is False
    assert guardada["motivo_descarte"] == "semi senior no acepto"


def test_el_enter_del_motivo_aprieta_descartar():
    from vacantia.ui.render import JS
    assert "input[name=motivo]" in JS and "button[value=no]" in JS


# --- lo que ve el modelo de tus descartes --------------------------------------

def test_el_ejemplo_lleva_el_stack():
    """Sin el stack, "pide tecnologías con las que no trabajo" no decía cuáles."""
    bloque = decisiones_para_el_prompt([
        marcada("Software Engineer Backend", False, motivo_clave="tecnologias",
                stack="Go, Kafka, gRPC"),
    ])
    assert 'stack: "Go, Kafka, gRPC"' in bloque


# --- archivar a la vista ---------------------------------------------------------

def test_archivar_se_ve_sin_abrir_el_menu():
    from vacantia.ui.render import _tarjeta

    html = _tarjeta({"url": "https://x/1", "title": "T", "score": 70}, "ana", "pendientes")
    a_la_vista = re.sub(r"<details.*?</details>", "", html, flags=re.S)
    assert re.search(r'<button class="fantasma" name="archivar" value="1"'
                     r'[^>]*formaction="/archivar"[^>]*>Archivar</button>', a_la_vista)
