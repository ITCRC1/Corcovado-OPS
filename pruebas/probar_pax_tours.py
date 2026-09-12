"""Cuanta gente de una reserva va a cada tour, y que eso no se pierda.

El reporte solo sabe cuanta gente hay en la HABITACION. Que de dos huespedes vaya uno
solo al tour es cosa de recepcion, y hasta ahora no habia donde anotarlo: o quedaba mal
—una entrada de parque de mas, un cupo de bote ocupado sin nadie— o se quitaba el tour
entero y desaparecia tambien el que si iba.

Lo que mas importa aqui es que el numero escrito a mano SOBREVIVA a la siguiente
importacion. Cada ciclo borra y rehace los tours de la reserva; sin la marca, la
correccion se perderia en silencio, que es la peor forma de perderla.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
from comun import cargar, reserva

import tours_pax


TOUR_SIN_ENTRADA = "MANGLAR"     # no requiere entrada al SINAC
TOUR_CON_ENTRADA = "PNC"         # si la requiere


def _reserva_con_tours(conf_no="900001", adl=2, chl=0, dias=(2,), tour=TOUR_SIN_ENTRADA,
                       **extra):
    """Una reserva que llega el 01-01-26 y lleva un tour cada dia de 'dias'."""
    return reserva(conf_no, "07", "01-01-26", "06-01-26", adl=adl, chl=chl,
                   operacion=[{"dia": d, "tour": tour} for d in dias], **extra)


def _tours(conn, conf_no="900001"):
    return [dict(f) for f in conn.execute(
        "SELECT id, fecha, tour_codigo, pax, pax_editado_a_mano FROM tour_asignado "
        "WHERE conf_no = ? ORDER BY fecha", (conf_no,))]


# ---------------------------------------------------------------------------
# Lo que vale por defecto
# ---------------------------------------------------------------------------

def por_defecto_va_la_habitacion_entera(c):
    """Es lo que hacia antes y lo que hay que seguir haciendo mientras nadie diga otra
    cosa: el caso normal es que la habitacion entera vaya al tour."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2, chl=1)])
    t = _tours(conn)
    c.igual(len(t), 1, "se cargo el tour")
    c.igual(t[0]["pax"], 3, "el pax por defecto es adultos + ninos")
    c.igual(t[0]["pax_editado_a_mano"], 0, "y no cuenta como escrito a mano")
    conn.close()


def cada_tour_lleva_su_propio_pax(c):
    """Antes la pantalla mostraba el pax de la RESERVA repetido sobre todos sus tours.
    De tres huespedes pueden ir los tres al nocturno y solo uno al manglar."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=3, dias=(2, 3))])
    t = _tours(conn)
    c.igual(len(t), 2, "dos tours")
    tours_pax.cambiar_pax(conn, t[0]["id"], "1")
    conn.commit()
    t = _tours(conn)
    c.igual([x["pax"] for x in t], [1, 3],
            "cambiar uno no toca el otro")
    conn.close()


# ---------------------------------------------------------------------------
# Escribirlo a mano
# ---------------------------------------------------------------------------

def se_puede_anotar_que_solo_va_uno(c):
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2)])
    t = _tours(conn)
    res = tours_pax.cambiar_pax(conn, t[0]["id"], "1")
    conn.commit()
    c.igual(res["pax"], 1, "queda en 1")
    c.igual(res["editado_a_mano"], True, "y marcado como escrito a mano")
    c.igual(res["pax_habitacion"], 2, "y dice cuantos hay en la habitacion")
    c.igual(_tours(conn)[0]["pax"], 1, "y eso es lo que quedo en la base")
    conn.close()


def vaciar_el_campo_vuelve_a_la_habitacion(c):
    """Sin esto no hay forma de deshacer: el numero quedaria clavado para siempre aunque
    despues cambie la habitacion. Vacio y cero NO son lo mismo."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2)])
    t = _tours(conn)
    tours_pax.cambiar_pax(conn, t[0]["id"], "1")
    conn.commit()
    res = tours_pax.cambiar_pax(conn, t[0]["id"], "")
    conn.commit()
    c.igual(res["pax"], 2, "vuelve a la habitacion entera")
    c.igual(res["editado_a_mano"], False, "y deja de estar marcado")
    c.igual(_tours(conn)[0]["pax_editado_a_mano"], 0, "tambien en la base")
    conn.close()


def no_pueden_ir_mas_de_los_que_hay_en_la_habitacion(c):
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2)])
    t = _tours(conn)
    try:
        tours_pax.cambiar_pax(conn, t[0]["id"], "3")
        c.cierto(False, "3 en una habitacion de 2 tiene que rebotar")
    except tours_pax.PaxInvalido as e:
        c.cierto("2" in str(e), "el mensaje dice cuantos hay en la habitacion")
    c.igual(_tours(conn)[0]["pax"], 2, "y no se escribio nada")
    conn.close()


def cero_no_es_la_forma_de_quitar_un_tour(c):
    """Un tour en cero sigue ocupando fila, cupo y entrada. Para que no vaya nadie esta
    la papelera, que ademas recalcula la entrada del parque."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2)])
    t = _tours(conn)
    try:
        tours_pax.cambiar_pax(conn, t[0]["id"], "0")
        c.cierto(False, "cero tiene que rebotar")
    except tours_pax.PaxInvalido as e:
        c.cierto("papelera" in str(e).lower(), "y el mensaje dice que hacer en su lugar")
    c.igual(_tours(conn)[0]["pax"], 2, "sin escribir nada")

    for malo in ("-1", "dos", "2.5"):
        try:
            tours_pax.cambiar_pax(conn, t[0]["id"], malo)
            c.cierto(False, f"'{malo}' tiene que rebotar")
        except tours_pax.PaxInvalido:
            c.ok += 1
    conn.close()


def un_tour_que_ya_no_existe_no_revienta(c):
    conn = comun.base_limpia()
    c.igual(tours_pax.cambiar_pax(conn, 99999, "1"), None,
            "devuelve None en vez de lanzar, para poder contestar 404")
    conn.close()


# ---------------------------------------------------------------------------
# Que aguante la siguiente importacion. Esto es lo que de verdad protege el trabajo.
# ---------------------------------------------------------------------------

def el_pax_escrito_a_mano_sobrevive_a_la_importacion(c):
    """Cada ciclo borra y rehace los tours de la reserva desde la fuente. Sin la marca,
    el numero volvia a ser la habitacion entera sin que nadie se enterara."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2)])
    t = _tours(conn)
    tours_pax.cambiar_pax(conn, t[0]["id"], "1")
    conn.commit()
    conn.close()

    cargar([_reserva_con_tours(adl=2, marca="2026-09-02T10:00:00Z")])

    conn = comun.conexion()
    t = _tours(conn)
    c.igual(len(t), 1, "sigue habiendo un solo tour")
    c.igual(t[0]["pax"], 1, "el pax escrito a mano SIGUE siendo 1")
    c.igual(t[0]["pax_editado_a_mano"], 1, "y sigue marcado, para la proxima vez")
    conn.close()


def el_pax_que_nadie_toco_si_se_actualiza(c):
    """Lo contrario tambien importa: si nadie lo corrigio, manda la reserva. Si llega
    una persona mas a la habitacion, el tour tiene que contarla."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2)])
    c.igual(_tours(conn)[0]["pax"], 2, "arranca en 2")
    conn.close()

    cargar([_reserva_con_tours(adl=3, marca="2026-09-02T10:00:00Z")])

    conn = comun.conexion()
    c.igual(_tours(conn)[0]["pax"], 3, "pasa a 3 solo")
    conn.close()


def el_pax_a_mano_se_mueve_con_el_tour_si_cambia_de_dia(c):
    """Igual que el guia y el bote: quien no iba a ir tampoco va el dia nuevo."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2, dias=(2,))])
    t = _tours(conn)
    dia_viejo = t[0]["fecha"]
    tours_pax.cambiar_pax(conn, t[0]["id"], "1")
    conn.commit()
    conn.close()

    cargar([_reserva_con_tours(adl=2, dias=(4,), marca="2026-09-02T10:00:00Z")])

    conn = comun.conexion()
    t = _tours(conn)
    c.igual(len(t), 1, "sigue siendo un tour, el mismo movido de dia")
    c.cierto(t[0]["fecha"] != dia_viejo, "y de verdad cambio de dia")
    c.igual(t[0]["pax"], 1, "el pax a mano se fue con el")
    conn.close()


def si_baja_la_gente_de_la_habitacion_el_pax_a_mano_se_recorta(c):
    """No pueden ir a un tour mas personas de las que quedan en la reserva. Sin esto,
    un 3 escrito a mano sobreviviria a que la habitacion pasara a 2."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=4)])
    t = _tours(conn)
    tours_pax.cambiar_pax(conn, t[0]["id"], "3")
    conn.commit()
    conn.close()

    cargar([_reserva_con_tours(adl=2, marca="2026-09-02T10:00:00Z")])

    conn = comun.conexion()
    c.igual(_tours(conn)[0]["pax"], 2,
            "se recorta a los que quedan en la habitacion")
    conn.close()


# ---------------------------------------------------------------------------
# La entrada del parque, que se compra por cabeza
# ---------------------------------------------------------------------------

def la_entrada_del_parque_se_recalcula(c):
    """Se compra por cabeza y con 15 dias de plazo. Si cambia el pax y el total no se
    recalcula, se compran tiquetes de mas o de menos y se descubre tarde."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours("900001", adl=2, tour=TOUR_CON_ENTRADA),
            _reserva_con_tours("900002", adl=2, tour=TOUR_CON_ENTRADA)])

    def total_sinac():
        f = conn.execute(
            "SELECT pax_total_grupo FROM entrada_sinac WHERE tour_codigo = ?",
            (TOUR_CON_ENTRADA,)).fetchone()
        return f["pax_total_grupo"] if f else None

    # 2 + 2 huespedes + 1 entrada para el guia.
    c.igual(total_sinac(), 5, "arranca contando las dos habitaciones y el guia")
    t = _tours(conn, "900001")
    res = tours_pax.cambiar_pax(conn, t[0]["id"], "1")
    conn.commit()
    c.igual(total_sinac(), 4, "al bajar uno, la entrada baja a 4")
    c.cierto(res["sinac"] is not None, "y la respuesta lo dice, para poder avisarlo")
    c.igual(res["sinac"]["pax_total"], 4, "con el total nuevo")
    conn.close()


def el_guia_cuenta_igual_en_las_cuatro_vias(c):
    """La importacion suma +1 por la entrada del guia. El recalculo que corre al agregar,
    quitar o editar un tour NO lo sumaba, asi que cualquiera de esas tres acciones bajaba
    el total en uno y se compraba una entrada de menos — sin aviso."""
    conn = comun.base_limpia()
    cargar([_reserva_con_tours("900001", adl=3, tour=TOUR_CON_ENTRADA)])
    del_import = conn.execute(
        "SELECT pax_total_grupo p FROM entrada_sinac WHERE tour_codigo = ?",
        (TOUR_CON_ENTRADA,)).fetchone()["p"]
    t = _tours(conn, "900001")
    recalculado = tours_pax.pax_sinac_pendiente(conn, TOUR_CON_ENTRADA, t[0]["fecha"])
    c.igual(recalculado, del_import,
            "el recalculo da lo MISMO que la importacion (3 huespedes + guia)")
    c.igual(recalculado, 4, "y son 4")

    # Sin nadie no hay salida, y sin salida no hay guia: cero es cero.
    conn.execute("DELETE FROM tour_asignado")
    c.igual(tours_pax.pax_sinac_pendiente(conn, TOUR_CON_ENTRADA, t[0]["fecha"]), 0,
            "si no va nadie el total es cero, no uno")
    conn.close()


def un_tour_sin_entrada_no_inventa_una(c):
    conn = comun.base_limpia()
    cargar([_reserva_con_tours(adl=2, tour=TOUR_SIN_ENTRADA)])
    t = _tours(conn)
    res = tours_pax.cambiar_pax(conn, t[0]["id"], "1")
    conn.commit()
    c.igual(res["sinac"], None, "el manglar no lleva entrada al parque")
    c.igual(conn.execute("SELECT COUNT(*) n FROM entrada_sinac").fetchone()["n"], 0,
            "y no se creo ninguna")
    conn.close()


# ---------------------------------------------------------------------------
# El cableado. Es por donde se rompio la vez anterior: la regla estaba bien y el dato
# no llegaba a la pantalla.
# ---------------------------------------------------------------------------

def el_dato_llega_hasta_la_pantalla(c):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()

    i = servidor.find('entry = {"id": r["id"]')
    c.cierto(i > 0, "se encuentra el armado de cada tour de la agenda")
    bloque = servidor[i:i + 1200]
    c.cierto('"pax": r["pax"]' in bloque,
             "la agenda manda el pax DE CADA TOUR, no solo el de la reserva")
    c.cierto('"pax_habitacion"' in bloque,
             "y cuantos hay en la habitacion, que es el tope del campo")
    c.cierto("r.adl, r.chl" in servidor,
             "para lo cual la consulta tiene que traer adl y chl")
    c.cierto("/api/tours/agenda/{tour_id}/pax" in servidor, "existe el endpoint")

    c.cierto("function celdaPaxTour" in pantalla, "la pantalla dibuja la celda del pax")
    c.cierto("cambiarPaxTour" in pantalla, "y la guarda")
    c.cierto("t.pax" in pantalla, "leyendo el pax del TOUR")
    # La celda del pax ya no puede ir con rowspan: era lo que la ataba a la reserva, y
    # por eso no habia donde ver ni corregir la diferencia entre un tour y otro.
    i = pantalla.find("<th>Fecha del tour</th>")
    c.cierto(i > 0, "se encuentra la tabla de la agenda")
    fila = pantalla[i:i + 4000]
    c.cierto("celdaPaxTour" in fila, "la celda del pax esta en esa tabla")
    c.igual('rowspan="${r.tours.length}">${r.pax}' in fila, False,
            "y ya NO repite el pax de la reserva con rowspan")


PRUEBAS = [
    por_defecto_va_la_habitacion_entera,
    cada_tour_lleva_su_propio_pax,
    se_puede_anotar_que_solo_va_uno,
    vaciar_el_campo_vuelve_a_la_habitacion,
    no_pueden_ir_mas_de_los_que_hay_en_la_habitacion,
    cero_no_es_la_forma_de_quitar_un_tour,
    un_tour_que_ya_no_existe_no_revienta,
    el_pax_escrito_a_mano_sobrevive_a_la_importacion,
    el_pax_que_nadie_toco_si_se_actualiza,
    el_pax_a_mano_se_mueve_con_el_tour_si_cambia_de_dia,
    si_baja_la_gente_de_la_habitacion_el_pax_a_mano_se_recorta,
    la_entrada_del_parque_se_recalcula,
    el_guia_cuenta_igual_en_las_cuatro_vias,
    un_tour_sin_entrada_no_inventa_una,
    el_dato_llega_hasta_la_pantalla,
]


if __name__ == "__main__":
    sys.exit(comun.correr("pax por tour", PRUEBAS))
