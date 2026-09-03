"""
Asistente para conectar el sistema con Opera Cloud.

Se corre con doble clic en conectar_opera.bat, y hace en orden lo que hay que hacer:

  1. Si no hay credenciales, deja el archivo listo para rellenar y explica dónde está.
  2. Comprueba que autentican.
  3. Pregunta a Opera qué bloques de datos responde (uno por uno: si un módulo no está
     contratado, Oracle rechaza la petición ENTERA, así que probarlos juntos no dice
     cuál falla).
  4. Descarga unas reservas y dice, campo por campo, qué llegó y qué no.
  5. Muestra qué entraría al sistema. NO GUARDA NADA.

El paso 4 es el que importa: los nombres de campo de OHIP cambian entre propiedades, y
un campo vacío en TODAS las reservas significa ruta equivocada, no dato ausente. Eso no
da error —da una operación a la que le falta información— así que hay que verlo antes
de encender la sincronización, no después.

    python conectar_opera.py [dias]
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# En la consola de Windows, escribir un acento con la salida redirigida a un archivo
# revienta con UnicodeEncodeError, y entonces esto no imprime NADA — el peor resultado
# posible para algo cuyo trabajo es explicar qué pasó. Se fuerza UTF-8 y se reemplaza lo
# que no se pueda escribir, así en el peor caso sale un carácter raro y no un vacío.
for flujo in (sys.stdout, sys.stderr):
    try:
        flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DIAS = int(sys.argv[1]) if len(sys.argv) > 1 else 14


def titulo(n, texto):
    print()
    print("=" * 78)
    print(f"  PASO {n}. {texto}")
    print("=" * 78)


def main():
    import opera_cloud as oc

    titulo(1, "LAS CREDENCIALES")
    if oc.crear_plantilla_credenciales():
        print("Se creó el archivo donde van las credenciales:")
        print()
        print("   " + os.path.abspath(oc.RUTA_CREDENCIALES))
        print()
        print("Ábralo con el Bloc de notas, reemplace los huecos <...> por los valores")
        print("que le dio Oracle, guarde, y vuelva a correr esto.")
        print()
        print("Lo que no le hayan dado, déjelo como está.")
        return 1

    faltan = oc._faltantes()
    if faltan:
        print("Todavía faltan datos:")
        for f in faltan:
            print(f"   · {f}")
        print()
        print("Complételos en:")
        print("   " + os.path.abspath(oc.RUTA_CREDENCIALES))
        print()
        print("(Si alguno lo tiene puesto como variable de entorno, esa manda sobre el")
        print(" archivo y este aviso no debería salir.)")
        return 1

    if oc.DESDE_ARCHIVO:
        print(f"Leídas del archivo: {', '.join(oc.DESDE_ARCHIVO)}")
    print(f"Gateway:            {oc.BASE_URL}")
    print(f"Hotel:              {oc.HOTEL_ID}")
    print(f"Esquema:            {oc.tipo_de_autenticacion()}")
    print("Están todas las que hacen falta.")

    titulo(2, "AUTENTICACIÓN")
    try:
        oc.obtener_token()
    except oc.OperaError as e:
        print("NO AUTENTICA. Esto es lo que respondió Oracle:")
        print()
        print(e)
        print()
        print("Lo más común, en este orden:")
        print("  · Client ID o Client Secret mal copiados (un espacio al final cuenta)")
        print("  · App Key de otro entorno (pruebas contra producción)")
        print("  · Gateway URL de otro entorno")
        print("  · La aplicación todavía no está aprobada en OHIP")
        print("  · El esquema es 'password' y falta el usuario de integración")
        return 1
    print("AUTENTICA CORRECTAMENTE.")

    hoy = datetime.date.today()
    desde = hoy.isoformat()
    hasta = (hoy + datetime.timedelta(days=DIAS)).isoformat()

    titulo(3, f"QUÉ RESPONDE OPERA (llegadas del {desde} al {hasta})")
    try:
        oc.descubrir(desde, hasta)
    except oc.OperaError as e:
        print("La descarga falló:")
        print()
        print(e)
        print()
        texto = str(e)
        if "not authorized" in texto or "OPERAWS-GEN0124" in texto or "GEN01265" in texto:
            # Este caso merece su propio mensaje: autentica pero no puede LEER, y eso no
            # se arregla tocando el sistema. Sin decirlo, uno se pasa la tarde revisando
            # credenciales que estaban bien.
            print("ESTO NO SE ARREGLA DESDE AQUÍ.")
            print()
            print("Oracle está diciendo que la aplicación autentica pero que el usuario")
            print("de integración NO tiene permiso para leer los datos de la propiedad.")
            print("Es un permiso que se concede en Opera/OHIP, no en este sistema.")
            print()
            print("Hay que pedirle a Oracle o al administrador de Opera:")
            print("  1. Asignarle la propiedad al usuario de integración")
            print("  2. Darle a su rol las tareas de lectura de reservas")
            print("  3. Suscribir la aplicación a esa propiedad en OHIP")
            print()
            print("Cíteles el código de error que aparece arriba: lo pueden buscar.")
        else:
            print("Si dice que el hotel no existe, revise OPERA_HOTEL_ID: es el código")
            print("de la propiedad en Opera, no su nombre.")
        return 1

    titulo(4, "QUÉ ENTRARÍA AL SISTEMA (no se guarda nada)")
    import opera_sync
    r = opera_sync.sincronizar(cargar=False)
    if r.get("estado") != "VISTA_PREVIA":
        print(r)
        return 1
    print(r.get("diagnostico") or "")
    print()
    print("-" * 78)
    diag = r.get("diagnostico") or ""
    if "REVISAR RUTA" in diag:
        print("HAY CAMPOS QUE LLEGAN VACÍOS EN TODAS LAS RESERVAS.")
        print()
        print("Eso casi siempre significa que en esta propiedad ese dato viene con otro")
        print("nombre. NO encienda la sincronización todavía: comparta el archivo")
        print("estructura_*.txt de data/opera_muestras/ con quien lleva el sistema.")
        print()
        print("Ese archivo trae SOLO nombres y tipos de campo — ningún nombre de huésped")
        print("ni dato personal— así que se puede compartir sin problema. El otro archivo")
        print("de esa carpeta (reservas_*.json) SÍ trae datos de huéspedes: ese no.")
    else:
        print("TODO LLEGA COMPLETO.")
        print()
        print("Ya se puede encender desde la pantalla Importar PDF:")
        print("  1. «Sincronizar ahora» una vez")
        print("  2. Revisar la Agenda y las Amenidades del día contra lo que ya sabe")
        print("  3. «Encender la sincronización»")
        print()
        print("El PDF sigue funcionando igual: son dos caminos al mismo sitio.")
    print("-" * 78)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(1)
