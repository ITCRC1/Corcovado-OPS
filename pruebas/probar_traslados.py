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
    c.igual(lista[0]["falta"], ["guía", "bote"], "arranca sin nada asignado")

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
    c.igual(lista[0]["falta"], [], "y ya no falta nada")
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
        c.igual(lista[0]["falta"], ["guía", "bote"], "marcada como que falta cubrirla")
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


PRUEBAS = [
    los_que_van_a_la_misma_hora_van_juntos,
    horas_distintas_son_corridas_distintas,
    sierpe_y_drake_no_se_mezclan,
    la_entrada_y_la_salida_son_corridas_distintas,
    sierpe_usa_el_horario_fijo_del_bote,
    el_que_no_tiene_hora_no_se_esconde,
    una_reserva_cancelada_sale_de_su_corrida,
    se_asigna_guia_y_bote_a_una_corrida,
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
