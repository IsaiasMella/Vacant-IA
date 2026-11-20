"""Lectura y escritura de los archivos que edita la UI.

La UI no habla con el motor: escribe sobre los mismos archivos que el motor ya
usa (`profiles/<nombre>.json`, `resume/<nombre>.md`, `companies.json`, `.env` y
`state/<nombre>/`). Una sola fuente de verdad, sin sincronizar nada.

Todo lo que toca disco vive acá, así `server.py` se ocupa sólo de HTTP.

Era un solo `data.py` de 1.714 líneas, y se partió en cuatro sin cambiar nada:

* `configuracion`: perfiles, CV, `.env`, empresas, fuentes y Telegram.
* `historial`: las ofertas, sus filtros, el feedback, la auditoría del filtro y
  archivar.
* `metricas`: los números de Estadísticas y de los gráficos.
* `estado`: el pie de la barra lateral.

Este archivo reexporta todo con los mismos nombres de antes, así que
`from vacantia.ui import data` y `data.ofertas(...)` siguen andando igual. Lo
privado que se reexporta es sólo lo que se usa desde afuera.

**Ojo al parchear en un test**: una función que se reemplaza acá no cambia la
que usan los submódulos entre ellos. Hay que parchear el submódulo donde vive.
"""

# Lo que la pantalla le pide a `data` aunque sea de `config`: era así cuando
# `data.py` lo importaba, y `formulario.py` y `server.py` lo siguen buscando acá.
from vacantia.config import cvs_con_texto, cvs_del_perfil, load_resumes  # noqa: F401

from vacantia.ui.data.configuracion import (  # noqa: F401
    CHAT_ID_COMPARTIDO,
    CLAVES_ENV,
    ENV_FILE,
    NOMBRE_VALIDO,
    PLANTILLA_CV,
    PLANTILLA_PERFIL,
    RESUME_DIR,
    TAREA_PROGRAMADA,
    _escribir_atomico,
    agregar_cv,
    borrar_cv,
    borrar_perfil,
    chat_id_de,
    companies_a_texto,
    crear_perfil,
    enmascarar,
    fijar_cvs,
    fuente_o_crear,
    guardar_chat_id,
    guardar_companies,
    guardar_cv,
    guardar_env,
    guardar_perfil,
    leer_companies,
    leer_cv,
    leer_env,
    leer_perfil,
    otros_perfiles_con_las_mismas_empresas,
    perfiles,
    ruta_companies,
    ruta_cv,
    separar_companies,
    texto_a_companies,
)
from vacantia.ui.data.historial import (  # noqa: F401
    _ETIQUETAS_MOTIVO,
    _MOTIVO_VIEJO,
    DIAS_RECIEN,
    META_REVISION,
    MOTIVOS,
    MOTIVOS_QUE_NO_ENSENIAN,
    POR_PAGINA,
    PUNTAJE_PARA_MOSTRAR,
    PUNTAJE_PARA_REVISAR,
    RANGOS,
    SIN_ESCRIBIR,
    _sin_marcar,
    archivar,
    buscar_oferta,
    ofertas_de_la_empresa,
    clave_de_motivo,
    como_job,
    consejo_con_llm,
    contar_ofertas,
    contar_por_fecha,
    cv_para_oferta,
    es_recien_publicada,
    escritos_a_mano,
    filtros_del_perfil,
    guardar_feedback,
    marca_de_cambio,
    mensajes_con_llm,
    motivo_del_sistema,
    motivos_del_sistema,
    ofertas,
    partes_del_motivo,
    resumen_revision,
    revisar_filtro,
    texto_del_motivo,
    viejas_sin_marcar,
)
from vacantia.ui.data.metricas import (  # noqa: F401
    DIAS_DE_ENTRADAS,
    PERIODO_POR_DEFECTO,
    PERIODOS,
    TOPE_HABILIDADES,
    TRAMOS_PUNTAJE,
    aplicadas_en,
    descartadas_en,
    distribucion_de_puntajes,
    entradas_por_dia,
    estadisticas,
    habilidades_pedidas,
    pena_de_ingles,
)
from vacantia.ui.data.estado import _hace_cuanto, estado_del_sistema  # noqa: F401
