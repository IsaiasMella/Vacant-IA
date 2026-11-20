"""La pestaña Métricas: de dónde vienen las ofertas y qué se pierde."""

from vacantia.ui.render.comun import avisos, esc

# --- pestaña Métricas -------------------------------------------------------


def _dato(numero, que: str, destacado: bool = False) -> str:
    clase = "dato destacado" if destacado else "dato"
    return (f'<div class="{clase}"><span class="numero">{esc(numero)}</span>'
            f'<span class="que">{esc(que)}</span></div>')


def _tabla(encabezados: tuple[str, str], filas: list[tuple[str, int]]) -> str:
    if not filas:
        return '<p class="explica">Todavía no hay ninguna.</p>'
    izq, der = encabezados
    cuerpo = "".join(f'<tr><td>{esc(k)}</td><td class="n">{v}</td></tr>'
                     for k, v in filas)
    return (f'<table class="numeros"><thead><tr><th>{esc(izq)}</th>'
            f'<th class="n">{esc(der)}</th></tr></thead>'
            f'<tbody>{cuerpo}</tbody></table>')


#: Cuántas frases escritas a mano van en el gráfico. Arriba quedan las que se
#: repiten, que son las que dicen algo; de ahí para abajo suelen ser de a una.
ESCRITOS_A_LA_VISTA = 10


def _cabecera(titulo: str, explica: str, total: int | None = None, que: str = "",
              de_donde: str = "") -> str:
    """Título y para qué sirve a la izquierda; el total, en grande, del otro lado.

    Las barras se medían contra la más larga, así que la de arriba salía
    siempre llena y "51" no decía de cuántas: 161 avisos que piden Python es
    casi todo sobre 200 y un "bueno de tener" sobre 1000. Primero el total se
    escribió como una frase más ("De las 219 ofertas analizadas. La barra
    entera son las 219.") y se perdía entre la explicación y el gráfico. En
    grande y del otro lado se lee antes que las barras, que es lo que
    corresponde: sin saber contra cuántas se mide, ninguna se entiende.

    `de_donde` es para cuando el total no es obvio: 219 analizadas son "de las
    230 que entraron", y sin decirlo parecía un número salido de la nada.
    """
    texto = " ".join(explica.split())
    lado = ""
    if total:
        extra = f'<span class="de-donde">{esc(de_donde)}</span>' if de_donde else ""
        lado = (f'<div class="panel-total"><span class="numero">{total}</span>'
                f'<span class="que">{esc(que)}</span>{extra}</div>')
    return (f'<div class="panel-cabeza"><div><h2>{esc(titulo)}</h2>'
            f'<p class="explica">{texto}</p></div>{lado}</div>')


def _escritos_a_mano(filas: list[tuple[str, int]], total: int | None = None) -> str:
    """Qué dice la barra "Escrito a mano", frase por frase.

    Sin esto, saber qué había adentro era abrir Descarté y leer tarjeta por
    tarjeta, o sea no saberlo.

    Va en barras como el gráfico de motivos de arriba, y **siempre en barras**,
    aunque sean dos frases: `_desglose` las pasaba a tabla con menos de tres, y
    son dos bloques del mismo panel que tienen que leerse igual. Las que no
    entran en el gráfico van en una tabla plegada, para que una lista de sesenta
    frases no empuje el resto de Métricas fuera de la pantalla.

    Se miden contra el mismo `total` que los motivos, todos los descartes, y
    no contra la suma de lo escrito: "2 de 4 escritas a mano" parece la mitad
    de algo, y de 84 descartes es casi nada.
    """
    from vacantia.ui.graficos import barras

    if not filas:
        return ""
    visibles, resto = filas[:ESCRITOS_A_LA_VISTA], filas[ESCRITOS_A_LA_VISTA:]
    plegadas = (f'<details class="como"><summary>Ver {len(resto)} más</summary>'
                f'{_tabla(("Lo que escribiste", "Veces"), resto)}</details>'
                if resto else "")
    return (f'<p class="explica">Lo que escribiste a mano, de lo más repetido a lo '
            f'menos:</p>{barras(visibles, "veces", total=total)}{plegadas}')


#: Cómo se lee cada motivo del sistema en la pantalla.
def _solapadas(e: dict) -> str:
    """Aviso de que las filas suman más que las ofertas.

    Una oferta puede caer por idioma y por lugar a la vez, y acá se cuenta en
    las dos filas: la pregunta que contesta esta tabla es cuánto saca cada
    filtro, no de a cuántas le tocó cada una. Sin decirlo, la suma no cierra
    contra el total de arriba y parece un error de cuentas.
    """
    cuantas = e.get("sistema_solapadas") or 0
    if not cuantas:
        return ""
    una = "oferta cae" if cuantas == 1 else "ofertas caen"
    return (f'<p class="explica">Las filas suman más que las ofertas: '
            f'{cuantas} {una} por más de un filtro a la vez y se cuentan en '
            f'cada uno. Son {e.get("sistema_total", 0)} distintas.</p>')


_MOTIVOS_SISTEMA = {
    "idioma": "Piden un inglés más alto que el tuyo",
    "lugar": "El lugar o la modalidad no te sirven",
    "no_es_oferta": "No es una oferta de trabajo",
    "titulo": "El título dice un puesto que no hacés",
    "tecnologias": "Pide tecnologías que no usás, sin alternativa",
    "nivel": "Es para un nivel menor al que buscás",
}


def _desglose(encabezados: tuple[str, str], filas: list[tuple[str, int]],
              total: int | None = None) -> str:
    """Un desglose, como gráfico o como tabla según cuántas filas tenga.

    El gráfico se gana el lugar cuando hay varias magnitudes que comparar de un
    vistazo. Con dos filas no hay comparación, hay dos números, y para dos
    números la tabla ocupa menos y se lee más rápido. El corte está en
    `graficos.MINIMO_PARA_GRAFICAR`.

    **Con `total` va siempre en barras**, medidas contra ese total. Ahí la
    pregunta ya no es cuál es más grande sino qué parte del total es cada una,
    y eso la tabla no lo muestra aunque haya una sola fila.

    **La tabla no desaparece nunca**: cuando hay gráfico va debajo, plegada.
    Un gráfico no da el valor exacto ni se puede copiar, y a veces lo que se
    quiere es justamente el número.
    """
    from vacantia.ui.graficos import barras, vale_un_grafico

    tabla = _tabla(encabezados, filas)
    if total:
        grafico = barras(filas, encabezados[1].lower(), total=total)
    elif vale_un_grafico(filas):
        grafico = barras(filas, encabezados[1].lower())
    else:
        return tabla
    if not grafico:
        return tabla
    return f"""{grafico}
<details class="como"><summary>Ver los números</summary>{tabla}</details>"""


def _grafico_de_puntajes(tramos: list[dict] | None) -> str:
    """El histograma de puntajes. La forma de la lista, de un vistazo.

    Va en columnas y no en barras horizontales porque el eje tiene un orden
    propio: de 0 a 100. Ordenarlo por tamaño, como hace `barras`, destruiría lo
    único que este gráfico tiene para decir.
    """
    from vacantia.ui.graficos import columnas

    if not tramos or not any(t.get("cuantas") for t in tramos):
        return ('<p class="explica">Todavía no hay ofertas puntuadas.</p>')
    datos = [{"etiqueta": t["etiqueta"], "cuantas": t["cuantas"],
              "destacada": t.get("avisa")} for t in tramos]
    return f"""{columnas(datos)}
<p class="pie-grafico"><span class="marca-color" aria-hidden="true"></span>
De este puntaje para arriba el sistema te avisa por Telegram. Se cambia en Mi
perfil, en <i>Puntaje mínimo para avisarme</i>.</p>"""


def _cuesta_el_ingles(perfil: str, ingles: dict) -> str:
    """Cuántas ofertas quedan afuera por el inglés, y cómo se cambia eso.

    Éste es el lugar del dato: acá se vino a mirar números, y el número viene
    con la salida al lado. Arriba de la lista de trabajos no va, porque ahí la
    persona vino a aplicar y lo primero que leería sería lo que se pierde.
    """
    cuantas = (ingles or {}).get("cuantas") or 0
    if not cuantas:
        return ""
    mejor, titulo = ingles.get("mejor"), ingles.get("mejor_titulo") or ""
    detalle = ""
    if mejor is not None:
        detalle = f" La mejor puntuaba {mejor} de 100"
        detalle += f": {titulo}." if titulo else "."
    return f"""<div class="callout atencion">
  <p><b>{esc(cuantas)} ofertas</b> piden un inglés más alto que el que declaraste.
  {esc(detalle)}</p>
  <p>Ese número sube cada vez que marcás una oferta como <i>Piden inglés</i>, y
  baja solo si subís tu nivel declarado.</p>
  <a class="salida" href="/datos?perfil={esc(perfil)}">Cambiar mi nivel de inglés</a>
</div>"""


def _como_viene_funcionando(perfil: str, salud: dict | None) -> str:
    """El "¿esto anda?" que antes había que abrir en una ventana negra aparte.

    Es lo mismo que mostraba la pantalla de estado: si está programado, cuándo
    corrió, qué encontró, si avisó por Telegram y qué se quejó. La diferencia es
    que ahora está adentro de la app, en castellano y sin nombres de archivo.

    Los avisos del registro van adentro de un desplegable: son texto de máquina,
    interesan cuando algo falla y no tienen por qué ocupar la pantalla el resto
    del tiempo.
    """
    if not salud:
        return ""

    # **Acá NO va el botón de buscar.** Métricas es una pantalla de lectura: se
    # entra a entender qué está pasando, no a hacer algo. El botón vivía suelto
    # al final de todo, lejos de cualquier cosa con la que tuviera relación, y
    # además ya está donde corresponde, al pie de la barra lateral, que se ve
    # desde todas las pantallas y ésta incluida.
    ahora = ("<p>Hay una búsqueda en curso. Cuando entren ofertas nuevas te "
             "avisa la pantalla de Trabajos.</p>"
             if salud.get("corriendo") else "")

    tareas = salud.get("programada")
    if tareas is None:
        programado = ('<p class="explica">No puedo consultar las búsquedas '
                      'automáticas en este sistema. Las de esta pantalla '
                      'funcionan igual.</p>')
    elif not tareas:
        programado = ('<p class="explica">No está programado para buscar solo. '
                      'Volvé a correr la instalación para activarlo.</p>')
    else:
        filas = "".join(
            f'<tr><td>{esc(t["nombre"])}</td><td>{esc(t["estado"])}</td>'
            f'<td class="fecha">{esc(t["proxima"])}</td></tr>' for t in tareas
        )
        programado = (
            '<table class="numeros"><thead><tr><th>Búsqueda automática</th>'
            '<th>Estado</th><th class="fecha">Próxima</th></tr></thead>'
            f'<tbody>{filas}</tbody></table>'
        )

    encontro = ""
    if salud.get("encontro"):
        cuando = salud.get("cuando") or ""
        duracion = salud.get("duracion") or ""
        pie = f"La última terminó {cuando}" if cuando else "En la última búsqueda"
        if duracion:
            pie += f", en {duracion}"
        encontro = (f'<p class="explica">{esc(pie)}.</p>'
                    + _tabla(("En la última búsqueda", "Ofertas"), salud["encontro"]))

    telegram = salud.get("telegram")
    aviso = (f'<p class="explica">Último aviso por Telegram: {esc(telegram)}.</p>'
             if telegram else
             '<p class="explica">Todavía no se envió ningún aviso por Telegram. '
             'Puede ser normal si no hubo ofertas que pasen el puntaje mínimo.</p>')

    problemas = ""
    if salud.get("problemas"):
        lineas = "".join(f"<li>{esc(p)}</li>" for p in salud["problemas"])
        problemas = f"""<details class="como">
  <summary>Ver los últimos avisos del registro</summary>
  <ul class="registro">{lineas}</ul>
  <p class="ayuda">Son las quejas que el sistema decidió no considerar graves.
  Si siempre aparece la misma, algo hay que mirar.</p>
</details>"""

    # Primero el gráfico: contesta de un vistazo la pregunta de toda la sección.
    # Una búsqueda en cero puede ser un mal día; varios días seguidos en cero
    # es que algo dejó de andar, y la tabla de la última búsqueda no lo dice.
    #
    # Con las dos semanas enteras en cero no va el gráfico: catorce columnas
    # grises son un gráfico vacío, y la frase avisa más fuerte que el dibujo.
    entradas = ""
    if salud.get("entradas"):
        from vacantia.ui.graficos import columnas

        if any(d.get("cuantas") for d in salud["entradas"]):
            entradas = ('<p class="explica">Ofertas nuevas por día, en las últimas '
                        'dos semanas. Un día en cero puede pasar; varios seguidos, '
                        'es que algo dejó de andar.</p>' + columnas(salud["entradas"]))
        else:
            entradas = ('<p>No entró ninguna oferta nueva en las últimas dos '
                        'semanas.</p>')

    # Va en su propia sección al pie y **no como un panel más**: no es un dato
    # sobre tu búsqueda de trabajo, es el estado de la máquina. Mezclarlo con
    # los desgloses obliga a leer "cuántas ofertas piden inglés" y "cuándo corre
    # la tarea programada" como si fueran la misma clase de cosa.
    return f"""<section class="salud">
  <h2>Cómo viene funcionando</h2>
  <p class="explica">El estado del programa, no de tu búsqueda. Mirá acá cuando
  algo no cierre: si hace días que no entra nada, la respuesta suele estar
  abajo.</p>
  {entradas}
  {programado}
  {encontro}
  {aviso}
  {problemas}
  {ahora}
</section>"""


def _habilidades(h: dict | None) -> str:
    """Qué te están pidiendo los avisos que entraron.

    Sale del campo que el modelo ya devolvía por cada oferta cuando la puntúa,
    así que **no cuesta ninguna llamada extra**: el aviso ya se le manda entero
    para puntuarlo, y pedirle de paso qué piden son unos tokens más de
    respuesta.

    Eso es también lo que la hace servir para cualquier oficio. No hay ninguna
    lista de tecnologías escrita en el código: el modelo lee el aviso y devuelve
    lo que ese aviso pide, sea LangChain, Google Analytics o la ISO 45001. Una
    lista escrita a mano habría que mantenerla para siempre y aun así nunca
    cubriría los oficios de los demás perfiles de la casa.

    Cuando quedan ofertas sin analizar se dice cuántas. Sin eso, un gráfico
    flaco se lee como "no piden nada" en vez de "todavía no lo miré todo".

    **Cada barra se mide contra las ofertas analizadas**, no contra la habilidad
    más pedida. "Python 161, AWS 45" no decía si AWS era algo que hay que
    aprender o un "bueno de tener": con el total al lado se ve que es 18% de
    245. Las que no pasaron por el analizador no entran en el total, porque no
    tienen nada que pedir.
    """
    from vacantia.ui.graficos import barras

    if not h or not h.get("filas"):
        return ""

    pie = ""
    if h.get("sin_datos"):
        cuantas = h["sin_datos"]
        una = "oferta todavía no pasó" if cuantas == 1 else "ofertas todavía no pasaron"
        pie = (f'<p class="pie-grafico">{cuantas} {una} por el analizador y no '
               f'suman acá. Entran solas en la próxima búsqueda.</p>')
    analizadas = h.get("ofertas") or 0
    return f"""{barras(h["filas"], "ofertas", total=analizadas or None)}
{pie}"""


def _panel(titulo: str, explica: str, cuerpo: str, total: int | None = None,
           que: str = "", de_donde: str = "") -> str:
    """Un bloque de Métricas: título, para qué sirve, y el gráfico.

    Métricas era una columna larguísima de secciones apiladas, con el gráfico de
    una y la explicación de la siguiente pegados, y media pantalla vacía a la
    derecha. Cada bloque encerrado en su propio panel se puede acomodar en dos
    columnas, y sobre todo deja de haber duda de a qué gráfico corresponde cada
    texto.

    **La explicación va arriba del gráfico y nunca abajo.** Un gráfico sin saber
    qué mide no se puede leer, así que leerlo primero y buscar el pie después es
    hacer el trabajo dos veces.

    El `explica` llega con los saltos y la sangría del f-string que lo escribió;
    se aplastan acá para que el HTML no salga con veinte espacios en el medio de
    una oración.
    """
    if not cuerpo.strip():
        return ""
    return f"""<section class="panel">
  {_cabecera(titulo, explica, total, que, de_donde)}
  {cuerpo}
</section>"""


def estadisticas(perfil: str, e: dict, desde: str, mensajes,
                 salud: dict | None = None,
                 puntajes: list[dict] | None = None,
                 habilidades: dict | None = None) -> str:
    """Los números que antes vivían apretados en los botones de arriba.

    Se separó porque compiten: mientras uno revisa ofertas, el único número que
    importa es cuántas faltan. "Archivadas 83" no es una tarea, es un archivo, y
    ocupaba el mismo espacio.
    """
    ingles = e.get("ingles") or {}
    sistema = e.get("sistema") or {}

    # Las tarjetas tienen que sumar el total, y no sumaban: faltaban las que
    # sacó el filtro, que eran 132 de 230. Se veía 10 + 84 + 4 y abajo "230 en
    # total", y la pregunta obvia era "¿230 qué?".
    partes = (e["sin_marcar"], e["aplicadas"], e["descartadas"], e["archivadas"],
              e.get("sistema_total") or 0)
    tarjetas = (
        _dato(e["sin_marcar"], "sin mirar", destacado=True)
        + _dato(e["aplicadas"], "aplicaste")
        + _dato(e["descartadas"], "descartaste")
        + _dato(e["archivadas"], "archivadas")
        + _dato(partes[4], "las sacó el filtro")
        + _dato(e["total"], "ofertas en total")
    )
    # La cuenta va escrita sólo si cierra. Una oferta archivada que además está
    # marcada contaría en dos tarjetas, y una suma que no da es peor que ninguna.
    suma = ""
    if e["total"] and sum(partes) == e["total"]:
        cuenta = " + ".join(str(p) for p in partes)
        suma = (f'<p class="explica">Cada oferta que entró está en una sola de '
                f'estas tarjetas: {cuenta} = {e["total"]}.</p>')

    analizadas = (habilidades or {}).get("ofertas") or 0
    sin_analizar = (habilidades or {}).get("sin_datos") or 0
    de_donde_analizadas = (f"de las {analizadas + sin_analizar} que entraron"
                           if sin_analizar else "")
    puntuadas = sum(t.get("cuantas") or 0 for t in (puntajes or []))

    motivos_filas = []
    from vacantia.ui.data import MOTIVOS
    etiquetas = {c: t for c, t, _ in MOTIVOS}
    for clave, cuantas in sorted((e.get("motivos") or {}).items(),
                                 key=lambda kv: -kv[1]):
        motivos_filas.append((etiquetas.get(clave, "Escrito a mano"), cuantas))

    sistema_filas = [(_MOTIVOS_SISTEMA.get(k, k), v)
                     for k, v in sorted(sistema.items(), key=lambda kv: -kv[1])]

    ventana = e.get("max_age_days")
    fuentes = list((e.get("por_fuente") or {}).items())

    # La pantalla cuenta tres cosas distintas y en este orden, que es el orden
    # en que sirven: qué hiciste, qué te piden ahí afuera, y qué está entrando.
    # Antes eran cinco paneles idénticos uno atrás del otro sin nada que dijera
    # cuál mirar primero, que es lo que la hacía confusa: todo pesaba igual.
    pedido = _habilidades(habilidades)
    foco = f"""<section class="foco">
  {_cabecera("Qué te están pidiendo",
             '''Las habilidades, herramientas y certificaciones que nombran los
             avisos, y en qué parte de ellos aparece cada una. <b>Es lo único de
             esta pantalla que dice qué hacer mañana</b>: lo que está arriba y no
             tenés es lo que más te está costando entrevistas.''',
             analizadas, "ofertas analizadas", de_donde_analizadas)}
  {pedido}
</section>""" if pedido else ""

    return f"""{avisos(mensajes)}
<h1>Métricas</h1>
<div class="tarjetas">{tarjetas}</div>
{suma}

{foco}

<h2 class="seccion">Qué está entrando, y qué queda afuera</h2>
<div class="paneles">
{_panel("Qué tan bien te encajan",
        '''Cuántas ofertas hay en cada tramo de puntaje, sobre todo lo que se
        buscó alguna vez. Una montaña pegada al cero significa que las búsquedas
        están mal apuntadas; una repartida significa que el problema es otro.''',
        _grafico_de_puntajes(puntajes),
        puntuadas, "ofertas puntuadas", "desde siempre" if desde != "todo" else "")}

{_panel("Por qué descartaste vos",
        '''Los motivos que elegiste al marcar <b>No apliqué</b>, medidos contra
        todas las que descartaste. Es lo único que el sistema puede aprender de
        vos: si la mayoría cae en un mismo motivo, ahí hay un filtro que conviene
        apretar en Mi perfil. Abajo, lo que escribiste a mano cuando ninguno de
        la lista servía.''',
        _desglose(("Motivo", "Ofertas"), motivos_filas,
                  total=e.get("descartadas") or 0)
        + _escritos_a_mano(e.get("escritos") or [], e.get("descartadas") or 0),
        e.get("descartadas") or 0, "descartaste")}

{_panel("Lo que descartó el sistema, sin preguntarte",
        '''Son las que no llegan a <b>Sin marcar</b> porque ya hay un veredicto:
        no las borra nadie y vuelven solas si cambiás el filtro que las sacó.''',
        _solapadas(e)
        + _desglose(("Motivo", "Ofertas"), sistema_filas)
        + _cuesta_el_ingles(perfil, ingles),
        e.get("sistema_total") or 0, "sacó el filtro")}

{_panel("De dónde vienen",
        f'''Qué portal trajo cada oferta, medido contra todas las que entraron.
        Ventana de búsqueda: los últimos
        {esc(ventana if ventana is not None else "?")} días, que se cambia en
        Configuración.''',
        _desglose(("Portal", "Ofertas"), fuentes, total=e.get("total") or 0),
        e.get("total") or 0, "ofertas que entraron")}
</div>

{_como_viene_funcionando(perfil, salud)}"""
