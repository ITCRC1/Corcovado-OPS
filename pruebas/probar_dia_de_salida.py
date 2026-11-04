"""Fija que el dia que el huesped SE VA solo caben los tours cortos de la manana.

POR QUE ESTA SUITE. Lo pidio el lodge mirando la previsualizacion de la hoja del dia:
«si la habitacion dice que sale, por alguna razon sigue cargando el tour que ya realizo
y no deberia ser asi». La regla que dieron es la de los tours cortos: vale el que
termina ANTES de que salga el bote, y nada mas.

EL CASO REAL que lo destapo, y que esta suite reconstruye: hab. 30, del 18 al 21 de
noviembre, con PAJAREO el 21. El itinerario lo pone a las 6:00 a. m. y el pajareo dura
dos horas — termina a las 8:00, que es exactamente cuando sale el bote de Sierpe
(equipaje 7:00, check-out 7:45). El huesped no llega. Y nada de eso daba error: el tour
salia en la hoja como cualquier otro y contaba para repartir guias.

LAS DOS FORMAS DE ROMPER ESTO, las dos calladas:

  · ESCONDER DE MAS. Un tour sin hora en el catalogo, o un huesped sin punto de salida,
    no se pueden juzgar. Si por las dudas se escondieran, la hoja saldria tranquila con
    un renglon menos y nadie lo echaria de menos. Se dejan a la vista y se avisa.
  · ESCONDER SIN DECIRLO. Si el tour descartado desapareciera en silencio, nadie iria a
    arreglar la reserva y seguiria mal puesta para siempre. Se cuenta en la hoja y se
    avisa en el dashboard.

Y de paso fija el emparejamiento por RESERVA. La hoja pegaba el tour a la fila por
numero de HABITACION, y el numero de habitacion se reutiliza: el dia que un cuarto
cambia de huesped —55 veces en los proximos cuatro meses— el tour del que LLEGA se
habria pintado en el renglon del que SE VA. Es la misma leccion que ya esta escrita para
las alergias de cocina.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Esta suite importa `main` para pasar por el resumen de verdad, y al importarlo se
# enciende el buzon de correo si hay llaves puestas en la maquina. Ninguna prueba sale
# a internet.
for _clave in [k for k in os.environ if k.startswith("BUZON_")]:
    os.environ.pop(_clave)

import comun                                      # noqa: E402

import hoja_dia                                   # noqa: E402
import validations as val                         # noqa: E402

HOY = datetime.date.today()


def _pms(fecha):
    return fecha.strftime("%d-%m-%y")


def _dia(n):
    return HOY + datetime.timedelta(days=n)


def _reserva(conn, conf_no, room, llega, sale, punto_salida="Sierpe",
             hora_vuelo_salida=None, nombre=None):
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status, punto_salida,
                                hora_vuelo_salida)
           VALUES (?,?,?,?,?,2,0,1,'POR INGRESAR',?,?)""",
        (conf_no, room, nombre or f"Huesped/{conf_no}", _pms(llega), _pms(sale),
         punto_salida, hora_vuelo_salida))
    conn.commit()
    return conf_no


def _tour(conn, conf_no, fecha, codigo, pax=2):
    cur = conn.execute(
        """INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax, grupo_operativo,
                                      origen)
           VALUES (?,?,?,?,'A','PDF')""", (conf_no, fecha.isoformat(), codigo, pax))
    conn.commit()
    return cur.lastrowid


def _resumen(fecha):
    import main
    return main._datos_del_resumen(fecha.isoformat())


# ---------------------------------------------------------------------------
# El reloj
# ---------------------------------------------------------------------------

def el_reloj_entiende_los_dos_formatos(c):
    """Hacen falta los dos: el catalogo de tours guarda 24 h y los horarios del dia de
    salida se escriben como se le imprimen al huesped."""
    conn = comun.base_limpia()
    casos = {
        "06:00": 360, "8:00 a.m.": 480, "8:00 am": 480, "17:45": 1065,
        "5:45 p.m.": 1065, "12:00 a.m.": 0, "12:30 p.m.": 750, "00:00": 0,
    }
    for texto, esperado in casos.items():
        c.igual(val.minutos_del_reloj(texto), esperado, f"«{texto}» son {esperado} min")
    for basura in ("", None, "nada", "25:00", "08:99", "ocho"):
        c.igual(val.minutos_del_reloj(basura), None, f"«{basura}» no es una hora")
    conn.close()


# ---------------------------------------------------------------------------
# La regla
# ---------------------------------------------------------------------------

def un_tour_que_no_llega_al_bote_no_va(c):
    """EL CASO DE LA HAB. 30. PAJAREO termina a las 08:00 y el bote de Sierpe sale a las
    8:00 a. m.: justo no llega."""
    conn = comun.base_limpia()
    sale = _dia(3)
    _reserva(conn, "700301", "30", _dia(0), sale, punto_salida="Sierpe")
    _tour(conn, "700301", sale, "PAJAREO")

    fuera = val.tours_del_dia_de_salida_que_no_caben(conn, sale.isoformat())
    c.igual(len(fuera), 1, "queda fuera")
    motivo = list(fuera.values())[0]
    c.cierto("PAJAREO" in motivo and "08:00" in motivo and "8:00 a.m." in motivo,
             "y el aviso dice las DOS horas, que es lo que hay que comparar")
    conn.close()


def un_tour_que_termina_antes_del_bote_si_va(c):
    """El MISMO tour, el MISMO dia, y esta vez si: por Drake con vuelo a las 2 de la
    tarde el bote sale a mediodia, y a las 08:00 el huesped ya volvio.

    Es la mitad que importa de la regla: no se descarta por caer el dia de salida, se
    descarta por no llegar. Sin esta prueba, «quitar todo lo del ultimo dia» pasaria
    igual y el lodge perderia los pajareos de verdad."""
    conn = comun.base_limpia()
    sale = _dia(3)
    _reserva(conn, "700302", "31", _dia(0), sale, punto_salida="Drake",
             hora_vuelo_salida="2:00 p.m.")
    _tour(conn, "700302", sale, "PAJAREO")

    c.igual(val.tours_del_dia_de_salida_que_no_caben(conn, sale.isoformat()), {},
            "no se descarta nada")
    conn.close()


def sin_datos_no_se_esconde_nada_pero_se_avisa(c):
    """La forma de fallar que nadie revisa seria esconder por falta de datos: la hoja
    sale tranquila y el renglon que faltaba no se echa de menos."""
    conn = comun.base_limpia()
    sale = _dia(3)
    # NGW no tiene horario en el catalogo: no se puede saber si llega al bote.
    _reserva(conn, "700303", "32", _dia(0), sale, punto_salida="Sierpe")
    _tour(conn, "700303", sale, "NGW")
    # Y este no tiene punto de salida: no se sabe a que hora se va.
    _reserva(conn, "700304", "33", _dia(0), sale, punto_salida=None)
    _tour(conn, "700304", sale, "PAJAREO")

    c.igual(val.tours_del_dia_de_salida_que_no_caben(conn, sale.isoformat()), {},
            "ninguno se esconde")

    avisos = [m for m in val.validar_todos_los_tours() if "Revisar con la agenda" in m]
    c.igual(len(avisos), 2, "pero los dos se avisan")
    c.cierto(any("no dice a qué hora termina" in m for m in avisos),
             "uno por el tour sin horario")
    c.cierto(any("no se sabe a qué hora sale" in m for m in avisos),
             "y otro por la salida sin punto")
    conn.close()


def un_tour_que_no_es_del_dia_de_salida_no_se_toca(c):
    """El Night Walk de la noche en que llega el huesped es lo normal en el lodge: cinco
    de los seis tours que tocan un borde son NW del dia de llegada."""
    conn = comun.base_limpia()
    llega, sale = _dia(0), _dia(3)
    _reserva(conn, "700305", "34", llega, sale, punto_salida="Sierpe")
    _tour(conn, "700305", llega, "NW")          # el dia que llega
    _tour(conn, "700305", _dia(1), "SIRENA")    # un dia de en medio

    c.igual(val.tours_del_dia_de_salida_que_no_caben(conn, llega.isoformat()), {},
            "el del dia de llegada se queda")
    c.igual(val.tours_del_dia_de_salida_que_no_caben(conn, _dia(1).isoformat()), {},
            "y el de en medio tambien")
    c.igual([m for m in val.validar_todos_los_tours() if "Revisar con la agenda" in m
             or "no le da tiempo" in m], [], "y no se avisa de nada")
    conn.close()


# ---------------------------------------------------------------------------
# El camino completo: resumen -> hoja del dia
# ---------------------------------------------------------------------------

def la_hoja_del_dia_no_le_pone_tour_a_quien_se_va(c):
    """De punta a punta, que es donde vivia el fallo: el resumen deja de contarlo y la
    fila SALE queda sin tour."""
    conn = comun.base_limpia()
    sale = _dia(3)
    _reserva(conn, "700306", "30", _dia(0), sale, punto_salida="Sierpe")
    _tour(conn, "700306", sale, "PAJAREO")
    # Y otra habitacion que NO se va ese dia, en el mismo tour: el tour sigue saliendo,
    # solo que sin el pax del que se marcha.
    _reserva(conn, "700307", "27", _dia(0), _dia(6), punto_salida="Sierpe")
    _tour(conn, "700307", sale, "PAJAREO")
    conn.close()

    resumen = _resumen(sale)
    pajareo = [t for t in resumen["tours"] if t["tour_codigo"] == "PAJAREO"]
    c.igual(len(pajareo), 1, "el tour sigue existiendo")
    c.igual(pajareo[0]["pax_total"], 2, "pero con el pax del que se queda, no los cuatro")
    c.igual(len(resumen["tours_fuera_por_salida"]), 1,
            "y lo descartado se devuelve, no se traga")

    conn = comun.conexion()
    d = hoja_dia.definicion(conn, sale.isoformat(), resumen)
    conn.close()
    por_hab = {str(f["hab"]): f for f in d["filas"]}
    c.igual(por_hab["30"]["estado"], "SALE", "la 30 se va")
    c.igual(por_hab["30"]["tour"], "", "y se va sin tour")
    c.igual(por_hab["27"]["tour"], "PAJAREO", "la 27 se queda y conserva el suyo")

    cuenta = dict((e, n) for e, n, _ in d["alertas"])
    c.igual(cuenta["Tours el día que se va"], 1,
            "la hoja dice cuantos quito: esconder sin decirlo es lo que impide arreglarlo")


def el_tour_se_pega_a_la_reserva_no_a_la_habitacion(c):
    """EL DIA QUE UN CUARTO CAMBIA DE HUESPED. Uno se va y otro llega al mismo numero de
    habitacion, y el que llega lleva tour.

    Emparejando por habitacion, la fila del que SE VA era la ultima que se quedaba con
    el cuarto: el tour del que LLEGA se pintaba en su renglon, y el que llega se quedaba
    sin el suyo. Las dos mitades mal, y ninguna da error.
    """
    conn = comun.base_limpia()
    hoy = _dia(0)
    _reserva(conn, "700308", "14", _dia(-3), hoy, punto_salida="Sierpe",
             nombre="SeVa/Pedro")
    _reserva(conn, "700309", "14", hoy, _dia(4), punto_salida="Sierpe",
             nombre="Llega/Marta")
    _tour(conn, "700309", hoy, "NW")           # el Night Walk del que LLEGA
    conn.close()

    resumen = _resumen(hoy)
    conn = comun.conexion()
    d = hoja_dia.definicion(conn, hoy.isoformat(), resumen)
    conn.close()

    por_conf = {f["conf_no"]: f for f in d["filas"]}
    c.igual(por_conf["700309"]["estado"], "ENTRA", "la reserva que llega")
    c.igual(por_conf["700309"]["tour"], "NW", "se queda con SU tour")
    c.igual(por_conf["700308"]["estado"], "SALE", "y la que se va")
    c.igual(por_conf["700308"]["tour"], "", "no hereda el del cuarto")


# ---------------------------------------------------------------------------
# El aviso
# ---------------------------------------------------------------------------

def el_aviso_sale_en_el_dashboard_el_dia_del_tour(c):
    """Se crea solo en cada carga —validar_todos_los_tours corre en cada sincronizacion y
    en cada importacion— asi que vale para las reservas que ya estan y para las que
    vengan. Y se fecha por su tour, no por el dia en que se escribio."""
    import alertas as A
    conn = comun.base_limpia()
    sale = _dia(3)
    _reserva(conn, "700310", "30", _dia(0), sale, punto_salida="Sierpe")
    _tour(conn, "700310", sale, "PAJAREO")

    val.validar_todos_los_tours()
    filas = conn.execute(
        """SELECT id, tipo, mensaje, referencia_id, referencia_texto FROM alerta
           WHERE resuelto = 0 AND tipo = 'TOUR_EL_DIA_QUE_SE_VA'""").fetchall()
    c.igual(len(filas), 1, "se creo el aviso")

    fechado = A.con_fecha(conn, filas)[0]
    c.igual((fechado["desde"], fechado["hasta"]), (sale.isoformat(), sale.isoformat()),
            "fechado el dia del tour")

    todas = conn.execute(
        "SELECT id, tipo, mensaje, referencia_id, referencia_texto FROM alerta "
        "WHERE resuelto = 0").fetchall()
    del_dia, _sin, _otros = A.repartir(conn, todas, sale.isoformat(),
                                       hoy=HOY.isoformat())
    c.cierto(any(a["tipo"] == "TOUR_EL_DIA_QUE_SE_VA" for a in del_dia),
             "y sale en el dashboard de ese dia")

    # Dos veces no son dos avisos: validar corre en cada carga.
    val.validar_todos_los_tours()
    c.igual(conn.execute("SELECT COUNT(*) FROM alerta WHERE tipo='TOUR_EL_DIA_QUE_SE_VA'"
                         ).fetchone()[0], 1, "y no se duplica en la siguiente carga")
    conn.close()


def main_():
    return comun.correr("Tours el dia de salida", [
        el_reloj_entiende_los_dos_formatos,
        un_tour_que_no_llega_al_bote_no_va,
        un_tour_que_termina_antes_del_bote_si_va,
        sin_datos_no_se_esconde_nada_pero_se_avisa,
        un_tour_que_no_es_del_dia_de_salida_no_se_toca,
        la_hoja_del_dia_no_le_pone_tour_a_quien_se_va,
        el_tour_se_pega_a_la_reserva_no_a_la_habitacion,
        el_aviso_sale_en_el_dashboard_el_dia_del_tour,
    ])


if __name__ == "__main__":
    sys.exit(main_())
