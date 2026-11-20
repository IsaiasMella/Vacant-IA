"""Las dos pantallas que se abren desde la tarjeta: mensajes y consejo.

Mensajes para el reclutador, y qué reordenar del CV para un aviso.
"""

from vacantia.ui.render.comun import ABRIR_EL_AVISO, avisos, esc

# --- mensajes para el reclutador -------------------------------------------

def linea_de_cv(cv: dict | None, que: str) -> str:
    """"Mandá tu CV Full Stack", con la marca de estimado cuando corresponde.

    La usan la tarjeta, Consejo y Mensajes, así las tres pantallas lo dicen
    igual. Vacía cuando no hay CV que nombrar, que es el caso de un perfil con
    un solo CV: ahí la línea no dice nada que la persona no sepa.

    Va en texto secundario y **no en índigo**: es información, no se toca, y en
    este sistema el índigo significa que algo se puede apretar.
    """
    if not cv or not cv.get("nombre"):
        return ""
    marca = (' <span class="cv-estimado" title="Calculado comparando las palabras '
             'del aviso con cada CV, sin preguntarle al modelo">estimado</span>'
             if cv.get("estimado") else "")
    return f'<p class="cv-recomendado">{que} <b>{esc(cv["nombre"])}</b>{marca}</p>'


def mensajes(perfil: str, oferta: dict, textos: dict[str, str], con_llm: bool,
             avisos_: list[tuple[str, str]], cv_usado: dict | None = None) -> str:
    """Los dos moldes, en cajas de texto para copiar y pegar."""
    titulo = oferta.get("scored_title") or oferta.get("title") or "(sin título)"
    url = oferta.get("url", "")
    cajas = "".join(
        f"""<div class="mensaje">
  <h3>{esc(etiqueta)}</h3>
  <textarea rows="8" onclick="this.select()">{esc(textos.get(clave, ''))}</textarea>
  <p class="ayuda">Clic adentro para seleccionar todo y copiar.</p>
</div>"""
        for clave, etiqueta in (("dm", "DM por LinkedIn"), ("mail", "Mail a RRHH"))
    )
    boton = "" if con_llm else f"""<form method="post" action="/mensajes">
  <input type="hidden" name="perfil" value="{esc(perfil)}">
  <input type="hidden" name="url" value="{esc(url)}">
  <button class="primario" type="submit">Completar con IA leyendo el aviso y mi CV</button>
  <p class="ayuda">Usa una llamada al modelo. Sin esto, completá a mano lo que
  está entre llaves.</p>
</form>"""
    return f"""{avisos(avisos_)}
<h1>Mensaje para {esc(oferta.get('company') or 'quien publicó')}</h1>
{linea_de_cv(cv_usado, 'Escrito para tu CV')}
<p class="sub"><span class="dato-linea">{esc(titulo)}</span>
<a href="{esc(url)}" {ABRIR_EL_AVISO}>Ver el aviso en el portal</a></p>
<p class="herramientas"><a class="boton" href="/trabajos?perfil={esc(perfil)}">Volver a Trabajos</a></p>
{cajas}
{boton}
<p class="ayuda">Estos moldes son un borrador: máximo 4 líneas, cero adjetivos
sobre uno mismo, y cerrar con una pregunta fácil de responder.</p>"""


# --- consejo sobre el CV ----------------------------------------------------

def consejo(perfil: str, oferta: dict, faltantes: list[str], texto: str,
            con_llm: bool, avisos_: list[tuple[str, str]],
            cv_usado: dict | None = None) -> str:
    """Qué reordenar del CV para este aviso. No lo reescribe."""
    titulo = oferta.get("scored_title") or oferta.get("title") or "(sin título)"
    url = oferta.get("url", "")

    if faltantes:
        lista = "".join(f"<li>{esc(t)}</li>" for t in faltantes)
        huecos = f"""<ul class="terminos">{lista}</ul>
<p class="ayuda">Están en el aviso y no en tu CV. <b>No las agregues si no las
hacés</b>: se nota en la primera entrevista. Sí valen las que sabés hacer y
escribiste con otra palabra.</p>"""
    else:
        huecos = ('<p class="ayuda">Tu CV ya menciona todos los términos '
                  'importantes del aviso.</p>')

    if texto:
        cuerpo = f'<div class="mensaje"><pre class="consejo">{esc(texto)}</pre></div>'
    else:
        cuerpo = f"""<form method="post" action="/consejo">
  <input type="hidden" name="perfil" value="{esc(perfil)}">
  <input type="hidden" name="url" value="{esc(url)}">
  <button class="primario" type="submit">Leer el aviso y decirme qué reordenar</button>
  <p class="ayuda">Usa una llamada al modelo. No reescribe el CV: dice qué subir
  y qué palabra falta.</p>
</form>"""

    return f"""{avisos(avisos_)}
<h1>Consejo para tu CV</h1>
{linea_de_cv(cv_usado, 'Comparando con tu CV')}
<p class="sub"><span class="dato-linea">{esc(titulo)}</span>
<span class="dato-linea">{esc(oferta.get('company') or 'sin empresa')}</span>
<a href="{esc(url)}" {ABRIR_EL_AVISO}>Ver el aviso en el portal</a></p>
<p class="herramientas"><a class="boton" href="/trabajos?perfil={esc(perfil)}">Volver a Trabajos</a></p>

<h2>Palabras del aviso que no están en tu CV</h2>
<div class="mensaje">{huecos}</div>

<h2>Qué mover</h2>
{cuerpo}
<p class="ayuda">Tu CV no se toca: esto es para que lo edites vos con criterio.</p>"""
