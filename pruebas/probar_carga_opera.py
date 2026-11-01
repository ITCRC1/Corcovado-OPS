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


def una_cancelada_sale_de_la_operacion(c):
    """Lo pidio el lodge: «todas las reservas que esten canceladas, es mejor que no
    aparezcan en la operacion».

    Y tenia mas razon de la que parece. Medido sobre la ventana real: la alerta «PNC el
    27 de noviembre tiene 14 pax, hacen falta 2 guias» salia de SIETE reservas canceladas
    y NINGUNA viva. Recepcion iba a repartir dos guias para un tour al que no va nadie.

    Se comprueban los DOS caminos de cancelacion, porque son distintos: la que llega ya
    cancelada en el lote, y la que se cancela porque la fuente dejo de reportarla."""
    conn = base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=4))

    dia = (HOY + datetime.timedelta(days=1)).strftime("%d")
    con_tour = {"operacion": [{"dia": dia, "tour": "PNC"}],
                "notas": "Favor colocar cuna en la habitacion"}
    a = dict(reserva(690001, "01", llega, sale, adl=2), **con_tour)
    b = dict(reserva(690002, "02", llega, sale, adl=2), **con_tour)
    cargar([a, b], vistas=[a, b])

    def cuenta(tabla, conf):
        return conn.execute(f"SELECT COUNT(*) n FROM {tabla} WHERE conf_no = ?",
                            (conf,)).fetchone()["n"]

    c.cierto(cuenta("tour_asignado", "690001") > 0, "la viva tiene su tour")
    c.cierto(cuenta("tour_asignado", "690002") > 0, "y la otra tambien, por ahora")
    c.cierto(cuenta("amenidad_tarea", "690002") > 0, "y su amenidad")

    # --- Camino 1: Opera la reporta CANCELADA ---
    b_cancelada = dict(b, res_status="CANCELADA")
    cargar([b_cancelada], vistas=[a, b_cancelada])

    c.igual(cuenta("tour_asignado", "690002"), 0,
            "la cancelada deja de ocupar la agenda de tours")
    c.igual(cuenta("amenidad_tarea", "690002"), 0,
            "y deja de pedirle trabajo a un departamento")
    c.igual(cuenta("itinerario", "690002"), 0, "y su itinerario no se le muestra a nadie")
    c.cierto(cuenta("tour_asignado", "690001") > 0,
            "pero la que sigue viva conserva el SUYO")

    # --- Camino 2: la fuente deja de reportarla ---
    cargar([a], vistas=[a])
    c.igual(estados(conn).get("690002"), "CANCELADA", "sigue cancelada")
    c.igual(cuenta("tour_asignado", "690002"), 0, "y sigue fuera de la agenda")
    conn.close()


def una_cancelada_no_se_lleva_el_trabajo_ya_hecho(c):
    """Si recepcion ya preparo el vino o ya dio la amenidad por hecha, ese registro NO
    desaparece porque la reserva se caiga: es la prueba de que se hizo."""
    conn = base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    r = dict(reserva(690010, "05", llega, sale, adl=2),
             notas="Botella de vino de cortesia para la pareja")
    cargar([r], vistas=[r])

    hechas = conn.execute(
        "SELECT COUNT(*) n FROM amenidad_tarea WHERE conf_no='690010'").fetchone()["n"]
    c.cierto(hechas > 0, "la amenidad entro")
    conn.execute("UPDATE amenidad_tarea SET estado='HECHA' WHERE conf_no='690010'")
    conn.commit()

    r_cancelada = dict(r, res_status="CANCELADA")
    cargar([r_cancelada], vistas=[r_cancelada])

    quedan = conn.execute(
        "SELECT COUNT(*) n FROM amenidad_tarea WHERE conf_no='690010'").fetchone()["n"]
    c.igual(quedan, hechas, "lo que ya se hizo se queda como registro")
    conn.close()


def el_grupo_toma_el_itinerario_de_la_nota_de_su_PM(c):
    """Opera guarda la info de un grupo en la nota de su habitacion ficticia —la PM,
    'posting master'—, no en la de cada cuarto. El sistema filtra las PM a proposito
    (nadie duerme ahi), asi que esa informacion se perdia entera.

    Medido con el grupo INTREPID del 11 de noviembre: nueve habitaciones del bloque
    835457, las nueve con la nota VACIA, y la PM del cuarto 9000 con el itinerario
    completo. Recepcion veia nueve cuartos sin tours, sin regimen y sin punto."""
    import opera_mapeo as om

    NOTA_PM = ("PAQUETE 4D/3N+FULL BOARD\n"
               "PNC+CIS+NW\n"
               "-------------------------------\n"
               "INGRESO: Via Sierpe\n"
               "SALIDA: Via Sierpe\n"
               "------------------------------\n"
               "OPERACION:\n\n"
               "11: INGRESO\n12: CIS\n13: PNC\n14: SALIDA\n\n"
               "------------------------------\n"
               "NOTAS:\n\n11 PAX TOTALES PARA LOS TOURS")

    # Una habitacion del grupo, sin nota propia.
    hab = {"conf_no": "599046363", "room_no": "09", "block_code": "835457",
           "arr_date": "11-11-26", "dep_date": "14-11-26"}
    c.igual(hab.get("itinerario_leido"), None, "empieza sin itinerario")

    aplicada = om.aplicar_nota_del_bloque(hab, NOTA_PM)
    c.igual(aplicada, True, "se le aplica la nota de su grupo")
    c.igual(hab.get("nota_del_bloque"), True, "y queda marcado de donde vino")
    c.cierto(hab.get("itinerario_leido"), "ahora SI tiene itinerario")
    # 'CIS' es el codigo 2027 del snorkel de Isla del Caño, y el lector lo traduce al
    # tour que el lodge ya opera. Que llegue como SNORKEL y no como CIS es lo correcto:
    # si entrara como CIS saldria una salida nueva al lado de la de siempre.
    tours = sorted({o["tour"] for o in (hab.get("operacion") or [])})
    c.igual(tours, ["PNC", "SNORKEL"], "con los tours del grupo, ya traducidos")
    c.cierto("Via Sierpe" in NOTA_PM and hab.get("punto_entrada") == "Sierpe",
             "y su punto de embarque")

    # EL REGIMEN TAMBIEN. 'texto_completo' es de donde el importador lo saca, y se arma
    # en incorporar_detalle, que ya corrio: sin rehacerlo, la habitacion recibia los
    # tours del grupo pero no su «+FULL BOARD», y en la hoja del restaurante salia
    # «sin dato». Paso de verdad con la hab 13 del grupo INTREPID.
    import importer
    c.igual(importer.detectar_regimen(hab), "PENSION_COMPLETA",
            "y el regimen del paquete del grupo")

    # LA NOTA PROPIA MANDA: una habitacion que ya tiene su itinerario no se toca.
    propia = {"conf_no": "599046999", "block_code": "835457",
              "arr_date": "11-11-26", "itinerario_leido": True,
              "operacion": [{"dia": "12", "tour": "SNORKEL"}]}
    c.igual(om.aplicar_nota_del_bloque(propia, NOTA_PM), False,
            "la que ya tiene itinerario propio no se pisa")
    c.igual([o["tour"] for o in propia["operacion"]], ["SNORKEL"],
            "y conserva SUS tours, no los del grupo")


def la_PM_de_un_grupo_cancelado_no_reparte_nada(c):
    """Un grupo que no viene no le pone tours a nadie."""
    import opera_mapeo as om

    def pm(estado):
        return {"roomStay": {"pseudoRoom": True,
                             "reservationBlock": {"blockIdList": [{"id": "999111"}]}},
                "reservationIdList": [{"id": "77", "type": "Reservation"}],
                "reservationStatus": estado}

    def detalle_falso(_ident):
        # La forma REAL que manda Opera: comments[].comment.text.value. Escribirla a
        # medias hacia que texto_de_las_notas devolviera vacio y la prueba fallara por
        # el fixture, no por el codigo.
        return {"comments": [{"comment": {
            "text": {"value": "OPERACION:\n11: INGRESO\n12: PNC\n"}}}]}

    viva = om.notas_de_los_bloques([pm("Reserved")], detalle_falso)
    c.igual(sorted(viva), ["999111"], "la PM viva si aporta su nota")

    muerta = om.notas_de_los_bloques([pm("Cancelled")], detalle_falso)
    c.igual(muerta, {}, "la PM cancelada no aporta nada")

    # Y una habitacion normal nunca se toma por master.
    normal = {"roomStay": {"pseudoRoom": False,
                           "reservationBlock": {"blockIdList": [{"id": "999111"}]}},
              "reservationIdList": [{"id": "78", "type": "Reservation"}],
              "reservationStatus": "Reserved"}
    c.igual(om.notas_de_los_bloques([normal], detalle_falso), {},
            "una habitacion de verdad no es el master del grupo")


def entre_varias_PM_gana_la_que_trae_el_itinerario(c):
    """Un bloque puede tener VARIAS habitaciones PM y la primera no es la buena.

    Medido: el bloque 679505 tiene cuatro —la del grupo y tres de guias—, y el 679373 y
    el 774779 tienen dos, donde la primera que aparece es la del guia («HABITACION GUIA ·
    Randall Campos PTE CEDULA») y la del itinerario es la otra. Quedandose con la
    primera, doce habitaciones del 28 de noviembre y seis del 18 de diciembre seguian sin
    tours: el grupo tenia su itinerario y el sistema estaba leyendo la cedula del guia."""
    import opera_mapeo as om

    def pm(ident, texto):
        return ({"roomStay": {"pseudoRoom": True,
                              "reservationBlock": {"blockIdList": [{"id": "700700"}]}},
                 "reservationIdList": [{"id": ident, "type": "Reservation"}],
                 "reservationStatus": "Reserved"}, texto)

    GUIA = "HABITACION GUIA\n\nRandall Campos PTE CEDULA"
    ITIN = ("PAQUETE 3N/4D+ FULL BOARD\nCIS - PNC\n"
            "OPERACION:\n28: INGRESO\n29: CIS\n30: PNC\n01: SALIDA\n")

    def correr(pares):
        textos = {ident: t for (cr, t) in pares
                  for ident in [cr["reservationIdList"][0]["id"]]}
        crudas = [cr for cr, _ in pares]
        return om.notas_de_los_bloques(
            crudas, lambda i: {"comments": [{"comment": {
                "text": {"value": textos[str(i)]}}}]})

    # La del guia PRIMERO, que es el orden que rompia.
    r = correr([pm("1", GUIA), pm("2", ITIN)])
    c.cierto("OPERACION" in r.get("700700", ""),
             "gana la que trae el itinerario, aunque llegue segunda")
    c.cierto("Randall" not in r.get("700700", ""),
             "y no la cedula del guia")

    # Y al reves da lo mismo: el orden de Opera deja de decidir.
    r2 = correr([pm("2", ITIN), pm("1", GUIA)])
    c.igual(r2.get("700700"), r.get("700700"),
            "el orden en que Opera devuelva las PM ya no cambia el resultado")

    # Entre DOS con itinerario, la mas completa.
    largo = ITIN + "NOTAS:\n11 PAX TOTALES PARA LOS TOURS\n"
    r3 = correr([pm("1", ITIN), pm("2", largo)])
    c.igual(r3.get("700700"), largo, "entre dos itinerarios gana el mas completo")


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
    una_cancelada_sale_de_la_operacion,
    una_cancelada_no_se_lleva_el_trabajo_ya_hecho,
    el_grupo_toma_el_itinerario_de_la_nota_de_su_PM,
    la_PM_de_un_grupo_cancelado_no_reparte_nada,
    entre_varias_PM_gana_la_que_trae_el_itinerario,
]

if __name__ == "__main__":
    sys.exit(comun.correr("carga de Opera", PRUEBAS))
