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
# Los precios — lo que el formulario de Google no calculaba
# ---------------------------------------------------------------------------

CON_PRECIO = {
    "TSHIRT": {"nombre": "T-shirt", "precio_centavos": 250},
    "SOCKS": {"nombre": "Pair of socks", "precio_centavos": 150},
    "DRESS": {"nombre": "Dress", "precio_centavos": None},
}


def el_precio_se_escribe_como_se_escribe(c):
    """Quien carga la lista teclea 2.50, 2,50 o $2.50. Rechazarle la coma seria hacerle
    perder el tiempo con algo que se entiende perfectamente."""
    limpiar()
    c.igual(hk.centavos_de("2.50"), 250, "con punto")
    c.igual(hk.centavos_de("2,50"), 250, "con coma")
    c.igual(hk.centavos_de("$2.50"), 250, "con el simbolo pegado")
    c.igual(hk.centavos_de(" 3 "), 300, "un entero con espacios")
    c.igual(hk.centavos_de(""), None, "vacio es 'sin precio', no cero")
    c.igual(hk.centavos_de(None), None, "y nada tambien")
    c.igual(hk.centavos_de("gratis"), False, "una palabra no es un precio")
    c.igual(hk.centavos_de("-5"), False, "ni un precio negativo")


def los_centavos_no_se_pierden_al_redondear(c):
    """int(2.99*100) da 298 porque 2.99 no es exacto en binario. Ese centavo perdido
    aparece en la cuenta de un huesped."""
    limpiar()
    c.igual(hk.centavos_de("2.99"), 299, "2.99 tienen que ser 299 centavos, no 298")
    c.igual(hk.centavos_de("8.29"), 829, "y 8.29 tienen que ser 829")


def el_total_es_precio_por_cantidad(c):
    limpiar()
    items, _ = hk.limpiar_items(
        [{"codigo": "TSHIRT", "cantidad": 3}, {"codigo": "SOCKS", "cantidad": 2}],
        CON_PRECIO)
    total, completo = hk.total_de(items)
    c.igual(total, 3 * 250 + 2 * 150, "tres camisetas y dos pares de medias")
    c.igual(completo, True, "y el total esta completo")
    c.igual(hk.formato_precio(total), "$10.50", "se muestra con dos decimales")


def sumar_muchas_veces_no_arrastra_decimales(c):
    """Doce veces 2.10 en coma flotante da 25.199999999999996. En centavos, 2520."""
    limpiar()
    prendas = {"X": {"nombre": "X", "precio_centavos": 210}}
    items, _ = hk.limpiar_items([{"codigo": "X", "cantidad": 12}], prendas)
    total, _ = hk.total_de(items)
    c.igual(total, 2520, "doce por 2.10 son 25.20 exactos")
    c.igual(hk.formato_precio(total), "$25.20", "y se imprimen asi")


def una_prenda_sin_precio_deja_el_total_incompleto(c):
    """Un total al que le falta una linea no es un total: decirlo igual le daria al
    huesped un numero que no va a coincidir con su cuenta."""
    limpiar()
    items, _ = hk.limpiar_items(
        [{"codigo": "TSHIRT", "cantidad": 2}, {"codigo": "DRESS", "cantidad": 1}],
        CON_PRECIO)
    total, completo = hk.total_de(items)
    c.igual(completo, False, "con una prenda sin precio, el total esta incompleto")
    c.igual(total, 500, "y lo que se pudo sumar sigue siendo correcto")


def el_precio_viaja_copiado_en_el_pedido(c):
    """Si housekeeping sube la lista el mes que viene, el pedido de la semana pasada
    tiene que seguir diciendo lo que se cotizo. Un huesped que ve un total en su telefono
    y otro en su cuenta no vuelve a confiar en ninguno de los dos."""
    limpiar()
    items, _ = hk.limpiar_items([{"codigo": "TSHIRT", "cantidad": 1}], CON_PRECIO)
    c.igual(items[0]["precio_centavos"], 250, "el precio va con la linea del pedido")


def el_precio_lo_pone_el_catalogo_y_no_el_formulario(c):
    """La pagina del huesped es publica: si el precio viajara en la peticion, cualquiera
    podria mandarse veinte camisas a cero."""
    limpiar()
    items, _ = hk.limpiar_items(
        [{"codigo": "TSHIRT", "cantidad": 20, "precio_centavos": 0}], CON_PRECIO)
    c.igual(items[0]["precio_centavos"], 250,
            "el precio que venga en la peticion se ignora")


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
    el_precio_se_escribe_como_se_escribe,
    los_centavos_no_se_pierden_al_redondear,
    el_total_es_precio_por_cantidad,
    sumar_muchas_veces_no_arrastra_decimales,
    una_prenda_sin_precio_deja_el_total_incompleto,
    el_precio_viaja_copiado_en_el_pedido,
    el_precio_lo_pone_el_catalogo_y_no_el_formulario,
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
