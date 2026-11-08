"""Cuatro cosas que pidió el lodge el 8 de noviembre, cada una con su porqué.

  1. DOS VUELOS SEGUIDOS, UN SOLO BOTE. «Cuando se detecte que 2 vuelos ingresan o salen
     con una diferencia de 45 minutos... utilizar la salida del que sale primero para
     ambas».
  2. EL GUÍA NO REPARTE LA OPERACIÓN. «Deshabilitar el permiso de que modifiquen los
     guías, grupo, pero que puedan acceder a los resúmenes de tours y ver las fotos de
     pasaporte».
  3. EL BT SALE EN EL RESUMEN. «Cuando una reserva necesite BT indicar en el resumen de
     operación que hay BT para esa reserva y la hora».
  4. EL PRIVADO SE VE. «Indicar tanto en reservas como en el resumen si el tour es
     privado o no».
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402

import auth                                      # noqa: E402
import hoja_dia                                  # noqa: E402
import traslados as T                            # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _html():
    with open(os.path.join(RAIZ, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 1. Dos vuelos seguidos, un solo bote
# ---------------------------------------------------------------------------

def dos_salidas_a_menos_de_45_minutos_salen_juntas(c):
    """EL EJEMPLO DEL LODGE, tal cual: vuelo a las 11:00 (bote 9:00) y vuelo a las 11:30
    (bote 9:30) — los dos botes salen a las 9:00."""
    acordadas = T.horas_acordadas([
        ("2026-11-20", "salida", "Drake", "9:00 a.m."),
        ("2026-11-20", "salida", "Drake", "9:30 a.m."),
    ])
    c.igual(acordadas.get(("2026-11-20", "salida", "Drake", "9:30 a.m.")), "9:00 a.m.",
            "el de las 9:30 se adelanta al de las 9:00")
    c.igual(acordadas.get(("2026-11-20", "salida", "Drake", "9:00 a.m.")), None,
            "y el de las 9:00 no se mueve")


def en_la_salida_manda_la_hora_mas_temprana(c):
    """Si los dos se fueran a las 9:30, el del vuelo de las 11:00 lo pierde."""
    acordadas = T.horas_acordadas([
        ("2026-11-20", "salida", "Drake", "08:15"),
        ("2026-11-20", "salida", "Drake", "08:45"),
        ("2026-11-20", "salida", "Drake", "08:30"),
    ])
    c.igual(acordadas.get(("2026-11-20", "salida", "Drake", "08:45")), "08:15",
            "las tres se van a las 08:15")
    c.igual(acordadas.get(("2026-11-20", "salida", "Drake", "08:30")), "08:15", "idem")


def las_entradas_van_con_su_hora_tal_cual(c):
    """LO PRECISÓ EL LODGE: «en las entradas tómalas normales como indique la reserva,
    ya que en ese punto no aplica el tema de las 2 horas».

    Y por ahí sale la cuenta: en la SALIDA la hora del bote se CALCULA —dos horas antes
    del vuelo— así que dos vuelos cercanos dan dos horas distintas para el mismo viaje y
    hay que decidir cual vale. En la ENTRADA no se calcula nada: la hora es la del
    vuelo, tal como viene en la reserva, porque el bote espera al avion."""
    acordadas = T.horas_acordadas([
        ("2026-11-20", "entrada", "Drake", "11:00 a.m."),
        ("2026-11-20", "entrada", "Drake", "11:30 a.m."),
    ])
    c.igual(acordadas, {}, "dos entradas cercanas NO se tocan")
    # Ni aunque sean cuatro y casi a la misma hora.
    c.igual(T.horas_acordadas([("2026-11-20", "entrada", "Drake", "11:00"),
                               ("2026-11-20", "entrada", "Drake", "11:05"),
                               ("2026-11-20", "entrada", "Drake", "11:10")]), {},
            "cada entrada se queda con la hora que diga su reserva")


def mas_de_45_minutos_son_dos_viajes(c):
    """El umbral es el que dio el lodge. A 46 minutos ya son dos corridas."""
    c.igual(T.horas_acordadas([("2026-11-20", "salida", "Drake", "08:00"),
                               ("2026-11-20", "salida", "Drake", "08:45")]),
            {("2026-11-20", "salida", "Drake", "08:45"): "08:00"},
            "45 minutos justos se juntan")
    c.igual(T.horas_acordadas([("2026-11-20", "salida", "Drake", "08:00"),
                               ("2026-11-20", "salida", "Drake", "08:46")]),
            {}, "46 minutos ya no")


def el_racimo_no_se_encadena(c):
    """Con vuelos a las 11:00, 11:40 y 12:20, encadenar pondría los tres juntos y el
    primero esperaría 80 minutos. Cada racimo abarca 45 minutos y no más."""
    acordadas = T.horas_acordadas([
        ("2026-11-20", "salida", "Drake", "11:00"),
        ("2026-11-20", "salida", "Drake", "11:40"),
        ("2026-11-20", "salida", "Drake", "12:20"),
    ])
    c.igual(acordadas.get(("2026-11-20", "salida", "Drake", "11:40")), "11:00",
            "el de las 11:40 se junta con el de las 11:00")
    c.igual(acordadas.get(("2026-11-20", "salida", "Drake", "12:20")), None,
            "pero el de las 12:20 NO: son 80 minutos del primero")


def no_se_juntan_los_que_no_viajan_juntos(c):
    """El racimo es por día, dirección y punto. Un Drake y un Sierpe a la misma hora son
    dos botes en dos sitios distintos, y una entrada no se junta con una salida."""
    c.igual(T.horas_acordadas([("2026-11-20", "salida", "Drake", "08:00"),
                               ("2026-11-20", "salida", "Sierpe", "08:10")]), {},
            "puntos distintos no se juntan")
    c.igual(T.horas_acordadas([("2026-11-20", "salida", "Drake", "08:00"),
                               ("2026-11-20", "entrada", "Drake", "08:10")]), {},
            "una entrada y una salida tampoco (y la entrada nunca se junta)")
    c.igual(T.horas_acordadas([("2026-11-20", "salida", "Drake", "08:00"),
                               ("2026-11-21", "salida", "Drake", "08:10")]), {},
            "ni dos dias distintos")
    # El BT es un viaje de SU reserva, pedido para engancharse con otro operador.
    c.igual(T.horas_acordadas([("2026-11-20", "extra", "12", "08:00"),
                               ("2026-11-20", "extra", "12", "08:10")]), {},
            "y un BT no se junta con nadie")


def sin_hora_no_se_junta_nada(c):
    """Los que todavía no tienen hora son justo los que hay que resolver: no se les
    inventa una juntándolos con otro."""
    c.igual(T.horas_acordadas([("2026-11-20", "salida", "Drake", ""),
                               ("2026-11-20", "salida", "Drake", "08:10")]), {},
            "sin hora, nada que acordar")
    c.igual(T.horas_acordadas([("2026-11-20", "salida", "Drake", "no es una hora"),
                               ("2026-11-20", "salida", "Drake", "08:10")]), {},
            "y una hora que no se puede leer tampoco")


def las_corridas_se_arman_con_la_hora_acordada(c):
    """EL CAMINO COMPLETO: dos reservas con vuelos a 30 minutos tienen que acabar en UNA
    corrida, no en dos. Es lo que decide cuántos capitanes se apartan."""
    conn = comun.base_limpia()
    try:
        for conf, hab, hora in (("700001", "01", "11:00 a.m."),
                                ("700002", "02", "11:30 a.m.")):
            conn.execute(
                """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                        dep_date, adl, chl, rooms, res_status,
                                        punto_salida, hora_vuelo_salida)
                   VALUES (?,?,?, '18-11-26','20-11-26', 2,0,1,'EN CASA','Drake', ?)""",
                (conf, hab, f"Huesped/{conf}", hora))
        conn.commit()
        lista = [x for x in T.corridas(conn, "2026-11-20", "2026-11-20")
                 if x["tipo"] == "salida"]
        c.igual(len(lista), 1, "una sola corrida de salida, no dos")
        if lista:
            c.igual(lista[0]["pax"], 4, "con la gente de las dos habitaciones")
            c.igual(len(lista[0]["huespedes"]), 2, "las dos habitaciones dentro")
            # 11:00 - 2 horas = 9:00. Es la del vuelo que sale primero.
            c.cierto("9:00" in (lista[0]["hora"] or ""),
                     f"a la hora del primero (dice «{lista[0]['hora']}»)")
            # Y queda dicho POR QUÉ: la hora que el otro habría tenido (11:30 - 2h).
            c.cierto("9:30" in (lista[0]["hora_origen"] or ""),
                     f"y se dice que se junta con el otro bote de las 9:30 "
                     f"(dice «{lista[0]['hora_origen']}»)")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. El guía no reparte la operación
# ---------------------------------------------------------------------------

def el_guia_mira_la_agenda_pero_no_la_reparte(c):
    guia = {"rol": "staff",
            "permisos_json": json.dumps(auth.PERFILES["Guías"], ensure_ascii=False)}
    c.igual(auth.PERFILES["Guías"].get("agenda"), "ver", "la agenda en solo lectura")
    c.cierto(auth.puede(guia, "agenda"), "abre la Agenda y su resumen de tours")
    c.cierto(not auth.puede(guia, "agenda", escribir=True),
             "y no puede tocar guia, grupo, fecha ni pax")
    # Lo que SÍ tiene que seguir pudiendo hacer.
    c.cierto(auth.puede(guia, "pasaportes", escribir=True),
             "toma la foto del pasaporte: es quien recibe al huesped")
    c.cierto(auth.puede(guia, "resumen"), "ve el resumen de operacion")
    c.cierto(auth.puede(guia, "sinac"), "y abre el tiquete del parque")
    c.cierto(auth.puede(guia, "transporte"), "y ve el transporte")


def la_pantalla_le_quita_los_selectores(c):
    """El permiso sin la pantalla no sirve de nada: hay que comprobar que la Agenda
    dibuja texto en vez de selectores cuando no se puede escribir."""
    html = _html()
    agenda = html.split("<tr><th>Huésped / Hab.</th><th>Tour</th>", 1)[1][:2600]
    for que in ('puedeEscribir("agenda")\n              ? `<input type="date"',
                'puedeEscribir("agenda") ? `<select id="gr-',
                'puedeEscribir("agenda") ? `<select id="g-'):
        c.cierto(que.replace("\n              ", "\n              ") in agenda
                 or que.split("?")[0] in agenda,
                 f"la fecha, el grupo y el guia van detras del permiso ({que[:34]}…)")
    c.cierto('${puedeEscribir("agenda") ? `<td><button class="btn" '
             'onclick="guardarAsignacion(' in agenda,
             "y el boton de guardar tambien")
    # El resumen por tour NO depende de poder escribir: es lo que el guia va a mirar.
    resumen = html.split("function resumenPorTour(", 1)[1].split("\n// '2026-09-12'", 1)[0]
    c.cierto('puedeEscribir("agenda")' not in resumen,
             "el resumen por tour se dibuja igual sin permiso de escritura")


def la_migracion_le_baja_la_agenda_solo_a_los_guias(c):
    """QUITA un permiso, que es lo contrario de lo habitual, así que la condición tiene
    que ser estrecha: recepción y gerencia no se tocan."""
    import init_db
    conn = comun.base_limpia()
    try:
        gente = {
            "un_guia": {"agenda": "escribir", "transporte": "ver", "resumen": "ver",
                        "pasaportes": "escribir", "sinac": "ver"},
            "recepcion2": {"agenda": "escribir", "reservas": "escribir",
                           "usuarios": "escribir"},
            "gerencia2": {"agenda": "escribir", "importar": "escribir"},
            "cocina2": {"restaurantes": "escribir"},
        }
        for usuario, permisos in gente.items():
            conn.execute(
                "INSERT INTO usuario (username, password_hash, salt, nombre_completo, "
                "                     rol, permisos_json) VALUES (?,?,?,?,?,?)",
                (usuario, "x", "x", usuario, "staff",
                 json.dumps(permisos, ensure_ascii=False)))
        conn.execute("UPDATE perfil_permisos SET permisos_json = ? WHERE nombre = 'Guías'",
                     (json.dumps(gente["un_guia"], ensure_ascii=False),))
        conn.execute("DELETE FROM sistema_meta WHERE clave = 'el_guia_no_reparte'")
        conn.commit()

        init_db._el_guia_no_reparte_la_operacion(conn)

        def rejilla(usuario):
            return json.loads(dict(conn.execute(
                "SELECT permisos_json FROM usuario WHERE username = ?",
                (usuario,)).fetchone())["permisos_json"])

        c.igual(rejilla("un_guia").get("agenda"), "ver", "al guia se le baja")
        c.igual(rejilla("un_guia").get("pasaportes"), "escribir",
                "sin tocarle los pasaportes")
        c.igual(rejilla("recepcion2").get("agenda"), "escribir",
                "a recepcion NO se le toca")
        c.igual(rejilla("gerencia2").get("agenda"), "escribir", "ni a gerencia")
        c.cierto("agenda" not in rejilla("cocina2"), "ni a quien no la tenia")

        perfil = json.loads(dict(conn.execute(
            "SELECT permisos_json FROM perfil_permisos WHERE nombre = 'Guías'"
        ).fetchone())["permisos_json"])
        c.igual(perfil.get("agenda"), "ver", "y el perfil guardado queda corregido")

        # Una sola vez: si manana el lodge decide que un guia si reparta, no se deshace.
        conn.execute("UPDATE usuario SET permisos_json = ? WHERE username = 'un_guia'",
                     (json.dumps(gente["un_guia"], ensure_ascii=False),))
        conn.commit()
        init_db._el_guia_no_reparte_la_operacion(conn)
        c.igual(rejilla("un_guia").get("agenda"), "escribir",
                "la segunda vez ya no hace nada")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 3 y 4. El BT y el privado, donde la gente los va a leer
# ---------------------------------------------------------------------------

def el_privado_se_dice_igual_en_los_tres_sitios(c):
    """La hoja del día lo escribe en la casilla de cada habitación, en la caja de tours
    del PDF y en la del Excel. Una sola función, o la misma salida parecería dos cosas
    distintas en la misma página."""
    c.igual(hoja_dia.etiqueta_tour({"tour_codigo": "PNC"}), "PNC", "lo normal")
    c.igual(hoja_dia.etiqueta_tour({"tour_codigo": "PNC", "es_privado": 1}),
            "PNC · PRIVADO", "el privado va pegado al codigo")
    c.igual(hoja_dia.etiqueta_tour({"tour_codigo": "PNC", "grupo_operativo": "B",
                                    "es_privado": 1}),
            "PNC gr.B · PRIVADO", "con su grupo si no es el A")
    c.igual(hoja_dia.etiqueta_tour({"tour_codigo": "PNC", "grupo_operativo": "A"}),
            "PNC", "el grupo A no se escribe: es el normal")


def el_privado_no_se_suma_con_el_compartido(c):
    """SIN ESTO LA HOJA MIENTE EN EL PAX. Un PNC privado y uno compartido el mismo día
    caían en la misma fila y se sumaban: una salida de 6 pax donde hay dos botes, dos
    guías y dos entradas del parque."""
    with open(os.path.join(RAIZ, "backend", "main.py"), encoding="utf-8") as f:
        main = f.read()
    consulta = main.split("tours = lista(", 1)[1].split('""", (fecha, *no_caben))', 1)[0]
    c.cierto("COALESCE(ta.es_privado, 0) es_privado" in consulta,
             "el resumen trae es_privado")
    c.cierto("COALESCE(ta.es_privado, 0)" in consulta.split("GROUP BY", 1)[1],
             "y agrupa por el, para no sumar dos salidas distintas")


def el_privado_se_ve_en_reservas_y_en_el_resumen(c):
    html = _html()
    # En el resumen de operación, que es la previsualización que circula.
    resumen = html.split('<p class="title">Tours del día</p>', 1)[1][:2200]
    c.cierto("t.es_privado ? ` ${insigniaPrivado()}`" in resumen,
             "el resumen de operacion lo marca")
    # En Reservas: la ficha de la reserva y la lista del itinerario.
    ficha = html.split("<h4>Tours de la estadía</h4>", 1)[1][:900]
    c.cierto("t.es_privado ? ` ${insigniaPrivado()}`" in ficha,
             "la ficha de la reserva tambien")
    itin = html.split("function seccionToursItinerario(", 1)[1][:1400]
    c.cierto("t.es_privado ? ` ${insigniaPrivado()}`" in itin,
             "y la lista de tours del itinerario")


def el_bt_sale_en_el_resumen_con_su_hora(c):
    """Hasta ahora el BT solo salía en Transporte: quien lee la hoja del día no sabía
    que esa habitación tiene un bote apartado."""
    conn = comun.base_limpia()
    try:
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                    dep_date, adl, chl, rooms, res_status)
               VALUES ('700010','14','Huesped/700010','18-11-26','22-11-26',
                       2,0,1,'EN CASA')""")
        conn.execute(
            """INSERT INTO traslado_extra (conf_no, fecha, hora, nota, origen)
               VALUES ('700010','2026-11-20','14:00','Se engancha con otro operador',
                       'PDF')""")
        conn.commit()
        conn.close()

        import main
        d = main._datos_del_resumen("2026-11-20")
        c.igual(len(d.get("bts") or []), 1, "el BT sale en el resumen")
        if d.get("bts"):
            b = d["bts"][0]
            c.igual(b["hora"], "14:00", "con su hora")
            c.igual(str(b["room_no"]), "14", "y su habitacion")
            c.igual(b["pax"], 2, "y su gente")

        # Y de ahi a la hoja del dia, en la casilla de NOTAS de esa habitacion.
        conn = comun.conexion()
        try:
            hoja = hoja_dia.definicion(conn, "2026-11-20", d)
        finally:
            conn.close()
        suyas = [f for f in hoja["filas"] if str(f.get("hab")) == "14"]
        c.cierto(suyas, "la habitacion sale en la hoja del dia")
        if suyas:
            c.cierto("BT 14:00" in (suyas[0].get("notas") or ""),
                     f"con «BT 14:00» en notas (dice «{suyas[0].get('notas')}»)")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def la_pantalla_dibuja_el_bt(c):
    html = _html()
    resumen = html.split('<p class="title">Tours del día</p>', 1)[1][:3200]
    c.cierto("(d.bts || []).length" in resumen, "el resumen pinta los BT si los hay")
    c.cierto("Botes extra (BT)" in resumen, "con un titulo que se entiende")
    c.cierto("sin hora" in resumen, "y dice cuando falta la hora, en vez de callarlo")


PRUEBAS = [
    dos_salidas_a_menos_de_45_minutos_salen_juntas,
    en_la_salida_manda_la_hora_mas_temprana,
    las_entradas_van_con_su_hora_tal_cual,
    mas_de_45_minutos_son_dos_viajes,
    el_racimo_no_se_encadena,
    no_se_juntan_los_que_no_viajan_juntos,
    sin_hora_no_se_junta_nada,
    las_corridas_se_arman_con_la_hora_acordada,
    el_guia_mira_la_agenda_pero_no_la_reparte,
    la_pantalla_le_quita_los_selectores,
    la_migracion_le_baja_la_agenda_solo_a_los_guias,
    el_privado_se_dice_igual_en_los_tres_sitios,
    el_privado_no_se_suma_con_el_compartido,
    el_privado_se_ve_en_reservas_y_en_el_resumen,
    el_bt_sale_en_el_resumen_con_su_hora,
    la_pantalla_dibuja_el_bt,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Las cuatro correcciones", PRUEBAS))
