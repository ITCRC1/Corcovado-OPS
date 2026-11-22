"""De donde entra y por donde sale cada huesped, leido de la nota de la reserva.

Mandar un bote al lugar equivocado, o a la hora equivocada, es de los errores mas caros
que puede cometer el sistema: el huesped se queda en un muelle sin senal. Por eso lo que
no se reconoce NO se adivina, se marca como pendiente y lo resuelve recepcion.

Los textos de aqui son REALES, copiados de las notas de Opera del lodge. Importa: las
formas que usa Reservaciones no son las que uno inventaria —«INGRESO: PTE», «Entrada:»
vacia, «Recogerlos en Punta Marenco 03:00 pm»— y son justo las que rompian el lector.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: F401  (fija la ruta de backend/)

import pdf_parser as pp


def _leer(texto):
    return pp.leer_texto_de_reserva(texto)


# ---------------------------------------------------------------------------
# Lo que se reconoce bien
# ---------------------------------------------------------------------------

def los_dos_puntos_se_leen_de_la_nota(c):
    d = _leer("CPL Paquete 2N/3D+Pension completa\nPNC\n"
              "Entrada: Via Sierpe ocupan parqueo\nSalida: Via Sierpe\n"
              "--------\nRooming:\nAlexander Mcintosch")
    c.igual(d["punto_entrada"], "Sierpe", "entra por Sierpe")
    c.igual(d["punto_salida"], "Sierpe", "y sale por Sierpe")
    c.igual(d["punto_entrada_sin_confirmar"], None, "sin nada pendiente")


def la_entrada_y_la_salida_pueden_ser_distintas(c):
    """Caso real: llega en avioneta a Drake y sale por Sierpe con transporte terrestre."""
    d = _leer("PAQUETE 4D/3N+PENSION COMPLETA\nBT INCLUDED\n"
              "INGRESO: DRAKE - Sansa Flight #1116 @ 09:00\n"
              "SALIDA: SIERPE - TIENEN TT DE SIERPE A HOTEL DEL MAR EN JACO\n")
    c.igual(d["punto_entrada"], "Drake", "entra por Drake")
    c.igual(d["punto_salida"], "Sierpe", "y sale por Sierpe")


def cada_hora_es_la_de_su_propio_campo(c):
    """El fallo: la hora se buscaba en la LINEA entera. En una nota escrita seguida, la
    linea lleva las dos horas y las dos se leian como la primera, asi que el bote de
    salida se apartaba para la hora de llegada."""
    seguido = ("PAQUETE 4D/3N+FULL BOARD PNC+C-CIS C-BT ----------------------------- "
               "INGRESO: Drake Bay (DRK) Sansa 2:45 PM "
               "SALIDA: Drake Bay (DRK) Sansa 9:25 AM "
               "----------------------------- ROOMING: SANDRA HOWARD")
    d = _leer(seguido)
    c.igual(d["punto_entrada"], "Drake", "el punto de entrada se lee igual")
    c.igual(d["punto_salida"], "Drake", "y el de salida")
    c.igual(d["hora_vuelo_entrada"], "2:45 p.m.", "llega a las 2:45 p.m.")
    c.igual(d["hora_vuelo_salida"], "9:25 a.m.", "y SALE a las 9:25 a.m., no a las 2:45")

    # En varias lineas, que es como llega hoy de Opera, tiene que dar lo mismo.
    en_lineas = _leer("INGRESO: Drake Bay (DRK) Sansa 2:45 PM\n"
                      "SALIDA: Drake Bay (DRK) Sansa  9:25 AM\n")
    c.igual(en_lineas["hora_vuelo_entrada"], "2:45 p.m.", "igual en varias lineas")
    c.igual(en_lineas["hora_vuelo_salida"], "9:25 a.m.", "igual en varias lineas")


def la_hora_pegada_al_numero_de_vuelo_se_lee(c):
    """Lo reporto el lodge con la hab 07 del 4 de noviembre: la nota dice
    «Entrada: Via Drake RZ1116 9:15» —la hora va pegada al numero de vuelo y SIN la marca
    a.m./p.m.— y la hora no entraba. El vuelo si, la hora no.

    La causa era un guardia de mas: se preguntaba por HORA_RE, que exige la marca, antes
    de llamar al convertidor, que si entiende las dos formas. Asi que la hora se tiraba
    en la puerta y en la hoja de traslados ese huesped salia sin hora: nadie sabia a que
    hora mandar el bote."""
    d = _leer("Entrada: Via Drake RZ1116 9:15\n"
              "Salida: Via Drake RZ1116 9:25\n")
    c.igual(d["vuelo_entrada"], "RZ1116", "el vuelo de entrada se lee")
    c.igual(d["vuelo_salida"], "RZ1116", "y el de salida")
    c.igual(d["hora_vuelo_entrada"], "9:15 a.m.", "y AHORA tambien la hora de entrada")
    c.igual(d["hora_vuelo_salida"], "9:25 a.m.", "y la de salida, que es otra")
    c.igual(d["punto_entrada"], "Drake", "sin perder el punto")

    # Las horas de la tarde sin marca siguen leyendose como tarde.
    t = _leer("Entrada: Via Drake RZ1140 2:45\nSalida: Via Sierpe RZ1150 15:30\n")
    c.igual(t["hora_vuelo_entrada"], "2:45 p.m.", "2:45 sin marca es de la tarde")
    c.igual(t["hora_vuelo_salida"], "3:30 p.m.", "y 15:30 se convierte a 12 horas")

    # Y una linea sin hora no se inventa una.
    s = _leer("Entrada: Via Sierpe\nSalida: Via Sierpe\n")
    c.igual(s["hora_vuelo_entrada"], None, "sin hora escrita no se inventa")
    c.igual(s["hora_vuelo_salida"], None, "ni la de salida")


# ---------------------------------------------------------------------------
# Lo que queda pendiente. No se adivina.
# ---------------------------------------------------------------------------

def copa_de_arbol_es_una_recogida_de_drake(c):
    """Misma decision que Punta Marenco: es otro lodge de la costa, en la ruta del bote
    de Drake. Lo reporto el lodge con la hab 04 del 7 de noviembre, cuya nota dice
    «Entrada: RECOGER EN COPA DEL ARBOL RESORT A LAS 14:30H» y quedaba sin punto.

    La nota real tiene las dos cosas a la vez, y es lo que hace valioso el caso: la
    ENTRADA es por Copa del Arbol y la SALIDA dice «VIA SIERPE». Si el lector se
    confundiera, mandaria el bote de Sierpe a recoger a alguien que esta en la costa de
    Drake."""
    real = ("CPL PAQUETE 2N/3D+FULL BOARD\n"
            "C-PNC\n"
            "Entrada: RECOGER EN COPA DEL ARBOL RESORT A LAS 14:30H\n"
            "Salida: VIA SIERPE dejarla en el muelle de Aguila de Osa en Sierpe a las "
            "09:30h ya que el auto rentado lo dejaria en el parqueo de ellos\n"
            "----------------------------\n"
            "Rooming:\n\nVenetia Fremlin-Key 159148049\n")
    d = _leer(real)
    c.igual(d["punto_entrada"], "Drake", "la entrada por Copa del Arbol es Drake")
    c.igual(d["punto_salida"], "Sierpe", "y la salida sigue siendo Sierpe")
    c.igual(d["punto_entrada_sin_confirmar"], None,
            "ya no queda pendiente de que alguien lo decida")

    # Las dos formas de escribirlo, y sin acentos.
    for frase in ("Copa de Arbol", "COPA DEL ARBOL RESORT", "Copa de Árbol"):
        c.igual(pp.punto_de(frase), "Drake", f"«{frase}» es Drake")


def punta_marenco_es_una_recogida_de_drake(c):
    """Decision de operacion: el bote que recoge en Punta Marenco es el de Drake. Es un
    punto de RECOGIDA, no un punto de embarque aparte. Antes quedaba pendiente y
    recepcion tenia que resolver a mano las tres habitaciones del mismo grupo."""
    d = _leer("Reserva CPL de inspeccion\n"
              "Entrada: Recogerlos en Punta Marenco 03:00 pm\n"
              "Salida: Via Drake drop off en playa agujitas salida 07:30 am desde el hotel\n")
    c.igual(d["punto_entrada"], "Drake", "entra por Drake")
    c.igual(d["punto_entrada_sin_confirmar"], None, "y ya no queda pendiente")
    c.igual(d["punto_salida"], "Drake", "la salida tambien")
    c.igual(d["hora_vuelo_entrada"], "3:00 p.m.", "con la hora de la recogida")
    c.igual(d["hora_vuelo_salida"], "7:30 a.m.", "y la de salida es la suya, no la otra")


def el_punto_no_tiene_que_ser_la_primera_palabra(c):
    """Se leia solo la primera palabra del valor, asi que «Recogerlos en Punta Marenco» o
    «drop off en playa agujitas» quedaban pendientes aunque nombraran el sitio."""
    for texto, espera in (("Recogerlos en Punta Marenco", "Drake"),
                          ("drop off en playa agujitas", "Drake"),
                          ("Drake Bay (DRK) Sansa 2:45 PM", "Drake"),
                          ("Via Sierpe ocupan parqueo", "Sierpe")):
        c.igual(pp.punto_de(texto), espera, f"«{texto}» es {espera}")


def dos_puntos_distintos_no_se_deciden_solos(c):
    """Si la frase nombra los dos, no hay una respuesta: hay un texto que alguien tiene
    que leer. Mandar el bote por suposicion es el error caro."""
    c.igual(pp.punto_de("no por Sierpe, finalmente por Drake"), None,
            "con dos puntos distintos no se elige")
    d = _leer("Entrada: cambio de Sierpe a Drake, confirmar con la agencia\n")
    c.igual(d["punto_entrada"], None, "queda sin confirmar")
    c.cierto(d["punto_entrada_sin_confirmar"], "y con el texto a la vista")


def la_hora_sirve_aunque_el_punto_no_se_reconozca(c):
    """Era lo que mas costaba: de un texto con hora pero sin punto reconocido, el sistema
    se quedaba con el texto y TIRABA la hora, asi que recepcion tenia que volver a abrir
    Opera para leer una hora que el sistema ya habia leido."""
    d = _leer("Entrada: Recogerlos en el muelle viejo 03:00 pm\n"
              "Salida: lo confirma la agencia, sale 07:30 am\n")
    c.igual(d["punto_entrada"], None, "el punto sigue sin confirmarse")
    c.igual(d["hora_vuelo_entrada"], "3:00 p.m.", "pero la hora se conserva")
    c.igual(d["hora_vuelo_salida"], "7:30 a.m.", "y la de salida es la suya, no la otra")


def el_campo_vacio_se_marca_como_vacio(c):
    """«Entrada:» sin nada detras es pendiente de verdad: Reservaciones todavia no lo
    sabe. Tiene que decirlo asi y no quedar en blanco, que se confunde con no leido."""
    d = _leer("cpl autorizado por isaac\nEntrada:\nSalida:\n--------\nRooming:\nKemly")
    c.igual(d["punto_entrada_sin_confirmar"], "(vacío en la reserva)",
            "dice que la reserva lo trae vacio")
    c.igual(d["punto_salida_sin_confirmar"], "(vacío en la reserva)", "las dos")
    c.cierto("PDF" not in (d["punto_entrada_sin_confirmar"] or ""),
             "y no habla de un PDF: hoy esto viene de Opera")


def el_pte_se_guarda_limpio(c):
    """«PTE» es como Reservaciones escribe «pendiente». El valor que ve recepcion tiene
    que ser eso y no el resto de la nota arrastrado detras."""
    d = _leer("PAQUETE 4D/3N+PENSION COMPLETA CPL\nC-BT+C-CIS+C-NGW\n"
              "------------------------------\nINGRESO: PTE\nSALIDA: PTE\n"
              "-----------------------------\nROOMING: PAM CRUSE")
    c.igual(d["punto_entrada_sin_confirmar"], "PTE", "entrada pendiente, y solo eso")
    c.igual(d["punto_salida_sin_confirmar"], "PTE", "salida pendiente, y solo eso")


def el_valor_no_se_come_el_resto_de_la_nota(c):
    """Escrito seguido, «Entrada:» llegaba hasta el final del texto y recepcion veia un
    parrafo entero donde tendria que ver un lugar."""
    d = _leer("INGRESO: PTE SALIDA: PTE ----------------------------- ROOMING: PAM CRUSE")
    c.igual(d["punto_entrada_sin_confirmar"], "PTE",
            "el valor se corta en el rotulo siguiente")
    c.cierto("ROOMING" not in (d["punto_entrada_sin_confirmar"] or ""),
             "y no arrastra el rooming")


def una_linea_de_salida_no_cuenta_como_entrada(c):
    """«SALIDA:» contiene «IDA» y otras trampas parecidas; la entrada solo se lee de una
    linea que sea de entrada."""
    d = _leer("SALIDA: Via Sierpe\n")
    c.igual(d["punto_salida"], "Sierpe", "la salida se lee")
    c.igual(d["punto_entrada"], None, "y no se confunde con una entrada")


# ---------------------------------------------------------------------------
# Las formas en que de verdad se escribe una hora
# ---------------------------------------------------------------------------
# TODAS ESTAS SON REALES, sacadas de las notas de Opera del lodge. Se midió: de once
# reservas vivas que tenian numero de vuelo y NINGUNA hora, las once la traian escrita
# —solo que de once maneras distintas—. Y el fallo era mudo: la reserva se veia completa,
# el traslado no se podia calcular y en la hoja del dia quedaba una casilla vacia.
#
# El que lo destapo: «Salida: Via Drake Sansa RZ1069 @2: 45 PM», con un espacio DENTRO
# de la hora.
HORAS_REALES = [
    ("Salida: Via Drake Sansa RZ1069 @2: 45 PM", "salida", "2:45 p.m."),
    ("Entrada: Via Drake Sansa RZ1068 @3:50 PM", "entrada", "3:50 p.m."),
    ("Salida: Via Drake SANSA Flight RZ1118 a las 11: 00 a.m", "salida", "11:00 a.m."),
    ("ENTRADA: VIA DRAKE RZ1070  12:50hrs", "entrada", "12:50 p.m."),
    ("Salida: Vía Drake RZ5751 departing at 13:25hrs", "salida", "1:25 p.m."),
    # La hora EN PUNTO, sin minutos: seis de las once venian asi.
    ("Entrada: Via Drake RZ1068 9am", "entrada", "9:00 a.m."),
    ("Salida: Drake rz 1071 1 pm", "salida", "1:00 p.m."),
    ("SALIDA:  Via Drake RZ1070 1PM", "salida", "1:00 p.m."),
    ("Salida: Via Drake RZ1071  13hrs", "salida", "1:00 p.m."),
    ("Salida: Via Drake RZ 1071 13h", "salida", "1:00 p.m."),
    ("SALIDA: Via Drake Sansa @RZ1071 1PM", "salida", "1:00 p.m."),
    ("Entrada: RECOGER EN Aguila de Osa Lodge a las 14:30h", "entrada", "2:30 p.m."),
]


def la_hora_se_lee_aunque_este_mal_escrita(c):
    for texto, lado, esperada in HORAS_REALES:
        d = _leer(texto + "\n")
        c.igual(d[f"hora_vuelo_{lado}"], esperada, f"«{texto[-22:]}» -> {esperada}")


def con_minutos_manda_la_hora_con_minutos(c):
    """El orden de los intentos es lo que decide esto: «12:50hrs» son las 12:50, no las
    12 en punto. Al agregar la hora en punto es justo lo que se puede romper."""
    c.igual(_leer("ENTRADA: Via Drake RZ1070 12:50hrs\n")["hora_vuelo_entrada"],
            "12:50 p.m.", "12:50hrs son las 12:50")
    c.igual(_leer("Salida: Via Drake RZ5751 13:25hrs\n")["hora_vuelo_salida"],
            "1:25 p.m.", "13:25hrs son la 1:25")


def lo_que_NO_es_una_hora_no_se_inventa(c):
    """La contraparte, que es la que evita pasarse: leer una hora donde no la hay manda
    un bote a una hora que nadie escribio, y eso es peor que no leerla."""
    for texto in ("se agrega adicional Sirena $772.92 facturar a la agencia",
                  "Monto total: $1,556.18",
                  "Salida: Via Drake RZ1069",
                  "(5 HOURS TOUR)",
                  "Hike 3 hours"):
        c.igual(pp.normalizar_hora(texto), None, f"«{texto[:34]}» no es una hora")


# ---------------------------------------------------------------------------
# Cuando recepcion corrige el punto
# ---------------------------------------------------------------------------
#
# EL CASO: la hab 13 del 18 de noviembre. El lodge sabia que ese huesped entraba por
# Sierpe y la pantalla decia Drake. Dos cosas faltaban:
#
#   1. El punto solo se podia elegir en «Pendientes de confirmar», o sea unicamente
#      cuando la reserva no lo decia. Si venia puesto y estaba mal, no habia donde
#      tocarlo.
#   2. Aunque se hubiera podido, el transporte es un area que Opera manda y el ciclo la
#      reescribe cada media hora: la correccion se habria deshecho sola, sin que nadie
#      tocara nada. Esa es la peor forma de fallar —el dato se arregla, se comprueba, y
#      vuelve a estar mal al rato— porque quien lo corrigio ya no esta mirando.

HOY = __import__("datetime").date.today()
USUARIO = {"usuario": "pruebas", "rol": "ADMIN"}


def _ddmmyy(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def _lote_de_opera(punto_entrada=None, pendiente=None, conf=880001, room="13"):
    """Una reserva como la entrega Opera, con su punto de entrada (o sin el)."""
    import datetime
    r = dict(comun.reserva(conf, room, _ddmmyy(HOY),
                           _ddmmyy(HOY + datetime.timedelta(days=3))),
             punto_entrada=punto_entrada,
             punto_entrada_sin_confirmar=pendiente)
    return [r]


def recepcion_puede_corregir_un_punto_que_ya_venia_puesto(c):
    """Lo que no se podia hacer: la reserva decia Drake y no habia donde cambiarlo."""
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada="Drake")
    comun.cargar(lote, vistas=lote)
    import main

    main.confirmar_transporte("880001", "entrada", "Sierpe", user=USUARIO)

    conn = comun.conexion()
    f = dict(conn.execute("SELECT * FROM reserva WHERE conf_no='880001'").fetchone())
    c.igual(f["punto_entrada"], "Sierpe", "queda por donde dijo recepcion")
    c.igual(f["punto_entrada_a_mano"], 1, "y marcado como puesto a mano")
    conn.close()


def la_sincronizacion_no_se_lleva_lo_que_puso_recepcion(c):
    """EL FALLO DE FONDO. Opera vuelve a pasar cada media hora con el mismo Drake."""
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada="Drake")
    comun.cargar(lote, vistas=lote)
    import main
    main.confirmar_transporte("880001", "entrada", "Sierpe", user=USUARIO)

    # El ciclo siguiente, con exactamente lo mismo que trae Opera.
    comun.cargar(lote, vistas=lote)

    conn = comun.conexion()
    f = dict(conn.execute("SELECT * FROM reserva WHERE conf_no='880001'").fetchone())
    c.igual(f["punto_entrada"], "Sierpe", "sigue siendo Sierpe tras sincronizar")
    c.igual(f["punto_entrada_a_mano"], 1, "y la marca sigue puesta")

    # Y tampoco si Opera deja de decir el punto y manda un texto que no se entiende:
    # escribir None encima seria perder la correccion de otra manera.
    sin_punto = _lote_de_opera(punto_entrada=None, pendiente="TRB")
    comun.cargar(sin_punto, vistas=sin_punto)
    f = dict(conn.execute("SELECT * FROM reserva WHERE conf_no='880001'").fetchone())
    c.igual(f["punto_entrada"], "Sierpe", "ni cuando la reserva deja de decirlo")
    c.igual(f["punto_entrada_sin_confirmar"], None,
            "y no vuelve a quedar pendiente de confirmar")
    c.igual([a for a in comun.alertas(conn, "TRANSPORTE_SIN_CONFIRMAR")], [],
            "ni vuelve el aviso de confirmarlo")
    conn.close()


def si_la_reserva_pasa_a_decir_otra_cosa_se_avisa(c):
    """La otra cara de respetar lo que puso recepcion.

    Si manana la reserva dice Drake porque el huesped acabo comprando el vuelo, el
    sistema sigue respetando el Sierpe que se fijo —y hace bien— pero callarselo dejaria
    a alguien esperando en el muelle equivocado con la pantalla diciendo que todo esta
    en orden.
    """
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada="Sierpe")
    comun.cargar(lote, vistas=lote)
    import main
    main.confirmar_transporte("880001", "entrada", "Sierpe", user=USUARIO)

    conn = comun.conexion()
    c.igual(comun.alertas(conn, "PUNTO_A_MANO_DISTINTO"), [],
            "mientras dicen lo mismo no se avisa nada")
    conn.close()

    cambio = _lote_de_opera(punto_entrada="Drake")
    comun.cargar(cambio, vistas=cambio)

    conn = comun.conexion()
    avisos = comun.alertas(conn, "PUNTO_A_MANO_DISTINTO")
    c.igual(len(avisos), 1, "cuando la reserva cambia, se avisa")
    c.cierto("Drake" in avisos[0] and "Sierpe" in avisos[0],
             "diciendo las dos: lo que dice la reserva y lo que esta fijado")
    f = dict(conn.execute("SELECT * FROM reserva WHERE conf_no='880001'").fetchone())
    c.igual(f["punto_entrada"], "Sierpe", "y el punto sigue siendo el de recepcion")
    conn.close()

    # El ciclo corre cada media hora: el aviso no se puede multiplicar.
    comun.cargar(cambio, vistas=cambio)
    comun.cargar(cambio, vistas=cambio)
    conn = comun.conexion()
    c.igual(len(comun.alertas(conn, "PUNTO_A_MANO_DISTINTO")), 1,
            "y sigue siendo uno solo tras tres ciclos")

    # Y si recepcion suelta la marca, el aviso se retira.
    main.confirmar_transporte("880001", "entrada", "automatico", user=USUARIO)
    conn.close()
    comun.cargar(cambio, vistas=cambio)
    conn = comun.conexion()
    c.igual(comun.alertas(conn, "PUNTO_A_MANO_DISTINTO"), [],
            "al soltar la marca el aviso se va")
    conn.close()


def una_reimportacion_del_pdf_tampoco_la_deshace(c):
    """El otro camino de escritura: el PDF reescribe la fila entera."""
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada="Drake")
    comun.cargar(lote, vistas=lote)
    import main
    main.confirmar_transporte("880001", "entrada", "Sierpe", user=USUARIO)

    comun.cargar(lote, vistas=lote, manda_en="TODO", fuente="Arrivals.PDF")

    conn = comun.conexion()
    f = dict(conn.execute("SELECT * FROM reserva WHERE conf_no='880001'").fetchone())
    c.igual(f["punto_entrada"], "Sierpe", "el reporte no deshace la correccion")
    c.igual(f["punto_entrada_a_mano"], 1, "y la marca sobrevive al REPLACE")
    conn.close()


def se_puede_devolver_el_mando_a_la_reserva(c):
    """Para que corregir no sea una puerta de un solo sentido: si el huesped acaba
    viniendo por donde decia la reserva, se suelta la marca."""
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada="Drake")
    comun.cargar(lote, vistas=lote)
    import main
    main.confirmar_transporte("880001", "entrada", "Sierpe", user=USUARIO)
    main.confirmar_transporte("880001", "entrada", "automatico", user=USUARIO)

    conn = comun.conexion()
    f = dict(conn.execute("SELECT * FROM reserva WHERE conf_no='880001'").fetchone())
    c.igual(f["punto_entrada_a_mano"], 0, "la marca se suelta")
    c.igual(f["punto_entrada"], "Sierpe",
            "y el valor se queda hasta que la fuente lo reescriba")

    comun.cargar(lote, vistas=lote)
    f = dict(conn.execute("SELECT * FROM reserva WHERE conf_no='880001'").fetchone())
    c.igual(f["punto_entrada"], "Drake", "el ciclo siguiente vuelve a mandar")
    conn.close()


def confirmar_una_habitacion_no_cierra_los_avisos_de_las_demas(c):
    """El filtro del aviso era solo «%de entrada de%»: confirmar UNA habitacion resolvia
    de golpe el aviso de todas. Recepcion dejaba de ver puntos sin confirmar y no habia
    forma de notarlo."""
    conn = comun.base_limpia()
    conn.close()
    lote = (_lote_de_opera(pendiente="PTE", conf=880001, room="13")
            + _lote_de_opera(pendiente="(vacio en la reserva)", conf=880002, room="14"))
    comun.cargar(lote, vistas=lote)

    conn = comun.conexion()
    c.igual(len(comun.alertas(conn, "TRANSPORTE_SIN_CONFIRMAR")), 2,
            "las dos quedan pendientes")
    conn.close()

    import main
    main.confirmar_transporte("880001", "entrada", "Sierpe", user=USUARIO)

    conn = comun.conexion()
    quedan = comun.alertas(conn, "TRANSPORTE_SIN_CONFIRMAR")
    c.igual(len(quedan), 1, "se cierra solo el de la habitacion confirmada")
    c.cierto(all("880001" not in a for a in quedan), "y es el de la otra el que queda")
    conn.close()


def un_punto_que_no_existe_no_se_guarda(c):
    from fastapi import HTTPException
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada="Drake")
    comun.cargar(lote, vistas=lote)
    import main
    for tipo, punto in (("entrada", "Palmar"), ("llegada", "Sierpe")):
        try:
            main.confirmar_transporte("880001", tipo, punto, user=USUARIO)
            c.cierto(False, f"«{tipo}/{punto}» tenia que dar 400")
        except HTTPException as e:
            c.igual(e.status_code, 400, f"«{tipo}/{punto}» da 400")
    try:
        main.confirmar_transporte("999999", "entrada", "Sierpe", user=USUARIO)
        c.cierto(False, "una reserva que no existe tenia que dar 404")
    except HTTPException as e:
        c.igual(e.status_code, 404, "y una reserva inexistente, 404")


def un_cambio_de_habitacion_no_pide_confirmar_un_muelle(c):
    """LO REPORTO EL LODGE: «estas notas que aparecen en transporte no corresponden ahi,
    se refiere a cambios de habitacion».

    El lodge escribe la mudanza en el MISMO campo donde va el punto, porque ahi es donde
    se escribe lo que pasa ese dia. Las tres notas de abajo son REALES, leidas de Opera:

        Entrada: In house se pasan de treehouse a agujas  rsvs 597482971 y 597484019
        Salida:  Se pasan el 24/11 a Agujas room rsv 597370448

    El lector hacia lo correcto —no reconocia Sierpe ni Drake— y lo dejaba «pendiente de
    confirmar». Pero no hay nada que confirmar: ese huesped no coge ningun bote, se muda
    de cuarto. Pidiendolo, la lista de pendientes se llena de cosas que NO SE PUEDEN
    CERRAR, y una lista asi se deja de mirar — que es justo lo que ya le paso a esta
    pantalla con las de diciembre.
    """
    import pdf_parser as pp

    SI = ["In house se pasan de treehouse a agujas  rsvs 597482971 y 597484019",
          "Se pasan el 24/11 a Agujas room rsv 597370448",
          "CLIENTES In house se pasan de TH a Agujas",
          "Se cambian de habitacion el 25"]
    for texto in SI:
        c.igual(pp.es_un_cambio_de_habitacion(texto), True,
                f"es una mudanza: «{texto[:46]}»")

    # LO QUE NO ES UNA MUDANZA SIGUE PIDIENDO CONFIRMACION. Si esto se pasara de listo,
    # el sistema dejaria de pedir el punto de alguien que SI viaja — y eso es un bote
    # que no se manda.
    NO = ["Via Drake RZ1118 11:00AM", "Recogerlos en Punta Marenco 03:00 pm", "PTE",
          "(vacío en la reserva)", "Aguila de Osa 10 am", "TRB", ""]
    for texto in NO:
        c.igual(pp.es_un_cambio_de_habitacion(texto), False,
                f"NO es una mudanza: «{texto[:46]}»")
    c.igual(pp.es_un_cambio_de_habitacion(None), False, "ni la falta de texto")


def la_mudanza_no_sale_en_pendientes_ni_genera_aviso(c):
    """El camino completo: ni en la lista de Transporte ni como alerta.

    Probar solo es_un_cambio_de_habitacion se detendria en el primer paso: la lista y el
    aviso los arma cada uno su propio SQL, y los dos tenian que aprender lo mismo.
    """
    import datetime
    import main

    conn = comun.base_limpia()
    ayer = HOY - datetime.timedelta(days=3)

    def reserva(conf, hab, llega, sale, p_ent, p_sal, t_ent=None, t_sal=None):
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                    dep_date, adl, chl, rooms, res_status,
                                    punto_entrada, punto_salida,
                                    punto_entrada_sin_confirmar,
                                    punto_salida_sin_confirmar)
               VALUES (?,?,?,?,?,2,0,1,'EN CASA',?,?,?,?)""",
            (conf, hab, f"Murray/{conf}", _ddmmyy(llega), _ddmmyy(sale),
             p_ent, p_sal, t_ent, t_sal))

    # Las tres de la foto: dos que «salen» hoy a otra habitacion y una que «entra».
    reserva("870001", "21", ayer, HOY, "Drake", None,
            t_sal="Se pasan el 24/11 a Agujas room rsv 597370448")
    reserva("870002", "22", ayer, HOY, "Drake", None,
            t_sal="Se pasan el 24/11 a Agujas room rsv 597370448")
    reserva("870003", "11", HOY, HOY + datetime.timedelta(days=3), None, "Drake",
            t_ent="In house se pasan de treehouse a agujas rsvs 597482971 y 597484019")
    # Y una que SI necesita que alguien decida.
    reserva("870004", "18", ayer, HOY, "Drake", None, t_sal="Aguila de Osa 10 am")
    conn.commit()
    conn.close()

    pendientes = main.transporte_pendientes(fecha=HOY.isoformat(), user=USUARIO)
    confs = {p["conf_no"] for p in pendientes}
    c.cierto("870004" in confs, "la que de verdad hay que confirmar sigue saliendo")
    for conf in ("870001", "870002", "870003"):
        c.cierto(conf not in confs, f"la mudanza {conf} YA no pide confirmacion")

    # Y la pantalla de Transporte lo dice en vez de poner «sin definir».
    d = main.transporte(fecha=HOY.isoformat(), user=USUARIO)
    suya = [x for x in d["salidas"] if x["conf_no"] == "870001"][0]
    c.igual(suya["cambio_de_habitacion"], True,
            "la fila sabe que ese dia no viaja, se muda")
    otra = [x for x in d["salidas"] if x["conf_no"] == "870004"][0]
    c.igual(otra["cambio_de_habitacion"], False, "y la que viaja, no")


def el_aviso_de_confirmar_no_salta_por_una_mudanza(c):
    """La otra mitad: la alerta. Un aviso que no se puede cerrar enseña a no mirar los
    avisos, y este saltaba en cada carga."""
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada=None,
                          pendiente="In house se pasan de treehouse a agujas rsvs 1 y 2")
    comun.cargar(lote, vistas=lote)

    conn = comun.conexion()
    avisos = [dict(a)["mensaje"] for a in conn.execute(
        "SELECT mensaje FROM alerta WHERE tipo = 'TRANSPORTE_SIN_CONFIRMAR' "
        "AND resuelto = 0")]
    conn.close()
    c.igual(avisos, [], "una mudanza no genera aviso de confirmar el punto")

    # Y lo que SI hay que confirmar sigue avisando.
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada=None, pendiente="Aguila de Osa 10 am")
    comun.cargar(lote, vistas=lote)
    conn = comun.conexion()
    cuantos = conn.execute(
        "SELECT COUNT(*) FROM alerta WHERE tipo = 'TRANSPORTE_SIN_CONFIRMAR' "
        "AND resuelto = 0").fetchone()[0]
    conn.close()
    c.igual(cuantos, 1, "lo que no es una mudanza sigue pidiendo confirmacion")


def la_hoja_del_dia_no_pone_en_drake_lo_que_no_sabe(c):
    """LO REPORTO EL LODGE con una reserva que en Opera dice «Entrada: Sierpe / Salida:
    Sierpe» y en la hoja del dia salia en la columna DRAKE.

    La hoja repartia asi: «la columna SIERPE si el punto empieza por sierpe, y si no, la
    de DRAKE». El resumen agrupa bajo «Sin definir» a las reservas cuyo punto el sistema
    NO SABE, y ese grupo no empieza por sierpe: su pax se imprimia en DRAKE con la misma
    seguridad que los demas.

    Es el error caro de este sistema puesto en papel —el bote va a la pista y el huesped
    espera en el muelle— y falla en silencio: esa hoja no se distingue de una correcta.
    Es ademas el MISMO fallo que ya estaba arreglado en el itinerario del huesped (ver
    sin_punto_el_itinerario_no_promete_sierpe), solo que aqui elegia el otro muelle.

    Medido sobre la base del lodge: 50 reservas vivas no tienen punto de entrada y 50 no
    tienen el de salida. Todas se imprimian bajo DRAKE el dia que se mueven.
    """
    import datetime
    import main
    import hoja_dia as hd

    conn = comun.base_limpia()
    ayer = HOY - datetime.timedelta(days=3)

    def reserva(conf, hab, p_ent, p_sal, pax=2):
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                    dep_date, adl, chl, rooms, res_status,
                                    punto_entrada, punto_salida)
               VALUES (?,?,?,?,?,?,0,1,'POR INGRESAR',?,?)""",
            (conf, hab, f"Prueba/{conf}", _ddmmyy(ayer), _ddmmyy(HOY), pax, p_ent, p_sal))

    reserva("880101", "03", None, None, pax=1)        # la de la foto: no se sabe
    reserva("880102", "02", "Sierpe", "Sierpe", pax=2)
    conn.commit()
    conn.close()

    resumen = main._datos_del_resumen(HOY.isoformat())
    conn = comun.conexion()
    d = hd.definicion(conn, HOY.isoformat(), resumen)
    conn.close()
    filas = {f["hab"]: f for f in d["filas"]}

    c.igual((filas["03"]["sierpe"], filas["03"]["drake"]), ("", ""),
            "sin muelle conocido, las DOS casillas quedan vacias")
    c.cierto("MUELLE" in hd.nota_de_la_fila(filas["03"]).upper(),
             "y la hoja lo dice en NOTAS, en vez de callarlo")
    c.cierto(hd.nota_de_la_fila(filas["03"]).startswith(hd.FALTA_EL_MUELLE),
             "delante de todo lo demas: sin eso no hay nada que ejecutar")

    # Y lo que SI se sabe sigue igual que siempre.
    c.igual((filas["02"]["sierpe"], filas["02"]["drake"]), (2, ""),
            "la que sale por Sierpe sigue contando en Sierpe")
    c.igual(hd.nota_de_la_fila(filas["02"]), "", "y sin aviso de nada")

    # La funcion que reparte, por si alguien la reusa.
    c.igual(hd.columna_del_punto("Sierpe"), "sierpe", "Sierpe a su columna")
    c.igual(hd.columna_del_punto("Drake"), "drake", "Drake a la suya")
    c.igual(hd.columna_del_punto("Sin definir"), None, "y lo que no se sabe, a ninguna")
    c.igual(hd.columna_del_punto(None), None, "ni lo que no es nada")


def quien_no_dice_nada_tambien_sale_en_los_pendientes(c):
    """La otra mitad: poder arreglarlo.

    La lista de «Pendientes de confirmar» de Transporte miraba
    `punto_*_sin_confirmar`, que SOLO se llena cuando la reserva habla de la entrada o
    la salida pero sin nombrar Sierpe ni Drake. La reserva que no dice nada de ese lado
    —porque la nota no llego o porque nadie la escribio— no tenia ese texto, asi que no
    salia en esa lista ni en ninguna otra: el sistema no sabia por donde viaja el
    huesped y no se lo decia a nadie.

    Medido sobre la base del lodge: de las 50 sin punto de entrada, 9 no dicen nada; de
    las 50 sin punto de salida, 8. Invisibles por completo.
    """
    import datetime
    import main

    conn = comun.base_limpia()
    ayer = HOY - datetime.timedelta(days=3)
    pasado = HOY + datetime.timedelta(days=4)

    def reserva(conf, hab, llega, sale, p_ent, p_sal, texto_ent=None):
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                    dep_date, adl, chl, rooms, res_status,
                                    punto_entrada, punto_salida,
                                    punto_entrada_sin_confirmar)
               VALUES (?,?,?,?,?,2,0,1,'POR INGRESAR',?,?,?)""",
            (conf, hab, f"Prueba/{conf}", _ddmmyy(llega), _ddmmyy(sale),
             p_ent, p_sal, texto_ent))

    # Sale HOY y no se sabe por donde, sin que la reserva diga nada: el caso nuevo.
    reserva("880201", "03", ayer, HOY, "Sierpe", None)
    # Entra HOY diciendo algo que no es un punto: el caso que ya salia.
    reserva("880202", "05", HOY, pasado, None, "Drake", texto_ent="Aguila de Osa 10 am")
    # Entra HOY, sin punto de entrada Y sin el de salida, pero su salida es en 4 dias.
    reserva("880203", "06", HOY, pasado, None, None)
    # Y una completa, que no tiene por que aparecer.
    reserva("880204", "07", ayer, HOY, "Sierpe", "Sierpe")
    conn.commit()
    conn.close()

    hoy = main.transporte_pendientes(fecha=HOY.isoformat(), user=USUARIO)
    por_conf = {p["conf_no"]: p for p in hoy}

    c.cierto("880201" in por_conf, "la que sale hoy sin punto YA sale en la lista")
    c.igual((por_conf["880201"]["falta_salida"], por_conf["880201"]["falta_entrada"]),
            (True, False), "y solo por la salida, que es lo que falta")
    c.igual(por_conf["880201"]["punto_salida_sin_confirmar"], None,
            "sin texto que enseñar: la reserva no dice nada de la salida")

    c.cierto("880202" in por_conf, "la que dice algo raro sigue saliendo, como antes")
    c.igual(por_conf["880202"]["punto_entrada_sin_confirmar"], "Aguila de Osa 10 am",
            "con su texto, para poder decidir leyendolo")

    c.igual(por_conf["880203"]["falta_entrada"], True, "la de hoy entra sin punto")
    c.igual(por_conf["880203"]["falta_salida"], False,
            "pero su salida es de otro dia y NO se arrastra al de hoy: una lista que "
            "mezcla dias no se puede cerrar")

    c.cierto("880204" not in por_conf, "y la que esta completa no estorba")

    # El dia de la salida de la 880203 si aparece su lado de salida.
    otro = main.transporte_pendientes(fecha=pasado.isoformat(), user=USUARIO)
    suya = next((p for p in otro if p["conf_no"] == "880203"), None)
    c.cierto(suya is not None and suya["falta_salida"],
             "cada lado sale el dia que le toca")


def sin_punto_el_itinerario_no_promete_sierpe(c):
    """El itinerario del huesped elegia Sierpe para TODO lo que no fuera Drake.

    Una reserva sin punto le prometia al huesped el bote de las 11:30 desde La
    Hacienda, con seguridad y sin marca de revisar. Medido sobre la base del lodge: 50
    reservas vivas no tienen punto, y de las que si lo tienen la mayoria es DRAKE (136
    contra 84), asi que el punto que se inventaba era ademas el menos probable.
    """
    import catalogo_itinerario as cat

    for sin in (None, "", "TRB", "PTE"):
        llegada = cat.texto_llegada(sin)
        c.cierto(llegada["requiere_revision"], f"llegada con «{sin}» queda por revisar")
        c.cierto("Sierpe (boat) or Drake" in llegada["detalles"],
                 "y dice que esta por confirmar en vez de elegir uno")
        c.cierto("La Hacienda" not in llegada["detalles"],
                 "sin prometer el muelle de Sierpe")
        salida = cat.texto_salida(sin)
        c.cierto(salida["requiere_revision"], f"salida con «{sin}» queda por revisar")
        c.cierto("La Hacienda" not in salida["detalles"],
                 "y tampoco promete el de la salida")

    # Y lo que si se sabe sigue igual que siempre.
    sierpe = cat.texto_llegada("Sierpe")
    c.cierto("La Hacienda, Sierpe" in sierpe["detalles"], "por Sierpe, lo de siempre")
    c.cierto(cat.SIERPE_BOTE_LLEGADA in sierpe["horario"], "con su hora fija")
    c.cierto(not sierpe["requiere_revision"], "y sin nada que revisar")
    drake = cat.texto_llegada("Drake", vuelo="RZ1068", hora="9:15 a.m.")
    c.cierto("Drake Bay Airport" in drake["detalles"], "por Drake, lo de siempre")
    c.cierto(not drake["requiere_revision"], "y con vuelo y hora, nada que revisar")
    c.cierto(cat.texto_salida("Sierpe")["horario"].count("___") == 0,
             "la salida por Sierpe conserva sus horarios fijos")


def al_cambiar_el_punto_se_rehace_el_itinerario_del_huesped(c):
    """LO QUE SE VIO EN LA HAB 13: el itinerario decia Sierpe y Transporte decia Drake.

    El itinerario se guarda escrito y solo se rehace cuando la reserva cambia en Opera.
    Al tocar el punto desde la pantalla eso no pasaba, asi que quedaban dos papeles
    diciendo cosas distintas: el bote iba a un sitio y el huesped tenia en la mano otro.
    """
    import json
    conn = comun.base_limpia()
    conn.close()
    lote = _lote_de_opera(punto_entrada=None, pendiente="TRB")
    comun.cargar(lote, vistas=lote)

    conn = comun.conexion()
    guardado = conn.execute(
        "SELECT filas_json FROM itinerario WHERE conf_no = '880001'").fetchone()
    c.cierto(guardado, "la carga deja un itinerario guardado")
    if guardado:
        texto = guardado["filas_json"]
        c.cierto("La Hacienda" not in texto,
                 "que sin punto no promete el muelle de Sierpe")
    conn.close()

    import main
    main.confirmar_transporte("880001", "entrada", "Sierpe", user=USUARIO)

    conn = comun.conexion()
    filas = json.loads(conn.execute(
        "SELECT filas_json FROM itinerario WHERE conf_no = '880001'").fetchone()["filas_json"])
    llegada = [f for f in filas if "Arrival" in (f.get("actividad") or "")]
    c.igual(len(llegada), 1, "sigue habiendo un dia de llegada")
    if llegada:
        c.cierto("La Hacienda, Sierpe" in (llegada[0].get("detalles") or ""),
                 "y ahora dice Sierpe, como la pantalla de Transporte")
    conn.close()

    # Si el itinerario lo escribio una persona NO se toca, pero se avisa.
    conn = comun.conexion()
    conn.execute("UPDATE itinerario SET editado = 1 WHERE conf_no = '880001'")
    conn.commit()
    conn.close()
    main.confirmar_transporte("880001", "entrada", "Drake", user=USUARIO)
    conn = comun.conexion()
    f = dict(conn.execute(
        "SELECT * FROM itinerario WHERE conf_no = '880001'").fetchone())
    c.cierto("La Hacienda, Sierpe" in f["filas_json"],
             "lo editado a mano no se reescribe solo")
    c.cierto(f["aviso_cambios"] and "punto de entrada" in f["aviso_cambios"],
             "pero la pantalla avisa que hay que revisarlo")
    conn.close()


def la_pantalla_deja_cambiar_el_punto_siempre(c):
    """No solo en «Pendientes de confirmar», que es como estaba."""
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "frontend", "index.html")
    with open(ruta, encoding="utf-8") as f:
        html = f.read()
    c.cierto("celdaPunto" in html, "la celda del punto es un selector")
    c.cierto("celdaPunto(r, \"entrada\")" in html and "celdaPunto(r, \"salida\")" in html,
             "en las dos tablas, entradas y salidas")
    c.cierto("cambiarPuntoDeEmbarque" in html, "que manda el cambio al servidor")
    c.cierto("automatico" in html, "y deja volver a lo que diga la reserva")
    c.cierto("punto_entrada_a_mano" in html, "la pantalla sabe cual se puso a mano")
    # El servidor tiene que mandarla, o el selector nunca ofreceria soltarla.
    ruta_main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "backend", "main.py")
    with open(ruta_main, encoding="utf-8") as f:
        servidor = f.read()
    i = servidor.find("def transporte(")
    c.cierto("punto_entrada_a_mano" in servidor[i:i + 2500]
             and "punto_salida_a_mano" in servidor[i:i + 2500],
             "y el endpoint de Transporte las devuelve")


PRUEBAS = [
    la_hora_se_lee_aunque_este_mal_escrita,
    con_minutos_manda_la_hora_con_minutos,
    lo_que_NO_es_una_hora_no_se_inventa,
    los_dos_puntos_se_leen_de_la_nota,
    la_entrada_y_la_salida_pueden_ser_distintas,
    cada_hora_es_la_de_su_propio_campo,
    la_hora_pegada_al_numero_de_vuelo_se_lee,
    punta_marenco_es_una_recogida_de_drake,
    copa_de_arbol_es_una_recogida_de_drake,
    el_punto_no_tiene_que_ser_la_primera_palabra,
    dos_puntos_distintos_no_se_deciden_solos,
    la_hora_sirve_aunque_el_punto_no_se_reconozca,
    el_campo_vacio_se_marca_como_vacio,
    el_pte_se_guarda_limpio,
    el_valor_no_se_come_el_resto_de_la_nota,
    una_linea_de_salida_no_cuenta_como_entrada,
    recepcion_puede_corregir_un_punto_que_ya_venia_puesto,
    la_sincronizacion_no_se_lleva_lo_que_puso_recepcion,
    si_la_reserva_pasa_a_decir_otra_cosa_se_avisa,
    una_reimportacion_del_pdf_tampoco_la_deshace,
    se_puede_devolver_el_mando_a_la_reserva,
    confirmar_una_habitacion_no_cierra_los_avisos_de_las_demas,
    un_punto_que_no_existe_no_se_guarda,
    un_cambio_de_habitacion_no_pide_confirmar_un_muelle,
    la_mudanza_no_sale_en_pendientes_ni_genera_aviso,
    el_aviso_de_confirmar_no_salta_por_una_mudanza,
    la_hoja_del_dia_no_pone_en_drake_lo_que_no_sabe,
    quien_no_dice_nada_tambien_sale_en_los_pendientes,
    sin_punto_el_itinerario_no_promete_sierpe,
    al_cambiar_el_punto_se_rehace_el_itinerario_del_huesped,
    la_pantalla_deja_cambiar_el_punto_siempre,
]


if __name__ == "__main__":
    sys.exit(comun.correr("puntos de embarque", PRUEBAS))
