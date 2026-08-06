"""
Publicación del sitio de itinerarios para que el huésped lo vea desde cualquier
lugar con internet, igual que hoy con Canva pero sin trabajo manual.

Idea central: en CADA publicación se regeneran TODAS las habitaciones desde los
datos actuales del sistema. Así nunca queda colgado el itinerario de un huésped
anterior, que es el error más costoso al rotar habitaciones.

El código QR de cada habitación se imprime una sola vez y sirve para siempre,
porque el enlace no cambia nunca: cambia solo el contenido al que apunta.
"""
import io
import os
import json
import zipfile
import secrets
import datetime
import urllib.request
import urllib.error
import hashlib

CONFIG_PATH = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "config_publicacion.json",
)

NETLIFY_API = "https://api.netlify.com/api/v1"


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def cargar_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            pass
    return {"proveedor": "netlify", "site_id": "", "token": "", "base_url": "",
            "enlaces_con_codigo": False,
            "habitaciones": [f"{i:02d}" for i in range(1, 31)]}


def guardar_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def esta_configurado():
    c = cargar_config()
    return bool(c.get("site_id") and c.get("token") and c.get("base_url"))


# ---------------------------------------------------------------------------
# Códigos fijos por habitación
# ---------------------------------------------------------------------------

def token_habitacion(conn, room_no):
    """Devuelve el código fijo de la habitación, creándolo la primera vez.
    Nunca se regenera: de eso depende que el QR impreso siga funcionando."""
    fila = conn.execute("SELECT token FROM habitacion_qr WHERE room_no = ?", (room_no,)).fetchone()
    if fila:
        return fila["token"]
    token = secrets.token_hex(4)   # 8 caracteres, suficiente para no ser adivinable
    conn.execute("INSERT INTO habitacion_qr (room_no, token) VALUES (?, ?)", (room_no, token))
    conn.commit()
    return token


def ruta_habitacion(conn, room_no):
    """Ruta pública de la habitación.

    Por defecto se usa el enlace simple (i/05), igual que los códigos QR ya
    generados. Si se activa "enlaces_con_codigo" en la configuración, se agrega un
    código aleatorio fijo (i/05-a1b2c3d4) para que nadie pueda adivinar el enlace de
    otra habitación; en ese caso los QR deben regenerarse."""
    if cargar_config().get("enlaces_con_codigo"):
        return f"i/{room_no}-{token_habitacion(conn, room_no)}"
    return f"i/{room_no}"


def url_habitacion(conn, room_no, base_url=None):
    base = (base_url or cargar_config().get("base_url", "")).rstrip("/")
    return f"{base}/{ruta_habitacion(conn, room_no)}/"


# ---------------------------------------------------------------------------
# Armado del sitio
# ---------------------------------------------------------------------------

def huella_habitacion(conn, room_no):
    """Huella del contenido de una habitación, calculada solo con los datos.

    Antes se calculaba generando la página y su PDF, lo que hacía que mostrar el
    estado tardara segundos (se producían 30 PDF de ~600 KB cada vez). El contenido
    de la página depende únicamente del huésped y de su itinerario, así que basta
    con resumir esos datos.
    """
    import qr_huesped as qrh
    reserva = qrh.ocupante_actual(conn, room_no)
    if not reserva:
        return hashlib.sha256(f"vacia|{room_no}".encode()).hexdigest()[:16], None, None
    fila = conn.execute(
        "SELECT nombre_bienvenida, filas_json FROM itinerario WHERE conf_no = ?",
        (reserva["conf_no"],)).fetchone()
    if fila:
        d = dict(fila)
        base = (f"{reserva['conf_no']}|{d['nombre_bienvenida']}|"
                f"{d.get('idioma') or 'en'}|{d['filas_json']}")
    else:
        base = f"{reserva['conf_no']}|sin-itinerario"
    return (hashlib.sha256(base.encode("utf-8")).hexdigest()[:16],
            reserva["conf_no"], reserva["nombre_principal"])


DIR_CACHE = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "cache_itinerarios",
)


def _pdf_desde_cache(room_no, huella, generar):
    """Devuelve el PDF de la habitación, reutilizando el de la última vez si su
    contenido no cambió.

    Generar un PDF toma ~100 ms de CPU; hacerlo para 30 habitaciones en cada
    publicación bloqueaba el programa varios segundos. Con esta caché solo se
    regeneran las habitaciones cuyo huésped o itinerario cambió.
    """
    os.makedirs(DIR_CACHE, exist_ok=True)
    ruta = os.path.join(DIR_CACHE, f"{room_no}-{huella}.pdf")
    if os.path.exists(ruta):
        try:
            with open(ruta, "rb") as f:
                return f.read()
        except OSError:
            pass
    datos = generar()
    if datos:
        try:
            # Se borran las versiones anteriores de esta habitación
            for viejo in os.listdir(DIR_CACHE):
                if viejo.startswith(f"{room_no}-") and viejo != os.path.basename(ruta):
                    try:
                        os.remove(os.path.join(DIR_CACHE, viejo))
                    except OSError:
                        pass
            with open(ruta, "wb") as f:
                f.write(datos)
        except OSError:
            pass
    return datos


def construir_sitio(conn):
    """Genera todos los archivos del sitio: una página por habitación (con su PDF
    descargable) más una página de inicio neutra. Devuelve {ruta: contenido_bytes}."""
    import qr_huesped as qrh
    import itinerario as itin
    import catalogo_itinerario as cat

    cfg = cargar_config()
    habitaciones = cfg.get("habitaciones") or []
    archivos = {}
    resumen = []

    for room in habitaciones:
        reserva = qrh.ocupante_actual(conn, room)
        filas, nombre, idioma = [], "", "en"
        if reserva:
            it = conn.execute("SELECT * FROM itinerario WHERE conf_no = ?",
                              (reserva["conf_no"],)).fetchone()
            if it:
                d = dict(it)
                filas = json.loads(d["filas_json"])
                nombre = d["nombre_bienvenida"] or ""
                idioma = d.get("idioma") or "en"
            else:
                datos = itin.datos_de_reserva(conn, reserva["conf_no"])
                if datos:
                    filas, _ = itin.construir_itinerario(datos)
                    nombre = datos["nombre_bienvenida"]

        ruta = ruta_habitacion(conn, room)

        # PDF descargable, con el mismo formato oficial. Se reutiliza el de la
        # publicación anterior si nada cambió en esa habitación.
        enlace_pdf = None
        if reserva and filas:
            huella_prev, _c, _n = huella_habitacion(conn, room)
            try:
                datos_pdf = _pdf_desde_cache(
                    room, huella_prev,
                    lambda: itin.generar_pdf_de_filas(nombre, filas, idioma).getvalue())
                if datos_pdf:
                    archivos[f"{ruta}/itinerary.pdf"] = datos_pdf
                    enlace_pdf = "itinerary.pdf"
            except Exception:
                pass

        html = qrh.pagina_huesped_html(
            reserva, filas, nombre, cat.HORARIOS_LODGE, cat.WHATSAPP_RECEPCION,
            enlace_pdf=enlace_pdf, room_no=room, para_web=True, idioma=idioma,
        )
        archivos[f"{ruta}/index.html"] = html.encode("utf-8")

        # Se usa la misma huella basada en datos que emplea estado_por_habitacion,
        # para que lo registrado al publicar coincida con lo que se compara después.
        huella, _c, _n = huella_habitacion(conn, room)
        resumen.append({"room_no": room,
                        "huesped": reserva["nombre_principal"] if reserva else None,
                        "conf_no": reserva["conf_no"] if reserva else None,
                        "huella": huella,
                        "url": url_habitacion(conn, room, cfg.get("base_url"))})

    # Página de inicio: no expone ningún dato de huéspedes
    archivos["index.html"] = (
        "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Corcovado Wilderness Lodge</title>"
        "<style>body{font-family:-apple-system,Arial,sans-serif;background:#F5F1E8;"
        "color:#1D332A;display:flex;min-height:100vh;align-items:center;"
        "justify-content:center;text-align:center;padding:24px;}"
        "p{font-size:15px;line-height:1.6;max-width:420px;}</style></head><body><div>"
        "<h2>Corcovado Wilderness Lodge</h2>"
        "<p>Please scan the QR code in your room to view your personal itinerary.</p>"
        "</div></body></html>"
    ).encode("utf-8")

    # Recursos compartidos (fondo, logo y tipografías) para que las páginas se vean
    # con el formato oficial también desde internet
    base_assets = os.environ.get("HOTEL_RESOURCE_DIR") or os.path.join(os.path.dirname(__file__), "..")
    dir_assets = os.path.join(base_assets, "frontend", "assets")
    if not os.path.isdir(dir_assets):
        dir_assets = os.path.join(os.path.dirname(__file__), "..", "frontend", "assets")
    for rel in ["logo.jpg", "itinerario/fondo.jpg",
                "fonts/Playfair-Bold.ttf", "fonts/Playfair-Regular.ttf",
                "fonts/ArchivoNarrow-Regular.ttf", "fonts/Cormorant-Italic.ttf",
                "fonts/Playfair-Bold-Cyr.ttf", "fonts/Playfair-Regular-Cyr.ttf",
                "fonts/PTSansNarrow-Cyr.ttf"]:
        ruta_local = os.path.join(dir_assets, rel)
        if os.path.exists(ruta_local):
            with open(ruta_local, "rb") as f:
                archivos[f"assets/{rel}"] = f.read()

    return archivos, resumen


def _zip_del_sitio(archivos):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for ruta, contenido in archivos.items():
            z.writestr(ruta, contenido)
    buf.seek(0)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Publicación
# ---------------------------------------------------------------------------

def publicar(conn, forzar=False):
    """Publica el sitio completo. Si no hay internet o falla, queda registrado como
    pendiente para reintentarlo después (el lodge tiene conexión intermitente)."""
    cfg = cargar_config()
    if not esta_configurado():
        return {"estado": "SIN_CONFIGURAR",
                "mensaje": "Falta configurar la dirección y el acceso de publicación."}

    archivos, resumen = construir_sitio(conn)
    datos_zip = _zip_del_sitio(archivos)

    url = f"{NETLIFY_API}/sites/{cfg['site_id']}/deploys"
    req = urllib.request.Request(url, data=datos_zip, method="POST")
    req.add_header("Authorization", f"Bearer {cfg['token']}")
    req.add_header("Content-Type", "application/zip")

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            respuesta = json.loads(resp.read().decode("utf-8"))
        conn.execute(
            """INSERT INTO publicacion (estado, detalle, habitaciones, intentos, publicado_en)
               VALUES ('PUBLICADO', ?, ?, 1, datetime('now'))""",
            (f"deploy {respuesta.get('id','')}", len(resumen)),
        )
        # Al publicar con éxito ya no queda nada pendiente: se publicó el sitio completo
        # y actualizado, así que los intentos fallidos anteriores quedan resueltos.
        conn.execute("UPDATE publicacion SET estado = 'RESUELTO' WHERE estado = 'PENDIENTE'")
        # Se guarda qué quedó publicado en cada habitación
        for r in resumen:
            conn.execute(
                """INSERT INTO publicacion_habitacion (room_no, conf_no, huella, publicado_en)
                   VALUES (?,?,?,datetime('now'))
                   ON CONFLICT(room_no) DO UPDATE SET
                     conf_no=excluded.conf_no, huella=excluded.huella,
                     publicado_en=excluded.publicado_en""",
                (r["room_no"], r["conf_no"], r["huella"]),
            )
        conn.commit()
        return {"estado": "PUBLICADO", "habitaciones": len(resumen), "resumen": resumen,
                "deploy_id": respuesta.get("id")}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        detalle = str(e)
        if isinstance(e, urllib.error.HTTPError):
            try:
                detalle = f"HTTP {e.code}: {e.read().decode('utf-8')[:250]}"
            except Exception:
                detalle = f"HTTP {e.code}"
        conn.execute(
            """INSERT INTO publicacion (estado, detalle, habitaciones, intentos)
               VALUES ('PENDIENTE', ?, ?, 1)""",
            (detalle, len(resumen)),
        )
        conn.commit()
        return {"estado": "PENDIENTE", "mensaje":
                "No se pudo publicar ahora (probablemente sin internet). "
                "Quedó en cola y se reintentará solo.", "detalle": detalle}


def hay_pendientes(conn):
    fila = conn.execute(
        "SELECT COUNT(*) c FROM publicacion WHERE estado = 'PENDIENTE'"
    ).fetchone()
    return fila["c"] > 0


def reintentar_pendientes(conn):
    """Si quedó algo sin publicar, se vuelve a intentar. Se publica el sitio completo
    y actualizado, no la versión vieja, para que el contenido siempre sea el correcto."""
    if not hay_pendientes(conn) or not esta_configurado():
        return None
    resultado = publicar(conn)
    if resultado.get("estado") == "PUBLICADO":
        conn.execute("UPDATE publicacion SET estado = 'RESUELTO' WHERE estado = 'PENDIENTE'")
        conn.commit()
    return resultado


def estado_por_habitacion(conn):
    """Para cada habitación indica si lo que se ve hoy ya está publicado o si cambió
    desde la última publicación. Solo consulta datos: no genera páginas ni PDF."""
    cfg = cargar_config()
    publicado = {r["room_no"]: dict(r) for r in conn.execute(
        "SELECT * FROM publicacion_habitacion").fetchall()}
    salida = []
    for room in cfg.get("habitaciones") or []:
        huella, conf_no, huesped = huella_habitacion(conn, room)
        ant = publicado.get(room)
        if not ant:
            estado = "SIN_PUBLICAR"
        elif ant["huella"] != huella:
            estado = "CAMBIO"
        else:
            estado = "PUBLICADO"
        salida.append({
            "room_no": room, "huella": huella, "conf_no": conf_no, "huesped": huesped,
            "url": url_habitacion(conn, room, cfg.get("base_url")),
            "estado": estado,
            "publicado_en": ant["publicado_en"] if ant else None,
            "conf_publicado": ant["conf_no"] if ant else None,
        })
    return salida


def estado_publicacion(conn):
    ultima = conn.execute(
        "SELECT * FROM publicacion ORDER BY id DESC LIMIT 1"
    ).fetchone()
    pendientes = conn.execute(
        "SELECT COUNT(*) c FROM publicacion WHERE estado = 'PENDIENTE'"
    ).fetchone()["c"]
    cfg = cargar_config()
    return {
        "configurado": esta_configurado(),
        "base_url": cfg.get("base_url", ""),
        "habitaciones": cfg.get("habitaciones", []),
        "pendientes": pendientes,
        "ultima": dict(ultima) if ultima else None,
    }
