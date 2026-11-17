"""La hora de un tour: como se escribe, como se guarda y como se dibuja.

EL FALLO QUE FIJA ESTA SUITE. Se agrego al catalogo una cabalgata de la tarde con la
hora escrita «2:00 pm», que es como la escribe cualquiera. El campo es texto libre y se
guardaba tal cual; todo lo que lo lee da por hecho «HH:MM» y lo parte por los dos
puntos, asi que la hora se leyo como las dos de la madrugada:

  · la linea del dia del Dashboard recortaba al borde cualquier salida fuera de la
    jornada, asi que la cabalgata se dibujo pegada al borde izquierdo y el pajareo de
    las 6 le quedo encima. Desde la pantalla el tour no existia;
  · el detector de choques, que no pudo leer «00 pm», supone que dos salidas PODRIAN
    coincidir cuando no entiende una hora: marco un conflicto con el PNC que no era;
  · la agenda ordena por el texto, asi que la ponia entre las 00 y las 06.

Ninguna de las tres da error. La salida sale en la tabla de abajo y no sale en la
linea, que es la forma de fallar que nadie reporta porque nadie la ve.

Las dos mitades de la correccion: la hora se normaliza AL GUARDARLA (backend/horas.py,
el catalogo y el arranque), y la linea del dia ESTIRA la ventana en vez de recortar,
reparte las cajas por el hueco que ocupan en pantalla y enseña aparte las salidas sin
hora en vez de tirarlas.
"""
import asyncio
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "frontend", "index.html")

HOY = datetime.date.today()
USUARIO = {"usuario": "pruebas", "rol": "ADMIN"}


def _pms(d):
    """date -> el 'DD-MM-YY' que guarda el PMS."""
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def _html():
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def _funcion_js(html, nombre):
    """El cuerpo de una funcion de JavaScript del index.html, contando las llaves."""
    i = html.find(f"function {nombre}(")
    if i < 0:
        return ""
    nivel, j = 0, i
    while j < len(html):
        if html[j] == "{":
            nivel += 1
        elif html[j] == "}":
            nivel -= 1
            if nivel == 0:
                return html[i:j + 1]
        j += 1
    return ""


def _sin_comentarios(texto):
    return "\n".join(r for r in texto.split("\n") if not r.lstrip().startswith("//"))


def _reserva(conn, conf_no, room="04"):
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES (?,?,?,?,?,2,0,1,'EN CASA')""",
        (str(conf_no), room, f"Huesped {conf_no}", _pms(HOY - datetime.timedelta(days=1)),
         _pms(HOY + datetime.timedelta(days=3))))


def _salida(conn, conf_no, codigo, guia=None, pax=2, fecha=None):
    conn.execute(
        """INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, guia_nombre, pax)
           VALUES (?,?,?,?,?)""",
        (str(conf_no), (fecha or HOY).isoformat(), codigo, guia, pax))


# ---------------------------------------------------------------------------
# Leer una hora escrita a mano
# ---------------------------------------------------------------------------

# Lo que de verdad se teclea en la caja del catalogo. La columna de la derecha son los
# minutos desde la medianoche.
COMO_SE_ESCRIBE = [
    ("14:00", 840), ("07:30", 450), ("7:30", 450), ("7.30", 450), ("7h30", 450),
    ("7 30", 450), ("730", 450), ("1400", 840), ("7", 420), ("14", 840),
    ("2:00 pm", 840), ("2:00 p.m.", 840), ("2:00 p. m.", 840), ("2 pm", 840),
    ("2PM", 840), ("2:00pm", 840), ("7:15 am", 435), ("7:15 a.m.", 435),
    ("12 am", 0), ("12:00 am", 0), ("12 pm", 720), ("12:30 pm", 750),
    ("00:00", 0), ("23:59", 1439),
    # Ya viene en 24 horas y ademas trae la marca: la marca no manda, o se iria al dia
    # siguiente.
    ("14:00 p.m.", 840),
    # Con espacios de mas y con el espacio duro que deja un copiar y pegar.
    ("  14:00  ", 840), ("14:00 ", 840),
]

NO_ES_UNA_HORA = ["manana", "despues del desayuno", "25:00", "7:75", "pm", "-1",
                  "14:00 a 16:30", "7:30-11:30", "a las 7", ""]


def una_hora_escrita_a_mano_se_entiende(c):
    """La caja del catalogo es texto libre y cada quien escribe la hora a su manera."""
    import horas
    for texto, minutos in COMO_SE_ESCRIBE:
        c.igual(horas.a_minutos(texto), minutos, f"«{texto}» son {minutos} minutos")
    c.igual(horas.normalizar("2:00 pm"), "14:00", "y se guarda siempre como HH:MM")
    c.igual(horas.normalizar("730"), "07:30", "con su cero adelante")


def lo_que_no_es_una_hora_no_se_inventa(c):
    """Adivinar seria peor: una hora inventada en el catalogo sale despues en la hoja
    del dia que el staff lee por WhatsApp, y ahi ya nadie duda de ella."""
    import horas
    for texto in NO_ES_UNA_HORA:
        c.igual(horas.a_minutos(texto), None, f"«{texto}» no es una hora")
    c.igual(horas.a_minutos(None), None, "y sin nada tampoco")
    c.cierto(horas.esta_en_blanco("") and horas.esta_en_blanco("   "),
             "el vacio se distingue de lo ilegible")
    c.cierto(not horas.esta_en_blanco("manana"), "lo ilegible no es vacio")

    # «2:00» a secas son las 2 de la madrugada y asi se guarda: no hay forma de saber si
    # quien lo escribio pensaba en la tarde.
    c.igual(horas.a_minutos("2:00"), 120, "sin marca no se supone la tarde")

    c.igual(horas.exigir("", "hora de inicio"), None, "un tour sin hora es legitimo")
    try:
        horas.exigir("despues del desayuno", "hora de inicio")
        c.cierto(False, "lo que no se entiende tiene que protestar")
    except ValueError as e:
        c.cierto("hora de inicio" in str(e) and "14:00" in str(e),
                 "y decir que campo es y como se escribe")


# ---------------------------------------------------------------------------
# El catalogo, que es por donde entra
# ---------------------------------------------------------------------------

def el_catalogo_guarda_la_hora_en_24_horas(c):
    """El caso de la cabalgata, por el camino de verdad: la pantalla de Catalogo."""
    conn = comun.base_limpia()
    conn.close()
    import main                      # despues de la base: al importarse abre la suya

    asyncio.run(main.crear_tour(
        {"codigo": "cabalgata pm", "nombre": "Cabalgata de la tarde",
         "horario_inicio": "2:00 pm", "horario_fin": "4:30 pm", "max_pax_guia": 6},
        user=USUARIO))

    conn = comun.conexion()
    fila = dict(conn.execute(
        "SELECT * FROM tour_catalogo WHERE codigo = 'CABALGATA PM'").fetchone())
    c.igual(fila["horario_inicio"], "14:00", "«2:00 pm» se guarda como 14:00")
    c.igual(fila["horario_fin"], "16:30", "y el fin igual")

    asyncio.run(main.editar_tour("CABALGATA PM",
                                 {"horario_inicio": "3pm", "horario_fin": "17:00"},
                                 user=USUARIO))
    fila = dict(conn.execute(
        "SELECT * FROM tour_catalogo WHERE codigo = 'CABALGATA PM'").fetchone())
    c.igual(fila["horario_inicio"], "15:00", "al corregirla tambien se normaliza")
    c.igual(fila["horario_fin"], "17:00", "y lo que ya estaba bien no se toca")
    conn.close()


def una_hora_que_no_se_entiende_se_rechaza_y_se_dice(c):
    """Guardarla en blanco seria convertir el error en una ausencia: el tour se queda
    sin hora, desaparece de la linea del dia y nadie sabe por que."""
    conn = comun.base_limpia()
    conn.close()
    from fastapi import HTTPException
    import main

    try:
        asyncio.run(main.crear_tour(
            {"codigo": "KAYAK", "nombre": "Kayak", "max_pax_guia": 6,
             "horario_inicio": "despues del desayuno"}, user=USUARIO))
        c.cierto(False, "una hora ilegible al crear tiene que dar 400")
    except HTTPException as e:
        c.igual(e.status_code, 400, "al crear, 400")
        c.cierto("despues del desayuno" in e.detail,
                 "y el mensaje repite lo que se escribio")

    conn = comun.conexion()
    c.igual(conn.execute("SELECT COUNT(*) FROM tour_catalogo WHERE codigo='KAYAK'").fetchone()[0],
            0, "y el tour NO se crea a medias")

    # Y sobre uno que ya existe: la hora buena se queda como estaba.
    try:
        asyncio.run(main.editar_tour("CABALGATA", {"horario_inicio": "por la tarde"},
                                     user=USUARIO))
        c.cierto(False, "una hora ilegible al editar tiene que dar 400")
    except HTTPException as e:
        c.igual(e.status_code, 400, "al editar, 400")
    c.igual(dict(conn.execute(
        "SELECT * FROM tour_catalogo WHERE codigo='CABALGATA'").fetchone())["horario_inicio"],
        "07:30", "y la hora que ya estaba guardada no se borra")
    conn.close()


def el_fin_antes_que_el_inicio_se_rechaza(c):
    """Ningun tour del lodge cruza la medianoche, asi que es siempre un dedazo. Con las
    horas al reves la caja se dibuja con duracion negativa."""
    conn = comun.base_limpia()
    conn.close()
    from fastapi import HTTPException
    import main
    try:
        asyncio.run(main.crear_tour(
            {"codigo": "PESCA PM", "nombre": "Pesca de tarde", "max_pax_guia": 6,
             "horario_inicio": "14:00", "horario_fin": "11:00"}, user=USUARIO))
        c.cierto(False, "el fin antes que el inicio tiene que protestar")
    except HTTPException as e:
        c.igual(e.status_code, 400, "400 y no un tour imposible")
        c.cierto("11:00" in e.detail and "14:00" in e.detail,
                 "diciendo las dos horas")


def el_arranque_arregla_las_horas_que_ya_estaban_guardadas(c):
    """La cabalgata ya estaba creada cuando se encontro el fallo. Corregir solo de aqui
    en adelante la habria dejado invisible hasta que alguien la reescribiera a mano."""
    import init_db
    conn = comun.base_limpia()
    conn.execute(
        """INSERT INTO tour_catalogo (codigo, nombre, horario_inicio, horario_fin,
                                      max_pax_guia)
           VALUES ('CABALGATA PM','Cabalgata de la tarde','2:00 pm','4:30 pm',6)""")
    conn.execute(
        """INSERT INTO tour_catalogo (codigo, nombre, horario_inicio, max_pax_guia)
           VALUES ('RARO','Tour raro','cuando amanezca',6)""")
    conn.commit()

    arreglados = init_db._normalizar_horas_del_catalogo(conn)
    fila = dict(conn.execute(
        "SELECT * FROM tour_catalogo WHERE codigo='CABALGATA PM'").fetchone())
    c.igual(fila["horario_inicio"], "14:00", "la que ya estaba guardada se reescribe")
    c.igual(fila["horario_fin"], "16:30", "las dos horas")
    c.cierto(arreglados >= 1, "y dice cuantas toco")

    c.igual(dict(conn.execute(
        "SELECT * FROM tour_catalogo WHERE codigo='RARO'").fetchone())["horario_inicio"],
        "cuando amanezca",
        "lo que no se entiende se deja como esta, no se borra")

    # Idempotente: al siguiente arranque no hay nada que hacer.
    c.igual(init_db._normalizar_horas_del_catalogo(conn), 0,
            "y al segundo arranque no toca nada")
    conn.close()


# ---------------------------------------------------------------------------
# Lo que la hora mal leida rompia ademas
# ---------------------------------------------------------------------------

def una_hora_ilegible_ya_no_inventa_un_conflicto(c):
    """Cuando no se entiende una hora se supone que las salidas PODRIAN coincidir, para
    avisar en vez de callar. Con «2:00 pm» ilegible, eso marcaba en rojo al guia del PNC
    por un choque que no existe — y un aviso que sale siempre se deja de mirar."""
    import validations
    conn = comun.base_limpia()
    conn.execute(
        """INSERT INTO tour_catalogo (codigo, nombre, horario_inicio, horario_fin,
                                      max_pax_guia)
           VALUES ('CABALGATA PM','Cabalgata de la tarde','2:00 pm','4:30 pm',6)""")
    conn.execute("INSERT INTO guia (nombre) VALUES ('PABLO')")
    _reserva(conn, 700001, room="03")
    _salida(conn, 700001, "PNC", guia="PABLO")
    _salida(conn, 700001, "CABALGATA PM", guia="PABLO")
    conn.commit()
    conn.close()

    choques = validations.detectar_conflictos_asignacion(HOY.isoformat())
    c.igual(len(choques), 0,
            "el PNC de la manana y la cabalgata de la tarde no chocan")

    # Y un choque de verdad se sigue viendo: mismo guia, dos salidas de la manana.
    conn = comun.conexion()
    _salida(conn, 700001, "SNORKEL", guia="PABLO")
    conn.commit()
    conn.close()
    choques = validations.detectar_conflictos_asignacion(HOY.isoformat())
    c.cierto(any("PABLO" in x["mensaje"] for x in choques),
             "pero el PNC y el snorkel, que si se pisan, se siguen avisando")


def la_salida_llega_a_la_pantalla_con_su_hora(c):
    """De punta a punta: se crea el tour desde Catalogo, se le asigna una reserva y el
    Dashboard —que es lo que dibuja la linea del dia— lo entrega con la hora en HH:MM."""
    conn = comun.base_limpia()
    conn.close()
    import main
    asyncio.run(main.crear_tour(
        {"codigo": "CABALGATA PM", "nombre": "Cabalgata de la tarde",
         "horario_inicio": "2:00 pm", "horario_fin": "4:30 pm", "max_pax_guia": 6},
        user=USUARIO))

    conn = comun.conexion()
    _reserva(conn, 700002, room="03")
    _salida(conn, 700002, "CABALGATA PM")
    conn.commit()
    conn.close()

    d = main.dashboard(HOY.isoformat(), user=USUARIO)
    suyo = [t for t in d["tours"] if t["tour_codigo"] == "CABALGATA PM"]
    c.igual(len(suyo), 1, "la salida llega al Dashboard")
    c.igual(suyo[0]["horario_inicio"], "14:00", "con la hora de la tarde")
    c.igual(suyo[0]["horario_fin"], "16:30", "y su hora de fin")


# ---------------------------------------------------------------------------
# La linea del dia (se lee el HTML como texto: no hay navegador aqui)
#
# La comprobacion de verdad, con un navegador y la funcion real, esta en
# pruebas/jornada.html: se abre y dice cuantas pasan.
# ---------------------------------------------------------------------------

def la_linea_del_dia_estira_la_ventana_en_vez_de_recortar(c):
    """Recortar al borde es lo que escondio la cabalgata debajo del pajareo."""
    cuerpo = _sin_comentarios(_funcion_js(_html(), "lineaDelDia"))
    c.cierto(cuerpo, "lineaDelDia sigue existiendo")
    c.cierto("let INICIO" in cuerpo and "const INICIO" not in cuerpo,
             "la ventana ya no es fija")
    c.cierto("JORNADA_INICIO" in cuerpo and "JORNADA_FIN" in cuerpo,
             "arranca siendo la jornada normal del lodge")
    c.cierto("INICIO = Math.max(0" in cuerpo and "FIN = Math.min(24 * 60" in cuerpo,
             "y se estira hasta donde haga falta")
    c.cierto("const SPAN = FIN - INICIO" in cuerpo,
             "el ancho se calcula DESPUES de estirar, no antes")


def ninguna_salida_se_dibuja_debajo_de_otra(c):
    """Dos cajas pueden pisarse aunque sus horarios no se toquen: la caja tiene un ancho
    minimo de 52 px. El reparto en pistas mide el hueco en pantalla, no el horario."""
    cuerpo = _sin_comentarios(_funcion_js(_html(), "lineaDelDia"))
    c.cierto("MINIMO_VISIBLE" in cuerpo, "hay un ancho minimo declarado")
    c.cierto("x.hueco" in cuerpo and "x.dur" not in cuerpo,
             "y la pista se elige por el hueco en pantalla, no por la duracion")


def una_salida_sin_hora_se_enseña_en_vez_de_desaparecer(c):
    """El Claro del Bosque y el spa van sin hora a proposito, y un tour nuevo puede
    entrar sin ella. Tirarlas en silencio era la otra forma de perder una salida."""
    html = _html()
    cuerpo = _sin_comentarios(_funcion_js(html, "lineaDelDia"))
    c.cierto("sinHora" in cuerpo, "las salidas sin hora se separan")
    c.cierto("jornada-sinhora" in cuerpo, "y se dibujan en su propia franja")
    c.cierto("Catálogo" in cuerpo or "Catalogo" in cuerpo,
             "diciendo donde se les pone el horario")
    c.cierto(".jornada-sinhora {" in html, "con su estilo")
    c.cierto("t.ini === null" in cuerpo,
             "se separan en vez de descartarse")
    c.cierto("!lista.length && !sinHora.length" in cuerpo,
             "y un dia con solo salidas sin hora tampoco se queda en blanco")


def la_pantalla_lee_la_hora_con_las_mismas_reglas_que_el_servidor(c):
    """Las dos puntas tienen que entender lo mismo.

    Se saca el patron de horaEnMinutos() del index.html y se corre en Python contra las
    mismas tablas de arriba: si alguien toca uno de los dos y no el otro, la hora se
    guarda de una forma y se dibuja de otra. Lo que se compara es que los dos ACEPTEN y
    PARTAN igual —no la aritmetica de despues, que son cinco renglones simetricos—, que
    es por donde se van a separar. Un «25:00» lo parten los dos igual y lo descarta
    despues el control de rango, en las dos puntas.
    """
    import horas
    cuerpo = _funcion_js(_html(), "horaEnMinutos")
    c.cierto(cuerpo, "horaEnMinutos() existe en la pantalla")
    m = re.search(r"\.match\(/(.+?)/\)", cuerpo)
    c.cierto(m, "con su patron")
    if not m:
        return
    patron = re.compile(m.group(1))

    for texto, _ in COMO_SE_ESCRIBE:
        limpio = texto.replace(" ", " ").strip().lower()
        js, py = patron.match(limpio), horas._PATRON.match(limpio)
        c.cierto(bool(js) and bool(py) and js.groups() == py.groups(),
                 f"«{texto}»: la pantalla y el servidor la parten igual")
    for texto in NO_ES_UNA_HORA:
        limpio = texto.replace(" ", " ").strip().lower()
        js, py = patron.match(limpio), horas._PATRON.match(limpio)
        c.igual(bool(js), bool(py),
                f"«{texto}»: la pantalla y el servidor la rechazan igual")

    cuerpo_linea = _sin_comentarios(_funcion_js(_html(), "lineaDelDia"))
    c.cierto("horaEnMinutos" in cuerpo_linea,
             "y la linea del dia la usa en vez de partir por los dos puntos")
    c.cierto('split(":")' not in cuerpo_linea,
             "no quedo ningun resto de la forma vieja de leerla")


def el_nombre_del_tour_no_se_sale_de_su_caja(c):
    """«CABALGATA» en una caja angosta se partia en tres renglones que se salian por
    debajo y se metian en la caja de al lado. Asi se vio el fallo en la captura."""
    html = _html()
    estilo = html.split(".jornada-tour b {")[1].split("}")[0].replace(" ", "")
    c.cierto("white-space:nowrap" in estilo, "el nombre va en una sola linea")
    c.cierto("text-overflow:ellipsis" in estilo,
             "y lo que no cabe se corta con puntos suspensivos")


PRUEBAS = [
    una_hora_escrita_a_mano_se_entiende,
    lo_que_no_es_una_hora_no_se_inventa,
    el_catalogo_guarda_la_hora_en_24_horas,
    una_hora_que_no_se_entiende_se_rechaza_y_se_dice,
    el_fin_antes_que_el_inicio_se_rechaza,
    el_arranque_arregla_las_horas_que_ya_estaban_guardadas,
    una_hora_ilegible_ya_no_inventa_un_conflicto,
    la_salida_llega_a_la_pantalla_con_su_hora,
    la_linea_del_dia_estira_la_ventana_en_vez_de_recortar,
    ninguna_salida_se_dibuja_debajo_de_otra,
    una_salida_sin_hora_se_enseña_en_vez_de_desaparecer,
    la_pantalla_lee_la_hora_con_las_mismas_reglas_que_el_servidor,
    el_nombre_del_tour_no_se_sale_de_su_caja,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Jornada y horas del catalogo", PRUEBAS))
