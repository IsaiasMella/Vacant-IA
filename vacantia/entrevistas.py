"""Repasar una entrevista grabada: qué te preguntaron, cómo respondiste y qué mejorar.

**Por qué existe (20/11/2026).** Isaías graba sus entrevistas (video de Meet,
Zoom o Teams) y después las mira para ver en qué falló. Esto hace ese repaso
por él: transcribe la grabación, la cruza con su CV y devuelve, pregunta por
pregunta, qué respondió, qué faltó y una respuesta mejor armada **sólo con lo que
el CV respalda**, la misma regla que `mensajes.py`: inventar experiencia se cae
en la primera pregunta técnica.

**La entrevista no necesita una oferta.** En la vida real a uno lo llaman dos
semanas o un mes y medio después de mandar el CV, a veces por un mensaje privado
a alguien de RRHH que no pasó por ninguna fuente. Por eso la entrevista es algo
aparte: grabación, nombre de la empresa como uno se acuerde, y fecha. Si en el
historial hay una oferta de esa empresa se propone (`ofertas_parecidas`), y si
la persona la confirma queda vinculada; si no, el análisis sale igual.

**Cómo se procesa** (`procesar`), en un proceso aparte para que la pantalla siga
andando (ver `arrancar`):

1. **ffmpeg saca el audio del video**, en mono, 16 kHz y Opus a 24 kbps, partido
   en tramos de 10 minutos. Una hora de video de Meet pesa cientos de MB; el
   audio así queda en unos 20 MB. Si ffmpeg no está, el error dice cómo
   instalarlo.
2. **Gemini transcribe cada tramo** por la Files API. Probado el 20/11/2026 con
   la clave de Isaías y `gemini-3.5-flash-lite`: el audio cuenta 25 tokens por
   segundo, así que una hora son unos 90.000 tokens de entrada. Los tramos están
   para que la salida no se corte: una hora de charla son unas 10.000 palabras,
   y un solo pedido con todo puede devolver la transcripción a medias.
3. **Gemini analiza la transcripción** contra el CV (y el aviso, si quedó
   vinculada) y devuelve JSON.

**Privacidad:** el audio sale a Google. En el plan gratis Google puede usarlo
para mejorar sus productos. Isaías lo eligió así sabiéndolo (20/11/2026). Los
archivos subidos se borran de Google apenas se transcriben, y el video subido
a la pantalla se borra de `state/` después de sacarle el audio: el original
sigue en la computadora de la persona.

Todo vive en `state/<perfil>/entrevistas/<id>/`:

    entrevista.json     empresa, fecha, oferta vinculada, estado y paso
    transcripcion.txt   el texto, tramo por tramo
    analisis.json       lo que muestra la pantalla
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from vacantia.log import get_logger
from vacantia.state import STATE_ROOT

logger = get_logger()

API = "https://generativelanguage.googleapis.com"

#: Minutos por tramo de audio. Diez minutos son unos 15.000 tokens de entrada y
#: una transcripción de unas 1.500 palabras: lejos de cualquier tope de salida.
MINUTOS_POR_TRAMO = 10

#: Formatos que acepta la pantalla. ffmpeg lee muchos más, pero la lista es la
#: que va en el `accept` del selector de archivo para no ofrecer un PDF.
EXTENSIONES = (".mp4", ".webm", ".mkv", ".mov", ".m4a", ".mp3", ".wav", ".ogg")

#: Los estados por los que pasa una entrevista, en orden.
ESTADOS = ("subida", "procesando", "lista", "error")

#: Tope de la grabación. Una hora de Meet en 1080p ronda 1 GB; 4 GB deja aire
#: para una entrevista larga sin dejar que un archivo equivocado llene el disco.
TAMANIO_MAXIMO = 4 * 1024 ** 3

#: Minutos sin novedades para dar por cortado un análisis. Cada paso actualiza
#: `entrevista.json`, y ninguno tarda más de unos minutos (un tramo de 10
#: minutos se transcribe en menos de uno). Si se apagó la compu o se cerró la
#: pantalla a la mitad, sin esto el cartel de "analizando" quedaba para siempre.
MINUTOS_SIN_NOVEDADES = 30

COMO_INSTALAR_FFMPEG = ("Falta ffmpeg, el programa que le saca el audio al video. "
                        "Instalalo abriendo PowerShell y escribiendo: "
                        "winget install Gyan.FFmpeg. Después cerrá y volvé a "
                        "abrir la pantalla.")


class ErrorDeEntrevista(ValueError):
    """Algo que la persona puede entender y, a veces, arreglar.

    Es un `ValueError` a propósito: el servidor ya convierte esos errores en el
    cartel rojo de la pantalla, con el texto tal cual.
    """


# --- dónde vive cada cosa ---------------------------------------------------

def carpeta(perfil: str, root: Path | None = None) -> Path:
    return (root or STATE_ROOT) / perfil / "entrevistas"


def carpeta_de(perfil: str, ident: str, root: Path | None = None) -> Path:
    if not re.fullmatch(r"[0-9a-z-]{1,60}", ident or ""):
        # El id llega desde la URL: sin esto, "../../" escribiría fuera de state.
        raise ErrorDeEntrevista("Esa entrevista no existe.")
    return carpeta(perfil, root) / ident


def _slug(texto: str) -> str:
    plano = "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                    if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", plano).strip("-")[:30] or "entrevista"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def leer(perfil: str, ident: str, root: Path | None = None) -> dict:
    ruta = carpeta_de(perfil, ident, root) / "entrevista.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        quieta = time.time() - ruta.stat().st_mtime
    except (OSError, ValueError):
        raise ErrorDeEntrevista("Esa entrevista no existe.")
    datos["id"] = ident
    # Se dice al leer y no se escribe: si el proceso en realidad seguía vivo,
    # su próximo paso pisa esto y la pantalla vuelve a mostrar el avance.
    if datos.get("estado") in ("subida", "procesando") and quieta > MINUTOS_SIN_NOVEDADES * 60:
        datos.update(estado="error", paso="",
                     error="El análisis se cortó a la mitad (¿se apagó la compu o se "
                           "cerró la pantalla?). Probá de nuevo.")
    return datos


def guardar(perfil: str, datos: dict, root: Path | None = None) -> None:
    ruta = carpeta_de(perfil, datos["id"], root) / "entrevista.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)


def _actualizar(perfil: str, ident: str, root: Path | None = None, **campos) -> dict:
    datos = leer(perfil, ident, root)
    datos.update(campos)
    guardar(perfil, datos, root)
    return datos


def nueva(perfil: str, empresa: str, fecha: str, archivo: str,
          root: Path | None = None) -> dict:
    """Crea la entrevista vacía. La grabación la escribe después el servidor."""
    empresa = " ".join(str(empresa or "").split())[:80]
    if not empresa:
        raise ErrorDeEntrevista("Falta el nombre de la empresa (como te acuerdes).")
    extension = Path(archivo or "").suffix.lower()
    if extension not in EXTENSIONES:
        raise ErrorDeEntrevista(
            f"No reconozco ese archivo. Sirven: {', '.join(EXTENSIONES)}.")
    try:
        cuando = date.fromisoformat(fecha).isoformat() if fecha else date.today().isoformat()
    except ValueError:
        cuando = date.today().isoformat()

    base = f"{cuando}-{_slug(empresa)}"
    ident, n = base, 2
    while (carpeta(perfil, root) / ident).exists():
        ident, n = f"{base}-{n}", n + 1
    datos = {"id": ident, "empresa": empresa, "fecha": cuando, "oferta_url": "",
             "archivo": Path(archivo).name, "grabacion": f"grabacion{extension}",
             "creada": _ahora(), "estado": "subida", "paso": "", "error": ""}
    guardar(perfil, datos, root)
    return datos


def ruta_de_la_grabacion(perfil: str, datos: dict, root: Path | None = None) -> Path:
    return carpeta_de(perfil, datos["id"], root) / datos["grabacion"]


def listar(perfil: str, root: Path | None = None) -> list[dict]:
    """Todas, la más reciente primero. Una carpeta rota se saltea."""
    salida = []
    base = carpeta(perfil, root)
    if not base.is_dir():
        return []
    for sub in base.iterdir():
        try:
            datos = leer(perfil, sub.name, root)
        except ErrorDeEntrevista:
            continue
        datos["tiene_analisis"] = (sub / "analisis.json").is_file()
        salida.append(datos)
    return sorted(salida, key=lambda d: (d.get("fecha", ""), d.get("creada", "")), reverse=True)


def analisis(perfil: str, ident: str, root: Path | None = None) -> dict | None:
    try:
        return json.loads((carpeta_de(perfil, ident, root) / "analisis.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def transcripcion(perfil: str, ident: str, root: Path | None = None) -> str:
    try:
        return (carpeta_de(perfil, ident, root) / "transcripcion.txt").read_text(encoding="utf-8")
    except OSError:
        return ""


def vincular(perfil: str, ident: str, url: str, root: Path | None = None) -> dict:
    return _actualizar(perfil, ident, root, oferta_url=str(url or "").strip())


def borrar(perfil: str, ident: str, root: Path | None = None) -> None:
    shutil.rmtree(carpeta_de(perfil, ident, root), ignore_errors=True)


# --- qué oferta puede ser ---------------------------------------------------

#: Lo que se le saca al nombre de una empresa para compararlo: "Redbee S.A." y
#: "redbee" son la misma, y "Software Factory" no dice nada de cuál es.
_RELLENO = {"sa", "srl", "sas", "sau", "inc", "llc", "ltd", "group", "grupo",
            "argentina", "latam", "software", "factory", "consulting", "the", "de"}


def _en_orden(nombre: str) -> list[str]:
    plano = "".join(c for c in unicodedata.normalize("NFD", str(nombre or "").lower())
                    if unicodedata.category(c) != "Mn")
    return [p for p in re.findall(r"[a-z0-9]+", plano) if p not in _RELLENO and len(p) > 1]


def _palabras(nombre: str) -> set[str]:
    return set(_en_orden(nombre))


def _junto(nombre: str) -> str:
    """"Red Bee" -> "redbee", en el orden en que se escribe."""
    return "".join(_en_orden(nombre))


def ofertas_parecidas(historial: list[dict], empresa: str, tope: int = 5) -> list[dict]:
    """Las ofertas del historial que pueden ser de esa empresa.

    Primero las que marcaste como aplicadas, que son las que más probablemente
    terminaron en una entrevista, y adentro de cada grupo la más reciente. Se
    compara por palabras y también todo junto, porque la misma empresa aparece
    como "redbee" y como "Red Bee".
    """
    buscadas, junta = _palabras(empresa), _junto(empresa)
    if not buscadas:
        return []
    candidatas = []
    for oferta in historial:
        nombre = oferta.get("company") or ""
        suyas = _palabras(nombre)
        if not suyas:
            continue
        if buscadas <= suyas or suyas <= buscadas or (junta and junta == _junto(nombre)):
            candidatas.append(oferta)

    def orden(o):
        return (o.get("aplicado") is True, o.get("fecha_feedback") or o.get("found_at") or "")

    return sorted(candidatas, key=orden, reverse=True)[:tope]


# --- ffmpeg -----------------------------------------------------------------

def ffmpeg() -> str:
    """La ruta de ffmpeg, o un error que dice cómo instalarlo."""
    ruta = shutil.which("ffmpeg")
    if not ruta:
        raise ErrorDeEntrevista(COMO_INSTALAR_FFMPEG)
    return ruta


def orden_de_ffmpeg(binario: str, entrada: Path, salida_dir: Path) -> list[str]:
    """Sólo el audio, mono, 16 kHz, Opus a 24 kbps, en tramos de 10 minutos.

    16 kHz mono es lo que necesita el reconocimiento de voz y nada más; a 24 kbps
    una hora queda en unos 11 MB. Opus en Ogg lo acepta Gemini como `audio/ogg`.
    """
    return [binario, "-hide_banner", "-loglevel", "error", "-y", "-i", str(entrada),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "24k",
            "-f", "segment", "-segment_time", str(MINUTOS_POR_TRAMO * 60),
            "-reset_timestamps", "1", str(salida_dir / "tramo_%03d.ogg")]


def extraer_audio(entrada: Path, salida_dir: Path) -> list[Path]:
    salida_dir.mkdir(parents=True, exist_ok=True)
    extra = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}
    resultado = subprocess.run(orden_de_ffmpeg(ffmpeg(), entrada, salida_dir),
                               capture_output=True, text=True, **extra)
    tramos = sorted(salida_dir.glob("tramo_*.ogg"))
    if resultado.returncode != 0 or not tramos:
        detalle = (resultado.stderr or "").strip().splitlines()[-1:] or ["sin detalle"]
        raise ErrorDeEntrevista(f"No pude sacar el audio de la grabación ({detalle[0]}). "
                                "¿El archivo se abre bien en tu computadora?")
    return tramos


# --- Gemini -----------------------------------------------------------------

def _clave_y_modelos(llm: dict) -> tuple[str, list[str]]:
    from vacantia.llm import _key

    clave = _key(llm, "gemini_api_key", "GEMINI_API_KEY")
    if not clave:
        raise ErrorDeEntrevista("Para repasar entrevistas hace falta la clave de Gemini "
                                "(GEMINI_API_KEY), en Configuración.")
    primero = llm.get("gemini_model") or "gemini-3.5-flash-lite"
    modelos = [primero] + [m for m in (llm.get("gemini_fallback_models") or []) if m != primero]
    return clave, modelos


def subir(ruta: Path, clave: str, tipo: str = "audio/ogg") -> dict:
    """Sube un archivo a la Files API de Gemini y espera a que esté listo."""
    import requests

    datos = ruta.read_bytes()
    inicio = requests.post(
        f"{API}/upload/v1beta/files", params={"key": clave}, timeout=60,
        headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                 "X-Goog-Upload-Header-Content-Length": str(len(datos)),
                 "X-Goog-Upload-Header-Content-Type": tipo,
                 "Content-Type": "application/json"},
        json={"file": {"display_name": ruta.name}})
    inicio.raise_for_status()
    destino = inicio.headers.get("X-Goog-Upload-URL")
    if not destino:
        raise ErrorDeEntrevista("Gemini no aceptó la subida del audio.")
    subida = requests.post(destino, data=datos, timeout=300,
                           headers={"X-Goog-Upload-Offset": "0",
                                    "X-Goog-Upload-Command": "upload, finalize"})
    subida.raise_for_status()
    archivo = subida.json()["file"]
    for _ in range(60):
        if archivo.get("state") != "PROCESSING":
            break
        time.sleep(2)
        archivo = requests.get(f"{API}/v1beta/{archivo['name']}",
                               params={"key": clave}, timeout=30).json()
    if archivo.get("state") != "ACTIVE":
        raise ErrorDeEntrevista("Gemini no pudo procesar el audio.")
    return archivo


def borrar_subido(archivo: dict, clave: str) -> None:
    """Se borra apenas se usa. Igual Google los borra solo a las 48 horas."""
    import requests

    try:
        requests.delete(f"{API}/v1beta/{archivo['name']}", params={"key": clave}, timeout=30)
    except Exception as e:
        logger.debug(f"[entrevistas] No pude borrar {archivo.get('name')} de Gemini: {e}")


def generar(partes: list[dict], clave: str, modelos: list[str], como_json: bool = False,
            temperatura: float = 0.2) -> str:
    """Un pedido a Gemini, probando los modelos en orden como `llm.chat_with_fallback`."""
    import requests

    config = {"temperature": temperatura}
    if como_json:
        config["responseMimeType"] = "application/json"
    ultimo = ""
    for modelo in modelos:
        for intento in range(2):
            try:
                r = requests.post(f"{API}/v1beta/models/{modelo}:generateContent",
                                  params={"key": clave}, timeout=600,
                                  json={"contents": [{"parts": partes}],
                                        "generationConfig": config})
            except Exception as e:
                ultimo = str(e)
                break
            if r.status_code == 429 and intento == 0:
                time.sleep(20)
                continue
            if not r.ok:
                ultimo = f"{r.status_code} {r.text[:200]}"
                logger.warning(f"[entrevistas] {modelo}: {ultimo}")
                break
            try:
                candidatos = r.json()["candidates"]
                return "".join(p.get("text", "") for p in candidatos[0]["content"]["parts"])
            except (KeyError, IndexError, ValueError):
                ultimo = f"{modelo} devolvió una respuesta vacía"
                break
    raise ErrorDeEntrevista(f"Gemini no respondió ({ultimo}). Puede ser el límite del "
                            "plan gratis: probá de nuevo en un rato.")


PROMPT_TRANSCRIBIR = """Transcribí este audio de una entrevista de trabajo, palabra por palabra, en el idioma en que se habla.

- El candidato se llama {nombre}. Rotulá sus intervenciones como "{nombre}:" y las de quien entrevista como "Entrevistador:" (si hay más de uno y se distinguen, "Entrevistador 1:", "Entrevistador 2:").
- Una línea por intervención. Sin resumir, sin corregir, sin agregar nada que no se diga.
- Si una parte no se entiende, poné [inaudible].
- Devolvé sólo la transcripción."""


def transcribir(tramos: list[Path], nombre: str, clave: str, modelos: list[str],
                al_avanzar=None) -> str:
    bloques = []
    for i, tramo in enumerate(tramos):
        if al_avanzar:
            al_avanzar(f"Transcribiendo: parte {i + 1} de {len(tramos)}")
        archivo = subir(tramo, clave)
        try:
            texto = generar([{"file_data": {"mime_type": archivo["mimeType"],
                                            "file_uri": archivo["uri"]}},
                             {"text": PROMPT_TRANSCRIBIR.format(nombre=nombre)}],
                            clave, modelos, temperatura=0)
        finally:
            borrar_subido(archivo, clave)
        desde = i * MINUTOS_POR_TRAMO
        bloques.append(f"--- Minuto {desde} a {desde + MINUTOS_POR_TRAMO} ---\n{texto.strip()}")
    return "\n\n".join(bloques)


PROMPT_ANALIZAR = """Sos un mentor que ayuda a {nombre} a mejorar en entrevistas de trabajo de tecnología. Te paso la transcripción de una entrevista real con {empresa}, su CV y, si hay, el aviso del puesto.

Reglas:
- Escribí en castellano rioplatense, de vos, directo y concreto. Aunque la entrevista haya sido en inglés.
- **La mejor respuesta se arma SÓLO con experiencia que el CV respalda.** Si el CV no respalda lo que preguntaron, decilo ("tu CV no muestra esto: si no lo hiciste, decí qué hiciste parecido") en vez de inventar. Una respuesta inventada se cae en la siguiente pregunta.
- Sé honesto: si una respuesta estuvo bien, decilo; si estuvo floja, explicá por qué.
- Las preguntas, en el orden en que aparecen. Las de cortesía ("¿me escuchás?") no van.

Devolvé SÓLO un JSON con esta forma:
{{
  "resumen": "2 o 3 frases: cómo fue en general",
  "puesto": "el puesto del que se habló, o \\"\\"",
  "preguntas": [
    {{"pregunta": "qué te preguntaron",
      "tu_respuesta": "lo que respondiste, resumido",
      "como_estuvo": "bien" | "regular" | "floja",
      "que_falto": "qué faltó o sobró; \\"\\" si estuvo bien",
      "mejor_respuesta": "cómo responderla la próxima, con tu experiencia real"}}
  ],
  "lo_que_salio_bien": ["..."],
  "a_mejorar": ["hábitos o formas de responder para corregir"],
  "temas_para_repasar": ["temas técnicos concretos para estudiar"],
  "preguntas_que_hiciste": ["las que hiciste vos a la empresa"],
  "preguntas_para_la_proxima": ["preguntas que te convenía hacer"],
  "proximos_pasos": "lo que dijeron que sigue, o \\"\\""
}}

CV de {nombre}:
{cv}

Aviso del puesto:
{aviso}

Transcripción:
{transcripcion}"""


def _json_de(texto: str) -> dict:
    """El objeto JSON de la respuesta, aunque venga con texto alrededor."""
    try:
        return json.loads(texto)
    except ValueError:
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio >= 0 and fin > inicio:
            try:
                return json.loads(texto[inicio:fin + 1])
            except ValueError:
                pass
    raise ErrorDeEntrevista("El análisis volvió en un formato que no entiendo. Probá de nuevo.")


def normalizar_analisis(crudo: dict) -> dict:
    """Con las claves que espera la pantalla, aunque el modelo se saltee alguna."""
    def lista(clave):
        return [str(x).strip() for x in (crudo.get(clave) or []) if str(x).strip()]

    preguntas = []
    for p in crudo.get("preguntas") or []:
        if not isinstance(p, dict) or not str(p.get("pregunta") or "").strip():
            continue
        como = str(p.get("como_estuvo") or "").strip().lower()
        preguntas.append({
            "pregunta": str(p.get("pregunta")).strip(),
            "tu_respuesta": str(p.get("tu_respuesta") or "").strip(),
            "como_estuvo": como if como in ("bien", "regular", "floja") else "regular",
            "que_falto": str(p.get("que_falto") or "").strip(),
            "mejor_respuesta": str(p.get("mejor_respuesta") or "").strip(),
        })
    return {
        "resumen": str(crudo.get("resumen") or "").strip(),
        "puesto": str(crudo.get("puesto") or "").strip(),
        "preguntas": preguntas,
        "lo_que_salio_bien": lista("lo_que_salio_bien"),
        "a_mejorar": lista("a_mejorar"),
        "temas_para_repasar": lista("temas_para_repasar"),
        "preguntas_que_hiciste": lista("preguntas_que_hiciste"),
        "preguntas_para_la_proxima": lista("preguntas_para_la_proxima"),
        "proximos_pasos": str(crudo.get("proximos_pasos") or "").strip(),
    }


def analizar(texto: str, empresa: str, nombre: str, cv: str, aviso: str,
             clave: str, modelos: list[str]) -> dict:
    prompt = PROMPT_ANALIZAR.format(nombre=nombre, empresa=empresa, cv=cv[:8000] or "(sin CV)",
                                    aviso=aviso[:4000] or "(no hay aviso vinculado)",
                                    transcripcion=texto)
    return normalizar_analisis(_json_de(generar([{"text": prompt}], clave, modelos,
                                                como_json=True)))


# --- todo junto --------------------------------------------------------------

def _cv_y_aviso(perfil: dict, nombre_perfil: str, oferta_url: str) -> tuple[str, str]:
    from vacantia.config import load_resumes
    from vacantia.state import State

    # Todos los CV, sin repetir: Isaías tiene dos, y la entrevista puede ser por
    # cualquiera de los dos perfiles.
    textos = [cv["texto"] for cv in load_resumes(perfil) if cv.get("texto")]
    cv = "\n\n---\n\n".join(dict.fromkeys(textos)) if textos else ""
    aviso = ""
    if oferta_url:
        for oferta in State(nombre_perfil).load_history():
            if oferta.get("url") == oferta_url:
                aviso = f"{oferta.get('title', '')} en {oferta.get('company', '')}\n\n" \
                        f"{oferta.get('description', '')}"
                break
    return cv, aviso


def procesar(nombre_perfil: str, ident: str, root: Path | None = None,
             perfil: dict | None = None) -> dict:
    """Saca el audio, transcribe, analiza y guarda. Nunca levanta: deja el error anotado."""
    from vacantia.config import load_profile

    def paso(texto: str) -> None:
        logger.info(f"[entrevistas] {ident}: {texto}")
        _actualizar(nombre_perfil, ident, root, paso=texto)

    datos = _actualizar(nombre_perfil, ident, root, estado="procesando", error="",
                        paso="Arrancando")
    dir_ = carpeta_de(nombre_perfil, ident, root)
    tramos_dir = dir_ / "tramos"
    try:
        perfil = perfil or load_profile(nombre_perfil)
        clave, modelos = _clave_y_modelos(perfil.get("llm") or {})
        nombre = (perfil.get("candidate") or {}).get("name") or "el candidato"

        texto = transcripcion(nombre_perfil, ident, root)
        if not texto:
            grabacion = ruta_de_la_grabacion(nombre_perfil, datos, root)
            if not grabacion.is_file():
                raise ErrorDeEntrevista("No encuentro la grabación: subila de nuevo.")
            paso("Sacando el audio del video")
            tramos = extraer_audio(grabacion, tramos_dir)
            texto = transcribir(tramos, nombre, clave, modelos, al_avanzar=paso)
            (dir_ / "transcripcion.txt").write_text(texto, encoding="utf-8")
            # Ya está transcripta: el video ocupa cientos de MB y el original
            # sigue en la computadora de la persona.
            grabacion.unlink(missing_ok=True)

        paso("Analizando tus respuestas")
        cv, aviso = _cv_y_aviso(perfil, nombre_perfil, datos.get("oferta_url", ""))
        resultado = analizar(texto, datos["empresa"], nombre, cv, aviso, clave, modelos)
        (dir_ / "analisis.json").write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        return _actualizar(nombre_perfil, ident, root, estado="lista", paso="",
                           analizada=_ahora())
    except ErrorDeEntrevista as e:
        logger.warning(f"[entrevistas] {ident}: {e}")
        return _actualizar(nombre_perfil, ident, root, estado="error", paso="", error=str(e))
    except Exception as e:
        logger.exception(f"[entrevistas] {ident}: falló el análisis")
        return _actualizar(nombre_perfil, ident, root, estado="error", paso="",
                           error=f"Algo falló al analizar la entrevista: {e}")
    finally:
        shutil.rmtree(tramos_dir, ignore_errors=True)


def arrancar(nombre_perfil: str, ident: str) -> None:
    """Lanza `procesar` en un proceso aparte, sin ventana, como `ui.corrida`.

    Una entrevista de una hora tarda unos minutos, y en un proceso aparte la
    pantalla sigue andando y el análisis no se corta si se recarga la página.
    """
    import os

    extra = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([sys.executable, "-m", "vacantia.entrevistas",
                      "--perfil", nombre_perfil, "--id", ident],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Analiza una entrevista grabada.")
    parser.add_argument("--perfil", required=True)
    parser.add_argument("--id", required=True)
    args = parser.parse_args(argv)
    # Las claves del .env las carga `load_profile`, adentro de `procesar`.
    resultado = procesar(args.perfil, args.id)
    return 0 if resultado.get("estado") == "lista" else 1


if __name__ == "__main__":
    sys.exit(main())
