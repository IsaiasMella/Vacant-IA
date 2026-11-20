"""El shell de la pantalla: la barra lateral y el panel de "Buscando trabajo".

`pagina()` arma el documento entero alrededor del cuerpo de cada pestaña.
`corrida_estado()` es el cartel del pie que se actualiza solo.
"""

from urllib.parse import urlencode

from vacantia.ui.render.comun import ICONOS, esc

# --- el shell ---------------------------------------------------------------

#: (ruta, etiqueta, clave). El sidebar agrupa por lo que la persona hace, no por
#: lo que la sección es: primero buscar, después revisar y configurar.
SECCIONES_BUSCAR = (
    ("trabajos", "Trabajos", "trabajos"),
    ("linkedin", "LinkedIn URLs", "linkedin"),
)
SECCIONES_RESTO = (
    ("estadisticas", "Métricas", "estadisticas"),
    ("datos", "Mi perfil", "datos"),
)
#: Configuración va sola, al pie, abajo de Buscar ahora. Es lo que se carga una
#: vez y no se vuelve a mirar: arriba, al lado de lo que se usa todos los días,
#: competía por la vista sin merecerlo.
SECCION_AL_PIE = ("configuracion", "Configuración", "configuracion")


def _boton_buscar(perfil: str, corriendo: bool, primario: bool = False) -> str:
    """El botón que arranca una búsqueda sin esperar el horario.

    Antes esto era un archivo `.bat` que había que ir a buscar al Explorador, y
    la pantalla te lo nombraba por su nombre de archivo. Si hay que ejecutar
    algo, es un botón con nombre humano.

    Al pie de la barra lateral va en secundario: la acción de esa pantalla es
    aplicar a una oferta, y dos primarios enfrentados obligan a decidir antes de
    leer. En un estado vacío no hay ninguna oferta que aplicar, así que ahí sí
    es el primario.
    """
    if corriendo:
        return ('<button type="button" disabled>Buscando ofertas</button>')
    clase = "primario" if primario else ""
    return f"""<form method="post" action="/buscar">
  <input type="hidden" name="perfil" value="{esc(perfil)}">
  <button class="{clase}" type="submit">Buscar ahora</button>
</form>"""


#: Cada cuánto le pregunta la pantalla al servidor cómo viene la búsqueda.
#:
#: Dos valores y no uno: mientras busca, el cartel cambia de etapa y dos
#: segundos es lo que hace que se sienta vivo; quieto, lo único que puede pasar
#: es que arranque la corrida programada, y preguntar cada dos segundos por eso
#: es tirar 1800 pedidos por hora a la basura.
#:
#: **El intervalo viaja en el fragmento, no en el JavaScript.** Cada respuesta
#: trae el suyo, así que el ritmo se acelera solo al arrancar la búsqueda y se
#: afloja solo al terminar, sin una línea de código nuestro.
LATIDO_BUSCANDO = "2s"
LATIDO_QUIETO = "15s"


def _cuanto_hace(segundos: int) -> str:
    """Los segundos que lleva la búsqueda, dichos como los diría una persona.

    Redondea a minutos enteros arriba del minuto: el segundero corriendo al lado
    de una barra que no avanza es lo que hace que cinco minutos se sientan
    veinte. Lo que el número tiene que contestar es "¿esto arrancó recién o hace
    un rato?", y para eso "3 minutos" alcanza.
    """
    if segundos < 60:
        return "recién arrancó"
    minutos = segundos // 60
    return "hace 1 minuto" if minutos == 1 else f"hace {minutos} minutos"


def _tramos(etapa: str) -> str:
    """La fila de tramos del panel: cuáles ya pasaron, en cuál está, cuáles no.

    Sale de `corrida.ETAPAS`, que es el orden del pipeline del motor, y **no de
    una lista escrita acá**: si mañana el motor gana o pierde una etapa, se toca
    en un solo lado y el panel la dibuja sola.
    """
    from vacantia.ui.corrida import ETAPAS

    orden = [clave for clave, _ in ETAPAS]
    # `arranque` es antes del primer tramo (-1) y `cierre` después del último.
    if etapa == "cierre":
        actual = len(orden)
    elif etapa in orden:
        actual = orden.index(etapa)
    else:
        actual = -1

    piezas = []
    for i, (clave, nombre) in enumerate(ETAPAS):
        if i < actual:
            estado, marca_ = "hecho", ICONOS["tilde-tramo"]
        elif i == actual:
            estado, marca_ = "activo", '<span class="punto" aria-hidden="true"></span>'
        else:
            estado, marca_ = "pendiente", '<span class="punto" aria-hidden="true"></span>'
        piezas.append(f'<li class="{estado}">{marca_}<span>{esc(nombre)}</span></li>')
    return f'<ol class="tramos">{"".join(piezas)}</ol>'


def _barra(paso: dict) -> str:
    """La barra del panel. Se llena de verdad sólo durante el puntaje.

    En las demás etapas no se sabe cuánto falta -- no se sabe cuántas fuentes
    van a contestar ni cuántas ofertas van a entrar -- así que la barra va sin
    porcentaje: dice "esto sigue andando", que es lo único cierto. Un porcentaje
    inventado que se clava en 40% durante dos minutos es peor que no tener
    ninguno.
    """
    total, hechas = int(paso.get("total") or 0), int(paso.get("hechas") or 0)
    if not total:
        return ('<div class="barra indefinida" role="progressbar"'
                ' aria-label="Buscando"><span></span></div>')
    porcentaje = min(100, round(hechas * 100 / total))
    return (f'<div class="barra" role="progressbar" aria-valuemin="0"'
            f' aria-valuemax="{total}" aria-valuenow="{hechas}"'
            f' aria-label="Ofertas puntuadas">'
            f'<span style="width: {porcentaje}%"></span></div>')


def panel_de_busqueda(paso: dict, oob: bool = False) -> str:
    """El panel grande de "Buscando trabajo", arriba del contenido.

    El cartel del pie de la barra lateral dice lo mismo en dos renglones de
    texto chico, y ese es justamente el problema que vino a resolver esto: al
    costado del campo visual y en cuerpo 12, arrancar una búsqueda y que no
    pasara nada visible se sentía igual que apretar un botón roto. El panel es
    lo que contesta "¿está haciendo algo?" de un vistazo y desde lejos.

    Los dos siguen existiendo y no es redundancia: el panel es el estado de
    *esta* búsqueda mientras dura, y el cartel del pie es el botón que la
    arranca y el lugar fijo donde vive el estado del sistema.

    **Vuelve siempre el contenedor, incluso vacío.** Es el único elemento de la
    pantalla que tiene que poder *desaparecer* solo cuando la búsqueda termina,
    y para que el reemplazo lo alcance el contenedor tiene que estar ahí. Si
    volviera `""` como el aviso de novedades, el panel quedaría clavado hasta
    que alguien recargue.

    Con `oob`, vuelve marcado para pisar al panel que ya está en la página
    aunque el pedido lo haya hecho el cartel de la barra lateral, que es otro
    elemento: así un solo pedido cada dos segundos actualiza los dos.

    **El `role="status"` lo lleva el cartel del pie y no éste.** Los dos dicen
    la misma oración y los dos se reemplazan cada dos segundos: con la etiqueta
    puesta en los dos, un lector de pantalla canta "Puntuando contra tu CV" dos
    veces cada dos segundos durante toda la búsqueda.
    """
    fuera = ' hx-swap-oob="true"' if oob else ""
    abre = f'<div class="buscando" id="buscando"{fuera}>'
    if not paso.get("corriendo"):
        return f"{abre}</div>"

    # El segundo renglón: durante el puntaje, cuántas lleva de cuántas, que es
    # el único momento en que se sabe el total de verdad. Fuera de ahí, de qué
    # perfil se trata, que con `--all` va cambiando y es lo que explica por qué
    # la búsqueda tarda el triple que de costumbre.
    if paso.get("total"):
        detalle = f'{paso["hechas"]} de {paso["total"]}'
    elif paso.get("perfil"):
        detalle = f'Perfil {paso["perfil"]}'
    else:
        detalle = ""

    return f"""{abre}
  <div class="cabecera">
    {ICONOS["buscando"]}
    <h2>Buscando trabajo</h2>
    <span class="hace">{esc(_cuanto_hace(int(paso.get("segundos") or 0)))}</span>
  </div>
  <p class="que">{esc(paso.get("paso", ""))}</p>
  <div class="avance">{_barra(paso)}<span class="detalle">{esc(detalle)}</span></div>
  {_tramos(paso.get("etapa", ""))}
  <p class="tranquilo">Seguí usando la pantalla: cuando entren ofertas nuevas, te avisa acá.</p>
</div>"""


def corrida_estado(perfil: str, paso: dict, marca: str, pendientes: int,
                   nuevas: int = 0, cambio: bool = False,
                   con_panel: bool = True) -> str:
    """El cartel del pie de la barra lateral: el botón, o en qué anda la búsqueda.

    Es el único pedazo de la pantalla que se actualiza solo. Se pide cada tantos
    segundos y se reemplaza entero; como el fragmento que vuelve trae de nuevo
    sus propios atributos, el ciclo se mantiene sin que nadie lo programe.

    `marca` y `pendientes` son **cómo estaba el historial cuando se abrió la
    página**, no ahora. Viajan en la dirección del pedido y vuelven iguales en
    cada respuesta, así que la comparación siempre es contra el momento en que
    la persona empezó a mirar. Sin eso, el aviso de "entraron 3 ofertas" se
    reiniciaría solo cada dos segundos y no diría nada.

    Cuando la corrida terminó y entraron ofertas, además del cartel vuelve el
    aviso de novedades marcado para reemplazar al de la página. **No recarga
    sola a propósito**: si alguien está escribiendo el motivo de un descarte,
    una recarga se lo borra. Avisa, y decide la persona.

    Con la misma respuesta viaja el panel grande de arriba del contenido. Es un
    solo pedido cada dos segundos que actualiza los tres lugares: el cartel del
    pie, el panel de arriba y el aviso de novedades. `con_panel=False` es para
    el armado inicial de la página, donde el panel lo pone `pagina()` en su
    lugar y mandarlo dos veces dejaría dos elementos con el mismo id.
    """
    destino = (f"/corrida?{urlencode({'perfil': perfil, 'marca': marca, 'pend': pendientes})}")
    latido = LATIDO_BUSCANDO if paso.get("corriendo") else LATIDO_QUIETO
    abre = (f'<div class="corrida" id="corrida" hx-get="{esc(destino)}" '
            f'hx-trigger="every {latido}" hx-swap="outerHTML">')

    if paso.get("corriendo"):
        # Dos renglones: qué está haciendo, y cuánto lleva de eso cuando el
        # total se sabe de verdad. Durante el puntaje se sabe; durante las
        # fuentes no, y un porcentaje inventado es peor que no poner ninguno.
        segunda = ""
        if paso.get("total"):
            segunda = f'{paso["hechas"]} de {paso["total"]}'
        elif paso.get("perfil"):
            segunda = f'Perfil {paso["perfil"]}'
        detalle = f'<p class="detalle">{esc(segunda)}</p>' if segunda else ""
        return (f'{abre}<p class="que" role="status">{esc(paso.get("paso", ""))}</p>'
                f'{detalle}</div>{panel_de_busqueda(paso, oob=True) if con_panel else ""}')

    boton = f"""<form method="post" action="/buscar" hx-post="/buscar"
      hx-target="#corrida" hx-swap="outerHTML">
  <input type="hidden" name="perfil" value="{esc(perfil)}">
  <input type="hidden" name="marca" value="{esc(marca)}">
  <input type="hidden" name="pend" value="{esc(pendientes)}">
  <button type="submit">Buscar ahora</button>
</form>"""
    # Sin corrida, el panel vuelve vacío igual: es lo que lo hace desaparecer
    # de la pantalla en el mismo pedido en que la búsqueda termina.
    panel = panel_de_busqueda(paso, oob=True) if con_panel else ""
    return f"{abre}{boton}</div>{panel}{_aviso_novedades(nuevas, cambio)}"


def _aviso_novedades(cuantas: int, cambio: bool) -> str:
    """El cartel de "entraron ofertas", listo para pisar al que está en la página.

    `hx-swap-oob` es lo que le permite a una respuesta tocar un elemento que no
    es el que la pidió: el cartel de la corrida vive en la barra lateral y el
    aviso abajo a la derecha, y los dos se actualizan con el mismo pedido.

    Vuelve vacío cuando no hay nada que avisar. Ojo: vacío de verdad, no el
    cartel escondido. Si volviera escondido, pisaría al que la persona está
    mirando y el aviso desaparecería solo a los dos segundos.

    **Que el historial cambie y que haya ofertas nuevas no son lo mismo.** Una
    corrida puede traer veinte avisos y que los veinte se caigan por filtro, o
    la persona puede estar marcando desde otra pestaña. En esos casos el número
    no sube pero la lista que está mirando ya no es la que hay, y eso también
    hay que decirlo.
    """
    if not cambio:
        return ""
    if cuantas <= 0:
        # El botón también cambia: "Ver las nuevas" abajo de "La lista cambió"
        # promete ofertas que a lo mejor no hay.
        que, hacer = "La lista cambió", "Actualizar"
    else:
        que = (f"Entraron {cuantas} ofertas nuevas" if cuantas != 1
               else "Entró 1 oferta nueva")
        hacer = "Ver las nuevas"
    return f"""
<div class="toast novedades visible" id="novedades" role="status" hx-swap-oob="true">
  <span>{esc(que)}</span>
  <button type="button" onclick="location.reload()">{esc(hacer)}</button>
</div>"""


def _estado_del_sistema(perfil: str, estado: dict | None) -> str:
    """El pie fijo de la barra lateral.

    Cuándo buscó, cuándo vuelve, qué ventana cubre, y el botón para buscar ya.
    Es la respuesta a "¿esto es todo lo que hay?", que es de donde sale la mayor
    parte de la ansiedad de buscar trabajo, y por eso tiene un lugar fijo y no
    un tooltip. El botón va acá y no arriba porque es la acción sobre este dato:
    la salida de "la última búsqueda fue hace seis horas".

    El punto medio se reserva para esta línea y no se usa en ninguna otra.
    """
    if not estado:
        return ""
    ultima = estado.get("ultima") or "todavía no buscó"
    proxima = estado.get("proxima") or ""
    ventana = estado.get("ventana")
    linea = f"Última búsqueda: {esc(ultima)}"
    if proxima:
        linea += f" &middot; Próxima: {esc(proxima)}"
    if ventana:
        cubre = (f"<p>Trae avisos de los últimos <span class='valor'>{esc(ventana)}</span> "
                 f"días.</p>")
    else:
        cubre = "<p>Trae avisos sin límite de antigüedad.</p>"
    # El cartel de la corrida va adentro del estado del sistema porque es el
    # mismo dato: "la última búsqueda fue hace seis horas" y "está buscando
    # ahora" se leen juntos o no se leen.
    cartel = corrida_estado(perfil, estado.get("paso") or {},
                            estado.get("marca") or "",
                            int(estado.get("pendientes") or 0),
                            con_panel=False)
    return f'<div class="estado"><p>{linea}</p>{cubre}{cartel}</div>' 


def pagina(titulo: str, cuerpo: str, perfil: str, perfiles: list[str], tab: str,
           estado: dict | None = None) -> str:
    """El shell: barra lateral a la izquierda, una sola columna a la derecha.

    Arriba del contenido va el panel de "Buscando trabajo", que arranca vacío si
    no hay ninguna búsqueda en curso. Vacío ocupa cero y no se ve; existe
    siempre porque es el lugar donde el cartel del pie lo va a ir a pisar cuando
    la búsqueda arranque, y para pisarlo tiene que estar.

    Va acá y no adentro de cada pantalla: la búsqueda se puede arrancar desde
    cualquiera, y quedarse mirando Métricas mientras corre es exactamente el
    momento en el que hace falta ver que está corriendo."""
    opciones = "".join(
        f'<option value="{esc(p)}"{" selected" if p == perfil else ""}>{esc(p)}</option>'
        for p in perfiles
    )

    def link(destino, etiqueta, clave):
        activa = " activa" if clave == tab else ""
        ahi = ' aria-current="page"' if clave == tab else ""
        return (f'<a class="nav-item{activa}" href="/{destino}?perfil={esc(perfil)}"{ahi}>'
                f'{ICONOS[clave]}<span class="etiqueta">{etiqueta}</span></a>')

    buscar = "".join(link(*s) for s in SECCIONES_BUSCAR)
    resto = "".join(link(*s) for s in SECCIONES_RESTO)

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Las ofertas de trabajo de varios portales, en una sola lista y con un puntaje de ajuste.">
<title>{esc(titulo)} · vacantia</title>
<link rel="stylesheet" href="/estilos.css">
<script src="/htmx.min.js" defer></script>
<script src="/app.js" defer></script>
</head><body class="app">
<a class="saltar" href="#contenido">Saltar al contenido</a>
<aside class="lateral">
  <a href="/trabajos?perfil={esc(perfil)}" class="marca-app">
    <span class="sello" aria-hidden="true">V</span><span class="nombre">VACANTIA</span>
  </a>
  <form class="perfil-sel" method="get" action="/{esc(tab)}">
    <label for="perfil-sel">Perfil</label>
    <select id="perfil-sel" name="perfil" onchange="this.form.submit()">{opciones}</select>
    <noscript><button type="submit">Cambiar de perfil</button></noscript>
  </form>
  <p class="grupo">Buscar</p>
  <nav aria-label="Buscar">{buscar}</nav>
  <hr class="separador">
  <nav aria-label="Revisar y configurar">{resto}</nav>
  {_estado_del_sistema(perfil, estado)}
  <nav class="al-pie" aria-label="Configuración">{link(*SECCION_AL_PIE)}</nav>
</aside>
<main id="contenido">{panel_de_busqueda((estado or {}).get("paso") or {})}{cuerpo}</main>
<!-- El aviso de que entraron ofertas. Nace escondido y en TODAS las pantallas,
     no sólo en Trabajos: el cartel de la corrida lo pisa con `hx-swap-oob`
     cuando la búsqueda termina, y para pisarlo tiene que existir. Si sólo
     estuviera en Trabajos, buscar desde Métricas no avisaría nada. -->
<div class="toast novedades" id="novedades" role="status"></div>
</body></html>"""
