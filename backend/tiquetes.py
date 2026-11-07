"""Los tiquetes del SINAC: el comprobante de la entrada al parque, guardado y a mano.

POR QUÉ EXISTE. Las entradas de Corcovado, Sirena y la Isla del Caño se compran en línea
y el SINAC devuelve un comprobante. Hasta ahora ese comprobante vivía en el correo de
recepción: el guía salía con una impresión, o con una captura en el teléfono, o sin nada.
En el puesto del parque no hay señal, así que «lo busco en el correo» no es una opción.

Recepción lo sube una vez desde la pantalla de Entradas SINAC y el guía lo abre desde el
mismo sitio, filtrado por la fecha del tour.

LA DECISIÓN QUE SOSTIENE TODO LO DEMÁS: el tiquete NO se cuelga de `entrada_sinac.id`.

Las entradas pendientes SE BORRAN —sinac.limpiar_huerfanas() quita las que se quedan sin
reservas detrás cuando un tour cambia de fecha o se cancela— y el importador las vuelve a
crear con otro id. Una clave foránea ahí dejaría el comprobante apuntando a una fila que
ya no existe, sin un solo error: el archivo seguiría en el disco y el botón del guía
saldría vacío. Se ancla a la FECHA, que es lo que sí sobrevive y además es por lo que
filtra la pantalla.

EL TOUR Y EL NÚMERO SON OPCIONALES. Recepción compra de una sola vez las entradas de
varios tours del mismo día, y a veces el comprobante no dice a cuál corresponde. Exigir
esos datos para poder subirlo significaría que no se sube: la fecha basta para que el
guía lo encuentre, y lo demás afina a qué fila de la tabla se le pone la marca.

ACEPTA PDF, a diferencia de los pasaportes. El SINAC manda el comprobante en PDF casi
siempre; rechazarlo obligaría a recepción a convertirlo a imagen antes de subirlo, que es
justo el paso que hace que la gente deje de usar una herramienta.

DÓNDE VIVEN LOS ARCHIVOS. En el volumen, junto a la base, no dentro de ella —igual que
las fotos de pasaporte y por lo mismo: este sistema hace muchos `SELECT *`—. El costo es
que el respaldo de la base no los incluye.

SIN SEÑAL. El archivo se sirve por una dirección que no cambia nunca —volver a subirlo
crea otra fila con otro número—, el programa de servicio lo guarda en el teléfono y lo
sirve sin preguntarle a la red. La pantalla pide calladamente los de los próximos días al
abrirse con señal, así que para cuando el guía llega al muelle ya están.
"""
import datetime
import os

import archivos
from init_db import DB_PATH

# Lo que se acepta: imágenes (una foto del comprobante impreso, o una captura) y PDF
# (como lo manda el SINAC).
TIPOS = dict(archivos.IMAGENES)
TIPOS.update(archivos.DOCUMENTOS)

LIMITE_BYTES = archivos.LIMITE_BYTES


class TiqueteInvalido(Exception):
    """Lo que llegó no es un comprobante que se pueda guardar."""


def carpeta():
    """Dónde viven los comprobantes: al lado de la base, dentro del volumen."""
    return os.path.join(os.path.dirname(DB_PATH), "tiquetes_sinac")


def normalizar_fecha(fecha):
    """La fecha como 'YYYY-MM-DD', o levanta. Es obligatoria y además es una carpeta.

    Se valida aquí y no solo en la pantalla porque una fecha inventada haría dos cosas
    malas a la vez: crear un directorio con cualquier texto dentro del volumen, y
    guardar un tiquete que el filtro por fechas nunca va a encontrar —el peor fallo
    posible aquí, porque no da error y solo se nota en el puesto del parque—.
    """
    texto = str(fecha or "").strip()
    try:
        return datetime.date.fromisoformat(texto).isoformat()
    except (ValueError, TypeError):
        raise TiqueteInvalido(
            "Falta la fecha del tour que cubre el tiquete, o no se entiende. "
            "Tiene que ser una fecha del calendario.")


def revisar(datos):
    """Comprueba el archivo antes de tocar el disco. Devuelve (extensión, tipo)."""
    try:
        return archivos.revisar(datos, TIPOS, que="tiquete")
    except archivos.ArchivoInvalido as e:
        raise TiqueteInvalido(str(e))


def guardar(conn, fecha, datos, tour_codigo=None, conf_entrada=None, titulo=None,
            pax=None, nota=None, quien=None):
    """Escribe el comprobante en el disco y su fila en la base. Devuelve la fila.

    EL ORDEN IMPORTA: primero el archivo, después la fila. Al revés, un fallo al escribir
    dejaría una fila que promete un comprobante que no existe, y el guía llegaría al
    puesto del parque con un botón que no abre nada. Así, lo peor que puede pasar es un
    archivo huérfano en el disco, que no le miente a nadie.
    """
    fecha = normalizar_fecha(fecha)
    ext, _mime = revisar(datos)

    relativa = archivos.escribir(
        carpeta(), archivos.nombre_nuevo(fecha, ext), datos)

    cur = conn.execute(
        """INSERT INTO tiquete_sinac
             (fecha, tour_codigo, conf_entrada, titulo, archivo, bytes, pax, nota,
              subido_por)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (fecha, _texto(tour_codigo), _texto(conf_entrada), _texto(titulo),
         relativa, len(datos), _entero(pax), _texto(nota), quien))
    conn.commit()
    return dict(conn.execute("SELECT * FROM tiquete_sinac WHERE id = ?",
                             (cur.lastrowid,)).fetchone())


def _texto(valor):
    limpio = str(valor or "").strip()
    return limpio or None


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def ruta_de(fila):
    """La ruta en disco de una fila, o None si el archivo ya no está."""
    return archivos.ruta_en(carpeta(), fila["archivo"])


def tipo_de(fila):
    return archivos.tipo_por_nombre(fila["archivo"])


def borrar(conn, tiquete_id):
    """Quita la fila y el archivo. Devuelve True si había algo que quitar.

    La fila se borra aunque el archivo no esté: una fila que promete un comprobante
    perdido es peor que no tener fila, porque la pantalla lo cuenta como resuelto.
    """
    fila = conn.execute("SELECT * FROM tiquete_sinac WHERE id = ?",
                        (tiquete_id,)).fetchone()
    if not fila:
        return False
    destino = ruta_de(fila)
    conn.execute("DELETE FROM tiquete_sinac WHERE id = ?", (tiquete_id,))
    conn.commit()
    if destino:
        try:
            os.remove(destino)
        except OSError:
            pass          # la fila ya no está, que es lo que ve la pantalla
    return True


def del_rango(conn, desde=None, hasta=None):
    """Los tiquetes de un rango de fechas, en orden de uso: por día y por tour.

    El archivo NO viaja dentro del listado: va por su propia dirección, con su permiso,
    para que una pantalla de dos meses no baje cincuenta PDF que nadie pidió.
    """
    consulta = ("SELECT id, fecha, tour_codigo, conf_entrada, titulo, bytes, pax, nota, "
                "       subido_por, subido_en, archivo "
                "FROM tiquete_sinac")
    params = ()
    if desde and hasta:
        consulta += " WHERE fecha BETWEEN ? AND ?"
        params = (desde, hasta)
    consulta += " ORDER BY fecha, IFNULL(tour_codigo,''), id"
    filas = []
    for f in conn.execute(consulta, params):
        d = dict(f)
        # La extensión sirve para saber si la pantalla lo abre como imagen o como PDF,
        # pero la ruta del archivo no sale de aquí: es una ruta del servidor.
        d["tipo"] = archivos.tipo_por_nombre(d.pop("archivo"))
        filas.append(d)
    return filas


def cubre(tiquete, entrada):
    """¿Este comprobante sirve para esta fila de la tabla?

    LA REGLA, en una sola función porque la usan la pantalla y las pruebas: el mismo día
    y, de lo que el tiquete SÍ diga, nada que contradiga a la entrada.

    Un tiquete sin tour cubre cualquier tour de ese día —es el caso de la compra de todo
    el día, que es como el lodge compra casi siempre—; uno con tour cubre solo ese. Lo
    mismo con el número de confirmación del SINAC.

    Se prefiere que un comprobante aparezca de más a que falte: de más, el guía ve un
    papel que no era el suyo y pasa la página; de menos, llega al puesto sin nada.
    """
    if tiquete.get("fecha") != entrada.get("fecha"):
        return False
    if tiquete.get("tour_codigo") and tiquete["tour_codigo"] != entrada.get("tour_codigo"):
        return False
    if (tiquete.get("conf_entrada")
            and tiquete["conf_entrada"] != (entrada.get("conf_entrada") or None)):
        return False
    return True


def uso(conn):
    """Cuántos comprobantes hay y cuánto ocupan. Lo enseña la pantalla de administración.

    Se cuenta sobre la BASE, no recorriendo el disco: lo que importa es lo que el sistema
    cree tener. Un archivo huérfano no se va a enseñar ni a respaldar.
    """
    fila = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(bytes),0) b FROM tiquete_sinac").fetchone()
    return {"tiquetes": fila["n"], "bytes": fila["b"],
            "dias": conn.execute(
                "SELECT COUNT(DISTINCT fecha) FROM tiquete_sinac").fetchone()[0]}
