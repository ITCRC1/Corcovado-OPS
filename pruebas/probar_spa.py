"""Fija lo que se puede cambiar de una cita de spa SIN cancelarla.

POR QUE ESTA SUITE. Lo pidio el lodge: «editar el tipo de masaje en caso que el cliente
quiera cambiarlo y no cancelar del todo la reserva del masaje». Hasta ahora la unica
salida era cancelar y volver a crear, y eso perdia dos cosas que no se recuperan:

  · LA FICHA MEDICA, que es un consentimiento para ESA cita: condiciones, cirugias,
    alergias, embarazo. Volver a pedirsela al huesped en recepcion no siempre pasa, y
    una cita sin ficha es una terapeuta trabajando a ciegas.
  · EL SITIO EN LA AGENDA. En temporada alta el hueco se lo lleva otro.

Y lo que esta suite fija de verdad es LA DURACION. Los minutos se copian del catalogo
al crear la cita, asi que cambiar el tratamiento sin recalcularlos deja un masaje de 90
minutos ocupando el hueco de 40: la agenda dice que cabe, el aviso de choque NO salta
—porque mira los minutos viejos— y el spa lo descubre con la huesped en la camilla.
Ese fallo no da error: da una agenda que miente.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402

import spa as _spa                               # noqa: E402

HOY = datetime.date.today()


def _cita(conn, servicio="JUNGLE", hora="10:00", estado="CONFIRMADA"):
    """Una cita con ficha medica, como las que crea el huesped desde su enlace."""
    minutos = conn.execute(
        "SELECT minutos FROM spa_servicio WHERE codigo = ?", (servicio,)).fetchone()[0]
    cur = conn.execute(
        """INSERT INTO spa_cita (conf_no, room_no, nombre_huesped, servicio_codigo,
                                 fecha, hora, minutos, terapeuta, estado, origen,
                                 condicion_medica, alergias, cirugia_reciente)
           VALUES (NULL, '12', 'Prueba/Ana', ?, ?, ?, ?, NULL, ?, 'HUESPED',
                   'hipertension', 'ninguna', 0)""",
        (servicio, HOY.isoformat(), hora, minutos, estado))
    conn.commit()
    return cur.lastrowid


def cambiar_el_tratamiento_recalcula_la_duracion(c):
    """LA MITAD QUE IMPORTA. JUNGLE dura 40 y DEEP 90: si los minutos se quedaran en 40,
    la agenda diria que cabe donde no cabe."""
    conn = comun.base_limpia()
    cita = _cita(conn, "JUNGLE")
    antes = dict(conn.execute("SELECT * FROM spa_cita WHERE id = ?", (cita,)).fetchone())
    c.igual(antes["minutos"], 40, "arranca con los 40 minutos del Jungle Bliss")

    codigo, minutos = _spa.cambiar_tratamiento(conn, cita, "DEEP")
    conn.commit()
    c.igual(codigo, "DEEP", "queda el tratamiento nuevo")
    c.igual(minutos, 90, "y la duracion del nuevo, no la vieja")

    guardada = dict(conn.execute("SELECT * FROM spa_cita WHERE id = ?", (cita,)).fetchone())
    c.igual(guardada["servicio_codigo"], "DEEP", "se guardo el tratamiento")
    c.igual(guardada["minutos"], 90, "y se guardaron los minutos")
    conn.close()


def cambiar_el_tratamiento_no_cancela_ni_pierde_la_ficha(c):
    """Lo que el lodge pidio evitar. La ficha medica es un consentimiento de esta cita:
    si se perdiera, la terapeuta trabajaria sin saber que la huesped es hipertensa."""
    conn = comun.base_limpia()
    cita = _cita(conn, "JUNGLE", hora="10:00", estado="CONFIRMADA")
    _spa.cambiar_tratamiento(conn, cita, "OCEAN")
    conn.commit()

    d = dict(conn.execute("SELECT * FROM spa_cita WHERE id = ?", (cita,)).fetchone())
    c.igual(d["estado"], "CONFIRMADA", "la cita sigue confirmada, no se cancela")
    c.igual(d["hora"], "10:00", "y conserva su hueco en la agenda")
    c.igual(d["condicion_medica"], "hipertension", "la ficha medica sigue ahi")
    c.igual(d["alergias"], "ninguna", "con sus alergias")
    c.igual(d["room_no"], "12", "y la habitacion")
    # Y sigue siendo UNA cita: no se duplico.
    c.igual(conn.execute("SELECT COUNT(*) FROM spa_cita").fetchone()[0], 1,
            "sigue habiendo una sola cita")
    conn.close()


def un_tratamiento_que_no_existe_se_rechaza(c):
    """Mejor un error que una cita con un tratamiento inventado: la terapeuta se
    presentaria sin saber que va a hacer."""
    conn = comun.base_limpia()
    cita = _cita(conn, "JUNGLE")
    for codigo in ("NOEXISTE", "masaje relajante"):
        try:
            _spa.cambiar_tratamiento(conn, cita, codigo)
            c.cierto(False, f"deberia rechazar «{codigo}»")
        except _spa.TratamientoInvalido:
            c.cierto(True, f"rechaza «{codigo}»")

    # Uno retirado del catalogo tampoco se puede poner de nuevo.
    conn.execute("UPDATE spa_servicio SET activo = 0 WHERE codigo = 'OCEAN'")
    conn.commit()
    try:
        _spa.cambiar_tratamiento(conn, cita, "OCEAN")
        c.cierto(False, "deberia rechazar uno dado de baja")
    except _spa.TratamientoInvalido:
        c.cierto(True, "rechaza un tratamiento dado de baja")

    # Y la cita no se toco en ninguno de los intentos.
    d = dict(conn.execute("SELECT * FROM spa_cita WHERE id = ?", (cita,)).fetchone())
    c.igual(d["servicio_codigo"], "JUNGLE", "la cita se queda como estaba")
    c.igual(d["minutos"], 40, "con su duracion")
    conn.close()


def sin_cambio_no_pasa_nada(c):
    """Mandar el mismo tratamiento, o ninguno, no es un error: la pantalla manda el
    valor del selector cada vez que se toca cualquier cosa de la fila."""
    conn = comun.base_limpia()
    cita = _cita(conn, "FLORA")
    for valor in (None, "", "FLORA"):
        codigo, minutos = _spa.cambiar_tratamiento(conn, cita, valor)
        c.igual(codigo, "FLORA", f"con {valor!r} se queda igual")
        c.igual(minutos, 60, "y la duracion no cambia")
    conn.close()


def sin_duracion_en_el_catalogo_se_conserva_la_que_tenia(c):
    """Dejar los minutos en blanco haria INVISIBLE el choque, que es peor que una
    duracion aproximada: una cita sin duracion no se solapa nunca con nada.

    Se prueba con CERO y no con NULL porque la columna es NOT NULL — un cero es la
    unica forma de que el catalogo no diga cuanto dura, y recorre la misma rama."""
    conn = comun.base_limpia()
    cita = _cita(conn, "JUNGLE")
    conn.execute("UPDATE spa_servicio SET minutos = 0 WHERE codigo = 'RAIN'")
    conn.commit()

    codigo, minutos = _spa.cambiar_tratamiento(conn, cita, "RAIN")
    c.igual(codigo, "RAIN", "el tratamiento cambia igual")
    c.igual(minutos, 40, "y se conserva la duracion que tenia, no queda en blanco")
    conn.close()


def el_choque_se_mira_con_la_duracion_NUEVA(c):
    """El fallo entero, de punta a punta. Dos citas que no chocaban con 40 minutos SI
    chocan con 90, y es justo lo que hay que ver ANTES de guardar."""
    conn = comun.base_limpia()
    cfg = _spa.cargar_config()
    terapeutas = [t[0] for t in conn.execute(
        "SELECT nombre FROM spa_terapeuta WHERE activo = 1")] or ["A"]

    cita = _cita(conn, "JUNGLE", hora="10:00")      # 10:00 - 10:40
    _cita(conn, "FLORA", hora="11:30")              # 11:30 - 12:30

    def citas_del_dia():
        return [dict(r) for r in conn.execute(
            "SELECT * FROM spa_cita WHERE estado != 'CANCELADA'")]

    # Con una sola terapeuta, 40 minutos a las 10:00 no estorban al de las 11:30.
    choques = _spa.revisar_choque(citas_del_dia(), "10:00", 40, terapeutas[:1], cfg,
                                  excluir_id=cita)
    c.igual(choques, [], "con 40 minutos no hay choque")

    # Al pasar a DEEP (90) la cita llega hasta las 11:30 y ya no cabe.
    _spa.cambiar_tratamiento(conn, cita, "DEEP")
    conn.commit()
    d = dict(conn.execute("SELECT * FROM spa_cita WHERE id = ?", (cita,)).fetchone())
    choques = _spa.revisar_choque(citas_del_dia(), d["hora"], d["minutos"],
                                  terapeutas[:1], cfg, excluir_id=cita)
    c.cierto(len(choques) > 0,
             "con 90 minutos SI se avisa del choque, que es lo que hay que ver")
    conn.close()


def la_pantalla_deja_cambiar_el_tratamiento(c):
    """Y que el selector este donde se lee la cita, no en otra pantalla."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    i = html.find("function filaCitaSpa(")
    c.cierto(i > 0, "existe la fila de la cita")
    bloque = html[i:i + 2600]
    c.cierto("moverCita(${c.id}, {servicio: this.value})" in bloque,
             "la fila deja cambiar el tratamiento")
    c.cierto("opcionesServicio(c)" in bloque, "con la lista del catalogo")

    j = html.find("function opcionesServicio(")
    c.cierto(j > 0, "existe la lista de tratamientos")
    opciones = html[j:html.find("function filaCitaSpa(", j)]
    # El que tiene puesto sale SIEMPRE, aunque ya no este activo: si no, una cita con un
    # tratamiento retirado mostraria otro distinto y bastaria tocar algo para cambiarlo
    # sin querer.
    c.cierto("hay || !actual" in opciones,
             "el tratamiento que ya tiene sale aunque este dado de baja")


PRUEBAS = [
    cambiar_el_tratamiento_recalcula_la_duracion,
    cambiar_el_tratamiento_no_cancela_ni_pierde_la_ficha,
    un_tratamiento_que_no_existe_se_rechaza,
    sin_cambio_no_pasa_nada,
    sin_duracion_en_el_catalogo_se_conserva_la_que_tenia,
    el_choque_se_mira_con_la_duracion_NUEVA,
    la_pantalla_deja_cambiar_el_tratamiento,
]


if __name__ == "__main__":
    sys.exit(comun.correr("spa", PRUEBAS))
