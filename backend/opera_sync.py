"""
Sincronización automática con Opera Cloud.

Cada ciclo trae de Opera las reservas de una ventana de fechas (por defecto desde
ayer hasta 60 días adelante), las traduce al formato del lodge, les aplica las MISMAS
reglas de negocio que al PDF y las carga en la base.

Tres principios rigen este módulo, y los tres existen por la misma razón: el sistema
lo usa recepción para operar el día, y un dato inventado es peor que un dato ausente.

- **Nunca romper la operación.** Si Opera no responde, el ciclo falla en silencio y se
  reintenta más tarde. El sistema sigue trabajando con lo que ya tiene.
- **No cancelar por dudas.** El cargador marca como CANCELADA toda reserva que no
  venga en el lote. Eso solo se activa si se pudo garantizar que la descarga vino
  completa; ante cualquier duda se carga sin cancelar nada.
- **No pisar el trabajo de recepción.** Los puntos de embarque deducidos de texto
  libre entran como "sin confirmar", para que recepción los valide.
"""
import datetime
import json
import os
import threading
import time

CONFIG_PATH = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "config_opera.json",
)

CONFIG_POR_DEFECTO = {
    "activo": False,
    "intervalo_minutos": 30,
    "dias_atras": 1,
    "dias_adelante": 60,
    # Cada cuántas horas se repasa TODO, ignorando las marcas de modificación.
    #
    # Es una red de seguridad, no el mecanismo normal. Lo normal es procesar solo lo
    # que cambió, comparando 'lastModifyDateTime'. Eso se comprobó sobre 20 reservas
    # reales: editar la nota SÍ mueve esa marca, así que los tours que recepción
    # agrega después se detectan.
    #
    # Pero si algún día Opera dejara de moverla en algún caso, el fallo sería
    # SILENCIOSO: la reserva se quedaría vieja para siempre y nadie se enteraría hasta
    # el día del tour. El repaso completo cierra esa puerta a un costo bajo —una vuelta
    # más al día sobre una ventana que ya se descarga igual—.
    #
    # En 0 se apaga.
    "horas_repaso_completo": 12,
}

# Estado del último ciclo, para mostrarlo en pantalla. Vive en memoria: es información
# de diagnóstico, no datos de la operación.
_estado = {
    "ultimo_intento": None,
    "ultimo_exito": None,
    "resultado": "nunca ejecutado",
    "detalle": None,
    "reservas_cargadas": 0,
    "descartadas": 0,
    "completo": None,
}
_lock = threading.Lock()


def cargar_config():
    cfg = dict(CONFIG_POR_DEFECTO)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                guardada = json.load(f)
            if isinstance(guardada, dict):
                cfg.update(guardada)
        except (ValueError, OSError):
            # Un archivo de configuración corrupto no puede tumbar el sistema: se
            # sigue con los valores por defecto, que dejan la sincronización apagada.
            pass
    return cfg


def guardar_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def esta_configurado():
    """Hay credenciales suficientes para intentar la conexión."""
    import opera_cloud as oc
    return not oc._faltantes()


def faltantes():
    import opera_cloud as oc
    return oc._faltantes()


def ventana(cfg=None):
    cfg = cfg or cargar_config()
    hoy = datetime.date.today()
    desde = hoy - datetime.timedelta(days=int(cfg.get("dias_atras", 1) or 0))
    hasta = hoy + datetime.timedelta(days=int(cfg.get("dias_adelante", 60) or 60))
    return desde.isoformat(), hasta.isoformat()


def estado():
    with _lock:
        return dict(_estado)


def _anotar(**campos):
    with _lock:
        _estado.update(campos)


def sincronizar(cargar=True):
    """Un ciclo completo. Devuelve un resumen; nunca lanza excepción hacia afuera."""
    import opera_cloud as oc
    import opera_mapeo as om

    _anotar(ultimo_intento=datetime.datetime.now().isoformat(timespec="seconds"))

    faltan = faltantes()
    if faltan:
        mensaje = "Faltan credenciales de Opera Cloud: " + ", ".join(faltan)
        _anotar(resultado="SIN_CONFIGURAR", detalle=mensaje)
        return {"estado": "SIN_CONFIGURAR", "mensaje": mensaje}

    desde, hasta = ventana()
    try:
        crudas, completo = oc.traer_todas_las_reservas(desde, hasta)
    except Exception as e:
        # Cubre falta de internet, Opera caída, credenciales vencidas. No se toca la
        # base: se reintenta en el próximo ciclo con lo que ya estaba cargado.
        detalle = str(e).splitlines()[0][:300]
        _anotar(resultado="SIN_CONEXION", detalle=detalle)
        return {"estado": "SIN_CONEXION", "mensaje": "No se pudo consultar Opera Cloud",
                "detalle": detalle}

    reservas, descartadas = om.mapear_lote(crudas)

    if not cargar:
        # Se le pasan los bloques que la propiedad concede para que un campo vacío se
        # explique por su causa real: falta el bloque, o falla la ruta.
        bloques = oc.bloques_recordados()
        # En la vista previa se pide el detalle de unas pocas reservas, para que el
        # diagnóstico muestre los tours de verdad y no una lista vacía. No se guarda
        # nada: es solo para mirar.
        #
        # La muestra se REPARTE a lo largo de la ventana, no se toman las primeras.
        #
        # Esto no es un detalle: las primeras reservas de la ventana son las de la
        # fecha más antigua, y en el lodge suelen ser un bloque entero de cuartos de
        # cortesía y de personal, que no llevan tours. Con esa muestra la vista previa
        # informaba "0 tours" y parecía que la conexión no sirve. El mismo error de
        # muestreo ya costó dos diagnósticos equivocados; aquí queda cerrado.
        candidatas = [x for x in reservas
                      if (x.get("res_status") or "") not in ("SALIO", "CANCELADA")]
        candidatas = candidatas or reservas
        paso = max(len(candidatas) // 8, 1)
        muestra = candidatas[::paso][:8]
        detalles = _traer_detalles(muestra)
        return {"estado": "VISTA_PREVIA", "desde": desde, "hasta": hasta,
                "recibidas": len(crudas), "mapeadas": len(reservas),
                "descartadas": descartadas, "completo": completo,
                "bloques": bloques, "manda_en": sorted(alcance_de_opera()),
                "detalle_de_muestra": len(muestra),
                "tours_en_la_muestra": detalles["tours"],
                "paquetes_sin_reconocer": sorted(detalles["desconocidos"]),
                "diagnostico": om.diagnostico(crudas, bloques=bloques,
                                              con_detalle=muestra)}

    if not reservas:
        detalle = f"Opera devolvio {len(crudas)} registros y ninguno se pudo usar"
        _anotar(resultado="SIN_RESERVAS", detalle=detalle,
                reservas_cargadas=0, descartadas=descartadas, completo=completo)
        return {"estado": "SIN_RESERVAS", "recibidas": len(crudas),
                "descartadas": descartadas, "mensaje": detalle}

    from importer import build_review_batch_desde_reservas
    from loader import load_batch
    from validations import validar_todos_los_tours

    # Solo lo que cambió. Opera no deja filtrar por fecha de modificación —se probaron
    # tres parámetros y los tres se ignoran en silencio—, así que la comparación se hace
    # aquí, contra la marca guardada de cada reserva.
    #
    # No es solo por ahorrar trabajo: reescribir las 70 reservas cada media hora movería
    # la marca de actualización de todas, y entonces nadie podría distinguir en la
    # pantalla lo que de verdad cambió de lo que solo se volvió a escribir.
    repaso = _toca_repaso_completo()
    if repaso:
        # Se procesan todas, sin mirar las marcas. Ver 'horas_repaso_completo'.
        nuevas, cambiadas, iguales = [], list(reservas), []
    else:
        nuevas, cambiadas, iguales = _separar_por_cambio(reservas)
    a_cargar = nuevas + cambiadas

    if not a_cargar:
        _anotar(ultimo_exito=datetime.datetime.now().isoformat(timespec="seconds"),
                resultado="SIN_CAMBIOS", detalle=None, reservas_cargadas=0,
                descartadas=descartadas, completo=completo)
        return {"estado": "SIN_CAMBIOS", "desde": desde, "hasta": hasta,
                "revisadas": len(reservas), "nuevas": 0, "cambiadas": 0,
                "sin_cambio": len(iguales), "completo": completo}

    # El detalle de cada reserva que cambió: de ahí salen los tours con su fecha, el
    # régimen y las amenidades. Una petición por reserva, y solo por las que cambiaron.
    detalles = _traer_detalles(a_cargar)

    lote = build_review_batch_desde_reservas(a_cargar)
    # Las amenidades que Opera entrega como paquete se agregan DESPUÉS del importador,
    # porque el importador las deduce del texto y aquí no hay texto: las sobrescribiría
    # con una lista vacía.
    _sumar_amenidades_de_opera(lote)

    # Solo se permite cancelar ausentes si la descarga vino completa. Con una lista
    # parcial, "no vino en el lote" no significa "cancelada": significa que falta, y
    # cancelarla sacaría de la agenda a un huésped que sí llega.
    manda = alcance_de_opera()
    load_batch(lote, fuente_pdf=f"Opera Cloud {desde}/{hasta}",
               marcar_ausentes_como_canceladas=bool(completo),
               manda_en=manda)
    alertas = validar_todos_los_tours()
    alertas += _avisar_paquetes_desconocidos(detalles["desconocidos"])

    _anotar(ultimo_exito=datetime.datetime.now().isoformat(timespec="seconds"),
            resultado="OK", detalle=None, reservas_cargadas=len(a_cargar),
            descartadas=descartadas, completo=completo)
    return {"estado": "OK", "desde": desde, "hasta": hasta,
            "revisadas": len(reservas),
            "reservas_cargadas": len(a_cargar),
            "nuevas": len(nuevas), "cambiadas": len(cambiadas),
            "sin_cambio": len(iguales),
            "repaso_completo": repaso,
            "descartadas": descartadas,
            # De qué está mandando Opera. Se devuelve para que la pantalla pueda decir
            # con claridad qué sigue viniendo del PDF.
            "manda_en": sorted(manda),
            "detalles_pedidos": detalles["pedidos"],
            "detalles_con_error": detalles["errores"],
            "tours_de_opera": detalles["tours"],
            "paquetes_sin_reconocer": sorted(detalles["desconocidos"]),
            "alertas_generadas": len(alertas), "completo": completo}


def _traer_detalles(reservas):
    """Le pide a Opera el detalle de cada reserva y se lo incorpora.

    Una petición por reserva. Es la única forma: la búsqueda no entrega los paquetes
    —Oracle rechaza ese bloque— y entrar a la reserva sí. Como solo se llama con las
    reservas que cambiaron, en régimen normal son unas pocas por ciclo.

    Un fallo en una reserva NO detiene el ciclo: se cuenta y se sigue. Esa reserva
    entra con su núcleo al día y sin tocar sus tours, que es exactamente lo que
    corresponde cuando no se pudo averiguar nada nuevo de ella.
    """
    import opera_cloud as oc
    import opera_mapeo as om

    pedidos = errores = 0
    tours = 0
    desconocidos = {}
    for r in reservas:
        ident = r.get("opera_id") or r.get("conf_no")
        if not ident:
            continue
        try:
            detalle = oc.traer_detalle(ident)
        except Exception as e:
            errores += 1
            _anotar(detalle=f"detalle de {ident}: {str(e).splitlines()[0][:120]}")
            continue
        pedidos += 1
        try:
            sin_reconocer = om.incorporar_detalle(r, detalle)
        except Exception as e:
            errores += 1
            _anotar(detalle=f"mapeo del detalle de {ident}: {str(e)[:120]}")
            continue
        tours += len(r.get("operacion") or [])
        for d in sin_reconocer:
            desconocidos.setdefault(d["codigo"], d)
    return {"pedidos": pedidos, "errores": errores, "tours": tours,
            "desconocidos": desconocidos}


def _sumar_amenidades_de_opera(lote):
    """Devuelve al lote lo que el importador borró sin saberlo.

    El importador deduce las amenidades y el régimen del TEXTO libre de la reserva, y
    en Opera no hay texto: los deja en blanco. Como los deduce él y sobreescribe, lo
    que salió de los paquetes hay que reponerlo DESPUÉS. Si se hiciera antes, se
    perdería.
    """
    for item in lote.get("reservas") or []:
        r = item.get("reserva") or {}

        # El régimen que sale de los paquetes de comida. El del texto manda si existe
        # —es más específico—, y este llena el hueco cuando no hay texto.
        if not r.get("regimen") and r.get("regimen_de_opera"):
            r["regimen"] = r["regimen_de_opera"]

        de_opera = r.get("amenidades_de_opera") or []
        if not de_opera:
            continue
        detectadas = list(r.get("amenidades_detectadas") or [])
        fechas = dict(r.get("fechas_de_amenidad") or {})
        for a in de_opera:
            if a["amenidad"] not in detectadas:
                detectadas.append(a["amenidad"])
            # Opera SÍ sabe qué noche es la cena privada. Es mejor que la fecha por
            # omisión, que es el día de llegada.
            if a.get("fecha"):
                fechas.setdefault(a["amenidad"], a["fecha"])
        r["amenidades_detectadas"] = detectadas
        r["fechas_de_amenidad"] = fechas


def _avisar_paquetes_desconocidos(desconocidos):
    """Un aviso por cada paquete de Opera que el sistema no supo interpretar.

    POR QUÉ AVISAR EN VEZ DE ADIVINAR: si llega un paquete nuevo —el lodge agrega un
    tour, o cambia un código— y el sistema lo interpreta "por parecido", puede poner el
    tour equivocado en la hoja del día y nadie lo notaría. Y si lo ignorara en
    silencio, el tour simplemente no aparecería. Un aviso es la única salida honesta.
    """
    if not desconocidos:
        return []
    from init_db import get_connection

    conn = get_connection()
    mensajes = []
    try:
        for codigo, d in sorted(desconocidos.items()):
            descripcion = d.get("descripcion") or "(sin descripción)"
            nota = f" — {d['nota']}" if d.get("nota") else ""
            msg = (f"Opera trae el paquete «{codigo}» ({descripcion}) y el sistema no "
                   f"sabe qué es{nota}. Si es un tour o una amenidad, hay que agregarlo "
                   f"al mapeo para que aparezca en la agenda.")
            ya = conn.execute(
                "SELECT 1 FROM alerta WHERE tipo='PAQUETE_SIN_MAPEAR' AND mensaje=? "
                "AND resuelto=0", (msg,)).fetchone()
            if not ya:
                conn.execute(
                    "INSERT INTO alerta (tipo, referencia_id, mensaje) "
                    "VALUES ('PAQUETE_SIN_MAPEAR', NULL, ?)", (msg,))
            mensajes.append(msg)
        conn.commit()
    finally:
        conn.close()
    return mensajes


def alcance_de_opera():
    """De qué áreas es dueña la sincronización de Opera: de TODAS.

    Con la consulta individual de cada reserva llega todo lo que el PDF imprime:

      nucleo      la reserva: huésped, fechas, habitación, pax, estado, cancelaciones
      tours       de los paquetes, con su fecha de consumo y la gente que va a cada uno
      regimen     desayuno/almuerzo/cena, de los paquetes de comida
      amenidades  de las Reservation Notes, con los mismos detectores que el PDF
      rooming     de las notas, con nombre y pasaporte
      textos      las notas libres: alergias, vínculos de grupo, guía sugerido
      transporte  el punto de embarque (Sierpe o Drake), el vuelo y la hora

    Las dos últimas son las que faltaban, y salen del bloque **`Comments`** —no
    `ReservationComments`, que es el nombre que Opera rechaza—.

    Si algún día la propiedad deja de entregar ese bloque, esta función lo detecta y
    devuelve solo las áreas que sí llegan: el sistema deja de pisar el trabajo del PDF
    en vez de vaciarlo.
    """
    import opera_cloud as oc

    areas = {"nucleo", "tours", "regimen", "amenidades", "rooming"}
    if "Comments" in set(oc.BLOQUES_DE_UNA_RESERVA):
        areas |= {"textos", "transporte"}
    return frozenset(areas)


_ultimo_repaso = {"cuando": 0.0}


def _toca_repaso_completo(cfg=None):
    """¿Toca repasar TODAS las reservas, sin mirar las marcas de modificación?

    Se marca el momento en cuanto se decide que sí, para que dos ciclos seguidos no
    hagan el repaso dos veces.
    """
    cfg = cfg if cfg is not None else cargar_config()
    try:
        horas = float(cfg.get("horas_repaso_completo") or 0)
    except (TypeError, ValueError):
        horas = 0
    if horas <= 0:
        return False
    ahora = time.time()
    if ahora - _ultimo_repaso["cuando"] < horas * 3600:
        return False
    _ultimo_repaso["cuando"] = ahora
    return True


def _separar_por_cambio(reservas):
    """(nuevas, cambiadas, iguales) comparando la marca de Opera con la guardada.

    Una reserva sin marca se trata como cambiada: es mejor reescribirla de más que
    dejarla vieja. Pasa si Opera deja de mandar 'lastModifyDateTime', y en ese caso
    esto se degrada a lo de antes —cargar todo cada vez— en vez de dejar de funcionar.
    """
    from init_db import get_connection

    conn = get_connection()
    try:
        guardadas = {}
        for fila in conn.execute(
                "SELECT conf_no, opera_modificado_en FROM reserva").fetchall():
            guardadas[str(fila["conf_no"])] = fila["opera_modificado_en"]
    except Exception:
        # Base sin la columna todavía (no se ha reiniciado el servidor): se cargan
        # todas, que es exactamente lo que hacía antes.
        return list(reservas), [], []
    finally:
        conn.close()

    nuevas, cambiadas, iguales = [], [], []
    for r in reservas:
        conf = str(r.get("conf_no"))
        if conf not in guardadas:
            nuevas.append(r)
            continue
        marca = r.get("opera_modificado_en")
        if not marca or str(marca) != str(guardadas[conf] or ""):
            cambiadas.append(r)
        else:
            iguales.append(r)
    return nuevas, cambiadas, iguales


# Se comprueba la configuración cada minuto en vez de dormir el intervalo entero, para
# que al encender la sincronización desde la pantalla el primer ciclo arranque enseguida
# y no hasta media hora después.
LATIDO = 60


def _bucle():
    ultimo = 0.0
    while True:
        try:
            cfg = cargar_config()
            intervalo = max(int(cfg.get("intervalo_minutos", 30) or 30), 5) * 60
            if cfg.get("activo") and esta_configurado() and (time.time() - ultimo) >= intervalo:
                ultimo = time.time()
                sincronizar()
        except Exception as e:
            # El hilo de fondo no puede morir: si muere, la sincronización se apaga
            # sin que nadie se entere hasta que falten reservas en la agenda.
            _anotar(resultado="ERROR", detalle=str(e)[:300])
        time.sleep(LATIDO)


_hilo = None


def iniciar_en_segundo_plano():
    """Arranca el ciclo automático.

    Es seguro llamarlo siempre, aunque no haya credenciales: el bucle comprueba en
    cada vuelta y no hace nada hasta que esté configurado y activado.
    """
    global _hilo
    if _hilo and _hilo.is_alive():
        return _hilo
    _hilo = threading.Thread(target=_bucle, daemon=True, name="opera-sync")
    _hilo.start()
    return _hilo


if __name__ == "__main__":
    import sys
    accion = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if accion == "preview":
        r = sincronizar(cargar=False)
        print(r.get("diagnostico") or r)
    elif accion == "ahora":
        print(sincronizar(cargar=True))
    else:
        print("Uso: python opera_sync.py [preview|ahora]")
