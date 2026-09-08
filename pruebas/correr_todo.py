"""Corre todas las suites, cada una en su propio proceso y su propia base.

POR QUÉ UN PROCESO POR SUITE. `init_db.DB_PATH` se calcula al importar el módulo, a
partir de HOTEL_DATA_DIR. Cambiarlo a mitad de un proceso no cambia la ruta que ya
quedó fijada, así que la única forma limpia de darle a cada suite su propia base es
arrancarla aparte con su propia carpeta.

Y hace falta de verdad: las suites se contaminan entre ellas. Una renombra un
restaurante, otra deja una reserva cancelada, otra agenda una cita. Corriendo en fila
sobre la misma carpeta salen fallos que no existen — ya pasó, y costó media hora
buscar una regresión que no estaba.

Uso:
    python pruebas/correr_todo.py            todas
    python pruebas/correr_todo.py carga      solo las que lleven 'carga' en el nombre
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)


def suites(filtro=None):
    nombres = sorted(f for f in os.listdir(AQUI)
                     if f.startswith("probar_") and f.endswith(".py"))
    if filtro:
        nombres = [n for n in nombres if filtro.lower() in n.lower()]
    return nombres


def correr(nombre):
    """Una suite, en su propio proceso, con una carpeta de datos recién creada."""
    carpeta = tempfile.mkdtemp(prefix="pruebas_cwl_")
    entorno = dict(os.environ)
    entorno["HOTEL_DATA_DIR"] = carpeta
    # Sin esto la salida del hijo llega en la página de códigos de Windows y los
    # acentos se ven como basura al recogerla.
    entorno["PYTHONIOENCODING"] = "utf-8"
    # El catálogo y el esquema salen del código, no de la carpeta de datos.
    entorno["HOTEL_RESOURCE_DIR"] = os.path.join(RAIZ, "backend")
    # Las credenciales de Opera NO se pasan: ninguna prueba debe salir a la red. Si
    # alguna lo intentara, es mejor que falle aquí que en el servidor del hotel.
    for clave in list(entorno):
        if clave.startswith("OPERA_"):
            entorno.pop(clave)

    comenzo = time.time()
    try:
        p = subprocess.run([sys.executable, os.path.join(AQUI, nombre)],
                           env=entorno, cwd=RAIZ, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return p.returncode, p.stdout, p.stderr, time.time() - comenzo
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else None
    nombres = suites(filtro)
    if not nombres:
        print("No hay suites que correr" + (f" con filtro {filtro!r}" if filtro else ""))
        return 1

    fallaron = []
    for nombre in nombres:
        codigo, salida, error, segundos = correr(nombre)
        print(salida.rstrip())
        if error.strip():
            print("  --- stderr ---")
            print("  " + error.strip().replace("\n", "\n  "))
        print(f"  ({segundos:.1f} s)\n")
        if codigo != 0:
            fallaron.append(nombre)

    print("=" * 60)
    if fallaron:
        print(f"FALLARON {len(fallaron)} de {len(nombres)} suites: {', '.join(fallaron)}")
    elif len(nombres) == 1:
        print("La suite paso.")
    else:
        print(f"Las {len(nombres)} suites pasaron.")
    print("=" * 60)
    return 1 if fallaron else 0


if __name__ == "__main__":
    sys.exit(main())
