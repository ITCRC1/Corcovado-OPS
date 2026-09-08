"""Fija las reglas con las que entran a la base las actualizaciones de Opera.

POR QUÉ EXISTE ESTA SUITE. El 2026-09-07 el hotel reportó que las reservas no
aparecían en el restaurante —solo la habitación 7— y que en Reservas salían como
canceladas. La causa: la regla que marca CANCELADA lo que la fuente dejó de reportar
comparaba contra EL LOTE (lo que cambió en ese ciclo) en vez de contra EL UNIVERSO
(todo lo que la fuente vio). Opera carga solo lo que cambió, a propósito, así que
bastaba que una reserva del día cambiara para que las demás llegadas de esa fecha
quedaran canceladas. La que sobrevivía era justamente la que había cambiado.

Ese fallo no da ningún error: deja la agenda a medias y se ve plausible. Nadie lo nota
hasta que un huésped se presenta en la puerta y no está en la lista. De ahí que estas
comprobaciones estén escritas y no dependan de que alguien se acuerde de mirar.

Cada prueba nombra la regla que fija. Si una falla, el mensaje dice qué se rompió sin
tener que leer el código.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402
from comun import alertas, base_limpia, cargar, conexion, estados, reserva  # noqa: E402

HOY = datetime.date.today()


def ddmmyy(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


LLEGADA = ddmmyy(HOY + datetime.timedelta(days=10))
SALIDA = ddmmyy(HOY + datetime.timedelta(days=13))


# ---------------------------------------------------------------------------

def un_lote_parcial_no_cancela_lo_que_la_fuente_sigue_viendo(c):
    """LA REGLA CENTRAL, y la que se rompió.

    Seis reservas llegan el mismo día. En el ciclo siguiente cambian cuatro. El lote
    trae esas cuatro; el universo sigue siendo las seis. Ninguna se cancela.

    El escenario está elegido para que la válvula NO pueda salvarlo: con 4 reportadas
    y 2 ausentes, 2 no es mayor que 4, así que la válvula se queda callada. Si alguien
    volviera a pasar el lote como universo, esta prueba falla — que es de lo que se
    trata.
    """
    conn = base_limpia()
    todas = [reserva(600000 + i, f"{i:02d}", LLEGADA, SALIDA) for i in range(1, 7)]
    cargar(todas, vistas=todas)
    c.igual(len(estados(conn)), 6, "las seis reservas entraron")

    cambiadas = [dict(r, opera_modificado_en="2026-09-08T08:00:00Z") for r in todas[:4]]
    cargar(cambiadas, vistas=todas)

    vivas = [k for k, v in estados(conn).items() if v != "CANCELADA"]
    c.igual(sorted(vivas), sorted(str(600000 + i) for i in range(1, 7)),
            "un lote parcial NO debe cancelar a las reservas que la fuente sigue viendo")
    c.igual(alertas(conn, "RESERVA_CANCELADA"), [],
            "no se debe inventar ningun aviso de cancelacion")
    conn.close()


def una_descarga_incompleta_no_cancela_nada(c):
    """Si no se pudo garantizar que la descarga vino completa, no se cancela.

    'No vino en el lote' solo significa 'cancelada' cuando se sabe que la lista estaba
    completa. Con una lista parcial significa 'falta'.
    """
    conn = base_limpia()
    todas = [reserva(610000 + i, f"{i:02d}", LLEGADA, SALIDA) for i in range(1, 5)]
    cargar(todas, vistas=todas)

    # Opera respondió a medias: solo se vio una, y 'completo' vino en False.
    cargar([todas[0]], vistas=[todas[0]], completo=False)

    c.igual(sorted(v for v in estados(conn).values()), ["POR INGRESAR"] * 4,
            "con la descarga incompleta no se debe cancelar ninguna")
    conn.close()


def la_valvula_frena_una_cancelacion_masiva(c):
    """La segunda línea: si desaparecieron más de las que la fuente reportó, no se toca nada.

    Es una red por si vuelve a colarse un error en el cálculo del universo. No debe
    saltar nunca con datos buenos, y cuando salta tiene que dejar aviso.
    """
    conn = base_limpia()
    todas = [reserva(620000 + i, f"{i:02d}", LLEGADA, SALIDA) for i in range(1, 6)]
    cargar(todas, vistas=todas)

    # Universo mal calculado: dice haber visto solo una de las cinco.
    cargar([todas[0]], vistas=[todas[0]])

    c.igual(sorted(set(estados(conn).values())), ["POR INGRESAR"],
            "la valvula debe dejar las reservas como estaban")
    c.igual(len(alertas(conn, "CANCELACION_SOSPECHOSA")), 1,
            "la valvula tiene que dejar un aviso, no callarse")
    conn.close()


def una_cancelacion_de_verdad_si_se_refleja(c):
    """Lo que NO se puede perder por protegerse: cuando Opera cancela, el sistema cancela.

    Una prueba que solo comprobara "no cancela nunca" se pasaría poniendo la regla en
    falso, y entonces una reserva cancelada de verdad seguiría ocupando mesa y bote.
    """
    conn = base_limpia()
    a, b = reserva(630001, "01", LLEGADA, SALIDA), reserva(630002, "02", LLEGADA, SALIDA)
    cargar([a, b], vistas=[a, b])

    # Opera reporta la 630002 como cancelada.
    b_cancelada = dict(b, res_status="CANCELADA",
                       opera_modificado_en="2026-09-08T09:00:00Z")
    cargar([b_cancelada], vistas=[a, b_cancelada])

    e = estados(conn)
    c.igual(e.get("630001"), "POR INGRESAR", "la que sigue viva no se toca")
    c.igual(e.get("630002"), "CANCELADA", "la que Opera cancelo tiene que quedar cancelada")
    conn.close()


def la_que_la_fuente_deja_de_reportar_se_cancela(c):
    """El caso del PDF: trae la hoja completa, así que su lote ES su universo.

    Sin 'vistas_por_la_fuente' la regla usa el lote. Eso es correcto para una fuente
    que entrega todo, y hay que dejarlo funcionando.
    """
    conn = base_limpia()
    todas = [reserva(640000 + i, f"{i:02d}", LLEGADA, SALIDA) for i in range(1, 6)]
    cargar(todas, vistas=todas)

    # El reporte actualizado ya no trae la 640005 ni la 640004; sí las otras tres.
    # Ausentes = 2, reportadas = 3, así que la valvula no se interpone.
    cargar(todas[:3], vistas=None, manda_en="TODO", fuente="Arrivals__Detailed.PDF")

    e = estados(conn)
    c.igual([e.get(f"64000{i}") for i in (1, 2, 3)],
            ["POR INGRESAR"] * 3, "las que el reporte sigue trayendo quedan vivas")
    c.igual([e.get("640004"), e.get("640005")], ["CANCELADA", "CANCELADA"],
            "las que el reporte completo dejo de traer se cancelan")
    c.igual(len(alertas(conn, "RESERVA_CANCELADA")), 2,
            "cada cancelacion deja su aviso para revisar tours y entradas")
    conn.close()


def una_reserva_que_revive_recupera_su_estado_y_retira_el_aviso(c):
    """Resurrección: la base la tenía por cancelada y la fuente la reporta viva.

    Pasa cuando la cancelación era falsa o cuando en Opera la reinstalaron. En los dos
    casos el aviso que quedó colgado ya no dice nada cierto.
    """
    conn = base_limpia()
    todas = [reserva(650000 + i, f"{i:02d}", LLEGADA, SALIDA) for i in range(1, 6)]
    cargar(todas, vistas=todas)
    cargar(todas[:3], vistas=None, manda_en="TODO")     # cancela la 4 y la 5
    c.igual(estados(conn).get("650004"), "CANCELADA", "quedo cancelada para la prueba")
    c.cierto(alertas(conn, "RESERVA_CANCELADA"), "y con su aviso puesto")

    # Opera la vuelve a reportar viva.
    revivida = dict(todas[3], opera_modificado_en="2026-09-08T11:00:00Z")
    cargar([revivida], vistas=todas)

    c.igual(estados(conn).get("650004"), "POR INGRESAR",
            "la reserva que Opera reporta viva tiene que volver a estar viva")
    c.cierto(not any("650004" in m for m in alertas(conn, "RESERVA_CANCELADA")),
             "su aviso de cancelacion tiene que quedar retirado")
    conn.close()


def se_recarga_la_cancelada_que_opera_reporta_viva_aunque_no_haya_cambiado(c):
    """La salida del callejón sin salida.

    El ciclo normal solo procesa lo que cambió. Una reserva mal cancelada en la base
    cuya marca de Opera coincide se daría por "sin cambios" y no se volvería a mirar
    nunca: la cancelación falsa se quedaría puesta para siempre. Por eso el estado
    entra en la comparación, no solo la marca.
    """
    conn = base_limpia()
    import opera_sync

    viva = reserva(660001, "01", LLEGADA, SALIDA, marca="2026-09-01T10:00:00Z")
    mal_cancelada = reserva(660002, "02", LLEGADA, SALIDA, marca="2026-09-01T10:00:00Z")
    cargar([viva, mal_cancelada], vistas=[viva, mal_cancelada])
    conn.execute("UPDATE reserva SET res_status='CANCELADA' WHERE conf_no='660002'")
    conn.commit()

    # Opera reporta las dos vivas, con la MISMA marca que ya está guardada.
    nuevas, cambiadas, iguales = opera_sync._separar_por_cambio([viva, mal_cancelada])

    c.igual([r["conf_no"] for r in cambiadas], ["660002"],
            "la mal cancelada tiene que recargarse aunque su marca no haya cambiado")
    c.igual([r["conf_no"] for r in iguales], ["660001"],
            "la que esta bien y no cambio no se recarga")
    c.igual(nuevas, [], "ninguna es nueva")
    conn.close()


def el_nucleo_de_opera_no_borra_el_trabajo_de_recepcion(c):
    """Una fuente parcial escribe lo suyo y no toca lo demás.

    Es el otro fallo silencioso del mismo cargador: al sincronizar se perdían los
    tours, el régimen, las notas y el punto de embarque de una reserva con trabajo
    hecho. Sin dar error — la reserva quedaba correcta y el resto en blanco.
    """
    conn = base_limpia()
    r = reserva(670001, "01", LLEGADA, SALIDA)
    cargar([r], vistas=[r])

    conn.execute(
        """UPDATE reserva SET regimen='PENSION_COMPLETA', nota_ingreso='Llega en bote 6pm',
                              punto_entrada='SIERPE'
           WHERE conf_no='670001'""")
    conn.commit()

    # Un ciclo en el que Opera solo manda el núcleo (la propiedad dejó de entregar
    # los bloques de notas y paquetes).
    cambiada = dict(r, room_no="09", opera_modificado_en="2026-09-08T12:00:00Z")
    cargar([cambiada], vistas=[cambiada], manda_en="NUCLEO")

    f = dict(conn.execute(
        "SELECT room_no, regimen, nota_ingreso, punto_entrada FROM reserva "
        "WHERE conf_no='670001'").fetchone())
    c.igual(f["room_no"], "09", "el nucleo si se actualiza")
    c.igual(f["regimen"], "PENSION_COMPLETA", "el regimen no se debe borrar")
    c.igual(f["nota_ingreso"], "Llega en bote 6pm", "las notas no se deben borrar")
    c.igual(f["punto_entrada"], "SIERPE", "el punto de embarque no se debe borrar")
    conn.close()


def la_hoja_del_restaurante_solo_cuenta_las_reservas_vivas(c):
    """De punta a punta: es la pantalla donde el hotel vio el problema.

    El reparto excluye lo CANCELADA, así que una cancelación falsa se ve como una hoja
    a medias. Se comprueba aquí para que la conexión entre las dos cosas quede fijada.
    """
    conn = base_limpia()
    import restaurantes

    llega, sale = ddmmyy(HOY), ddmmyy(HOY + datetime.timedelta(days=3))
    todas = [reserva(680000 + i, f"{i:02d}", llega, sale, adl=2) for i in range(1, 5)]
    cargar(todas, vistas=todas)

    d = restaurantes.distribuir(conn, HOY)
    en_cena = sorted(x["room_no"] for x in
                     d["cena"]["terra_kitchen"] + d["cena"]["bar_el_bosque"])
    c.igual(en_cena, ["01", "02", "03", "04"], "las cuatro vivas van a la cena")
    c.igual(d["cena"]["total"], 8, "y suman sus 8 pax")

    conn.execute("UPDATE reserva SET res_status='CANCELADA' WHERE conf_no='680002'")
    conn.commit()

    d = restaurantes.distribuir(conn, HOY)
    en_cena = sorted(x["room_no"] for x in
                     d["cena"]["terra_kitchen"] + d["cena"]["bar_el_bosque"])
    c.igual(en_cena, ["01", "03", "04"], "una cancelada desaparece de la cena")
    c.igual(d["cena"]["total"], 6, "y su pax deja de contar")
    conn.close()


PRUEBAS = [
    un_lote_parcial_no_cancela_lo_que_la_fuente_sigue_viendo,
    una_descarga_incompleta_no_cancela_nada,
    la_valvula_frena_una_cancelacion_masiva,
    una_cancelacion_de_verdad_si_se_refleja,
    la_que_la_fuente_deja_de_reportar_se_cancela,
    una_reserva_que_revive_recupera_su_estado_y_retira_el_aviso,
    se_recarga_la_cancelada_que_opera_reporta_viva_aunque_no_haya_cambiado,
    el_nucleo_de_opera_no_borra_el_trabajo_de_recepcion,
    la_hoja_del_restaurante_solo_cuenta_las_reservas_vivas,
]

if __name__ == "__main__":
    sys.exit(comun.correr("carga de Opera", PRUEBAS))
