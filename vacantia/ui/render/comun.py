"""Lo que usan todas las pantallas: escapar, los iconos, los estáticos.

También el signo de pregunta con globo (`_ayuda_al_lado`) y sus dos
variantes para rótulos y tildes. Nacieron en el constructor de LinkedIn URLs
y viven acá porque `formulario.py` (Mi perfil y Configuración) los usa igual.
"""

from html import escape
from pathlib import Path

#: Cómo se abre el aviso en el portal. **`noreferrer` no es cosmético ni está
#: por privacidad: sin él, Computrabajo se rompe.**
#:
#: Sin `noreferrer` el navegador le cuenta al portal que venís de
#: `http://127.0.0.1:8756`, y Computrabajo guarda esa dirección en una cookie
#: propia (`extrfr`, de *external referrer*). A partir de ahí, **todos** los
#: pedidos de ese navegador al sitio llevan una URL a localhost adentro de una
#: cookie, que es la firma clásica de un ataque SSRF, y el firewall que tiene
#: delante contesta `403 Forbidden` en el sitio entero hasta que se borre la
#: cookie. No es un aviso el que falla: es uno que rompe todos los siguientes.
#:
#: Verificado el 7/9/2026 pegándole a un aviso con la cookie armada a mano:
#:
#:     extrfr=http://127.0.0.1:8756/trabajos       -> 403
#:     extrfr=http://localhost:8756/trabajos       -> 403
#:     extrfr=http%3A%2F%2F127.0.0.1%3A8756%2F...  -> 403  (tampoco zafa escapada)
#:     extrfr=https://ejemplo.com/x                -> 200  (un referrer normal no molesta)
#:     extrfr=127.0.0.1:8756/trabajos              -> 200  (sin el esquema no dispara)
#:     sin la cookie                               -> 200
#:
#: `noreferrer` implica `noopener`, así que reemplazarlo no pierde nada.
ABRIR_EL_AVISO = 'target="_blank" rel="noreferrer"'

# --- iconos -----------------------------------------------------------------
#
# Lucide, dibujados a mano acá adentro: son cuatro trazos y bajar una librería
# entera para eso sería pedirle a la red algo que la app no necesita. Todos con
# el mismo grosor de línea, que es lo que hace que se vean de la misma familia.

def _icono(trazos: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{trazos}</svg>')


ICONOS = {
    "trabajos": _icono('<rect width="20" height="14" x="2" y="7" rx="2"/>'
                       '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'),
    "linkedin": _icono('<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.8 1.7"/>'
                       '<path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.8-1.7"/>'),
    "estadisticas": _icono('<path d="M3 3v18h18"/><path d="M18 17V9"/>'
                           '<path d="M13 17V5"/><path d="M8 17v-3"/>'),
    "datos": _icono('<circle cx="12" cy="8" r="4.5"/><path d="M20 21a8 8 0 0 0-16 0"/>'),
    # Una cámara de video: las entrevistas se graban en Meet, Zoom o Teams.
    "entrevistas": _icono('<path d="m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 11"/>'
                          '<rect x="2" y="6" width="14" height="12" rx="2"/>'),
    "configuracion": _icono('<path d="M20 7h-9"/><path d="M14 17H5"/>'
                            '<circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>'),
    "filtradas": _icono('<path d="M3 5h18l-7 8v6l-4 2v-8Z"/>'),
    "mas": _icono('<circle cx="5" cy="12" r=".6"/><circle cx="12" cy="12" r=".6"/>'
                  '<circle cx="19" cy="12" r=".6"/>'),
    # El anillo del panel de "Buscando trabajo". Es un círculo entero más un
    # arco encima: el CSS gira sólo el arco, así que aun con el movimiento
    # apagado queda un anillo completo y no un gajo suelto que parece un error
    # de dibujo.
    "buscando": _icono('<circle class="aro" cx="12" cy="12" r="9"/>'
                       '<path class="arco" d="M21 12a9 9 0 0 0-9-9"/>'),
    # El tilde de un tramo cumplido. Sin círculo alrededor: al lado del punto
    # de los tramos que faltan, el tilde solo ya dice "éste pasó".
    "tilde-tramo": _icono('<path d="M4 12.5 9 17.5 20 6.5"/>'),
}

#: **El JavaScript de la pantalla vive en `static/app.js`, no acá**, y htmx en
#: `static/htmx.min.js`. Se sirven como archivos aparte, igual que el CSS y por
#: la misma razón: adentro de un string de Python no hay resaltado de sintaxis,
#: ni autocompletado, ni linter que te avise que te comiste un paréntesis.
#:
#: Se leen de disco en cada pedido, así que editás el archivo, apretás F5 y lo
#: ves. No hay que reiniciar el servidor.
#:
#: Dos `.parent` porque este archivo vive en `ui/render/` y `static/` está en
#: `ui/`, al lado del paquete.
ESTATICOS = Path(__file__).parent.parent / "static"


def estatico(nombre: str) -> str:
    """Un archivo de `static/`, tal cual está en disco.

    Binario y decodificado a mano: `read_text()` en Windows traduce los finales
    de línea, y el contenido tiene que salir byte por byte como se escribió.
    """
    return (ESTATICOS / nombre).read_bytes().decode("utf-8")


def esc(texto) -> str:
    """Escapa para HTML. Sólo `None` se convierte en vacío.

    Ojo con `texto or ""`, que fue el bug: el cero es falsy, así que una oferta
    puntuada 0 salía con la caja del puntaje en blanco. Y justo el 0 es el
    puntaje que más importa mostrar, porque es el que dice "esto no es para vos".
    """
    return escape("" if texto is None else str(texto), quote=True)


def avisos(mensajes: list[tuple[str, str]]) -> str:
    """[(clase, texto)] -> los carteles de arriba de todo."""
    return "".join(f'<div class="aviso {esc(c)}">{esc(t)}</div>' for c, t in mensajes)


# --- el signo de pregunta ------------------------------------------------

def _rotulo_con_ayuda(rotulo: str, ayuda: str) -> str:
    """El rótulo de un campo con el signo de pregunta al lado.

    El signo va **afuera** del `<label>`: adentro, pasarle el mouse o tocarlo
    marcaría la tilde, y lo que se quería era leer qué hace.
    """
    return f'<div class="rotulo-con-ayuda">{rotulo}{_ayuda_al_lado(ayuda, abajo=True)}</div>'


def _tilde_con_ayuda(nombre: str, etiqueta: str, marcada: bool, ayuda: str) -> str:
    return (f'<span class="tilde-con-ayuda"><label><input type="checkbox" '
            f'name="{esc(nombre)}" value="1"{" checked" if marcada else ""}> '
            f'{esc(etiqueta)}</label>{_ayuda_al_lado(ayuda, abajo=True)}</span>')


def _ayuda_al_lado(texto: str, abajo: bool = False) -> str:
    """El signo de pregunta que muestra la explicación al pasarle por encima.

    Para lo que hace falta una vez y estorba siempre. El texto largo suelto en
    la pantalla compite con el control que importa; escondido detrás de un
    ícono, está cuando se busca y no antes.

    **No es sólo hover.** Se abre también con el foco del teclado, porque quien
    tabula no pasa el mouse por ningún lado, y el texto está en el DOM desde el
    principio para que un lector de pantalla lo lea como nota del rótulo.

    Con `abajo`, el globo se abre hacia abajo y hacia la derecha. Es el de los
    rótulos del constructor: están arriba y a la izquierda de una columna que
    scrollea, y abierto hacia arriba y a la izquierda la columna lo cortaba.
    """
    clase = "ayuda-al-lado abajo" if abajo else "ayuda-al-lado"
    return (f'<span class="{clase}" tabindex="0" role="note">'
            f'<span class="signo" aria-hidden="true">?</span>'
            f'<span class="globo">{esc(texto)}</span></span>')
