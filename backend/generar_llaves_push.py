"""
Las llaves para las notificaciones al celular (VAPID).

NO HACE FALTA CORRERLO A MANO. El sistema las genera solo la primera vez que arranca y
las guarda junto a la base de datos (data/llaves_avisos.json, o el volumen del servidor).
Esto existe por si alguien quiere ponerlas a mano en las variables del servidor:

    python generar_llaves_push.py

    HOTEL_PUSH_PRIVADA   la llave privada. Secreta, solo en el servidor.
    HOTEL_PUSH_PUBLICA   la llave pública. La recibe el navegador de cada persona.

Si las variables están puestas, MANDAN sobre el archivo. Eso sirve para tener las mismas
llaves en dos instalaciones, o para rotarlas a propósito.

Si algún día se cambian, **todos los celulares dejan de recibir** y cada persona tiene
que volver a activar las notificaciones. Por eso se generan una vez y se guardan, en vez
de crearse en cada arranque.
"""
import os
import json
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(datos):
    """base64 de URL, sin el relleno de '=' — es como lo espera el navegador."""
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def generar():
    clave = ec.generate_private_key(ec.SECP256R1())

    # La privada, en el formato que espera pywebpush: los 32 bytes del número, en base64
    privada = _b64(clave.private_numbers().private_value.to_bytes(32, "big"))

    # La pública, como punto sin comprimir (0x04 + X + Y): es lo que pide el navegador
    publica = _b64(clave.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint))

    return privada, publica


def cargar_o_crear(ruta):
    """Las llaves guardadas junto a la base. Si no existen, se crean y se guardan.

    POR QUÉ EXISTE: las notificaciones estaban apagadas hasta que alguien pusiera dos
    variables en el servidor a mano. Eso es un paso que nadie descubre solo, y el
    resultado era una pantalla que decía "no están configurados" sin que quedara claro
    quién tenía que hacer qué. Ahora el sistema se las genera y la pantalla funciona.

    Van al lado de la base de datos a propósito: es el mismo sitio donde viven las
    suscripciones de cada teléfono. Si se pierde uno se pierde el otro, así que
    guardarlos aparte no protegería de nada y sí daría un caso raro más.

    Devuelve (privada, publica), o (None, None) si el archivo no se pudo escribir —el
    sistema sigue arrancando, solo sin avisos, que es como estaba antes.
    """
    # La LECTURA va en su propio try, y esto importa: si el archivo quedó a medio
    # escribir (un corte de luz, un disco lleno), leerlo revienta. Antes ese error se
    # mezclaba con los de escritura y el resultado era dejar los avisos apagados para
    # siempre por un archivo roto que se podía rehacer solo. Ahora se rehace.
    try:
        if os.path.exists(ruta):
            with open(ruta, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("privada") and d.get("publica"):
                return d["privada"], d["publica"]
    except (OSError, ValueError, AttributeError):
        pass

    try:
        privada, publica = generar()
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"privada": privada, "publica": publica,
                       "_nota": ("Llaves de las notificaciones al celular. NO se suben "
                                 "al repositorio. Si se borran, cada persona tiene que "
                                 "volver a activar los avisos en su teléfono.")},
                      f, indent=2)
        return privada, publica
    except (OSError, ValueError, KeyError):
        # Disco de solo lectura, archivo corrupto, permisos. No es motivo para que el
        # sistema no arranque: las notificaciones son un extra, la operación no.
        return None, None


if __name__ == "__main__":
    privada, publica = generar()
    print("")
    print("=" * 74)
    print("  LLAVES PARA LAS NOTIFICACIONES AL CELULAR")
    print("=" * 74)
    print("")
    print("  Pon estas dos variables en el servidor (en Railway, pestaña Variables):")
    print("")
    print(f"  HOTEL_PUSH_PRIVADA={privada}")
    print(f"  HOTEL_PUSH_PUBLICA={publica}")
    print("")
    print("  Y esta, con un correo de contacto del hotel. La piden los servidores de")
    print("  Google y Apple para poder avisar si algo va mal con los envíos:")
    print("")
    print("  HOTEL_PUSH_CONTACTO=mailto:management@thecostaricacollection.com")
    print("")
    print("  Guárdalas. Si se cambian, todos los celulares dejan de recibir y cada")
    print("  persona tiene que volver a activar las notificaciones.")
    print("=" * 74)
    print("")
