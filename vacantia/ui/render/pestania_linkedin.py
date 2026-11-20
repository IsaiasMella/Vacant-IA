"""La pestaña LinkedIn URLs: los dos constructores, favoritos y sugeridas."""

from urllib.parse import quote, urlencode

from vacantia.fechas import dias_desde
from vacantia.ui.render.comun import (
    ABRIR_EL_AVISO,
    ICONOS,
    _ayuda_al_lado,
    _rotulo_con_ayuda,
    _tilde_con_ayuda,
    avisos,
    esc,
)
from vacantia.ui.render.pestania_trabajos import _en_hora_local

# --- pestaña LinkedIn URLs --------------------------------------------------
#
# El scraper trae lo publicado hace uno a tres días; los avisos de hoy no los
# indexó todavía ningún buscador y por eso no aparecen en Trabajos. Esta sección
# es la otra mitad: armar la dirección de búsqueda de LinkedIn que los muestra.
#
# Las dos pestañas son la misma pantalla: constructor a la izquierda, dirección
# y favoritos a la derecha, y el anotador de lo aplicado abajo del botón.

#: (clave, etiqueta). La primera es la que se abre por defecto.
#:
#: Publicaciones va primero porque es la que resuelve el agujero real: los
#: avisos que se publican como posteo del feed y nunca llegan a la pestaña Jobs.
#: Jobs el scraper lo trae, pero tarde y sin los filtros de poca competencia.
PESTANIAS_LINKEDIN = (
    ("publicaciones", "Publicaciones"),
    ("jobs", "Jobs"),
)


def _tildes(nombre: str, opciones, marcadas, columnas: bool = True) -> str:
    """Una fila de tildes. `marcadas` es el conjunto de los que vienen puestos."""
    puestas = {str(m).lower() for m in (marcadas or [])}
    tildes = "".join(
        f'<label><input type="checkbox" name="{esc(nombre)}" value="{esc(o)}"'
        f'{" checked" if str(o).lower() in puestas else ""}> {esc(o)}</label>'
        for o in opciones
    )
    return f'<div class="checks{" en-columnas" if columnas else ""}">{tildes}</div>'


def _desplegable(nombre: str, opciones, elegida: str, etiqueta: str,
                 ayuda: str = "") -> str:
    ops = "".join(
        f'<option value="{esc(c)}"{" selected" if c == elegida else ""}>{esc(e)}</option>'
        for c, e, *_ in opciones
    )
    rotulo = f'<label for="{esc(nombre)}">{esc(etiqueta)}</label>'
    if ayuda:
        rotulo = _rotulo_con_ayuda(rotulo, ayuda)
    return f"""<div class="campo">
  {rotulo}
  <select id="{esc(nombre)}" name="{esc(nombre)}">{ops}</select>
</div>"""


def _opciones(nombre: str, pares, marcadas, tipo: str = "checkbox") -> str:
    """Tildes o radios donde el valor no es lo que se lee (`f_WT=2` es Remoto)."""
    puestas = {str(m) for m in (marcadas or [])}
    return "".join(
        f'<label><input type="{tipo}" name="{esc(nombre)}" value="{esc(v)}"'
        f'{" checked" if str(v) in puestas else ""}> {esc(e)}</label>'
        for v, e, *_ in pares
    )


#: Los campos del constructor que hay que reponer al volver de un POST. El
#: orden es el de la pantalla, para que la dirección de la barra se lea igual
#: que el formulario.
_CAMPOS_DEL_ARMADOR = ("puestos", "lugares", "idioma", "sin_junior",
                       "cuando", "orden", "de_quien")


def _volver_al_armador(perfil: str, elegido: dict) -> str:
    """La query que devuelve esta misma pantalla, con lo mismo elegido.

    Los botones del contador son un POST: sin esto, anotar una postulación
    recargaría la pantalla en blanco y se perdería la búsqueda recién armada,
    que es justo lo que la persona está por usar.
    """
    if elegido.get("tab") == "jobs":
        return _volver_al_armador_jobs(perfil, elegido)
    partes: list[tuple[str, str]] = [("perfil", perfil), ("tab", "publicaciones")]
    partes += [("puesto", str(p)) for p in elegido.get("puestos") or []]
    partes += [("lugar", str(l)) for l in elegido.get("lugares") or []]
    partes.append(("idioma", str(elegido.get("idioma") or "es")))
    if elegido.get("sin_junior"):
        partes.append(("sin_junior", "1"))
    for clave, porde in (("cuando", "24h"), ("orden", "recientes"),
                         ("de_quien", "todos")):
        partes.append((clave, str(elegido.get(clave) or porde)))
    return urlencode(partes)


def _volver_al_armador_jobs(perfil: str, elegido: dict) -> str:
    """Lo mismo que `_volver_al_armador`, con los campos de la pestaña Jobs."""
    partes: list[tuple[str, str]] = [("perfil", perfil), ("tab", "jobs")]
    partes += [("puesto", str(p)) for p in elegido.get("puestos") or []]
    if elegido.get("tambien"):
        partes.append(("tambien", str(elegido["tambien"])))
    if elegido.get("sin_junior"):
        partes.append(("sin_junior", "1"))
    partes.append(("donde", str(elegido.get("donde") or "argentina")))
    partes += [("modalidad", str(m)) for m in elegido.get("modalidades") or []]
    partes += [("nivel", str(n)) for n in elegido.get("niveles") or []]
    for clave, porde in (("cuando", "24h"), ("orden", "recientes")):
        partes.append((clave, str(elegido.get(clave) or porde)))
    if elegido.get("pocos"):
        partes.append(("pocos", "1"))
    if elegido.get("sencilla"):
        partes.append(("sencilla", "1"))
    return urlencode(partes)


def _apliques(perfil: str, sin_confirmar: int, confirmadas: int,
              volver: str, tab: str = "publicaciones") -> str:
    """El anotador de lo que aplicaste desde un posteo de LinkedIn.

    Va acá y no en Trabajos porque acá es donde pasa: abrís la búsqueda, ves un
    posteo, escribís, y volvés. Marcarlo en otra pantalla sería acordarse
    después, y lo que no se marca en el momento no se marca nunca.

    Estas postulaciones no tienen ninguna oferta detrás: no entraron por el
    scraper y no están en el historial. Por eso hay que contarlas a mano, y por
    eso **suman al contador grande de Trabajos**: es el mismo trabajo.

    **Son dos pasos y no uno.** El más y el menos mueven un anotador que todavía
    no cuenta para nada; *Confirmar* lo pasa al contador de Trabajos y lo deja en
    cero. Un solo número que sube y nunca vuelve a cero no se puede confirmar:
    no habría forma de saber si lo que ves es lo de esta tanda o lo de toda la
    semana, ni de corregir un toque de más una hora después.

    **La forma es la de un stepper**, una sola pieza con los dos botones y el
    número adentro, y no tres cajas sueltas: tres cajas iguales no dicen que se
    tocan juntas ni cuál es el número y cuáles los botones.

    El verde es sólo del número y de *Confirmar*: en este sistema el verde
    significa lo que ya hiciste, y el más y el menos todavía no son nada. Y va
    con la palabra al lado, nunca sólo el color.

    La explicación larga vive adentro del signo de pregunta. Estaba suelta abajo
    del anotador, tres renglones de texto chico al pie de la barra, y competía
    con el único control de la pantalla que importa, que es *Armar la búsqueda*.
    """
    # A dónde volver viaja en la dirección del POST y no en un campo escondido:
    # el constructor es un GET, y un campo escondido más se colaría en la query
    # de "Armar la búsqueda" y crecería sobre sí mismo en cada armado.
    paso = ('type="submit" formmethod="post" '
            f'formaction="/linkedin-apliques?volver={quote(volver)}"')
    vacio = " disabled" if not sin_confirmar else ""
    ya = (f"Ya sumaste {confirmadas}." if confirmadas
          else "Todavía no sumaste ninguna.")
    if tab == "jobs":
        # El aviso de Jobs, a diferencia del posteo, puede haber entrado también
        # por el buscador automático: contarlo en los dos lados lo cuenta doble.
        explica = ("Contá acá lo que vayas mandando desde estas búsquedas y "
                   "confirmá al terminar. Si el aviso ya está en Trabajos, "
                   "marcalo ahí y no acá, para no contarlo dos veces. ")
    else:
        explica = "Contá acá lo que vayas mandando desde un posteo y confirmá al terminar. "
    return f"""<div class="apliques">
  <p class="rotulo">Apliqué desde acá{_ayuda_al_lado(
      explica +
      "Recién ahí suman al contador de Trabajos, y el anotador vuelve a cero. "
      "Lo que no confirmes sigue esperándote cuando volvés. " + ya)}</p>
  <div class="pasos">
    <span class="stepper">
      <button class="paso" {paso} name="menos" value="1"
              aria-label="Sacar una del anotador"{vacio}>&#8722;</button>
      <b class="numero">{sin_confirmar}</b>
      <button class="paso" {paso} name="suma" value="1"
              aria-label="Sumar una al anotador">+</button>
    </span>
    <button class="confirmar" {paso} name="confirmar" value="1"{vacio}>Confirmar</button>
  </div>
</div>"""


def _constructor(perfil: str, elegido: dict, puestos: list[str],
                 apliques: dict | None = None) -> str:
    """El formulario que arma la búsqueda.

    Es un `<form method="get">` y no JavaScript, como el filtro de antigüedad y
    el selector de perfil. Eso trae algo gratis: lo que elegiste queda en la
    dirección de esta misma pantalla, así que volver acá con el botón de atrás
    te devuelve el constructor como lo dejaste.
    """
    from vacantia.ui.linkedin_urls import (
        CUANDO, DE_QUIEN, EXCLUIR, GATILLOS_EN, GATILLOS_ES, LUGARES, ORDEN,
    )

    idioma = elegido.get("idioma", "es")
    gatillos = "".join(
        f'<label><input type="radio" name="idioma" value="{esc(c)}"'
        f'{" checked" if c == idioma else ""}> {esc(e)}</label>'
        for c, e in (("es", "En español"), ("en", "En inglés"), ("ambos", "Los dos"))
    )

    return f"""<form class="datos armador" method="get" action="/linkedin">
<input type="hidden" name="perfil" value="{esc(perfil)}">
<input type="hidden" name="tab" value="publicaciones">

<h2>Qué buscar</h2>
<div class="grilla">
  <div class="campo ancho">
    <label>Puestos</label>
    {_tildes("puesto", puestos, elegido.get("puestos"))}
    <p class="ayuda">Se buscan todos juntos: alcanza con que el posteo diga uno.
    Salen de <b>Puestos a buscar</b>, en
    <a href="/datos?perfil={esc(perfil)}">Mi perfil</a>: lo que agregues o saques
    ahí aparece o desaparece de acá.</p>
  </div>
  <div class="campo ancho">
    <label>Cómo lo escribe quien contrata</label>
    <div class="checks">{gatillos}</div>
    <p class="ayuda">Es lo que separa un posteo que habla del tema de uno que
    ofrece trabajo: {esc(GATILLOS_ES[0])}, {esc(GATILLOS_ES[1])}, {esc(GATILLOS_EN[0])}.</p>
  </div>
  <div class="campo">
    <label>Dónde</label>
    {_tildes("lugar", LUGARES, elegido.get("lugares"), columnas=False)}
  </div>
  <div class="campo">
    <label>Qué dejar afuera</label>
    <div class="checks">
      <label><input type="checkbox" name="sin_junior" value="1"
      {" checked" if elegido.get("sin_junior") else ""}> Puestos junior</label>
    </div>
    <p class="ayuda">Saca {esc(", ".join(EXCLUIR))}.</p>
  </div>
</div>

<h2>Cómo mostrarlo</h2>
<div class="grilla">
  {_desplegable("cuando", CUANDO, elegido.get("cuando", "24h"), "Publicado hace")}
  {_desplegable("orden", ORDEN, elegido.get("orden", "recientes"), "Ordenar por")}
  {_desplegable("de_quien", DE_QUIEN, elegido.get("de_quien", "todos"), "Publicado por")}
</div>

<div class="guardar">
  <button class="primario" type="submit">Armar la búsqueda</button>
  {_apliques(perfil, (apliques or {}).get("pendientes", 0),
              (apliques or {}).get("confirmadas", 0),
              _volver_al_armador(perfil, elegido))}
</div>
</form>"""


def _constructor_jobs(perfil: str, elegido: dict, puestos: list[str],
                      apliques: dict | None = None) -> str:
    """El constructor de la pestaña Jobs. La misma forma que el de Publicaciones.

    Mismo formulario GET, mismas dos secciones, el mismo botón y el mismo
    anotador abajo: quien aprendió a usar una pestaña ya sabe usar la otra.
    Cambia lo que se elige, porque LinkedIn Jobs filtra por otras cosas.

    Lo que no se entiende con leer el rótulo lleva el signo de pregunta, igual
    que el anotador: nivel, menos de 10 candidatos, solicitud sencilla. Escrito
    suelto al pie de cada campo, eran seis párrafos compitiendo con el botón.
    """
    from vacantia.ui.linkedin_urls import (
        CUANDO_JOBS, DONDE_JOBS, EXCLUIR_JOBS, MODALIDADES, NIVELES, ORDEN_JOBS,
    )

    donde = elegido.get("donde") or "argentina"
    return f"""<form class="datos armador" method="get" action="/linkedin">
<input type="hidden" name="perfil" value="{esc(perfil)}">
<input type="hidden" name="tab" value="jobs">

<h2>Qué buscar</h2>
<div class="grilla">
  <div class="campo ancho">
    <label>Puestos</label>
    {_tildes("puesto", puestos, elegido.get("puestos"))}
    <p class="ayuda">Se buscan todos juntos: alcanza con que el aviso diga uno.
    Salen de <b>Puestos a buscar</b>, en
    <a href="/datos?perfil={esc(perfil)}">Mi perfil</a>.</p>
  </div>
  <div class="campo ancho">
    {_rotulo_con_ayuda('<label for="tambien">Que además diga</label>',
        "Palabras que el aviso tiene que tener, además del puesto, separadas "
        "por coma. Alcanza con que tenga una de ellas. Sirve para quedarte con "
        "los que piden lo tuyo, por ejemplo: Python, RAG, OpenAI. Al entrar "
        "viene con tus Habilidades de Mi perfil; borralo y no filtra nada.")}
    <input type="text" id="tambien" name="tambien" value="{esc(elegido.get("tambien", ""))}"
           placeholder="Python, RAG, OpenAI">
  </div>
  <div class="campo">
    {_rotulo_con_ayuda("<label>Dónde</label>",
        "Argentina incluye los remotos que LinkedIn ofrece para Argentina. "
        "Cualquier lugar agranda mucho la lista, y la mayoría de lo que suma "
        "pide inglés.")}
    <div class="checks">{_opciones("donde", DONDE_JOBS, [donde], tipo="radio")}</div>
  </div>
  <div class="campo">
    {_rotulo_con_ayuda("<label>Modalidad</label>",
        "Sin tildar ninguna, entran todas.")}
    <div class="checks">{_opciones("modalidad", MODALIDADES, elegido.get("modalidades"))}</div>
  </div>
  <div class="campo ancho">
    {_rotulo_con_ayuda("<label>Nivel</label>",
        "Son los niveles de LinkedIn. No hay uno que sea sólo Senior: "
        "«Intermedio» es su Mid-Senior, y ahí se cuelan semi seniors. Por eso "
        "conviene tildar también «Puestos junior y semi senior» en Qué dejar "
        "afuera. Sin tildar ninguno, entran todos.")}
    <div class="checks">{_opciones("nivel", NIVELES, elegido.get("niveles"))}</div>
  </div>
  <div class="campo ancho">
    <label>Qué dejar afuera</label>
    <div class="checks">
      <label><input type="checkbox" name="sin_junior" value="1"
      {" checked" if elegido.get("sin_junior") else ""}> Puestos junior y semi senior</label>
    </div>
    <p class="ayuda">Saca {esc(", ".join(EXCLUIR_JOBS))}.</p>
  </div>
</div>

<h2>Cómo mostrarlo</h2>
<div class="grilla">
  {_desplegable("cuando", CUANDO_JOBS, elegido.get("cuando", "24h"), "Publicado hace",
      ayuda="Última hora es para revisar dos o tres veces por día: llegás "
            "entre los primeros. Una semana es para un barrido, una vez por día.")}
  {_desplegable("orden", ORDEN_JOBS, elegido.get("orden", "recientes"), "Ordenar por")}
  <div class="campo ancho">
    <label>Poca competencia</label>
    <div class="checks">
      {_tilde_con_ayuda("pocos", "Menos de 10 candidatos", bool(elegido.get("pocos")),
          "Sólo los avisos a los que se postularon menos de 10 personas. Es "
          "donde tu CV tiene más chances de que alguien lo lea. Junto con "
          "Última hora, trae poco: si da cero, sacá uno de los dos.")}
      {_tilde_con_ayuda("sencilla", "Solicitud sencilla", bool(elegido.get("sencilla")),
          "Sólo los avisos que se aplican adentro de LinkedIn, en un clic, con "
          "el CV que tenés cargado allá. Sirven para mandar muchos rápido; los "
          "demás te llevan a la página de la empresa.")}
    </div>
  </div>
</div>

<div class="guardar">
  <button class="primario" type="submit">Armar la búsqueda</button>
  {_apliques(perfil, (apliques or {}).get("pendientes", 0),
              (apliques or {}).get("confirmadas", 0),
              _volver_al_armador_jobs(perfil, elegido), tab="jobs")}
</div>
</form>"""


def _bloque_de_url(perfil: str, url: str, nombre: str, ya_guardada: bool,
                   tab: str = "publicaciones") -> str:
    """La dirección armada, entera y a la vista.

    **Nunca escondida detrás de un botón.** La persona tiene que poder leerla
    antes de usarla: es un texto largo con comillas y paréntesis que LinkedIn a
    veces interpreta distinto, y si algo sale raro lo primero que se mira es
    esto.

    La acción principal es abrirla, no copiarla: no vino a llevarse un texto,
    vino a ver los posteos.
    """
    guardar = "" if ya_guardada else f"""<form class="guardar-favorito" method="post" action="/linkedin-favorito">
  <input type="hidden" name="perfil" value="{esc(perfil)}">
  <input type="hidden" name="tab" value="{esc(tab)}">
  <input type="hidden" name="url" value="{esc(url)}">
  <label for="nombre-fav">Nombre</label>
  <input type="text" id="nombre-fav" name="nombre" value="{esc(nombre)}">
  <button type="submit">Guardar en favoritos</button>
</form>"""
    ya = ('<p class="ayuda">Esta búsqueda ya está en tus favoritos.</p>'
          if ya_guardada else "")

    return f"""<section class="armada" aria-label="La búsqueda armada">
  <h2>Tu búsqueda</h2>
  <p class="url-generada">{esc(url)}</p>
  <p class="herramientas">
    <a class="boton primario" href="{esc(url)}" {ABRIR_EL_AVISO}>Abrir en LinkedIn</a>
    <button type="button" onclick="copiar(this, {esc(url)!r})">Copiar link</button>
  </p>
  {guardar}{ya}
  <p class="ayuda">{"Al abrirla, LinkedIn cae en Empleos con los filtros puestos: "
                    "fijate arriba de la lista que figuren todos." if tab == "jobs" else
                    "Al abrirla, LinkedIn cae directo en la pestaña Publicaciones "
                    "con los filtros puestos."} Si algún día deja de filtrar, rehacé
  los filtros a mano en LinkedIn y pegá acá la dirección nueva.</p>
</section>"""


def _aviso_de_recorte(entraron: dict | None, pedidos: dict | None) -> str:
    """Cuando el texto no entra, se recorta. Hay que decirlo.

    LinkedIn no avisa que la búsqueda es muy larga: aplica los filtros, muestra
    "No se han encontrado resultados" y te deja creyendo que no hay vacantes.
    Medido: con seis frases devuelve cero, con cuatro trae posteos de hace un
    minuto. Así que se recorta, pero callarlo sería peor que el problema: la
    persona creería que está buscando "vacante" y en realidad no.
    """
    entraron, pedidos = entraron or {}, pedidos or {}
    faltan = []
    if (n := pedidos.get("gatillos", 0) - entraron.get("gatillos", 0)) > 0:
        faltan.append(f"{n} " + ("frase de las que dijiste que usan"
                                 if n == 1 else "frases de las que dijiste que usan"))
    if (n := pedidos.get("excluir", 0) - entraron.get("excluir", 0)) > 0:
        faltan.append(f"{n} " + ("palabra de las que querías dejar afuera"
                                 if n == 1 else "palabras de las que querías dejar afuera"))
    if not faltan:
        return ""
    return f"""<div class="callout atencion">
  <p>Quedaron afuera {" y ".join(faltan)}: con más, LinkedIn devuelve cero
  resultados y no avisa por qué.</p>
  <p class="ayuda">Se conservaron las que más rinden. Si querés las otras, armá
  una segunda búsqueda y guardala aparte: dos búsquedas cortas traen más que una
  larga que no trae nada.</p>
</div>"""


def _todavia_sin_armar() -> str:
    """El lugar de la dirección, mientras no haya ninguna.

    La columna de la derecha existe siempre, así que el hueco se nombra en vez
    de dejarlo en blanco: al entrar por primera vez, esto dice de dónde va a
    salir lo que va a aparecer acá.
    """
    return """<section class="armada" aria-label="La búsqueda armada">
  <h2>Tu búsqueda</h2>
  <div class="vacio"><b>Todavía no armaste ninguna.</b>
  Elegí a la izquierda qué buscar y apretá el botón de abajo de todo, «Armar la
  búsqueda». La dirección aparece acá, entera y a la vista, para que puedas
  leerla antes de abrirla.</div>
</section>"""


def _sugeridas(perfil: str, sugeridas: list[dict], guardados: list[dict],
               tab: str = "publicaciones") -> str:
    """Las búsquedas que conviene tener, armadas con tus puestos (ver
    `linkedin_urls.sugeridas`). Cada una se abre o se guarda con un toque.

    Las que ya guardaste no se repiten acá: ya están abajo, en tus guardadas.
    Si están todas guardadas, la sección desaparece.
    """
    ya = {f.get("url") for f in guardados}
    quedan = [s for s in sugeridas if s.get("url") not in ya]
    if not quedan:
        return ""
    if tab == "jobs":
        explica = ("Avisos de las últimas 2 horas, remotos y con menos de 10 "
                   "candidatos: llegás entre los primeros. Abrilas dos o tres "
                   "veces por día. Los puestos en castellano no van: en Empleos "
                   "traen los mismos avisos que en inglés.")
    else:
        explica = ("Posteos de las últimas 24 horas que dicen «buscamos» o «estamos "
                   "buscando», con tus puestos en grupos chicos: con más de 110 "
                   "letras LinkedIn devuelve cero. Los puestos en castellano van "
                   "primero, porque acá sí traen posteos en castellano.")
    filas = "".join(f"""<li class="favorito sugerida">
  <div class="datos">
    <h3>{esc(s["nombre"])}</h3>
    <p class="url-generada chica">{esc(s["url"])}</p>
  </div>
  <div class="acciones">
    <a class="boton" href="{esc(s["url"])}" {ABRIR_EL_AVISO}>Abrir</a>
    <form method="post" action="/linkedin-favorito">
      <input type="hidden" name="perfil" value="{esc(perfil)}">
      <input type="hidden" name="tab" value="{esc(tab)}">
      <input type="hidden" name="url" value="{esc(s["url"])}">
      <input type="hidden" name="nombre" value="{esc(s["nombre"])}">
      <button type="submit">Guardar</button>
    </form>
  </div>
</li>""" for s in quedan)
    return f"""<div class="titulo-con-ayuda"><h2>Sugeridas para vos</h2>{_ayuda_al_lado(explica, abajo=True)}</div>
<ul class="favoritos sugeridas">{filas}</ul>"""


def _favoritos(perfil: str, guardados: list[dict], tab: str = "publicaciones") -> str:
    """Las búsquedas que ya sabés que sirven, para no rearmarlas cada vez.

    En Jobs el título lleva la rutina del documento de estrategia adentro del
    signo de pregunta: es lo que dice qué guardar y cuándo abrirlo.
    """
    titulo = "<h2>Tus búsquedas guardadas</h2>"
    if tab == "jobs":
        titulo = ('<div class="titulo-con-ayuda"><h2>Tus búsquedas guardadas</h2>'
                  + _ayuda_al_lado(
                      "A la mañana, abrí las de última hora, la de menos de 10 "
                      "candidatos y la de solicitud sencilla, y aplicá a todo lo "
                      "que sirva. Después, un barrido de la última semana. A la "
                      "tarde, de nuevo las de última hora: ya traen avisos nuevos.",
                      abajo=True)
                  + "</div>")
    if not guardados:
        que = "avisos" if tab == "jobs" else "posteos"
        return f"""{titulo}
<div class="vacio"><b>Todavía no guardaste ninguna.</b>
Cuando armes una búsqueda que te traiga {que} que sirven, guardala acá y la
volvés a abrir de un toque. La idea es tener cuatro o cinco y revisarlas dos
veces por día: los {que} buenos duran horas.</div>"""

    filas = []
    for f in guardados:
        cuando = _en_hora_local(f.get("guardada"))
        dias = dias_desde(cuando) if cuando else None
        desde = ("hoy" if dias == 0 else "ayer" if dias == 1
                 else f"hace {dias} días" if dias else "")
        filas.append(f"""<li class="favorito">
  <div class="datos">
    <h3>{esc(f.get("nombre"))}</h3>
    {f'<p class="cuando">Guardada {esc(desde)}</p>' if desde else ''}
    <p class="url-generada chica">{esc(f.get("url"))}</p>
  </div>
  <div class="acciones">
    <a class="boton primario" href="{esc(f.get("url"))}" {ABRIR_EL_AVISO}>Abrir</a>
    <details class="menu">
      <summary title="Más opciones" aria-label="Más opciones">{ICONOS['mas']}</summary>
      <div class="panel">
        <button type="button" onclick="copiar(this, {esc(f.get("url"))!r})">Copiar link</button>
        <form method="post" action="/linkedin-favorito">
          <input type="hidden" name="perfil" value="{esc(perfil)}">
          <input type="hidden" name="tab" value="{esc(tab)}">
          <input type="hidden" name="url" value="{esc(f.get("url"))}">
          <button class="fantasma" name="borrar" value="1">Sacar de favoritos</button>
        </form>
      </div>
    </details>
  </div>
</li>""")
    return f"""{titulo}
<ul class="favoritos">{"".join(filas)}</ul>"""


def linkedin(perfil: str, tab: str, mensajes: list[tuple[str, str]],
             elegido: dict | None = None, url: str = "",
             guardados: list[dict] | None = None,
             puestos: list[str] | None = None,
             apliques: dict | None = None,
             sugeridas: list[dict] | None = None) -> str:
    """Las direcciones de búsqueda de LinkedIn, en dos pestañas.

    Las pestañas son navegación adentro de la sección, no un filtro, y por eso
    van arriba del contenido y no adentro de una tarjeta. Para filtrar están las
    píldoras de la lista de trabajos.
    """
    from vacantia.ui.linkedin_urls import (
        PUESTOS_SUGERIDOS, nombre_sugerido, nombre_sugerido_jobs,
    )

    if tab not in dict(PESTANIAS_LINKEDIN):
        tab = PESTANIAS_LINKEDIN[0][0]
    elegido = {**(elegido or {}), "tab": tab}
    guardados = guardados or []
    puestos = puestos or list(PUESTOS_SUGERIDOS)

    botones = "".join(
        f'<a class="pestania{" activa" if clave == tab else ""}" '
        f'href="/linkedin?perfil={esc(perfil)}&tab={esc(clave)}"'
        f'{" aria-current=page" if clave == tab else ""}>{esc(etiqueta)}</a>'
        for clave, etiqueta in PESTANIAS_LINKEDIN
    )

    ya = any(f.get("url") == url for f in guardados)
    if tab == "jobs":
        nombre = nombre_sugerido_jobs(elegido.get("puestos"), elegido.get("cuando", "24h"),
                                      bool(elegido.get("pocos")),
                                      bool(elegido.get("sencilla")))
        controles = _constructor_jobs(perfil, elegido, puestos, apliques)
        # En Jobs no se recorta nada: el tope de largo es del buscador de posteos.
        recorte = ""
        sub = """Los avisos de la pestaña Empleos, apenas salen. El buscador
automático también los trae, pero tarde y sin los filtros que más rinden:
publicado hace una hora, menos de 10 candidatos, solicitud sencilla. Esos sólo
los ve quien entra logueado."""
    else:
        nombre = nombre_sugerido(elegido.get("puestos"), elegido.get("cuando", "24h"),
                                 elegido.get("idioma") == "en")
        controles = _constructor(perfil, elegido, puestos, apliques)
        recorte = _aviso_de_recorte(elegido.get("entraron"), elegido.get("pedidos"))
        sub = """Muchas vacantes se publican como un posteo del muro y nunca llegan
a la pestaña de empleos. El buscador las indexa uno a tres días tarde, cuando ya
se llenaron de postulantes. Estas direcciones las muestran apenas se publican."""

    # Dos columnas: a la izquierda lo que elegís, a la derecha lo que sale.
    # Antes iba todo en una sola columna larga y la dirección aparecía abajo
    # de todo, fuera de pantalla; encima el formulario es GET, así que al
    # armarla la página se recargaba y el navegador la abría arriba. Así, el
    # resultado nace al lado de los controles y nada se mueve.
    cuerpo = f"""<div class="taller">
<div class="lado controles">{controles}</div>
<div class="lado resultado">{recorte}\
{_bloque_de_url(perfil, url, nombre, ya, tab) if url else _todavia_sin_armar()}\
{_sugeridas(perfil, sugeridas or [], guardados, tab)}\
{_favoritos(perfil, guardados, tab)}</div>
</div>"""

    return f"""{avisos(mensajes)}
<h1>LinkedIn URLs</h1>
<p class="sub">{sub}</p>
<nav class="pestanias" aria-label="Tipo de búsqueda">{botones}</nav>
{cuerpo}"""
