"""La pestaña Trabajos: la lista de ofertas y la tarjeta de cada una."""

from datetime import date, datetime  # noqa: F401  (date, para la anotación)
from urllib.parse import quote

from vacantia.fechas import dias_desde, fecha_de, parse_posted
from vacantia.ui.render.comun import ABRIR_EL_AVISO, ICONOS, avisos, esc
from vacantia.ui.render.mensajes_y_consejo import linea_de_cv
from vacantia.ui.render.pestania_metricas import _MOTIVOS_SISTEMA
from vacantia.ui.render.shell import _boton_buscar

# --- pestaña Trabajos -------------------------------------------------------

FILTROS = (
    ("pendientes", "Sin marcar"),
    ("aplicadas", "Apliqué"),
    ("descartadas", "Descarté"),
    ("filtradas", "Filtradas"),
    ("archivadas", "Archivadas"),
    ("todas", "Todas"),
)

#: El otro eje: qué tan viejo es el aviso. Se cruza con FILTROS, no lo reemplaza.
RANGOS = (
    ("hoy", "Hoy"),
    ("7d", "Últimos 7 días"),
    ("30d", "Últimos 30 días"),
    ("todo", "Sin filtro"),
)


def _cuando(oferta: dict) -> tuple[str, str]:
    """(texto, título) del chip de fecha.

    Distingue "publicado" de "visto" a propósito. Casi la mitad de los avisos no
    dicen cuándo se publicaron y ahí se cae a la fecha en que lo encontramos,
    que puede ser mucho más nueva: un aviso de hace tres meses encontrado ayer
    parecería de ayer. Decir cuál de las dos es cuesta una palabra.
    """
    momento, publicada = fecha_de(oferta)
    if momento is None:
        return "sin fecha", "El aviso no dice cuándo se publicó."
    dias = dias_desde(momento) or 0
    if publicada:
        cuando = "publicado hoy" if dias <= 0 else f"publicado hace {dias} d"
        return cuando, f"El aviso dice que se publicó el {momento.isoformat()}."
    visto = "visto hoy" if dias <= 0 else f"visto hace {dias} d"
    return visto, ("El aviso no dice cuándo se publicó. Esta es la fecha en que "
                   f"lo encontramos ({momento.isoformat()}): el aviso puede ser "
                   "bastante más viejo.")


def _en_hora_local(guardada) -> "date | None":
    """El día local de una marca de tiempo guardada en UTC.

    Si no trae hora, o no se entiende, cae en `parse_posted`, que ya sabe leer
    todos los formatos que aparecen en el historial.
    """
    crudo = str(guardada or "").strip()
    if not crudo:
        return None
    try:
        momento = datetime.fromisoformat(crudo.replace("Z", "+00:00"))
    except ValueError:
        return parse_posted(crudo[:10])
    if momento.tzinfo is None:      # una fecha sola, sin hora ni zona
        return momento.date()
    return momento.astimezone().date()


def _cuando_marcada(oferta: dict) -> tuple[str, str]:
    """(texto, título) de cuándo se marcó. Vacío si no hay fecha guardada.

    La fecha se guarda en UTC y hay que pasarla a la hora de acá **antes** de
    quedarse con el día. Cortando los primeros diez caracteres del texto, todo
    lo que marcabas entre las 21:00 y la medianoche quedaba con la fecha de
    mañana en UTC, y al día siguiente la tarjeta decía "Aplicaste hoy" a algo de
    ayer. Son tres horas por día, justo las que más se usa la pantalla.
    """
    momento = _en_hora_local(oferta.get("fecha_feedback"))
    if momento is None:
        return "", ""
    dias = dias_desde(momento) or 0
    cuando = ("hoy" if dias <= 0 else "ayer" if dias == 1 else f"hace {dias} días")
    return cuando, f"El {momento.isoformat()}"


def _select_de_motivos() -> str:
    """El desplegable de por qué no apliqué.

    Con 60 descartes se vio en qué se convierte un campo de texto obligatorio:
    46 veces la misma frase escrita a mano. Los motivos salen de lo que de
    verdad se escribió, no de lo que uno imagina que se va a escribir.

    Al lado queda el campo de texto, **opcional**: con cualquiera de los dos
    alcanza para descartar. No hay una opción "Otro motivo" en la lista a
    propósito — obligaba a abrir el desplegable, bajar hasta "Otro" y recién ahí
    escribir, tres pasos de más justo en el caso en que ya tenías la mano en el
    teclado.
    """
    from vacantia.ui.data import MOTIVOS

    opciones = "".join(
        f'<option value="{esc(clave)}" title="{esc(ayuda)}">{esc(etiqueta)}</option>'
        for clave, etiqueta, ayuda in MOTIVOS
    )
    return (f'<select name="motivo_clave" aria-label="Motivo del descarte">'
            f'<option value="">Por qué no apliqué…</option>{opciones}</select>')


def _cabecera_de_tarjeta(oferta: dict) -> str:
    """Puntaje, título y etiquetas: lo que se lee de un vistazo."""
    score = oferta.get("score")
    clase = "puntaje alto" if isinstance(score, int) and score >= 70 else "puntaje"
    titulo = oferta.get("scored_title") or oferta.get("title") or "(sin título)"
    lugar = oferta.get("location_remote") or oferta.get("location") or ""
    url = oferta.get("url", "")

    # Cada dato en su propia etiqueta, en vez de una tira separada por puntos.
    # Con cuatro datos la tira quedaba "ACME · Remoto · linkedin · 2026-09-04",
    # que se lee como una sola frase larga y no deja distinguir qué es cada cosa.
    cuando, detalle_fecha = _cuando(oferta)
    etiquetas = "".join(
        f'<li class="{cls}">{esc(valor)}</li>'
        for valor, cls in (
            (oferta.get("company"), "empresa"),
            (lugar, "lugar"),
            (oferta.get("source"), "origen"),
        )
        if valor
    )
    etiquetas += (f'<li class="cuando" title="{esc(detalle_fecha)}">'
                  f'{esc(cuando)}</li>')

    return f"""  <div class="{clase}">{esc(score if score is not None else '?')}<span class="de">de 100</span></div>
  <div class="datos">
    <h3><a href="{esc(url)}" {ABRIR_EL_AVISO}>{esc(titulo)}</a></h3>
    <ul class="datos-meta">{etiquetas}</ul>"""


def _ocultos(perfil: str, ver: str, desde: str, pagina: int, url: str) -> str:
    return (f'<input type="hidden" name="perfil" value="{esc(perfil)}">'
            f'<input type="hidden" name="ver" value="{esc(ver)}">'
            f'<input type="hidden" name="desde" value="{esc(desde)}">'
            f'<input type="hidden" name="p" value="{pagina}">'
            f'<input type="hidden" name="url" value="{esc(url)}">')


def _tarjeta_filtrada(oferta: dict, perfil: str, desde: str, pagina: int,
                      cabecera: str) -> str:
    """Una oferta que descartó el sistema solo, para auditar si acertó.

    Lo que se lee acá es distinto de lo que se lee en Sin marcar. En Sin marcar
    la pregunta es "¿me postulo?"; acá es "¿el filtro acertó?", y para
    contestarla hacen falta dos cosas juntas: **los motivos que dio el sistema**
    y **el aviso**, para poder ir a mirarlo. Por eso van arriba de todo y con su
    explicación completa, y no escondidos en un tooltip.

    **Van todos los motivos, no el primero.** Una oferta puede caer por idioma y
    por lugar a la vez, y mostrando uno solo la pantalla mentía: si el que se
    mostraba estaba mal atribuido, la respuesta honesta era "mal descartada" y
    la oferta volvía a la lista aunque el otro motivo la sacara con derecho.

    **Tres respuestas y no dos.** Faltaba justo la del medio, que es la que
    apareció usándolo: bien sacada, pero por el motivo equivocado. Con dos
    botones eso había que contestarlo mintiendo para un lado o para el otro.
    Sólo "mal" devuelve la oferta a Sin marcar; las otras dos la dejan afuera,
    que es lo correcto, y se cuentan por separado para poder ver qué filtro es
    el que atribuye mal.
    """
    url = oferta.get("url", "")
    razon = oferta.get("reason") or ""
    motivos = oferta.get("_motivos_sistema") or []
    if not motivos:
        motivos = [("", "")]
    porques = "".join(
        f'<p class="por-que"><b>{esc(_MOTIVOS_SISTEMA.get(clave, "El sistema la descartó"))}</b>'
        f'{f"""<span class="detalle">{esc(explica)}</span>""" if explica else ""}</p>'
        for clave, explica in motivos
    )
    # Desde el 17/9/2026 hay cuatro filtros, así que pueden ser más de dos.
    cuantos = "los dos" if len(motivos) == 2 else f"los {len(motivos)}"
    y_ademas = (f'<p class="ayuda">Cae por {cuantos}: alcanza con que uno esté bien '
                'para que no tenga que llegarte.</p>' if len(motivos) > 1 else "")
    return f"""<article class="oferta filtrada">
{cabecera}
    {porques}{y_ademas}
    {f'<p class="razon">{esc(razon)}</p>' if razon else ''}
    <form class="acciones" method="post" action="/revisar-filtro">
      {_ocultos(perfil, "filtradas", desde, pagina, url)}
      <button class="primario" name="revision" value="bien"
              onclick="return marcar(this, false)">Bien descartada</button>
      <button name="revision" value="motivo"
              onclick="return marcar(this, false)">Bien, motivo equivocado</button>
      <button name="revision" value="mal"
              onclick="return marcar(this, false)">Mal descartada</button>
      <span class="ayuda">Sólo <b>Mal descartada</b> la devuelve a Sin marcar
      para que puedas aplicar.</span>
    </form>
  </div>
</article>"""


def _tarjeta(oferta: dict, perfil: str, ver: str, desde: str = "todo",
             pagina: int = 1) -> str:
    """Una oferta.

    Es el componente central de la app y el que más disciplina necesita. Por
    defecto se ven **dos controles y nada más**: "Apliqué" en primario y "No
    apliqué" en secundario. El bloque de motivo se despliega adentro de la misma
    tarjeta recién cuando se marca "No apliqué"; los links auxiliares viven en
    el menú de tres puntos de la esquina.

    **"Archivar" está a la vista, en fantasma.** Es "no le doy bola a esta
    oferta", por la razón que sea: muy vieja, no era una oferta, o cualquier
    otra que no vale la pena explicar. Vivió en ese menú como "Ya no está", que
    lo achicaba a los avisos vencidos, y en la práctica desapareció. Isaías lo
    pidió a la vista el 25/9/2026. Es el único tercer control permitido, y en
    fantasma para no competir con los otros dos.

    Una vez marcada, la tarjeta pierde el vidrio esmerilado y baja a superficie
    plana: así se distingue de un vistazo lo que queda por hacer de lo que ya
    está hecho.
    """
    url = oferta.get("url", "")
    aplicado = oferta.get("aplicado")
    marcada, detalle_marca = _cuando_marcada(oferta)
    cabecera = _cabecera_de_tarjeta(oferta)

    if oferta.get("archivada") and aplicado is None:
        cuando_arch, det = _cuando_marcada({"fecha_feedback": oferta.get("fecha_archivada")})
        etiqueta = f"Archivada {cuando_arch}" if cuando_arch else "Archivada"
        return f"""<article class="oferta marcada">
{cabecera}
    <form class="acciones" method="post" action="/archivar">
      {_ocultos(perfil, ver, desde, pagina, url)}
      <span class="marca" title="{esc(det)}">{esc(etiqueta)}</span>
      <button class="fantasma" name="archivar" value="0">Devolver a la lista</button>
    </form>
  </div>
</article>"""

    if aplicado is True:
        etiqueta = f"Aplicaste {marcada}" if marcada else "Aplicaste"
        return f"""<article class="oferta marcada">
{cabecera}
    <p class="marca si" title="{esc(detalle_marca)}">{esc(etiqueta)}</p>
  </div>
</article>"""

    if aplicado is False:
        from vacantia.ui.data import partes_del_motivo
        etiqueta = f"Descartada {marcada}" if marcada else "Descartada"
        # El motivo de la lista y el escrito a mano van en elementos separados:
        # unirlos con un punto medio los convierte en una sola frase larga, y
        # el punto medio está reservado para la línea de estado del sistema.
        de_la_lista, escrito = partes_del_motivo(oferta)
        motivo = ""
        if de_la_lista:
            motivo += f'<span class="motivo-elegido">{esc(de_la_lista)}</span>'
        if escrito:
            motivo += f'<span class="motivo-escrito">{esc(escrito)}</span>'
        return f"""<article class="oferta marcada">
{cabecera}
    <p class="marca" title="{esc(detalle_marca)}">{esc(etiqueta)}</p>
    <p class="marca-motivo">{motivo or "sin motivo"}</p>
  </div>
</article>"""

    if ver == "filtradas":
        return _tarjeta_filtrada(oferta, perfil, desde, pagina, cabecera)

    razon = oferta.get("reason") or ""
    stack = oferta.get("stack") or ""
    enlace = quote(url, safe="")
    return f"""<article class="oferta">
{cabecera}
    {f'<p class="stack">{esc(stack)}</p>' if stack else ''}
    {f'<p class="razon">{esc(razon)}</p>' if razon else ''}
    {linea_de_cv(oferta.get('_cv'), 'Mandá tu CV')}
    <form class="acciones" method="post" action="/feedback">
      {_ocultos(perfil, ver, desde, pagina, url)}
      <button class="primario" name="aplicado" value="si"
              onclick="return marcar(this, false)">Apliqué</button>
      <details class="motivo">
        <summary>No apliqué</summary>
        <div class="cuerpo">
          {_select_de_motivos()}
          <input type="text" name="motivo" placeholder="...o escribí otro motivo">
          <p class="error-motivo">Elegí uno de la lista o escribí el motivo. Con
          cualquiera de los dos alcanza.</p>
          <button name="aplicado" value="no"
                  onclick="return marcar(this, true)">Descartar la oferta</button>
        </div>
      </details>
      <button class="fantasma" name="archivar" value="1"
              formaction="/archivar" formnovalidate
              title="No le doy bola, por la razón que sea. La saca de la lista sin pedir motivo y sin enseñarle nada al sistema. Se puede devolver desde Archivadas.">Archivar</button>
      <details class="menu">
        <summary title="Más opciones" aria-label="Más opciones">{ICONOS['mas']}</summary>
        <div class="panel">
          <a href="/mensajes?perfil={esc(perfil)}&url={enlace}">Mensaje para escribirle</a>
          <a href="/consejo?perfil={esc(perfil)}&url={enlace}">Consejo para el CV</a>
        </div>
      </details>
    </form>
  </div>
</article>"""


# Cada filtro vacío significa algo distinto, y decir siempre "no hay ofertas"
# desperdicia el único momento en que la pantalla tiene toda la atención puesta.
#
# El tercer elemento dice si ese vacío se arregla buscando. Cuando sí, la
# pantalla ofrece el botón en vez de nombrar un archivo que hay que ir a abrir
# al Explorador.
VACIO = {
    "pendientes": ("No te queda ninguna sin mirar.",
                   "Cuando entren ofertas nuevas van a aparecer acá. "
                   "Si no querés esperar al próximo horario, buscá ahora.", True),
    "aplicadas": ("Todavía no marcaste ninguna como aplicada.",
                  "Cuando mandes un CV, tocá <b>Apliqué</b> en esa oferta.", False),
    "descartadas": ("Todavía no descartaste ninguna.",
                    "Cuando una no sirva, tocá <b>No apliqué</b> y escribí por qué. "
                    "Ese motivo es lo que después afina las búsquedas.", False),
    "filtradas": ("No queda ninguna sin revisar.",
                  "Acá caen las que el sistema descarta solo, por idioma o por "
                  "lugar, para que puedas contestar si acertó. Las revisaste a "
                  "todas: cuando entren ofertas nuevas van a aparecer las que "
                  "el filtro saque.", False),
    "archivadas": ("No archivaste ninguna todavía.",
                   "Archivar es para las ofertas a las que no les das bola, por "
                   "la razón que sea: muy viejas, no eran una oferta, o lo que "
                   "fuere. No pide motivo y no le enseña nada al sistema: sólo "
                   "las saca de la lista.", False),
    "todas": ("Todavía no hay ofertas guardadas.",
              "Buscá ahora para correr la primera búsqueda. Tarda unos minutos y "
              "podés seguir usando la pantalla mientras tanto.", True),
}


def _selector_de_periodo(perfil: str, ver: str, desde: str, elegido: str) -> str:
    """El desplegable de 7 días / 2 semanas / mes / ... del cartel de arriba.

    Es un GET con los otros filtros escondidos adentro: cambiar el período no
    tiene que perder en qué pestaña estabas ni el filtro de antigüedad.
    """
    from vacantia.ui.data import PERIODOS

    opciones = "".join(
        f'<option value="{esc(clave)}"'
        f'{" selected" if clave == elegido else ""}>{esc(etiqueta)}</option>'
        for clave, etiqueta, _ in PERIODOS
    )
    return f"""<form class="periodo" method="get" action="/trabajos">
  <input type="hidden" name="perfil" value="{esc(perfil)}">
  <input type="hidden" name="ver" value="{esc(ver)}">
  <input type="hidden" name="desde" value="{esc(desde)}">
  <label for="cuando-apliq">Período</label>
  <select id="cuando-apliq" name="apliq" onchange="this.form.submit()">{opciones}</select>
  <noscript><button>Ver el período</button></noscript>
</form>"""


def _postulaciones(perfil: str, ver: str, desde: str, aplicadas: dict | None,
                   descartadas: dict | None = None) -> str:
    """El cartel grande de arriba de la lista. **Cambia según la pestaña.**

    Antes era uno solo y vivía únicamente en *Sin marcar*. El problema es que el
    número de arriba y la lista de abajo hablaban de cosas distintas: parado en
    *Apliqué* veías nueve tarjetas y un cartel que decía once, porque el cartel
    sumaba las que contaste a mano desde un posteo de LinkedIn.

    Ahora cada pestaña trae el número que corresponde a lo que estás mirando:

    * **Sin marcar** — el total de postulaciones, de donde sea que salgan. Es la
      pantalla que se abre por defecto y la pregunta ahí es "¿estoy haciendo
      algo?", que no distingue de dónde salió cada una.
    * **Apliqué** — sólo las que marcaste en esta lista, que son las que tenés
      abajo. Un número más grande que la lista se lee como un error.
    * **Descarté** — no cuántas sino **por qué**, que es la única parte de esto
      que se puede accionar: "46 de 78 por inglés" es una perilla de Mi perfil
      esperando que la muevan.
    * **Filtradas** ya tiene su propio marcador de auditoría, y dos marcadores
      en la misma pantalla no se leen, compiten.

    El verde no decora: en este sistema significa lo que ya hiciste, igual que
    en la tarjeta de una oferta aplicada. Y va con la palabra al lado, nunca
    sólo el color. Por eso *Descarté* **no** va en verde: descartar no es un
    logro, es higiene.
    """
    if ver == "descartadas":
        return _cartel_de_descartes(perfil, ver, desde, descartadas)
    if ver not in ("pendientes", "aplicadas") or not aplicadas:
        return ""

    from vacantia.ui.graficos import columnas

    cuantas = aplicadas.get("cuantas", 0)
    selector = _selector_de_periodo(perfil, ver, desde, aplicadas.get("periodo", ""))

    if not cuantas:
        cuerpo = ('<p class="vacio-corto">Todavía no marcaste ninguna en este '
                  'período. Cuando mandes un CV, tocá <b>Apliqué</b> en esa '
                  'oferta y el número empieza a subir.</p>')
    else:
        # El reparto es lo que hace que el total signifique algo: 12
        # postulaciones en un mes puede ser tres semanas sin hacer nada y una a
        # los tiros, y eso no se ve en el total.
        #
        # En una semana el reparto es por día y no por semana: repartir siete
        # días en semanas daba una barra sola, que no compara con nada, y la
        # tarjeta quedaba con el número grande y un vacío al lado.
        tramos = [{"etiqueta": e, "cuantas": n}
                  for e, n in aplicadas.get("reparto") or []]
        por = "día" if aplicadas.get("unidad") == "día" else "semana"
        cuerpo = (f'<div class="reparto" aria-label="Postulaciones por {por}">'
                  f'{columnas(tramos, "postulaciones")}</div>'
                  if len(tramos) > 1 else "")

    trabajo = "trabajo" if cuantas == 1 else "trabajos"
    cuando = esc(aplicadas.get("etiqueta", ""))
    if ver == "aplicadas":
        # Parado acá el número YA es sólo el de la lista, así que en vez de
        # explicar qué se sumó hay que explicar qué se restó: si no, el cartel
        # y el contador de la barra de arriba no cierran y parece un bug.
        cuando += " · sólo las de esta lista"
    else:
        # De dónde salió el número, cuando parte no salió de esta lista. Sin
        # esto, el total sube sin que se haya marcado ninguna tarjeta y no hay
        # forma de entender por qué.
        a_mano = aplicadas.get("a_mano") or 0
        if a_mano:
            cuando += f" · {a_mano} anotadas en LinkedIn URLs"
    return f"""<section class="postulaciones" aria-label="Postulaciones">
  <p class="cuenta"><span class="numero">{cuantas}</span>
     <span class="que">{trabajo} a los que apliqué</span>
     <span class="cuando">{cuando}</span></p>
  {selector}
  {cuerpo}
</section>"""


def _cartel_de_descartes(perfil: str, ver: str, desde: str,
                         descartadas: dict | None) -> str:
    """Por qué venís descartando, con el mismo selector de período.

    El total de descartes no sirve para nada por sí solo: descartar no es
    trabajo que quieras sostener, así que no hay ritmo que cuidar. Lo que sirve
    es el desglose, porque cada motivo que se repite mucho es una perilla de Mi
    perfil que conviene mover: si 46 de 78 caen por inglés, o subís el nivel
    declarado o dejás de buscar puestos que lo piden, pero hay algo que hacer.

    Por eso acá el gráfico es de barras por motivo y no de columnas por semana,
    y por eso el número grande no va en verde: el verde en este sistema
    significa lo que ya hiciste, y descartar no es un logro.
    """
    from vacantia.ui.graficos import barras, vale_un_grafico

    if not descartadas:
        return ""

    cuantas = descartadas.get("cuantas", 0)
    filas = descartadas.get("motivos") or []
    selector = _selector_de_periodo(perfil, ver, desde, descartadas.get("periodo", ""))

    if not cuantas:
        cuerpo = ('<p class="vacio-corto">No descartaste ninguna en este período. '
                  'Cuando una no sirva, tocá <b>No apliqué</b> y elegí por qué: '
                  'ese motivo es lo que después afina las búsquedas.</p>')
    elif vale_un_grafico(filas):
        cuerpo = (f'<div class="reparto" aria-label="Motivos de descarte">'
                  f'{barras(filas, "ofertas")}</div>')
    else:
        # Con uno o dos motivos no hay nada que comparar: el gráfico sería una
        # barra al 100% al lado de otra al 30%, que dice menos que la frase.
        cuerpo = '<ul class="motivos-cortos">' + "".join(
            f"<li><b>{esc(n)}</b> {esc(etiqueta.lower())}</li>"
            for etiqueta, n in filas) + "</ul>"

    oferta = "oferta" if cuantas == 1 else "ofertas"
    return f"""<section class="postulaciones descartes" aria-label="Motivos de descarte">
  <p class="cuenta"><span class="numero">{cuantas}</span>
     <span class="que">{oferta} que descarté</span>
     <span class="cuando">{esc(descartadas.get("etiqueta", ""))}</span></p>
  {selector}
  {cuerpo}
</section>"""


def _marcador_del_filtro(ver: str, revision: dict | None) -> str:
    """Cuántas veces acertó el filtro y cuántas se equivocó, de un vistazo.

    Va arriba de la lista de Filtradas y en ningún otro lado. No es un recuento
    de lo que se pierde, que ésos viven en Métricas: es el resultado del trabajo
    que la persona está haciendo en esta misma pantalla, y sin verlo revisar
    veinte avisos es tirarlos a un pozo.

    **Es acumulativo**: cuenta toda la semana de prueba, no la página abierta.
    Con dos días de muestra un porcentaje sobre lo de hoy no dice nada.
    """
    if ver != "filtradas" or not revision:
        return ""
    bien, mal = revision.get("bien", 0), revision.get("mal", 0)
    if not bien and not mal:
        return f"""<div class="callout marcador">
  <p>Acá se revisa si el sistema descartó bien. A medida que contestes, van a
  aparecer los dos contadores y vas a poder ver si el filtro está afinado.</p>
  <p class="ayuda">Con {revision.get('meta', 0)} revisadas ya se puede decir algo.</p>
</div>"""
    revisadas = bien + mal
    # De las bien descartadas, cuántas lo estaban por el motivo equivocado. Va
    # adentro del contador de aciertos y no al lado: es un acierto del filtro y
    # un error de la explicación, y son dos cosas distintas.
    con_motivo_mal = revision.get("motivo_errado", 0)
    errado = (f'<span class="valor">{con_motivo_mal}</span> con el motivo mal'
              if con_motivo_mal else "")
    faltan = revision.get("faltan", 0)
    meta = revision.get("meta", 0)
    if faltan:
        # El progreso hacia la meta, y no un porcentaje de aciertos: con 19
        # revisadas un "100% de aciertos" suena a veredicto y todavía no lo es.
        cierre = (f"Sobre {revisadas} revisadas. Con {meta} ya se puede decir si el "
                  f"filtro anda: te faltan {faltan}.")
    else:
        cierre = (f"Sobre {revisadas} revisadas, y con {meta} alcanza para saberlo. "
                  "Ya tenés la muestra.")
    return f"""<div class="callout marcador">
  <p class="cuenta"><span class="valor">{bien}</span> bien descartadas
     <span class="valor">{mal}</span> mal descartadas{errado}</p>
  <p class="ayuda">{esc(cierre)} Las que marcaste mal volvieron a Sin marcar.</p>
</div>"""


def _filtradas_vacia(perfil: str, corriendo: bool, revision: dict | None) -> str:
    """No queda nada para revisar. Por qué, que no es lo mismo en los dos casos.

    O revisaste todo lo que había, o lo que queda puntúa tan poco que no vale la
    pena mirarlo: si el filtro se equivocó con una de 20, esa oferta no te iba a
    servir igual. Decir cuántas quedaron abajo del corte evita que la pantalla
    vacía se lea como "se terminaron las ofertas".
    """
    from vacantia.ui.data import PUNTAJE_PARA_REVISAR

    bajo = (revision or {}).get("bajo_puntaje", 0)
    if bajo:
        detalle = (
            f"Revisaste todas las que valía la pena mirar. Quedan {bajo} que el "
            f"filtro sacó y puntúan menos de {PUNTAJE_PARA_REVISAR}: aunque se "
            "haya equivocado con alguna, no te iban a servir. Cuando entre una "
            f"de {PUNTAJE_PARA_REVISAR} para arriba va a aparecer acá."
        )
    else:
        detalle = (
            "Acá caen las que el sistema descarta solo, por idioma o por lugar, "
            f"de {PUNTAJE_PARA_REVISAR} puntos para arriba. Cuando entren "
            "ofertas nuevas van a aparecer las que el filtro saque."
        )
    return (f'<div class="vacio"><b>No queda ninguna por revisar.</b>{detalle}'
            f'<div class="salida">{_boton_buscar(perfil, corriendo, primario=True)}</div>'
            f'</div>')


def _desplegable_de_fecha(perfil: str, ver: str, desde: str, cuentas: dict) -> str:
    """La antigüedad como desplegable y no como cuatro botones.

    Eran cuatro chips que ocupaban una fila entera para algo que se toca una vez
    por semana, compitiendo por atención con lo que sí importa mientras uno
    trabaja: cuántas quedan por mirar. Un desplegable dice lo mismo en un renglón.

    Sin JavaScript sigue funcionando: es un `<form method=get>` con su botón,
    que el `onchange` sólo adelanta.
    """
    opciones = "".join(
        f'<option value="{esc(clave)}"{" selected" if clave == desde else ""}>'
        f'{esc(etiqueta)} ({(cuentas or {}).get(clave, 0)})</option>'
        for clave, etiqueta in RANGOS
    )
    return f"""<form class="filtro-fecha" method="get" action="/trabajos">
  <input type="hidden" name="perfil" value="{esc(perfil)}">
  <input type="hidden" name="ver" value="{esc(ver)}">
  <label for="desde">Antigüedad del aviso</label>
  <select id="desde" name="desde" onchange="this.form.submit()">{opciones}</select>
  <noscript><button>Filtrar por antigüedad</button></noscript>
</form>"""


def _encabezado(ver: str, conteo: dict, filtro_fecha: str) -> str:
    """El número grande a la izquierda y el filtro de fecha a la derecha.

    El número es el único dato que importa mientras uno revisa: cuántas faltan.
    Estaba adentro de un chip, del mismo tamaño que los otros cuatro contadores,
    compitiendo con "Archivadas 83" — que no es una tarea, es un archivo.
    """
    cuantas = int((conteo or {}).get(ver, 0))
    # Sólo en "Sin marcar" el número es una tarea pendiente. En las otras
    # pestañas es un archivo, y no merece el tamaño.
    if ver != "pendientes":
        return f'<div class="encabezado"><div></div>{filtro_fecha}</div>'
    return f"""<div class="encabezado">
  <p class="cuantas"><span class="numero">{cuantas}</span>
     <span class="que">sin mirar</span></p>
  {filtro_fecha}
</div>"""


def _con_banda_de_recientes(ofertas: list[dict], perfil: str, ver: str,
                            desde: str, pagina: int) -> str:
    """Las tarjetas, con un rótulo que separa lo recién publicado del resto.

    `data.ofertas` ya las ordenó con las recientes arriba; acá sólo se dibuja
    dónde termina ese grupo. Se hace en dos rótulos y no en un color de tarjeta
    porque lo que hay que contestar es "¿hasta dónde miro hoy?", y una línea que
    cruza la lista lo dice mejor que un borde en cada una.

    Si no hay ninguna reciente, o si son todas, no se dibuja nada: un rótulo que
    encabeza la lista entera no separa nada y sólo ocupa lugar.
    """
    from vacantia.ui.data import DIAS_RECIEN

    tarjetas = [_tarjeta(o, perfil, ver, desde, pagina) for o in ofertas]
    cuantas = sum(1 for o in ofertas if o.get("_recien"))
    if not 0 < cuantas < len(ofertas):
        return "".join(tarjetas)

    def rotulo(texto: str, cuenta: str, detalle: str) -> str:
        numero = f'<span class="cuenta">{cuenta}</span>' if cuenta else ""
        return (f'<h3 class="banda"><span>{texto}</span>{numero}'
                f'<span class="detalle">{detalle}</span></h3>')

    dias = "de hoy o ayer" if DIAS_RECIEN <= 2 else f"de los últimos {DIAS_RECIEN} días"
    return (
        rotulo("Recién publicadas", str(cuantas),
               f"Avisos {dias}. Son a los que menos gente se postuló todavía.")
        + "".join(tarjetas[:cuantas])
        + rotulo("El resto", "", "Ordenadas por puntaje, como siempre.")
        + "".join(tarjetas[cuantas:])
    )


def _paginas(perfil: str, ver: str, desde: str, pagina: int, paginas: int,
             total: int) -> str:
    """La barra de abajo. No se dibuja si todo entra en una página."""
    if paginas <= 1:
        return ""

    def link(destino: int, etiqueta: str) -> str:
        if not 1 <= destino <= paginas:
            return f'<span class="quieto">{etiqueta}</span>'
        return (f'<a href="/trabajos?perfil={esc(perfil)}&ver={esc(ver)}'
                f'&desde={esc(desde)}&p={destino}">{etiqueta}</a>')

    return f"""<nav class="paginas" aria-label="Páginas">
  {link(pagina - 1, "Anteriores")}
  {link(pagina + 1, "Siguientes")}
  <span class="donde">Página {pagina} de {paginas}</span>
  <span class="donde">{total} ofertas</span>
</nav>"""


def _archivar_viejas(perfil: str, ver: str, desde: str, cuantas: dict) -> str:
    """El botón para encajonar de una todas las que quedaron viejas.

    Un aviso de hace tres semanas casi siempre está cubierto, y con 43 en esa
    situación archivarlas de a una es trabajo al pedo. Sólo aparece si hay algo
    que archivar, y dice cuántas son antes de apretar. Todo en fantasma: es
    mantenimiento y no compite con la acción de la pantalla.
    """
    if ver != "pendientes" or not cuantas:
        return ""
    opciones = "".join(
        f'<button class="fantasma" name="dias" value="{dias}">Más de {dias} días ({n})</button>'
        for dias, n in sorted(cuantas.items()) if n
    )
    if not opciones:
        return ""
    return f"""<form class="encajonar" method="post" action="/archivar-viejas">
  <input type="hidden" name="perfil" value="{esc(perfil)}">
  <input type="hidden" name="desde" value="{esc(desde)}">
  <span>Archivar los avisos viejos:</span>{opciones}
  <span class="ayuda">Los saca de la lista sin enseñarle nada al sistema sobre
  lo que te gusta. Se pueden devolver.</span>
</form>"""


def trabajos(perfil: str, ofertas: list[dict], conteo: dict, ver: str,
             mensajes: list[tuple[str, str]], desde: str = "todo",
             conteo_fecha: dict | None = None,
             marca: str = "", pagina: int = 1, paginas: int = 1,
             viejas: dict | None = None, corriendo: bool = False,
             revision: dict | None = None, aplicadas: dict | None = None,
             descartadas: dict | None = None) -> str:
    """La lista.

    Arriba no va ningún recuento de lo que se pierde: cuántas ofertas quedan
    afuera por el inglés es información legítima, pero vive en Métricas, con la
    explicación y con el link a donde se cambia el nivel declarado.
    """
    def chips(opciones, activo, param, cuentas, otro_param, otro_valor):
        salida = []
        for clave, etiqueta in opciones:
            # "Filtradas" se pinta distinto del resto: no es una pestaña más
            # donde mirar lo que ya hiciste, es la tarea de revisar si el filtro
            # automático acierta, y hay que poder encontrarla de un vistazo. Va
            # en el azul de "estado del sistema", con su ícono, y no en el
            # índigo de acción: una píldora rellena del color de acción se
            # confunde con un botón. Rojo tampoco: no es un error.
            clases = " ".join(c for c in (
                "activa" if clave == activo else "",
                "revisar" if clave == "filtradas" else "",
            ) if c)
            icono = ICONOS["filtradas"] if clave == "filtradas" else ""
            salida.append(
                f'<a href="/trabajos?perfil={esc(perfil)}&{otro_param}={esc(otro_valor)}'
                f'&{param}={clave}"{f" class=\'{clases}\'" if clases else ""}>'
                f'{icono}{etiqueta} '
                f'<span class="cuenta">{(cuentas or {}).get(clave, 0)}</span></a>'
            )
        return "".join(salida)

    # Cada botón conserva el valor del otro eje: cambiar de "Sin marcar" a
    # "Descarté" no tiene por qué devolverte a ver los avisos de hace un año.
    por_estado = chips(FILTROS, ver, "ver", conteo, "desde", desde)
    por_fecha = _desplegable_de_fecha(perfil, ver, desde, conteo_fecha)

    if ofertas:
        listado = (_con_banda_de_recientes(ofertas, perfil, ver, desde, pagina)
                   + _paginas(perfil, ver, desde, pagina, paginas,
                              int((conteo or {}).get(ver, 0))))
    elif desde != "todo":
        listado = (
            '<div class="vacio"><b>Ninguna en ese rango de fechas.</b>'
            'Probá con <b>Sin filtro</b> para ver también las más viejas.</div>'
        )
    elif ver == "filtradas":
        listado = _filtradas_vacia(perfil, corriendo, revision)
    else:
        titulo, detalle, se_arregla_buscando = VACIO.get(ver, VACIO["todas"])
        salida = (f'<div class="salida">{_boton_buscar(perfil, corriendo, primario=True)}</div>'
                  if se_arregla_buscando else "")
        listado = f'<div class="vacio"><b>{titulo}</b>{detalle}{salida}</div>'

    # El aviso de "entraron ofertas nuevas" ya no se arma acá. Lo trae el cartel
    # de la corrida del pie de la barra lateral: pregunta por la marca del
    # historial en el mismo pedido con el que pregunta en qué anda la búsqueda,
    # y pisa el aviso del shell con `hx-swap-oob`. Antes eran dos relojes
    # distintos preguntando por cosas parecidas.

    return f"""{avisos(mensajes)}
<h1>Trabajos</h1>
{_postulaciones(perfil, ver, desde, aplicadas, descartadas)}
<div class="filtros">{por_estado}</div>
{_encabezado(ver, conteo, por_fecha)}
{_marcador_del_filtro(ver, revision)}
{_archivar_viejas(perfil, ver, desde, viejas or {})}
{listado}"""
