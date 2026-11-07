"""Las fotos de los pasaportes: dónde viven, a quién pertenecen y quién las ve.

POR QUÉ EXISTE. En el puesto del parque —San Pedrillo, Sirena, Isla del Caño— el
guardaparques pide identificación, y hoy eso significa que el huésped se lleve el
pasaporte a la selva o en un bote. El lodge pidió fotografiarlo una vez y que el guía lo
pueda enseñar desde el teléfono en los tours de los días siguientes. Los ocho tours que
requieren entrada del SINAC son justo PNC, SIRENA, SNORKEL, ISLA y BUCEO.

LA DECISIÓN QUE SOSTIENE TODO LO DEMÁS: la foto NO se cuelga de `huesped.id`.

El rooming se borra y se vuelve a escribir ENTERO en cada importación —ver
loader._guardar_rooming— así que esos id cambian cada media hora. Una clave foránea ahí
dejaría todas las fotos apuntando a filas que ya no existen, y lo haría sin un solo
error: el archivo seguiría en el disco, la pantalla del guía saldría vacía, y nadie lo
notaría hasta el puesto del parque. Se ancla al número de reserva y al nombre
normalizado, que es lo que sí sobrevive a una sincronización.

Y LA FOTO PUEDE SER DE ALGUIEN QUE EL PMS NO LISTÓ. Medido sobre la base real: 19
reservas vivas no tienen rooming cargado, y hay una cuyo único «huésped» se llama «LISTA
DE PASAPORTES EN ATTACHMENTS». Si solo se pudiera fotografiar a quien ya está en la
tabla, esas reservas —que son justo las que más falta hacen— quedarían fuera.

DÓNDE VIVEN LOS ARCHIVOS. En el volumen, junto a la base, no dentro de ella. En la base
harían crecer un archivo de 2 MB a cientos, y este sistema hace muchos `SELECT *`. El
costo de sacarlos es que el respaldo de la base NO los incluye; por eso hay un respaldo
de fotos aparte, y la pantalla de administración dice en letra grande que son dos cosas.
El lodge eligió guardarlas indefinidamente, así que no hay borrado automático: solo el
botón de borrar una por una.

SIN SEÑAL. En el puesto del parque no hay internet, y una foto solo se puede enseñar si
sus bytes ya están en el teléfono: no hay forma de esquivar eso. Lo que sí se puede
quitar es el PASO que había que acordarse de dar. La imagen se sirve por una dirección
que no cambia nunca —volver a tomarla crea otra fila con otro número—, el programa de
servicio la guarda y la sirve del teléfono sin preguntarle a la red, y la Agenda las pide
calladamente al abrirse con señal. Para cuando el guía llega al muelle ya están, sin que
nadie haya tocado ningún botón de descarga.
"""
import datetime
import os
import unicodedata

import archivos
from init_db import DB_PATH

# Lo que se acepta subir. La pantalla ya achica la foto a JPEG antes de mandarla, así que
# en la práctica siempre llega JPEG; los otros dos están porque un navegador raro podría
# mandar PNG y rechazarlo sería peor que guardarlo.
#
# AQUÍ NO ENTRA EL PDF, aunque archivos.py sepa reconocerlo: esto es una foto tomada con
# la cámara del teléfono al recibir al huésped. El tiquete del SINAC sí lo acepta, y por
# eso cada módulo elige su lista en vez de compartir una sola.
TIPOS = dict(archivos.IMAGENES)

LIMITE_BYTES = archivos.LIMITE_BYTES


class FotoInvalida(Exception):
    """Lo que llegó no es una imagen, o pesa más de lo que se acepta."""


def carpeta():
    """Dónde viven las fotos: al lado de la base, dentro del volumen."""
    return os.path.join(os.path.dirname(DB_PATH), "pasaportes")


def clave(nombre):
    """El nombre comparable: sin tildes, en mayúsculas y SIN IMPORTAR EL ORDEN.

    Hace falta porque el PMS escribe el nombre de dos formas en la misma reserva: el
    rooming dice «Sanne Catharina Beckers» y la reserva dice «Beckers/Sanne Catharina».
    Quien toma la foto copia la que tenga delante, y comparando el texto tal cual esas
    dos son personas distintas: la pantalla mostraría a Sanne dos veces, una con foto y
    otra sin ella, y nadie sabría cuál es la buena.

    Por eso las palabras se ORDENAN antes de comparar. Dos personas distintas con las
    mismas palabras del nombre en otro orden no existen; el mismo nombre escrito al
    revés, en esta base, pasa todo el tiempo.
    """
    base = (nombre or "").replace(",", " ").replace("/", " ").replace(".", " ")
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", base)
                         if not unicodedata.combining(c))
    return " ".join(sorted(sin_tildes.upper().split()))


def _extension(datos):
    """('jpg', 'image/jpeg') mirando los primeros bytes. No se cree la extensión."""
    try:
        return archivos.tipo_de_los_bytes(datos, TIPOS)
    except archivos.ArchivoInvalido:
        raise FotoInvalida("El archivo no es una foto (se esperaba JPG, PNG o WEBP).")


def revisar(datos):
    """Comprueba el archivo antes de tocar el disco. Devuelve (extensión, tipo).

    El mensaje del tamaño termina diciendo qué hacer —volver a tomarla desde la
    pantalla— porque quien lo lee está en el mostrador con el huésped delante, y un
    «máximo 8 MB» a secas no le dice cómo salir del paso.
    """
    if not datos:
        raise FotoInvalida("No llegó ninguna foto.")
    if len(datos) > LIMITE_BYTES:
        raise FotoInvalida(
            f"La foto pesa {len(datos) // 1024 // 1024} MB y el máximo son "
            f"{LIMITE_BYTES // 1024 // 1024} MB. Volvé a tomarla desde la pantalla, que "
            f"la achica sola.")
    return _extension(datos)


def _nombre_de_archivo(conf_no, ext):
    return os.path.join(_seguro(conf_no), f"{_marca()}.{ext}")


def _marca():
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")


def _seguro(texto):
    """Un trozo de ruta sin sorpresas. La comprobación vive en archivos.seguro()."""
    return archivos.seguro(texto, por_defecto="sin_reserva")


def guardar(conn, conf_no, nombre, datos, quien=None, pasaporte=None,
            origen="RECEPCION", nota=None):
    """Escribe la foto en el disco y su fila en la base. Devuelve la fila.

    EL ORDEN IMPORTA: primero el archivo, después la fila. Al revés, un fallo al escribir
    dejaría una fila que promete una foto que no existe, y la pantalla del guía enseñaría
    un hueco en el puesto del parque. Así, lo peor que puede pasar es un archivo huérfano
    en el disco, que no le miente a nadie.
    """
    ext, mime = revisar(datos)
    nombre = (nombre or "").strip()
    if not nombre:
        raise FotoInvalida("Falta el nombre de la persona del pasaporte.")

    relativa = _nombre_de_archivo(conf_no, ext)
    destino = os.path.join(carpeta(), relativa)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as f:
        f.write(datos)

    cur = conn.execute(
        """INSERT INTO pasaporte_foto
             (conf_no, nombre, nombre_clave, pasaporte, archivo, bytes, tomada_por,
              origen, nota)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (str(conf_no), nombre, clave(nombre), (pasaporte or "").strip() or None,
         relativa.replace("\\", "/"), len(datos), quien,
         origen if origen in ("RECEPCION", "GUIA") else "RECEPCION", nota))
    conn.commit()
    return dict(conn.execute("SELECT * FROM pasaporte_foto WHERE id = ?",
                             (cur.lastrowid,)).fetchone())


def ruta_de(fila):
    """La ruta en disco de una fila, o None si el archivo ya no está."""
    destino = os.path.join(carpeta(), *str(fila["archivo"]).split("/"))
    return destino if os.path.exists(destino) else None


def tipo_de(fila):
    ext = str(fila["archivo"]).rsplit(".", 1)[-1].lower()
    return {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
        ext, "application/octet-stream")


def borrar(conn, foto_id):
    """Quita la fila y el archivo. Devuelve True si había algo que quitar.

    La fila se borra aunque el archivo no esté: una fila que promete una foto perdida es
    peor que no tener fila, porque la pantalla la cuenta como hecha.
    """
    fila = conn.execute("SELECT * FROM pasaporte_foto WHERE id = ?", (foto_id,)).fetchone()
    if not fila:
        return False
    destino = ruta_de(fila)
    conn.execute("DELETE FROM pasaporte_foto WHERE id = ?", (foto_id,))
    conn.commit()
    if destino:
        try:
            os.remove(destino)
        except OSError:
            pass          # la fila ya no está, que es lo que ve la pantalla
    return True


def de_la_reserva(conn, conf_no):
    """Quién va en esa reserva y a quién le falta la foto.

    Junta DOS listas que no tienen por qué coincidir: el rooming que manda el PMS y las
    fotos que se tomaron. Se emparejan por el nombre normalizado, y lo que no empareja
    NO se descarta — sale igual, marcado. Descartarlo sería esconder justo los dos casos
    que importan: el huésped que el PMS no listó, y la foto tomada con el nombre escrito
    de otra forma.
    """
    rooming = [dict(r) for r in conn.execute(
        "SELECT nombre_completo, pasaporte FROM huesped WHERE conf_no = ? ORDER BY id",
        (str(conf_no),))]
    fotos = [dict(f) for f in conn.execute(
        "SELECT * FROM pasaporte_foto WHERE conf_no = ? ORDER BY tomada_en",
        (str(conf_no),))]

    # La clave se vuelve a calcular aquí en vez de usar la guardada. La columna sigue
    # existiendo —sirve para buscar— pero no manda: si algún día hay que afinar la
    # normalización, recalcular deja todas las fotos en su sitio, mientras que confiar en
    # lo guardado las dejaría huérfanas en silencio.
    por_clave = {}
    for f in fotos:
        por_clave.setdefault(clave(f["nombre"]), []).append(f)

    gente, usadas = [], set()
    for r in rooming:
        k = clave(r["nombre_completo"])
        suyas = por_clave.get(k, [])
        usadas.add(k)
        gente.append({
            "nombre": r["nombre_completo"],
            "pasaporte": r["pasaporte"],
            "en_rooming": True,
            "fotos": [_resumen(f) for f in suyas],
        })
    for k, suyas in por_clave.items():
        if k in usadas:
            continue
        gente.append({
            "nombre": suyas[0]["nombre"],
            "pasaporte": suyas[0]["pasaporte"],
            "en_rooming": False,
            "fotos": [_resumen(f) for f in suyas],
        })
    return gente


def _resumen(fila):
    """Lo que la pantalla necesita de una foto. El archivo NO se manda: la imagen va por
    su propia dirección, con su permiso, para que no viaje dentro de cada listado."""
    return {"id": fila["id"], "tomada_en": fila["tomada_en"],
            "tomada_por": fila["tomada_por"], "origen": fila["origen"],
            "bytes": fila["bytes"]}


def salidas_del_dia(conn, fecha):
    """Las salidas de un día con su gente, para el botón de la Agenda de tours.

    Las canceladas no entran: no van a ningún tour.
    """
    filas = [dict(r) for r in conn.execute(
        """SELECT ta.id, ta.tour_codigo, ta.grupo_operativo, ta.guia_nombre, ta.pax,
                  ta.conf_no, r.room_no, r.nombre_principal,
                  tc.horario_inicio, tc.requiere_entrada_sinac
             FROM tour_asignado ta
             JOIN reserva r ON r.conf_no = ta.conf_no
             LEFT JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
            WHERE ta.fecha = ? AND r.res_status != 'CANCELADA'
            ORDER BY tc.horario_inicio, ta.tour_codigo,
                     CAST(r.room_no AS INTEGER)""", (fecha,))]

    salidas = {}
    for f in filas:
        k = (f["tour_codigo"], f["grupo_operativo"] or "A")
        s = salidas.setdefault(k, {
            "tour_codigo": f["tour_codigo"],
            "grupo_operativo": f["grupo_operativo"] or "A",
            "horario_inicio": f["horario_inicio"],
            "guia_nombre": f["guia_nombre"],
            "requiere_entrada_sinac": bool(f["requiere_entrada_sinac"]),
            "habitaciones": [],
        })
        s["habitaciones"].append({
            "conf_no": f["conf_no"],
            "room_no": f["room_no"],
            "nombre_principal": f["nombre_principal"],
            "pax": f["pax"],
            "gente": de_la_reserva(conn, f["conf_no"]),
        })

    lista = list(salidas.values())
    for s in lista:
        s["pax"] = sum(h["pax"] or 0 for h in s["habitaciones"])
        s["con_foto"] = sum(1 for h in s["habitaciones"] for g in h["gente"] if g["fotos"])
        s["sin_foto"] = sum(1 for h in s["habitaciones"] for g in h["gente"]
                            if not g["fotos"])
    return lista


def uso(conn):
    """Cuántas fotos hay y cuánto ocupan. Lo enseña la pantalla de administración.

    Se cuenta sobre la BASE, no recorriendo el disco: lo que importa es lo que el sistema
    cree tener. Si hubiera archivos huérfanos no se cuentan, y es correcto — no se van a
    enseñar ni a respaldar.
    """
    fila = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(bytes),0) b FROM pasaporte_foto").fetchone()
    return {"fotos": fila["n"], "bytes": fila["b"],
            "reservas": conn.execute(
                "SELECT COUNT(DISTINCT conf_no) FROM pasaporte_foto").fetchone()[0]}
