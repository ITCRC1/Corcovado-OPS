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

    # Dos problemas muy distintos, y se atienden en sitios distintos: una ruta mala se
    # corrige en el código; un bloque que Oracle no concede, no —por mucho que se
    # insista aquí—. Mezclarlos hace perder días buscando en el lado equivocado.
    if "REVISAR RUTA" in diag:
        print("HAY CAMPOS VACÍOS QUE SÍ DEBERÍAN LLEGAR.")
        print()
        print("El bloque que trae ese dato sí responde, así que en esta propiedad el")
        print("campo viene con otro nombre. Se arregla en el mapeo: comparta el archivo")
        print("estructura_*.txt de data/opera_muestras/ con quien lleva el sistema.")
        print()
        print("Ese archivo trae SOLO nombres y tipos de campo — ningún nombre de huésped")
        print("ni dato personal— así que se puede compartir sin problema. El otro archivo")
        print("de esa carpeta (reservas_*.json) SÍ trae datos de huéspedes: ese no.")
        print("-" * 78)
        return 0

    alcance = r.get("manda_en") or []
    tours = r.get("tours_en_la_muestra")
    sin_mapear = r.get("paquetes_sin_reconocer") or []

    if "REVISAR RUTA" in diag:
        print("HAY CAMPOS VACÍOS QUE SÍ DEBERÍAN LLEGAR.")
        print()
        print("Comparta el archivo estructura_*.txt de data/opera_muestras/ con quien")
        print("lleva el sistema: trae SOLO nombres y tipos de campo, ningún dato de")
        print("huésped. El otro archivo de esa carpeta (reservas_*.json) SÍ los trae.")
        print("-" * 78)
        return 0

    print("LA SINCRONIZACIÓN TRAE TODO LO QUE TRAE EL PDF.")
    print()
    print("De dónde sale cada cosa:")
    print("  Reservation Notes  -> el itinerario por día con su entrada del SINAC,")
    print("                        el punto de embarque (Sierpe/Drake) con vuelo y hora,")
    print("                        el rooming con pasaportes, las alergias y las")
    print("                        amenidades, y los vínculos de grupo")
    print("  Los paquetes       -> el régimen de comidas y qué tours están vendidos")
    print("  La reserva         -> huésped, fechas, habitación, pax, estado, agencia")
    print("                        y las CANCELACIONES")
    print()
    print(f"  ({tours} tours leídos en la muestra de esta corrida)")
    print()
    print("Es el MISMO texto que imprime el PDF, leído con el MISMO lector. Si una")
    print("reserva todavía no tiene los tours repartidos, aquí tampoco aparecerán —")
    print("igual que en el PDF, porque es la misma nota.")
    print()
    print(f"Opera manda en: {', '.join(alcance)}")
    print()
    print("DOS RESGUARDOS, por si algún día Opera deja de entregar algo:")
    print("  - Si no puede leer el itinerario de una reserva, NO borra los tours que")
    print("    ya tenga. No poder verlos no es lo mismo que no existir.")
    print("  - Si deja de entregar las notas, el sistema lo detecta y deja de mandar")
    print("    en esas áreas, en vez de vaciarlas.")
    print()
    if sin_mapear:
        print("OJO — paquetes que el sistema no supo interpretar:")
        for c in sin_mapear:
            print(f"  - {c}")
        print("No se adivinan: queda un aviso para que se agreguen al mapeo.")
        print()
    print("PARA ENCENDERLA, desde la pantalla Importar:")
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
