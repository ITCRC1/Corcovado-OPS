"""
Itinerarios por código QR, servidos en vivo desde el propio sistema.

Antes esto publicaba un sitio estático en Netlify: generaba las 30 páginas con sus
PDF, las subía y había que apretar un botón cada vez. Eso traía tres problemas:

  · El sitio quedaba desactualizado. Si recepción editaba un itinerario, movía un
    tour o cambiaba un restaurante, el huésped seguía viendo la versión anterior
    hasta que alguien publicara.
  · Había que republicar todos los días, porque al cambiar los ocupantes cambia el
    contenido de cada habitación. Si nadie lo hacía, el huésped nuevo escaneaba su
    código y veía el itinerario del huésped anterior.
  · Dependía de una cuenta externa, de un token y de tener internet justo entonces.

Ahora la página se arma en el instante en que el huésped escanea su código. Siempre
muestra lo que hay en el sistema, sin publicar nada y sin depender de terceros.

Lo único que se configura es la dirección por la que el sistema es accesible desde
el celular del huésped, y la lista de habitaciones del hotel.
"""

import os
import json
import secrets

CONFIG_PATH = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "config_publicacion.json",
)

HABITACIONES_POR_DEFECTO = [f"{i:02d}" for i in range(1, 31)]


def cargar_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    cfg.setdefault("base_url", "")
    cfg.setdefault("habitaciones", list(HABITACIONES_POR_DEFECTO))
    cfg.setdefault("enlaces_con_codigo", False)
    return cfg


def guardar_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    actual = cargar_config()
    for k in ("base_url", "habitaciones", "enlaces_con_codigo"):
        if k in cfg:
            actual[k] = cfg[k]
    if isinstance(actual.get("habitaciones"), str):
        actual["habitaciones"] = [h.strip() for h in actual["habitaciones"].split(",") if h.strip()]
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(actual, f, ensure_ascii=False, indent=2)
    return actual


def esta_configurado():
    """Basta con saber por qué dirección se alcanza el sistema desde el celular."""
    return bool(cargar_config().get("base_url"))


# ---------------------------------------------------------------------------
# Enlaces de cada habitación
# ---------------------------------------------------------------------------

def token_habitacion(conn, room_no):
    """Código secreto de la habitación, si se activaron los enlaces con código.

    Se genera una sola vez y no cambia nunca: los códigos QR se imprimen una vez y
    se pegan en el cuarto, así que el enlace tiene que seguir funcionando siempre.
    """
    fila = conn.execute("SELECT token FROM habitacion_qr WHERE room_no = ?", (room_no,)).fetchone()
    if fila and dict(fila).get("token"):
        return dict(fila)["token"]
    token = secrets.token_urlsafe(6)
    conn.execute(
        "INSERT INTO habitacion_qr (room_no, token) VALUES (?,?) "
        "ON CONFLICT(room_no) DO UPDATE SET token = excluded.token",
        (room_no, token))
    conn.commit()
    return token


def ruta_habitacion(conn, room_no):
    cfg = cargar_config()
    if cfg.get("enlaces_con_codigo"):
        return f"/i/{room_no}/{token_habitacion(conn, room_no)}"
    return f"/i/{room_no}"


def url_habitacion(conn, room_no, base_url=None):
    base = (base_url if base_url is not None else cargar_config().get("base_url") or "").rstrip("/")
    ruta = ruta_habitacion(conn, room_no)
    return f"{base}{ruta}" if base else ruta


# ---------------------------------------------------------------------------
# Estado informativo de las habitaciones
# ---------------------------------------------------------------------------

def estado_por_habitacion(conn):
    """Qué habitaciones tienen huésped y qué verá el QR de cada una.

    No hay estado "publicado" ni "pendiente": la página se arma al escanear, así que
    siempre está al día. Esta lista es solo para que recepción pueda revisar.
    """
    import qr_huesped as qrh

    cfg = cargar_config()
    salida = []
    for room in cfg.get("habitaciones") or []:
        r = qrh.ocupante_actual(conn, room)
        it = None
        if r:
            fila = conn.execute(
                "SELECT idioma, editado FROM itinerario WHERE conf_no = ?",
                (r["conf_no"],)).fetchone()
            it = dict(fila) if fila else None
        salida.append({
            "room_no": room,
            "conf_no": r["conf_no"] if r else None,
            "huesped": r["nombre_principal"] if r else None,
            "arr_date": r["arr_date"] if r else None,
            "dep_date": r["dep_date"] if r else None,
            "idioma": (it or {}).get("idioma") or "en",
            "editado": bool((it or {}).get("editado")),
            "tiene_itinerario": it is not None,
            "url": url_habitacion(conn, room, cfg.get("base_url")),
        })
    return salida


def resumen(conn):
    por_hab = estado_por_habitacion(conn)
    con = sum(1 for x in por_hab if x["huesped"])
    return {
        "habitaciones": len(por_hab),
        "con_huesped": con,
        "sin_ocupante": len(por_hab) - con,
    }


# ---------------------------------------------------------------------------
# Comidas del huésped, para su página
# ---------------------------------------------------------------------------

def comidas_de(conn, reserva, idioma="en"):
    """Restaurantes asignados al huésped durante su estadía.

    Se calcula al momento de servir la página, así que si la distribución cambió hoy
    el huésped lo ve al escanear su código. Por eso no va en el PDF impreso.
    """
    import datetime
    try:
        import restaurantes as rest
        import traducciones as tr
    except ImportError:
        return None

    def a_fecha(dd):
        try:
            d, m, y = dd.split("-")
            return datetime.date(2000 + int(y), int(m), int(d))
        except (ValueError, AttributeError):
            return None

    llega, sale = a_fecha(reserva.get("arr_date")), a_fecha(reserva.get("dep_date"))
    if not llega:
        return None
    fin = sale or llega
    cn = reserva["conf_no"]
    salida, d = [], llega
    while d < fin and len(salida) < 12:
        try:
            dist = rest.distribuir(conn, d)
        except Exception:
            break

        def buscar(bloque):
            for restaurante, clave in ((rest.TERRA, "terra_kitchen"), (rest.VITRALES, "vitrales")):
                for x in bloque[clave]:
                    if x["conf_no"] == cn:
                        return restaurante, x.get("hora")
            return None, None

        alm, _ = buscar(dist["almuerzo"])
        cena, hora = buscar(dist["cena"])
        if alm or cena:
            salida.append({"dia": tr.formatear_fecha(d.isoformat(), idioma),
                           "almuerzo": alm, "cena": cena, "hora": hora})
        d += datetime.timedelta(days=1)
    return salida or None
