"""
El spa: citas, horarios y choques.

CÓMO FUNCIONA, Y POR QUÉ ASÍ
----------------------------
El huésped **pide** una cita; el spa la **confirma**. No es una reserva en firme desde el
primer momento. Es como se trabaja hoy en el lodge —la hora se acuerda con el spa— y
tiene una ventaja concreta: el sistema no promete una hora que después no se puede
cumplir porque un tratamiento se alargó o la terapeuta llegó tarde.

Lo que el sistema SÍ aporta, y es lo que no daba el formulario de Google:

  · Avisa de CHOQUES. Con la duración de cada tratamiento, el espacio entre citas y
    cuántas terapeutas hay, sabe cuándo dos citas no caben. Antes dos huéspedes podían
    pedir las 10:00 y nadie se enteraba hasta el día.
  · Sabe QUIÉN es el huésped. La cita queda ligada a su reserva, así que solo ofrece
    días de su estadía y la ficha médica no depende de que escriba bien su habitación.
  · Cruza el BUCEO. La pregunta del formulario se conserva tal cual —es de salud y la
    contesta el huésped— pero además el sistema mira si tiene un tour de buceo cerca de
    la cita y lo señala. Dos redes en vez de una.

El precio en dinero queda fuera a propósito: es otro proceso del hotel.
"""
import os
import json
import datetime
import secrets

CONFIG_PATH = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "config_spa.json",
)

# Los valores del lodge. Se pueden cambiar desde la pantalla del spa.
CONFIG_POR_DEFECTO = {
    "abre": "09:30",
    "cierra": "20:00",
    # Espacio entre una cita y la siguiente de la MISMA terapeuta: limpiar la cabina,
    # cambiar sábanas, recibir al siguiente huésped. No es tiempo muerto.
    "minutos_entre": 30,
    # Cada cuántos minutos se ofrecen horas de inicio. 15 da opciones sin marear.
    "paso_minutos": 15,
}

ESTADOS = ("SOLICITADA", "CONFIRMADA", "HECHA", "CANCELADA")
# Las que ocupan a una terapeuta. Una cancelada no estorba, y una hecha ya pasó pero
# sigue ocupando su hueco en el día que se está mirando.
ESTADOS_QUE_OCUPAN = ("SOLICITADA", "CONFIRMADA", "HECHA")


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def cargar_config():
    cfg = dict(CONFIG_POR_DEFECTO)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                guardada = json.load(f)
            if isinstance(guardada, dict):
                cfg.update({k: v for k, v in guardada.items() if k in CONFIG_POR_DEFECTO})
        except (OSError, ValueError):
            # Un archivo torcido no puede dejar el spa sin horario: se siguen usando los
            # valores por defecto, que son los del lodge.
            pass
    return cfg


def guardar_config(cfg):
    limpia = dict(CONFIG_POR_DEFECTO)
    for clave in ("abre", "cierra"):
        if cfg.get(clave) and _minutos(cfg[clave]) is not None:
            limpia[clave] = _hhmm(_minutos(cfg[clave]))
    for clave, minimo, maximo in (("minutos_entre", 0, 180), ("paso_minutos", 5, 60)):
        try:
            limpia[clave] = max(minimo, min(int(cfg[clave]), maximo))
        except (TypeError, ValueError, KeyError):
            pass
    if _minutos(limpia["cierra"]) <= _minutos(limpia["abre"]):
        raise ValueError("La hora de cierre tiene que ser después de la de apertura.")
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(limpia, f, ensure_ascii=False, indent=2)
    return limpia


# ---------------------------------------------------------------------------
# Horas
# ---------------------------------------------------------------------------

def _minutos(hhmm):
    """'09:30' -> 570. None si no es una hora."""
    try:
        h, m = str(hhmm).strip().split(":")[:2]
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except (ValueError, AttributeError, TypeError):
        pass
    return None


def _hhmm(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def normalizar_hora(hhmm):
    m = _minutos(hhmm)
    return _hhmm(m) if m is not None else None


def _ocupa(cita, cfg):
    """(desde, hasta) en minutos del día que esta cita le quita a una terapeuta.

    Se le suma el espacio entre citas AL FINAL: la terapeuta no queda libre en el
    momento en que termina el masaje.
    """
    inicio = _minutos(cita.get("hora"))
    if inicio is None:
        return None
    dura = int(cita.get("minutos") or 60)
    return inicio, inicio + dura + int(cfg.get("minutos_entre", 30))


# ---------------------------------------------------------------------------
# Choques
# ---------------------------------------------------------------------------

def revisar_choque(citas_del_dia, hora, minutos, terapeutas, cfg, excluir_id=None,
                   terapeuta=None):
    """¿Cabe una cita a esa hora? Devuelve una lista de avisos (vacía si cabe).

    Dos comprobaciones distintas, y las dos importan:

      · El HORARIO del spa. Una cita que empieza a las 19:30 y dura 90 minutos termina
        a las 21:00, con el spa cerrado desde las 20:00.
      · La CAPACIDAD. Con dos terapeutas caben dos citas a la vez y no tres. Si la cita
        trae terapeuta asignada, se mira solo la de ella: puede haber hueco en general
        y no con la persona que se eligió.

    No lo impide, avisa. Es la misma decisión que en la Agenda de tours: el spa sabe si
    puede absorber algo que el sistema ve apretado, y bloquearlo obligaría a inventar
    citas falsas para saltarse el sistema.
    """
    avisos = []
    inicio = _minutos(hora)
    if inicio is None:
        return ["La hora no tiene el formato hora:minutos."]
    dura = int(minutos or 60)
    fin = inicio + dura

    abre, cierra = _minutos(cfg["abre"]), _minutos(cfg["cierra"])
    if inicio < abre:
        avisos.append(f"El spa abre a las {cfg['abre']}.")
    if fin > cierra:
        avisos.append(
            f"Terminaría a las {_hhmm(fin)} y el spa cierra a las {cfg['cierra']}.")

    nueva = (inicio, inicio + dura + int(cfg.get("minutos_entre", 30)))
    activas = [c for c in citas_del_dia
               if c.get("estado") in ESTADOS_QUE_OCUPAN and c.get("id") != excluir_id]

    if terapeuta:
        suyas = [c for c in activas if (c.get("terapeuta") or "") == terapeuta]
        for c in suyas:
            otra = _ocupa(c, cfg)
            if otra and nueva[0] < otra[1] and otra[0] < nueva[1]:
                avisos.append(
                    f"{terapeuta} ya tiene una cita a las {c.get('hora')} "
                    f"({c.get('servicio_nombre') or c.get('servicio_codigo')}, "
                    f"hab. {c.get('room_no') or '?'}).")
                break
    else:
        # Sin terapeuta elegida: se cuenta cuántas citas se solapan con esta.
        solapan = 0
        for c in activas:
            otra = _ocupa(c, cfg)
            if otra and nueva[0] < otra[1] and otra[0] < nueva[1]:
                solapan += 1
        libres = max(len(terapeutas), 0) - solapan
        if libres <= 0:
            avisos.append(
                f"A esa hora ya hay {solapan} cita(s) y solo hay {len(terapeutas)} "
                f"terapeuta(s). No alcanza.")
    return avisos


def horas_libres(citas_del_dia, minutos, terapeutas, cfg, excluir_id=None):
    """Las horas de inicio en que esa duración cabe con alguna terapeuta.

    Se usa para SUGERIR, no para reservar: el huésped pide una hora y el spa confirma.
    Aun así vale mucho, porque evita que pida una hora que no existe.
    """
    abre, cierra = _minutos(cfg["abre"]), _minutos(cfg["cierra"])
    paso = int(cfg.get("paso_minutos", 15))
    dura = int(minutos or 60)
    libres = []
    hora = abre
    while hora + dura <= cierra:
        if not revisar_choque(citas_del_dia, _hhmm(hora), dura, terapeutas, cfg,
                              excluir_id=excluir_id):
            libres.append(_hhmm(hora))
        hora += paso
    return libres


def terapeuta_sugerida(citas_del_dia, hora, minutos, terapeutas, cfg, excluir_id=None):
    """La primera terapeuta que tiene el hueco libre. None si ninguna.

    Sirve para que el spa no tenga que ir probando: al confirmar una cita se le propone
    quién puede tomarla.
    """
    for t in terapeutas:
        if not revisar_choque(citas_del_dia, hora, minutos, terapeutas, cfg,
                              excluir_id=excluir_id, terapeuta=t):
            return t
    return None


# ---------------------------------------------------------------------------
# Avisos de salud
# ---------------------------------------------------------------------------

def avisos_de_salud(cita, tours_de_buceo=()):
    """Lo que la terapeuta tiene que saber ANTES de empezar.

    La ficha médica la contesta el huésped y se guarda tal cual. Esto solo la traduce a
    avisos: un dato guardado que nadie lee no protege a nadie.

    'tours_de_buceo' son las fechas ISO en que ese huésped tiene buceo según el sistema.
    Se cruza con la fecha de la cita porque la pregunta del formulario depende de que el
    huésped recuerde —y es una pregunta de salud y seguridad, no de logística.
    """
    avisos = []
    if cita.get("embarazo"):
        avisos.append("Embarazo: confirmar qué tratamientos son adecuados.")
    if cita.get("cirugia_reciente"):
        avisos.append("Cirugía reciente: revisar antes de empezar.")
    if cita.get("buceo_24h"):
        avisos.append("Buceó en las últimas 24 h (lo dijo el huésped).")

    fecha = cita.get("fecha")
    if fecha:
        try:
            dia = datetime.date.fromisoformat(str(fecha))
        except ValueError:
            dia = None
        if dia:
            for f in tours_de_buceo:
                try:
                    d = datetime.date.fromisoformat(str(f))
                except (ValueError, TypeError):
                    continue
                dias = (dia - d).days
                if 0 <= dias <= 1:
                    cuando = "el mismo día" if dias == 0 else "el día anterior"
                    avisos.append(
                        f"El sistema tiene un tour de BUCEO {cuando} ({f}). "
                        f"Confirmar con el huésped antes del tratamiento.")
                    break

    texto = " ".join(str(cita.get(c) or "") for c in ("condicion_medica", "alergias")).strip()
    if texto and texto.lower() not in ("no", "ninguna", "ninguno", "n/a", "na", "none"):
        avisos.append("Tiene anotada condición médica o alergia: leer la ficha.")
    return avisos


# ---------------------------------------------------------------------------
# El enlace personal del huésped
# ---------------------------------------------------------------------------

def token_de_reserva(conn, conf_no, crear=True):
    """El código del enlace que se le manda al huésped. Se crea la primera vez.

    Va por RESERVA y no por habitación: el código de la habitación no cambia nunca
    —los QR se imprimen y se pegan— así que serviría para siempre y un huésped anterior
    podría abrir el enlace del siguiente. Este solo vale mientras esa reserva exista.
    """
    fila = conn.execute("SELECT token FROM spa_enlace WHERE conf_no = ?",
                        (conf_no,)).fetchone()
    if fila and dict(fila).get("token"):
        return dict(fila)["token"]
    if not crear:
        return None
    token = secrets.token_urlsafe(9)
    conn.execute(
        "INSERT INTO spa_enlace (conf_no, token) VALUES (?,?) "
        "ON CONFLICT(conf_no) DO UPDATE SET token = excluded.token",
        (conf_no, token))
    conn.commit()
    return token


def reserva_de_token(conn, conf_no, token):
    """La reserva si el código coincide, o None. Nunca dice cuál de los dos falló."""
    if not conf_no or not token:
        return None
    fila = conn.execute("SELECT token FROM spa_enlace WHERE conf_no = ?",
                        (conf_no,)).fetchone()
    if not fila:
        return None
    if not secrets.compare_digest(str(dict(fila)["token"]), str(token)):
        return None
    r = conn.execute(
        """SELECT conf_no, room_no, nombre_principal, arr_date, dep_date, res_status
           FROM reserva WHERE conf_no = ?""", (conf_no,)).fetchone()
    if not r or (dict(r)["res_status"] or "").upper() == "CANCELADA":
        return None
    return dict(r)
