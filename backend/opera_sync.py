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
        return {"estado": "VISTA_PREVIA", "desde": desde, "hasta": hasta,
                "recibidas": len(crudas), "mapeadas": len(reservas),
                "descartadas": descartadas, "completo": completo,
                "diagnostico": om.diagnostico(crudas)}

    if not reservas:
        detalle = f"Opera devolvio {len(crudas)} registros y ninguno se pudo usar"
        _anotar(resultado="SIN_RESERVAS", detalle=detalle,
                reservas_cargadas=0, descartadas=descartadas, completo=completo)
        return {"estado": "SIN_RESERVAS", "recibidas": len(crudas),
                "descartadas": descartadas, "mensaje": detalle}

    from importer import build_review_batch_desde_reservas
    from loader import load_batch
    from validations import validar_todos_los_tours

    lote = build_review_batch_desde_reservas(reservas)
    # Solo se permite cancelar ausentes si la descarga vino completa. Con una lista
    # parcial, "no vino en el lote" no significa "cancelada": significa que falta, y
    # cancelarla sacaría de la agenda a un huésped que sí llega.
    load_batch(lote, fuente_pdf=f"Opera Cloud {desde}/{hasta}",
               marcar_ausentes_como_canceladas=bool(completo))
    alertas = validar_todos_los_tours()

    _anotar(ultimo_exito=datetime.datetime.now().isoformat(timespec="seconds"),
            resultado="OK", detalle=None, reservas_cargadas=len(reservas),
            descartadas=descartadas, completo=completo)
    return {"estado": "OK", "desde": desde, "hasta": hasta,
            "reservas_cargadas": len(reservas), "descartadas": descartadas,
            "alertas_generadas": len(alertas), "completo": completo}


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
