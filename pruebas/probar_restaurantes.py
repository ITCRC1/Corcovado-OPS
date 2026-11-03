"""El reparto del comedor y, sobre todo, que un grupo no se parta.

La regla del modulo dice que los grupos y familias no se separan NUNCA. El reparto
automatico la cumplia; el cambio a mano no: movia una habitacion sola y las otras siete
de la agencia se quedaban en el otro restaurante. La regla decia una cosa y el boton
hacia otra, y lo descubria el salonero con la gente ya sentada.

Esta suite fija las dos mitades de la regla, porque hasta ahora no habia ninguna prueba
que tocara grupos ni el comedor.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
from comun import cargar, reserva

import restaurantes as rest

HOY = datetime.date.today()


def ddmmyy(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def _habs(lista):
    """Las habitaciones de un bloque de la distribucion, ordenadas, para comparar."""
    return sorted(x["room_no"] for x in lista)


def _cena(conn, fecha=None):
    d = rest.distribuir(conn, fecha or HOY)
    return d["cena"]


def _grupo(n, bloque="AGENCIA1", adl=2, desde=1, estado="EN CASA"):
    """n habitaciones que viajan juntas por compartir codigo de bloque."""
    llegada = HOY - datetime.timedelta(days=1)
    salida = HOY + datetime.timedelta(days=3)
    return [reserva(f"{bloque}{i}", f"{desde + i:02d}", ddmmyy(llegada), ddmmyy(salida),
                    estado=estado, adl=adl, block_code=bloque)
            for i in range(n)]


def _solo(conf_no, hab, adl=2, estado="EN CASA"):
    llegada = HOY - datetime.timedelta(days=1)
    salida = HOY + datetime.timedelta(days=3)
    return reserva(conf_no, hab, ddmmyy(llegada), ddmmyy(salida), estado=estado, adl=adl)


def _quien_es(conn, bloque="AGENCIA1"):
    return [f["conf_no"] for f in conn.execute(
        "SELECT conf_no FROM reserva WHERE block_code = ? ORDER BY conf_no", (bloque,))]


# ---------------------------------------------------------------------------
# Lo que ya funcionaba: el reparto automatico no parte grupos
# ---------------------------------------------------------------------------

def el_reparto_automatico_no_parte_un_grupo(c):
    conn = comun.base_limpia()
    cargar(_grupo(4) + [_solo("SOLA1", "20"), _solo("SOLA2", "21")])
    cena = _cena(conn)
    habs_grupo = set(_habs([{"room_no": f"{1 + i:02d}"} for i in range(4)]))
    en_tk = set(_habs(cena["terra_kitchen"])) & habs_grupo
    en_bosque = set(_habs(cena["bar_el_bosque"])) & habs_grupo
    c.cierto(not (en_tk and en_bosque),
             "las cuatro habitaciones del grupo caen en el MISMO restaurante")
    c.igual(len(en_tk) + len(en_bosque), 4, "y estan las cuatro")
    conn.close()


# ---------------------------------------------------------------------------
# Lo que se arregla: el cambio a mano tampoco lo parte
# ---------------------------------------------------------------------------

def mover_una_habitacion_del_grupo_las_mueve_todas(c):
    """El caso que reporto el hotel. Antes salia una sola y el resto se quedaba."""
    conn = comun.base_limpia()
    cargar(_grupo(4) + [_solo("SOLA1", "20"), _solo("SOLA2", "21")])
    miembros = _quien_es(conn)
    donde_estaban = ("terra_kitchen"
                     if any(x["conf_no"] == miembros[0] for x in _cena(conn)["terra_kitchen"])
                     else "bar_el_bosque")
    destino = rest.BOSQUE if donde_estaban == "terra_kitchen" else rest.TERRA

    aplicadas, excepciones = rest.mover_grupo(conn, HOY, miembros[0], "CENA", destino)
    conn.commit()

    c.igual(len(aplicadas), 3, "se llevo a las otras tres del grupo")
    c.igual(excepciones, [], "sin dejar a ninguna atras")

    cena = _cena(conn)
    caja = cena["bar_el_bosque"] if destino == rest.BOSQUE else cena["terra_kitchen"]
    conf_alli = {x["conf_no"] for x in caja}
    c.cierto(set(miembros) <= conf_alli,
             f"las cuatro del grupo quedaron en {destino}")
    conn.close()


def mover_una_reserva_sola_no_arrastra_a_nadie(c):
    conn = comun.base_limpia()
    cargar(_grupo(4) + [_solo("SOLA1", "20"), _solo("SOLA2", "21")])
    aplicadas, excepciones = rest.mover_grupo(conn, HOY, "SOLA1", "CENA", rest.TERRA)
    conn.commit()
    c.igual(aplicadas, [], "una reserva que viaja sola no tiene a quien llevarse")
    c.igual(excepciones, [], "ni a quien dejar atras")
    conn.close()


def destildando_la_casilla_sale_una_sola(c):
    """Hace falta de verdad: a veces una pareja del grupo cena aparte esa noche."""
    conn = comun.base_limpia()
    cargar(_grupo(4))
    miembros = _quien_es(conn)
    aplicadas, _ = rest.mover_grupo(conn, HOY, miembros[0], "CENA", rest.TERRA,
                                    solo_esta=True)
    conn.commit()
    c.igual(aplicadas, [], "no se movio nadie mas")
    filas = conn.execute("SELECT conf_no FROM restaurante_cambio").fetchall()
    c.igual([f["conf_no"] for f in filas], [miembros[0]],
            "y solo quedo escrito el cambio de esa")
    conn.close()


def a_quien_ya_separaron_a_mano_no_se_le_pisa(c):
    """Alguien la aparto a proposito. Volver a juntarla desharia esa decision sin avisar,
    asi que se informa y se deja donde esta."""
    conn = comun.base_limpia()
    cargar(_grupo(4))
    miembros = _quien_es(conn)
    # La cuarta se manda sola a Terra Kitchen.
    rest.mover_grupo(conn, HOY, miembros[3], "CENA", rest.TERRA, solo_esta=True)
    conn.commit()
    # Y ahora se manda el grupo a Bar el Bosque desde la primera.
    aplicadas, excepciones = rest.mover_grupo(conn, HOY, miembros[0], "CENA", rest.BOSQUE)
    conn.commit()

    c.igual(sorted(x["conf_no"] for x in aplicadas), sorted(miembros[1:3]),
            "se llevo a las dos que no estaban separadas")
    c.igual([x["conf_no"] for x in excepciones], [miembros[3]],
            "y dejo a la que estaba puesta a mano")
    c.cierto("a mano" in excepciones[0]["motivo"], "diciendo por que")

    cena = _cena(conn)
    c.cierto(any(x["conf_no"] == miembros[3] for x in cena["terra_kitchen"]),
             "que sigue donde la habian puesto")
    conn.close()


def a_quien_tiene_cena_privada_no_se_le_mueve(c):
    """No esta en la mesa del grupo: esta en la piscina. Moverla de restaurante no
    significa nada y le quitaria el sitio que su cena privada ocupa en Bar el Bosque."""
    conn = comun.base_limpia()
    cargar(_grupo(4))
    miembros = _quien_es(conn)
    # Se escribe como la reconoce el sistema (ver restaurantes._filtro_privada), para
    # que la prueba no invente su propia forma de marcar una cena privada.
    conn.execute(
        "INSERT INTO amenidad_tarea (conf_no, amenidad, tarea, area_responsable, fecha) "
        "VALUES (?,?,?,?,?)",
        (miembros[2], "Cena privada", "Montar cena privada", "Restaurante",
         HOY.isoformat()))
    conn.commit()
    c.cierto(miembros[2] in rest._cenas_privadas(conn, HOY),
             "el sistema la reconoce como cena privada")

    aplicadas, excepciones = rest.mover_grupo(conn, HOY, miembros[0], "CENA", rest.TERRA)
    conn.commit()
    c.igual(sorted(x["conf_no"] for x in aplicadas), sorted([miembros[1], miembros[3]]),
            "se lleva a las otras dos")
    c.igual([x["conf_no"] for x in excepciones], [miembros[2]],
            "y deja a la de la cena privada")
    c.cierto("privada" in excepciones[0]["motivo"], "diciendo por que")
    conn.close()


def el_que_ya_se_fue_no_se_mueve(c):
    """Un companero de grupo que salio en la manana no tiene mesa esa noche."""
    conn = comun.base_limpia()
    lote = _grupo(3)
    # A la tercera se le adelanta la salida a HOY: cena en otro lado, no aqui.
    lote[2]["dep_date"] = ddmmyy(HOY)
    cargar(lote)
    miembros = _quien_es(conn)
    aplicadas, _ = rest.mover_grupo(conn, HOY, miembros[0], "CENA", rest.TERRA)
    conn.commit()
    c.igual(sorted(x["conf_no"] for x in aplicadas), sorted(miembros[1:2]),
            "solo se mueve quien cena esa noche")
    conn.close()


def mover_dos_veces_no_duplica_filas(c):
    conn = comun.base_limpia()
    cargar(_grupo(3))
    miembros = _quien_es(conn)
    rest.mover_grupo(conn, HOY, miembros[0], "CENA", rest.TERRA)
    rest.mover_grupo(conn, HOY, miembros[0], "CENA", rest.BOSQUE)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) n FROM restaurante_cambio").fetchone()["n"]
    c.igual(n, 3, "una fila por habitacion, no dos")
    destinos = {f["restaurante"] for f in
                conn.execute("SELECT restaurante FROM restaurante_cambio")}
    c.igual(destinos, {rest.BOSQUE}, "y todas apuntan al ultimo destino")
    conn.close()


def el_almuerzo_usa_su_propia_comida(c):
    """Mover el almuerzo no puede tocar la cena, ni al reves: son filas distintas."""
    conn = comun.base_limpia()
    cargar(_grupo(3))
    miembros = _quien_es(conn)
    rest.mover_grupo(conn, HOY, miembros[0], "ALMUERZO", rest.BOSQUE)
    conn.commit()
    comidas = {f["comida"] for f in
               conn.execute("SELECT comida FROM restaurante_cambio")}
    c.igual(comidas, {"ALMUERZO"}, "solo se escribio el almuerzo")
    n = conn.execute(
        "SELECT COUNT(*) n FROM restaurante_cambio WHERE comida = 'ALMUERZO'"
    ).fetchone()["n"]
    c.igual(n, 3, "para las tres del grupo")
    conn.close()


# ---------------------------------------------------------------------------
# El cableado hasta la pantalla
# ---------------------------------------------------------------------------

def el_boton_manda_lo_del_grupo(c):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    with open(os.path.join(raiz, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()

    c.cierto('id="mover-todo-el-grupo"' in pantalla, "existe la casilla")
    i = pantalla.find("async function cambiarRestaurante")
    c.cierto(i > 0, "existe el manejador del boton")
    fn = pantalla[i:i + 1400]
    c.cierto("mover-todo-el-grupo" in fn, "que lee la casilla")
    c.cierto("solo_esta" in fn, "y manda solo_esta")
    c.cierto("d.excepciones" in fn or "excepciones" in fn,
             "y enseña a quien NO se movio, que es lo que hay que mirar")

    c.cierto("rest.mover_grupo(" in servidor,
             "el endpoint usa la regla del modulo y no escribe por su cuenta")
    # El aviso de capacidad miraba solo Terra Kitchen; moviendo grupos enteros, pasarse
    # de los 45 de Bar el Bosque deja de ser un caso raro.
    j = servidor.find("def restaurantes_cambiar")
    bloque = servidor[j:j + 2600]
    c.cierto("cap_bosque" in bloque, "y el aviso de capacidad ya mira Bar el Bosque")


def la_alergia_sale_en_restaurantes_y_NO_en_amenidades(c):
    """Lo pidio el lodge: «elimina las restricciones alimenticias de la hoja de
    amenidades y que solo se reflejen en la parte de alergias del modulo de restaurante».

    En Amenidades ocupaban sitio entre tareas que hay que PREPARAR —una cuna, una
    decoracion, una botella de vino— y una alergia no se prepara, se sabe.

    LO QUE NO PUEDE PASAR, y es el riesgo de verdad de este cambio: que una fila caiga
    fuera de las DOS pantallas y no aparezca en ninguna parte. Por eso las dos deciden
    con la MISMA funcion, y esto comprueba que sean complementarias exactas."""
    FILAS = [
        # (amenidad, tarea, detalle, deberia_verse_en_Restaurantes)
        ("Restricción alimentaria / alergia", "AVISAR A COCINA",
         "Lactose, hazelnut and peanut allergy", True),
        ("Restricción alimentaria / alergia", "AVISAR A COCINA",
         "*no pork, no shellfish", True),
        # Recepcion a veces la escribe con otro nombre y la alergia va en el detalle.
        ("Preferencia del huesped", None, "alergico a mariscos", True),
        # Y las que NO son restriccion se quedan en Amenidades.
        ("Cuna / bebé", "Notificar a housekeeping", "viaja con un niño de 2 años", False),
        ("Decoración por cumpleaños", None, "Ann Evelyn celebra su cumpleaños", False),
        ("Botella de vino cortesía", None, "Autorizado por gerencia", False),
        ("Almohadas o toallas extra", None, "EXTRA PILLOWS", False),
        ("Tarjeta de bienvenida", None, "Regalo de bienvenida", False),
        # La cena privada es de cocina pero tiene su propio sitio: no es una alergia.
        ("Cena privada", "Notificar a cocina", "Cena privada en la playa", False),
        # Y la alergia que NO es de comida tampoco: cocina no puede hacer nada con ella.
        ("Restricción alimentaria / alergia", None, "Down Feather Allergy", False),
        ("Restricción alimentaria / alergia", None,
         "Ambos tiene alergía a las plumas", False),
    ]
    for amenidad, tarea, detalle, en_restaurantes in FILAS:
        es = bool(rest.es_restriccion_alimentaria(amenidad, tarea, detalle))
        c.igual(es, en_restaurantes,
                f"«{str(detalle)[:34]}» va a "
                f"{'Restaurantes' if en_restaurantes else 'Amenidades'}")

    # La pantalla de Amenidades usa ESA funcion, no una copia suya. Con dos reglas
    # distintas una fila podria caer fuera de las dos y no verse en ninguna parte.
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()
    i = servidor.find("LAS RESTRICCIONES ALIMENTARIAS NO SALEN AQUÍ")
    c.cierto(i > 0, "la pantalla de amenidades dice por que las excluye")
    c.cierto("es_restriccion_alimentaria" in servidor[i:i + 1600],
             "y decide con la misma funcion que Restaurantes")


def la_alergia_que_no_es_de_comida_va_como_alerta(c):
    """Lo decidio el lodge: «eliminemos solo lo que son alergias gastronomicas de la hoja
    de amenidades, las otras alergias tiremoslas como alerta a la reserva nada mas».

    Una alergia a las plumas no la arregla cocina —no hay desayuno que ayude— y tampoco
    se prepara desde la hoja de amenidades. Lo que hace falta es que alguien la vea al
    abrir la reserva: eso es un aviso.

    EL «Y» DE LA REGLA ES LO DELICADO. Se exige que nombre un alergeno no alimentario Y
    que NO nombre ninguna comida: «allergic to feathers and peanuts» es las dos cosas, y
    tratarla como no alimentaria le esconderia el mani a cocina. Ante la duda, de comida
    —que es el lado seguro—."""
    NO_COMIDA = ["Down Feather Allergy",
                 "Ambos tiene alergía a las plumas",
                 "Alergia al latex",
                 "allergic to bee sting"]
    for texto in NO_COMIDA:
        c.cierto(rest.es_alergia_no_alimentaria("Restricción alimentaria / alergia",
                                                None, texto),
                 f"«{texto[:34]}» no es de comida")
        c.igual(rest.es_restriccion_alimentaria("Restricción alimentaria / alergia",
                                                None, texto), False,
                f"y por eso NO va a la pestaña de cocina")

    # LAS DOS COSAS A LA VEZ se tratan como de comida. Es el caso que no puede fallar.
    MIXTAS = ["allergic to feathers and peanuts",
              "Alergia a las plumas y al gluten",
              "down feather allergy + lactose intolerant"]
    for texto in MIXTAS:
        c.igual(rest.es_alergia_no_alimentaria(None, None, texto), False,
                f"«{texto[:34]}» nombra comida: NO se saca de cocina")
        c.cierto(rest.es_restriccion_alimentaria("Restricción alimentaria / alergia",
                                                 None, texto),
                 "y sigue saliendo en la pestaña de alergias")

    # Y una alergia de comida normal no se confunde con las de plumas.
    for texto in ("Lactose, hazelnut and peanut allergy", "No pork or octopus",
                  "One allergy to gluten (James)"):
        c.igual(rest.es_alergia_no_alimentaria(None, None, texto), False,
                f"«{texto[:30]}» es de comida")


def la_alerta_de_la_alergia_no_alimentaria_llega_a_la_base(c):
    """De punta a punta: la nota entra, la alergia de plumas no sale en amenidades ni en
    cocina, y queda un aviso con la habitacion y el texto."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    r = dict(reserva(670200, "13", llega, sale, adl=2),
             notas="Down Feather Allergy")
    cargar([r], vistas=[r])

    # No esta en la pestaña de cocina.
    c.igual(rest.restricciones_del_dia(conn, HOY), [],
            "la alergia a las plumas no llega a la pestaña de cocina")

    # Pero hay aviso, con la habitacion y el texto.
    avisos = conn.execute(
        """SELECT mensaje FROM alerta
           WHERE tipo = 'ALERGIA_NO_ALIMENTARIA' AND resuelto = 0""").fetchall()
    c.igual(len(avisos), 1, "queda UN aviso para la reserva")
    msg = avisos[0]["mensaje"]
    c.cierto("13" in msg, "el aviso dice la habitacion")
    c.cierto("Feather" in msg, "y el texto de la alergia")
    c.cierto("almohada" in msg.lower(), "y que hay que mirar las almohadas")

    # Cargar otra vez no lo duplica: el ciclo pasa muchas veces por la misma reserva.
    cargar([r], vistas=[r])
    n = conn.execute("""SELECT COUNT(*) n FROM alerta
                        WHERE tipo='ALERGIA_NO_ALIMENTARIA' AND resuelto=0"""
                     ).fetchone()["n"]
    c.igual(n, 1, "y no se duplica al recargar")
    conn.close()


def la_fila_de_la_alergia_no_se_borra(c):
    """Se deja de MOSTRAR en Amenidades, pero la fila sigue en la base: es la que lee
    Restaurantes y la que guarda el estado. Si se borrara, el boton de «marcar avisada»
    no tendria sobre que escribir y la alergia desapareceria de las dos pantallas."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    r = dict(reserva(670100, "07", llega, sale, adl=2),
             notas="Lactose, hazelnut and peanut allergy")
    cargar([r], vistas=[r])

    fila = conn.execute(
        """SELECT id, amenidad, detalle, estado FROM amenidad_tarea
           WHERE conf_no = '670100'""").fetchone()
    c.cierto(fila is not None, "la fila de la alergia se guarda igual que siempre")
    c.igual(fila["estado"], "PENDIENTE", "con su estado")
    c.cierto("Lactose" in (fila["detalle"] or ""), "y con su detalle")

    hallazgo = rest.restricciones_del_dia(conn, HOY)
    c.igual([x["room_no"] for x in hallazgo], ["07"],
            "y la pestaña de alergias la muestra")
    conn.close()


def la_misma_alergia_vista_por_dos_fuentes_es_UNA_fila(c):
    """EL DUPLICADO DE VERDAD, el que el lodge ve en la hoja de cocina.

    Cada fuente borra y regenera SOLO sus filas —el PDF las suyas, Opera las suyas— y
    eso dejaba dos filas de la misma alergia en cuanto las dos la veian. En la pantalla
    salia la habitacion 09 con «Lactose, hazelnut and peanut allergy Mr.» y «Lactose,
    hazelnut and peanut allergy», una debajo de la otra, con recortes distintos del
    mismo texto.

    No se veia en una base recien creada: hace falta que la reserva haya pasado por las
    DOS fuentes, que es lo que lleva meses pasando en el lodge.
    """
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    NOTA = "Lactose, hazelnut and peanut allergy"

    # Primero el PDF (camino completo), que es como entro la reserva hace meses.
    r = dict(reserva(680100, "09", llega, sale, adl=2), notas=NOTA)
    cargar([r], vistas=[r], manda_en="TODO")
    c.igual(conn.execute(
        "SELECT COUNT(*) FROM amenidad_tarea WHERE amenidad LIKE 'Restricci%'"
    ).fetchone()[0], 1, "el PDF deja una fila")

    # Y despues Opera, que la vuelve a ver. Antes aqui aparecia la segunda.
    cargar([r], vistas=[r])
    filas = [dict(f) for f in conn.execute(
        """SELECT id, origen, detalle FROM amenidad_tarea
           WHERE amenidad LIKE 'Restricci%' ORDER BY id""")]
    c.igual(len(filas), 1, "Opera NO agrega una segunda: sigue siendo una sola")
    if filas:
        c.igual(filas[0]["origen"], "OPERA",
                "y queda la de la fuente que acaba de escribir, que es la que esta al dia")

    # Y la hoja de cocina enseña una, no dos.
    c.igual(len(rest.restricciones_del_dia(conn, HOY)), 1, "la hoja enseña una")
    conn.close()


def al_juntar_las_dos_fuentes_no_se_pierde_el_trabajo_hecho(c):
    """La contraparte, y es la que importa: juntar no puede borrar lo que alguien hizo.

    Si cocina ya marco la alergia como avisada, o recepcion le corrigio el texto, eso
    tiene que sobrevivir aunque la fila que lo guardaba fuera de la otra fuente. Perderlo
    en silencio es peor que el duplicado: la alergia reaparece como pendiente y nadie
    sabe que ya se habia revisado."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    r = dict(reserva(680110, "09", llega, sale, adl=2),
             notas="Lactose, hazelnut and peanut allergy")
    cargar([r], vistas=[r], manda_en="TODO")          # entra por el PDF

    # Recepcion le corrige el texto y cocina la marca avisada.
    conn.execute("""UPDATE amenidad_tarea SET detalle = ?, editado_a_mano = 1,
                                              estado = 'HECHA'
                    WHERE amenidad LIKE 'Restricci%'""",
                 ("Lactosa, avellana y mani. Confirmado por telefono.",))
    conn.commit()

    cargar([r], vistas=[r])                            # y entra Opera

    filas = [dict(f) for f in conn.execute(
        """SELECT origen, detalle, estado, editado_a_mano FROM amenidad_tarea
           WHERE amenidad LIKE 'Restricci%'""")]
    c.igual(len(filas), 1, "sigue siendo una sola fila")
    if filas:
        c.igual(filas[0]["detalle"], "Lactosa, avellana y mani. Confirmado por telefono.",
                "con el texto que escribio recepcion")
        c.igual(filas[0]["estado"], "HECHA", "y sin reabrir lo que cocina ya reviso")
        c.igual(filas[0]["editado_a_mano"], 1, "sigue marcada como editada")
    conn.close()


def la_misma_nota_en_dos_reservas_es_UNA_alergia(c):
    """Lo que el lodge vio como «las alergias se estan duplicando».

    NO era la base: medido sobre las 331 reservas cargadas, ninguna tiene la misma
    restriccion dos veces. Lo que pasa es que una familia que toma DOS habitaciones lleva
    la misma nota copiada en las dos —el agente la escribe igual en ambas reservas de
    Opera— y la hoja de cocina enseñaba el mismo texto dos veces, como si fueran dos
    personas distintas con la misma alergia.

    Es el caso real de las habitaciones 04 y 16 del 1 de enero: las dos de Forrester, las
    dos con «My adult son, Reed... has a dairy allergy».

    LO QUE NO PUEDE PASAR es que se pierda una habitacion al juntarlas: cocina sirve por
    mesa y necesita saber en cuales esta."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    NOTA = "Reed has a dairy allergy, no butter"
    lote = [dict(reserva(670200, "04", llega, sale, adl=2), notas=NOTA),
            dict(reserva(670201, "16", llega, sale, adl=2), notas=NOTA),
            # Y una tercera con OTRA alergia, que no se puede juntar con las anteriores.
            dict(reserva(670202, "09", llega, sale, adl=2),
                 notas="One allergy to gluten")]
    cargar(lote, vistas=lote)

    guardadas = conn.execute(
        "SELECT COUNT(*) FROM amenidad_tarea WHERE amenidad LIKE 'Restricci%'").fetchone()[0]
    c.igual(guardadas, 3, "en la base siguen las tres filas, una por reserva")

    lista = rest.restricciones_del_dia(conn, HOY)
    c.igual(len(lista), 2, "pero en la hoja son DOS restricciones, no tres")

    juntas = [x for x in lista if x["en_cuantas_reservas"] > 1]
    c.igual(len(juntas), 1, "una sola quedo agrupada")
    if juntas:
        c.igual(sorted(juntas[0]["habitaciones"]), ["04", "16"],
                "y lista las DOS habitaciones, que es lo que cocina necesita")
        c.igual(len(juntas[0]["ids"]), 2,
                "con los dos ids, para poder marcarlas y corregirlas juntas")

    sola = [x for x in lista if x["en_cuantas_reservas"] == 1]
    c.igual([x["habitaciones"] for x in sola], [["09"]], "la otra alergia queda aparte")
    conn.close()


def dos_alergias_sin_detalle_no_se_juntan(c):
    """La contraparte, que es la que evita pasarse de listo: sin texto que comparar, dos
    restricciones vacias pueden ser dos cosas distintas que alguien no escribio. Juntarlas
    esconderia una alergia de verdad, que es el error caro de esta pantalla."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    lote = [dict(reserva(670210, "04", llega, sale, adl=2), notas=""),
            dict(reserva(670211, "16", llega, sale, adl=2), notas="")]
    cargar(lote, vistas=lote)
    # Se les pone la restriccion a mano, sin detalle, como cuando recepcion la anota por
    # telefono y no escribe de que es.
    for conf in ("670210", "670211"):
        conn.execute(
            """INSERT INTO amenidad_tarea (conf_no, amenidad, origen, detalle, tarea,
                                           area_responsable, estado)
               VALUES (?, 'Restricción alimentaria / alergia', 'MANUAL', NULL,
                       'AVISAR A COCINA', 'Cocina', 'PENDIENTE')""", (conf,))
    conn.commit()

    lista = rest.restricciones_del_dia(conn, HOY)
    c.igual(len(lista), 2, "sin texto no se juntan: siguen siendo dos")
    conn.close()


def una_alergia_quitada_a_mano_no_vuelve_al_sincronizar(c):
    """Lo pidio el lodge: «que tambien las alergias se puedan eliminar o agregar de forma
    manual».

    Quitar la que vino de una fuente no puede ser un DELETE: la siguiente sincronizacion
    la regenera, y el boton pareceria no haber hecho nada —se usa, parece que funciono, y
    la alergia reaparece al dia siguiente—. Se marca, y el cargador respeta la marca.

    Es la misma regla que ya protegia lo editado a mano, y por la misma razon: es la
    decision de una persona, no un dato de la fuente."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    r = dict(reserva(680200, "09", llega, sale, adl=2),
             notas="Lactose, hazelnut and peanut allergy")
    cargar([r], vistas=[r])
    c.igual(len(rest.restricciones_del_dia(conn, HOY)), 1, "la alergia esta")

    # Alguien la quita porque no aplica.
    conn.execute("UPDATE amenidad_tarea SET oculta = 1 WHERE amenidad LIKE 'Restricci%'")
    conn.commit()
    c.igual(len(rest.restricciones_del_dia(conn, HOY)), 0, "sale de la hoja de cocina")

    # Y NO vuelve en la siguiente sincronizacion, que es lo que importa.
    cargar([r], vistas=[r])
    c.igual(len(rest.restricciones_del_dia(conn, HOY)), 0,
            "y sigue fuera despues de sincronizar")
    # La fila sigue ahi: si mañana alguien pregunta por que desaparecio, hay rastro.
    c.igual(conn.execute(
        "SELECT COUNT(*) FROM amenidad_tarea WHERE amenidad LIKE 'Restricci%'"
    ).fetchone()[0], 1, "pero la fila se conserva, no se borra el rastro")
    conn.close()


def una_alergia_quitada_se_puede_devolver(c):
    """Quitar es facil de hacer por equivocacion: el lodge quito las de un dia entero
    creyendo que estaban duplicadas. Por eso no se borran, se marcan — y por eso tiene
    que haber donde verlas y devolverlas. Sin esa segunda mitad, la marca no sirve de
    nada y la alergia se pierde igual que si se hubiera borrado."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    lote = [dict(reserva(680300, "09", llega, sale, adl=2),
                 notas="Lactose, hazelnut and peanut allergy"),
            dict(reserva(680301, "21", llega, sale, adl=2),
                 notas="*no pork, no shellfish")]
    cargar(lote, vistas=lote)
    c.igual(len(rest.restricciones_del_dia(conn, HOY)), 2, "hay dos alergias")
    c.igual(len(rest.restricciones_del_dia(conn, HOY, solo_quitadas=True)), 0,
            "y ninguna quitada")

    # Se quitan las dos, como paso de verdad.
    conn.execute("UPDATE amenidad_tarea SET oculta = 1 WHERE amenidad LIKE 'Restricci%'")
    conn.commit()
    c.igual(len(rest.restricciones_del_dia(conn, HOY)), 0, "la hoja queda vacia")
    quitadas = rest.restricciones_del_dia(conn, HOY, solo_quitadas=True)
    c.igual(len(quitadas), 2, "pero las dos siguen ahi, listas para devolver")
    c.igual(sorted(x["habitaciones"][0] for x in quitadas), ["09", "21"],
            "con su habitacion, para saber de quien es cada una")

    # Y devolver una la trae de vuelta sin tocar la otra.
    ids = [x["id"] for x in quitadas if x["habitaciones"] == ["09"]]
    conn.execute("UPDATE amenidad_tarea SET oculta = 0 WHERE id = ?", (ids[0],))
    conn.commit()
    c.igual([x["habitaciones"] for x in rest.restricciones_del_dia(conn, HOY)], [["09"]],
            "vuelve la que se devolvio")
    c.igual([x["habitaciones"] for x in
             rest.restricciones_del_dia(conn, HOY, solo_quitadas=True)], [["21"]],
            "y la otra sigue quitada")
    conn.close()


def una_alergia_agregada_a_mano_sale_en_la_hoja(c):
    """La otra mitad: la que el huesped avisa por telefono o al sentarse a comer.

    Se anota DONDE SE LEE. Y se borra de verdad al quitarla: no la genera ninguna
    fuente, asi que no vuelve."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    r = dict(reserva(680210, "12", llega, sale, adl=2), notas="")
    cargar([r], vistas=[r])
    c.igual(len(rest.restricciones_del_dia(conn, HOY)), 0, "no tenia ninguna")

    conn.execute(
        """INSERT INTO amenidad_tarea (conf_no, amenidad, origen, detalle, tarea,
                                       area_responsable, estado)
           VALUES ('680210', 'Restricción alimentaria / alergia', 'MANUAL',
                   'Celiaco, avisa al llegar', 'AVISAR A COCINA', 'Cocina',
                   'PENDIENTE')""")
    conn.commit()

    lista = rest.restricciones_del_dia(conn, HOY)
    c.igual(len(lista), 1, "la anotada a mano sale en la hoja")
    if lista:
        c.igual(lista[0]["habitaciones"], ["12"], "en su habitacion")
        c.igual(lista[0]["origen"], "MANUAL", "y marcada como puesta a mano")

    # Y sobrevive a la sincronizacion: cada fuente administra solo lo suyo.
    cargar([r], vistas=[r])
    c.igual(len(rest.restricciones_del_dia(conn, HOY)), 1,
            "y no se la lleva la siguiente sincronizacion")
    conn.close()


def la_hoja_de_cocina_dice_si_se_puede_quitar(c):
    """Una restriccion que vino de Opera NO se puede borrar: volveria en la siguiente
    sincronizacion. Lo que si se puede es corregirla, y al corregirla queda marcada y el
    cargador ya no la pisa.

    La pantalla tiene que saberlo para ofrecer lo que de verdad hace. Un boton «Quitar»
    que no quita nada es peor que no tenerlo: se usa, parece que funciono, y la alergia
    reaparece al dia siguiente."""
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    r = dict(reserva(670220, "07", llega, sale, adl=2),
             notas="One allergy to gluten")
    cargar([r], vistas=[r])

    lista = rest.restricciones_del_dia(conn, HOY)
    c.igual(len(lista), 1, "hay una restriccion")
    if lista:
        c.cierto("origen" in lista[0], "la hoja sabe de donde vino")
        # Lo que importa no es el nombre del origen —'OPERA' hoy, 'PDF' cuando entra por
        # el reporte— sino que NO sea MANUAL, que es la unica que se puede borrar.
        c.igual(lista[0]["origen"] == "MANUAL", False,
                "esta vino de la fuente, asi que no se puede borrar")
        c.igual(lista[0]["editado_a_mano"], False, "y todavia nadie la toco")

    # Y una anotada a mano SI se puede quitar: si no, el boton no tendria sentido nunca.
    conn.execute(
        """INSERT INTO amenidad_tarea (conf_no, amenidad, origen, detalle, tarea,
                                       area_responsable, estado)
           VALUES ('670220', 'Restricción alimentaria / alergia', 'MANUAL',
                   'sin cilantro', 'AVISAR A COCINA', 'Cocina', 'PENDIENTE')""")
    conn.commit()
    a_mano = [x for x in rest.restricciones_del_dia(conn, HOY)
              if x["origen"] == "MANUAL"]
    c.igual(len(a_mano), 1, "la anotada a mano sale marcada como tal")
    conn.close()


PRUEBAS = [
    el_reparto_automatico_no_parte_un_grupo,
    mover_una_habitacion_del_grupo_las_mueve_todas,
    mover_una_reserva_sola_no_arrastra_a_nadie,
    destildando_la_casilla_sale_una_sola,
    a_quien_ya_separaron_a_mano_no_se_le_pisa,
    a_quien_tiene_cena_privada_no_se_le_mueve,
    el_que_ya_se_fue_no_se_mueve,
    mover_dos_veces_no_duplica_filas,
    el_almuerzo_usa_su_propia_comida,
    el_boton_manda_lo_del_grupo,
    la_alergia_sale_en_restaurantes_y_NO_en_amenidades,
    la_alergia_que_no_es_de_comida_va_como_alerta,
    la_alerta_de_la_alergia_no_alimentaria_llega_a_la_base,
    la_fila_de_la_alergia_no_se_borra,
    la_misma_alergia_vista_por_dos_fuentes_es_UNA_fila,
    al_juntar_las_dos_fuentes_no_se_pierde_el_trabajo_hecho,
    la_misma_nota_en_dos_reservas_es_UNA_alergia,
    dos_alergias_sin_detalle_no_se_juntan,
    la_hoja_de_cocina_dice_si_se_puede_quitar,
    una_alergia_quitada_a_mano_no_vuelve_al_sincronizar,
    una_alergia_quitada_se_puede_devolver,
    una_alergia_agregada_a_mano_sale_en_la_hoja,
]


if __name__ == "__main__":
    sys.exit(comun.correr("restaurantes y grupos", PRUEBAS))
