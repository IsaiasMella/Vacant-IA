"""La pestaña Entrevistas: subir la grabación, ver el avance y leer el repaso.

El análisis nunca corre de verdad: `entrevistas.arrancar` se reemplaza por una
función que anota a quién habría lanzado. El análisis en sí está probado en
`test_entrevistas.py`.
"""

import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from tests.test_ui import _con_historial, get, post, sitio  # noqa: F401
from vacantia import entrevistas as ent

ANALISIS = {
    "resumen": "Bien en lo técnico, floja la parte de Kubernetes.",
    "puesto": "AI Engineer",
    "preguntas": [
        {"pregunta": "¿Trabajaste con RAG?", "tu_respuesta": "Sí, en Aduana.",
         "como_estuvo": "bien", "que_falto": "", "mejor_respuesta": "Contalo con números."},
        {"pregunta": "¿Desplegaste en Kubernetes?", "tu_respuesta": "No mucho.",
         "como_estuvo": "floja", "que_falto": "Un ejemplo concreto",
         "mejor_respuesta": "Tu CV no muestra esto: contá lo parecido que sí hiciste."},
    ],
    "lo_que_salio_bien": ["Fuiste al grano"],
    "a_mejorar": ["No titubear"],
    "temas_para_repasar": ["Kubernetes básico"],
    "preguntas_que_hiciste": [],
    "preguntas_para_la_proxima": ["¿Cómo despliegan?"],
    "proximos_pasos": "Te mandan la prueba técnica.",
}


@pytest.fixture
def lanzadas(monkeypatch):
    """A quién habría lanzado `arrancar`, sin lanzar ningún proceso."""
    llamadas = []
    monkeypatch.setattr(ent, "arrancar", lambda perfil, ident: llamadas.append((perfil, ident)))
    return llamadas


def _subir(base, contenido=b"video falso", **campos):
    params = {"perfil": "test", "empresa": "RedBee", "fecha": "2026-11-20",
              "archivo": "Meet.mp4", **campos}
    req = Request(f"{base}/entrevista-subir?{urlencode(params)}", data=contenido,
                  method="POST", headers={"Content-Type": "application/octet-stream"})
    try:
        with urlopen(req) as r:
            return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def _lista(tmp, ident, analisis=ANALISIS):
    """Deja una entrevista como si el análisis hubiera terminado."""
    datos = ent.leer("test", ident)
    datos["estado"] = "lista"
    ent.guardar("test", datos)
    carpeta = ent.carpeta_de("test", ident)
    (carpeta / "analisis.json").write_text(json.dumps(analisis), encoding="utf-8")
    (carpeta / "transcripcion.txt").write_text("Entrevistador: ¿RAG?\nTest: Sí.",
                                               encoding="utf-8")


def test_la_pestania_esta_en_la_barra_lateral(sitio):
    base, _ = sitio
    _, html, _ = get(base, "/entrevistas?perfil=test")
    assert 'class="nav-item activa" href="/entrevistas?perfil=test"' in html
    assert "<h1>Entrevistas</h1>" in html
    assert 'id="subir-entrevista"' in html
    assert "Todavía no cargaste ninguna" in html
    # Un solo primario, como en todas las pantallas.
    assert html[html.index("<main"):].count('class="primario"') == 1


def test_subir_guarda_la_grabacion_y_lanza_el_analisis(sitio, lanzadas):
    """La grabación llega como cuerpo del pedido y se escribe a disco: un video
    de Meet de una hora pesa cientos de MB y no se carga entero en memoria."""
    base, tmp = sitio
    codigo, respuesta = _subir(base, b"x" * 3_000_000)
    assert codigo == 200
    assert respuesta["url"] == "/entrevistas?perfil=test&id=2026-11-20-redbee"
    assert lanzadas == [("test", "2026-11-20-redbee")]

    datos = ent.leer("test", "2026-11-20-redbee")
    assert datos["empresa"] == "RedBee" and datos["archivo"] == "Meet.mp4"
    assert ent.ruta_de_la_grabacion("test", datos).stat().st_size == 3_000_000


def test_una_subida_rota_no_deja_nada(sitio, lanzadas):
    base, _ = sitio
    codigo, respuesta = _subir(base, archivo="cv.pdf")
    assert codigo == 400 and "No reconozco" in respuesta["error"]
    codigo, respuesta = _subir(base, empresa="")
    assert codigo == 400 and "empresa" in respuesta["error"]
    codigo, respuesta = _subir(base, perfil="nadie")
    assert codigo == 400
    assert lanzadas == []
    assert ent.listar("test") == []


def test_mientras_analiza_la_pagina_se_pregunta_sola(sitio, lanzadas):
    """Cada 4 segundos pregunta el estado; cuando termina, htmx recarga la
    página entera con el repaso (`HX-Refresh`)."""
    base, _ = sitio
    _subir(base)
    _, html, _ = get(base, "/entrevistas?perfil=test&id=2026-11-20-redbee")
    assert "Analizando la entrevista" in html
    assert 'hx-trigger="every 4s"' in html

    with urlopen(f"{base}/entrevista-estado?perfil=test&id=2026-11-20-redbee") as r:
        assert "Analizando" in r.read().decode("utf-8")
        assert r.headers.get("HX-Refresh") is None

    _lista(None, "2026-11-20-redbee")
    with urlopen(f"{base}/entrevista-estado?perfil=test&id=2026-11-20-redbee") as r:
        assert r.headers.get("HX-Refresh") == "true"


def test_el_repaso_muestra_cada_pregunta_y_abre_las_flojas(sitio, lanzadas):
    base, _ = sitio
    _subir(base)
    _lista(None, "2026-11-20-redbee")
    _, html, _ = get(base, "/entrevistas?perfil=test&id=2026-11-20-redbee")

    assert "<h1>Entrevista con RedBee</h1>" in html
    assert "vie 20/11" in html                      # la fecha con el día
    assert "Bien en lo técnico" in html
    assert "¿Trabajaste con RAG?" in html and "¿Desplegaste en Kubernetes?" in html
    # Las flojas vienen abiertas: son lo que hay que mirar.
    assert '<details class="pregunta" open>' in html
    assert html.count('<details class="pregunta"') == 2
    assert '<span class="como floja">Floja</span>' in html
    assert "Kubernetes básico" in html and "Te mandan la prueba técnica." in html
    assert "Ver la transcripción" in html
    assert "Borrar esta entrevista" in html


def test_propone_las_ofertas_de_esa_empresa_y_se_puede_vincular(sitio, lanzadas):
    """La entrevista llega semanas después y uno no se acuerda por dónde mandó
    el CV: se proponen las del historial con ese nombre de empresa."""
    base, tmp = sitio
    _con_historial(tmp, [
        {"url": "https://ejemplo/redbee-ai", "title": "Senior AI Specialist",
         "company": "redbee", "source": "linkedin", "aplicado": True,
         "fecha_feedback": "2026-09-08T12:00:00+00:00", "found_at": "2026-09-07T12:00:00+00:00"},
        {"url": "https://ejemplo/otra", "title": "Otra", "company": "Globant",
         "aplicado": True, "fecha_feedback": "2026-09-08T12:00:00+00:00"},
    ])
    _subir(base, empresa="Red Bee")
    _lista(None, "2026-11-20-red-bee")

    _, html, _ = get(base, "/entrevistas?perfil=test&id=2026-11-20-red-bee")
    assert "¿Es por alguna de éstas?" in html
    assert "Senior AI Specialist" in html and "Globant" not in html
    assert "aplicaste el mar 8/9" in html           # el 8/9/2026 fue martes

    _, html, _ = post(base, "/entrevista-vincular", {
        "perfil": "test", "id": "2026-11-20-red-bee", "url": "https://ejemplo/redbee-ai"})
    assert "quedó vinculada" in html
    assert "¿Es por alguna de éstas?" not in html
    assert "Por el aviso" in html
    assert ent.leer("test", "2026-11-20-red-bee")["oferta_url"] == "https://ejemplo/redbee-ai"


def test_volver_a_analizar_y_borrar(sitio, lanzadas):
    base, _ = sitio
    _subir(base)
    lanzadas.clear()

    # Mientras analiza no se lanza otro análisis encima.
    post(base, "/entrevista-analizar", {"perfil": "test", "id": "2026-11-20-redbee"})
    assert lanzadas == []

    _lista(None, "2026-11-20-redbee")
    post(base, "/entrevista-analizar", {"perfil": "test", "id": "2026-11-20-redbee"})
    assert lanzadas == [("test", "2026-11-20-redbee")]

    _, html, _ = post(base, "/entrevista-borrar", {"perfil": "test", "id": "2026-11-20-redbee"})
    assert "Borré la entrevista con RedBee" in html
    assert ent.listar("test") == []


def test_el_error_se_muestra_con_el_boton_para_reintentar(sitio, lanzadas):
    base, _ = sitio
    _subir(base)
    datos = ent.leer("test", "2026-11-20-redbee")
    datos.update(estado="error", error="Gemini no respondió (429). Probá de nuevo en un rato.")
    ent.guardar("test", datos)

    _, html, _ = get(base, "/entrevistas?perfil=test&id=2026-11-20-redbee")
    assert "Gemini no respondió" in html
    assert '<button class="primario" type="submit">Probar de nuevo</button>' in html


def test_un_analisis_que_quedo_colgado_se_da_por_cortado(sitio, lanzadas):
    """Si se apagó la compu a la mitad, el cartel de "analizando" quedaba para
    siempre. Pasados 30 minutos sin novedades, se ofrece reintentar."""
    import os
    import time

    base, _ = sitio
    _subir(base)
    archivo = ent.carpeta_de("test", "2026-11-20-redbee") / "entrevista.json"
    viejo = time.time() - 31 * 60
    os.utime(archivo, (viejo, viejo))

    _, html, _ = get(base, "/entrevistas?perfil=test&id=2026-11-20-redbee")
    assert "se cortó a la mitad" in html
    assert "Probar de nuevo" in html


def test_una_entrevista_que_no_existe_vuelve_a_la_lista(sitio):
    base, _ = sitio
    _, html, _ = get(base, "/entrevistas?perfil=test&id=no-existe")
    assert "Esa entrevista no existe." in html
    assert 'id="subir-entrevista"' in html
    _, html, _ = get(base, "/entrevistas?perfil=test&id=../../profiles")
    assert "Esa entrevista no existe." in html


def test_la_lista_dice_el_estado_de_cada_una(sitio, lanzadas):
    base, _ = sitio
    _subir(base)
    _subir(base, empresa="Mercado Libre", fecha="2026-11-18")
    _lista(None, "2026-11-18-mercado-libre")
    _, html, _ = get(base, "/entrevistas?perfil=test")
    assert "Tus entrevistas" in html
    assert html.index("RedBee") < html.index("Mercado Libre")   # la más reciente arriba
    assert '<span class="estado-entrevista lista">Lista</span>' in html
    assert '<span class="estado-entrevista subida">Esperando</span>' in html
