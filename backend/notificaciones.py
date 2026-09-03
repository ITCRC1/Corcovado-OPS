"""
Avisos al celular del personal (notificaciones web).

QUÉ HACE FALTA PARA QUE FUNCIONE, y conviene saberlo antes:

  · Las dos llaves de HOTEL_PUSH_PRIVADA y HOTEL_PUSH_PUBLICA (ver
    generar_llaves_push.py). Sin ellas todo esto queda APAGADO y el sistema funciona
    igual que antes: es el mismo criterio que la sincronización entre estaciones y la
    puerta del portal.
  · En **iPhone**, el aviso solo llega si la persona agregó la app a la pantalla de
    inicio. En una pestaña de Safari no llega, y no hay forma de saltarse eso: es una
    restricción de Apple. En Android llega también desde el navegador.
  · Internet en los dos lados. El aviso viaja por los servidores de Google o de Apple,
    así que si el lodge se queda sin señal el aviso se queda en cola allá y entra cuando
    el celular vuelve a tener datos. No se pierde, pero puede tardar.

TRES REGLAS QUE NO SE ROMPEN AQUÍ:

  1. Enviar NUNCA hace fallar lo que estaba pasando. Si el servidor de Google no
     responde, la importación del PDF tiene que terminar bien igual. Todo va envuelto y
     en un hilo aparte.
  2. Los avisos se AGRUPAN. Una importación puede crear treinta amenidades; treinta
     notificaciones seguidas hacen que la persona silencie la app el primer día, y
     entonces ya no sirve para nada.
  3. Nadie recibe aviso de lo que él mismo acaba de hacer.
"""
import os
import json
import time
import threading
import datetime

PRIVADA = (os.environ.get("HOTEL_PUSH_PRIVADA") or "").strip()
PUBLICA = (os.environ.get("HOTEL_PUSH_PUBLICA") or "").strip()

# Sin las variables puestas, el sistema se genera las llaves solo y las guarda al lado
# de la base. Antes esto quedaba apagado esperando que alguien pusiera dos variables a
# mano, y la pantalla decía "no están configurados" sin que nadie supiera qué hacer con
# eso. Las variables siguen mandando si están: sirven para usar las mismas llaves en dos
# instalaciones, o para rotarlas a propósito.
if not (PRIVADA and PUBLICA):
    try:
        from init_db import DB_PATH as _DB
        from generar_llaves_push import cargar_o_crear as _cargar
        _p, _u = _cargar(os.path.join(os.path.dirname(_DB), "llaves_avisos.json"))
        if _p and _u:
            PRIVADA, PUBLICA = _p, _u
    except Exception:
        # Falta 'cryptography', la ruta no se puede escribir, lo que sea: el sistema
        # arranca igual y los avisos quedan apagados, que es como estaban antes.
        pass
CONTACTO = (os.environ.get("HOTEL_PUSH_CONTACTO")
            or "mailto:no-reply@corcovadowildernesslodge.com").strip()

# Cuánto se espera a cada servidor de notificaciones. Corto a propósito: si tarda más,
# el aviso no vale la pena y no puede quedarse colgando un hilo del servidor.
TIEMPO_LIMITE = 10

# A qué hora (del servidor) se manda el repaso de lo pendiente para hoy.
HORA_REPASO = int(os.environ.get("HOTEL_PUSH_HORA_REPASO") or "6")


def habilitado():
    """Si las notificaciones están configuradas. Con esto apagado nada de aquí actúa."""
    return bool(PRIVADA and PUBLICA)


def clave_publica():
    return PUBLICA


def _disponible():
    """Si la librería de envío está instalada. Se comprueba aparte de las llaves para
    poder decir con precisión qué falta."""
    try:
        import pywebpush  # noqa: F401
        return True
    except ImportError:
        return False


def estado():
    """Para que la pantalla pueda explicar por qué no funciona, en vez de callarse."""
    if not _disponible():
        return {"activo": False,
                "motivo": "Falta la librería pywebpush en el servidor."}
    if not habilitado():
        return {"activo": False,
                "motivo": ("No se pudieron crear las llaves de los avisos. Revisa que "
                           "la carpeta de datos se pueda escribir, o pon a mano "
                           "HOTEL_PUSH_PRIVADA y HOTEL_PUSH_PUBLICA en el servidor "
                           "(python generar_llaves_push.py las genera).")}
    return {"activo": True, "clave_publica": PUBLICA}


# ---------------------------------------------------------------------------
# Suscripciones
# ---------------------------------------------------------------------------

def guardar_suscripcion(conn, usuario_id, suscripcion, aparato=None):
    """Anota que este aparato quiere recibir avisos.

    Si la misma dirección vuelve a llegar (la persona la activó otra vez), se actualiza
    en vez de duplicarse: el navegador puede dar la misma dirección más de una vez.
    """
    endpoint = (suscripcion or {}).get("endpoint")
    claves = (suscripcion or {}).get("keys") or {}
    if not endpoint or not claves.get("p256dh") or not claves.get("auth"):
        return False, "La suscripción del navegador llegó incompleta."
    conn.execute(
        """INSERT INTO suscripcion_push (endpoint, usuario_id, p256dh, auth, aparato)
           VALUES (?,?,?,?,?)
           ON CONFLICT(endpoint) DO UPDATE SET
             usuario_id = excluded.usuario_id,
             p256dh = excluded.p256dh,
             auth = excluded.auth,
             aparato = excluded.aparato,
             fallos = 0""",
        (endpoint, usuario_id, claves["p256dh"], claves["auth"],
         (aparato or "")[:120] or None))
    conn.commit()
    return True, None


def borrar_suscripcion(conn, endpoint):
    conn.execute("DELETE FROM suscripcion_push WHERE endpoint = ?", (endpoint,))
    conn.commit()


def suscripciones_de(conn, usuario_id):
    return [dict(r) for r in conn.execute(
        "SELECT endpoint, aparato, creado_en FROM suscripcion_push WHERE usuario_id = ?",
        (usuario_id,)).fetchall()]


def destinatarios_amenidades(conn, excluir_usuario_id=None):
    """TODOS los usuarios activos, sin mirar permisos.

    Decisión del hotel, tomada a sabiendas: en el lodge trabaja un equipo pequeño y
    quien tiene que preparar algo tiene que enterarse, tenga o no acceso a esa pantalla
    del sistema. Los permisos siguen mandando en lo que cada quien puede VER Y HACER
    dentro del sistema; lo que se decidió es que el aviso no se guíe por ellos.

    Lo que eso implica, para que quede escrito: el texto del aviso lleva datos del
    huésped ("Hab. 12 · Restricción alimentaria", que además es dato de salud), así que
    ese texto le llega también a quien no puede abrir la pantalla de Amenidades. Al
    tocarlo, la app no lo lleva ahí —comprueba el permiso antes de navegar— pero el
    texto ya lo leyó.

    Si algún día hace falta afinarlo, este es el único sitio donde se decide. Cada
    amenidad tiene su área responsable (Cocina, Housekeeping…), pero los usuarios no
    tienen área, así que hoy no se puede repartir por área aunque se quisiera.
    """
    filas = conn.execute(
        "SELECT id FROM usuario WHERE activo = 1").fetchall()
    return [u["id"] for u in filas
            if not (excluir_usuario_id and u["id"] == excluir_usuario_id)]


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------

def _enviar_ahora(filas, carga):
    """Manda de verdad, y devuelve las direcciones que ya no existen.

    Un 404 o un 410 del servidor de notificaciones significa que ese aparato se fue para
    siempre (la app se desinstaló, o se borraron los datos del navegador). Esas se
    borran. Cualquier otro error se cuenta pero no se borra: puede ser pasajero.
    """
    from pywebpush import webpush, WebPushException

    muertas, fallidas = [], []
    for f in filas:
        try:
            webpush(
                subscription_info={
                    "endpoint": f["endpoint"],
                    "keys": {"p256dh": f["p256dh"], "auth": f["auth"]},
                },
                data=json.dumps(carga, ensure_ascii=False),
                vapid_private_key=PRIVADA,
                vapid_claims={"sub": CONTACTO},
                timeout=TIEMPO_LIMITE,
            )
        except WebPushException as e:
            codigo = getattr(getattr(e, "response", None), "status_code", None)
            if codigo in (404, 410):
                muertas.append(f["endpoint"])
            else:
                fallidas.append((f["endpoint"], codigo or str(e)[:80]))
        except Exception as e:            # red caída, DNS, lo que sea
            fallidas.append((f["endpoint"], f"{type(e).__name__}"))
    return muertas, fallidas


def enviar(usuario_ids, titulo, cuerpo, etiqueta="amenidades", pantalla=5, datos=None):
    """Manda un aviso a esos usuarios, en un hilo aparte.

    Vuelve de inmediato: quien llama no espera a Google. Si algo falla, se anota en el
    registro del servidor y nada más — un aviso que no sale no puede tumbar una
    importación de PDF ni dejar a medias el guardado de una amenidad.

    'etiqueta' agrupa: dos avisos con la misma etiqueta se reemplazan en el celular en
    vez de apilarse. Así el repaso de la mañana no deja siete notificaciones viejas.
    """
    if not habilitado() or not _disponible() or not usuario_ids:
        return

    carga = {
        "titulo": titulo,
        "cuerpo": cuerpo,
        "etiqueta": etiqueta,
        "pantalla": pantalla,
        "datos": datos or {},
    }

    def trabajo():
        from init_db import get_connection
        conn = get_connection()
        try:
            marcas = ",".join("?" * len(usuario_ids))
            filas = [dict(r) for r in conn.execute(
                f"""SELECT endpoint, p256dh, auth FROM suscripcion_push
                    WHERE usuario_id IN ({marcas})""", list(usuario_ids)).fetchall()]
            if not filas:
                return
            muertas, fallidas = _enviar_ahora(filas, carga)
            if muertas:
                conn.execute(
                    f"""DELETE FROM suscripcion_push
                        WHERE endpoint IN ({','.join('?' * len(muertas))})""", muertas)
            for endpoint, _motivo in fallidas:
                conn.execute(
                    "UPDATE suscripcion_push SET fallos = fallos + 1 WHERE endpoint = ?",
                    (endpoint,))
            enviadas = len(filas) - len(muertas) - len(fallidas)
            if enviadas:
                conn.execute(
                    f"""UPDATE suscripcion_push SET ultimo_envio = datetime('now'),
                        fallos = 0 WHERE endpoint IN ({','.join('?' * len(filas))})""",
                    [f["endpoint"] for f in filas])
            conn.commit()
            if muertas:
                print(f"[avisos] {len(muertas)} aparato(s) ya no existen: se quitaron")
            if fallidas:
                print(f"[avisos] {len(fallidas)} no se pudieron entregar: "
                      + ", ".join(str(m) for _e, m in fallidas[:3]))
        except Exception as e:
            # Aquí no se levanta nunca: este hilo no puede tumbar el servidor.
            print(f"[avisos] error al enviar: {type(e).__name__}: {e}")
        finally:
            conn.close()

    threading.Thread(target=trabajo, daemon=True).start()


def enviar_a_uno(usuario_id, titulo, cuerpo, etiqueta="prueba"):
    enviar([usuario_id], titulo, cuerpo, etiqueta=etiqueta)


# ---------------------------------------------------------------------------
# Los avisos concretos
# ---------------------------------------------------------------------------

def _texto_amenidad(a):
    hab = a.get("room_no") or "?"
    return f"Hab. {hab} · {a.get('amenidad') or 'requerimiento'}"


def aviso_amenidad_nueva(conn, amenidad, quien_la_creo=None):
    """Una amenidad agregada a mano. Va de una porque es un acto deliberado."""
    if not habilitado():
        return
    destinos = destinatarios_amenidades(conn, excluir_usuario_id=quien_la_creo)
    if not destinos:
        return
    cuando = amenidad.get("fecha")
    detalle = _texto_amenidad(amenidad)
    if cuando:
        detalle += f" · para el {cuando}"
    area = amenidad.get("area_responsable")
    if area:
        detalle += f" · {area}"
    enviar(destinos, "Requerimiento nuevo", detalle, etiqueta="amenidad-nueva")


def destinatarios_spa(conn):
    """Quien tenga permiso en la pantalla del Spa: recepción y el spa.

    AQUÍ SÍ SE MIRAN LOS PERMISOS, al contrario que en las amenidades — y es a pedido
    del hotel. La razón práctica: una cita de spa la atiende quien está en el spa, y el
    aviso lleva datos de salud del huésped ("embarazo", "cirugía reciente"). Mandarlo a
    todo el personal repartiría ese dato de más sin que nadie lo necesitara.

    Quien administra el sistema (recepción y gerencia) tiene la pantalla, así que le
    llega. Si hace falta que le llegue a alguien más, se le da permiso de Spa en la
    pantalla de Usuarios — sin tocar código.
    """
    import auth
    filas = conn.execute(
        "SELECT id, rol, permisos_json FROM usuario WHERE activo = 1").fetchall()
    destinos = []
    for u in filas:
        if auth.puede(dict(u), "spa"):
            destinos.append(u["id"])
    return destinos


def aviso_cita_spa(cita):
    """Una cita que pidió el huésped por su enlace. Va de una: hay que confirmarla.

    Se abre en la pantalla del Spa al tocarlo (índice 7 del menú).

    No lleva la ficha médica en el texto: para eso se abre la cita. Un aviso que se lee
    en la pantalla de bloqueo del teléfono no es sitio para un dato de salud.
    """
    if not habilitado():
        return
    from init_db import get_connection
    conn = get_connection()
    try:
        destinos = destinatarios_spa(conn)
    finally:
        conn.close()
    if not destinos:
        return
    partes = [f"Hab. {cita.get('room_no') or '?'}"]
    if cita.get("servicio"):
        partes.append(str(cita["servicio"]))
    if cita.get("fecha"):
        partes.append(f"el {cita['fecha']}")
    if cita.get("hora"):
        partes.append(f"a las {cita['hora']}")
    enviar(destinos, "Cita de spa por confirmar", " · ".join(partes),
           etiqueta="spa-cita", pantalla=7)


def aviso_amenidades_importadas(conn, cuantas, para_manana=0):
    """Después de importar el PDF: UN aviso con el total, no uno por amenidad.

    Treinta notificaciones seguidas hacen que la persona silencie la app, y entonces
    tampoco recibirá la que sí importaba.
    """
    if not habilitado() or not cuantas:
        return
    destinos = destinatarios_amenidades(conn)
    if not destinos:
        return
    cuerpo = f"{cuantas} amenidad(es) para preparar"
    if para_manana:
        cuerpo += f", {para_manana} para mañana"
    enviar(destinos, "Reporte importado", cuerpo, etiqueta="import-amenidades")


def pendientes_para(conn, fecha_iso):
    """Amenidades pendientes cuya fecha es ese día."""
    return [dict(r) for r in conn.execute(
        """SELECT a.id, a.amenidad, a.area_responsable, a.fecha, r.room_no
           FROM amenidad_tarea a JOIN reserva r ON r.conf_no = a.conf_no
           WHERE a.estado = 'PENDIENTE' AND a.fecha = ?
             AND r.res_status != 'CANCELADA'
           ORDER BY CAST(r.room_no AS INTEGER)""", (fecha_iso,)).fetchall()]


def aviso_repaso_del_dia(conn, fecha=None):
    """El repaso de la mañana: qué hay pendiente para hoy.

    Se manda una sola vez al día. La marca de que ya se mandó vive en config_estacion,
    así que un reinicio del servidor no lo repite.
    """
    if not habilitado():
        return 0
    hoy = (fecha or datetime.date.today()).isoformat()
    marca = conn.execute(
        "SELECT valor FROM config_estacion WHERE clave = 'push_repaso_enviado'"
    ).fetchone()
    if marca and marca["valor"] == hoy:
        return 0

    pendientes = pendientes_para(conn, hoy)
    conn.execute(
        """INSERT INTO config_estacion (clave, valor) VALUES ('push_repaso_enviado', ?)
           ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor""", (hoy,))
    conn.commit()

    if not pendientes:
        return 0
    destinos = destinatarios_amenidades(conn)
    if not destinos:
        return 0

    # Las tres primeras por nombre, y el resto contado: en la pantalla del celular no
    # cabe más, y una lista cortada a la mitad se lee peor que un total.
    muestra = " · ".join(_texto_amenidad(a) for a in pendientes[:3])
    if len(pendientes) > 3:
        muestra += f" · y {len(pendientes) - 3} más"
    enviar(destinos, f"Hoy: {len(pendientes)} pendiente(s)", muestra,
           etiqueta="repaso-dia")
    return len(pendientes)


# ---------------------------------------------------------------------------
# El hilo del repaso diario
# ---------------------------------------------------------------------------

def _bucle_repaso():
    """Revisa cada media hora si ya es la hora del repaso y si falta mandarlo.

    Se comprueba la hora en vez de dormir hasta ella a propósito: así un reinicio del
    servidor a media noche no se salta el repaso del día.
    """
    from init_db import get_connection
    time.sleep(60)          # un momento de gracia, que el servidor quede sirviendo
    while True:
        try:
            if datetime.datetime.now().hour >= HORA_REPASO:
                conn = get_connection()
                try:
                    n = aviso_repaso_del_dia(conn)
                    if n:
                        print(f"[avisos] repaso del día enviado: {n} pendiente(s)")
                finally:
                    conn.close()
        except Exception as e:
            print(f"[avisos] el repaso del día falló: {type(e).__name__}: {e}")
        time.sleep(1800)


def arrancar():
    """Arranca el hilo del repaso, solo si las notificaciones están configuradas."""
    if not habilitado():
        return False
    if not _disponible():
        print("AVISO: hay llaves de notificaciones pero falta pywebpush. "
              "Los avisos al celular quedan apagados.")
        return False
    threading.Thread(target=_bucle_repaso, daemon=True).start()
    print(f"[avisos] notificaciones al celular activas · repaso diario a las "
          f"{HORA_REPASO}:00")
    return True
