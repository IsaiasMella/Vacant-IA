"""La pestaña Entrevistas: subir una grabación y leer el repaso.

El análisis lo hace `vacantia/entrevistas.py`; acá sólo se arma el HTML. Dos
pantallas: la lista (con el formulario para subir) y el repaso de una.

**La oferta es opcional.** La entrevista llega semanas después del CV, a veces
por un mensaje privado a alguien de RRHH, y uno no se acuerda por dónde mandó.
Por eso la pantalla sólo *propone* las ofertas del historial que pueden ser de
esa empresa, y el repaso sale igual si no se elige ninguna.
"""

from datetime import date

from vacantia.ui.render.comun import ABRIR_EL_AVISO, avisos, esc

#: Cómo se dice cada estado de una entrevista en la lista.
ESTADO = {
    "subida": "Esperando",
    "procesando": "Analizando…",
    "lista": "Lista",
    "error": "No se pudo analizar",
}

#: Cómo estuvo cada respuesta. **Floja no va en rojo:** el rojo en esta app es
#: para errores y acciones destructivas, y una respuesta floja es algo para
#: practicar, no un error del sistema.
COMO_ESTUVO = {"bien": "Bien", "regular": "Regular", "floja": "Floja"}


def _fecha(iso: str) -> str:
    from vacantia.ui.semanas import dia_corto

    try:
        return dia_corto(date.fromisoformat(iso))
    except (TypeError, ValueError):
        return iso or ""


def _formulario_de_subida(perfil: str) -> str:
    """Empresa, fecha y grabación. La sube `app.js` (ver `subirEntrevista`).

    No es un formulario común porque la grabación es un video de cientos de MB:
    el navegador la manda entera como cuerpo del pedido y el servidor la escribe
    a disco de a pedazos, sin cargarla en memoria. Por eso hace falta
    JavaScript, y sin él lo dice.
    """
    from vacantia.entrevistas import EXTENSIONES

    hoy = date.today().isoformat()
    return f"""<form class="subir-entrevista mensaje" id="subir-entrevista"
      data-perfil="{esc(perfil)}" onsubmit="return subirEntrevista(this)">
  <h2>Cargar una entrevista</h2>
  <div class="campo">
    <label for="ent-empresa">Empresa</label>
    <input id="ent-empresa" name="empresa" type="text" required maxlength="80"
           placeholder="Como te acuerdes, por ejemplo RedBee">
  </div>
  <div class="campo">
    <label for="ent-fecha">Fecha de la entrevista</label>
    <input id="ent-fecha" name="fecha" type="date" value="{hoy}" max="{hoy}">
  </div>
  <div class="campo">
    <label for="ent-grabacion">Grabación</label>
    <input id="ent-grabacion" name="grabacion" type="file" required
           accept="{esc(','.join(EXTENSIONES))}">
    <p class="ayuda">El video de Meet, Zoom o Teams, o un audio. Se le saca el
    audio en tu computadora y sólo el audio se manda a Gemini (Google) para
    pasarlo a texto.</p>
  </div>
  <button class="primario" type="submit">Analizar la entrevista</button>
  <progress class="progreso-subida" max="100" value="0" hidden></progress>
  <p class="estado-subida ayuda" aria-live="polite"></p>
  <noscript><p class="ayuda">Para subir la grabación hace falta tener JavaScript
  activado en el navegador.</p></noscript>
</form>"""


def entrevistas(perfil: str, lista: list[dict], avisos_: list[tuple[str, str]]) -> str:
    """La lista de entrevistas, la más reciente arriba, y el formulario."""
    if lista:
        filas = "".join(
            f"""<li class="entrevista-item">
  <a href="/entrevistas?perfil={esc(perfil)}&amp;id={esc(e['id'])}">
    <span class="empresa">{esc(e['empresa'])}</span>
    <span class="cuando">{esc(_fecha(e.get('fecha', '')))}</span>
  </a>
  <span class="estado-entrevista {esc(e.get('estado', ''))}">{esc(ESTADO.get(e.get('estado', ''), ''))}</span>
</li>"""
            for e in lista)
        historial = f'<h2>Tus entrevistas</h2><ul class="lista-entrevistas">{filas}</ul>'
    else:
        historial = ('<p class="vacio-corto">Todavía no cargaste ninguna. Cuando '
                     'tengas la grabación de una entrevista, subila acá.</p>')
    return f"""{avisos(avisos_)}
<h1>Entrevistas</h1>
<p class="sub">Subí la grabación de una entrevista y te devuelvo, pregunta por
pregunta, qué respondiste, qué faltó y cómo responderla la próxima con lo que
dice tu CV.</p>
{_formulario_de_subida(perfil)}
{historial}"""


def estado_en_curso(perfil: str, datos: dict) -> str:
    """El cartel de "analizando", que se pregunta solo cada 4 segundos.

    Cuando termina, el servidor contesta con `HX-Refresh` y la página se
    recarga entera con el repaso: no hay que apretar nada.
    """
    paso = datos.get("paso") or "Arrancando"
    return f"""<div class="analizando mensaje" role="status"
     hx-get="/entrevista-estado?perfil={esc(perfil)}&amp;id={esc(datos['id'])}"
     hx-trigger="every 4s" hx-swap="outerHTML">
  <p><b>Analizando la entrevista.</b> {esc(paso)}…</p>
  <p class="ayuda">Una entrevista de una hora tarda unos minutos. Podés seguir
  usando la pantalla: cuando termine, esta página se actualiza sola.</p>
</div>"""


def _lista(titulo: str, items: list[str]) -> str:
    if not items:
        return ""
    return (f'<section class="repaso-bloque"><h2>{esc(titulo)}</h2><ul>'
            + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul></section>")


def _pregunta(p: dict) -> str:
    """Una pregunta, plegada. Las flojas vienen abiertas: son lo que hay que mirar."""
    como = p.get("como_estuvo", "regular")
    abierta = " open" if como == "floja" else ""
    falto = (f'<h4>Qué faltó</h4><p>{esc(p["que_falto"])}</p>'
             if p.get("que_falto") else "")
    return f"""<details class="pregunta"{abierta}>
  <summary><span class="texto">{esc(p['pregunta'])}</span>
    <span class="como {esc(como)}">{esc(COMO_ESTUVO.get(como, como))}</span></summary>
  <div class="cuerpo">
    <h4>Lo que respondiste</h4><p>{esc(p.get('tu_respuesta') or '—')}</p>
    {falto}
    <h4>Cómo responderla la próxima</h4><p>{esc(p.get('mejor_respuesta') or '—')}</p>
  </div>
</details>"""


def _ofertas_propuestas(perfil: str, datos: dict, parecidas: list[dict]) -> str:
    """"¿Es por alguna de éstas?": las del historial con el nombre de la empresa."""
    if datos.get("oferta_url") or not parecidas:
        return ""
    filas = []
    for o in parecidas:
        cuando = (f"aplicaste el {_fecha((o.get('fecha_feedback') or '')[:10])}"
                  if o.get("aplicado") is True else
                  f"la viste el {_fecha((o.get('found_at') or '')[:10])}")
        filas.append(f"""<li>
  <form method="post" action="/entrevista-vincular">
    <input type="hidden" name="perfil" value="{esc(perfil)}">
    <input type="hidden" name="id" value="{esc(datos['id'])}">
    <input type="hidden" name="url" value="{esc(o.get('url', ''))}">
    <span class="dato-linea"><b>{esc(o.get('scored_title') or o.get('title') or '')}</b>
      · {esc(o.get('company') or '')} · {esc(o.get('source') or '')} · {esc(cuando)}</span>
    <button type="submit">Es ésta</button>
  </form>
</li>""")
    return f"""<section class="repaso-bloque propuestas">
  <h2>¿Es por alguna de éstas?</h2>
  <p class="ayuda">Son las de tu historial con ese nombre de empresa. Si es una,
  el próximo análisis la tiene en cuenta. Si mandaste el CV por otro lado, no
  hace falta elegir nada.</p>
  <ul>{"".join(filas)}</ul>
</section>"""


def entrevista(perfil: str, datos: dict, analisis: dict | None, transcripcion: str,
               parecidas: list[dict], oferta: dict | None,
               avisos_: list[tuple[str, str]]) -> str:
    """El repaso de una entrevista."""
    ident = esc(datos["id"])
    estado = datos.get("estado", "")
    ocultos = (f'<input type="hidden" name="perfil" value="{esc(perfil)}">'
               f'<input type="hidden" name="id" value="{ident}">')

    if oferta:
        vinculo = (f'<span class="dato-linea">Por el aviso '
                   f'<a href="{esc(oferta.get("url", ""))}" {ABRIR_EL_AVISO}>'
                   f'{esc(oferta.get("scored_title") or oferta.get("title") or "")}</a>'
                   f' ({esc(oferta.get("source") or "")})</span>')
    else:
        vinculo = ""

    if estado in ("subida", "procesando"):
        cuerpo = estado_en_curso(perfil, datos)
    elif estado == "error":
        cuerpo = f"""{avisos([("error", datos.get("error") or "No se pudo analizar.")])}
<form method="post" action="/entrevista-analizar">{ocultos}
  <button class="primario" type="submit">Probar de nuevo</button>
</form>"""
    else:
        a = analisis or {}
        preguntas = "".join(_pregunta(p) for p in a.get("preguntas") or [])
        proximos = (f'<section class="repaso-bloque"><h2>Lo que sigue</h2>'
                    f'<p>{esc(a["proximos_pasos"])}</p></section>'
                    if a.get("proximos_pasos") else "")
        volver = (f"""<form method="post" action="/entrevista-analizar">{ocultos}
  <button type="submit">Volver a analizar</button>
  <p class="ayuda">Usa la transcripción guardada, no vuelve a subir el audio.
  Sirve después de elegir el aviso.</p>
</form>""")
        cuerpo = f"""<div class="mensaje resumen-entrevista"><p>{esc(a.get('resumen', ''))}</p></div>
{_ofertas_propuestas(perfil, datos, parecidas)}
<section class="repaso-bloque"><h2>Pregunta por pregunta</h2>
{preguntas or '<p class="ayuda">No encontré preguntas en la transcripción.</p>'}</section>
{_lista("Lo que salió bien", a.get("lo_que_salio_bien") or [])}
{_lista("Para corregir", a.get("a_mejorar") or [])}
{_lista("Temas para repasar", a.get("temas_para_repasar") or [])}
{_lista("Lo que preguntaste vos", a.get("preguntas_que_hiciste") or [])}
{_lista("Para preguntar la próxima", a.get("preguntas_para_la_proxima") or [])}
{proximos}
{volver}"""

    texto = (f"""<details class="transcripcion"><summary>Ver la transcripción</summary>
<pre>{esc(transcripcion)}</pre></details>""" if transcripcion else "")
    borrar = f"""<form method="post" action="/entrevista-borrar">{ocultos}
  <details class="borrar-cv">
    <summary>Borrar esta entrevista</summary>
    <div class="cuerpo">
      <p>Se borra la entrevista con <b>{esc(datos['empresa'])}</b>: la
      transcripción y el análisis. Tu grabación original no se toca.</p>
      <button class="peligro" type="submit">Sí, borrarla</button>
    </div>
  </details>
</form>"""

    return f"""{avisos(avisos_)}
<h1>Entrevista con {esc(datos['empresa'])}</h1>
<p class="sub"><span class="dato-linea">{esc(_fecha(datos.get('fecha', '')))}</span>
{vinculo}</p>
<p class="herramientas"><a class="boton" href="/entrevistas?perfil={esc(perfil)}">Volver a Entrevistas</a></p>
{cuerpo}
{texto}
{borrar}"""
