"""Indeed y Get on Board.

⚠️ Estos tests usan tablas y JSON de ejemplo, NO los sitios reales. Prueban que
la fuente hace lo que tiene que hacer con lo que recibe; que lo que reciba se
parezca a esto se verificó a mano contra los sitios el 19/11/2026 y está anotado
en los docstrings de cada fuente y en NOTAS-PARA-ISAIAS.md (2.49).
"""

import json

import pandas as pd

from vacantia.sources import SOURCE_REGISTRY
from vacantia.sources.getonbrd import GetOnBoardSource, _texto
from vacantia.sources.indeed import IndeedSource, _canonica, ubicacion

PERFIL = {"keywords": ["AI Engineer", "Python"], "filters": {"max_age_days": 7}}


def test_las_dos_estan_registradas():
    assert SOURCE_REGISTRY["indeed"] is IndeedSource
    assert SOURCE_REGISTRY["getonbrd"] is GetOnBoardSource


# --- Indeed ----------------------------------------------------------------

def _fila(**campos) -> dict:
    """Una fila como las que devuelve JobSpy para Indeed (columnas reales)."""
    base = {
        "job_url": "https://ar.indeed.com/viewjob?jk=81e84a3359486229",
        "job_url_direct": "https://corva.example/jobs/1",
        "title": "Senior Python Developer",
        "company": "CORVA",
        "location": "Buenos Aires, B, AR",
        "date_posted": "2026-11-19",
        "is_remote": False,
        "description": "Buscamos Python con FastAPI.",
    }
    return {**base, **campos}


def test_no_necesita_tinyfish():
    """Antes Indeed se leía con TinyFish y sin esa clave quedaba apagada.

    Ahora lee la API de la app de Indeed por JobSpy: lo único que puede faltar
    es el paquete, igual que en LinkedIn.
    """
    ok, motivo = IndeedSource({"type": "indeed"}, PERFIL).is_available()
    assert "TINYFISH" not in motivo.upper()
    assert ok or "jobspy" in motivo


def test_la_url_guardada_es_la_canonica_de_siempre():
    """Es la clave contra la que se compara todo lo que ya se vio de Indeed.

    Si cambiara, los avisos que ya están en el historial entrarían de nuevo
    como nuevos, y se pagaría otra vez por puntuarlos.
    """
    esperada = "https://ar.indeed.com/viewjob?jk=a7eef2df3e324c35"
    assert _canonica("https://ar.indeed.com/viewjob?jk=a7eef2df3e324c35") == esperada
    assert _canonica("https://ar.indeed.com/viewjob?jk=A7EEF2DF3E324C35&from=serp") == esperada
    assert _canonica("https://ar.indeed.com/rc/clk?jk=a7eef2df3e324c35&bb=TOKEN") == esperada
    assert _canonica("https://ar.indeed.com/jobs?q=AI&vjk=a7eef2df3e324c35") == esperada
    # `fromjk` es de los links de sueldos: no es un aviso.
    assert _canonica("https://ar.indeed.com/career/salaries/AI?fromjk=abc123def456") == ""
    assert _canonica("") == ""


def test_la_ubicacion_de_indeed():
    """Así la arma JobSpy: ciudad, código de provincia y código de país.

    El código de país se cambia por el nombre, que es lo que compara el filtro
    de ubicación. Y la provincia sola ("B") no es una ciudad: si lo fuera, el
    filtro de ciudad compararía "Bahía Blanca" contra "B".
    """
    assert ubicacion("Buenos Aires, B, AR", "Argentina") == (
        "Argentina", "Buenos Aires", "B", False)
    assert ubicacion("B, AR", "Argentina") == ("Argentina", "", "B", False)
    assert ubicacion("Córdoba, X, AR", "Argentina") == ("Argentina", "Córdoba", "X", False)
    assert ubicacion("", "Argentina") == ("", "", "", False)


def test_desde_casa_es_remoto_aunque_indeed_no_lo_marque():
    """Visto el 19/11/2026: "Cloud SysAdmin" de DonWeb venía como "Desde casa,
    AR" con `is_remote` en falso. Sin esto quedaba con la ciudad "Desde casa"
    y el filtro de ciudad lo tiraba."""
    assert ubicacion("Desde casa, AR", "Argentina") == ("Argentina", "", "", True)

    s = IndeedSource({"type": "indeed"}, PERFIL)
    job = s._a_job(pd.Series(_fila(location="Desde casa, AR", is_remote=False)), "Python")
    assert job.work_mode == "remote" and job.city == ""


def test_arma_el_aviso_con_todo_lo_que_hace_falta_para_puntuarlo():
    s = IndeedSource({"type": "indeed"}, PERFIL)
    job = s._a_job(pd.Series(_fila(job_url="https://ar.indeed.com/viewjob?jk=ABC123DEF456&from=x")),
                   "Python")
    assert job.url == "https://ar.indeed.com/viewjob?jk=abc123def456"
    assert job.title == "Senior Python Developer"
    assert job.company == "CORVA"
    assert job.source == "indeed"
    assert job.posted_at == "2026-11-19"
    assert (job.country, job.city, job.region) == ("Argentina", "Buenos Aires", "B")
    # Que Indeed no lo marque como remoto no quiere decir que sea presencial.
    assert job.work_mode == ""
    assert "FastAPI" in job.description and "FastAPI" in job.descripcion_completa
    assert job.raw["job_url_direct"] == "https://corva.example/jobs/1"

    remoto = s._a_job(pd.Series(_fila(is_remote=True)), "Python")
    assert remoto.work_mode == "remote"


def test_un_aviso_sin_url_o_sin_titulo_no_entra_en_indeed():
    s = IndeedSource({"type": "indeed"}, PERFIL)
    assert s._a_job(pd.Series(_fila(job_url="")), "q") is None
    assert s._a_job(pd.Series(_fila(title=None)), "q") is None


def test_le_pide_a_indeed_la_ventana_y_el_pais(monkeypatch):
    """La ventana va en horas (`hours_old`), como en LinkedIn, y el país decide
    el dominio (`ar.indeed.com`). No se manda `is_remote`: con la ventana
    puesta, JobSpy lo ignora en Indeed y la modalidad la filtra `filters.py`."""
    import jobspy

    pedidos = []

    def falso(**kwargs):
        pedidos.append(kwargs)
        return pd.DataFrame([_fila()])

    monkeypatch.setattr(jobspy, "scrape_jobs", falso)
    IndeedSource({"type": "indeed"}, PERFIL)._scrape("AI Engineer")
    pedido = pedidos[0]
    assert pedido["site_name"] == ["indeed"]
    assert pedido["search_term"] == "AI Engineer"
    assert pedido["country_indeed"] == "argentina"
    assert pedido["hours_old"] == 7 * 24
    assert "is_remote" not in pedido
    assert "location" not in pedido          # todo el país

    sin_ventana = {**PERFIL, "filters": {"max_age_days": 0}}
    IndeedSource({"type": "indeed"}, sin_ventana)._scrape("AI Engineer")
    assert "hours_old" not in pedidos[1]


def test_junta_las_busquedas_sin_repetir_y_tira_lo_viejo(monkeypatch):
    """El mismo aviso aparece en dos búsquedas: entra una vez. Y lo de más de
    7 días se tira con su motivo, para que el embudo diga por qué."""
    viejo = "2020-01-01"
    tablas = {
        "AI Engineer": pd.DataFrame([_fila(), _fila(job_url="https://ar.indeed.com/viewjob?jk=0123456789ab",
                                                    title="Viejo", date_posted=viejo)]),
        "Python": pd.DataFrame([_fila()]),
    }
    monkeypatch.setattr(IndeedSource, "_scrape", lambda self, t: tablas[t])
    s = IndeedSource({"type": "indeed", "delay_between_searches": 0}, PERFIL)
    salida = s.fetch()
    assert [j.title for j in salida] == ["Senior Python Developer"]
    assert [d["titulo"] for d in s.descartes] == ["Viejo"]
    assert "más de 7 días" in s.descartes[0]["motivo"]


def test_una_busqueda_que_falla_no_tumba_la_corrida(monkeypatch):
    def scrape(self, termino):
        if termino == "AI Engineer":
            raise RuntimeError("429")
        return pd.DataFrame([_fila()])

    monkeypatch.setattr(IndeedSource, "_scrape", scrape)
    salida = IndeedSource({"type": "indeed", "delay_between_searches": 0}, PERFIL).fetch()
    assert len(salida) == 1


def test_indeed_busca_los_puestos_de_los_cv_y_rota():
    """Los términos salen de `terminos_de_busqueda` (los puestos del perfil y de
    cada CV) y se rotan con `max_queries`: el tope no se saca, porque es una API
    sin login y que no se bloquee depende de no abusar."""
    perfil = {"keywords": ["A", "B", "C"],
              "cvs": [{"nombre": "X", "path": "x.md", "palabras_clave": ["D"]}]}
    s = IndeedSource({"type": "indeed", "max_queries": 2}, perfil)
    assert s.terminos() == ["A", "B"]
    assert s.siguiente_en_rotacion == 2
    todos = IndeedSource({"type": "indeed", "max_queries": 10}, perfil).terminos()
    assert "D" in todos


# --- Get on Board ----------------------------------------------------------

def test_no_necesita_ninguna_credencial():
    """Es la única fuente que no scrapea y no gasta una sola credencial.

    Por eso conviene tenerla prendida: cuando las demás se saltean por falta de
    TINYFISH_API_KEY, ésta sigue trayendo.
    """
    s = GetOnBoardSource({"type": "getonbrd"}, PERFIL)
    assert s.is_available() == (True, "")
    assert GetOnBoardSource({"type": "getonbrd"}, {}).is_available()[0] is False


def test_la_descripcion_html_se_pasa_a_texto():
    """Es lo que va al prompt del que puntúa: con las etiquetas adentro, la
    mitad del presupuesto de tokens se lo comen los `<strong>`."""
    assert _texto("<ul><li>Python</li><li>FastAPI</li></ul>") == "Python\nFastAPI"
    assert _texto("<p>Hola &amp; chau<br>Segunda</p>") == "Hola & chau\nSegunda"
    assert _texto("") == ""
    assert _texto(None) == ""


# Un aviso tal como lo devuelve la API, recortado. La estructura es la real,
# verificada el 9/9/2026 contra /api/v0/search/jobs.
CRUDO = {
    "type": "job",
    "id": "ai-engineer-niuro-remote",
    "links": {"public_url": "https://www.getonbrd.com/jobs/ai-engineer-niuro-remote"},
    "attributes": {
        "title": "AI Back-end Engineer",
        "description": "<ul><li>Experiencia con <strong>Python</strong></li></ul>",
        "functions": "<div>Diseñar servicios</div>",
        "desirable": "",
        "projects": "",
        "remote": True,
        "remote_modality": "fully_remote",
        "countries": ["Remote"],
        "published_at": 1788205797,
        "category_name": "Machine Learning & AI",
        "applications_count": 97,
        "min_salary": 2300,
        "max_salary": 2800,
        "company": {"data": {"id": 6322, "type": "company"}},
    },
}


def _fuente(**config):
    s = GetOnBoardSource({"type": "getonbrd", **config}, PERFIL)
    s._empresas[6322] = "Niuro"       # como si ya la hubiera resuelto
    return s


def test_arma_el_aviso_con_todo_lo_que_hace_falta_para_puntuarlo():
    job = _fuente()._a_job(CRUDO, "AI Engineer")
    assert job.url == "https://www.getonbrd.com/jobs/ai-engineer-niuro-remote"
    assert job.title == "AI Back-end Engineer"
    assert job.company == "Niuro"
    assert job.work_mode == "remote"
    assert job.posted_at == "2026-08-31"          # el sello unix, como fecha
    assert "Python" in job.description and "<strong>" not in job.description
    assert "Diseñar servicios" in job.description  # los cuatro campos, juntos


def test_remote_no_es_un_pais():
    """La API lo mezcla en `countries`, y ponerlo en `country` hacía que el
    filtro de ubicación lo comparara contra "Argentina" y lo tirara."""
    job = _fuente(country_code="AR")._a_job(CRUDO, "AI Engineer")
    assert job.country == "Argentina"
    assert job.work_mode == "remote"

    con_pais = {**CRUDO, "attributes": {**CRUDO["attributes"],
                                        "countries": ["Chile"], "remote": False,
                                        "remote_modality": "hybrid"}}
    otro = _fuente()._a_job(con_pais, "AI Engineer")
    assert otro.country == "Chile" and otro.work_mode == "hybrid"


def test_un_aviso_sin_url_o_sin_titulo_no_entra():
    s = _fuente()
    assert s._a_job({"attributes": {"title": "X"}, "links": {}}, "q") is None
    assert s._a_job({"attributes": {"title": ""}, "links": {"public_url": "u"}}, "q") is None
    assert s._a_job({}, "q") is None


def test_una_fecha_rota_no_tumba_la_corrida():
    roto = {**CRUDO, "attributes": {**CRUDO["attributes"], "published_at": "ayer"}}
    job = _fuente()._a_job(roto, "AI Engineer")
    assert job is not None and job.posted_at == ""


def test_la_empresa_se_pide_una_sola_vez_por_id(monkeypatch):
    """Varios avisos comparten empresa, y sin el nombre `Job.dedupe_key`
    devuelve "" y el dedupe por empresa+título no corre."""
    pedidos = []
    s = GetOnBoardSource({"type": "getonbrd"}, PERFIL)

    def falso_get(self, ruta, **params):
        pedidos.append(ruta)
        return {"data": {"attributes": {"name": "Niuro"}}}

    monkeypatch.setattr(GetOnBoardSource, "_get", falso_get)
    for _ in range(3):
        assert s._empresa(CRUDO["attributes"]) == "Niuro"
    assert pedidos == ["companies/6322"]          # una sola vez, no tres

    # Un aviso sin empresa no rompe ni pide nada.
    assert s._empresa({}) == ""
    assert len(pedidos) == 1


def test_la_api_caida_no_tumba_la_corrida(monkeypatch):
    monkeypatch.setattr(GetOnBoardSource, "_get", lambda self, ruta, **p: {})
    assert GetOnBoardSource({"type": "getonbrd"}, PERFIL).fetch() == []


# --- Get on Board por categoría --------------------------------------------

def _aviso(slug: str, titulo: str = "AI Engineer", empresa: str = "Niuro") -> dict:
    """Un aviso como lo devuelve la API con `expand=["company"]`: la empresa
    viene adentro, con su nombre, y el id es un slug y no un número."""
    return {
        "id": slug,
        "links": {"public_url": f"https://www.getonbrd.com/jobs/{slug}"},
        "attributes": {**CRUDO["attributes"], "title": titulo,
                       "published_at": int(__import__("time").time()),
                       "company": {"data": {"id": empresa.lower(), "type": "company",
                                            "attributes": {"name": empresa}}}},
    }


def test_por_categoria_trae_todo_sin_terminos_ni_rotacion(monkeypatch):
    """El mercado de Get on Board para la Argentina es chico (101 ofertas activas
    el 19/11/2026, 43 entre programación e IA). Buscándolo por 17 términos de a
    3 por corrida se llegaba hasta 7 días tarde, y 42 ofertas nunca se vieron.
    Leyendo las categorías enteras no se escapa ninguna."""
    pedidos = []

    def falso_get(self, ruta, **params):
        pedidos.append((ruta, params))
        if ruta == "categories/programming/jobs":
            return {"data": [_aviso("a"), _aviso("b")], "meta": {"total_pages": 1}}
        if ruta == "categories/machine-learning-ai/jobs":
            # "a" está en las dos categorías: entra una sola vez.
            return {"data": [_aviso("a"), _aviso("c")], "meta": {"total_pages": 1}}
        raise AssertionError(f"no debería pedir {ruta}")

    monkeypatch.setattr(GetOnBoardSource, "_get", falso_get)
    s = GetOnBoardSource({"type": "getonbrd",
                          "categorias": ["programming", "machine-learning-ai"]}, {})
    assert s.is_available() == (True, "")      # sin keywords: no las necesita
    salida = s.fetch()

    assert [j.url.rsplit("/", 1)[1] for j in salida] == ["a", "b", "c"]
    assert s.siguiente_en_rotacion is None     # no hay nada que rotar
    ruta, params = pedidos[0]
    assert params["country_code"] == "AR"
    assert params["per_page"] == 100
    assert params["expand"] == '["company"]'


def test_por_categoria_pasa_de_pagina_hasta_el_tope(monkeypatch):
    """Lee las páginas que diga `total_pages`, pero nunca más de `max_paginas`:
    sin `country_code`, programación sola tiene 300 avisos en todo el portal."""
    paginas = []

    def falso_get(self, ruta, **params):
        paginas.append(params["page"])
        return {"data": [_aviso(f"p{params['page']}")], "meta": {"total_pages": 9}}

    monkeypatch.setattr(GetOnBoardSource, "_get", falso_get)
    s = GetOnBoardSource({"type": "getonbrd", "categorias": ["programming"],
                          "max_paginas": 2}, PERFIL)
    assert len(s.fetch()) == 2
    assert paginas == [1, 2]


def test_por_categoria_corta_cuando_no_hay_mas_paginas(monkeypatch):
    paginas = []

    def falso_get(self, ruta, **params):
        paginas.append(params["page"])
        return {"data": [_aviso("x")] if params["page"] == 1 else [],
                "meta": {"total_pages": 1}}

    monkeypatch.setattr(GetOnBoardSource, "_get", falso_get)
    GetOnBoardSource({"type": "getonbrd", "categorias": ["programming"]}, PERFIL).fetch()
    assert paginas == [1]


def test_la_empresa_que_viene_en_el_aviso_no_se_pide_aparte(monkeypatch):
    """Con `expand=["company"]` el nombre viene en el listado. Antes era una
    llamada más por empresa, y leyendo categorías enteras serían decenas."""
    def no_deberia(self, ruta, **params):
        raise AssertionError(f"pidió {ruta}")

    monkeypatch.setattr(GetOnBoardSource, "_get", no_deberia)
    s = GetOnBoardSource({"type": "getonbrd"}, PERFIL)
    assert s._empresa(_aviso("a", empresa="Improving")["attributes"]) == "Improving"


def test_sin_categorias_sigue_buscando_por_terminos(monkeypatch):
    """Para un perfil que no es de tecnología las categorías no sirven: sigue
    la búsqueda de siempre, y también pide la empresa adentro del aviso."""
    pedidos = []

    def falso_get(self, ruta, **params):
        pedidos.append((ruta, params))
        return {"data": [_aviso(params["query"].replace(" ", "-").lower())]}

    monkeypatch.setattr(GetOnBoardSource, "_get", falso_get)
    salida = GetOnBoardSource({"type": "getonbrd"}, PERFIL).fetch()
    assert [r for r, _ in pedidos] == ["search/jobs", "search/jobs"]
    assert {p["query"] for _, p in pedidos} == {"AI Engineer", "Python"}
    assert all(p["expand"] == '["company"]' for _, p in pedidos)
    assert len(salida) == 2


# --- el embudo y lo que ya se vio --------------------------------------------

def test_lo_que_la_fuente_tira_y_ya_se_habia_visto_no_se_anota():
    """Get on Board deja una oferta activa semanas, y pasados los 7 días la
    fuente la tira por vieja en cada corrida. El 19/11/2026, 47 de las 89
    descartadas así se habían visto frescas: contarlas inflaba el embudo y
    parecía que se perdían ofertas que no se perdieron."""
    from types import SimpleNamespace

    from vacantia.embudo import Embudo
    from vacantia.engine import RunResult, _embudo_de_fuentes
    from vacantia.models import clave_de_url

    fuente = SimpleNamespace(name="getonbrd", descartes=[
        {"url": "https://www.getonbrd.com/jobs/vista", "titulo": "Vista",
         "motivo": "publicado hace más de 7 días"},
        {"url": "https://www.getonbrd.com/jobs/nueva", "titulo": "Nunca vista",
         "motivo": "publicado hace más de 7 días"},
    ])
    embudo = Embudo("prueba", dry_run=True)
    _embudo_de_fuentes(embudo, [fuente], [], RunResult(),
                       {clave_de_url("https://www.getonbrd.com/jobs/vista/")})

    assert [d["titulo"] for d in embudo.descartes] == ["Nunca vista"]
    assert embudo.conteo["getonbrd"]["descartada_en_fuente"] == 1
