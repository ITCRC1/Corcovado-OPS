"""
Levanta el sistema en local CON los avisos al celular encendidos, para poder verlos.

    python probar_avisos.py

Usa una carpeta de datos aparte (data-avisos/) y unas llaves de prueba, así no toca
nada de la base real ni de la de producción.

Por qué se puede probar de verdad desde aquí: los navegadores tratan `localhost` como
sitio seguro, así que las notificaciones funcionan igual que con https. El aviso sale a
los servidores de Google de verdad y vuelve a esta computadora — es una prueba completa,
no una simulación.

En el celular NO va a funcionar apuntando a la IP de esta máquina: ahí sí hace falta
https, y eso solo lo hay en el servidor de verdad.
"""
import os
import sys
import secrets
import subprocess

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "data-avisos")
PUERTO = os.environ.get("PORT") or "8000"

sys.path.insert(0, os.path.join(AQUI, "backend"))
os.environ["HOTEL_DATA_DIR"] = DATOS
os.makedirs(DATOS, exist_ok=True)

# Llaves SOLO para esta prueba. Las de producción se generan aparte y se guardan en el
# servidor; estas se regeneran cada vez que no existan, y viven en la carpeta de prueba.
ARCHIVO_LLAVES = os.path.join(DATOS, "llaves-de-prueba.txt")
if os.path.exists(ARCHIVO_LLAVES):
    with open(ARCHIVO_LLAVES, encoding="utf-8") as f:
        privada, publica = f.read().strip().split("\n")[:2]
else:
    from generar_llaves_push import generar
    privada, publica = generar()
    with open(ARCHIVO_LLAVES, "w", encoding="utf-8") as f:
        f.write(f"{privada}\n{publica}\n")

entorno = dict(os.environ)
entorno.update({
    "HOTEL_DATA_DIR": DATOS,
    "HOTEL_PORT": PUERTO,
    "HOTEL_HOST": "127.0.0.1",
    "HOTEL_ABRIR_NAVEGADOR": "0",
    "HOTEL_ADMIN_PASSWORD": "clavedepruebas2026",
    "HOTEL_PUSH_PRIVADA": privada,
    "HOTEL_PUSH_PUBLICA": publica,
    "HOTEL_PUSH_CONTACTO": "mailto:management@thecostaricacollection.com",
    "PYTHONIOENCODING": "utf-8",
})

print("")
print("=" * 70)
print("  CORCOVADO-OPS con los AVISOS AL CELULAR encendidos")
print("=" * 70)
print(f"  Abre:  http://localhost:{PUERTO}")
print("")
print("  Entra con:   usuario recepcion    contraseña clavedepruebas2026")
print("")
print("  Dónde está el botón:")
print("    1. Entra a la pantalla AMENIDADES (el 🎁 del menú)")
print("    2. Debajo de los filtros verás la barra:  🔔 Avisos al celular")
print("    3. Toca «Activar en este aparato» y acepta el permiso del navegador")
print("    4. Ahí aparecen los botones «Probar» y «Desactivar aquí»")
print("")
print("  «Probar» manda un aviso de verdad, por los servidores de Google, y debería")
print("  salirte como notificación del sistema en unos segundos.")
print("")
print("  También puedes probar la fecha de las amenidades: la columna «Para el día»")
print("  con su selector, y en Restaurantes el botón «Elegir noche».")
print("")
print(f"  Los datos de esta prueba van en data-avisos/, aparte de todo lo demás.")
print("  Para cerrar, cierra esta ventana.")
print("=" * 70)
print("")

subprocess.run([sys.executable, os.path.join(AQUI, "backend", "launcher.py")],
               env=entorno, cwd=os.path.join(AQUI, "backend"))
