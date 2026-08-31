"""
Genera el par de llaves para las notificaciones al celular (VAPID).

    python generar_llaves_push.py

Se corre UNA sola vez. Imprime dos valores que van en las variables del servidor:

    HOTEL_PUSH_PRIVADA   la llave privada. Secreta, solo en el servidor.
    HOTEL_PUSH_PUBLICA   la llave pública. La recibe el navegador de cada persona.

Si algún día se cambian, **todos los celulares dejan de recibir** y cada persona tiene
que volver a activar las notificaciones. Así que se generan una vez y se guardan.
"""
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
