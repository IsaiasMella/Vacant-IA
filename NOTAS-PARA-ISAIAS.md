# Notas para Isaías

**740 tests pasan.**

```
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests -q      →  740 passed
```

Andando todo: los 3 portales argentinos, Indeed, Get on Board, LinkedIn Jobs,
las páginas de empleo de las empresas, seguir reclutadores, el scoring con
Gemini y la pantalla.

Este archivo es corto a propósito: qué falta, qué hay que saber para usarlo, y
las decisiones que no conviene deshacer. El porqué detallado de cada cosa está
en los docstrings del código. La versión larga de estas notas está en el
historial de git, en el commit `fe29188`; 2.40 y 2.41 no llegaron a esa versión.

---

# 1. LO QUE FALTA HACER

| # | Qué | Dónde |
|---|---|---|
| 1 | **Cargar tu CV de Full Stack**, con sus puestos y habilidades. Hasta entonces 2.29 no se nota | Mi perfil → Mis CV |
| 2 | **Decidir qué hacés con el inglés.** Hay unas 90 ofertas ya puntuadas esperando detrás de esa casilla (2.28) | Mi perfil |
| 3 | **Usarlo una semana** y anotar qué falla antes de pasárselo a nadie | — |
| 4 | **4 ofertas viejas sin los juicios de 2.41** (3 de `google_posts`, 1 de .NET). Marcarlas a mano o re-puntuarlas (4 llamadas) | Trabajos |

Ya está instalado y corre solo desde el 5/9/2026 (2.14). Armarle la copia a cada
familiar queda para después de la semana de prueba (2.32).

---

# 2. LO QUE TENÉS QUE SABER

## 2.1. Cómo filtra por ubicación

| Campo | Qué hace |
|---|---|
| `country` vacío | de todo el mundo |
| `country: "Argentina"` | **sólo Argentina, también el remoto** |
| `city` vacía | cualquier lugar del país |
| `city: ["Bahía Blanca", "Punta Alta"]` | **sólo filtra presencial e híbrido**; el remoto entra venga de donde venga |
| `work_modes: ["remote"]` | sólo remoto, salvo un presencial en tus ciudades, que entra igual |

- El remoto tiene que ser de Argentina: uno de Colombia o México, que por temas
  legales contrata sólo allá, no entra.
- Tu perfil: `country: "Argentina"`, `city: "Bahía Blanca"`. Se edita en Mi perfil.
- Para aceptar remoto de cualquier país: `"remote_anywhere": true` dentro de
  `filters.location`. Está apagado.

## 2.2. Telegram: cada persona su chat

Las claves son de la máquina, **el chat no**. Sin esto, dos personas en la misma
compu reciben todo en el mismo teléfono.

1. Que le escriba cualquier cosa a su bot.
2. Su `chat_id`: `https://api.telegram.org/bot<TOKEN>/getUpdates` → `"chat":{"id":...}`,
   o @userinfobot (link en Configuración).
3. Configuración → *Mi Telegram* → pegar → Guardar.

Vacío = usa el `TELEGRAM_CHAT_ID` del `.env`, o sea el tuyo.

## 2.3. Corrida de prueba

```
.venv\Scripts\python.exe -m vacantia.run --profile isaias --dry-run
$env:LOG_LEVEL="DEBUG"; .venv\Scripts\python.exe -m vacantia.run --profile isaias --dry-run
```

Corre todo e imprime el resultado, pero no manda Telegram ni escribe el
historial. **Sí gasta** llamadas al modelo y a TinyFish. La de verdad es la
misma línea sin `--dry-run`, o el botón **Buscar ahora** de la barra lateral.
Todo queda en `vacantia.log`.

## 2.4. Los mensajes al reclutador

Son tus mensajes de siempre (`vacantia/mensajes.py`). El modelo sólo escribe la
lista de requisitos que tu CV respalda y el nombre limpio del puesto. El cierre
según el día, tu nombre y *Cómo me presento* los pone el código: un modelo no
sabe qué día es.

## 2.5. El 403 de Computrabajo

Lo causaba la pantalla: el referrer `http://127.0.0.1:8756` terminaba en la
cookie `extrfr` y el firewall de Computrabajo lo leía como un ataque. Los links
salen con `rel="noreferrer"` y no vuelve a pasar. **No sacar ese
`noreferrer`.** Si igual aparece, se borran las cookies de Computrabajo de la
última hora.

## 2.6. Si un portal deja de traer nada

Síntoma: `0 aviso(s)` en `vacantia.log`. Los portales cambian las direcciones.
En el perfil, bloque de esa fuente:

```jsonc
{ "type": "bumeran", "enabled": true,
  "search_url": "una búsqueda real, con {query} donde va el puesto",
  "job_url_pattern": "un pedazo común a las direcciones de aviso, ej: /empleos/" }
```

Si trae avisos pero sin empresa, o con títulos tipo *Oferta De Trabajo De ...*,
el portal cambió la página del aviso y el lector no la entiende (pasó con
Computrabajo, 2.40).

## 2.7. LinkedIn

- Se leen los posts sueltos y la búsqueda de Jobs. **El perfil de una persona no**
  (`HTTP 999`), y no se arregla sin usuario y contraseña, que es lo que haría que
  te bloqueen la cuenta.
- Para seguir a un reclutador se le pregunta a Google por sus publicaciones. Se
  filtra por el identificador del perfil y no por el nombre. Cuesta una búsqueda
  por reclutador y por corrida; se apaga con `"buscar_posts": false` en `rrhh`.
- `google_posts` es otra cosa: busca por puesto, de cualquiera.

## 2.8. Antigüedad de los avisos

- **Una sola perilla** en Configuración, *No traerme avisos de más de N días*, y
  la heredan todas las fuentes. Vos 7, papá 30. `0` la apaga.
- **Un aviso sin fecha entra igual:** lo que no se sabe no filtra.
- **Las recién publicadas van arriba**, en una banda aparte. El puntaje no se
  toca, sólo el orden. No suben las de menos de tu puntaje mínimo ni las que no
  tienen fecha.
- **No bajar la ventana a 1 día:** Google tarda en indexar, y un post de ayer que
  aparece pasado mañana quedaría afuera para siempre. Con 7 días volvían 10
  publicaciones; con 1 día, 2.

## 2.9. Descartar

- Lo que el filtro ya sacó no llega a *Sin marcar*: va a *Filtradas* (2.21) y
  vuelve solo si cambiás el filtro. Se calcula al mirar, no se guarda una marca.
- El motivo se elige de una lista **o** se escribe; con cualquiera alcanza. **No
  hay opción "Otro"** a propósito: agregaba tres pasos justo cuando ya ibas a
  escribir.
- Los motivos viven en `vacantia/motivos.py`. *Inglés*, *presencial* y *caso
  especial* no le enseñan nada al modelo; los otros tres sí (2.41).

## 2.10 a 2.12. Pantalla: detalles chicos

- *Sin marcar* es el número grande; todo lo demás vive en Métricas.
- Después de marcar vuelve a donde estabas. `form.submit()` no dispara `submit`,
  y hay un test que lo fija.
- Los desplegables usan los tokens del sistema y la flecha es un token más.

## 2.13. La cuenta de Gemini

Si el log dice que fallaron los modelos:

- **`404 no longer available`:** Google dio de baja ese modelo. Los vigentes se
  ven en `https://generativelanguage.googleapis.com/v1beta/models?key=TU_KEY` y
  se cambian en `llm.model` / `llm.fallback_models`.
- **`429 prepayment credits are depleted`:** sin saldo. Se arregla en <https://ai.studio/projects>.
- **Plan B:** `provider: "openrouter"` en el perfil (50 llamadas por día).
- **Sin modelo cae a una heurística** que cuenta palabras del título. Esos
  puntajes no significan nada; el log dice `[heurística, sin LLM]`.

## 2.14. Qué hace `instalar.bat`

Registra una tarea de Windows por perfil, `Vacantia - <nombre>`. No queda
ningún proceso corriendo. Se despierta al iniciar sesión (3 minutos después; 13
para el segundo perfil) y en tres horarios por día (12:00, 16:30 y 23:59 con un
solo perfil). Si la compu estaba apagada, corre al prenderla. No abre ventana
(`pythonw.exe`) y no se encima con otra corrida. Cómo le viene yendo: Métricas →
*Cómo viene funcionando*. Para que deje de correr: `desinstalar.bat`.

## 2.15. AI Engineer no es Machine Learning

Conectás modelos ya entrenados a producto; **no entrenás modelos**. Eso tiene
que estar dicho en tres lugares: el CV, los términos de búsqueda y
`not_suitable`. Si falta en uno, se cuelan ofertas de ML con 90 puntos.

## 2.16. Puestos que no querés ni pagar por puntuar

*Puestos que NO quiero*, en Mi perfil: si el **título** tiene uno de esos
términos, se descarta sin llamar al modelo. Sobre tus datos, eso ahorra el 28%
de las llamadas.

- **Nunca mira la descripción:** un AI Engineer nombra "machine learning" todo el tiempo.
- **Antes de puntuar sólo se filtra por título y por país.** Un híbrido en Bahía
  Blanca tiene que entrar, y la ciudad la completa el modelo.

## 2.17. Archivar

*Archivar* (antes *Ya no está*, 2.43) es "no le doy bola a esta oferta", por la
razón que sea: muy vieja, no era una oferta, o lo que fuere. Es un estado
aparte, no un descarte: no lleva motivo, y como descarte le enseñaría al modelo
una preferencia que no dijiste. Se deshace desde *Archivadas*. El atajo por antigüedad no archiva las
que no tienen fecha ni las que ya marcaste.

## 2.18 y 2.19. La pantalla, rearmada

- Todo sale de los tokens de `vacantia/ui/css/tokens.css`. Hay tests que fallan
  si una regla escribe un color suelto o si un par de texto y fondo baja de 4.5:1.
- Un solo tema, el oscuro.
- *Buscar ahora* corre en un proceso aparte, sin ventana, y no deja arrancar dos.
- `buscar_ahora.bat` y `estado.bat` ya no existen: son un botón y una sección de Métricas.

## 2.20, 2.24 y 2.31. LinkedIn URLs

La app arma la dirección y vos la abrís. Es la única forma de llegar a los
posteos del día, porque Google los indexa uno a tres días tarde. Los puestos
tildables son tus *Puestos a buscar*, los mismos que usa el buscador automático
(las habilidades no, 2.48). Arriba de las guardadas están las sugeridas (2.48).

Lo probado contra LinkedIn, que es el mapa si algún día deja de andar:

- **`NOT (a OR b)` devuelve cero:** se emite un NOT por término.
- **Publicaciones tiene un tope de unas 110 letras.** Arriba de eso devuelve cero
  sin avisar. Cuando se recorta, la pantalla lo dice. En Jobs no hay tope.
- **`contentType=["jobs"]` deja la lista en cero:** no usarlo.
- **Jobs:** `geoId=100446943` es Argentina, `f_WT` la modalidad, `f_E=4`
  Mid-Senior, `f_TPR` la antigüedad. El link 1 de
  `estrategia-links-linkedin-pestana-jobs.md` sale igual, con un test.
- **LinkedIn avisó que retira la búsqueda clásica** desde septiembre. Si los links
  dejan de filtrar, hay que rehacer los filtros en `vacantia/ui/linkedin_urls.py`.
- **El anotador:** + y − anotan, *Confirmar* suma al contador grande. Un
  *Confirmar* todavía no se puede deshacer.

## 2.21 y 2.25. La pestaña Filtradas

Ahí cae lo que el filtro saca solo, con el motivo, para auditarlo:

- *Bien descartada*
- *Mal descartada*: vuelve a Sin marcar.
- *Bien, motivo equivocado*

Muestra sólo las de 50 puntos para arriba; la meta son 40 revisadas. Vive en
`revision_filtro` y no toca `aplicado`. Se muestran **todos** los motivos, con
el idioma primero, porque el lugar lo deduce el modelo y ahí aparecen los errores.

## 2.22. Indeed y Get on Board

- **Get on Board:** API pública, sin token y sin TinyFish. Sigue trayendo aunque
  falte la clave de TinyFish. Se pide `country_code=AR`, y "Remote" en
  `countries` se lee como modalidad, no como país. Desde el 19/11 se lee por
  categoría (2.49).
- **Indeed:** desde el 19/11 se lee con JobSpy, por la API de la app, y ya no
  con TinyFish (2.49). Se sigue guardando `viewjob?jk=<id>`.

## 2.23, 2.27 y 2.35 a 2.38. Métricas

- **Contador de postulaciones** con reparto por semana. Las semanas en cero se
  dibujan en gris.
- **Gráficos hechos con HTML y tokens**, sin librería. Con menos de tres filas va
  una tabla en lugar de un gráfico.
- **Qué te están pidiendo** sale del campo `stack` que el modelo ya devolvía. No
  hay ninguna lista de tecnologías en el código, a propósito: tiene que servir
  para cualquier oficio.
- **Cada bloque dice contra cuántas se mide**, con el número grande de la
  cabecera (`_cabecera` en `render.py`). Si agregás un bloque, pasale el total.
- **Las tarjetas de arriba suman el total**, y la cuenta escrita aparece sólo si cierra.
- **Lo escrito a mano** se agrupa sin mirar mayúsculas ni tildes, y no se
  interpreta más que eso: cuando una idea se repite, va al desplegable.
- **Verde es lo que ya hiciste, nunca decoración.** El rojo, sólo para lo que
  está mal de verdad.

## 2.26 y 2.39. CSS, htmx y el panel de búsqueda

- El CSS está en `vacantia/ui/css/` y el JS en `static/app.js`. Se leen del disco
  en cada pedido, así que alcanza con F5.
- htmx está vendorizado; nunca desde un CDN.
- **Un solo pedido cada 2 segundos** actualiza el cartel del pie, el panel
  *Buscando trabajo* y el aviso de ofertas nuevas (`hx-swap-oob`). Si hace falta
  un cuarto lugar, se cuelga de ahí y no de otro reloj.
- **La barra no inventa porcentajes:** sólo se llena durante el puntaje, que es
  cuando se sabe el total. Las etapas salen de `corrida.ETAPAS`.
- **Nunca recarga sola:** avisa, y decidís vos.

## 2.28. Por qué no hay más ofertas

Al 12/9/2026, 163 de 220 ofertas se caían por inglés, el 74%. Es el único filtro
que mueve la aguja: aceptar avisos en inglés deja 90 para revisar hoy, 12 de
ellas con 60 o más. La casilla es *Aceptar avisos en inglés* en Mi perfil.
**No la toqué**: es tu decisión.

**Apify no:** pide tarjeta para cada persona, cobra por resultado y no resuelve
lo del inglés. Vale la pena mirarlo recién si prendés el inglés y te quedás
igual sin ofertas.

## 2.29. Más de un CV

Cada CV tiene sus puestos, que se suman en todas las fuentes, y sus habilidades,
que no se buscan (2.48). La oferta se puntúa contra el CV que mejor encaja y la tarjeta dice cuál mandar.
Decisiones que no conviene deshacer:

- **Con un solo CV, el prompt sale byte a byte igual.** Hay un test.
- **Un CV vacío no cuenta.** Se guarda el **id**, no el nombre.
- **Enter guarda y no agrega un CV:** hay un botón de guardar invisible al
  principio del formulario. No sacarlo.
- **Con varios CV, el "qué hago" del perfil no va al modelo:** sesgaba el puntaje
  hacia uno de los CV.

Pendiente natural: registrar qué CV mandaste al marcar *Apliqué*.

## 2.30. Empresas por perfil

Cada perfil tiene su `companies-<nombre>.json`. Pasó que guardar el perfil de
papá pisó tu lista. Si dos perfiles quedan apuntando al mismo archivo, el primero
que guarda pasa a tener el suyo.

## 2.32. Preparar la copia de un familiar

Cada familiar recibe una **copia independiente**: su carpeta, su repo de GitHub y
su propio Claude Code. No queda ningún vínculo con tu repo.

**Qué hay en `scripts/copia-familiar/`** (en tu repo son archivos sueltos):

- **`CLAUDE.md`:** reemplaza al tuyo. Le dice a su Claude que habla con alguien
  que no programa y cómo guardar los cambios.
- **`settings.json`:** va a `.claude/settings.json` y bloquea de verdad:
  - borrar historial (`push --force`, `reset --hard`, `clean`, `branch -D`);
  - leer o editar `.env`;
  - editar `state/` y `scripts/`.

  Subir y unir cambios pide confirmación.
- **`preparar.ps1`:** deja todo listo. Se niega si la carpeta sigue conectada a tu repo.

`.claude/rules/` viaja con la copia: lo usan los dos Claude.

**Su Claude** trabaja cada pedido en una rama `cambio/xxx`, corre los tests y
recién ahí une a `main` y sube. Para deshacer usa `git revert`.

**Paso a paso.** La máquina, una vez:

1. Cuenta de GitHub para la persona.
2. `winget install Git.Git GitHub.cli`.
3. Claude Code, con **su** cuenta.
4. Bajar el programa: el ZIP, o clonar y **borrar `.git`**. Antes subí lo último tuyo.
5. `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\copia-familiar\preparar.ps1`,
   y después `gh auth login --web` y `gh repo create vacantia --private --source . --push`.
6. En `profiles\`, borrá los que no son de ella y renombrá el que sirva de base
   (`isaias.json` → `hermana.json`, con `"name"` y `cv_path` cambiados). **Antes
   de instalar**, porque se programa una tarea por cada perfil.
7. `instalar.bat`.
8. `abrir.bat` → Configuración → *Claves*: Gemini, TinyFish y Telegram, **los de ella**.

Después, desde Mi perfil:

- palabras clave y *Puestos que NO quiero*;
- sus CV;
- dónde, modalidad e inglés;
- empresas y reclutadores;
- *Qué NO me sirve*, que es lo que más afina el puntaje;
- su chat de Telegram.

Para usarlo, abre una terminal en la carpeta, escribe `claude` y pide en
castellano. Si algo salió mal: *"volvé atrás el último cambio"*.

Falta probar las barandas en la primera copia de verdad: que `push --force`
quede bloqueado y que `push` pida confirmación.

## 2.33 y 2.34. Mi perfil y Configuración

- **Mi perfil** es lo que tocás seguido: CV, palabras, dónde, inglés, empresas,
  reclutadores y datos personales.
- **Configuración** es lo de una vez: claves, Telegram, fuentes, puntajes,
  antigüedad y crear o borrar un perfil.
- **Cada pantalla guarda sólo sus campos** (`aplicar_datos` y
  `aplicar_configuracion`). Un tilde sin marcar no viaja en el formulario: si Mi
  perfil leyera las fuentes, las apagaría todas. Los tests de
  `tests/test_configuracion.py` lo cuidan.
- **Borrar un perfil** se lleva su JSON, sus CV, sus empresas, `state/<nombre>/`
  y la tarea programada. Lo compartido con otro perfil no se borra.
- `DESIGN.md` quedó desactualizado en dos cosas que no toqué: no nombra
  Configuración, y dice que borrar es un modal (se hizo en el lugar).

## 2.40. Computrabajo repetía ofertas

El 17/9/2026 el mismo aviso entró ocho veces. Kaizen republica con URLs
distintas, y Computrabajo había cambiado la página: el lector dejó de leer
título y empresa, y sin empresa no corre el control por empresa + título.

Se arregló en `extraer_computrabajo`:

- el título es el primer `#` de nivel 1;
- la empresa se corta en el **último** " - ".

El historial se reparó; el respaldo quedó en
`state/isaias/*.bak-computrabajo-20260917-120122.json`.

## 2.41. Aprende de lo que marcás

- **Ejemplos en el prompt:** cada lote lleva tus últimos 12 descartes y 6
  aplicadas (`vacantia/aprendizaje.py`), unos 1.200 tokens. No entran inglés,
  presencial ni caso especial.
- **`is_job_offer`:** si el modelo dice que no es oferta, el **código** fuerza el
  0. Con el prompt solo, un posteo con 70 llegaba igual a Telegram.
- **Tecnologías que NO uso,** en Mi perfil: `.NET`, `Java` y `C#`. La "o" la
  juzga el modelo ("Java o .NET" se va; "Python o Java" entra). El filtro
  confirma al leer que la tecnología siga en tu lista, así que sacar una
  devuelve esas ofertas sin re-puntuar.
- **Todo lo que saca va a Filtradas**, donde se puede marcar *Mal descartada*.

## 2.43. Nivel mínimo, Archivar a la vista y el Enter que aplicaba

El 25/9/2026 dijiste que seguía sin aprender. Mirando tu historial:

- **Archivar, a la vista en cada tarjeta**, en fantasma: es "no le doy bola",
  por la razón que sea. Vivía escondido en el menú de tres puntos como *Ya no
  está*, que además lo achicaba a los avisos vencidos. Es la única excepción a
  la regla de dos controles.
- **"semi senior no acepto" quedó guardada como APLICADA.** Enter en el campo del
  motivo manda el formulario con el primer botón, que es *Apliqué*: el sistema
  aprendió que te gustan las Semi Senior. Ahora Enter descarta (`app.js`), y el
  servidor trata "Apliqué + motivo escrito" como descarte. Esa oferta ya se
  corrigió en tu historial (copia en `state/isaias/job_history.bak-aplicada-por-enter-20260925.json`).
- **Nivel mínimo del puesto**, en Mi perfil (`filters.seniority_minima`). El
  tuyo quedó en Senior. Mira primero el título ("SSR", "Semi Senior", "Jr",
  "Practicante"; "SSr/Sr" entra porque te acepta) y, si no dice nada, el nivel
  que devuelve el modelo. Se calcula al leer, así que ya sacó las Semi Senior
  que tenías sin marcar. Va a *Filtradas* como "Es para un nivel menor".
- **Los ejemplos del prompt llevan el stack.** "Pide tecnologías con las que no
  trabajo" no decía cuáles; ahora el modelo ve, por ejemplo, `PHP, Laravel`.
- **Tecnologías: la lista manda.** Sólo filtra lo que está en *Tecnologías que
  NO uso*. Hoy tenés `.NET, Java, C#`; si te llegan PHP, Scala o Go, sumalas ahí.

## 2.44. El error 10053 de la ventana no era un error

El 6/10/2026 la ventana de `abrir.bat` mostró dos tracebacks con
`ConnectionAbortedError: [WinError 10053]` mientras corría una búsqueda.

- **Qué era:** el cartel de la corrida pregunta cada 2 segundos cómo va. Si
  cambiás de pestaña o apretás F5 justo en ese momento, el navegador corta el
  pedido a la mitad, y Windows avisa con ese error al querer contestarle.
- **Por qué parecía grave:** el servidor lo trataba como un bug. Lo anotaba como
  ERROR y además intentaba mandar la página de "Algo falló" por la misma
  conexión cortada, que volvía a fallar. De ahí el segundo traceback.
- **Ahora:** un corte del navegador se suelta en silencio (`Handler.handle` en
  `vacantia/ui/server.py`). Los bugs de verdad siguen saliendo como antes.

## 2.45. El embudo por fuente, Backend Python y el remoto para LATAM

El 16/10/2026 se midió qué rendía cada fuente cruzando `vacantia.log` con el
historial (153 corridas, del 7/9 al 16/10). Salieron tres cosas:

- **`excluir_titulos` tenía "Backend"** y tiraba antes del modelo justo lo que
  buscás: "Senior Backend Python + IA Developer – Remoto", "Sr Python Backend
  Developer". Se sacó. Se agregó **"Lead"**, que cubre Tech Lead y Team Lead.
- **El filtro de país tiraba remotos de afuera que contratan desde LATAM**: un
  "LLM Engineer" y un "Full Stack AI Engineer" de EE. UU., con 88 y 90 puntos.
  Ahora tu perfil tiene `filters.location.remoto_abierto_a_latam: true`: entran
  si el aviso dice LATAM, Latin America, worldwide o "desde cualquier país".
  El remoto *para* Colombia sigue afuera.
- **No había registro por fuente.** Con `"registro_embudo": true` (sólo en tu
  perfil) cada corrida deja `state/isaias/embudo.jsonl`, las descartadas con su
  motivo en `descartadas.jsonl`, y `notificada_en` en el historial. Ver *El
  embudo de cada corrida* en el README.

## 2.46. Indeed: todos los avisos eran el mismo

- **El problema:** `Job.key` cortaba la URL en el `?` para sacar el tracking, y
  en Indeed el id del aviso va ahí (`viewjob?jk=…`). Para el dedupe todos los
  avisos de Indeed eran `https://ar.indeed.com/viewjob`: en cinco semanas entró
  **uno solo** al historial, y el resto se descartó como "ya visto".
- **Ahora:** la clave sale de `models.clave_de_url`, que conserva `jk` y `vjk`
  (Indeed) y `gh_jid` (Greenhouse embebido), y sigue sacando `utm`, `ref` y el
  resto. Las demás fuentes llevan el id en la ruta; se revisaron todas.
- **Migración:** `seen_jobs.json` lleva `version_claves: 2`. Al pasar, se suma la
  clave nueva de todo lo que está en el historial, así lo ya visto no vuelve como
  nuevo. Se corrió a mano el 16/10/2026 sobre `isaias` y `juan_carlos`, con copia
  en `seen_jobs.bak-claves-20261016.json`. Los avisos de Indeed que se perdieron
  como "ya vistos" nunca se guardaron: ésos van a entrar una vez.
- **`excluir_titulos` también después del modelo**, sobre el título que él
  extrae. Antes se miraba sólo el de la fuente, y un post que el modelo tituló
  "TECH LEAD | SENIOR FULL STACK e AI ENGINEER" llegó a puntuarse con "Lead" en
  la lista.

## 2.47. La pantalla sólo muestra de 50 para arriba

- **El pedido:** "menores a 50 no quiero ver nada". En `isaias` eran 1044 de las
  1179 sin marcar, y tapaban las 135 que servían.
- **Ahora:** `PUNTAJE_PARA_MOSTRAR = 50` en `ui/data.py`. Se corta en
  `_por_estado` y en `contar_ofertas`, así la lista y los números dicen lo mismo,
  en todas las pestañas **menos Apliqué** (hay 3 aplicadas debajo de 50, y para
  el seguimiento tienen que seguir ahí).
- **No se borra nada:** el historial queda igual, para el dedupe y los gráficos.
  Sin puntaje se muestra, porque no se sabe si está debajo.
- **Tests:** cuatro que usaban ofertas de 0, 10 o 45 para probar el orden pasaron
  a puntajes de 50 para arriba, sin cambiar lo que protegen. Uno nuevo:
  `test_menos_de_50_no_se_ve_salvo_en_aplique`.

## 2.48. Búsquedas que no se repiten, puestos aparte de habilidades e inglés antes del modelo

Salió de la investigación del 19/11/2026 (unas 1.000 ofertas de LinkedIn de los
últimos 30 días). Seis cambios:

- **A. La rotación es por corrida, no por día.** Las tres corridas del día
  (12:00, 16:30, 23:59) hacían las mismas búsquedas: el 18/11, dos seguidas de
  LinkedIn trajeron unas 50 ofertas cada una y 31 ya estaban vistas. Ahora cada
  fuente sigue desde donde quedó, con la posición en
  `state/<perfil>/rotacion.json` (`vacantia/rotacion.py`). La guarda el motor
  al final, así que un `--dry-run` o una corrida que se cae no la mueven.
  **No se subió** `max_searches` de LinkedIn: sigue en 3.
- **C. Puestos y habilidades, separados.** En Mi perfil hay *Puestos a buscar* y
  *Habilidades*, en el perfil y en cada CV. Los puestos se buscan. Las habilidades
  van al modelo (`- Skills:` en el prompt), al triaje y a "Que además diga" de
  Jobs, que al entrar viene con ellas. Los campos conservan su nombre en el JSON
  (`keywords` y `palabras_clave` son los puestos; `habilidades` es nuevo), así que
  las copias de la familia siguen andando. "Full Stack" y "Full-stack" cuentan
  como una búsqueda. **Migración:** en tu perfil, Python, FastAPI, React y Next.js
  pasaron a habilidades, arriba y en el CV Full Stack. Los 14 puestos de tu CV
  principal no se tocaron. `juan_carlos` no tenía nada para mover.
  **CV nuevo (19/11):** `resume/isaias.md` y `resume/isaias-cv-2.md` se rearmaron
  desde "Isaias Mella - CV - Full Stack.pdf" (eran iguales entre sí y lo siguen
  siendo). Las habilidades salen de su stack: las comunes arriba (Python, FastAPI,
  TypeScript, PostgreSQL...), las de IA en el CV principal (LLM, RAG, LangChain,
  Whisper, tool calling...) y las de front en el Full Stack (React, Next.js, React
  Native...): 25 en total. Al modelo y al triaje les llegan todas; "Que además
  diga" precarga sólo las primeras 6 (`MAX_HABILIDADES_PRECARGADAS`), porque un OR
  de 25 tecnologías ya no filtra. El inglés B1 del PDF no se pasó al `.md`, igual
  que antes: el perfil dice que no querés puestos con inglés.
- **G. Inglés antes del modelo.** El 19/11, 9 de 11 ofertas de LinkedIn se
  cayeron por idioma *después* de pagar la puntuación. Ahora, con el inglés
  desactivado, `filters.pide_ingles_sin_puntuar` descarta antes lo que pide
  inglés por escrito o está escrito en inglés. Lee el **texto entero**: las
  fuentes cortan en 3.000 caracteres, y por eso se te pasó una que lo pedía al
  final. El texto entero vive en `Job.descripcion_completa`, que **no** se guarda
  en el historial. Contra tu historial, coincidió con el modelo en 729 de 755
  avisos en inglés, le erró a 1 de unos 850 en castellano (un "Cloud Platform
  Engineer Lead", que igual sale por "Lead") y no habría tirado ninguna de las
  que aplicaste. El modelo sigue como segunda capa. En el embudo estas
  descartadas cuentan como "antes del LLM" y no como "idioma".
- **H. Get on Board** ya no busca "Machine Learning" ni "Data", que estaban en
  tus puestos excluidos: tiraba 15 avisos por corrida.
- **D. Sugeridas en LinkedIn URLs.** Hasta 5 por pestaña, armadas con tus
  puestos, con *Abrir* y *Guardar*. En Publicaciones van los títulos en
  castellano primero y "Forward Deployed" acortado, todas de 110 letras para
  abajo y con un NOT por término. En Jobs van las últimas 2 horas, remotos y con
  menos de 10 candidatos, sin repetir los títulos en castellano. El tope de 110
  en Jobs no se midió: se usa por precaución.
- **F. `google_posts` apagado en tu perfil** (779 ofertas, 0 postulaciones). El
  interruptor ya existía: es el tilde en Configuración. En 125 corridas desde el
  16/10, google_posts puso 2,7 ofertas por corrida en el modelo. Con lotes de 6
  eso son **0,43 llamadas menos por corrida en promedio, hasta 2**: 54 de las
  189 que se hicieron, un 29%. Se ahorran además las 4 búsquedas de TinyFish
  por corrida.

**Pendiente:** los `search_terms` propios de las fuentes siguen sumando términos
redundantes según la investigación: LinkedIn "GenAI Engineer" y "AI Agent
Engineer", Indeed "GenAI Engineer" y "Software Engineer Python", Get on Board
"Python" y "LLM". Ocupan lugares de la rotación. No los toqué porque no estaban
en el pedido. (Los de Get on Board ya no se usan: ahora lee por categoría, 2.49.)

## 2.49. Indeed y Get on Board, arreglados

Salió de mirar el embudo de la semana del 12 al 19/11. Las dos fuentes andaban
mal por cómo las leíamos, no por el portal.

- **Indeed, con JobSpy.** Con TinyFish, Cloudflare no dejaba leer la página de
  cada aviso: 161 avisos distintos con "Indeed no dejó leer el aviso", y en
  noviembre corridas de 2 legibles de 25. Ahora usa JobSpy, el mismo paquete de
  LinkedIn, que lee la API de la app de Indeed. Probado el 19/11:
  - Con "Python": 30 de 30 avisos completos en 0,8 s.
  - Con tu perfil: 26 avisos con empresa, descripción y fecha en 9,6 s.
  - **No gasta TinyFish** y trae la fecha, que antes no venía.
  - La dirección guardada es la misma, así que tu historial sigue sirviendo.
  - En tu perfil `results_wanted` pasó de 25 a 50: hasta 100 sigue siendo un solo
    pedido. Se sacó `sort`, que era de la versión vieja.
  - **"Sólo remoto" no se le pide:** JobSpy no lo deja combinar con la ventana
    de días, así que lo filtra `filters.py`, como en el resto de las fuentes.
- **Get on Board, por categoría.** Para la Argentina hay **101 ofertas activas
  en todo el portal**, y 43 entre programación e IA. Las recorríamos con 17
  términos de a 3 por corrida:
  - Llegábamos hasta 7 días tarde.
  - De las 89 tiradas por viejas, **42 nunca las habíamos visto**.

  Ahora tu perfil tiene `"categorias": ["programming", "machine-learning-ai"]`:
  son 2 pedidos por corrida, que traen todo. Sin `categorias`, la fuente busca
  por términos como antes, que es lo que sirve para un perfil que no es de
  tecnología. La empresa viene en el mismo pedido (`expand=["company"]`), así
  que se ahorra una llamada por empresa.
- **Lo que ya viste no se cuenta otra vez como descarte.** Get on Board tira por
  vieja, en cada corrida, una oferta que vimos fresca hace dos semanas: 47 de
  las 89. Ahora el motor no anota el descarte de una fuente si esa dirección ya
  está en `seen_jobs.json`.

**Para que decidas:** en la prueba del 19/11, de las 43 de Get on Board sólo 2
eran de esta semana, y **23 tienen más de 7 días y nunca las viste**. Siguen
abiertas. Si las querés ver una vez, poné `"max_age_days": 30` en el bloque de
`getonbrd`: entran a puntuar unas 23, que son unas 4 llamadas al modelo.

## 2.42. Jev: probado y descartado por ahora

El 22/9/2026 se probó **Jev** (TypeSafe AI), un modelo que no escribe texto:
contesta preguntas cerradas (sí o no, elegir una opción, un puntaje) con qué tan
seguro está. Se llamó por el AI Gateway de Vercel (`typesafe-ai/jev`), que es
gratis hasta el 25/9, con `AI_GATEWAY_API_KEY` en `.env`.

**Cómo se probó:** a 110 ofertas de tu historial con marca tuya se les hicieron
las mismas preguntas cerradas que hoy le hace el prompt a Gemini. Se comparó
contra tu marca y contra lo que Gemini había guardado. No se tocó el motor, y el
script ya se borró.

| Pregunta | Gemini | Jev |
|---|---|---|
| Pide inglés (52 descartes tuyos) | 41 (79%) | 46 (88%) con corte en 0.5 |
| Pide inglés, pero aplicaste igual (12) | 1 error | 2 con corte en 0.5; **0 con corte en 0.8** |
| No es oferta (17) | 10 | 9 |
| Tecnologías que no usás (11) | — | 6, sin errores en las que aplicaste |
| Encaje: separa aplicadas de "no era mi puesto" | 0.93 | 0.90 |

- **Decide igual que Gemini, no mejor.** La ventaja en inglés está inflada: lo
  que Gemini ya filtraba nunca te llegó, así que esos descartes son justo los
  que se le escaparon.
- **La confianza sí sirve.** Por encima de 0.8 no se equivocó nunca con lo que
  aplicaste; los errores estuvieron entre 0.5 y 0.8.
- **Los puntajes salen más bajos** (48 contra 73 en lo que aplicaste). Si se
  usara, habría que recalibrar `min_score`.
- **No escribe texto:** motivo, stack y ciudad los seguiría haciendo Gemini.
- **Es rápido y barato:** 0.5 s por oferta y US$ 0.013 las 110. Pero Gemini ya es
  gratis y el cuello de botella no es el modelo.
- **Es inestable:** con 4 pedidos en paralelo, 14 de 83 volvieron con "alta
  demanda del proveedor".
- **Algunas marcas tuyas parecen discutibles:** 3 de tus "no es oferta" parecen
  ofertas reales ("Estamos contratando!!! buscamos desarrolladores", Sawy). Jev
  les dio 0.97.

**Si algún día se retoma:** usar Jev sólo como segunda opinión para "pide
inglés" y "tecnologías", y mandar a la pantalla lo que caiga entre 0.5 y 0.8 en
vez de descartarlo. Gemini seguiría con todo lo de texto. El endpoint es
`POST https://ai-gateway.vercel.sh/typesafe/v1/systemone`, con `state` y
`questions` (tipos `noul`, `choice` y `score`).

---

# 3. DESCARTADO A PROPÓSITO

- **CV en PDF:** salía feo y se borró. El CV es Markdown en `resume/`. No volver
  a construirlo sin acordarse de esto.
- **Recolección compartida o en un servidor:** cada casa aporta su propia IP
  residencial, y eso es lo que evita que LinkedIn bloquee. Una IP de datacenter
  es lo primero que filtra.
- **Apify** (2.28) y **Jev** (2.42), por ahora.
- **Que un país deducido no pueda filtrar solo:** se midió, y las 4 ofertas que
  habría devuelto estaban bien deducidas (España y Chile).

# 4. IDEAS, NO PENDIENTES

- **Ofertas por mail** además de Telegram, para papá: es un archivo nuevo en
  `vacantia/notifiers/`, sin tocar el motor.
- **Reescribir el `README.md`** como guía de instalación para cada persona.
- **Apuntar al mercado de afuera** cuando el inglés deje de ser un problema. Se
  toca `filters.language`, la ubicación y las palabras clave (2.28).

# 5. LOS ARCHIVOS

| Archivo | Para qué | Cuándo |
|---|---|---|
| `instalar.bat` | Instala y programa las búsquedas | Una vez, y de nuevo al agregar un perfil o mover la carpeta |
| `abrir.bat` | La pantalla | Todos los días |
| `desinstalar.bat` | Deja de buscar y borra el programa; pregunta aparte por los datos | Cuando consiguieron trabajo |

`vacantia.log` es lo primero que hay que mirar cuando algo falla. `.env` tiene
las claves y no se sube a git. La arquitectura del código está en
`.claude/rules/proyecto.md` y en el `README.md`.
