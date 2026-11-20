"""El motor: fuentes → Job → quitar duplicados → scoring → filtro → notificación.

El motor no sabe nada de TinyFish ni de Telegram: sólo habla con las interfaces
Source y Notifier. Cambiar de fuente o de canal no toca este archivo.
"""

import time
from dataclasses import dataclass, field

from vacantia.aprendizaje import decisiones_para_el_prompt
from vacantia.config import load_resumes
from vacantia.embudo import ETAPA_DEL_FILTRO, Embudo, esta_prendido
from vacantia.filters import (
    apply_filters,
    descartar_antes_de_puntuar,
    drop_filled,
    english_pain_lines,
)
from vacantia.log import get_logger
from vacantia.models import Job
from vacantia.notifiers import build_notifiers
from vacantia.notifiers.base import Notifier
from vacantia.notifiers.console import ConsoleNotifier
from vacantia import rotacion
from vacantia.scoring import filter_by_min_score, score_jobs, triage
from vacantia.sources import build_sources
from vacantia.sources.base import Source
from vacantia.sources.dummy import DummySource
from vacantia.state import State

logger = get_logger()


def _cap(msg: str) -> str:
    """Mayúscula inicial sin tocar el resto (str.capitalize baja NOMBRES_ASI)."""
    return msg[:1].upper() + msg[1:]


@dataclass
class RunResult:
    fetched: int = 0
    new: int = 0
    filled: int = 0
    scored: int = 0
    filtered_out: int = 0
    english_dropped: int = 0
    deferred: int = 0
    matched: int = 0
    sources_used: list[str] = field(default_factory=list)
    notifiers_used: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)
    seconds: float = 0.0


def _usable_sources(profile: dict, result: RunResult) -> list[Source]:
    """Fuentes activas y disponibles. Si no queda ninguna, cae a DummySource."""
    usable: list[Source] = []
    for source in build_sources(profile):
        ok, why = source.is_available()
        if ok:
            usable.append(source)
        else:
            msg = f"fuente '{source.name}' no disponible ({why})"
            logger.warning(_cap(msg))
            result.skipped.append(msg)

    if not usable:
        logger.warning("Ninguna fuente disponible — uso DummySource para probar el pipeline.")
        result.skipped.append("sin fuentes disponibles → fallback a DummySource")
        usable.append(DummySource({"type": "dummy"}, profile))
    return usable


def _usable_notifiers(profile: dict, result: RunResult) -> list[Notifier]:
    """Notificadores activos y disponibles. Si no queda ninguno, imprime por consola."""
    usable: list[Notifier] = []
    for notifier in build_notifiers(profile):
        ok, why = notifier.is_available()
        if ok:
            usable.append(notifier)
        else:
            msg = f"notificador '{notifier.name}' no disponible ({why})"
            logger.warning(_cap(msg))
            result.skipped.append(msg)

    if not usable:
        logger.warning("Ningún notificador disponible — imprimo por consola.")
        result.skipped.append("sin notificadores disponibles → fallback a consola")
        usable.append(ConsoleNotifier({"type": "console"}, profile))
    return usable


def collect(sources: list[Source], result: RunResult) -> list[Job]:
    """Corre todas las fuentes. Una fuente que explota no tumba la corrida."""
    jobs: list[Job] = []
    for source in sources:
        logger.info(f"--- Fuente: {source.name} ---")
        try:
            found = source.fetch()
        except Exception as e:
            msg = f"fuente '{source.name}' falló: {e}"
            logger.error(_cap(msg))
            result.skipped.append(msg)
            continue
        for job in found:
            job.source = job.source or source.name
        result.sources_used.append(source.name)
        jobs.extend(found)
        logger.info(f"--- {source.name}: {len(found)} oferta(s) ---")
    return jobs


def _embudo_de_fuentes(embudo: Embudo, sources: list[Source], jobs: list[Job],
                       result: RunResult) -> None:
    """Lo que trajo cada fuente y lo que tiró ella misma antes de devolverlo."""
    for source in sources:
        for d in getattr(source, "descartes", []):
            embudo.descartar(source.name, "descartada_en_fuente", d["motivo"],
                             d["url"], d.get("titulo", ""), d.get("empresa", ""))
    embudo.contar_jobs("trajo", jobs)
    embudo.fallas = list(result.skipped)


def empty_run_notes(result: RunResult, fstats, min_score: int) -> list[str]:
    """Qué pasó en una corrida que no tiene nada para avisar.

    Es lo que le da sentido a `notify_when_empty`: sin este detalle, "hoy no
    salió nada" y "hace tres días que la fuente está caída" son el mismo
    silencio, y el segundo caso no se descubre hasta que alguien lo busca.
    """
    fuentes = ", ".join(dict.fromkeys(result.sources_used)) or "ninguna"
    lineas = [f"Sin coincidencias. Revisé {result.fetched} oferta(s) de: {fuentes}."]

    partes = []
    ya_vistas = result.fetched - result.new - result.filled
    if ya_vistas > 0:
        partes.append(f"{ya_vistas} ya vistas o repetidas")
    if result.filled:
        partes.append(f"{result.filled} ya cubiertas")
    if result.deferred:
        partes.append(f"{result.deferred} diferidas para la próxima corrida")
    if result.scored:
        partes.append(f"{result.scored} puntuadas")
    if partes:
        lineas.append(" · ".join(partes) + ".")

    if fstats.dropped:
        porque = ", ".join(f"{n} por {etq}" for etq, n in fstats.by_reason.most_common())
        lineas.append(f"{fstats.dropped} descartadas por los filtros ({porque}).")
    if result.scored and not result.matched:
        lineas.append(f"Ninguna llegó al min_score de {min_score}.")

    if result.skipped:
        lineas.extend(f"⚠ {nota}" for nota in result.skipped)
    else:
        lineas.append("Ningún error en la corrida: el silencio es del mercado, no del sistema.")
    return lineas


def run(profile: dict, dry_run: bool = False) -> RunResult:
    t0 = time.time()
    result = RunResult()
    name = profile.get("name", "?")
    min_score = int(profile.get("min_score", 60))
    top_n = profile.get("top_n")

    logger.info(f"=== vacantia — perfil '{name}' ===")
    logger.info(f"min_score={min_score} | top_n={top_n or 'todos'}")

    # Todos los CV del perfil: se puntúa contra el que mejor encaja con cada oferta.
    cvs = load_resumes(profile)
    state = State(name)
    # Se cuenta siempre, que es gratis; se guarda sólo si el perfil lo pide.
    embudo = Embudo(name, dry_run)

    # 1) fuentes → Job
    sources = _usable_sources(profile, result)
    jobs = collect(sources, result)
    result.fetched = len(jobs)
    logger.info(f"Total recolectado: {len(jobs)} oferta(s)")
    _embudo_de_fuentes(embudo, sources, jobs, result)

    # 2) quitar duplicados
    new_jobs = state.filter_new(jobs)
    for job, etapa, motivo in state.ultimos_descartes:
        # "Ya vista" se cuenta y no se anota: es la misma oferta de una corrida
        # anterior, que ya quedó registrada cuando se la vio por primera vez.
        if etapa == "ya_vista":
            embudo.contar(job.source, etapa)
        else:
            embudo.descartar_job(etapa, job, motivo)

    # 2 bis) vacantes ya cubiertas. Va antes del scoring: puntuar una búsqueda
    #        cerrada es gastar una llamada al LLM para descartarla después.
    new_jobs, cubiertas = drop_filled(new_jobs)
    result.filled = len(cubiertas)
    result.new = len(new_jobs)
    for job, marca in cubiertas:
        embudo.descartar_job("cubierta", job, f"vacante ya cubierta ({marca})")

    # 2 ter) lo que ya se sabe que no sirve, antes de pagar por puntuarlo. El
    #        título que nombra un puesto que la persona no hace, y la ubicación
    #        cuando la fuente ya la trajo. Va antes del triaje para que el tope
    #        de la corrida se gaste en candidatas de verdad.
    new_jobs, descartadas = descartar_antes_de_puntuar(new_jobs, profile)
    if descartadas:
        logger.info(f"Descartadas {len(descartadas)} sin gastar una llamada al modelo")
        for job, motivo in descartadas:
            logger.debug(f"    sin puntuar: {job.display_title[:60]} — {motivo}")
            embudo.descartar_job("antes_del_llm", job, motivo)
    result.new = len(new_jobs)

    # 3) triaje: si entraron muchas de golpe (cargaste empresas nuevas, cambiaste
    #    los search_terms), puntúa las más prometedoras y difiere el resto.
    to_score, deferred = triage(new_jobs, cvs, profile)
    result.deferred = len(deferred)
    embudo.contar_jobs("diferida", deferred)

    # 4) scoring contra el CV, con lo que la persona ya marcó como ejemplo.
    #    Sin esto el sistema no aprendía: los descartes se guardaban y el modelo
    #    nunca los veía (ver `aprendizaje`).
    decisiones = decisiones_para_el_prompt(state.load_history()) if to_score else ""
    scored = score_jobs(to_score, cvs, profile, decisiones) if to_score else []
    result.scored = len(scored)
    embudo.contar_jobs("puntuada", scored)

    # 5) filtros de ubicación / modalidad / idioma
    eligible, fstats = apply_filters(scored, profile)
    result.filtered_out = fstats.dropped
    result.english_dropped = fstats.english_count
    for job, why, etiqueta in fstats.descartadas:
        embudo.descartar_job(ETAPA_DEL_FILTRO.get(etiqueta, etiqueta), job, why)

    # Informe opcional: cuántas se cayeron por idioma y cuánto valía la mejor.
    # Va en la notificación a pedido del perfil — ver report.english_pain.
    notes: list[str] = []
    if (profile.get("report") or {}).get("english_pain", False):
        notes = english_pain_lines(fstats)

    # 6) filtro por min_score
    matches = filter_by_min_score(eligible, min_score, top_n)
    result.matched = len(matches)
    result.jobs = matches
    logger.info(f"{len(matches)} de {len(eligible)} pasaron el min_score de {min_score}")
    superan = filter_by_min_score(eligible, min_score)
    for job in eligible:
        if job not in superan:
            embudo.descartar_job("bajo_umbral", job,
                                 f"puntaje {job.score or 0}, debajo del mínimo de {min_score}"
                                 if (job.score or 0) < min_score
                                 else "el modelo dijo que no vale la pena postularse")
    embudo.contar_jobs("supera_umbral", superan)
    # Pasan el umbral pero no entran en las `top_n` del aviso: quedan en la
    # pantalla y no llegan al Telegram. Se cuentan porque es lo que se pierde
    # de vista, no porque se descarten.
    embudo.contar_jobs("fuera_del_top", [j for j in superan if j not in matches])

    # Si no hay nada que avisar, el aviso lo explica (ver notify_when_empty).
    if not matches:
        notes = notes + empty_run_notes(result, fstats, min_score)

    # 7) notificación
    if dry_run:
        logger.info("--dry-run: no notifico ni guardo estado.")
        ConsoleNotifier({"type": "console"}, profile).send(matches, notes)
        result.seconds = time.time() - t0
        embudo.contar_jobs("sin_avisar", matches)
        if esta_prendido(profile):
            embudo.guardar(state.dir, result.seconds)
        return result

    notify_empty = bool(profile.get("notify_when_empty", False))
    if matches or notify_empty:
        for notifier in _usable_notifiers(profile, result):
            try:
                if notifier.send(matches, notes):
                    result.notifiers_used.append(notifier.name)
            except Exception as e:
                msg = f"notificador '{notifier.name}' falló: {e}"
                logger.error(_cap(msg))
                result.skipped.append(msg)
    else:
        logger.info("Sin coincidencias — no notifico (poné notify_when_empty=true para avisar igual).")

    # 8) estado: recién acá marcamos como vistas, para que un fallo previo
    #    no haga perder ofertas que nunca llegaron a avisarse.
    # Sólo lo que efectivamente se puntuó: las diferidas por el triaje tienen
    # que volver a aparecer en la próxima corrida.
    # Las ya cubiertas también: no cuestan nada, pero vuelven en cada corrida
    # mientras el buscador las tenga indexadas.
    state.mark_seen(to_score + [j for j, _ in cubiertas])
    state.save(scored)
    # La próxima corrida sigue la rotación de términos desde donde quedó ésta.
    # Va acá y no en cada fuente para que un --dry-run no la mueva.
    rotacion.guardar(name, {s.name: s.siguiente_en_rotacion for s in sources
                            if s.siguiente_en_rotacion is not None},
                     root=state.dir.parent)

    # 9) embudo. "Avisada" es lo que salió por un canal que la persona lee: la
    #    consola sola no cuenta, porque devuelve True aunque Telegram haya fallado.
    avisadas = matches if any(n != "console" for n in result.notifiers_used) else []
    embudo.contar_jobs("avisada", avisadas)
    embudo.contar_jobs("sin_avisar", [j for j in matches if j not in avisadas])
    if esta_prendido(profile):
        if avisadas:
            state.marcar_notificadas([j.url for j in avisadas])
        embudo.fallas = list(result.skipped)
        embudo.guardar(state.dir, time.time() - t0)

    result.seconds = time.time() - t0
    logger.info(
        f"=== Listo en {result.seconds:.1f}s — {result.fetched} recolectadas, "
        f"{result.new} nuevas, {result.filled} ya cubiertas, {result.deferred} diferidas, "
        f"{result.filtered_out} filtradas, {result.matched} avisadas ==="
    )
    return result
