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
]


if __name__ == "__main__":
    sys.exit(comun.correr("restaurantes y grupos", PRUEBAS))
