"""Fija las reglas de la lavandería: el plazo del mismo día, las cantidades y el enlace.

POR QUÉ ESTA SUITE. Housekeeping reemplaza un formulario de Google, y lo que justifica
el cambio no es la pantalla: son tres reglas que el formulario no podía tener.

  · Que al huésped se le DIGA si su ropa vuelve el mismo día. Era el reclamo del día
    siguiente: el formulario le preguntaba la hora de recolección y no le contestaba nada.
  · Que el enlace sepa quién es, y deje de servir cuando la reserva termina. El formulario
    le pedía nombre y habitación, y quien escribía 23 en vez de 32 no recibía su ropa.
  · Que lo que se recogió quede escrito aunque el catálogo cambie después.

Las tres son silenciosas si se rompen: nada da error, simplemente alguien se queda sin su
ropa o recibe la de otro. De ahí que estén fijadas aquí y no dependan de que alguien se
acuerde de probarlas.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402
from comun import base_limpia, cargar, conexion, reserva   # noqa: E402

import housekeeping as hk                        # noqa: E402

HOY = datetime.date.today()


def ddmmyy(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def limpiar():
    """Base nueva, sin dejar la conexión abierta.

    `base_limpia()` devuelve una conexión lista para usar, y en Windows dejarla abierta
    impide borrar el archivo en la prueba siguiente: salen diecisiete PermissionError que
    no tienen nada que ver con lo que se estaba probando.
    """
    base_limpia().close()


LLEGADA = ddmmyy(HOY)
SALIDA = ddmmyy(HOY + datetime.timedelta(days=4))


# ---------------------------------------------------------------------------
# El plazo del mismo día — lo que el formulario no podía contestar
# ---------------------------------------------------------------------------

def la_hora_tope_decide_si_la_ropa_vuelve_hoy(c):
    limpiar()
    cfg = dict(hk.CONFIG_POR_DEFECTO, hora_tope_mismo_dia="09:00")
    c.igual(hk.vuelve_mismo_dia("07:30", cfg), True,
            "recogida temprano tiene que volver el mismo dia")
    c.igual(hk.vuelve_mismo_dia("09:00", cfg), True,
            "justo a la hora tope todavia alcanza")
    c.igual(hk.vuelve_mismo_dia("09:30", cfg), False,
            "media hora tarde ya no alcanza")


def sin_hora_tope_el_hotel_no_promete_nada(c):
    """None y False son cosas distintas: 'vuelve mañana' es una promesa, 'no prometemos'
    es otra. La página no debe decir la primera cuando el hotel quiso decir la segunda."""
    limpiar()
    cfg = dict(hk.CONFIG_POR_DEFECTO, hora_tope_mismo_dia="")
    c.igual(hk.vuelve_mismo_dia("07:00", cfg), None,
            "sin hora tope no se promete plazo, ni a favor ni en contra")


def la_hora_tope_tiene_que_caer_dentro_del_horario(c):
    """Una tope fuera del horario o no la alcanza nadie o la alcanzan todos: en los dos
    casos el aviso deja de significar algo, y nadie se entera de que quedó inservible."""
    limpiar()
    fallo = None
    try:
        hk.guardar_config({"abre": "07:00", "cierra": "18:00",
                           "hora_tope_mismo_dia": "05:00"})
    except ValueError as e:
        fallo = str(e)
    c.cierto(fallo, "una hora tope antes de abrir tiene que rechazarse")


def las_horas_que_se_le_ofrecen_caen_dentro_del_horario(c):
    limpiar()
    cfg = dict(hk.CONFIG_POR_DEFECTO, abre="07:00", cierra="09:00", paso_minutos=30)
    horas = hk.horas_de_recoleccion(cfg)
    c.igual(horas, ["07:00", "07:30", "08:00", "08:30", "09:00"],
            "las horas ofrecidas son las del horario de recoleccion")


# ---------------------------------------------------------------------------
# Las cantidades — lo que la cuadrícula de 1 a 6 no dejaba decir
# ---------------------------------------------------------------------------

PRENDAS = {"TSHIRT": "T-shirt", "SOCKS": "Pair of socks", "DRESS": "Dress"}


def se_puede_pedir_mas_de_seis_de_una_prenda(c):
    """El 1-6 del formulario era un tope de Google Forms, no del hotel. Una familia de
    cuatro lo pasa con la ropa interior de dos dias."""
    limpiar()
    items, problema = hk.limpiar_items(
        [{"codigo": "SOCKS", "cantidad": 14}], PRENDAS)
    c.igual(problema, None, "catorce pares de medias tienen que poder pedirse")
    c.igual(items[0]["cantidad"], 14, "y guardarse tal cual")


def una_cantidad_absurda_se_frena(c):
    """No es una regla del hotel: ataja el dedazo de quien teclea 111 en vez de 11 y deja
    a housekeeping esperando un bulto que no existe."""
    limpiar()
    cfg = dict(hk.CONFIG_POR_DEFECTO, max_por_prenda=99)
    _, problema = hk.limpiar_items([{"codigo": "TSHIRT", "cantidad": 500}], PRENDAS, cfg)
    c.cierto(problema, "una cantidad sobre el tope tiene que rechazarse")
    c.cierto(problema and "99" in problema, "y el aviso tiene que decir cual es el tope")


def las_prendas_en_cero_no_entran(c):
    """El huésped toca + y luego − hasta dejarla en cero: eso es no mandarla, no mandar
    cero. Una fila en cero deja a housekeeping contando bultos que no existen."""
    limpiar()
    items, problema = hk.limpiar_items(
        [{"codigo": "TSHIRT", "cantidad": 0}, {"codigo": "SOCKS", "cantidad": 2}],
        PRENDAS)
    c.igual(problema, None, "que una prenda quede en cero no invalida el pedido")
    c.igual([i["codigo"] for i in items], ["SOCKS"], "solo entra lo que tiene cantidad")


def un_pedido_sin_ninguna_prenda_no_entra(c):
    limpiar()
    _, problema = hk.limpiar_items([], PRENDAS)
    c.cierto(problema, "un pedido vacio tiene que rechazarse")
    _, problema = hk.limpiar_items([{"codigo": "TSHIRT", "cantidad": 0}], PRENDAS)
    c.cierto(problema, "y uno con todo en cero tambien")


def una_prenda_que_no_existe_se_ignora(c):
    """Llega de una página pública: lo que no esté en el catálogo no se guarda."""
    limpiar()
    items, problema = hk.limpiar_items(
        [{"codigo": "INVENTADA", "cantidad": 3}, {"codigo": "DRESS", "cantidad": 1}],
        PRENDAS)
    c.igual(problema, None, "una prenda inventada no tumba el pedido")
    c.igual([i["codigo"] for i in items], ["DRESS"], "pero no entra")


def el_nombre_de_la_prenda_se_copia_al_pedido(c):
    """Si housekeeping renombra 'T-shirt' mañana, el pedido de hoy tiene que seguir
    diciendo qué se recogió: es el registro de lo que se entregó, no el catálogo de hoy."""
    limpiar()
    items, _ = hk.limpiar_items([{"codigo": "TSHIRT", "cantidad": 2}], PRENDAS)
    c.igual(items[0]["nombre"], "T-shirt", "el nombre viaja con el pedido, no la llave")


# ---------------------------------------------------------------------------
# Los estados — dos pasos más que el spa, a pedido del hotel
# ---------------------------------------------------------------------------

def el_pedido_avanza_por_su_camino(c):
    limpiar()
    c.igual(hk.siguiente_estado("SOLICITADO"), "CONFIRMADO", "de solicitado se confirma")
    c.igual(hk.siguiente_estado("CONFIRMADO"), "RECOGIDO", "y luego se recoge")
    c.igual(hk.siguiente_estado("RECOGIDO"), "ENTREGADO", "y luego se entrega")
    c.igual(hk.siguiente_estado("ENTREGADO"), None, "y ahi termina")


def se_puede_deshacer_un_paso_pero_no_volver_al_principio(c):
    """Housekeeping marca 'recogido' por error y lo deshace. Lo que no puede pasar por un
    toque de mas es saltar del final al principio y borrar las horas ya anotadas."""
    limpiar()
    ok, _ = hk.puede_pasar_a("RECOGIDO", "CONFIRMADO")
    c.cierto(ok, "volver un paso atras tiene que poder hacerse")
    ok, motivo = hk.puede_pasar_a("ENTREGADO", "SOLICITADO")
    c.igual(ok, False, "del final al principio no")
    c.cierto(motivo, "y con un motivo que se pueda leer")


def un_pedido_cancelado_no_revive(c):
    limpiar()
    ok, _ = hk.puede_pasar_a("CANCELADO", "CONFIRMADO")
    c.igual(ok, False, "un pedido cancelado no vuelve a la vida solo")
    ok, _ = hk.puede_pasar_a("RECOGIDO", "CANCELADO")
    c.cierto(ok, "pero cancelar tiene que poder hacerse en cualquier momento")


# ---------------------------------------------------------------------------
# El enlace del huésped
# ---------------------------------------------------------------------------

def el_enlace_es_el_mismo_cada_vez_que_se_pide(c):
    """Si cambiara, el que recepción ya mandó por WhatsApp dejaría de servir."""
    limpiar()
    cargar([reserva("900001", "12", LLEGADA, SALIDA)])
    conn = conexion()
    try:
        uno = hk.token_de_reserva(conn, "900001")
        otro = hk.token_de_reserva(conn, "900001")
        c.igual(uno, otro, "el enlace de una reserva no puede cambiar entre visitas")
        c.cierto(uno and len(uno) >= 8, "y tiene que ser dificil de adivinar")
    finally:
        conn.close()


def el_enlace_de_una_reserva_no_abre_la_de_otra(c):
    limpiar()
    cargar([reserva("900001", "12", LLEGADA, SALIDA),
            reserva("900002", "13", LLEGADA, SALIDA)])
    conn = conexion()
    try:
        token1 = hk.token_de_reserva(conn, "900001")
        c.igual(hk.reserva_de_token(conn, "900002", token1), None,
                "el codigo de una habitacion no puede abrir la de al lado")
        buena = hk.reserva_de_token(conn, "900001", token1)
        c.cierto(buena and buena["room_no"] == "12", "y el propio si abre la suya")
    finally:
        conn.close()


def un_codigo_inventado_no_abre_nada(c):
    limpiar()
    cargar([reserva("900001", "12", LLEGADA, SALIDA)])
    conn = conexion()
    try:
        hk.token_de_reserva(conn, "900001")
        c.igual(hk.reserva_de_token(conn, "900001", "inventado"), None,
                "un codigo que no coincide no abre la pagina")
        c.igual(hk.reserva_de_token(conn, "900001", ""), None,
                "y uno vacio tampoco")
    finally:
        conn.close()


def el_enlace_deja_de_servir_si_la_reserva_se_cancela(c):
    """Era la otra mitad del problema del formulario de Google: servía para siempre."""
    limpiar()
    cargar([reserva("900001", "12", LLEGADA, SALIDA)])
    conn = conexion()
    try:
        token = hk.token_de_reserva(conn, "900001")
        c.cierto(hk.reserva_de_token(conn, "900001", token), "mientras vive, abre")
        conn.execute("UPDATE reserva SET res_status = 'CANCELADA' WHERE conf_no = ?",
                     ("900001",))
        conn.commit()
        c.igual(hk.reserva_de_token(conn, "900001", token), None,
                "cancelada la reserva, el enlace deja de abrir")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# El catálogo de prendas
# ---------------------------------------------------------------------------

def el_catalogo_arranca_con_las_prendas_del_formulario(c):
    """Las ocho del formulario de Google, para no tener que escribirlas a mano."""
    limpiar()
    conn = conexion()
    try:
        filas = conn.execute(
            "SELECT codigo, nombre_en FROM hk_prenda WHERE activo = 1 ORDER BY orden"
        ).fetchall()
        nombres = [f["nombre_en"] for f in filas]
        c.igual(len(filas), 8, "tienen que sembrarse las ocho prendas del formulario")
        c.cierto("Long sleeve shirts" in nombres,
                 "y sin heredar la errata 'slevee' del original")
    finally:
        conn.close()


PRUEBAS = [
    la_hora_tope_decide_si_la_ropa_vuelve_hoy,
    sin_hora_tope_el_hotel_no_promete_nada,
    la_hora_tope_tiene_que_caer_dentro_del_horario,
    las_horas_que_se_le_ofrecen_caen_dentro_del_horario,
    se_puede_pedir_mas_de_seis_de_una_prenda,
    una_cantidad_absurda_se_frena,
    las_prendas_en_cero_no_entran,
    un_pedido_sin_ninguna_prenda_no_entra,
    una_prenda_que_no_existe_se_ignora,
    el_nombre_de_la_prenda_se_copia_al_pedido,
    el_pedido_avanza_por_su_camino,
    se_puede_deshacer_un_paso_pero_no_volver_al_principio,
    un_pedido_cancelado_no_revive,
    el_enlace_es_el_mismo_cada_vez_que_se_pide,
    el_enlace_de_una_reserva_no_abre_la_de_otra,
    un_codigo_inventado_no_abre_nada,
    el_enlace_deja_de_servir_si_la_reserva_se_cancela,
    el_catalogo_arranca_con_las_prendas_del_formulario,
]


if __name__ == "__main__":
    sys.exit(comun.correr("housekeeping", PRUEBAS))
