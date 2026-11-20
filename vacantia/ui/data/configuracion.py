"""La configuración de cada persona: perfiles, CV, `.env`, empresas, fuentes y Telegram.

Es lo que se edita en *Mi perfil* y *Configuración*. Vivía en `ui/data.py`
junto con las ofertas y las métricas; se separó sin cambiar nada (ver
`ui/data/__init__.py`).
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from vacantia.config import PROFILES_DIR, cvs_del_perfil, id_de_cv, profile_path
from vacantia.log import get_logger
from vacantia.state import STATE_ROOT

logger = get_logger()


ENV_FILE = Path(".env")
RESUME_DIR = Path("resume")
PLANTILLA_PERFIL = PROFILES_DIR / "example.json"
PLANTILLA_CV = RESUME_DIR / "EJEMPLO_CV.md"

#: Claves que la UI deja editar en el `.env`. El resto del archivo no se toca.
#:
#: El TELEGRAM_CHAT_ID NO está acá a propósito: es el único dato que no se
#: comparte. Dos personas que usan la misma computadora comparten la clave del
#: bot y las de las APIs, pero cada una tiene que recibir SUS ofertas en SU
#: Telegram, así que el chat_id va dentro del perfil (ver `chat_id_de`).
CLAVES_ENV = (
    "TELEGRAM_TOKEN",
    "GEMINI_API_KEY",
    "TINYFISH_API_KEY",
    "OPENROUTER_API_KEY",
)

#: Lo que se deja en el perfil cuando la persona no carga un chat propio: cae
#: al TELEGRAM_CHAT_ID del .env, que es como venía funcionando.
CHAT_ID_COMPARTIDO = "${TELEGRAM_CHAT_ID}"

NOMBRE_VALIDO = re.compile(r"^[a-z0-9_-]{2,32}$")


# --- perfiles ---------------------------------------------------------------

def perfiles() -> list[str]:
    """Los perfiles editables. `example` es la plantilla, no se lista."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json") if p.stem != "example")


def leer_perfil(nombre: str) -> dict:
    """El JSON tal cual está en disco.

    A propósito NO se usa `config.load_profile`: esa resuelve los `${VAR}` a su
    valor real, y guardar eso escribiría las claves de la API dentro del perfil,
    que se versiona en git.
    """
    ruta = profile_path(nombre)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el perfil '{nombre}'")
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar_perfil(nombre: str, data: dict) -> None:
    ruta = profile_path(nombre)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(ruta, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    logger.info(f"[ui] Perfil guardado: {ruta}")


def _escribir_atomico(ruta: Path, texto: str) -> None:
    """Escribe a un temporal y reemplaza. Si se corta la luz a mitad de un
    guardado, el archivo viejo queda entero en vez de truncado."""
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)


def crear_perfil(nombre: str) -> str:
    """Perfil nuevo en blanco a partir de la plantilla. Devuelve el nombre.

    No inventa datos de nadie: copia `profiles/example.json` con los
    placeholders puestos para que la persona los complete desde la UI.
    """
    nombre = (nombre or "").strip().lower().replace(" ", "_")
    if not NOMBRE_VALIDO.match(nombre):
        raise ValueError(
            "El nombre tiene que tener entre 2 y 32 letras, números, guiones o "
            "guiones bajos, sin espacios ni acentos (ej: maria, juan_pablo)."
        )
    if nombre == "example":
        raise ValueError("'example' es la plantilla: elegí otro nombre.")
    destino = profile_path(nombre)
    if destino.exists():
        raise ValueError(f"Ya existe un perfil llamado '{nombre}'.")
    if not PLANTILLA_PERFIL.exists():
        raise FileNotFoundError(f"Falta la plantilla {PLANTILLA_PERFIL}")

    data = json.loads(PLANTILLA_PERFIL.read_text(encoding="utf-8"))
    data.pop("_comentario", None)   # la nota es del molde, no del perfil nuevo
    data["name"] = nombre
    data["cv_path"] = f"resume/{nombre}.md"
    # Cada perfil con su propio archivo de empresas. La plantilla trae
    # `companies.json`, que es el de Isaías: copiado tal cual, el perfil nuevo
    # compartía ese archivo, y guardar su lista pisaba la del otro. Pasó el
    # 12/9/2026 con el perfil de papá y se perdieron las 10 empresas de Isaías.
    for fuente in data.get("sources") or []:
        if fuente.get("type") == "careers":
            fuente["companies_file"] = f"companies-{nombre}.json"
    guardar_perfil(nombre, data)

    cv = RESUME_DIR / f"{nombre}.md"
    if not cv.exists():
        RESUME_DIR.mkdir(parents=True, exist_ok=True)
        if PLANTILLA_CV.exists():
            shutil.copyfile(PLANTILLA_CV, cv)
        else:
            cv.write_text("# PEGAR CV ACÁ\n", encoding="utf-8")
        logger.info(f"[ui] CV en blanco creado: {cv}")
    return nombre


#: Cómo se llama la búsqueda programada de cada perfil. La registra
#: `scripts/instalar.ps1` con este mismo nombre.
TAREA_PROGRAMADA = "Vacantia - {}"


def borrar_perfil(nombre: str) -> str:
    """Borra un perfil con todo lo suyo. Devuelve qué pasó con su tarea programada.

    **Es definitivo**, y por eso la pantalla pide confirmación antes de llegar
    acá. Se va:

    * `profiles/<nombre>.json`. `example` nunca: es el molde de los nuevos.
    * Sus CV, salvo el archivo que lea otro perfil.
    * `companies-<nombre>.json`, salvo que lo use otro perfil. Un archivo con
      otro nombre, como el `companies.json` de antes de separar las listas, no
      se toca: aunque este perfil lo use, no es suyo.
    * `state/<nombre>/`: las ofertas guardadas, lo que marcaste, los favoritos.
    * Su búsqueda programada de Windows. Si no está o no se deja sacar, lo demás
      se borra igual y la pantalla lo avisa: una tarea huérfana falla sola al
      no encontrar el perfil, que es mucho menos grave que un perfil a medio
      borrar.

    Devuelve "sacada", "no-estaba" o "fallo".
    """
    if nombre == "example":
        raise ValueError("'example' es el molde de los perfiles nuevos: no se borra.")
    if nombre not in perfiles():
        raise ValueError(f"No existe el perfil '{nombre}'.")
    try:
        perfil = leer_perfil(nombre)
    except json.JSONDecodeError:
        perfil = {}             # roto, pero igual se tiene que poder borrar
    cvs = cvs_del_perfil(perfil) if perfil else []
    empresas = ruta_companies(perfil)
    empresas_compartidas = otros_perfiles_con_las_mismas_empresas(nombre, perfil)

    # Primero el estado, que es lo único que puede fallar a mitad de camino: un
    # archivo abierto por una búsqueda en curso. Si falla acá, el perfil sigue
    # entero y se puede volver a intentar.
    estado = STATE_ROOT / nombre
    if estado.is_dir():
        shutil.rmtree(estado)

    # El perfil antes que los CV: `_archivo_de_cv_en_uso` recorre todos los
    # perfiles, y con éste todavía en disco cada CV suyo figuraría en uso.
    profile_path(nombre).unlink()
    for cv in cvs:
        ruta = Path(cv["path"])
        if (ruta.is_file() and ruta.resolve() != PLANTILLA_CV.resolve()
                and not _archivo_de_cv_en_uso(ruta)):
            ruta.unlink()

    if (empresas.name == f"companies-{nombre}.json" and empresas.is_file()
            and not empresas_compartidas):
        empresas.unlink()

    logger.info(f"[ui] Perfil borrado: {nombre}")
    return _sacar_tarea_programada(nombre)


def _sacar_tarea_programada(nombre: str) -> str:
    """Saca la búsqueda programada de un perfil. "sacada", "no-estaba" o "fallo".

    Primero pregunta si está. Un perfil creado desde la pantalla no tiene tarea
    hasta que se vuelve a correr la instalación, y decirle "no pude sacarla" a
    quien nunca la tuvo lo manda a buscar un problema que no existe.

    `schtasks` viene con Windows. Las tareas se registran con el usuario común,
    así que sacarlas no pide permisos de administrador.
    """
    tarea = TAREA_PROGRAMADA.format(nombre)
    opciones = {"capture_output": True, "text": True, "errors": "replace", "timeout": 15,
                "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        consulta = subprocess.run(["schtasks", "/Query", "/TN", tarea], **opciones)
        if consulta.returncode != 0:
            logger.info(f"[ui] {tarea} no estaba programada")
            return "no-estaba"
        borrado = subprocess.run(["schtasks", "/Delete", "/TN", tarea, "/F"], **opciones)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"[ui] No pude sacar la tarea {tarea}: {e}")
        return "fallo"
    if borrado.returncode != 0:
        logger.warning(f"[ui] No pude sacar la tarea {tarea}: "
                       f"{(borrado.stderr or borrado.stdout or '').strip()}")
        return "fallo"
    logger.info(f"[ui] Tarea sacada: {tarea}")
    return "sacada"


# --- CV ---------------------------------------------------------------------

def ruta_cv(perfil: dict) -> Path:
    return Path(perfil.get("cv_path") or f"resume/{perfil.get('name', 'cv')}.md")


def leer_cv(perfil: dict) -> str:
    ruta = ruta_cv(perfil)
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


def fijar_cvs(perfil: dict, cvs: list[dict]) -> None:
    """Escribe la lista de CV en el perfil (en memoria; guardarlo es aparte).

    `cv_path` sigue apuntando al primero: lo leen el drafter y cualquier cosa
    vieja que todavía piense en un CV solo, y así no se entera del cambio.
    """
    perfil["cvs"] = [
        {"id": cv["id"], "nombre": cv["nombre"], "path": cv["path"],
         "palabras_clave": list(cv.get("palabras_clave") or []),
         "habilidades": list(cv.get("habilidades") or [])}
        for cv in cvs
    ]
    perfil["cv_path"] = perfil["cvs"][0]["path"]


def agregar_cv(nombre_perfil: str) -> str:
    """Suma un CV vacío al perfil, para completarlo en la pantalla. Devuelve su id.

    Nace vacío a propósito y así no cuenta para nada (ver `config.cvs_con_texto`)
    hasta que tenga texto: agregarlo no cambia ninguna recomendación ni ningún
    puntaje. El archivo es `resume/<perfil>-<id>.md`; si ya existía uno con ese
    nombre, no se pisa.
    """
    perfil = leer_perfil(nombre_perfil)
    cvs = cvs_del_perfil(perfil)
    ids = {cv["id"] for cv in cvs}
    numero = len(cvs) + 1
    while id_de_cv(f"CV {numero}") in ids:
        numero += 1
    nombre_cv = f"CV {numero}"
    cv_id = id_de_cv(nombre_cv)

    ruta = RESUME_DIR / f"{nombre_perfil}-{cv_id}.md"
    if not ruta.exists():
        RESUME_DIR.mkdir(parents=True, exist_ok=True)
        ruta.write_text("", encoding="utf-8")

    fijar_cvs(perfil, cvs + [{"id": cv_id, "nombre": nombre_cv,
                             "path": ruta.as_posix(), "palabras_clave": [],
                             "habilidades": []}])
    guardar_perfil(nombre_perfil, perfil)
    logger.info(f"[ui] CV agregado a {nombre_perfil}: {cv_id} ({ruta})")
    return cv_id


def borrar_cv(nombre_perfil: str, cv_id: str) -> str:
    """Borra un CV del perfil y su archivo. Devuelve su nombre, o "" si no se pudo.

    **Es definitivo**, y por eso la pantalla pide confirmación antes de llegar
    acá. No se puede borrar el último: el perfil tiene que quedar con uno.

    El archivo no se borra si lo lee otro CV, de éste o de otro perfil: pasa si
    alguien apunta dos CV al mismo texto a mano, y borrar uno no puede dejar al
    otro vacío. Las ofertas que recomendaban el CV borrado se vuelven a estimar
    solas.
    """
    perfil = leer_perfil(nombre_perfil)
    cvs = cvs_del_perfil(perfil)
    borrado = next((cv for cv in cvs if cv["id"] == cv_id), None)
    quedan = [cv for cv in cvs if cv["id"] != cv_id]
    if borrado is None or not quedan:
        return ""
    fijar_cvs(perfil, quedan)
    guardar_perfil(nombre_perfil, perfil)

    ruta = Path(borrado["path"])
    if ruta.exists() and not _archivo_de_cv_en_uso(ruta):
        ruta.unlink()
        logger.info(f"[ui] CV borrado de {nombre_perfil}: {cv_id} ({ruta})")
    else:
        logger.info(f"[ui] CV sacado de {nombre_perfil}: {cv_id} (el archivo lo usa otro CV)")
    return borrado["nombre"]


def _archivo_de_cv_en_uso(ruta: Path) -> bool:
    """¿Algún CV de algún perfil lee este archivo?"""
    objetivo = ruta.resolve()
    for nombre in perfiles():
        try:
            otro = leer_perfil(nombre)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if any(Path(cv["path"]).resolve() == objetivo for cv in cvs_del_perfil(otro)):
            return True
    return False


def guardar_cv(perfil: dict, texto: str) -> None:
    ruta = ruta_cv(perfil)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(ruta, texto.replace("\r\n", "\n"))
    logger.info(f"[ui] CV guardado: {ruta} ({len(texto)} chars)")


# --- .env -------------------------------------------------------------------

def leer_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    valores = {}
    for linea in ENV_FILE.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def guardar_env(cambios: dict[str, str]) -> list[str]:
    """Escribe sólo las claves que vienen con valor, respetando el resto.

    Un campo vacío en el formulario significa "no lo cambies", no "borralo":
    la UI muestra las claves enmascaradas, así que si vaciarlas borrara el
    valor, entrar a la pantalla y guardar sin tocar nada dejaría a la persona
    sin credenciales.
    """
    cambios = {k: v.strip() for k, v in cambios.items() if k in CLAVES_ENV and v.strip()}
    if not cambios:
        return []

    lineas = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    pendientes = dict(cambios)
    salida = []
    for linea in lineas:
        clave = linea.split("=", 1)[0].strip() if "=" in linea else ""
        if clave in pendientes and not linea.strip().startswith("#"):
            salida.append(f"{clave}={pendientes.pop(clave)}")
        else:
            salida.append(linea)
    for clave, valor in pendientes.items():
        salida.append(f"{clave}={valor}")

    _escribir_atomico(ENV_FILE, "\n".join(salida) + "\n")
    # Para que la corrida que se dispare desde esta misma sesión las vea.
    for clave, valor in cambios.items():
        os.environ[clave] = valor
    logger.info(f"[ui] .env actualizado: {', '.join(sorted(cambios))}")
    return sorted(cambios)


def enmascarar(valor: str) -> str:
    """'abc123def456' -> 'abc1…f456'. Para mostrar sin exponer la clave."""
    valor = (valor or "").strip()
    if not valor:
        return ""
    if len(valor) <= 8:
        return "•" * len(valor)
    return f"{valor[:4]}…{valor[-4:]}"


# --- empresas ---------------------------------------------------------------

def ruta_companies(perfil: dict) -> Path:
    fuente = _fuente(perfil, "careers")
    return Path((fuente or {}).get("companies_file") or "companies.json")


def leer_companies(perfil: dict) -> list[dict]:
    ruta = ruta_companies(perfil)
    if not ruta.exists():
        return []
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning(f"[ui] {ruta} no es JSON válido — lo muestro vacío")
        return []
    return data if isinstance(data, list) else []


def otros_perfiles_con_las_mismas_empresas(nombre_perfil: str, perfil: dict) -> list[str]:
    """Los demás perfiles que leen y escriben el mismo archivo de empresas."""
    propia = ruta_companies(perfil).resolve()
    otros = []
    for otro in perfiles():
        if otro == nombre_perfil:
            continue
        try:
            if ruta_companies(leer_perfil(otro)).resolve() == propia:
                otros.append(otro)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return otros


def separar_companies(nombre_perfil: str, perfil: dict) -> list[str]:
    """Si otro perfil usa el mismo archivo de empresas, éste pasa a tener el suyo.

    Devuelve con quiénes lo compartía, o [] si no hizo falta separar. Cambia el
    perfil en memoria: guardarlo es de quien llama.

    **El que se va es el que guarda, y el otro no se toca.** Así, guardar la
    lista de un perfil nunca puede pisar la de otro, que es exactamente lo que
    pasó cuando compartían archivo: se guardó el perfil de papá y la lista de
    Isaías desapareció.
    """
    otros = otros_perfiles_con_las_mismas_empresas(nombre_perfil, perfil)
    if otros:
        # Si el bloque no existía, nace apagado: separar la lista no puede
        # prender una fuente. Prenderla es de Configuración.
        fuente_o_crear(perfil, "careers", {"enabled": False})["companies_file"] = (
            f"companies-{nombre_perfil}.json")
    return otros


def companies_a_texto(companies: list[dict]) -> str:
    """Una empresa por línea: `Nombre | careers_url | dominio`."""
    return "\n".join(
        " | ".join(
            [c.get("name", ""), c.get("careers_url", ""), c.get("search_domain", "")]
        ).rstrip(" |")
        for c in companies
    )


def texto_a_companies(texto: str, previas: list[dict]) -> list[dict]:
    """Parsea el textarea conservando los campos que la UI no muestra.

    `use_search`, `location` y `region` no están en el formulario; si se
    reconstruyera la lista de cero se perderían (y con ellos el ahorro de las
    siete empresas que tienen la búsqueda apagada).
    """
    por_nombre = {c.get("name", "").strip().lower(): c for c in previas}
    salida = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        partes = [p.strip() for p in linea.split("|")]
        nombre = partes[0]
        if not nombre:
            continue
        entrada = dict(por_nombre.get(nombre.lower(), {}))
        entrada["name"] = nombre
        if len(partes) > 1 and partes[1]:
            entrada["careers_url"] = partes[1]
        if len(partes) > 2 and partes[2]:
            entrada["search_domain"] = partes[2]
        entrada.setdefault("careers_url", "")
        salida.append(entrada)
    return salida


def guardar_companies(perfil: dict, companies: list[dict]) -> None:
    ruta = ruta_companies(perfil)
    _escribir_atomico(ruta, json.dumps(companies, indent=2, ensure_ascii=False) + "\n")
    logger.info(f"[ui] {ruta} actualizado ({len(companies)} empresa(s))")


# --- fuentes dentro del perfil ---------------------------------------------

def _fuente(perfil: dict, tipo: str) -> dict | None:
    for entrada in perfil.get("sources", []) or []:
        if entrada.get("type") == tipo:
            return entrada
    return None


def fuente_o_crear(perfil: dict, tipo: str, defaults: dict | None = None) -> dict:
    """Devuelve el bloque de esa fuente en el perfil, creándolo si no está."""
    encontrada = _fuente(perfil, tipo)
    if encontrada is not None:
        return encontrada
    nueva = {"type": tipo, "enabled": True, **(defaults or {})}
    perfil.setdefault("sources", []).append(nueva)
    return nueva


# --- Telegram por persona ---------------------------------------------------

def _telegram(perfil: dict) -> dict:
    """El bloque del notificador de Telegram, creándolo si no está."""
    for entrada in perfil.get("notifiers") or []:
        if entrada.get("type") == "telegram":
            return entrada
    nuevo = {"type": "telegram", "enabled": True, "token": "${TELEGRAM_TOKEN}",
             "chat_id": CHAT_ID_COMPARTIDO}
    perfil.setdefault("notifiers", []).append(nuevo)
    return nuevo


def chat_id_de(perfil: dict) -> str:
    """El chat propio de esta persona, o "" si usa el compartido del .env."""
    valor = str(_telegram(perfil).get("chat_id") or "").strip()
    return "" if valor.startswith("${") else valor


def guardar_chat_id(perfil: dict, chat_id: str) -> None:
    """Vacío = volver al chat compartido del .env."""
    chat_id = (chat_id or "").strip()
    _telegram(perfil)["chat_id"] = chat_id or CHAT_ID_COMPARTIDO
