"""Fija las reglas de los traslados: quien entra y quien sale, con su guia y su bote.

POR QUE ESTA SUITE. Es el momento mas delicado del dia: si nadie va al muelle de Sierpe
o a la pista de Drake, el huesped se queda tirado con las maletas en un lugar sin senal.
Hasta ahora los tours tenian guia y bote asignados y los traslados no.

Lo que hay que fijar, y por que cada cosa falla EN SILENCIO si se rompe:

  · Que los que se mueven a la MISMA hora, por el mismo punto y en la misma direccion
    vayan en la misma corrida. Si se partieran, se mandarian dos botes para seis
    personas; si se juntaran los de horas distintas, alguien esperaria en la pista.
  · Que las corridas se DERIVEN de las reservas y no se guarden. Guardadas, cambiar la
    hora de un vuelo deja la corrida vieja con gente que ya no viaja en ella.
  · Que cambiar la hora de un vuelo deje la corrida nueva SIN ASIGNAR, en vez de
    arrastrar una asignacion que nadie confirmo. Arrastrarla es lo que deja a alguien
    esperando.
  · Que una reserva cancelada desaparezca de su corrida sola.
  · Que el mismo bote y el mismo guia puedan hacer varios viajes el mismo dia —es lo
    normal por Drake— pero no dos AL MISMO TIEMPO.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402
from comun import base_limpia, cargar, conexion, reserva   # noqa: E402

import traslados as tr                           # noqa: E402

HOY = datetime.date.today()


def ddmmyy(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def iso(d):
    return d.isoformat()


def limpiar():
    """Base nueva sin dejar la conexion abierta: en Windows una conexion viva impide
    borrar el archivo en la prueba siguiente."""
    base_limpia().close()


MANANA = HOY + datetime.timedelta(days=1)


# ---------------------------------------------------------------------------
# La corrida se arma por hora
# ---------------------------------------------------------------------------

def los_que_van_a_la_misma_hora_van_juntos(c):
    """Tres habitaciones en el vuelo de las 09:00 son UNA corrida, no tres."""
    limpiar()
    cargar([
        reserva("A1", "01", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=3)),
                punto_entrada="Drake", hora_vuelo_entrada="09:00"),
        reserva("A2", "02", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=3)),
                punto_entrada="Drake", hora_vuelo_entrada="09:00"),
        reserva("A3", "03", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=3)),
                punto_entrada="Drake", hora_vuelo_entrada="09:00", adl=1),
    ])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    conn.close()
    c.igual(len(lista), 1, "las tres habitaciones son una sola corrida")
    if lista:
        c.igual(lista[0]["pax"], 5, "con el pax sumado (2+2+1)")
        c.igual(len(lista[0]["huespedes"]), 3, "y las tres habitaciones adentro")
        c.igual(lista[0]["hora"], "09:00", "a la hora del vuelo")
        c.igual(lista[0]["punto"], "Drake", "por Drake")


def horas_distintas_son_corridas_distintas(c):
    """El mismo bote hace varios viajes el mismo dia: es lo normal por Drake, donde cada
    vuelo llega a una hora. Juntarlos mandaria un solo bote a una sola hora y la mitad
    de la gente se quedaria en la pista."""
    limpiar()
    cargar([
        reserva("B1", "01", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Drake", hora_vuelo_entrada="09:00"),
        reserva("B2", "02", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Drake", hora_vuelo_entrada="14:30"),
    ])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    conn.close()
    c.igual(len(lista), 2, "dos vuelos, dos corridas")
    c.igual([x["hora"] for x in lista], ["09:00", "14:30"], "ordenadas por hora")


def sierpe_y_drake_no_se_mezclan(c):
    """Son dos lugares distintos a cientos de curvas de distancia."""
    limpiar()
    cargar([
        reserva("C1", "01", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Sierpe"),
        reserva("C2", "02", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Drake", hora_vuelo_entrada="09:00"),
    ])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    conn.close()
    c.igual(sorted(x["punto"] for x in lista), ["Drake", "Sierpe"],
            "una corrida por punto")


def la_entrada_y_la_salida_son_corridas_distintas(c):
    """Aunque coincidan en punto y hora: son viajes en direcciones opuestas."""
    limpiar()
    cargar([
        reserva("D1", "01", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Sierpe"),
        reserva("D2", "02", ddmmyy(MANANA - datetime.timedelta(days=2)), ddmmyy(MANANA),
                punto_salida="Sierpe"),
    ])
    conn = conexion()
    lista = tr.corridas(conn, iso(MANANA), iso(MANANA))
    conn.close()
    tipos = sorted(x["tipo"] for x in lista)
    c.igual(tipos, ["entrada", "salida"], "una de entrada y una de salida")


def sierpe_usa_el_horario_fijo_del_bote(c):
    """El PDF no repite la hora de Sierpe porque el bote sale siempre a la misma. Sin
    esta regla, todos los de Sierpe caerian en la corrida 'sin hora'."""
    limpiar()
    cargar([reserva("E1", "01", ddmmyy(MANANA),
                    ddmmyy(MANANA + datetime.timedelta(days=2)),
                    punto_entrada="Sierpe")])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    conn.close()
    c.cierto(lista and lista[0]["hora"] != tr.SIN_HORA,
             "la entrada por Sierpe sale con hora, no vacia")
    if lista:
        c.igual(lista[0]["hora_origen"], "horario fijo de Sierpe", "y se dice de donde")


def por_sierpe_la_hora_fija_manda_sobre_la_de_la_reserva(c):
    """La regla que dio el lodge: «cuando sea un ingreso que se indique la misma hora, y
    cuando sea una salida dos horas antes de lo que diga la reserva; esto en el caso
    EXCLUSIVO de Drake. Para Sierpe se mantiene la hora fija».

    Antes cualquier hora escrita en la reserva ganaba, y por Sierpe salian horas de la
    tarde: medido, la habitacion 09 del 2 de noviembre a las 14:20, y las 21 y 13 del
    dia 3 a las 15:13 y 15:11. Por Sierpe el bote sale a la misma hora para todos, asi
    que esas horas eran otra cosa —el check-in del PMS— y ademas PARTIAN EN TRES
    CORRIDAS a gente que viaja en el mismo bote."""
    import catalogo_itinerario as cat
    limpiar()
    cargar([
        # Las tres por Sierpe el mismo dia, dos de ellas con hora escrita y distinta.
        reserva("S1", "09", ddmmyy(MANANA),
                ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Sierpe", arr_time="14:20"),
        reserva("S2", "21", ddmmyy(MANANA),
                ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Sierpe", hora_vuelo_entrada="15:13"),
        reserva("S3", "13", ddmmyy(MANANA),
                ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Sierpe"),
    ])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    c.igual(len(lista), 1, "las tres van en UNA corrida: es el mismo bote")
    if lista:
        c.igual(lista[0]["hora"], cat.SIERPE_BOTE_LLEGADA,
                "a la hora fija de Sierpe, no a la que diga la reserva")
        c.igual(lista[0]["hora_origen"], "horario fijo de Sierpe", "y se dice de donde")
        c.igual(len(lista[0]["huespedes"]), 3, "con las tres habitaciones dentro")
    conn.close()


def por_drake_el_ingreso_lleva_la_hora_del_vuelo_sin_tocar(c):
    """La otra mitad de la regla, y la que evita pasarse: por Drake el bote espera al
    avion, asi que en el INGRESO la hora es la del vuelo tal cual. Las dos horas antes
    son solo para la SALIDA."""
    limpiar()
    cargar([reserva("D1", "07", ddmmyy(MANANA),
                    ddmmyy(MANANA + datetime.timedelta(days=2)),
                    punto_entrada="Drake", hora_vuelo_entrada="9:15 a.m.",
                    punto_salida="Drake", hora_vuelo_salida="9:25 a.m.")])
    conn = conexion()
    entra = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    c.igual([x["hora"] for x in entra], ["9:15 a.m."],
            "el ingreso por Drake va a la hora del vuelo, sin restar nada")

    sale_dia = MANANA + datetime.timedelta(days=2)
    sale = [x for x in tr.corridas(conn, iso(sale_dia), iso(sale_dia))
            if x["tipo"] == "salida"]
    c.igual([x["hora"] for x in sale], ["7:25 a.m."],
            "y la salida por Drake, dos horas antes del vuelo")
    if sale:
        c.igual(sale[0]["hora_origen"], "calculado del vuelo", "y se dice de donde")
    conn.close()


def el_que_no_tiene_hora_no_se_esconde(c):
    """Drake sin hora de vuelo no se puede ubicar en ninguna corrida. Tiene que salir
    igual, marcado: es justo el que hay que resolver. Una lista que solo muestre a los
    que ya tienen hora esconde el trabajo que queda."""
    limpiar()
    cargar([reserva("F1", "01", ddmmyy(MANANA),
                    ddmmyy(MANANA + datetime.timedelta(days=2)),
                    punto_entrada="Drake")])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    conn.close()
    c.igual(len(lista), 1, "aparece igual")
    if lista:
        c.igual(lista[0]["hora"], tr.SIN_HORA, "en la corrida sin hora")
        c.igual(lista[0]["hora_origen"], "falta la hora del vuelo", "diciendo que falta")


def una_reserva_cancelada_sale_de_su_corrida(c):
    """Sin esto se mandaria un bote por alguien que no viene."""
    limpiar()
    cargar([
        reserva("G1", "01", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Sierpe"),
        reserva("G2", "02", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Sierpe", estado="CANCELADA"),
    ])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    conn.close()
    c.igual(len(lista), 1, "queda una corrida")
    if lista:
        c.igual(lista[0]["pax"], 2, "con el pax de la que sigue viva, no de las dos")


# ---------------------------------------------------------------------------
# La asignacion
# ---------------------------------------------------------------------------

def se_asigna_guia_y_bote_a_una_corrida(c):
    limpiar()
    cargar([reserva("H1", "01", ddmmyy(MANANA),
                    ddmmyy(MANANA + datetime.timedelta(days=2)),
                    punto_entrada="Sierpe")])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    hora = lista[0]["hora"]
    c.igual(lista[0]["falta"], ["guía", "bote", "capitán"], "arranca sin nada asignado")

    guia = conn.execute("SELECT nombre FROM guia LIMIT 1").fetchone()["nombre"]
    bote = conn.execute(
        "SELECT nombre FROM bote WHERE gestionado_por_hotel = 1 LIMIT 1").fetchone()["nombre"]
    _, problema = tr.asignar(conn, iso(MANANA), "entrada", "Sierpe", hora,
                             guia=guia, bote=bote)
    c.igual(problema, None, "se guarda sin problema")

    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    c.igual(lista[0]["guia_nombre"], guia, "queda el guia")
    c.igual(lista[0]["bote_nombre"], bote, "y el bote")
    # Desde que los botes viven en Transporte la corrida tambien lleva capitan, asi
    # que guia + bote ya no la dejan completa: sigue faltando quien la maneje.
    c.igual(lista[0]["falta"], ["capitán"], "pero sigue faltando el capitan")
    conn.close()


def dejar_sin_asignar_es_distinto_de_no_mandar_el_dato(c):
    """Igual que en los tours: un parametro ausente no toca lo que habia, uno vacio
    borra la asignacion. Sin esa diferencia no hay forma de QUITAR un guia desde la
    pantalla, y el aviso de 'sin guia' busca NULL: un texto vacio se le escaparia."""
    limpiar()
    conn = conexion()
    guia = conn.execute("SELECT nombre FROM guia LIMIT 1").fetchone()["nombre"]
    bote = conn.execute(
        "SELECT nombre FROM bote WHERE gestionado_por_hotel = 1 LIMIT 1").fetchone()["nombre"]

    tr.asignar(conn, iso(MANANA), "entrada", "Sierpe", "08:00", guia=guia, bote=bote)
    # Solo el bote: el guia no se manda y tiene que quedarse.
    tr.asignar(conn, iso(MANANA), "entrada", "Sierpe", "08:00", bote="")
    fila = conn.execute(
        "SELECT guia_nombre, bote_nombre FROM traslado WHERE hora = '08:00'").fetchone()
    c.igual(fila["guia_nombre"], guia, "el guia que no se mando sigue puesto")
    c.igual(fila["bote_nombre"], None, "y el bote vacio quedo en NULL, no en ''")
    conn.close()


def no_se_asigna_a_un_punto_inventado(c):
    limpiar()
    conn = conexion()
    _, p1 = tr.asignar(conn, iso(MANANA), "entrada", "Puerto Jimenez", "08:00")
    c.cierto(p1, "un punto que no es Sierpe ni Drake se rechaza")
    _, p2 = tr.asignar(conn, iso(MANANA), "de paseo", "Sierpe", "08:00")
    c.cierto(p2, "una direccion que no es entrada ni salida se rechaza")
    _, p3 = tr.asignar(conn, "", "entrada", "Sierpe", "08:00")
    c.cierto(p3, "y sin fecha tampoco")
    c.igual(tr.normalizar_punto(" sIeRpE "), "Sierpe",
            "pero el punto se entiende como venga escrito")
    conn.close()


def cambiar_la_hora_del_vuelo_deja_la_corrida_sin_asignar(c):
    """LA regla que evita el peor error de todos.

    Si a un huesped le mueven el vuelo, su corrida cambia. Arrastrar la asignacion a la
    hora nueva —sin que nadie la confirme— es lo que deja a alguien esperando en la
    pista creyendo que lo van a buscar. La corrida nueva tiene que aparecer VACIA, para
    que se vea que hay que volver a decidir.
    """
    limpiar()
    cargar([reserva("I1", "01", ddmmyy(MANANA),
                    ddmmyy(MANANA + datetime.timedelta(days=2)),
                    punto_entrada="Drake", hora_vuelo_entrada="09:00")])
    conn = conexion()
    guia = conn.execute("SELECT nombre FROM guia LIMIT 1").fetchone()["nombre"]
    tr.asignar(conn, iso(MANANA), "entrada", "Drake", "09:00", guia=guia)

    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    c.igual(lista[0]["guia_nombre"], guia, "asignada a las 09:00")

    # Al huesped le mueven el vuelo
    conn.execute("UPDATE reserva SET hora_vuelo_entrada = '14:30' WHERE conf_no = 'I1'")
    conn.commit()

    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada"]
    c.igual(len(lista), 1, "sigue habiendo una sola corrida")
    if lista:
        c.igual(lista[0]["hora"], "14:30", "a la hora nueva")
        c.igual(lista[0]["guia_nombre"], None,
                "y SIN guia: hay que volver a decidir quien va")
        c.igual(lista[0]["falta"], ["guía", "bote", "capitán"], "marcada como que falta cubrirla")
    conn.close()


# ---------------------------------------------------------------------------
# Capacidad y choques
# ---------------------------------------------------------------------------

def se_avisa_si_no_cabe_la_gente_en_el_bote(c):
    limpiar()
    conn = conexion()
    bote = conn.execute(
        """SELECT nombre, capacidad_max FROM bote
           WHERE gestionado_por_hotel = 1 AND capacidad_max IS NOT NULL
           ORDER BY capacidad_max LIMIT 1""").fetchone()
    cap = bote["capacidad_max"]
    corrida = {"fecha": iso(MANANA), "tipo": "entrada", "punto": "Sierpe",
               "hora": "08:00", "pax": cap + 3, "bote_nombre": bote["nombre"]}
    aviso = tr._aviso_capacidad(corrida, {bote["nombre"]: cap})
    c.cierto(aviso, "avisa que no cabe")
    c.cierto(aviso and str(cap + 3 - cap) in aviso,
             "y dice cuantos lugares faltan, no solo que no cabe")

    corrida["pax"] = cap
    c.igual(tr._aviso_capacidad(corrida, {bote["nombre"]: cap}), None,
            "justo a capacidad no se avisa")
    conn.close()


def un_bote_privado_no_tiene_tope(c):
    """El bote privado lo pone la agencia y el lodge no decide cuanta gente le cabe.
    Avisar ahi seria un aviso que nadie puede resolver, y los avisos que no se pueden
    resolver son los que ensenan a ignorar todos los demas."""
    limpiar()
    conn = conexion()
    caps = tr.capacidades_de_botes(conn)
    externos = [r["nombre"] for r in conn.execute(
        "SELECT nombre FROM bote WHERE gestionado_por_hotel = 0")]
    conn.close()
    for nombre in externos:
        c.cierto(nombre not in caps, f"{nombre} no entra en el control de capacidad")


def el_mismo_bote_puede_hacer_varios_viajes_al_dia(c):
    """Es lo normal por Drake. Marcarlo como conflicto llenaria la pantalla de avisos
    falsos, y con avisos falsos se dejan de leer los verdaderos."""
    limpiar()
    lista = [
        {"fecha": iso(MANANA), "tipo": "entrada", "punto": "Drake", "hora": "09:00",
         "guia_nombre": "Luis", "bote_nombre": "Osa I"},
        {"fecha": iso(MANANA), "tipo": "entrada", "punto": "Drake", "hora": "14:30",
         "guia_nombre": "Luis", "bote_nombre": "Osa I"},
    ]
    c.igual(tr.conflictos(lista), [], "dos viajes a horas distintas no chocan")


def el_mismo_bote_no_puede_estar_en_dos_lados_a_la_vez(c):
    limpiar()
    lista = [
        {"fecha": iso(MANANA), "tipo": "entrada", "punto": "Drake", "hora": "09:00",
         "guia_nombre": "Luis", "bote_nombre": "Osa I"},
        {"fecha": iso(MANANA), "tipo": "salida", "punto": "Sierpe", "hora": "09:00",
         "guia_nombre": "Luis", "bote_nombre": "Osa I"},
    ]
    avisos = tr.conflictos(lista)
    c.igual(len(avisos), 2, "choca el guia y choca el bote")
    c.cierto(any("Luis" in a for a in avisos), "y se dice quien")
    c.cierto(any("Sierpe" in a and "Drake" in a for a in avisos),
             "y entre que dos traslados")


def los_externos_se_pueden_repetir(c):
    """'EXTERNO' no es una persona: es 'lo pone alguien de afuera'."""
    limpiar()
    lista = [
        {"fecha": iso(MANANA), "tipo": "entrada", "punto": "Drake", "hora": "09:00",
         "guia_nombre": "EXTERNO", "bote_nombre": "PRIVADO"},
        {"fecha": iso(MANANA), "tipo": "salida", "punto": "Sierpe", "hora": "09:00",
         "guia_nombre": "EXTERNO", "bote_nombre": "PRIVADO"},
    ]
    c.igual(tr.conflictos(lista), [], "externo y privado no cuentan como choque")


def la_misma_hora_escrita_distinto_es_la_misma_hora(c):
    """Las horas llegan en DOS formatos: '09:00' del PDF, y '11:30 a.m.' de los horarios
    fijos del lodge. Comparando los textos tal cual, un guia en Sierpe a las '9:00 a.m.'
    y en Drake a las '09:00' no salia como choque — y es el mismo momento. Nadie puede
    estar en los dos lugares, y el que se quede sin guia es un huesped en un muelle."""
    limpiar()
    c.igual(tr.minutos_de("09:00"), 540, "09:00 son 540 minutos")
    c.igual(tr.minutos_de("9:00 a.m."), 540, "y 9:00 a.m. tambien")
    c.igual(tr.minutos_de("11:30 a.m."), 690, "11:30 a.m.")
    c.igual(tr.minutos_de("1:00 p.m."), 780, "1:00 p.m. es la una de la tarde")
    c.igual(tr.minutos_de("12:00 a.m."), 0, "las doce de la noche son las cero")
    c.igual(tr.minutos_de("12:30 p.m."), 750, "y 12:30 p.m. es el mediodia")
    c.igual(tr.minutos_de(""), None, "sin hora no hay minutos")
    c.igual(tr.minutos_de("a la tarde"), None, "ni con un texto que no es hora")
    c.igual(tr.minutos_de("25:00"), None, "ni con una hora imposible")

    lista = [
        {"fecha": iso(MANANA), "tipo": "entrada", "punto": "Drake", "hora": "09:00",
         "guia_nombre": "Luis", "bote_nombre": None},
        {"fecha": iso(MANANA), "tipo": "salida", "punto": "Sierpe", "hora": "9:00 a.m.",
         "guia_nombre": "Luis", "bote_nombre": None},
    ]
    avisos = tr.conflictos(lista)
    c.igual(len(avisos), 1, "se detecta el choque aunque la hora este escrita distinto")


def las_corridas_salen_ordenadas_por_hora_real(c):
    """Ordenadas como texto, '9:00 a.m.' cae despues de '14:30' y la lista del dia
    quedaria en un orden que no es el del reloj."""
    limpiar()
    cargar([
        reserva("J1", "01", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Drake", hora_vuelo_entrada="14:30"),
        reserva("J2", "02", ddmmyy(MANANA), ddmmyy(MANANA + datetime.timedelta(days=2)),
                punto_entrada="Drake", hora_vuelo_entrada="09:00"),
    ])
    conn = conexion()
    lista = [x for x in tr.corridas(conn, iso(MANANA), iso(MANANA))
             if x["tipo"] == "entrada" and x["punto"] == "Drake"]
    conn.close()
    c.igual([x["hora"] for x in lista], ["09:00", "14:30"], "primero la de las 9")


def sin_hora_no_se_inventan_choques(c):
    """Dos corridas sin hora no se pueden declarar simultaneas: no se sabe."""
    limpiar()
    lista = [
        {"fecha": iso(MANANA), "tipo": "entrada", "punto": "Drake", "hora": tr.SIN_HORA,
         "guia_nombre": "Luis", "bote_nombre": "Osa I"},
        {"fecha": iso(MANANA), "tipo": "salida", "punto": "Sierpe", "hora": tr.SIN_HORA,
         "guia_nombre": "Luis", "bote_nombre": "Osa I"},
    ]
    c.igual(tr.conflictos(lista), [], "sin hora no se afirma que choquen")


def el_resumen_cuenta_lo_que_falta_cubrir(c):
    limpiar()
    lista = [
        {"fecha": iso(MANANA), "tipo": "entrada", "punto": "Drake", "hora": "09:00",
         "guia_nombre": "Luis", "bote_nombre": None, "pax": 4},
        {"fecha": iso(MANANA), "tipo": "salida", "punto": "Sierpe", "hora": tr.SIN_HORA,
         "guia_nombre": None, "bote_nombre": None, "pax": 2},
    ]
    r = tr.resumen(lista)
    c.igual(r["corridas"], 2, "dos corridas")
    c.igual(r["pax"], 6, "seis pax")
    c.igual(r["sin_guia"], 1, "una sin guia")
    c.igual(r["sin_bote"], 2, "dos sin bote")
    c.igual(r["sin_hora"], 1, "y una sin hora")


def se_asigna_capitan_y_ayudante_a_una_corrida(c):
    """Lo pidio el lodge: los botes se coordinan desde Transporte, con capitan y
    ayudante. Los dos salen del MISMO catalogo: en el lodge la misma persona es capitan
    un dia y ayudante otro, segun con quien le toque el bote."""
    conn = base_limpia()
    r = dict(reserva(710001, "01", ddmmyy(HOY),
                     ddmmyy(HOY + datetime.timedelta(days=3)), adl=2),
             punto_entrada="Sierpe")
    cargar([r], vistas=[r])

    lista = tr.corridas(conn, iso(HOY), iso(HOY))
    c.igual(len(lista), 1, "hay una corrida")
    k = lista[0]

    ok, problema = tr.asignar(conn, k["fecha"], k["tipo"], k["punto"], k["hora"],
                              capitan="WILL", ayudante="JUNIOR")
    c.igual(problema, None, "se asignan los dos")

    lista = tr.corridas(conn, iso(HOY), iso(HOY))
    c.igual(lista[0]["capitan_nombre"], "WILL", "queda el capitan")
    c.igual(lista[0]["ayudante_nombre"], "JUNIOR", "y el ayudante")

    # Dejar uno en «Sin asignar» lo borra, sin tocar el otro.
    tr.asignar(conn, k["fecha"], k["tipo"], k["punto"], k["hora"], ayudante="")
    lista = tr.corridas(conn, iso(HOY), iso(HOY))
    c.igual(lista[0]["ayudante_nombre"], None, "se puede quitar el ayudante")
    c.igual(lista[0]["capitan_nombre"], "WILL", "y el capitan sigue puesto")
    conn.close()


def nadie_va_de_capitan_y_de_ayudante_a_la_vez(c):
    """Una corrida con la misma persona en los dos puestos tiene UNA persona, no dos, y
    en el muelle faltaria alguien.

    EL CASO QUE IMPORTA es el segundo: los dos selectores se cambian por separado, asi
    que poner de ayudante a quien ya era capitan llega al servidor con el capitan
    AUSENTE. Mirando solo lo que llega se dejaria pasar; hay que mirar lo que va a
    quedar guardado."""
    conn = base_limpia()
    r = dict(reserva(710002, "02", ddmmyy(HOY),
                     ddmmyy(HOY + datetime.timedelta(days=3)), adl=2),
             punto_entrada="Sierpe")
    cargar([r], vistas=[r])
    k = tr.corridas(conn, iso(HOY), iso(HOY))[0]

    ok, problema = tr.asignar(conn, k["fecha"], k["tipo"], k["punto"], k["hora"],
                              capitan="WILL", ayudante="WILL")
    c.cierto(problema is not None, "no se deja poner a la misma persona dos veces")
    c.cierto("WILL" in (problema or ""), "y el aviso dice quien es")

    # Y por separado, que es como pasa de verdad en la pantalla.
    tr.asignar(conn, k["fecha"], k["tipo"], k["punto"], k["hora"], capitan="NERYS")
    ok, problema = tr.asignar(conn, k["fecha"], k["tipo"], k["punto"], k["hora"],
                              ayudante="NERYS")
    c.cierto(problema is not None,
             "tampoco cambiando solo el ayudante sobre un capitan ya puesto")

    lista = tr.corridas(conn, iso(HOY), iso(HOY))
    c.igual(lista[0]["capitan_nombre"], "NERYS", "el capitan no se toco")
    c.igual(lista[0]["ayudante_nombre"], None, "y el ayudante quedo sin poner")
    conn.close()


def sin_capitan_se_cuenta_pero_sin_ayudante_no(c):
    """No todas las corridas llevan ayudante —un bote chico con dos pasajeros va solo con
    su capitan— asi que contarlo como faltante pintaria de amarillo media pantalla todos
    los dias y el aviso dejaria de significar algo."""
    conn = base_limpia()
    r = dict(reserva(710003, "03", ddmmyy(HOY),
                     ddmmyy(HOY + datetime.timedelta(days=3)), adl=2),
             punto_entrada="Sierpe")
    cargar([r], vistas=[r])

    lista = tr.corridas(conn, iso(HOY), iso(HOY))
    c.igual(tr.resumen(lista)["sin_capitan"], 1, "sin capitan se cuenta")
    c.cierto("capitán" in lista[0]["falta"], "y sale en lo que falta")
    c.igual("ayudante" in lista[0]["falta"], False, "el ayudante NO se cuenta")

    k = lista[0]
    tr.asignar(conn, k["fecha"], k["tipo"], k["punto"], k["hora"], capitan="DYLAN")
    lista = tr.corridas(conn, iso(HOY), iso(HOY))
    c.igual(tr.resumen(lista)["sin_capitan"], 0, "y deja de contarse al ponerlo")
    conn.close()


def los_capitanes_del_lodge_estan_en_el_catalogo(c):
    """Los cinco que dio el lodge. Si el catalogo llegara vacio, los selectores de
    Transporte saldrian sin nadie y no se podria asignar a ninguno."""
    conn = base_limpia()
    nombres = sorted(x["nombre"] for x in conn.execute(
        "SELECT nombre FROM capitan WHERE activo = 1"))
    c.igual(nombres, ["DYLAN", "EZEQUIEL", "JUNIOR", "NERYS", "WILL"],
            "estan los cinco capitanes")
    conn.close()


# ---------------------------------------------------------------------------
# Los tours que van en bote
# ---------------------------------------------------------------------------
#
# El lodge los mando a Transporte: «se asignan en la parte de transportes, lo que son
# tours acuaticos que necesitan bote». Son un viaje de bote igual que una corrida de
# muelle, y verlos en dos pantallas distintas era justo lo que hacia que un bote
# apareciera comprometido dos veces el mismo dia.

def _con_tour(conf_no, tour, dia=2, adl=2, **extra):
    """Una reserva que llega el 01-01-26 y lleva UN tour el dia 'dia' de la estadia."""
    return reserva(conf_no, "07", "01-01-26", "06-01-26", adl=adl,
                   operacion=[{"dia": dia, "tour": tour}], **extra)


def solo_los_tours_que_llevan_bote_salen_en_transporte(c):
    """Una caminata no ocupa bote. Si saliera en la lista habria que ponerle uno —o
    dejarla en rojo para siempre— y el aviso de «sin bote» dejaria de significar nada."""
    limpiar()
    cargar([_con_tour("800001", "MANGLAR"),          # requiere_bote = 1
            _con_tour("800002", "CLARO")])           # requiere_bote = 0
    conn = conexion()
    fechas = [f["fecha"] for f in conn.execute(
        "SELECT DISTINCT fecha FROM tour_asignado ORDER BY fecha")]
    lista = tr.salidas_de_tour(conn, min(fechas), max(fechas))
    codigos = sorted(t["tour_codigo"] for t in lista)
    c.igual(codigos, ["MANGLAR"], "solo el tour que lleva bote")
    c.igual(lista[0]["pax"], 2, "con su pax")
    c.igual(lista[0]["falta"], ["guía", "bote", "capitán"],
            "y arranca sin nadie puesto")
    conn.close()


def el_tour_se_agrupa_por_fecha_tour_y_grupo(c):
    """Dos habitaciones en el mismo tour son UNA salida, no dos: suben al mismo bote.

    Si se contaran por separado, la pantalla pediria dos botes para cuatro personas y el
    aviso de capacidad miraria media salida cada vez."""
    limpiar()
    cargar([_con_tour("800010", "MANGLAR"), _con_tour("800011", "MANGLAR")])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]
    lista = tr.salidas_de_tour(conn, fecha, fecha)
    c.igual(len(lista), 1, "las dos habitaciones son una sola salida")
    c.igual(lista[0]["pax"], 4, "con el pax sumado")
    c.igual(len(lista[0]["habitaciones"]), 2, "y las dos habitaciones adentro")

    # Partir el tour en dos grupos SI son dos salidas: es justo para lo que sirve el
    # grupo, y cada uno lleva su propio bote.
    conn.execute("UPDATE tour_asignado SET grupo_operativo = 'B' WHERE conf_no = ?",
                 ("800011",))
    conn.commit()
    lista = tr.salidas_de_tour(conn, fecha, fecha)
    c.igual(len(lista), 2, "partido en dos grupos son dos salidas")
    c.igual(sorted(t["grupo"] for t in lista), ["A", "B"], "una por grupo")
    conn.close()


def el_bote_se_le_pone_al_grupo_entero(c):
    """Todo el grupo sube al mismo bote. Dejar una reserva del grupo con otro bote seria
    gente del mismo tour esperando en dos muelles."""
    limpiar()
    cargar([_con_tour("800020", "MANGLAR"), _con_tour("800021", "MANGLAR")])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]
    bote = conn.execute(
        "SELECT nombre FROM bote WHERE gestionado_por_hotel = 1 LIMIT 1").fetchone()["nombre"]

    cuantas, problema = tr.asignar_tour(conn, fecha, "MANGLAR", "A",
                                        bote=bote, capitan="WILL", ayudante="DYLAN")
    c.igual(problema, None, "se guarda sin problema")
    c.igual(cuantas, 2, "y toca las dos reservas del grupo")

    puestos = [dict(f) for f in conn.execute(
        "SELECT bote_nombre, capitan_nombre, ayudante_nombre FROM tour_asignado")]
    c.igual([p["bote_nombre"] for p in puestos], [bote, bote], "las dos con el bote")
    c.igual([p["capitan_nombre"] for p in puestos], ["WILL", "WILL"], "y el capitan")

    lista = tr.salidas_de_tour(conn, fecha, fecha)
    c.igual(lista[0]["falta"], ["guía"], "ya solo falta el guia, que se pone en la Agenda")
    conn.close()


def el_guia_del_tour_no_se_toca_desde_transporte(c):
    """El guia se elige en la Agenda. Si esta ruta lo pisara, asignar un bote borraria
    el guia que recepcion acababa de poner, y nadie se enteraria hasta el dia del tour."""
    limpiar()
    cargar([_con_tour("800030", "MANGLAR")])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]
    guia = conn.execute("SELECT nombre FROM guia LIMIT 1").fetchone()["nombre"]
    conn.execute("UPDATE tour_asignado SET guia_nombre = ?", (guia,))
    conn.commit()

    tr.asignar_tour(conn, fecha, "MANGLAR", "A", bote="TIBURON")
    c.igual(conn.execute("SELECT guia_nombre FROM tour_asignado").fetchone()[0], guia,
            "el guia sigue donde estaba")
    c.igual(tr.salidas_de_tour(conn, fecha, fecha)[0]["guia_nombre"], guia,
            "y Transporte lo enseña")
    conn.close()


def nadie_va_de_capitan_y_de_ayudante_en_la_misma_salida_de_tour(c):
    """La misma regla que en una corrida de muelle, y por la misma razon: los dos
    selectores se cambian por separado, asi que poner de ayudante a quien ya era capitan
    llega aqui con el capitan AUSENTE."""
    limpiar()
    cargar([_con_tour("800040", "MANGLAR")])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]

    _, problema = tr.asignar_tour(conn, fecha, "MANGLAR", "A",
                                  capitan="NERYS", ayudante="NERYS")
    c.cierto(problema is not None, "no se deja poner a la misma persona dos veces")

    tr.asignar_tour(conn, fecha, "MANGLAR", "A", capitan="NERYS")
    _, problema = tr.asignar_tour(conn, fecha, "MANGLAR", "A", ayudante="NERYS")
    c.cierto(problema is not None,
             "tampoco cambiando solo el ayudante sobre un capitan ya puesto")
    c.igual(conn.execute("SELECT ayudante_nombre FROM tour_asignado").fetchone()[0], None,
            "y el ayudante quedo sin poner")
    conn.close()


def un_tour_de_una_reserva_cancelada_no_pide_bote(c):
    """Lo mismo que ya valia para las corridas de muelle: una cancelada no viaja, y
    pedirle bote es mandar a alguien al muelle a esperar a quien no viene."""
    limpiar()
    cargar([_con_tour("800050", "MANGLAR")])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]
    c.igual(len(tr.salidas_de_tour(conn, fecha, fecha)), 1, "viva, pide bote")

    conn.execute("UPDATE reserva SET res_status = 'CANCELADA' WHERE conf_no = ?",
                 ("800050",))
    conn.commit()
    c.igual(len(tr.salidas_de_tour(conn, fecha, fecha)), 0, "cancelada, no")
    conn.close()


# ---------------------------------------------------------------------------
# La modalidad privada
# ---------------------------------------------------------------------------
#
# Lo pidio el lodge: «los tours que vienen declarados como privados... requieren guia
# separado o bote separado si corresponde, y que no se sume de manera automatica con los
# tours normales sino en una casilla resumen aparte».
#
# Es la razon de ser del producto: el huesped paga por NO compartir. Si el sistema los
# junta, se manda un bote donde hacen falta dos y alguien se queda en el muelle.

def _priv(conf_no, tour, dia=2, adl=2, privado=True):
    """Una reserva con UN tour en la modalidad que se pida."""
    return reserva(conf_no, "07", "01-01-26", "06-01-26", adl=adl,
                   operacion=[{"dia": dia, "tour": tour, "privado": privado}])


def la_modalidad_privada_llega_a_la_base(c):
    """Opera la manda pegada al codigo («PRV-PNC») y hasta ahora se perdia por el camino:
    opera_mapeo la leia, el importador no la copiaba y el cargador no la guardaba. El tour
    privado entraba a la agenda igual que uno compartido y nadie se enteraba."""
    limpiar()
    cargar([_priv("810001", "MANGLAR", privado=True),
            _priv("810002", "MANGLAR", privado=False)])
    conn = conexion()
    puestos = {f["conf_no"]: f["es_privado"] for f in conn.execute(
        "SELECT conf_no, es_privado FROM tour_asignado")}
    c.igual(puestos.get("810001"), 1, "el privado queda marcado")
    c.igual(puestos.get("810002"), 0, "y el compartido no")
    conn.close()


def el_privado_y_el_compartido_son_dos_salidas(c):
    """LO MAS IMPORTANTE. Mismo tour, mismo dia, misma hora: si se juntaran, Transporte
    enseñaria una sola corrida, se le asignaria un bote y el otro grupo no tendria
    ninguno."""
    limpiar()
    cargar([_priv("810010", "MANGLAR", privado=True),
            _priv("810011", "MANGLAR", privado=False)])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]
    lista = tr.salidas_de_tour(conn, fecha, fecha)
    c.igual(len(lista), 2, "son dos salidas, no una")
    c.igual(sorted(t["privado"] for t in lista), [False, True], "una de cada modalidad")
    c.igual([t["pax"] for t in lista], [2, 2], "y el pax NO se suma entre ellas")
    conn.close()


def el_bote_del_privado_no_se_le_pone_al_compartido(c):
    """Si la modalidad no entrara en la llave del guardado, poner el bote de uno se lo
    pondria al otro — justo lo que el huesped pago por evitar."""
    limpiar()
    cargar([_priv("810020", "MANGLAR", privado=True),
            _priv("810021", "MANGLAR", privado=False)])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]

    cuantas, problema = tr.asignar_tour(conn, fecha, "MANGLAR", "A",
                                        bote="TIBURON", privado=True)
    c.igual(problema, None, "se guarda sin problema")
    c.igual(cuantas, 1, "y toca SOLO la reserva privada")

    puestos = {f["conf_no"]: f["bote_nombre"] for f in conn.execute(
        "SELECT conf_no, bote_nombre FROM tour_asignado")}
    c.igual(puestos.get("810020"), "TIBURON", "el privado lleva el bote")
    c.igual(puestos.get("810021"), None, "y el compartido sigue sin bote")
    conn.close()


def la_capacidad_no_suma_el_privado_con_el_compartido(c):
    """El aviso de «no cabe» tiene que contar la salida de verdad. Sumando las dos
    modalidades inventaria un sobrecupo que no existe —o, peor, taparia uno que si—."""
    import validations
    limpiar()
    # MANGLAR admite 7 por guia. Cuatro privados y cuatro compartidos son 8 sumados,
    # pero cuatro y cuatro por separado: ninguna salida pasa del tope.
    cargar([_priv("810030", "MANGLAR", privado=True, adl=4),
            _priv("810031", "MANGLAR", privado=False, adl=4)])
    conn = conexion()
    uno = conn.execute(
        "SELECT id FROM tour_asignado WHERE conf_no = '810030'").fetchone()["id"]
    conn.close()
    avisos = validations.validar_tour_asignado(uno)
    c.igual([a for a in avisos if "guía" in a or "guia" in a], [],
            "no se avisa de un sobrecupo que no existe")

    # Y que el aviso SIGUE saliendo cuando el sobrecupo es de verdad. Una prueba que solo
    # comprueba el silencio no distingue «bien contado» de «dejo de contar».
    #
    # Tiene que ser UNA sola reserva privada que no cabe en un guia, no dos sumadas: dos
    # privadas del mismo dia son dos salidas con dos guias, y sumarlas seria el error que
    # la mitad de arriba acaba de descartar.
    limpiar()
    cargar([_priv("810032", "MANGLAR", privado=True, adl=8)])
    conn = conexion()
    uno = conn.execute(
        "SELECT id FROM tour_asignado WHERE conf_no = '810032'").fetchone()["id"]
    conn.close()
    avisos = validations.validar_tour_asignado(uno)
    c.cierto(any("máximo por guía" in a for a in avisos),
             "ocho en una sola salida privada si pasan del tope de un guia")
    c.cierto(any("privado" in a for a in avisos),
             "y el aviso dice que es la salida privada")


def dos_privados_del_mismo_dia_no_van_en_el_mismo_bote(c):
    """Privado quiere decir SIN NADIE MAS. Dos reservas distintas que compran el mismo
    tour privado el mismo dia son dos salidas, no una.

    No es un caso inventado: el 19 de noviembre de 2026, en los datos reales del lodge,
    el PNC privado son la habitacion 12 y la 11 —dos familias que no se conocen—. Con la
    modalidad sola en la llave se juntaban en una salida de 6 pax y se les asignaba UN
    bote, que es exactamente lo que pagaron por evitar."""
    limpiar()
    cargar([_priv("810050", "MANGLAR", privado=True),
            _priv("810051", "MANGLAR", privado=True)])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]
    lista = tr.salidas_de_tour(conn, fecha, fecha)
    c.igual(len(lista), 2, "son dos salidas privadas, no una")
    c.igual([t["pax"] for t in lista], [2, 2], "y el pax no se suma entre ellas")
    c.igual(sorted(t["conf_no"] for t in lista), ["810050", "810051"],
            "cada una dice de que reserva es")

    # Y el bote de una no se le pone a la otra.
    cuantas, problema = tr.asignar_tour(conn, fecha, "MANGLAR", "A", bote="TIBURON",
                                        privado=True, conf_no="810050")
    c.igual(problema, None, "se guarda sin problema")
    c.igual(cuantas, 1, "y toca una sola reserva")
    puestos = {f["conf_no"]: f["bote_nombre"] for f in conn.execute(
        "SELECT conf_no, bote_nombre FROM tour_asignado")}
    c.igual(puestos.get("810050"), "TIBURON", "la que se eligio lleva el bote")
    c.igual(puestos.get("810051"), None, "la otra privada sigue sin bote")
    conn.close()


def dos_compartidos_del_mismo_dia_SI_van_juntos(c):
    """La otra mitad, que es la que evita pasarse de listo: lo compartido se sigue
    juntando. Si la reserva entrara en la llave tambien para los compartidos, cada
    habitacion pediria su propio bote y el lodge mandaria cinco botes medio vacios."""
    limpiar()
    cargar([_priv("810060", "MANGLAR", privado=False),
            _priv("810061", "MANGLAR", privado=False)])
    conn = conexion()
    fecha = conn.execute("SELECT fecha FROM tour_asignado LIMIT 1").fetchone()["fecha"]
    lista = tr.salidas_de_tour(conn, fecha, fecha)
    c.igual(len(lista), 1, "las dos habitaciones comparten una sola salida")
    c.igual(lista[0]["pax"], 4, "con el pax sumado")
    c.igual(lista[0]["conf_no"], None, "y sin reserva propia: es de todas")
    conn.close()


def la_pesca_es_privada_aunque_llegue_por_la_nota(c):
    """El comunicado del lodge: la pesca deportiva «se comercializa unicamente en
    modalidad privada».

    opera_paquetes ya lo sabia, pero solo servia al leer un PAQUETE. Un tour que entra
    por la NOTA del itinerario —«dia 3: PESCA»— no trae modalidad, y asi entraron las dos
    salidas de pesca que tiene el lodge cargadas: como compartidas. En la hoja del dia se
    veia una salida abierta donde hay un charter de una sola familia."""
    limpiar()
    cargar([reserva("810070", "07", "01-01-26", "06-01-26",
                    operacion=[{"dia": 2, "tour": "PESCA"}])])
    conn = conexion()
    fila = conn.execute("SELECT tour_codigo, es_privado FROM tour_asignado").fetchone()
    c.igual(fila["tour_codigo"], "PESCA", "entra como pesca")
    c.igual(fila["es_privado"], 1, "y privada, aunque la nota no lo dijera")
    conn.close()

    # Y la contraparte: un tour que SI se vende compartido no se marca solo. Marcar de
    # mas parte en dos salidas lo que es una, y pide un guia por habitacion.
    limpiar()
    cargar([reserva("810071", "07", "01-01-26", "06-01-26",
                    operacion=[{"dia": 2, "tour": "SIRENA"}])])
    conn = conexion()
    c.igual(conn.execute("SELECT es_privado FROM tour_asignado").fetchone()[0], 0,
            "pero una SIRENA por la nota no se marca sola: tambien se vende compartida")
    conn.close()


# Los que el lodge nombro uno por uno: «cuando sean tours terrestres (CABALGATA, CLARO,
# CLW, GTT, HDA, NGW, NW, PAJAREO, PARED, PNC, PNC PRIVADO, PRV-SIR, TREENET) no solicite
# bote o capitan ya que no necesita, y en el modulo de transporte no aparezcan estos
# tours ya que no necesitan transporte».
#
# PARED no es un codigo del catalogo: es como se le dice de palabra a CLW, la pared de
# escalada. Entra como alias, no como tour nuevo.
# PRV-SIR tampoco: es el codigo de Opera del Sirena privado, que se guarda como SIRENA
# con la marca de privado. Queda fuera de esta lista a proposito — ver el comentario de
# TOURS_QUE_VAN_POR_TIERRA.
TERRESTRES = ["CABALGATA", "CLARO", "CLW", "GTT", "HDA", "NGW", "NW", "PAJAREO",
              "PNC", "PNC PRIVADO", "TREENET"]


def los_tours_terrestres_no_piden_bote(c):
    """Lo que el lodge nombro uno por uno. El que mas pesa es PNC: es el tour mas comun
    —137 salidas cargadas— y pedia bote, capitan y ayudante todos los dias."""
    conn = base_limpia()
    piden = {r["codigo"]: r["requiere_bote"] for r in conn.execute(
        "SELECT codigo, requiere_bote FROM tour_catalogo")}
    for codigo in TERRESTRES:
        c.igual(piden.get(codigo), 0, f"{codigo} no pide bote")
    # Y la contraparte, que es la que evita pasarse: los que SI van en bote siguen
    # pidiendolo. Una lista que apaga todo no se distingue de una bien hecha.
    for codigo in ("SNORKEL", "ISLA", "MANGLAR", "BALLENAS", "PESCA"):
        c.igual(piden.get(codigo), 1, f"{codigo} sigue pidiendo bote")
    conn.close()


def la_base_ya_instalada_tambien_se_corrige(c):
    """EL CAMINO DE PRODUCCION, que es el unico que importa aqui.

    Cambiar la tupla del catalogo solo sirve para una base NUEVA: el sembrado es un
    INSERT OR IGNORE, asi que en la base del lodge —que ya tiene PNC con bote— no cambia
    nada. La correccion la hace _corregir_tours_por_tierra al arrancar.

    Y corre UNA SOLA VEZ: el catalogo se edita desde la pantalla, asi que si corriera en
    cada arranque, el dia que alguien marcara un tour como de bote a proposito el sistema
    se lo desharia solo al reiniciar."""
    import init_db
    conn = base_limpia()
    # Se simula la base instalada: PNC con bote y sin la marca de correccion.
    conn.execute("UPDATE tour_catalogo SET requiere_bote = 1 "
                 "WHERE codigo IN ('PNC','PNC PRIVADO')")
    conn.execute("DELETE FROM sistema_meta WHERE clave = ?", (init_db._MARCA_TIERRA,))
    conn.commit()

    init_db._corregir_tours_por_tierra(conn)
    piden = {r["codigo"]: r["requiere_bote"] for r in conn.execute(
        "SELECT codigo, requiere_bote FROM tour_catalogo")}
    c.igual(piden.get("PNC"), 0, "la base instalada queda corregida")
    c.igual(piden.get("PNC PRIVADO"), 0, "la version privada tambien")

    # Y si el lodge lo vuelve a poner a mano, no se le deshace al reiniciar.
    conn.execute("UPDATE tour_catalogo SET requiere_bote = 1 WHERE codigo = 'PNC'")
    conn.commit()
    init_db._corregir_tours_por_tierra(conn)
    c.igual(conn.execute(
        "SELECT requiere_bote FROM tour_catalogo WHERE codigo = 'PNC'").fetchone()[0], 1,
        "lo que el lodge cambie a mano se respeta")
    conn.close()


def un_tour_terrestre_no_sale_en_transporte(c):
    """Transporte es la pantalla de lo que se mueve en bote. Una caminata ahi es una
    fila que nunca se va a poder cerrar: no hay bote que asignarle."""
    limpiar()
    cargar([_con_tour("810080", "PNC"),          # terrestre
            _con_tour("810081", "SNORKEL")])     # va en bote
    conn = conexion()
    fechas = [f["fecha"] for f in conn.execute(
        "SELECT DISTINCT fecha FROM tour_asignado ORDER BY fecha")]
    lista = tr.salidas_de_tour(conn, min(fechas), max(fechas))
    c.igual(sorted(t["tour_codigo"] for t in lista), ["SNORKEL"],
            "solo sale el que va en bote")
    conn.close()


def el_kayak_de_san_josecito_va_en_bote(c):
    """Lo corrigio el lodge: «el tour de kayak es un tour de bote y lo estas tomando como
    terrestre».

    Entro al catalogo con la nomenclatura 2027 (KSJ, «Kayak a San Josecito») y ahi se
    dejo sin bote a proposito: ese comunicado da el nombre y la modalidad, no la
    operacion, y se prefirio no inventar. Pero a San Josecito se va por mar, y sin la
    marca el tour NO SALIA en Transporte: no habia donde asignarle bote, capitan ni
    ayudante. Un tour que no aparece en la pantalla no deja hueco donde mirar — es la
    forma de faltar que nadie reporta.
    """
    conn = base_limpia()
    c.igual(conn.execute(
        "SELECT requiere_bote FROM tour_catalogo WHERE codigo = 'SAN JOSECITO'"
    ).fetchone()[0], 1, "el catalogo nuevo ya lo trae con bote")
    conn.close()

    # Y de punta a punta: que aparezca en Transporte, que es para lo que sirve la marca.
    limpiar()
    cargar([_con_tour("810082", "SAN JOSECITO"),
            _con_tour("810083", "PNC")])             # terrestre, para no pasarse
    conn = conexion()
    fechas = [f["fecha"] for f in conn.execute(
        "SELECT DISTINCT fecha FROM tour_asignado ORDER BY fecha")]
    lista = tr.salidas_de_tour(conn, min(fechas), max(fechas))
    c.igual(sorted(t["tour_codigo"] for t in lista), ["SAN JOSECITO"],
            "sale en Transporte, y la caminata sigue sin salir")
    conn.close()


def la_base_ya_instalada_tambien_recibe_el_bote_del_kayak(c):
    """EL CAMINO DE PRODUCCION. Cambiar la tupla del catalogo solo sirve para una base
    NUEVA: el sembrado es un INSERT OR IGNORE, asi que en la base del lodge —que ya tiene
    San Josecito sin bote— no cambiaria nada."""
    import init_db
    conn = base_limpia()
    # Se simula la base instalada: sin bote y sin la marca de correccion.
    conn.execute("UPDATE tour_catalogo SET requiere_bote = 0 "
                 "WHERE codigo = 'SAN JOSECITO'")
    conn.execute("DELETE FROM sistema_meta WHERE clave = ?", (init_db._MARCA_BOTE,))
    conn.commit()

    init_db._corregir_tours_en_bote(conn)
    c.igual(conn.execute(
        "SELECT requiere_bote FROM tour_catalogo WHERE codigo = 'SAN JOSECITO'"
    ).fetchone()[0], 1, "la base instalada queda corregida")

    # Y si el lodge lo quita a mano, no se le vuelve a poner al reiniciar.
    conn.execute("UPDATE tour_catalogo SET requiere_bote = 0 "
                 "WHERE codigo = 'SAN JOSECITO'")
    conn.commit()
    init_db._corregir_tours_en_bote(conn)
    c.igual(conn.execute(
        "SELECT requiere_bote FROM tour_catalogo WHERE codigo = 'SAN JOSECITO'"
    ).fetchone()[0], 0, "lo que el lodge cambie a mano se respeta")
    conn.close()


def la_pared_de_escalada_se_reconoce_por_su_nombre(c):
    """«PARED» es como se le dice en el lodge a CLW. Sin el alias, una reserva que lo
    escriba asi no encuentra codigo y la actividad no llega a la agenda: se avisa como
    «tour sin catalogo» y alguien tiene que ir a corregir la nota."""
    limpiar()
    cargar([reserva("810090", "07", "01-01-26", "06-01-26",
                    operacion=[{"dia": 2, "tour": "PARED"}])])
    conn = conexion()
    fila = conn.execute("SELECT tour_codigo FROM tour_asignado").fetchone()
    c.cierto(fila is not None, "la actividad llega a la agenda")
    if fila:
        c.igual(fila["tour_codigo"], "CLW", "y entra como la pared de escalada")
    c.igual(len(comun.alertas(conn, "TOUR_SIN_CATALOGO")), 0,
            "sin avisar de un codigo que no existe")
    conn.close()


def el_codigo_privado_del_catalogo_tambien_cuenta(c):
    """La otra via: un PDF escribe «PNC PRIVADO», que el catalogo ya marca como privado.
    Si solo se mirara la marca de Opera, esa fila se contaria con las compartidas."""
    limpiar()
    cargar([reserva("810040", "07", "01-01-26", "06-01-26",
                    operacion=[{"dia": 2, "tour": "PNC PRIVADO"}])])
    conn = conexion()
    fila = conn.execute(
        "SELECT tour_codigo, es_privado FROM tour_asignado").fetchone()
    c.igual(fila["tour_codigo"], "PNC PRIVADO", "entra con su codigo")
    c.igual(fila["es_privado"], 1, "y marcado como privado sin que Opera lo dijera")
    conn.close()


# ---------------------------------------------------------------------------
# El BT: el viaje de bote EXTRA que pide una reserva
# ---------------------------------------------------------------------------
#
# Lo pidio el lodge: «existe una nomenclatura denominada BT (boat transfer), cuando en
# alguna reserva aparezca esta debe ser cargada en la parte de transporte para ser
# asignada el capitan o ayudante correspondiente».
#
# Transporte armaba sus corridas con el punto de ENTRADA y el de SALIDA, asi que un BT
# no aparecia en ninguna parte: nadie le asignaba bote ni capitan y el dia del viaje
# habia que acordarse.

# Los dos textos REALES del lodge. Se copian enteros a proposito: lo que decide si esto
# funciona es la forma de escribirlo, y un ejemplo limpio no prueba nada.
BT_HAB_09 = ("Clientes solicitan BT el 08 para tour con Pacheco. Llegan a las 6:25 AM "
             "y regresan a las 2:00 PM · C-EBT 07/11")
BT_HAB_08 = ("Para el 25 solicitan BT roundtrip  a un bote de unos amigos que van para "
             "Sirena. Llegan por ellos cerca de la orilla a las 6:20 AM")


def el_dia_del_BT_sale_del_itinerario_no_del_texto(c):
    """EL DIA LO DA EL ITINERARIO, y esto es lo que hace fiable todo lo demas.

    La reserva escribe «08: BT» en su linea de operacion, igual que un tour. Deducirlo
    de una frase suelta no es fiable —un numero en una nota puede ser un precio, un
    vuelo o una hora— y, medido sobre las reservas reales, ademas repetia el mismo viaje
    una vez por cada campo donde la nota aparecia: la habitacion 09 salia con CINCO
    corridas donde hay dos, y con el pax duplicado."""
    import boat_transfer as bt

    viajes, avisos = bt.leer(["08"], BT_HAB_09, "2026-11-06", "2026-11-11")
    c.igual(avisos, [], "la hab 09 se entiende entera")
    c.igual([(v["fecha"], v["hora"]) for v in viajes],
            [("2026-11-08", "06:25"), ("2026-11-08", "14:00")],
            "ida y vuelta el dia 8: son DOS movimientos de bote")

    viajes, _ = bt.leer(["25"], BT_HAB_08, "2026-11-25", "2026-11-28")
    c.igual([(v["fecha"], v["hora"]) for v in viajes], [("2026-11-25", "06:20")],
            "y uno solo para la hab 08, que trae una sola hora")

    # El MISMO dia nombrado dos veces no son dos viajes: la nota llega por varios campos.
    viajes, _ = bt.leer(["08", "08"], BT_HAB_09, "2026-11-06", "2026-11-11")
    c.igual(len(viajes), 2, "el dia repetido no duplica las corridas")


def el_parser_recoge_el_BT_del_itinerario(c):
    """La linea «08: BT» se perdia EN SILENCIO: «BT» tiene dos letras y el aviso de
    actividad no reconocida pide mas de dos. Asi que el viaje no llegaba a Transporte y
    nadie le asignaba bote ni capitan — sin ningun error de por medio."""
    import pdf_parser
    leido = pdf_parser.leer_texto_de_reserva(
        "Operacion:\n06: In\n07: C-EBT\n08: BT\n11: Out\n")
    dias = [x["dia"] for x in (leido.get("traslados_extra") or [])]
    c.igual(dias, ["08"], "el BT del itinerario se recoge, con su dia")
    # «C-EBT» NO es un BT: es el aviso de cama o almohada extra, y esta en la linea de
    # al lado en la misma reserva.
    c.igual(len(leido.get("traslados_extra") or []), 1,
            "y «C-EBT» no se confunde con uno")


def un_BT_sin_dia_no_se_inventa(c):
    """El error caro de esta pantalla. Un bote preparado el dia que no era cuesta lo
    mismo que no prepararlo, y encima nadie lo revisa porque la pantalla ya decia que
    estaba cubierto. Se avisa y que recepcion lo escriba en el itinerario."""
    import boat_transfer as bt

    viajes, avisos = bt.leer([], "Clientes solicitan BT para ir al pueblo",
                             "2026-11-06", "2026-11-11")
    c.igual(viajes, [], "sin dia en el itinerario no se crea ninguna corrida")
    c.igual(len(avisos), 1, "pero se avisa, que es lo que hace que alguien lo escriba")

    # Y NO se avisa cuando el BT viene incluido en la tarifa: ahi no hay nada extra que
    # preparar, y los avisos falsos enseñan a ignorar los de verdad.
    viajes, avisos = bt.leer([], "PAQUETE 3N/4D+FULL BOARD BT INCLUDED PNC + CIS",
                             "2026-11-06", "2026-11-11")
    c.igual(viajes, [], "el BT del paquete no es un viaje extra")
    c.igual(avisos, [], "y no se avisa de el")

    # Un dia del itinerario que no cae en la estadia tampoco se usa.
    viajes, avisos = bt.leer(["28"], "Solicitan BT", "2026-11-06", "2026-11-11")
    c.igual(viajes, [], "un dia fuera de la estadia no se usa")
    c.igual(len(avisos), 1, "tambien se avisa")

    # Sin hora SI se crea: la corrida sale «sin hora» y la pantalla lo señala, que es
    # distinto de inventarsela.
    viajes, _ = bt.leer(["09"], "Solicitan BT para ir a Drake",
                        "2026-11-06", "2026-11-11")
    c.igual([(v["fecha"], v["hora"]) for v in viajes], [("2026-11-09", None)],
            "sin hora la corrida existe igual, marcada")


def el_BT_sale_en_transporte_y_se_le_asigna_capitan(c):
    """De punta a punta por el camino REAL de carga, que es lo que pidio el lodge:
    que aparezca en Transporte para poder asignarle capitan."""
    limpiar()
    dia = HOY + datetime.timedelta(days=2)
    r = dict(reserva(720100, "09", ddmmyy(HOY),
                     ddmmyy(HOY + datetime.timedelta(days=5)), adl=2),
             punto_entrada="Sierpe",
             # El dia sale del ITINERARIO, como lo escribe la reserva de verdad.
             traslados_extra=[{"dia": f"{dia.day:02d}"}],
             notas=("Clientes solicitan BT para tour con Pacheco. "
                    "Llegan a las 6:25 AM y regresan a las 2:00 PM"))
    cargar([r], vistas=[r])

    conn = conexion()
    guardados = [dict(x) for x in conn.execute(
        "SELECT fecha, hora, nota FROM traslado_extra ORDER BY hora")]
    c.igual(len(guardados), 2, "se guardan los dos viajes del BT")
    if guardados:
        c.igual(guardados[0]["fecha"], dia.isoformat(), "el dia que dice la nota")
        c.cierto("Pacheco" in (guardados[0]["nota"] or ""),
                 "con el texto de la reserva, que es lo que necesita quien lo coordina")

    lista = [x for x in tr.corridas(conn, iso(dia), iso(dia)) if x["tipo"] == "extra"]
    c.igual(len(lista), 2, "y salen DOS corridas en Transporte")
    if lista:
        c.igual(lista[0]["punto"], "09", "identificadas por su habitacion")
        c.cierto("capitán" in lista[0]["falta"], "pidiendo capitan, como cualquier corrida")

        # Y se les puede asignar, que es para lo que estan.
        k = lista[0]
        ok, problema = tr.asignar(conn, k["fecha"], "extra", k["punto"], k["hora"],
                                  bote="TIBURON", capitan="WILL")
        c.igual(problema, None, "se puede asignar bote y capitan")
        de_nuevo = [x for x in tr.corridas(conn, iso(dia), iso(dia))
                    if x["tipo"] == "extra" and x["hora"] == k["hora"]]
        c.igual(de_nuevo[0]["capitan_nombre"], "WILL", "y queda guardado")
        # La OTRA corrida del mismo dia no se toca: son dos viajes distintos.
        otra = [x for x in tr.corridas(conn, iso(dia), iso(dia))
                if x["tipo"] == "extra" and x["hora"] != k["hora"]]
        c.igual(otra[0]["capitan_nombre"], None, "sin tocar el otro viaje del dia")
    conn.close()


def el_BT_de_una_cancelada_no_pide_bote(c):
    """Lo mismo que ya valia para las demas corridas: una cancelada no viaja."""
    limpiar()
    dia = HOY + datetime.timedelta(days=2)
    r = dict(reserva(720110, "09", ddmmyy(HOY),
                     ddmmyy(HOY + datetime.timedelta(days=5)), adl=2),
             punto_entrada="Sierpe",
             traslados_extra=[{"dia": f"{dia.day:02d}"}],
             notas="Solicitan BT a las 7:00 AM")
    cargar([r], vistas=[r])
    conn = conexion()
    c.igual(len([x for x in tr.corridas(conn, iso(dia), iso(dia))
                 if x["tipo"] == "extra"]), 1, "viva, el BT pide bote")

    conn.execute("UPDATE reserva SET res_status = 'CANCELADA' WHERE conf_no = '720110'")
    conn.commit()
    c.igual(len([x for x in tr.corridas(conn, iso(dia), iso(dia))
                 if x["tipo"] == "extra"]), 0, "cancelada, no")
    conn.close()


PRUEBAS = [
    los_que_van_a_la_misma_hora_van_juntos,
    horas_distintas_son_corridas_distintas,
    sierpe_y_drake_no_se_mezclan,
    la_entrada_y_la_salida_son_corridas_distintas,
    sierpe_usa_el_horario_fijo_del_bote,
    por_sierpe_la_hora_fija_manda_sobre_la_de_la_reserva,
    por_drake_el_ingreso_lleva_la_hora_del_vuelo_sin_tocar,
    el_que_no_tiene_hora_no_se_esconde,
    una_reserva_cancelada_sale_de_su_corrida,
    se_asigna_guia_y_bote_a_una_corrida,
    se_asigna_capitan_y_ayudante_a_una_corrida,
    nadie_va_de_capitan_y_de_ayudante_a_la_vez,
    sin_capitan_se_cuenta_pero_sin_ayudante_no,
    los_capitanes_del_lodge_estan_en_el_catalogo,
    solo_los_tours_que_llevan_bote_salen_en_transporte,
    el_tour_se_agrupa_por_fecha_tour_y_grupo,
    el_bote_se_le_pone_al_grupo_entero,
    el_guia_del_tour_no_se_toca_desde_transporte,
    nadie_va_de_capitan_y_de_ayudante_en_la_misma_salida_de_tour,
    un_tour_de_una_reserva_cancelada_no_pide_bote,
    la_modalidad_privada_llega_a_la_base,
    el_privado_y_el_compartido_son_dos_salidas,
    el_bote_del_privado_no_se_le_pone_al_compartido,
    la_capacidad_no_suma_el_privado_con_el_compartido,
    dos_privados_del_mismo_dia_no_van_en_el_mismo_bote,
    dos_compartidos_del_mismo_dia_SI_van_juntos,
    la_pesca_es_privada_aunque_llegue_por_la_nota,
    los_tours_terrestres_no_piden_bote,
    la_base_ya_instalada_tambien_se_corrige,
    un_tour_terrestre_no_sale_en_transporte,
    el_kayak_de_san_josecito_va_en_bote,
    la_base_ya_instalada_tambien_recibe_el_bote_del_kayak,
    la_pared_de_escalada_se_reconoce_por_su_nombre,
    el_dia_del_BT_sale_del_itinerario_no_del_texto,
    el_parser_recoge_el_BT_del_itinerario,
    un_BT_sin_dia_no_se_inventa,
    el_BT_sale_en_transporte_y_se_le_asigna_capitan,
    el_BT_de_una_cancelada_no_pide_bote,
    el_codigo_privado_del_catalogo_tambien_cuenta,
    dejar_sin_asignar_es_distinto_de_no_mandar_el_dato,
    no_se_asigna_a_un_punto_inventado,
    cambiar_la_hora_del_vuelo_deja_la_corrida_sin_asignar,
    se_avisa_si_no_cabe_la_gente_en_el_bote,
    un_bote_privado_no_tiene_tope,
    el_mismo_bote_puede_hacer_varios_viajes_al_dia,
    el_mismo_bote_no_puede_estar_en_dos_lados_a_la_vez,
    los_externos_se_pueden_repetir,
    la_misma_hora_escrita_distinto_es_la_misma_hora,
    las_corridas_salen_ordenadas_por_hora_real,
    sin_hora_no_se_inventan_choques,
    el_resumen_cuenta_lo_que_falta_cubrir,
]


if __name__ == "__main__":
    sys.exit(comun.correr("traslados", PRUEBAS))
