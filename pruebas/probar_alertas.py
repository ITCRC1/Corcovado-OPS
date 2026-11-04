"""Fija a qué día pertenece cada aviso del dashboard.

POR QUE ESTA SUITE. El dashboard es una pantalla de UN día, y los avisos eran lo único
que no lo respetaba: salían todos los abiertos, de cualquier fecha, incluidas las ya
pasadas. El lodge lo pidió —«eliminar las alertas con fechas vencidas y solo mostrar
las alertas que el usuario filtre por fechas o aparezca por defecto»— y medido sobre la
base real la pantalla del 4 de noviembre pasó de 20 avisos a 4: los 16 que sobraban
eran de otros días y salían IGUAL todos los días.

LO QUE SE PUEDE ROMPER SIN QUE NADIE SE ENTERE. Acotar por fecha es esconder cosas, y
esconder de más no da error: da una pantalla tranquila con un aviso dentro que nadie
leyó. Por eso lo que esta suite vigila de verdad son los bordes:

  · que un aviso SIN fecha no se filtre nunca —si se filtrara, desaparecería para
    siempre, porque no hay ningún día al que ir a buscarlo—;
  · que el aviso de una reserva dure hasta el día de SALIDA incluido, que es el día en
    que la alergia del que se va sigue importando porque desayuna aquí;
  · que el aviso de cancelación no se esconda a sí mismo. Es el caso bonito: habla de
    una reserva cancelada, y la regla «lo de una cancelada no se enseña» lo borraría
    justo a él, que es el que avisa de la cancelación.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                      # noqa: E402

import alertas as A                               # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOY = datetime.date.today()


def _dia(n):
    return (HOY + datetime.timedelta(days=n)).isoformat()


def _pms(iso):
    """ISO -> el 'DD-MM-YY' que guarda el PMS."""
    y, m, d = iso.split("-")
    return f"{d}-{m}-{y[2:]}"


def _reserva(conn, conf_no, llega, sale, estado="POR INGRESAR", room="12"):
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES (?,?,?,?,?,2,0,1,?)""",
        (conf_no, room, f"Huesped {conf_no}", _pms(llega), _pms(sale), estado))
    conn.commit()
    return conf_no


def _aviso(conn, tipo, mensaje, referencia_id=None, referencia_texto=None):
    cur = conn.execute(
        "INSERT INTO alerta (tipo, referencia_id, referencia_texto, mensaje) VALUES (?,?,?,?)",
        (tipo, referencia_id, referencia_texto, mensaje))
    conn.commit()
    return cur.lastrowid


def _abiertos(conn):
    return conn.execute("""SELECT id, tipo, mensaje, referencia_id, referencia_texto
                           FROM alerta WHERE resuelto = 0""").fetchall()


def _ids(filas):
    return {f["id"] for f in filas}


# ---------------------------------------------------------------------------
# De dónde sale la fecha
# ---------------------------------------------------------------------------

def un_aviso_de_tour_es_del_dia_de_su_tour(c):
    """La fuente más firme: una fecha guardada en tour_asignado, no deducida de un texto."""
    conn = comun.base_limpia()
    _reserva(conn, "900001", _dia(1), _dia(5))
    cur = conn.execute(
        """INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax, grupo_operativo)
           VALUES ('900001', ?, 'SNORKEL', 10, 'A')""", (_dia(3),))
    conn.commit()
    tour = cur.lastrowid
    aviso = _aviso(conn, "CAPACIDAD_GUIA",
                   f"SNORKEL el {_dia(3)} tiene 10 pax, pero el maximo por guia es 8.",
                   referencia_id=tour)

    for n, sale in ((2, False), (3, True), (4, False)):
        dia, _sin, _otros = A.repartir(conn, _abiertos(conn), _dia(n), hoy=HOY.isoformat())
        c.igual(aviso in _ids(dia), sale,
                f"el aviso del tour {'sale' if sale else 'no sale'} el dia {n:+d}")
    conn.close()


def un_aviso_de_reserva_dura_toda_la_estadia(c):
    """Y el dia de SALIDA incluido.

    Es a proposito distinto de la regla de «en casa», que excluye al que se va porque
    cuenta cabezas: a quien hay que dar de comer y donde dormir. Un aviso no es una
    cabeza. La alerta de Opera del trasplantado de corazon —higiene y seguridad
    alimentaria— desaparecia la manana en que desayunaba aqui por ultima vez. Medido
    sobre la base real, el acotado viejo perdia asi cuatro avisos el 8 de noviembre.
    """
    conn = comun.base_limpia()
    _reserva(conn, "900002", _dia(2), _dia(5))
    aviso = _aviso(conn, "ALERTA_OPERA",
                   "Hab. 12 (llega manana): dieta sin gluten.",
                   referencia_texto="900002")

    visible = []
    for n in range(0, 8):
        dia, _sin, _otros = A.repartir(conn, _abiertos(conn), _dia(n), hoy=HOY.isoformat())
        if aviso in _ids(dia):
            visible.append(n)
    c.igual(visible, [2, 3, 4, 5], "sale desde la llegada hasta la salida, incluida")
    conn.close()


def la_fecha_sale_del_texto_cuando_no_hay_a_quien_apuntar(c):
    """El ultimo recurso. Varios avisos no apuntan a nada: la unica fecha que tienen es
    la que alguien escribio en la frase, y se escribe de las dos formas de la casa."""
    conn = comun.base_limpia()
    iso = _aviso(conn, "CUARTO_DOBLE",
                 f"La habitacion 12 tiene DOS reservas la noche del {_dia(4)}.")
    pms = _aviso(conn, "TRANSPORTE_SIN_CONFIRMAR",
                 f"Confirmar punto de entrada de Perez (hab. 12, {_pms(_dia(6))}): "
                 f"el PDF dice \"muelle\" - no indica Sierpe ni Drake.")

    por_id = {a["id"]: a for a in A.con_fecha(conn, _abiertos(conn))}
    c.igual(por_id[iso]["desde"], _dia(4), "lee la fecha escrita en ISO")
    c.igual(por_id[pms]["desde"], _dia(6), "y la escrita como la guarda el PMS")

    dia, _sin, _otros = A.repartir(conn, _abiertos(conn), _dia(4), hoy=HOY.isoformat())
    c.igual(_ids(dia), {iso}, "cada uno sale en el dia que dice su texto")
    conn.close()


def un_aviso_de_amenidad_hereda_la_estadia_de_su_reserva(c):
    """La alergia no alimentaria apunta a la fila de amenidad, no a la reserva: hay que
    dar el salto de una a otra o el aviso se queda sin fecha."""
    conn = comun.base_limpia()
    _reserva(conn, "900003", _dia(10), _dia(13))
    cur = conn.execute(
        """INSERT INTO amenidad_tarea (conf_no, amenidad, tarea, area_responsable, origen)
           VALUES ('900003', 'Down Feather Allergy', 'Cambiar almohadas', 'HOUSEKEEPING', 'OPERA')""")
    conn.commit()
    aviso = _aviso(conn, "ALERGIA_NO_ALIMENTARIA",
                   "Alergia NO alimentaria en la hab. 12: revisar almohadas.",
                   referencia_id=cur.lastrowid)

    por_id = {a["id"]: a for a in A.con_fecha(conn, _abiertos(conn))}
    c.igual((por_id[aviso]["desde"], por_id[aviso]["hasta"]), (_dia(10), _dia(13)),
            "la amenidad lleva a su reserva y la reserva pone las fechas")
    conn.close()


# ---------------------------------------------------------------------------
# Lo que se esconde y lo que NO
# ---------------------------------------------------------------------------

def un_aviso_vencido_no_sale_en_la_pantalla_de_hoy(c):
    """La mitad que se pidio: lo de ayer no se cuela en la pantalla de hoy."""
    conn = comun.base_limpia()
    _reserva(conn, "900004", _dia(-9), _dia(-4))
    vencido = _aviso(conn, "ALERTA_OPERA", "Hab. 12: dieta sin gluten.",
                     referencia_texto="900004")
    _reserva(conn, "900005", _dia(0), _dia(3))
    de_hoy = _aviso(conn, "ALERTA_OPERA", "Hab. 14: alergia al mani.",
                    referencia_texto="900005")

    dia, sin_f, otros = A.repartir(conn, _abiertos(conn), HOY.isoformat(), hoy=HOY.isoformat())
    c.igual(_ids(dia), {de_hoy}, "solo queda el aviso del dia")
    c.igual(sin_f, [], "y ninguno sin fecha")
    c.igual(otros, 0, "el vencido tampoco se cuenta entre los de otras fechas")
    c.cierto(vencido not in _ids(dia), "el vencido no esta")
    conn.close()


def un_dia_pasado_se_puede_ir_a_ver_a_proposito(c):
    """«Vencido» quiere decir que se cuela sin que nadie lo pida, no que no se pueda ir
    a buscar. Si alguien navega al dia de ayer, ve los avisos de ayer, igual que ve sus
    entradas y sus tours."""
    conn = comun.base_limpia()
    _reserva(conn, "900006", _dia(-9), _dia(-4))
    viejo = _aviso(conn, "ALERTA_OPERA", "Hab. 12: dieta sin gluten.",
                   referencia_texto="900006")

    dia, _sin, _otros = A.repartir(conn, _abiertos(conn), _dia(-6), hoy=HOY.isoformat())
    c.igual(_ids(dia), {viejo}, "en su propio dia si se ve")
    conn.close()


def un_aviso_sin_fecha_sale_siempre(c):
    """Y es lo que impide que esto se convierta en una perdida.

    Un paquete que Opera trae y el sistema no sabe que es no pertenece a ningun dia.
    Filtrarlo por dia lo haria desaparecer de todas las pantallas a la vez, sin error y
    sin sitio donde ir a buscarlo: trabajo pendiente borrado en silencio.
    """
    conn = comun.base_limpia()
    suelto = _aviso(conn, "PAQUETE_SIN_MAPEAR",
                    "Opera trae el paquete SPAP y el sistema no sabe que es.")

    for n in (-30, 0, 1, 60):
        dia, sin_f, _otros = A.repartir(conn, _abiertos(conn), _dia(n), hoy=HOY.isoformat())
        c.igual(_ids(sin_f), {suelto}, f"sale tambien el dia {n:+d}")
        c.igual(dia, [], "y no se cuela entre los del dia, que es otra cosa")
    conn.close()


def un_aviso_de_una_reserva_cancelada_no_sale(c):
    """La cancelada no esta en ningun modulo, y un aviso sobre quien no viene es
    exactamente la confusion que se pidio quitar."""
    conn = comun.base_limpia()
    _reserva(conn, "900007", _dia(1), _dia(4), estado="CANCELADA")
    _aviso(conn, "ALERTA_OPERA", "Hab. 12: dieta sin gluten.", referencia_texto="900007")

    for n in (0, 1, 2, 3, 4):
        dia, sin_f, otros = A.repartir(conn, _abiertos(conn), _dia(n), hoy=HOY.isoformat())
        c.igual((len(dia), len(sin_f), otros), (0, 0, 0),
                f"no sale el dia {n:+d}, ni como del dia ni como sin fecha")
    conn.close()


def el_aviso_de_cancelacion_no_se_esconde_a_si_mismo(c):
    """EL CASO QUE SE MUERDE LA COLA. El aviso de que una reserva se cancelo habla, por
    definicion, de una reserva cancelada. Si la regla de arriba lo alcanzara, borraria
    justo al mensajero: nadie se enteraria de la cancelacion.

    No lo alcanza porque ese texto escribe «conf 900008», no «reserva 900008», y el
    reconocedor pide la palabra. Se comprueba con el texto REAL, el que produce
    loader._aviso_de_cancelacion, para que cambiarlo rompa esta prueba y no la
    operacion.
    """
    conn = comun.base_limpia()
    import loader
    _reserva(conn, "900008", _dia(3), _dia(6), estado="CANCELADA")
    mensaje = loader._aviso_de_cancelacion("Perez/Juan", "12", _pms(_dia(3)), "900008")
    aviso = _aviso(conn, "RESERVA_CANCELADA", mensaje)

    por_id = {a["id"]: a for a in A.con_fecha(conn, _abiertos(conn))}
    c.cierto(not por_id[aviso]["cancelada"], "no se toma por el aviso de una cancelada")
    c.igual(por_id[aviso]["desde"], _dia(3), "se fecha el dia en que habria llegado")

    dia, _sin, _otros = A.repartir(conn, _abiertos(conn), _dia(3), hoy=HOY.isoformat())
    c.igual(_ids(dia), {aviso}, "y se ve")
    conn.close()


def se_cuentan_los_de_otras_fechas_para_no_perderlos_de_vista(c):
    """Un numero, no la lista. La lista larga es lo que se vino a quitar; el numero es
    lo que evita que alguien de por hecho que no hay nada pendiente."""
    conn = comun.base_limpia()
    _reserva(conn, "900009", _dia(0), _dia(1))
    hoy_ = _aviso(conn, "ALERTA_OPERA", "Hab. 12: hoy.", referencia_texto="900009")
    _reserva(conn, "900010", _dia(8), _dia(9))
    _aviso(conn, "ALERTA_OPERA", "Hab. 14: la semana que viene.", referencia_texto="900010")
    _reserva(conn, "900011", _dia(-8), _dia(-7))
    _aviso(conn, "ALERTA_OPERA", "Hab. 16: el mes pasado.", referencia_texto="900011")

    dia, _sin, otros = A.repartir(conn, _abiertos(conn), HOY.isoformat(), hoy=HOY.isoformat())
    c.igual(_ids(dia), {hoy_}, "se ve el de hoy")
    c.igual(otros, 1, "se cuenta el que viene, no el que paso")
    conn.close()


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------

def _cuerpo(nombre):
    with open(os.path.join(RAIZ, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    i = html.find(f"function {nombre}(")
    if i < 0:
        return ""
    siguientes = [x for x in (html.find("\nfunction ", i + 20),
                              html.find("\nasync function ", i + 20)) if x > i]
    trozo = html[i:min(siguientes)] if siguientes else html[i:i + 9000]
    return "\n".join(r for r in trozo.split("\n") if not r.lstrip().startswith("//"))


def el_dashboard_separa_los_que_no_tienen_fecha(c):
    """Mezclados con los del dia pareceria que son de hoy, y nadie los resolveria."""
    cuerpo = _cuerpo("mostrarListaDash")
    c.cierto("a.desde" in cuerpo, "la pantalla mira la fecha que trae cada aviso")
    c.cierto("Sin fecha" in cuerpo, "y rotula aparte los que no la tienen")
    c.cierto("alertas_otros_dias" in cuerpo, "y dice cuantos quedan en otras fechas")
    c.cierto("escaparHTML(a.mensaje)" in cuerpo,
             "el texto del aviso viene de Opera, asi que se escapa")


def main():
    return comun.correr("Alertas del dashboard", [
        un_aviso_de_tour_es_del_dia_de_su_tour,
        un_aviso_de_reserva_dura_toda_la_estadia,
        la_fecha_sale_del_texto_cuando_no_hay_a_quien_apuntar,
        un_aviso_de_amenidad_hereda_la_estadia_de_su_reserva,
        un_aviso_vencido_no_sale_en_la_pantalla_de_hoy,
        un_dia_pasado_se_puede_ir_a_ver_a_proposito,
        un_aviso_sin_fecha_sale_siempre,
        un_aviso_de_una_reserva_cancelada_no_sale,
        el_aviso_de_cancelacion_no_se_esconde_a_si_mismo,
        se_cuentan_los_de_otras_fechas_para_no_perderlos_de_vista,
        el_dashboard_separa_los_que_no_tienen_fecha,
    ])


if __name__ == "__main__":
    sys.exit(main())
