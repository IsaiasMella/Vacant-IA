"""Las búsquedas sugeridas de LinkedIn URLs.

Salen de la investigación del 19/11/2026 (unas 1.000 ofertas de LinkedIn de los
últimos 30 días): en Jobs la búsqueda es por significado, y un título en
castellano trae los mismos avisos en inglés; en Publicaciones es por frase
exacta, y ahí el título en castellano sí trae posteos en castellano. Lo que se
fija acá son las reglas de LinkedIn que ya se aprendieron a los golpes: no pasar
de 110 caracteres en Publicaciones y un NOT por término.
"""

from urllib.parse import parse_qs, urlparse

from vacantia.ui import data, linkedin_urls
from vacantia.ui.linkedin_urls import (
    GATILLOS_ES, TOPE_KEYWORDS, que_entro_en, sugeridas_jobs, sugeridas_publicaciones,
)

from tests.test_ui import get, post, sitio  # noqa: F401

PUESTOS = ["AI Engineer", "Applied AI Engineer", "Forward Deployed Engineer",
           "LLM Engineer", "Python Developer", "Backend Python", "Full Stack Developer",
           "Ingeniero de IA", "Desarrollador IA", "Desarrollador Python",
           "Especialista en IA"]
PERFIL = {"keywords": PUESTOS, "habilidades": ["React"]}


def _params(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# --- Publicaciones ---------------------------------------------------------------

def test_publicaciones_nunca_pasa_del_tope_y_lleva_dos_gatillos():
    """Con más de ~120 caracteres LinkedIn devuelve cero sin avisar; sin dos
    frases de contratación trae charlas sobre el tema."""
    sugeridas = sugeridas_publicaciones(PERFIL)
    assert sugeridas
    for s in sugeridas:
        texto = _params(s["url"])["keywords"]
        assert len(texto) <= TOPE_KEYWORDS
        assert que_entro_en(texto, GATILLOS_ES)["gatillos"] >= 2


def test_publicaciones_usa_un_not_por_termino():
    """`NOT (a OR b)` devuelve cero: medido el 10/9/2026."""
    for s in sugeridas_publicaciones(PERFIL):
        assert "NOT (" not in _params(s["url"])["keywords"]


def test_publicaciones_pone_primero_los_puestos_en_castellano():
    primera = _params(sugeridas_publicaciones(PERFIL)[0]["url"])["keywords"]
    assert primera.startswith('("Ingeniero de IA"')


def test_publicaciones_incluye_forward_deployed_acortado():
    """La frase exacta "Forward Deployed Engineer" no encuentra "Forward
    Deployed AI Engineer", que es el mismo puesto."""
    textos = " ".join(_params(s["url"])["keywords"] for s in sugeridas_publicaciones(PERFIL))
    assert '"Forward Deployed"' in textos
    assert "Forward Deployed Engineer" not in textos


def test_publicaciones_mira_las_ultimas_24_horas_y_lo_mas_nuevo_primero():
    p = _params(sugeridas_publicaciones(PERFIL)[0]["url"])
    assert p["datePosted"] == '"past-24h"' and p["sortBy"] == '"date_posted"'


def test_las_habilidades_no_entran_en_las_sugeridas():
    todas = sugeridas_publicaciones(PERFIL) + sugeridas_jobs(PERFIL)
    assert not any("React" in _params(s["url"])["keywords"] for s in todas)


def test_no_se_muestran_mas_de_cinco():
    muchos = {"keywords": [f"Puesto {i}" for i in range(40)]}
    assert len(sugeridas_publicaciones(muchos)) == linkedin_urls.MAX_SUGERIDAS
    assert len(sugeridas_jobs(muchos)) == linkedin_urls.MAX_SUGERIDAS


# --- Jobs ------------------------------------------------------------------------

def test_jobs_trae_las_ultimas_2_horas_remoto_y_con_menos_de_10_candidatos():
    p = _params(sugeridas_jobs(PERFIL)[0]["url"])
    assert p["f_TPR"] == "r7200"
    assert p["f_WT"] == "2"
    assert p["f_JIYN"] == "true"
    assert p["sortBy"] == "DD" and p["geoId"] == "100446943"


def test_jobs_no_repite_los_titulos_en_castellano():
    textos = " ".join(_params(s["url"])["keywords"] for s in sugeridas_jobs(PERFIL))
    assert "Ingeniero" not in textos and "Desarrollador" not in textos
    assert '"Forward Deployed Engineer"' in textos


def test_jobs_usa_los_de_castellano_si_no_hay_otros():
    """Un perfil de seguridad e higiene puede tener todo en castellano."""
    solo = {"keywords": ["Técnico en Seguridad e Higiene", "Analista QHSE"]}
    textos = " ".join(_params(s["url"])["keywords"] for s in sugeridas_jobs(solo))
    assert "Analista QHSE" in textos


def test_el_nombre_dice_cuantos_puestos_busca():
    nombre = sugeridas_jobs(PERFIL)[0]["nombre"]
    assert nombre.startswith("AI Engineer y ") and "más" in nombre


# --- en la pantalla -----------------------------------------------------------------

def _con_puestos(*puestos):
    perfil = data.leer_perfil("test")
    perfil["keywords"] = list(puestos)
    data.guardar_perfil("test", perfil)


def test_la_pantalla_muestra_las_sugeridas_con_su_boton_de_guardar(sitio):
    base, _ = sitio
    _con_puestos("AI Engineer", "Ingeniero de IA")
    _, html, _ = get(base, "/linkedin?perfil=test")
    assert "Sugeridas para vos" in html
    assert 'class="favoritos sugeridas"' in html
    assert ">Guardar</button>" in html


def test_guardar_una_sugerida_la_pasa_a_tus_guardadas(sitio):
    base, _ = sitio
    _con_puestos("AI Engineer")
    sugerida = sugeridas_jobs(data.leer_perfil("test"))[0]
    post(base, "/linkedin-favorito", {"perfil": "test", "tab": "jobs",
                                      "url": sugerida["url"], "nombre": sugerida["nombre"]})
    assert linkedin_urls.guardada_como("test", sugerida["url"]) == sugerida["nombre"]
    _, html, _ = get(base, "/linkedin?perfil=test&tab=jobs")
    # Ya no está entre las sugeridas, y como era la única la sección se va.
    assert "Sugeridas para vos" not in html
    assert sugerida["nombre"] in html
