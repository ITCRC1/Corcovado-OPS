"""Los cuartos de la casa de guias: entran en la operacion sin ser habitaciones de hotel.

LO PIDIO EL LODGE. Opera manda los cuartos de la casa de guias con su propio numero y una
«G» detras —31G y 32G— y ahi mete Reservas al guia de un grupo: «estas no corresponden de
forma directa como habitaciones de hotel, porque solo se habilitan cuando Reservas coloca
el guia ahi; hay que contarlas dentro de la operacion cuando aparezcan y que actue como
una habitacion mas del hotel con el grupo que corresponda».

QUE HACIA FALTA Y QUE NO. Medido antes de tocar nada con una reserva en «31G»: ya entraba
en el resumen, en los desayunos, en el reparto del comedor y en la hoja del dia, y viajaba
con su grupo porque comparte el block code. Eso no se toco. Lo que faltaba:

  · el NOMBRE. «31G» no le dice nada a quien lee la hoja en el muelle;
  · el ORDEN. Las listas ordenan con CAST(room_no AS INTEGER), y de un numero que no
    empieza por digito eso da 0: el cuarto de guias se habria puesto antes de la 01 en
    las quince pantallas que ordenan asi;
  · la OCUPACION. No es una habitacion que se venda.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun
from comun import cargar, reserva

import habitaciones as habs

HOY = datetime.date.today()
USUARIO = {"usuario": "pruebas", "rol": "ADMIN"}
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dd(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def _un_grupo_con_su_guia(cuarto="31G"):
    """Dos habitaciones de agencia y el guia que las acompaña, como lo manda Opera."""
    ayer = HOY - datetime.timedelta(days=1)
    luego = HOY + datetime.timedelta(days=3)
    cargar([
        dict(reserva("G0001", "11", dd(ayer), dd(luego), estado="EN CASA", adl=2,
                     block_code="AGENCIA1"), regimen="PENSION_COMPLETA"),
        dict(reserva("G0002", "12", dd(ayer), dd(luego), estado="EN CASA", adl=2,
                     block_code="AGENCIA1"), regimen="PENSION_COMPLETA"),
        dict(reserva("G0003", cuarto, dd(ayer), dd(luego), estado="EN CASA", adl=1,
                     block_code="AGENCIA1"), nombre_principal="Campos/Jimmy",
             regimen="PENSION_COMPLETA"),
    ])


# ---------------------------------------------------------------------------
# Que lleguen: Opera los marca igual que las PM de facturacion
# ---------------------------------------------------------------------------

def _crudo_de_opera(conf, hab, tarifa="GUIA", pseudo=True, nombre="Campos/Jimmy"):
    """Una reserva como la manda Opera. Los valores son los REALES de la ventana del
    lodge, leidos de la API: ver el comentario de es_cuarto_ficticio."""
    cuarto = {"pseudoRoom": pseudo, "ratePlanCode": tarifa,
              "arrivalDate": "2026-11-22", "departureDate": "2026-11-25",
              "adultCount": 1, "childCount": 0, "numberOfRooms": 1,
              "roomType": "PI", "linkCode": "589711467 BELITZ PARTY"}
    if hab:
        cuarto["roomId"] = hab
    apellido, _, pila = nombre.partition("/")
    return {
        "reservationIdList": [{"type": "Reservation", "id": conf}],
        "roomStay": cuarto,
        "reservationGuest": {"profileInfo": {"profile": {"customer": {"personName": [
            {"surname": apellido, "givenName": pila}]}}}},
    }


def el_cuarto_de_guias_no_se_descarta_como_una_PM(c):
    """EL FALLO QUE REPORTO EL LODGE: «no aparece, tampoco en restaurantes, tours y
    demas informaciones donde debe aparecer».

    La reserva se perdia ANTES de entrar, en el filtro de pseudo-rooms, y sin ningun
    error. Opera marca `pseudoRoom: true` en los cuartos de la casa de guias por lo mismo
    que en las PM de facturacion —no se venden— pero no se parecen en nada: aqui duerme
    una persona, con su nombre, que come con un grupo y sale a los tours con el.

    Comprobado contra la API de Opera: de las 226 pseudo-rooms de la ventana, 15 son
    cuartos de guias que se estaban perdiendo y 211 son PM de verdad.
    """
    import opera_mapeo as om

    # El caso exacto que reporto el lodge: 596208023, Campos/Jimmy, cuarto 31G.
    suya = _crudo_de_opera("596208023", "31G")
    c.igual(om.es_cuarto_ficticio(suya), False, "el cuarto de guias YA no se descarta")
    r = om.mapear(suya)
    c.cierto(r is not None, "y la reserva se mapea")
    c.igual(r["conf_no"], "596208023", "con su numero")
    c.igual(r["adl"], 1, "y su pax: hay una persona durmiendo ahi")

    # Las DOS señales, porque ninguna sola alcanza. Medido en la ventana del lodge:
    # uno llega sin habitacion asignada —solo con la tarifa GUIA— y otro tiene
    # habitacion «33G» con una tarifa distinta.
    sin_hab = _crudo_de_opera("600380184", None, nombre="GUIA/STAFF")
    c.igual(om.es_cuarto_ficticio(sin_hab), False,
            "el que todavia no tiene cuarto entra por la tarifa GUIA")
    otra_tarifa = _crudo_de_opera("602723837", "33G", tarifa="HUSR")
    c.igual(om.es_cuarto_ficticio(otra_tarifa), False,
            "y el 33G entra por el numero, aunque su tarifa sea otra")


def las_PM_de_verdad_se_siguen_descartando(c):
    """La otra mitad, y la que hace que esto se pueda aplicar sin romper nada.

    Las PM —«posting master»— son las habitaciones de facturacion de un grupo: no hay
    nadie a quien llevarle una amenidad ni quien salga a un tour. Medido en su dia: el
    cuarto 9000 entraba a la agenda como una llegada normal con 0 adultos, y recepcion
    veia un cuarto que no esta en el hotel sin forma de saber por que.
    """
    import opera_mapeo as om
    for conf, hab, tarifa in (("900001", "9000", "PMTR"), ("900002", "PM1", "RACK"),
                              ("900003", None, "PMTR")):
        pm = _crudo_de_opera(conf, hab, tarifa=tarifa, nombre="HOLD/HOLD")
        c.igual(om.es_cuarto_ficticio(pm), True,
                f"la PM {hab or 'sin cuarto'} se sigue dejando fuera")
        c.igual(om.mapear(pm), None, "y no se mapea")

    # Una habitacion normal no es pseudo-room y entra, como siempre.
    normal = _crudo_de_opera("589711467", "13", tarifa="A30OL", pseudo=False,
                             nombre="Belitz/Party")
    c.igual(om.es_cuarto_ficticio(normal), False, "una habitacion de hotel entra")


# ---------------------------------------------------------------------------
# Reconocerlos y nombrarlos
# ---------------------------------------------------------------------------

def el_cuarto_de_guias_se_reconoce_y_se_renombra(c):
    """«31G» es el cuarto 16 de la casa de guias y «32G» el 15. Lo dijo el lodge.

    Se traduce a «G16» y no a «16» a secas porque el lodge YA tiene una habitacion 16 de
    huespedes: con «16» habria dos renglones con el mismo numero en la hoja del dia y
    nadie podria saber cual es cual.
    """
    c.igual(habs.normalizar("31G"), "G16", "31G es la 16 de guias")
    c.igual(habs.normalizar("32G"), "G15", "32G es la 15")
    c.igual(habs.normalizar("16"), "16", "y la 16 de huespedes se queda como esta")
    c.igual(habs.normalizar("08"), "08", "igual que cualquier otra")

    c.igual(habs.es_de_guia("31G"), True, "31G es de guias")
    c.igual(habs.es_de_guia("G16"), True, "y sigue siendolo con el nombre nuevo")
    c.igual(habs.es_de_guia("16"), False, "la 16 de huespedes NO lo es")
    c.igual(habs.es_de_guia(""), False, "y la falta de numero tampoco")
    c.igual(habs.es_de_guia(None), False, "ni la ausencia")

    # UNO QUE NO ESTE EN EL MAPA. El lodge puede habilitar otro cuarto sin avisar, y es
    # mejor que salga marcado como de guias —en su sitio al final de la lista— a que
    # entre como una habitacion de hotel mas y descuadre la ocupacion en silencio.
    c.igual(habs.es_de_guia("33G"), True, "un cuarto nuevo se reconoce por la G")
    c.igual(habs.normalizar("33G"), "G33", "y se nombra igual que los demas")


def el_numero_se_traduce_AL_CARGAR_y_no_al_dibujar(c):
    """Se traduce en el cargador, que es por donde entran todas.

    Traducirlo al dibujar habria obligado a tocar las quince pantallas que enseñan el
    numero de habitacion, y la que se olvidara diria «31G» mientras la de al lado dice
    «G16» — que es la clase de contradiccion que este sistema ya tuvo tres veces.
    """
    conn = comun.base_limpia()
    conn.close()
    _un_grupo_con_su_guia()

    conn = comun.conexion()
    guardado = {f["conf_no"]: f["room_no"] for f in conn.execute(
        "SELECT conf_no, room_no FROM reserva")}
    conn.close()
    c.igual(guardado["G0003"], "G16", "en la base ya esta con el numero del lodge")
    c.igual(guardado["G0001"], "11", "y las habitaciones normales no se tocan")


def las_que_ya_estaban_cargadas_se_renombran_al_arrancar(c):
    """El cargador arregla las que entren de ahora en adelante; las que YA estaban se
    quedarian con el numero de Opera para siempre, y en la hoja del dia el renglon del
    guia diria «31G»."""
    import contextlib
    import io
    import init_db
    conn = comun.base_limpia()
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES ('G9001','31G','Campos/Jimmy','01-01-27','04-01-27',1,0,1,'EN CASA')""")
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES ('G9002','32G','Otro/Guia','01-01-27','04-01-27',1,0,1,'EN CASA')""")
    conn.commit()

    # Por _migrar, que es por donde pasa de verdad: corre en cada arranque.
    with contextlib.redirect_stdout(io.StringIO()):
        init_db._migrar(conn)

    quedaron = {f["conf_no"]: f["room_no"] for f in conn.execute(
        "SELECT conf_no, room_no FROM reserva")}
    c.igual(quedaron["G9001"], "G16", "la que estaba como 31G pasa a G16")
    c.igual(quedaron["G9002"], "G15", "y la 32G a G15")
    c.igual(init_db._renombrar_los_cuartos_de_guias(conn), 0,
            "y correrla de nuevo no cambia nada")
    conn.close()


# ---------------------------------------------------------------------------
# Que cuente en la operacion, como una habitacion mas
# ---------------------------------------------------------------------------

def el_guia_cuenta_en_la_operacion_del_dia(c):
    """«Que actue como una habitacion mas del hotel». Duerme aqui, desayuna aqui y sale
    en la hoja del dia como cualquier otro renglon."""
    import main
    import hoja_dia as hd
    conn = comun.base_limpia()
    conn.close()
    _un_grupo_con_su_guia()

    r = main._datos_del_resumen(HOY.isoformat())
    c.igual([x["room_no"] for x in r["en_casa"]], ["11", "12", "G16"],
            "esta en casa, y AL FINAL de la lista")
    c.igual([x["room_no"] for x in r["desayunos"]], ["11", "12", "G16"],
            "y desayuna")
    c.igual(r["pax_en_casa"], 5, "sus pax cuentan: dos cuartos de dos y el guia")

    conn = comun.conexion()
    hoja = hd.definicion(conn, HOY.isoformat(), r)
    conn.close()
    filas = {f["hab"]: f for f in hoja["filas"]}
    c.cierto("G16" in filas, "sale en la hoja del dia")
    c.igual(filas["G16"]["huesped"], "JIMMY CAMPOS", "con el nombre del guia")
    c.igual(filas["G16"]["pax"], 1, "y su pax")


def el_guia_come_con_su_grupo(c):
    """Lo eligio el lodge: va al mismo restaurante que las habitaciones a las que
    acompaña y cuenta para la capacidad. Es lo que significa «con el grupo que
    corresponda»: el block code ya los junta, y eso es lo que hace que no se separen."""
    import restaurantes as rest
    import grupos
    conn = comun.base_limpia()
    conn.close()
    _un_grupo_con_su_guia()

    conn = comun.conexion()
    claves = {f["room_no"]: grupos.clave_de(dict(f)) for f in conn.execute(
        "SELECT room_no, grupo_id, block_code, conf_no FROM reserva")}
    d = rest.distribuir(conn, HOY)
    conn.close()

    c.igual(len(set(claves.values())), 1,
            "el guia viaja con su grupo: una sola clave para los tres")
    juntos = d["cena"]["terra_kitchen"] + d["cena"]["bar_el_bosque"]
    donde = {x["room_no"]: ("TK" if x in d["cena"]["terra_kitchen"] else "BOSQUE")
             for x in juntos}
    c.igual(len(set(donde.values())), 1,
            "los tres cenan en el MISMO restaurante, el guia incluido")
    c.cierto("G16" in donde, "el cuarto de guias esta sentado")
    c.igual(d["cena"]["total"], 5, "y sus pax cuentan para la capacidad")


def el_cuarto_de_guias_no_sube_la_ocupacion(c):
    """No es una habitacion que se venda. Con 31 ocupados sobre 30 vendibles el informe
    habria pasado del 100% sin que nadie hubiera vendido de mas.

    El guia SI sigue contando en el pax: esta durmiendo aqui y comiendo aqui.
    """
    import main
    import informe
    conn = comun.base_limpia()
    conn.close()
    _un_grupo_con_su_guia()

    oc = main.ocupacion(HOY.isoformat(), HOY.isoformat(), user=USUARIO)
    dia = oc["dias"][0]
    c.igual(dia["habitaciones"], 2, "cuentan las DOS habitaciones de hotel")
    c.igual(dia["pax"], 5, "y los cinco pax, el guia incluido")
    c.igual(dia["porcentaje"], round(100 * 2 / oc["total_habitaciones"]),
            "el porcentaje sale de las que se venden")

    conn = comun.conexion()
    m = informe.metricas(conn, HOY.isoformat(), HOY.isoformat())
    conn.close()
    c.igual(m["pax_noche"], 5, "el informe cuenta los cinco pax")
    c.igual(m["ocupacion"], round(100 * 2 / informe.total_habitaciones()),
            "y la misma ocupacion que la pantalla: las dos salen de la misma regla")

    # La funcion, por si alguien la reusa.
    c.igual(habs.solo_las_que_se_venden({"11", "12", "G16"}), {"11", "12"},
            "el cuarto de guias sale de la cuenta")
    c.igual(habs.solo_las_que_se_venden({"11", "16"}), {"11", "16"},
            "y la 16 de huespedes se queda, que esa si se vende")


# ---------------------------------------------------------------------------
# El orden de las listas
# ---------------------------------------------------------------------------

def el_cuarto_de_guias_va_al_FINAL_de_las_listas(c):
    """CAST('G16' AS INTEGER) da 0, asi que ordenando como antes el cuarto de guias se
    habria puesto ANTES de la 01 en las quince pantallas que ordenan por habitacion. No
    daba error: daba una lista en la que el primer renglon no es el que uno espera."""
    conn = comun.base_limpia()
    for hab in ("04", "23", "G16", "01", "G15"):
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                    dep_date, adl, chl, rooms, res_status)
               VALUES (?,?,'Prueba/Uno','01-01-27','04-01-27',2,0,1,'EN CASA')""",
            (f"X{hab}", hab))
    conn.commit()
    orden = [f[0] for f in conn.execute(
        "SELECT room_no FROM reserva ORDER BY " + habs.ORDEN)]
    conn.close()
    c.igual(orden, ["01", "04", "23", "G15", "G16"],
            "las de hotel por numero y los cuartos de guias al final")

    # La misma regla en Python, para lo que no se ordena en SQL.
    c.igual(sorted(["04", "23", "G16", "01", "G15"], key=habs.orden),
            ["01", "04", "23", "G15", "G16"],
            "y ordenando en Python sale igual")


def ninguna_consulta_se_quedo_ordenando_a_la_vieja(c):
    """Son quince sitios en cinco archivos. El que se olvide deja ESA pantalla ordenando
    distinto que las otras catorce, y no da ningun error: solo una lista con el cuarto de
    guias colado delante de la 01."""
    import re
    sueltas = []
    for carpeta, _, archivos in os.walk(os.path.join(RAIZ, "backend")):
        for nombre in archivos:
            if not nombre.endswith(".py"):
                continue
            ruta = os.path.join(carpeta, nombre)
            with open(ruta, encoding="utf-8") as f:
                texto = f.read()
            for m in re.finditer(r"CAST\(\w*\.?room_no\s+AS\s+INTEGER\)", texto):
                # La propia expresion compartida si lo usa: es donde vive.
                if nombre == "habitaciones.py":
                    continue
                sueltas.append(f"{nombre}:{texto[:m.start()].count(chr(10)) + 1}")
    c.igual(sueltas, [],
            "ninguna consulta ordena con CAST(room_no) por su cuenta")


PRUEBAS = [
    el_cuarto_de_guias_no_se_descarta_como_una_PM,
    las_PM_de_verdad_se_siguen_descartando,
    el_cuarto_de_guias_se_reconoce_y_se_renombra,
    el_numero_se_traduce_AL_CARGAR_y_no_al_dibujar,
    las_que_ya_estaban_cargadas_se_renombran_al_arrancar,
    el_guia_cuenta_en_la_operacion_del_dia,
    el_guia_come_con_su_grupo,
    el_cuarto_de_guias_no_sube_la_ocupacion,
    el_cuarto_de_guias_va_al_FINAL_de_las_listas,
    ninguna_consulta_se_quedo_ordenando_a_la_vieja,
]


if __name__ == "__main__":
    sys.exit(comun.correr("cuartos de guias", PRUEBAS))
