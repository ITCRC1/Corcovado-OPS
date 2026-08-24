"""Importación automática del reporte del PMS, sin que nadie descargue nada.

Lo que molesta hoy no es leer el PDF —eso ya funciona y está probado— sino que alguien
tenga que entrar a OPERA, descargar el reporte y subirlo. Esto quita ese paso.

Cómo funciona: OPERA puede programar el reporte "Arrivals: Detailed" para que salga solo
por correo. El sistema revisa ese buzón cada cierto tiempo, encuentra el PDF adjunto y lo
importa con el mismo lector de siempre.

Y tiene una propiedad que vale más de lo que parece: **funciona igual si el reporte lo
manda OPERA solo o si una persona lo reenvía a mano**. Mientras se configura el envío
automático, o el día que falle, cualquiera reenvía el correo a esa dirección y el sistema
lo levanta. No hay dos caminos que mantener, es el mismo.

Decisiones deliberadas:

  · NO se borra ningún correo. Se marcan como leídos, nada más. Si algo sale mal, el
    original sigue ahí para revisarlo.
  · El mismo archivo no se importa dos veces: se guarda la huella del contenido. OPERA
    puede reenviar el mismo reporte, y reimportar de más no rompe nada, pero llena el
    historial de ruido.
  · Un PDF que no sea el reporte de llegadas se rechaza y queda anotado, en vez de
    importarse a medias.
  · Todo queda registrado —lo importado y lo rechazado—, porque una importación
    automática que falla en silencio es peor que no tenerla.

Reimportar es seguro: el lector conserva las asignaciones de guía y bote que ya hizo
recepción, incluso si el reporte movió el tour de día.
"""
import email
import hashlib
import imaplib
import os
import tempfile
import traceback
from email.header import decode_header

# Todo por variables de entorno: ninguna credencial en el código.
HOST = os.environ.get("BUZON_HOST") or ""          # ej. imap.gmail.com
PUERTO = int(os.environ.get("BUZON_PUERTO") or 993)
USUARIO = os.environ.get("BUZON_USUARIO") or ""
CLAVE = os.environ.get("BUZON_CLAVE") or ""
CARPETA = os.environ.get("BUZON_CARPETA") or "INBOX"
# Filtro opcional: si se define, solo se miran los correos de ese remitente. Conviene
# ponerlo para que un correo cualquiera con un PDF adjunto no entre a la operación.
REMITENTE = (os.environ.get("BUZON_REMITENTE") or "").strip().lower()
MINUTOS = max(int(os.environ.get("BUZON_MINUTOS") or 20), 5)


def configurado():
    return bool(HOST and USUARIO and CLAVE)


def _texto(cabecera):
    """Decodifica un asunto o remitente que venga codificado (=?UTF-8?B?...?=)."""
    if not cabecera:
        return ""
    partes = []
    for valor, codificacion in decode_header(cabecera):
        if isinstance(valor, bytes):
            try:
                partes.append(valor.decode(codificacion or "utf-8", "replace"))
            except LookupError:
                partes.append(valor.decode("utf-8", "replace"))
        else:
            partes.append(valor)
    return "".join(partes).strip()


def _adjuntos_pdf(mensaje):
    """Los PDF del correo, como (nombre, contenido)."""
    salida = []
    for parte in mensaje.walk():
        if parte.get_content_maintype() == "multipart":
            continue
        nombre = _texto(parte.get_filename()) or ""
        tipo = (parte.get_content_type() or "").lower()
        if tipo == "application/pdf" or nombre.lower().endswith(".pdf"):
            datos = parte.get_payload(decode=True)
            if datos:
                salida.append((nombre or "reporte.pdf", datos))
    return salida


def _ya_importado(conn, huella):
    fila = conn.execute(
        "SELECT 1 FROM importacion_buzon WHERE huella = ? AND estado = 'IMPORTADO'",
        (huella,)).fetchone()
    return fila is not None


def _anotar(conn, remitente, asunto, archivo, huella, reservas, estado, detalle=None):
    conn.execute(
        """INSERT INTO importacion_buzon
           (remitente, asunto, archivo, huella, reservas, estado, detalle)
           VALUES (?,?,?,?,?,?,?)""",
        (remitente, asunto, archivo, huella, reservas, estado, detalle))
    conn.commit()


def _importar_pdf(conn, datos, nombre, remitente, asunto):
    """Lee el PDF y lo carga. Devuelve (estado, reservas, detalle)."""
    from importer import build_review_batch
    from loader import load_batch

    huella = hashlib.sha256(datos).hexdigest()
    if _ya_importado(conn, huella):
        _anotar(conn, remitente, asunto, nombre, huella, 0, "REPETIDO",
                "Este mismo archivo ya se había importado.")
        return "REPETIDO", 0, "ya estaba importado"

    ruta = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(datos)
            ruta = tmp.name
        batch = build_review_batch(ruta)
    except Exception:
        _anotar(conn, remitente, asunto, nombre, huella, 0, "ERROR",
                "No se pudo leer el PDF:\n" + traceback.format_exc()[-1200:])
        return "ERROR", 0, "no se pudo leer"
    finally:
        if ruta and os.path.exists(ruta):
            os.unlink(ruta)

    cuantas = len(batch.get("reservas") or [])
    if not cuantas:
        # Casi seguro no es el reporte de llegadas: una factura, una firma, otro reporte.
        _anotar(conn, remitente, asunto, nombre, huella, 0, "IGNORADO",
                "El PDF no contiene reservas: no parece el reporte de llegadas.")
        return "IGNORADO", 0, "sin reservas"

    load_batch(batch, fuente_pdf=f"buzón: {nombre}")
    try:
        from validations import validar_todos_los_tours
        validar_todos_los_tours()
    except Exception:
        pass          # las validaciones no deben tumbar una importación ya hecha
    _anotar(conn, remitente, asunto, nombre, huella, cuantas, "IMPORTADO")
    return "IMPORTADO", cuantas, None


def revisar(get_connection):
    """Mira el buzón y trae lo que haya. Devuelve un resumen de lo que hizo.

    Nunca lanza: si el correo no responde, se anota y se reintenta en la próxima vuelta.
    Una caída del buzón no puede tumbar el sistema.
    """
    if not configurado():
        return {"configurado": False}

    resumen = {"configurado": True, "correos": 0, "importados": 0, "reservas": 0,
               "ignorados": 0, "errores": 0, "detalle": [], "fallo": None}
    buzon = None
    try:
        buzon = imaplib.IMAP4_SSL(HOST, PUERTO)
        buzon.login(USUARIO, CLAVE)
        buzon.select(CARPETA)
        criterio = ["UNSEEN"]
        if REMITENTE:
            criterio = ["UNSEEN", "FROM", REMITENTE]
        estado, respuesta = buzon.search(None, *criterio)
        if estado != "OK":
            resumen["fallo"] = "No se pudo buscar en el buzón"
            return resumen

        ids = respuesta[0].split()
        conn = get_connection()
        try:
            for num in ids:
                estado, datos = buzon.fetch(num, "(RFC822)")
                if estado != "OK" or not datos or not datos[0]:
                    continue
                mensaje = email.message_from_bytes(datos[0][1])
                remitente = _texto(mensaje.get("From"))
                asunto = _texto(mensaje.get("Subject"))
                resumen["correos"] += 1

                pdfs = _adjuntos_pdf(mensaje)
                if not pdfs:
                    # Sin adjunto no hay nada que hacer; se marca leído para no volver
                    # a mirarlo en cada vuelta.
                    buzon.store(num, "+FLAGS", "\\Seen")
                    resumen["detalle"].append({"asunto": asunto, "estado": "SIN_ADJUNTO"})
                    continue

                for nombre, contenido in pdfs:
                    est, cuantas, detalle = _importar_pdf(
                        conn, contenido, nombre, remitente, asunto)
                    resumen["detalle"].append({"asunto": asunto, "archivo": nombre,
                                               "estado": est, "reservas": cuantas})
                    if est == "IMPORTADO":
                        resumen["importados"] += 1
                        resumen["reservas"] += cuantas
                    elif est == "ERROR":
                        resumen["errores"] += 1
                    else:
                        resumen["ignorados"] += 1
                buzon.store(num, "+FLAGS", "\\Seen")
        finally:
            conn.close()
    except Exception as e:
        resumen["fallo"] = f"{type(e).__name__}: {e}"
    finally:
        if buzon is not None:
            try:
                buzon.logout()
            except Exception:
                pass
    return resumen


def historial(conn, limite=25):
    filas = conn.execute(
        """SELECT recibido_en, remitente, asunto, archivo, reservas, estado, detalle
           FROM importacion_buzon ORDER BY id DESC LIMIT ?""", (limite,)).fetchall()
    return [dict(f) for f in filas]


def resumen_estado(conn):
    """Para la pantalla: si está configurado y cómo viene funcionando."""
    ultima = conn.execute(
        """SELECT recibido_en, archivo, reservas FROM importacion_buzon
           WHERE estado = 'IMPORTADO' ORDER BY id DESC LIMIT 1""").fetchone()
    return {
        "configurado": configurado(),
        "buzon": USUARIO if configurado() else None,
        "carpeta": CARPETA if configurado() else None,
        "remitente_filtrado": REMITENTE or None,
        "cada_minutos": MINUTOS,
        "ultima_importacion": dict(ultima) if ultima else None,
        "historial": historial(conn),
    }
