"""Los puestos se buscan; las habilidades no.

Antes era una sola lista. "Python", "React" y "FastAPI" se buscaban en los
portales como si fueran puestos: "React" en LinkedIn trae frontend, que después
se descarta por título, y cada habilidad ocupaba uno de los 3 lugares por
corrida que tiene LinkedIn. Desde el 19/11/2026 van separadas: los puestos
(`keywords` del perfil y `palabras_clave` de cada CV) son lo que se busca, y las
habilidades (`habilidades`) afinan la búsqueda de Jobs y le dicen al modelo qué
sabe hacer la persona.
"""

import json

from vacantia import config, scoring
from vacantia.ui import data, formulario, linkedin_urls

from tests.test_ui import get, post, sitio  # noqa: F401

PERFIL = {
    "name": "test",
    "keywords": ["Full Stack", "Full-stack"],
    "habilidades": ["Python", "FastAPI"],
    "cvs": [
        {"id": "ai", "nombre": "AI", "path": "resume/ai.md",
         "palabras_clave": ["AI Engineer"], "habilidades": ["RAG", "python"]},
        {"id": "fs", "nombre": "Full Stack", "path": "resume/fs.md",
         "palabras_clave": ["Full Stack Developer"], "habilidades": ["React", "Next.js"]},
    ],
}


# --- qué se busca y qué no ------------------------------------------------------

def test_las_habilidades_no_se_buscan_en_los_portales():
    terminos = config.terminos_de_busqueda(PERFIL)
    assert terminos == ["Full Stack", "AI Engineer", "Full Stack Developer"]
    assert not {"Python", "FastAPI", "RAG", "React", "Next.js"} & set(terminos)


def test_full_stack_con_y_sin_guion_es_una_sola_busqueda():
    """Estaban las dos en el perfil de Isaías, ocupando dos lugares de la rotación."""
    assert config.terminos_de_busqueda({"keywords": ["Full Stack", "full-stack"]}) == \
        ["Full Stack"]


def test_las_habilidades_juntan_las_del_perfil_y_las_de_cada_cv_sin_repetir():
    assert config.habilidades_del_perfil(PERFIL) == \
        ["Python", "FastAPI", "RAG", "React", "Next.js"]


def test_un_perfil_viejo_sin_habilidades_sigue_andando():
    viejo = {"keywords": ["Python"], "cvs": [{"id": "a", "path": "r.md",
                                             "palabras_clave": ["AI Engineer"]}]}
    assert config.habilidades_del_perfil(viejo) == []
    assert config.cvs_del_perfil(viejo)[0]["habilidades"] == []
    assert config.terminos_de_busqueda(viejo) == ["Python", "AI Engineer"]


def test_el_constructor_ofrece_puestos_y_no_habilidades():
    assert linkedin_urls.puestos_de(PERFIL) == ["Full Stack", "AI Engineer",
                                                "Full Stack Developer"]
    assert linkedin_urls.habilidades_de(PERFIL) == "Python, FastAPI, RAG, React, Next.js"


def test_que_ademas_diga_precarga_solo_las_primeras_habilidades():
    """Con el CV entero son 25, y un OR de 25 tecnologías ya no filtra nada.
    Al modelo le siguen llegando todas."""
    muchas = {"keywords": ["AI Engineer"], "habilidades": [f"H{i}" for i in range(25)]}
    precargadas = linkedin_urls.habilidades_de(muchas).split(", ")
    assert precargadas == [f"H{i}" for i in range(linkedin_urls.MAX_HABILIDADES_PRECARGADAS)]
    assert "H24" in scoring.build_candidate_profile(muchas)


# --- el modelo y el triaje sí las usan ---------------------------------------------

def test_el_modelo_recibe_las_habilidades_aparte_de_los_puestos():
    prompt = scoring.build_candidate_profile(PERFIL)
    assert "- Keywords of interest: Full Stack, Full-stack" in prompt
    assert "- Skills: Python, FastAPI, RAG, React, Next.js" in prompt


def test_sin_habilidades_el_prompt_queda_como_antes():
    prompt = scoring.build_candidate_profile({"keywords": ["Python"]})
    assert "Skills" not in prompt


def test_el_triaje_cuenta_tambien_las_habilidades():
    """Un aviso que dice FastAPI pinta mejor que uno que no, aunque FastAPI no
    se busque en ningún portal."""
    palabras = scoring._palabras_del_triaje(PERFIL)
    assert "fastapi" in palabras and "full stack" in palabras


# --- Mi perfil --------------------------------------------------------------------

def test_mi_perfil_muestra_puestos_y_habilidades_por_separado(sitio):
    base, _ = sitio
    _, html, _ = get(base, "/datos?perfil=test")
    assert "Puestos a buscar" in html and 'name="habilidades"' in html
    assert "Puestos a buscar con este CV" in html
    assert 'name="cv_principal_habilidades"' in html


def test_guardar_mi_perfil_escribe_las_habilidades(sitio):
    base, _ = sitio
    post(base, "/datos", {"perfil": "test", "keywords": "AI Engineer",
                          "habilidades": "Python, FastAPI",
                          "cv_principal_palabras": "LLM Engineer",
                          "cv_principal_habilidades": "RAG, OpenAI"})
    perfil = data.leer_perfil("test")
    assert perfil["keywords"] == ["AI Engineer"]
    assert perfil["habilidades"] == ["Python", "FastAPI"]
    assert perfil["cvs"][0]["palabras_clave"] == ["LLM Engineer"]
    assert perfil["cvs"][0]["habilidades"] == ["RAG", "OpenAI"]


def test_guardar_otra_cosa_no_borra_las_habilidades_del_cv(sitio):
    """`fijar_cvs` rearma cada CV con los campos que conoce: si no conociera
    `habilidades`, guardar el nombre del CV las borraría."""
    base, tmp = sitio
    perfil = data.leer_perfil("test")
    data.fijar_cvs(perfil, [{**config.cvs_del_perfil(perfil)[0], "habilidades": ["RAG"]}])
    data.guardar_perfil("test", perfil)

    post(base, "/datos", {"perfil": "test", "cv_principal_nombre": "AI"})
    guardado = json.loads((tmp / "profiles" / "test.json").read_text(encoding="utf-8"))
    assert guardado["cvs"][0]["habilidades"] == ["RAG"]


def test_un_cv_nuevo_nace_sin_habilidades(sitio):
    nuevo = data.agregar_cv("test")
    cv = next(c for c in data.leer_perfil("test")["cvs"] if c["id"] == nuevo)
    assert cv["habilidades"] == []


def test_el_formulario_explica_por_que_no_van_las_habilidades():
    html = formulario.render_datos("ana", {"keywords": ["Python"]}, [])
    assert "Lo que sabés hacer va en Habilidades" in html


# --- "Que además diga" en Jobs ----------------------------------------------------

def _con_habilidades(*habilidades):
    perfil = data.leer_perfil("test")
    perfil["habilidades"] = list(habilidades)
    data.guardar_perfil("test", perfil)


def test_al_entrar_a_jobs_que_ademas_diga_trae_las_habilidades(sitio):
    base, _ = sitio
    _con_habilidades("Python", "FastAPI")
    _, html, _ = get(base, "/linkedin?perfil=test&tab=jobs")
    assert 'name="tambien" value="Python, FastAPI"' in html


def test_si_la_persona_lo_vacio_no_se_vuelve_a_llenar(sitio):
    base, _ = sitio
    _con_habilidades("Python", "FastAPI")
    _, html, _ = get(base, "/linkedin?perfil=test&tab=jobs&puesto=Python&tambien=")
    assert 'name="tambien" value=""' in html
    assert "AND" not in html.split('class="url-generada"')[1].split("</p>")[0]


def test_publicaciones_no_usa_las_habilidades(sitio):
    base, _ = sitio
    _con_habilidades("FastAPI")
    _, html, _ = get(base, "/linkedin?perfil=test")
    assert 'value="FastAPI"' not in html
