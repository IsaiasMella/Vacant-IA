"""Repasar entrevistas grabadas (`vacantia/entrevistas.py`).

Nada de esto llama a Gemini ni corre ffmpeg: la subida, la generación y la
extracción del audio se reemplazan por funciones falsas. Que la API de Gemini
acepte el audio así se probó a mano el 20/11/2026 (ver el docstring del módulo).
"""

import json

import pytest

from vacantia import entrevistas as ent

PERFIL = {
    "name": "prueba",
    "candidate": {"name": "Isaías"},
    "cv_path": "resume/prueba.md",
    "llm": {"llm_provider": "gemini", "gemini_api_key": "clave-de-prueba",
            "gemini_model": "modelo-a", "gemini_fallback_models": ["modelo-b"]},
}

ANALISIS = {
    "resumen": "Fue bien en lo técnico, floja la parte de nube.",
    "puesto": "AI Engineer",
    "preguntas": [
        {"pregunta": "¿Usaste RAG?", "tu_respuesta": "Sí, en Aduana.",
         "como_estuvo": "bien", "que_falto": "", "mejor_respuesta": "Contar el chatbot."},
        {"pregunta": "¿Desplegaste en AWS?", "tu_respuesta": "Dudé.",
         "como_estuvo": "MUY MAL", "que_falto": "Ejemplo concreto", "mejor_respuesta": "..."},
        {"pregunta": "", "tu_respuesta": "sin pregunta, no va"},
    ],
    "lo_que_salio_bien": ["Claridad", ""],
    "temas_para_repasar": ["Despliegue en la nube"],
}


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    """Una instalación de juguete: todas las rutas del proyecto son relativas."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume").mkdir()
    (tmp_path / "resume" / "prueba.md").write_text("# CV\nRAG con LangChain en Aduana.",
                                                    encoding="utf-8")
    return tmp_path


def _con_grabacion(empresa="RedBee", archivo="Meet 20-11.mp4", fecha="2026-11-20"):
    datos = ent.nueva("prueba", empresa, fecha, archivo)
    ent.ruta_de_la_grabacion("prueba", datos).write_bytes(b"video falso")
    return datos


# --- crear y guardar --------------------------------------------------------

def test_una_entrevista_nueva_nace_con_fecha_empresa_y_sin_oferta(raiz):
    """La oferta no hace falta: muchas veces uno no sabe por dónde mandó el CV."""
    datos = ent.nueva("prueba", "  Red   Bee ", "2026-11-20", "grabación.MP4")
    assert datos["id"] == "2026-11-20-red-bee"
    assert datos["empresa"] == "Red Bee"
    assert datos["oferta_url"] == ""
    assert datos["estado"] == "subida"
    assert datos["grabacion"] == "grabacion.mp4"
    assert ent.leer("prueba", datos["id"])["empresa"] == "Red Bee"

    # Dos entrevistas con la misma empresa el mismo día no se pisan.
    assert ent.nueva("prueba", "Red Bee", "2026-11-20", "otra.mp4")["id"] == "2026-11-20-red-bee-2"


def test_sin_empresa_o_con_un_archivo_que_no_es_grabacion_no_se_crea(raiz):
    with pytest.raises(ent.ErrorDeEntrevista, match="empresa"):
        ent.nueva("prueba", "  ", "2026-11-20", "a.mp4")
    with pytest.raises(ent.ErrorDeEntrevista, match="No reconozco"):
        ent.nueva("prueba", "RedBee", "2026-11-20", "cv.pdf")


def test_el_id_que_llega_por_la_url_no_sale_de_la_carpeta(raiz):
    """El id viaja en la URL: sin validarlo, "../../" escribiría fuera de state."""
    for malo in ("../../etc", "a/b", "", "A" * 80):
        with pytest.raises(ent.ErrorDeEntrevista):
            ent.carpeta_de("prueba", malo)


def test_listar_trae_la_mas_reciente_primero(raiz):
    ent.nueva("prueba", "Vieja", "2026-10-01", "a.mp4")
    ent.nueva("prueba", "Nueva", "2026-11-19", "b.mp4")
    assert [e["empresa"] for e in ent.listar("prueba")] == ["Nueva", "Vieja"]
    assert ent.listar("otro") == []


# --- qué oferta puede ser ---------------------------------------------------

HISTORIAL = [
    {"url": "u1", "company": "redbee", "title": "Senior AI Specialist",
     "aplicado": True, "fecha_feedback": "2026-09-08T12:00:00+00:00"},
    {"url": "u2", "company": "Redbee S.A.", "title": "Backend",
     "aplicado": None, "found_at": "2026-11-01T12:00:00+00:00"},
    {"url": "u3", "company": "Mercado Libre", "title": "Evals",
     "aplicado": True, "fecha_feedback": "2026-10-30T12:00:00+00:00"},
    {"url": "u4", "company": "", "title": "sin empresa"},
]


def test_propone_las_ofertas_de_esa_empresa_primero_las_aplicadas():
    """El caso real: RedBee llamó dos semanas después y no había forma de
    saber de qué aviso. En el historial estaba: "Senior AI Specialist", aplicada
    el 8/9. Las aplicadas van primero porque son las que terminan en entrevista."""
    assert [o["url"] for o in ent.ofertas_parecidas(HISTORIAL, "RedBee")] == ["u1", "u2"]
    # Escrita separada, también: "Red Bee" y "redbee" son la misma.
    assert [o["url"] for o in ent.ofertas_parecidas(HISTORIAL, "Red Bee")] == ["u1", "u2"]
    assert [o["url"] for o in ent.ofertas_parecidas(HISTORIAL, "mercado libre")] == ["u3"]
    assert ent.ofertas_parecidas(HISTORIAL, "Globant") == []
    # "S.A." o "Argentina" solos no tienen que traer cualquier cosa.
    assert ent.ofertas_parecidas(HISTORIAL, "S.A.") == []


# --- ffmpeg -----------------------------------------------------------------

def test_saca_solo_el_audio_liviano_y_en_tramos(tmp_path):
    """Mono a 16 kHz y Opus a 24 kbps: una hora de video de Meet queda en unos
    11 MB. Los tramos de 10 minutos son para que la transcripción no se corte."""
    orden = ent.orden_de_ffmpeg("ffmpeg", tmp_path / "v.mp4", tmp_path)
    assert "-vn" in orden
    assert orden[orden.index("-ac") + 1] == "1"
    assert orden[orden.index("-ar") + 1] == "16000"
    assert orden[orden.index("-segment_time") + 1] == "600"
    assert orden[-1].endswith("tramo_%03d.ogg")


def test_sin_ffmpeg_dice_como_instalarlo(tmp_path, monkeypatch):
    monkeypatch.setattr(ent.shutil, "which", lambda nombre: None)
    with pytest.raises(ent.ErrorDeEntrevista, match="winget install Gyan.FFmpeg"):
        ent.extraer_audio(tmp_path / "v.mp4", tmp_path / "tramos")


# --- el análisis --------------------------------------------------------------

def test_el_analisis_queda_con_las_claves_que_espera_la_pantalla():
    """El modelo a veces se saltea claves o inventa valores: la pantalla no
    puede romperse por eso."""
    limpio = ent.normalizar_analisis(ANALISIS)
    assert [p["pregunta"] for p in limpio["preguntas"]] == ["¿Usaste RAG?", "¿Desplegaste en AWS?"]
    assert limpio["preguntas"][1]["como_estuvo"] == "regular"   # "MUY MAL" no es un valor
    assert limpio["lo_que_salio_bien"] == ["Claridad"]
    assert limpio["a_mejorar"] == [] and limpio["proximos_pasos"] == ""


def test_el_json_se_rescata_aunque_venga_con_texto_alrededor():
    assert ent._json_de('Acá va:\n```json\n{"resumen": "ok"}\n```') == {"resumen": "ok"}
    with pytest.raises(ent.ErrorDeEntrevista):
        ent._json_de("no hay nada")


# --- todo junto --------------------------------------------------------------

@pytest.fixture
def gemini_falso(monkeypatch):
    """Reemplaza ffmpeg y Gemini. Devuelve la lista de pedidos que recibió."""
    pedidos = []

    def extraer(entrada, salida_dir):
        salida_dir.mkdir(parents=True, exist_ok=True)
        tramos = [salida_dir / "tramo_000.ogg", salida_dir / "tramo_001.ogg"]
        for t in tramos:
            t.write_bytes(b"audio")
        return tramos

    def subir(ruta, clave, tipo="audio/ogg"):
        return {"name": f"files/{ruta.stem}", "uri": f"https://x/{ruta.stem}",
                "mimeType": "audio/ogg"}

    def generar(partes, clave, modelos, como_json=False, temperatura=0.2):
        pedidos.append({"partes": partes, "modelos": modelos, "json": como_json})
        if como_json:
            return json.dumps(ANALISIS)
        return "Entrevistador: ¿Usaste RAG?\nIsaías: Sí, en Aduana."

    monkeypatch.setattr(ent, "extraer_audio", extraer)
    monkeypatch.setattr(ent, "subir", subir)
    monkeypatch.setattr(ent, "borrar_subido", lambda archivo, clave: None)
    monkeypatch.setattr(ent, "generar", generar)
    return pedidos


def test_procesar_transcribe_analiza_y_borra_el_video(raiz, gemini_falso):
    datos = _con_grabacion()
    salida = ent.procesar("prueba", datos["id"], perfil=PERFIL)

    assert salida["estado"] == "lista" and salida["error"] == ""
    # Un pedido por tramo de transcripción, y uno de análisis en JSON.
    assert [p["json"] for p in gemini_falso] == [False, False, True]
    assert gemini_falso[0]["modelos"] == ["modelo-a", "modelo-b"]

    texto = ent.transcripcion("prueba", datos["id"])
    assert "--- Minuto 0 a 10 ---" in texto and "--- Minuto 10 a 20 ---" in texto
    assert ent.analisis("prueba", datos["id"])["preguntas"][0]["pregunta"] == "¿Usaste RAG?"

    carpeta = ent.carpeta_de("prueba", datos["id"])
    # El video pesa cientos de MB y el original sigue en la compu de la persona.
    assert not ent.ruta_de_la_grabacion("prueba", datos).exists()
    assert not (carpeta / "tramos").exists()


def test_el_analisis_lleva_el_cv_y_el_aviso_si_quedo_vinculada(raiz, gemini_falso):
    estado = raiz / "state" / "prueba"
    estado.mkdir(parents=True)
    (estado / "job_history.json").write_text(json.dumps([
        {"url": "https://ejemplo/aviso", "title": "Senior AI Specialist",
         "company": "redbee", "description": "Buscamos experiencia con LangGraph."}]),
        encoding="utf-8")
    datos = _con_grabacion()
    ent.vincular("prueba", datos["id"], "https://ejemplo/aviso")
    ent.procesar("prueba", datos["id"], perfil=PERFIL)

    prompt = gemini_falso[-1]["partes"][0]["text"]
    assert "RAG con LangChain en Aduana" in prompt          # el CV
    assert "Buscamos experiencia con LangGraph" in prompt   # el aviso
    assert "Isaías: Sí, en Aduana." in prompt               # la transcripción


def test_volver_a_analizar_no_transcribe_de_nuevo(raiz, gemini_falso, monkeypatch):
    """Transcribir es lo caro. Si ya está, re-analizar (por ejemplo después de
    vincular la oferta) usa el texto guardado aunque el video ya no esté."""
    datos = _con_grabacion()
    ent.procesar("prueba", datos["id"], perfil=PERFIL)
    monkeypatch.setattr(ent, "extraer_audio",
                        lambda *a: pytest.fail("no tenía que volver a sacar el audio"))
    gemini_falso.clear()

    assert ent.procesar("prueba", datos["id"], perfil=PERFIL)["estado"] == "lista"
    assert [p["json"] for p in gemini_falso] == [True]


def test_si_gemini_falla_queda_el_error_para_la_persona(raiz, gemini_falso, monkeypatch):
    def falla(*a, **k):
        raise ent.ErrorDeEntrevista("Gemini no respondió (429). Probá de nuevo en un rato.")

    monkeypatch.setattr(ent, "generar", falla)
    datos = _con_grabacion()
    salida = ent.procesar("prueba", datos["id"], perfil=PERFIL)
    assert salida["estado"] == "error"
    assert "Probá de nuevo" in salida["error"]
    # La grabación no se borra si no se pudo transcribir: hay que poder reintentar.
    assert ent.ruta_de_la_grabacion("prueba", datos).exists()


def test_sin_clave_de_gemini_lo_dice(raiz, gemini_falso, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    sin_clave = {**PERFIL, "llm": {**PERFIL["llm"], "gemini_api_key": ""}}
    datos = _con_grabacion()
    salida = ent.procesar("prueba", datos["id"], perfil=sin_clave)
    assert salida["estado"] == "error" and "GEMINI_API_KEY" in salida["error"]


def test_un_error_inesperado_tampoco_deja_la_entrevista_colgada(raiz, gemini_falso, monkeypatch):
    """Si quedara en "procesando", la pantalla mostraría el cartel para siempre."""
    monkeypatch.setattr(ent, "generar", lambda *a, **k: 1 / 0)
    datos = _con_grabacion()
    salida = ent.procesar("prueba", datos["id"], perfil=PERFIL)
    assert salida["estado"] == "error" and "division by zero" in salida["error"]
