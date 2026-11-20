"""El HTML de la UI. Sin plantillas ni librerías: strings y f-strings.

La hoja de estilos vive en `estilos.py` y es la implementación de `DESIGN.md`.
Acá sólo se arma el marcado, y hay tres reglas que mandan sobre cualquier otra
consideración cuando se toca una pantalla:

1. **Una decisión por vez.** En pantalla está la acción que la persona vino a
   hacer. Los controles secundarios aparecen cuando se necesitan, no antes. En
   la tarjeta de oferta eso es una regla dura: **más de dos controles visibles
   por oferta es un error de diseño.**
2. **Nunca mostrar lo que la persona se pierde antes de lo que puede hacer.**
   Los recuentos de ofertas inalcanzables son información legítima y viven en
   Métricas, con la explicación y con el link a la sección donde se arregla.
   Arriba de la lista de trabajos no va ningún recuento de pérdidas.
3. **El estado del sistema es siempre visible.** Cuándo buscó, cuándo vuelve a
   buscar, qué ventana de días cubre. Tiene lugar fijo al pie de la barra
   lateral, en castellano llano, y es texto estático: cambia cuando cambia el
   dato, no solo.

**Cómo está repartido.** Antes era un solo `render.py` de casi 2.500 líneas;
ahora es un paquete con un módulo por pestaña, y este `__init__` re-exporta
los nombres de siempre para que `from vacantia.ui import render` y
`render.trabajos(...)` sigan andando igual desde `server.py`, `formulario.py`
y los tests:

- `comun`: lo que usan todas las pantallas. `esc`, `estatico`, los iconos,
  `ABRIR_EL_AVISO`, `avisos` y el signo de pregunta con globo.
- `shell`: la barra lateral, el estado del sistema, el botón de Buscar ahora
  y el panel de "Buscando trabajo". `pagina()` es el shell entero.
- `pestania_trabajos`: la pestaña Trabajos y la tarjeta de oferta.
- `pestania_linkedin`: la pestaña LinkedIn URLs, con sus dos constructores.
- `pestania_metricas`: la pestaña Métricas.
- `mensajes_y_consejo`: los mensajes para el reclutador y el consejo sobre
  el CV, que se abren desde la tarjeta.
"""

# Re-exportados: son los nombres que se usan como `render.X` desde afuera.
# Los privados que están acá los importan `formulario.py` o los tests.
from vacantia.ui.render.comun import (  # noqa: F401
    ABRIR_EL_AVISO,
    ESTATICOS,
    ICONOS,
    _ayuda_al_lado,
    _rotulo_con_ayuda,
    _tilde_con_ayuda,
    avisos,
    esc,
    estatico,
)
from vacantia.ui.render.mensajes_y_consejo import consejo, linea_de_cv, mensajes  # noqa: F401
from vacantia.ui.render.pestania_entrevistas import (  # noqa: F401
    entrevista,
    entrevistas,
    estado_en_curso,
)
from vacantia.ui.render.pestania_linkedin import PESTANIAS_LINKEDIN, linkedin  # noqa: F401
from vacantia.ui.render.pestania_metricas import (  # noqa: F401
    ESCRITOS_A_LA_VISTA,
    _desglose,
    estadisticas,
)
from vacantia.ui.render.pestania_trabajos import (  # noqa: F401
    FILTROS,
    RANGOS,
    VACIO,
    _cuando_marcada,
    _tarjeta,
    trabajos,
)
from vacantia.ui.render.shell import (  # noqa: F401
    LATIDO_BUSCANDO,
    LATIDO_QUIETO,
    SECCION_AL_PIE,
    SECCIONES_BUSCAR,
    SECCIONES_RESTO,
    _cuanto_hace,
    corrida_estado,
    pagina,
    panel_de_busqueda,
)


def __getattr__(nombre: str):
    """`render.JS` y `render.CSS` siguen andando, leyendo el archivo de ahora.

    Son los nombres que existían cuando el código estaba adentro de strings de
    Python. Los usan los tests, y al leer en el momento un test mira lo que hay
    en disco y no lo que había cuando se importó el módulo.
    """
    if nombre == "JS":
        return estatico("app.js")
    if nombre == "CSS":
        from vacantia.ui import estilos

        return estilos.hoja()
    raise AttributeError(f"module {__name__!r} no tiene {nombre!r}")
