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
import contextlib
import datetime
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Dos pruebas importan `main` para pasar por el endpoint de verdad, y al importarlo se
# enciende el buzon de correo si hay llaves puestas en la maquina. Una prueba no sale a
# internet: se quitan antes de que nadie las lea.
for _clave in [k for k in os.environ if k.startswith("BUZON_")]:
    os.environ.pop(_clave)

import comun                                     # noqa: E402

import spa as _spa                               # noqa: E402

HOY = datetime.date.today()


def _pms(fecha):
    """date -> el 'DD-MM-YY' en que el PMS guarda las fechas."""
    return fecha.strftime("%d-%m-%y")


def _cita(conn, servicio="JUNGLE", hora="10:00", estado="CONFIRMADA",
          room_no="12", terapeuta=None):
    """Una cita con ficha medica, como las que crea el huesped desde su enlace."""
    minutos = conn.execute(
        "SELECT minutos FROM spa_servicio WHERE codigo = ?", (servicio,)).fetchone()[0]
    cur = conn.execute(
        """INSERT INTO spa_cita (conf_no, room_no, nombre_huesped, servicio_codigo,
                                 fecha, hora, minutos, terapeuta, estado, origen,
                                 condicion_medica, alergias, cirugia_reciente)
           VALUES (NULL, ?, 'Prueba/Ana', ?, ?, ?, ?, ?, ?, 'HUESPED',
                   'hipertension', 'ninguna', 0)""",
        (room_no, servicio, HOY.isoformat(), hora, minutos, terapeuta, estado))
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


def dos_citas_seguidas_de_la_misma_habitacion_no_chocan(c):
    """EL CASO QUE REPORTO EL LODGE, con sus numeros: la hab. 02 con «Soul and Body» de
    30' a las 15:45 y «Jungle Bliss» de 40' a las 16:15, las dos con Hellen. El sistema
    las marcaba como «2 citas que no caben como estan».

    «En casos asi si es posible que sea la misma terapista, porque si notas es la misma
    habitacion, misma persona, no habria conflicto».

    Y no lo hay: no se solapan ni un minuto —la primera termina exactamente cuando
    empieza la segunda—. Lo que saltaba era el espacio ENTRE citas, que son 30 minutos
    para limpiar la cabina y recibir al siguiente huesped. Aqui no hay siguiente huesped:
    es la misma gente en el mismo cuarto encadenando sus tratamientos.
    """
    conn = comun.base_limpia()
    cfg = _spa.cargar_config()
    primera = _cita(conn, "SOUL", hora="15:45", room_no="02", terapeuta="Hellen")
    segunda = _cita(conn, "JUNGLE", hora="16:15", room_no="02", terapeuta="Hellen")
    citas = [dict(r) for r in conn.execute("SELECT * FROM spa_cita")]
    conn.close()

    # Las dos direcciones: el aviso salia por duplicado, una vez desde cada cita.
    c.igual(_spa.revisar_choque(citas, "16:15", 40, ["Hellen"], cfg,
                                excluir_id=segunda, terapeuta="Hellen", room_no="02"),
            [], "la de las 16:15 cabe detras de la de las 15:45")
    c.igual(_spa.revisar_choque(citas, "15:45", 30, ["Hellen"], cfg,
                                excluir_id=primera, terapeuta="Hellen", room_no="02"),
            [], "y mirado desde la otra, tampoco choca")

    # Y con UNA sola terapeuta en todo el spa, por capacidad, tambien caben.
    c.igual(_spa.revisar_choque(citas, "16:15", 40, ["Hellen"], cfg,
                                excluir_id=segunda, room_no="02"),
            [], "sin terapeuta elegida, la capacidad tampoco las cuenta como dos a la vez")


def dos_citas_que_se_solapan_de_verdad_siguen_chocando(c):
    """LA OTRA MITAD, y es la que hace que el cambio se pueda aplicar sin romper nada:
    una terapeuta no puede estar en dos camillas a la vez, sea la misma habitacion o no.
    Lo que se quito es el espacio de limpieza entre citas seguidas, no la comprobacion
    de que no se monten una encima de otra.
    """
    conn = comun.base_limpia()
    cfg = _spa.cargar_config()
    _cita(conn, "RAIN", hora="15:45", room_no="02", terapeuta="Hellen")   # 60': hasta 16:45
    segunda = _cita(conn, "JUNGLE", hora="16:15", room_no="02", terapeuta="Hellen")
    citas = [dict(r) for r in conn.execute("SELECT * FROM spa_cita")]
    conn.close()

    avisos = _spa.revisar_choque(citas, "16:15", 40, ["Hellen"], cfg,
                                 excluir_id=segunda, terapeuta="Hellen", room_no="02")
    c.cierto(len(avisos) > 0,
             "a las 16:15 con la de las 15:45 corriendo hasta las 16:45 SI hay choque")
    c.cierto("15:45" in avisos[0], "y el aviso dice con cual")


def entre_habitaciones_distintas_el_espacio_sigue_valiendo(c):
    """Lo que no cambia: entre dos cuartos la terapeuta si necesita sus 30 minutos —hay
    que limpiar la cabina, cambiar sabanas y recibir a otro huesped—. Si esto se hubiera
    quitado de paso, el spa quedaria con una agenda imposible de cumplir.
    """
    conn = comun.base_limpia()
    cfg = _spa.cargar_config()
    _cita(conn, "SOUL", hora="15:45", room_no="02", terapeuta="Hellen")
    segunda = _cita(conn, "JUNGLE", hora="16:15", room_no="03", terapeuta="Hellen")
    citas = [dict(r) for r in conn.execute("SELECT * FROM spa_cita")]
    conn.close()

    avisos = _spa.revisar_choque(citas, "16:15", 40, ["Hellen"], cfg,
                                 excluir_id=segunda, terapeuta="Hellen", room_no="03")
    c.cierto(len(avisos) > 0, "de la 02 a la 03 sigue haciendo falta el espacio")
    c.cierto("hab. 02" in avisos[0], "y se dice de que habitacion es la otra cita")


def la_hora_que_se_le_ofrece_al_huesped_es_la_que_se_le_acepta(c):
    """Las dos puertas tienen que decir lo mismo. La lista de horas libres es TODO lo que
    el huesped ve en su enlace: si las 16:15 no aparecieran ahi, de nada valdria que el
    sistema las aceptara — nadie las pediria. Y al reves seria peor: ofrecerle una hora
    que al tocarla se rechaza.
    """
    conn = comun.base_limpia()
    cfg = _spa.cargar_config()
    _cita(conn, "SOUL", hora="15:45", room_no="02", terapeuta="Hellen")
    citas = [dict(r) for r in conn.execute("SELECT * FROM spa_cita")]
    conn.close()

    suyas = _spa.horas_libres(citas, 40, ["Hellen"], cfg, room_no="02")
    c.cierto("16:15" in suyas, "a la 02 se le ofrecen las 16:15, justo detras de la suya")
    ajenas = _spa.horas_libres(citas, 40, ["Hellen"], cfg, room_no="03")
    c.cierto("16:15" not in ajenas, "y a otra habitacion no, que ahi si hay que limpiar")

    # Y la terapeuta que se propone para la segunda es LA MISMA, que es lo que el lodge
    # hace y lo que el huesped espera.
    c.igual(_spa.terapeuta_sugerida(citas, "16:15", 40, ["Hellen", "Rocío"], cfg,
                                    room_no="02"),
            "Hellen", "la segunda cita del cuarto le cae a la misma terapeuta")


def la_agenda_del_spa_no_marca_las_dos_citas_del_mismo_cuarto(c):
    """EL CAMINO COMPLETO, por la pantalla de la foto.

    La regla vive en spa.revisar_choque, pero la AGENDA arma su propia llamada: si no le
    pasara la habitacion, el aviso seguiria encendido con la regla ya arreglada y
    probando solo la funcion esto daria verde. Es el error que mas se repite en este
    sistema —una regla arreglada en un sitio y otra pantalla que arma su propio SQL— asi
    que se comprueba por donde se ve.
    """
    import main
    conn = comun.base_limpia()
    _cita(conn, "SOUL", hora="15:45", room_no="02", terapeuta="Hellen")
    _cita(conn, "JUNGLE", hora="16:15", room_no="02", terapeuta="Hellen")
    conn.close()

    d = main.listar_citas_spa(fecha=HOY.isoformat(), user={"usuario": "pruebas"})
    marcadas = [x for x in d["citas"] if x.get("choques")]
    c.igual(marcadas, [], "la agenda no marca ninguna de las dos")

    # Y lo contrario: si de verdad se montan, la agenda SI lo marca.
    conn = comun.conexion()
    conn.execute("UPDATE spa_cita SET hora = '16:00' WHERE hora = '16:15'")
    conn.commit()
    conn.close()
    d = main.listar_citas_spa(fecha=HOY.isoformat(), user={"usuario": "pruebas"})
    c.cierto(any(x.get("choques") for x in d["citas"]),
             "con las citas montadas de verdad, el aviso sigue estando")


def el_enlace_del_huesped_deja_encadenar_la_segunda_cita(c):
    """La otra puerta, y la que mas pesa: al huesped su enlace le BLOQUEA la hora, no se
    la avisa. Con el espacio de limpieza aplicado a su propia cita anterior, pedir la
    segunda le daba un 409 —«esa hora ya se ocupo»— sobre una hora que estaba libre para
    el. Y antes de eso ni siquiera la veia: la lista de horas es todo lo que tiene.
    """
    import asyncio
    import main
    conn = comun.base_limpia()
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES ('910301','02','Smith/Ruth',?,?,2,0,1,'POR INGRESAR')""",
        (_pms(HOY), _pms(HOY + datetime.timedelta(days=3))))
    # Su primera cita, con la unica terapeuta que queda activa.
    conn.execute("UPDATE spa_terapeuta SET activo = 0 WHERE nombre != 'Hellen'")
    conn.execute(
        """INSERT INTO spa_cita (conf_no, room_no, nombre_huesped, servicio_codigo,
                                 fecha, hora, minutos, terapeuta, estado, origen)
           VALUES ('910301','02','Ruth Smith','SOUL',?, '15:45', 30, 'Hellen',
                   'CONFIRMADA','HUESPED')""", (HOY.isoformat(),))
    token = _spa.token_de_reserva(conn, "910301")
    conn.commit()
    conn.close()

    horas = main.spa_publico_horas("910301", token, HOY.isoformat(), "JUNGLE")
    c.cierto("16:15" in horas["horas"],
             "se le ofrecen las 16:15, justo cuando termina la suya")

    respuesta = asyncio.run(main.spa_publico_pedir("910301", token, {
        "servicio_codigo": "JUNGLE", "fecha": HOY.isoformat(), "hora": "16:15",
        "nombre_huesped": "Ruth Smith", "acepto_terminos": True}))
    c.igual(len(respuesta["mis_citas"]), 2, "y al pedirlas quedan sus dos citas")


def las_terapeutas_tienen_nombre(c):
    """El equipo del spa, con nombre y no «Terapeuta 1». Lo fue dando el lodge: primero
    Hellen y Rocio, despues Ivania y Xinia."""
    conn = comun.base_limpia()
    nombres = sorted(r[0] for r in conn.execute(
        "SELECT nombre FROM spa_terapeuta WHERE activo = 1"))
    c.igual(nombres, ["Hellen", "Ivania", "Rocío", "Xinia"],
            "las cuatro terapeutas del lodge")
    conn.close()


def agregar_una_terapeuta_sube_cuantas_citas_caben(c):
    """CUANTAS SON NO ES SOLO UNA LISTA. El aviso de choques cuenta las terapeutas
    ACTIVAS para saber cuantas citas caben a la misma hora: con dos, dos; con cuatro,
    cuatro.

    Por eso esta prueba no se conforma con contar nombres. Un nombre de mas en la
    siembra no da ningun error — abre un hueco a la misma hora que nadie puede atender,
    y eso se descubre con dos huespedes en la puerta del spa.
    """
    conn = comun.base_limpia()
    cfg = _spa.cargar_config()
    minutos = conn.execute(
        "SELECT minutos FROM spa_servicio WHERE codigo = 'JUNGLE'").fetchone()[0]

    def choca_con(cuantas_citas, cuantas_terapeutas):
        citas = [{"id": i, "hora": "10:00", "minutos": minutos, "estado": "CONFIRMADA"}
                 for i in range(cuantas_citas)]
        return bool(_spa.revisar_choque(
            citas, "10:00", minutos, ["T%d" % i for i in range(cuantas_terapeutas)], cfg))

    c.igual(choca_con(3, 4), False, "con cuatro terapeutas caben cuatro a las 10:00")
    c.igual(choca_con(4, 4), True, "la quinta ya choca")
    c.igual(choca_con(2, 2), True, "y con dos, la tercera chocaba igual que antes")

    # Y las apagadas NO cuentan: apagar a una tiene que cerrar un hueco, no dejarlo.
    conn.execute("UPDATE spa_terapeuta SET activo = 0 WHERE nombre = 'Xinia'")
    conn.commit()
    activas = [r[0] for r in conn.execute(
        "SELECT nombre FROM spa_terapeuta WHERE activo = 1 ORDER BY nombre")]
    c.igual(activas, ["Hellen", "Ivania", "Rocío"], "la apagada sale del reparto")
    conn.close()


def a_la_base_ya_instalada_le_entran_las_nuevas(c):
    """EL CAMINO DE PRODUCCION. La siembra es un INSERT OR IGNORE, asi que agregar un
    nombre a la lista alcanza: entran las que faltan y no se toca a las que ya estan.

    Lo que hay que comprobar de verdad es lo segundo: que a una terapeuta APAGADA desde
    el Catalogo no se le vuelva a encender el interruptor en el siguiente arranque. Eso
    no daria error — le devolveria citas a alguien que ya no trabaja ahi.
    """
    import init_db
    conn = comun.base_limpia()
    # Se simula la base instalada: solo las dos primeras, y una de ellas apagada.
    conn.execute("DELETE FROM spa_terapeuta")
    conn.executemany("INSERT INTO spa_terapeuta (nombre, activo) VALUES (?,?)",
                     [("Hellen", 1), ("Rocío", 0)])
    conn.commit()
    conn.close()

    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db(reset=False)

    conn = comun.conexion()
    estado = {r[0]: r[1] for r in conn.execute(
        "SELECT nombre, activo FROM spa_terapeuta")}
    c.igual(sorted(estado), ["Hellen", "Ivania", "Rocío", "Xinia"],
            "las nuevas entran en la base que ya existia")
    c.igual(estado["Rocío"], 0, "y la que estaba apagada sigue apagada")
    c.igual(estado["Ivania"], 1, "las nuevas entran encendidas")
    conn.close()


def renombrar_una_terapeuta_arrastra_sus_citas(c):
    """EL CAMINO DE PRODUCCION, y donde esto se habria roto en silencio.

    El nombre es la LLAVE de spa_terapeuta y spa_cita lo guarda como texto. Un UPDATE a
    secas dejaria las citas apuntando a una terapeuta que ya no existe: la agenda del
    spa las mostraria sin nadie asignado y el reparto de carga contaria una terapeuta
    de menos — sin ningun error de por medio."""
    import init_db
    conn = comun.base_limpia()
    # Se simula la base instalada: los nombres de fabrica, con citas asignadas.
    conn.execute("DELETE FROM spa_terapeuta")
    conn.executemany("INSERT INTO spa_terapeuta (nombre, activo) VALUES (?,1)",
                     [("Terapeuta 1",), ("Terapeuta 2",)])
    cita = _cita(conn, "JUNGLE")
    conn.execute("UPDATE spa_cita SET terapeuta = 'Terapeuta 1' WHERE id = ?", (cita,))
    conn.execute("DELETE FROM sistema_meta WHERE clave = ?", (init_db._MARCA_TERAPEUTAS,))
    conn.commit()

    init_db._poner_nombre_a_las_terapeutas(conn)

    nombres = sorted(r[0] for r in conn.execute("SELECT nombre FROM spa_terapeuta"))
    c.igual(nombres, ["Hellen", "Rocío"], "quedan con su nombre")
    c.igual(dict(conn.execute("SELECT terapeuta FROM spa_cita WHERE id = ?",
                              (cita,)).fetchone())["terapeuta"], "Hellen",
            "y la cita se fue con ella, no quedo huerfana")

    # Y lo que el lodge cambie a mano NO se le deshace al reiniciar.
    #
    # El cambio se hace con los TRES pasos —crear, mover las citas, borrar— porque es
    # lo que hace la pantalla y porque un UPDATE del nombre a secas lo rechaza la base:
    # el nombre es la llave y la cita la referencia. Esa es, justamente, la razon de ser
    # de la funcion que se esta probando.
    conn.execute("INSERT INTO spa_terapeuta (nombre, activo) VALUES ('Helen', 1)")
    conn.execute("UPDATE spa_cita SET terapeuta = 'Helen' WHERE terapeuta = 'Hellen'")
    conn.execute("DELETE FROM spa_terapeuta WHERE nombre = 'Hellen'")
    conn.execute("DELETE FROM sistema_meta WHERE clave = ?", (init_db._MARCA_TERAPEUTAS,))
    conn.commit()
    init_db._poner_nombre_a_las_terapeutas(conn)
    nombres = sorted(r[0] for r in conn.execute("SELECT nombre FROM spa_terapeuta"))
    c.igual(nombres, ["Helen", "Rocío"], "se respeta lo que cambiaron a mano")
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


# ---------------------------------------------------------------------------
# Quien recibe el tratamiento
# ---------------------------------------------------------------------------
# Lo pidio el lodge: «en algunas habitaciones hay 2 pax y no sabemos cual toma el
# masaje». La reserva trae un solo nombre —el titular— asi que en una doble la cita
# entraba a nombre del que no era. No daba error: llegaba completa, con su hora y su
# ficha medica, solo que de otra persona. La terapeuta se entera cuando ya esta delante.


def el_nombre_escrito_manda_sobre_el_titular(c):
    conn = comun.base_limpia()
    c.igual(_spa.nombre_de_la_cita("Ana Perez", "Perez/Juan"), "Ana Perez",
            "manda quien va a recibir el tratamiento")
    c.igual(_spa.nombre_de_la_cita("  Ana Perez  ", "Perez/Juan"), "Ana Perez",
            "sin los espacios de sobra")
    c.igual(_spa.nombre_de_la_cita("", "Perez/Juan"), "Perez/Juan",
            "si no escribio nada, el titular: una cita sin nombre no la atiende nadie")
    c.igual(_spa.nombre_de_la_cita("   ", "Perez/Juan"), "Perez/Juan",
            "y un nombre de puros espacios es no haber escrito nada")
    c.igual(_spa.nombre_de_la_cita(None, None), None, "sin ninguno de los dos, nada")
    # El tope no es paranoia de formulario publico: el nombre va a la hoja del dia, que
    # es un PDF de columnas fijas. Un nombre larguisimo no da error, desmaqueta la hoja.
    c.igual(len(_spa.nombre_de_la_cita("A" * 400, "Perez/Juan")), _spa.LARGO_NOMBRE,
            "se corta antes de romper la hoja del dia")
    conn.close()


def el_enlace_del_huesped_guarda_el_nombre_que_escribio(c):
    """EL CAMINO COMPLETO, por el endpoint de verdad.

    La regla se decide en spa.nombre_de_la_cita, pero el fallo vivia una capa mas
    arriba: el endpoint publico pisaba el nombre con el titular DESPUES de recibirlo.
    Probar solo la funcion habria dado verde con el error intacto.
    """
    import asyncio
    conn = comun.base_limpia()
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES ('910001','12','Perez/Juan',?,?,2,0,1,'POR INGRESAR')""",
        (_pms(HOY), _pms(HOY + datetime.timedelta(days=3))))
    token = _spa.token_de_reserva(conn, "910001")
    conn.commit()
    conn.close()                      # el endpoint abre la suya y toma BEGIN IMMEDIATE

    import main
    pedido = {
        "nombre_huesped": "Ana Perez", "servicio_codigo": "JUNGLE",
        "fecha": HOY.isoformat(), "hora": "10:00", "acepto_terminos": True,
        "condicion_medica": "ninguna", "cirugia_reciente": "0", "alergias": "ninguna",
        "embarazo": "0", "buceo_24h": "0",
    }
    respuesta = asyncio.run(main.spa_publico_pedir("910001", token, dict(pedido)))

    conn = comun.conexion()
    fila = dict(conn.execute("SELECT * FROM spa_cita WHERE id = ?",
                             (respuesta["id"],)).fetchone())
    c.igual(fila["nombre_huesped"], "Ana Perez", "se guardo a quien recibe el masaje")
    c.igual(fila["room_no"], "12", "la habitacion sigue saliendo de la reserva")
    c.igual(fila["conf_no"], "910001", "y la reserva tambien")
    c.igual(fila["estado"], "SOLICITADA", "entra por confirmar, como antes")

    # La lista que el huesped ve de vuelta dice de quien es cada cita: en una doble, sin
    # el nombre las dos se ven iguales y la segunda parece repetida.
    c.cierto(any(x.get("nombre_huesped") == "Ana Perez"
                 for x in respuesta.get("mis_citas", [])),
             "y la lista de «lo que ya tienes pedido» dice de quien es")
    conn.close()


def sin_nombre_escrito_el_enlace_se_queda_con_el_titular(c):
    """Una cita sin nombre no la atiende nadie, asi que el titular es la red."""
    import asyncio
    conn = comun.base_limpia()
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES ('910002','14','Perez/Juan',?,?,2,0,1,'POR INGRESAR')""",
        (_pms(HOY), _pms(HOY + datetime.timedelta(days=3))))
    token = _spa.token_de_reserva(conn, "910002")
    conn.commit()
    conn.close()

    import main
    respuesta = asyncio.run(main.spa_publico_pedir("910002", token, {
        "servicio_codigo": "JUNGLE", "fecha": HOY.isoformat(), "hora": "11:00",
        "acepto_terminos": True}))

    conn = comun.conexion()
    fila = dict(conn.execute("SELECT nombre_huesped FROM spa_cita WHERE id = ?",
                             (respuesta["id"],)).fetchone())
    c.igual(fila["nombre_huesped"], "Perez/Juan", "queda el titular de la reserva")
    conn.close()


def el_enlace_se_ofrece_solo_para_los_del_dia(c):
    """LO REPORTO EL LODGE: «a la hora de enviar el link despliega de la misma habitacion
    todas las reservas proximas a llegar, lo cual es confuso».

    Y tenia razon: la lista iba de hoy a catorce dias por delante, asi que una habitacion
    con tres reservas encadenadas salia tres veces y no habia forma de saber cual es la
    del huesped que esta en el cuarto AHORA. Mandar el enlace equivocado es mandarle a
    alguien el de otro: la pagina lleva el nombre y la estadia de esa reserva.
    """
    import main
    conn = comun.base_limpia()
    hoy = HOY

    def _reserva(conf, hab, llega, sale):
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                    dep_date, adl, chl, rooms, res_status)
               VALUES (?,?,?,?,?,2,0,1,'POR INGRESAR')""",
            (conf, hab, f"Huesped/{conf}", _pms(llega), _pms(sale)))

    # La 12, con TRES reservas encadenadas: la de ahora y dos que vienen.
    _reserva("910101", "12", hoy - datetime.timedelta(days=2), hoy + datetime.timedelta(days=2))
    _reserva("910102", "12", hoy + datetime.timedelta(days=3), hoy + datetime.timedelta(days=6))
    _reserva("910103", "12", hoy + datetime.timedelta(days=8), hoy + datetime.timedelta(days=11))
    # Una que llega HOY: esa si va, es a quien hay que mandarle el enlace al entrar.
    _reserva("910104", "14", hoy, hoy + datetime.timedelta(days=3))
    # Y una que se va hoy: salio en el bote de la manana, no le queda noche que reservar.
    _reserva("910105", "16", hoy - datetime.timedelta(days=3), hoy)
    conn.commit()
    conn.close()

    d = main.enlaces_spa(fecha=hoy.isoformat(), user={"usuario": "pruebas"})
    confs = [h["conf_no"] for h in d["huespedes"]]
    c.igual(sorted(confs), ["910101", "910104"],
            "solo la reserva que esta en el cuarto hoy y la que llega hoy")
    c.cierto("910102" not in confs and "910103" not in confs,
             "las proximas de esa misma habitacion no se ofrecen")
    c.cierto("910105" not in confs, "ni la que se va hoy, que ya no tiene noches")
    c.igual(d.get("fecha"), hoy.isoformat(),
            "y la lista dice de que dia es, para que no se lea como «todas»")

    # Para preparar los de otro dia se mueve la fecha, que es como se mira todo lo demas.
    otro = main.enlaces_spa(fecha=(hoy + datetime.timedelta(days=4)).isoformat(),
                            user={"usuario": "pruebas"})
    c.igual([h["conf_no"] for h in otro["huespedes"]], ["910102"],
            "ese dia la 12 es la otra reserva, y es la unica que sale")


def el_enlace_saluda_a_todos_los_de_la_habitacion(c):
    """LO PIDIO EL LODGE: «que aparezcan los 2 nombres o los que correspondan a las
    personas que estan en la habitacion en el encabezado, no solo 1 nombre».

    En una doble, saludar solo al titular deja al otro fuera de un enlace que tambien es
    suyo — y es justo quien puede estar pidiendo el masaje. Los nombres salen de la
    MISMA funcion que escribe el nombre en la hoja del dia, para que el enlace y la hoja
    no nombren a gente distinta.

    Y SIN LAS FECHAS DE LA ESTADIA, que las quito el lodge: «eliminar la fecha de
    estadia que esta en azul, para no causar confusion». Se confundian con la fecha de
    la cita, que es la que el huesped elige justo abajo.
    """
    import main
    conn = comun.base_limpia()
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES ('910201','12','Magorian/Flynn',?,?,2,2,1,'POR INGRESAR')""",
        (_pms(HOY), _pms(HOY + datetime.timedelta(days=4))))
    for nombre in ("Flynn Magorian", "Alasdair Magorian"):
        conn.execute("INSERT INTO huesped (conf_no, nombre_completo) VALUES ('910201',?)",
                     (nombre,))
    conn.commit()
    reserva = dict(conn.execute(
        "SELECT * FROM reserva WHERE conf_no='910201'").fetchone())
    d = main._datos_publicos_spa(conn, reserva)
    conn.close()

    c.igual(d["nombres"], "Flynn Magorian y Alasdair Magorian",
            "el encabezado nombra a los dos")
    c.cierto("MAGORIAN" not in d["nombres"],
             "y no a gritos: la pagina la lee el huesped, no el staff")

    # La estadia se sigue mandando —el calendario la necesita para no dejar elegir un
    # dia fuera— pero ya no se escribe en el encabezado.
    import spa_pagina as pag
    c.cierto("{desde}" not in pag.TEXTOS["es"]["habitacion"]
             and "{hasta}" not in pag.TEXTOS["es"]["habitacion"],
             "la linea de la habitacion ya no lleva fechas (es)")
    c.cierto("{desde}" not in pag.TEXTOS["en"]["habitacion"],
             "ni en ingles")
    c.cierto(d["estadia_desde"] and d["estadia_hasta"],
             "pero la estadia sigue viajando, que el calendario la usa")
    c.cierto("D.nombres" in pag._PLANTILLA, "la pagina usa los nombres de la habitacion")


def una_reserva_sin_rooming_saluda_al_titular(c):
    """La contraparte: si Opera no mando la lista de acompanantes no hay nada que
    componer, y el enlace tiene que seguir saludando igual que antes."""
    import main
    conn = comun.base_limpia()
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES ('910202','14','Perez/Juan',?,?,2,0,1,'POR INGRESAR')""",
        (_pms(HOY), _pms(HOY + datetime.timedelta(days=2))))
    conn.commit()
    reserva = dict(conn.execute(
        "SELECT * FROM reserva WHERE conf_no='910202'").fetchone())
    d = main._datos_publicos_spa(conn, reserva)
    conn.close()
    c.igual(d["nombres"], "Juan Perez", "se saluda al titular, con su nombre de pila")


def el_formulario_pregunta_el_nombre_de_primero(c):
    """Y lo pide VACIO.

    Precargarlo con el titular seria contestar la pregunta por el huesped justo con la
    respuesta que suele estar mal — y la ficha medica de abajo quedaria a nombre de
    quien no la contesto.
    """
    import spa_pagina
    plantilla = spa_pagina._PLANTILLA

    c.cierto('id="nombre"' in plantilla, "el campo existe")
    # De primero DENTRO de la tarjeta de pedir, antes del tratamiento.
    i_nombre = plantilla.find('id="nombre"')
    i_trat = plantilla.find('id="serv"')
    c.cierto(0 < i_nombre < i_trat, "va antes que el tratamiento")
    c.cierto('value="${esc(D.nombre' not in plantilla, "no viene precargado")
    c.cierto('nombre_huesped: nombre' in plantilla, "se manda al guardar")
    c.cierto('if (!nombre) return mostrar(T("falta_nombre"))' in plantilla,
             "y no se puede enviar sin el")
    # Que sobreviva al boton EN/ES: cambiar de idioma no puede costarle lo ya escrito.
    c.cierto('nombre: v("nombre")' in plantilla, "se lee al cambiar de idioma")
    c.cierto('p("nombre", d.nombre)' in plantilla, "y se vuelve a escribir")

    # El lodge lo pidio en ingles, que es el idioma por omision de la pagina; el espanol
    # va igual porque la pagina tiene el boton y, sin la entrada, caeria al ingles.
    for idioma in ("en", "es"):
        for clave in ("nombre_q", "nombre_ayuda", "nombre_ph", "falta_nombre", "para"):
            c.cierto(bool(spa_pagina.TEXTOS[idioma].get(clave)),
                     f"{idioma}: esta el texto «{clave}»")
    c.igual(spa_pagina.TEXTOS["en"]["nombre_q"], "Name", "en ingles se llama Name")
    c.igual(spa_pagina.IDIOMA_POR_DEFECTO, "en", "y el ingles sigue siendo el de salida")


PRUEBAS = [
    cambiar_el_tratamiento_recalcula_la_duracion,
    cambiar_el_tratamiento_no_cancela_ni_pierde_la_ficha,
    un_tratamiento_que_no_existe_se_rechaza,
    sin_cambio_no_pasa_nada,
    sin_duracion_en_el_catalogo_se_conserva_la_que_tenia,
    el_choque_se_mira_con_la_duracion_NUEVA,
    dos_citas_seguidas_de_la_misma_habitacion_no_chocan,
    dos_citas_que_se_solapan_de_verdad_siguen_chocando,
    entre_habitaciones_distintas_el_espacio_sigue_valiendo,
    la_hora_que_se_le_ofrece_al_huesped_es_la_que_se_le_acepta,
    la_agenda_del_spa_no_marca_las_dos_citas_del_mismo_cuarto,
    el_enlace_del_huesped_deja_encadenar_la_segunda_cita,
    las_terapeutas_tienen_nombre,
    agregar_una_terapeuta_sube_cuantas_citas_caben,
    a_la_base_ya_instalada_le_entran_las_nuevas,
    renombrar_una_terapeuta_arrastra_sus_citas,
    la_pantalla_deja_cambiar_el_tratamiento,
    el_nombre_escrito_manda_sobre_el_titular,
    el_enlace_del_huesped_guarda_el_nombre_que_escribio,
    sin_nombre_escrito_el_enlace_se_queda_con_el_titular,
    el_enlace_se_ofrece_solo_para_los_del_dia,
    el_enlace_saluda_a_todos_los_de_la_habitacion,
    una_reserva_sin_rooming_saluda_al_titular,
    el_formulario_pregunta_el_nombre_de_primero,
]


if __name__ == "__main__":
    sys.exit(comun.correr("spa", PRUEBAS))
