"""Lo común a todo archivo que la gente sube: dónde se puede escribir y qué es.

Hay dos sitios donde este sistema guarda archivos que suben las personas —las fotos de
pasaporte y los tiquetes del SINAC— y los dos tienen que decidir lo mismo: si el trozo de
texto que viene de afuera se puede usar como nombre de carpeta, y qué clase de archivo es
en realidad. Esas dos respuestas viven aquí, UNA SOLA VEZ.

No es orden por el orden. La primera es una comprobación de seguridad —un valor con «..»
dentro escribe fuera del volumen— y la segunda decide si lo que se guarda es lo que dice
ser. Tenerlas escritas dos veces es la forma en que una se corrige y la otra no, y nadie
se entera hasta que importa. En este mismo repositorio ya pasó con los avisos de
transporte: la regla estaba en un camino de escritura y no en el otro, y el aviso
sencillamente no salía.

LOS BYTES MANDAN, NO LA EXTENSIÓN. El nombre del archivo lo pone quien sube; un «.jpg»
no garantiza nada. Lo que decide qué es un archivo son sus primeros bytes.
"""
import datetime
import os
import re

# Las firmas de lo que el sistema sabe guardar. Cada módulo elige cuáles acepta: el
# pasaporte solo imágenes —es una foto tomada con el teléfono—, el tiquete del SINAC
# también PDF, porque así es como el SINAC manda el comprobante.
JPEG = b"\xff\xd8\xff"
PNG = b"\x89PNG\r\n\x1a\n"
RIFF = b"RIFF"              # se confirma con 'WEBP' en el byte 8
PDF = b"%PDF-"

IMAGENES = {
    JPEG: ("jpg", "image/jpeg"),
    PNG: ("png", "image/png"),
    RIFF: ("webp", "image/webp"),
}
DOCUMENTOS = {PDF: ("pdf", "application/pdf")}

# Lo que un tipo conocido pesa en el disco, para servirlo después. Se deduce de la
# extensión al leer, que es lo único que queda guardado de la fila.
POR_EXTENSION = {ext: mime for ext, mime in
                 list(IMAGENES.values()) + list(DOCUMENTOS.values())}

# Tope por archivo. No es el tamaño esperado —una foto achicada pesa unos 300 KB y un
# comprobante del SINAC menos de 1 MB— sino el muro: sin él, un teléfono que mande la
# foto sin procesar sube 5 MB y basta con que alguien repita para llenar el volumen.
LIMITE_BYTES = 8 * 1024 * 1024


class ArchivoInvalido(Exception):
    """Lo que llegó no es de un tipo aceptado, o pesa más de lo que se admite."""


def tipo_de_los_bytes(datos, aceptados):
    """('jpg', 'image/jpeg') mirando los primeros bytes. Levanta si no es ninguno.

    `aceptados` es un diccionario firma -> (extensión, tipo), para que cada módulo
    decida qué admite sin repetir la comparación.
    """
    for firma, (ext, mime) in aceptados.items():
        if datos.startswith(firma):
            if firma == RIFF and datos[8:12] != b"WEBP":
                continue
            return ext, mime
    nombres = sorted({e.upper() for e, _ in aceptados.values()})
    raise ArchivoInvalido(
        f"El archivo no es de un tipo aceptado (se esperaba {', '.join(nombres)}).")


def revisar(datos, aceptados, que="archivo"):
    """Comprueba lo que llegó ANTES de tocar el disco. Devuelve (extensión, tipo)."""
    if not datos:
        raise ArchivoInvalido(f"No llegó ningún {que}.")
    if len(datos) > LIMITE_BYTES:
        raise ArchivoInvalido(
            f"El {que} pesa {len(datos) // 1024 // 1024} MB y el máximo son "
            f"{LIMITE_BYTES // 1024 // 1024} MB.")
    return tipo_de_los_bytes(datos, aceptados)


def seguro(texto, por_defecto="sin_clasificar"):
    """Un trozo de ruta sin sorpresas: solo letras, números, guiones y guiones bajos.

    El valor viene de afuera —un número de reserva de Opera, una fecha escrita a mano— y
    acaba siendo un nombre de carpeta. Sin esto, un valor con «..» dentro escribiría
    fuera del volumen.
    """
    limpio = re.sub(r"[^A-Za-z0-9_-]", "", str(texto or ""))
    return limpio or por_defecto


def nombre_nuevo(carpeta_relativa, ext):
    """Una ruta relativa que no choca con ninguna otra: marca de tiempo al microsegundo.

    Se usa la hora y no un contador porque así el archivo es único sin preguntarle nada a
    la base, y porque ordenados por nombre quedan ordenados por cuándo se subieron.
    """
    marca = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
    return os.path.join(seguro(carpeta_relativa), f"{marca}.{ext}")


def escribir(raiz, relativa, datos):
    """Guarda los bytes y devuelve la ruta relativa con barras normales.

    Se normaliza la barra a propósito: en Windows os.path.join mete «\\», y esa ruta se
    guarda en la base y se vuelve a leer en el servidor, que es Linux.
    """
    destino = os.path.join(raiz, *str(relativa).replace("\\", "/").split("/"))
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as f:
        f.write(datos)
    return str(relativa).replace("\\", "/")


def ruta_en(raiz, relativa):
    """La ruta en disco de un archivo guardado, o None si ya no está."""
    destino = os.path.join(raiz, *str(relativa).replace("\\", "/").split("/"))
    return destino if os.path.exists(destino) else None


def tipo_por_nombre(relativa):
    """El tipo que hay que servir, deducido de la extensión guardada."""
    ext = str(relativa).rsplit(".", 1)[-1].lower()
    return POR_EXTENSION.get(ext, "application/octet-stream")
