"""Fija la nomenclatura de abreviaturas de tours del lodge (catalogo 2027).

POR QUE ESTA SUITE. El lodge definio codigos nuevos para los tours y cuatro modalidades
por cada uno:

    PNC           regular / compartido
    C-PNC         cortesia (Complementary)
    PRV-PNC       privado, con cargo
    PRV|CPL-PNC   privado y ademas cortesia

YA SE ESTAN USANDO. En las reservas de Opera de hoy aparece
«PAQUETE 4D/3N+PENSION COMPLETA CPL C-BT+C-CIS+C-NGW». Sin entender el prefijo, el
sistema daba esos codigos por DESCONOCIDOS y esas reservas se quedaban sin sus tours en
la hoja del dia — sin dar ningun error.

Y falla en silencio en las dos direcciones: un prefijo mal leido puede convertir un tour
en otro, y entonces la hoja del dia manda el bote y el guia equivocados.
"""
import contextlib
import io
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402
import opera_paquetes as op                      # noqa: E402


# ---------------------------------------------------------------------------
# Los prefijos
# ---------------------------------------------------------------------------

def se_leen_las_cuatro_modalidades(c):
    """Las cuatro formas del documento, sobre el ejemplo que el propio documento usa."""
    c.igual(op.descomponer("PNC"), ("PNC", False, False), "PNC: regular")
    c.igual(op.descomponer("C-PNC"), ("PNC", False, True), "C-PNC: cortesia")
    c.igual(op.descomponer("PRV-PNC"), ("PNC", True, False), "PRV-PNC: privado")
    c.igual(op.descomponer("PRV|CPL-PNC"), ("PNC", True, True),
            "PRV|CPL-PNC: privado y cortesia")


def se_aceptan_las_dos_formas_del_cuarto_caso(c):
    """El documento lo escribe de dos maneras: 'PRV|CPL-PNC' en la tabla de reglas y
    'PRV|CPLPNC' en la tabla maestra. Discutir cual es la buena no le sirve a nadie; lo
    que sirve es que ninguna de las dos se pierda."""
    for escrito in ("PRV|CPL-PNC", "PRV|CPLPNC", "PRV|C-PNC", "PRV |CPL- PNC"):
        c.igual(op.descomponer(escrito), ("PNC", True, True),
                f"«{escrito}» se entiende igual")


def el_prefijo_no_convierte_un_tour_en_otro(c):
    """Un PNC privado sigue siendo la caminata a San Pedrillo: mismo horario, mismo
    bote, misma entrada del SINAC. Si el prefijo cambiara el tour, la hoja del dia
    mostraria dos salidas donde hay una."""
    for codigo in ("PNC", "C-PNC", "PRV-PNC", "PRV|CPL-PNC"):
        c.igual(op.clasificar(codigo)["valor"], "PNC", f"«{codigo}» es el tour PNC")


def el_sufijo_de_descuento_se_sigue_quitando(c):
    """Los codigos traen el descuento comercial pegado al final ('CIS30'), y eso ya
    funcionaba. Tiene que seguir funcionando CON prefijo."""
    c.igual(op.descomponer("CIS30"), ("CIS", False, False), "CIS30 -> CIS")
    c.igual(op.descomponer("C-CIS30"), ("CIS", False, True), "C-CIS30 -> CIS, cortesia")
    c.igual(op.descomponer("PRV-CIS3027"), ("CIS", True, False), "PRV-CIS3027 -> CIS")


def un_codigo_que_solo_es_prefijo_no_inventa_un_tour(c):
    """'PRV-' sin nada detras no es un tour. Quedarse con una base vacia haria que
    cualquier cosa empatara con cualquier cosa."""
    for raro in ("PRV-", "C-", "PRV|CPL-"):
        base, _, _ = op.descomponer(raro)
        c.cierto(base and base != "", f"«{raro}» no deja una base vacia")
        c.igual(op.clasificar(raro)["tipo"], "desconocido",
                f"«{raro}» se avisa como desconocido")


# ---------------------------------------------------------------------------
# Los codigos reales que YA aparecen en Opera
# ---------------------------------------------------------------------------

def los_codigos_de_la_reserva_real_se_reconocen(c):
    """De una reserva de verdad: «PENSION COMPLETA CPL C-BT+C-CIS+C-NGW»."""
    bt = op.clasificar("C-BT")
    c.igual(bt["tipo"], "traslado", "C-BT es un traslado en bote, no un tour")
    c.igual(bt["cortesia"], True, "y es cortesia")

    cis = op.clasificar("C-CIS")
    c.igual(cis["tipo"], "tour", "C-CIS es un tour")
    c.igual(cis["valor"], "SNORKEL", "el snorkel de Isla del Caño")
    c.igual(cis["cortesia"], True, "de cortesia")

    ngw = op.clasificar("C-NGW")
    c.igual(ngw["tipo"], "tour", "C-NGW es un tour")
    c.igual(ngw["valor"], "NGW", "la caminata naturalista, que es nueva")
    c.igual(ngw["cortesia"], True, "de cortesia")


def ninguno_de_los_23_codigos_queda_como_desconocido(c):
    """Es el punto de todo esto: que una reserva con la nomenclatura nueva no se quede
    sin sus tours."""
    sueltos = []
    for cod, _, _, _ in op.CATALOGO_2027:
        for forma in (cod, f"C-{cod}", f"PRV-{cod}", f"PRV|CPL-{cod}"):
            if op.clasificar(forma)["tipo"] == "desconocido":
                sueltos.append(forma)
    for cod in op.TRASLADOS_2027:
        for forma in (cod, f"C-{cod}"):
            if op.clasificar(forma)["tipo"] == "desconocido":
                sueltos.append(forma)
    c.igual(sueltos, [], "ningun codigo del catalogo queda sin reconocer")


# ---------------------------------------------------------------------------
# Lo que el documento pide distinguir
# ---------------------------------------------------------------------------

def el_manglar_del_traslado_no_es_el_tour_de_manglar(c):
    """El documento lo subraya: «No usar MGS y MGX como sinonimos». MGX viene incluido
    en el traslado; tratarlo como tour pondria una salida de manglar en la hoja del dia
    que no existe, con su guia y su bote apartados."""
    c.igual(op.clasificar("MGS")["tipo"], "tour", "MGS es el tour completo")
    c.igual(op.clasificar("MGS")["valor"], "MANGLAR", "y es el manglar de siempre")
    c.igual(op.clasificar("MGX")["tipo"], "traslado",
            "MGX es parte del traslado, NO un tour")


def la_descripcion_del_MGX_no_crea_un_tour_de_manglar(c):
    """El caso real del comunicado. La descripcion que acompana al codigo lleva la
    palabra —«BT+MGX: Boat transfer + Experiencia de Manglar durante el traslado»— y el
    reconocimiento de tours busca «MANGLAR» por texto. Salia una salida de manglar en la
    hoja del dia, con guia y bote apartados, para un tour que NO existe."""
    import pdf_parser as pp
    ejemplo = "BT+MGX: Boat transfer + Experiencia de Manglar durante el traslado"
    c.igual(pp.cross_reference_tours(ejemplo), [],
            "el manglar del traslado no crea un tour")
    c.igual(pp.cross_reference_tours("BT+MGX: boat transfer + mangrove experience"), [],
            "ni escrito en ingles")

    # Y lo contrario, que es lo que hace que esto no sea un parche: un manglar de VERDAD
    # tiene que seguir apareciendo, aunque la reserva traiga tambien un MGX.
    c.cierto("MANGLAR" in pp.cross_reference_tours("03: MGS"),
             "MGS sigue siendo el tour de manglar")
    c.cierto("MANGLAR" in pp.cross_reference_tours("BT+MGX el sabado y 04: MGS"),
             "y se reconoce aunque en la misma reserva haya un MGX")
    c.cierto("MANGLAR" in pp.cross_reference_tours("BT+MGX, y aparte el tour MANGLAR"),
             "el codigo MANGLAR en mayusculas manda sobre el MGX")


def un_servicio_privado_de_cortesia_es_las_dos_cosas(c):
    """'PRV|C-' es la forma canonica del comunicado para privado + CPL. La cortesia vivia
    en un grupo SIN NOMBRE de la expresion, asi que se leia privado y nada mas: el
    servicio no quedaba marcado como cortesia a la hora de cobrar. El caso de 'C-' solo
    si estaba bien, que es por lo que no saltaba a la vista."""
    import pdf_parser as pp
    for texto in ("03: PRV|C-PNC", "03: PRV|CPL-PNC"):
        c.igual(pp.modalidad_antes_de(texto, texto.index("PNC")), (True, True),
                f"«{texto}» es privado Y cortesia")
    for texto, espera in (("03: PNC", (False, False)),
                          ("03: C-PNC", (False, True)),
                          ("03: PRV-PNC", (True, False))):
        c.igual(pp.modalidad_antes_de(texto, texto.index("PNC")), espera,
                f"«{texto}» sigue igual")
    # Y el otro camino, el de los paquetes de Opera, tiene que decir lo mismo.
    c.igual(op.descomponer("PRV|C-PNC"), ("PNC", True, True),
            "los dos caminos coinciden")


def un_codigo_nuevo_no_crea_un_tour_que_ya_existe(c):
    """Lo que reporto el hotel. KSJ es el San Josecito que el lodge YA hace, con el
    nombre nuevo, y entraba como tour APARTE: una salida «KSJ» sin ficha de itinerario
    al lado de la de siempre. La tabla de equivalencias existe para evitar justo eso."""
    import init_db
    c.igual(op.clasificar("KSJ")["valor"], "SAN JOSECITO",
            "KSJ es el San Josecito de siempre")
    codigos = {t[0] for t in init_db.TOURS}
    c.cierto("SAN JOSECITO" in codigos,
             "y SAN JOSECITO existe en el catalogo, que es lo que exige la clave foranea")
    c.igual("KSJ" in codigos, False, "KSJ ya no es un tour aparte")
    # Y los que SI son nuevos siguen siendolo: el documento los da como actividades
    # distintas y no hay ninguna equivalente.
    for cod in ("DSD", "SFF", "CLW", "HDA", "NGW"):
        c.cierto(cod in codigos, f"{cod} sigue siendo un tour propio")


def todo_tour_reconocido_tiene_ficha_de_itinerario(c):
    """El otro sintoma: el itinerario del huesped mostraba «Dsd» —el codigo con la
    primera letra en mayuscula— porque no habia ficha. Es un documento que se le manda
    al huesped con el nombre interno del sistema."""
    import catalogo_itinerario as cat
    import init_db
    for codigo, nombre, *_ in init_db.TOURS:
        base = codigo.replace(" PRIVADO", "").strip().upper()
        info = cat.texto_tour(codigo)
        c.cierto(base in cat.TOURS_ITINERARIO,
                 f"«{codigo}» tiene ficha de itinerario")
        c.cierto(info["nombre"] and info["nombre"] != codigo.title(),
                 f"«{codigo}» muestra un nombre de verdad, no el codigo")


def los_tours_ya_guardados_se_unifican_al_arrancar(c):
    """Lo que reporto el hotel: en la agenda salia SNORKEL por un lado y CIS por otro,
    con la misma gente repartida entre los dos.

    Arreglar la tabla de equivalencias no arregla lo YA guardado: recepcion habia creado
    los alias a mano como tours aparte, y la importacion solo vuelve a tocar las reservas
    que cambian. Se unifican al arrancar, por RENOMBRADO: ninguna salida se pierde."""
    import init_db
    conn = comun.base_limpia()

    # Como esta en produccion: los alias existen como tours propios...
    for cod in ("CIS", "EBT", "KSJ"):
        conn.execute(
            """INSERT OR IGNORE INTO tour_catalogo
                 (codigo, nombre, max_pax_guia, requiere_entrada_sinac, requiere_bote,
                  es_privado, activo) VALUES (?,?,8,0,0,0,1)""", (cod, cod))
    conn.execute("INSERT INTO reserva (conf_no, adl, chl, res_status, arr_date, dep_date) "
                 "VALUES ('R1',2,0,'EN CASA','01-05-26','06-05-26')")
    # ...con salidas repartidas entre el alias y el tour de siempre.
    for cod, fecha in (("SNORKEL", "2026-05-01"), ("CIS", "2026-05-02"),
                       ("EBT", "2026-05-03"), ("KSJ", "2026-05-04"),
                       # y una que CHOCA: el mismo dia que su SNORKEL.
                       ("CIS", "2026-05-01")):
        conn.execute("INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax) "
                     "VALUES ('R1',?,?,2)", (fecha, cod))
    conn.commit()
    conn.close()

    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db()                      # el arranque, que es donde se unifica

    conn = comun.conexion()
    por_tour = {r["t"]: r["n"] for r in conn.execute(
        "SELECT tour_codigo t, COUNT(*) n FROM tour_asignado GROUP BY t")}
    c.igual(por_tour.get("CIS"), None, "CIS ya no existe como tour aparte")
    c.igual(por_tour.get("EBT"), None, "ni EBT")
    c.igual(por_tour.get("KSJ"), None, "ni KSJ")
    c.igual(por_tour.get("SNORKEL"), 2,
            "el SNORKEL suma el suyo y el del alias, sin la duplicada del mismo dia")
    c.igual(por_tour.get("PAJAREO"), 1, "EBT quedo en PAJAREO")
    c.igual(por_tour.get("SAN JOSECITO"), 1, "KSJ quedo en SAN JOSECITO")

    del_catalogo = {r["codigo"] for r in conn.execute(
        "SELECT codigo FROM tour_catalogo")}
    for cod in ("CIS", "EBT", "KSJ"):
        c.igual(cod in del_catalogo, False,
                f"«{cod}» se retiro del catalogo, para que no se vuelva a usar")

    # Idempotente: arrancar otra vez no encuentra nada que hacer ni rompe nada.
    conn.close()
    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db()
    conn = comun.conexion()
    c.igual(conn.execute("SELECT COUNT(*) n FROM tour_asignado").fetchone()["n"], 4,
            "arrancar dos veces no cambia nada")
    conn.close()


def el_claro_del_bosque_y_el_garden_to_table_son_uno_solo(c):
    """Lo confirmo el lodge: CLARO y GTT son EL MISMO TOUR.

    Estaban partidos en dos, y eso no se ve como un error: se ve como dos salidas el
    mismo dia, cada una pidiendo su guia y su cupo, y el mismo huesped contado dos veces.
    GTE ya apuntaba a CLARO desde el principio; GTT se habia quedado fuera.

    SOBREVIVE CLARO. Medido sobre la base del lodge: CLARO tenia nombre propio en el
    catalogo («Claro del Bosque»), seis salidas contra una, y CBE y GTE ya apuntaban ahi.
    La fila de GTT se llamaba literalmente «GTT».
    """
    import pdf_parser
    # Las cinco formas de escribirlo caen en el mismo tour, y en UNO solo. Lo de «uno
    # solo» es la mitad que importa: con GTT en la lista de codigos Y en la de alias, el
    # lector devolvia ['GTT', 'CLARO'] y la reserva salia dos veces el mismo dia.
    for texto in ("GTT", "GTE", "CBE", "Garden to Table", "Garden-to-Table",
                  "CLARO", "Claro del Bosque", "CB"):
        c.igual(pdf_parser.cross_reference_tours(texto), ["CLARO"],
                f"«{texto}» es Claro del Bosque, y uno solo")
    c.igual(op.TOURS_POR_RAIZ.get("GTT"), "CLARO", "y el paquete de Opera tambien")
    c.cierto("GTT" not in pdf_parser.TOUR_CODES,
             "GTT ya no es un codigo propio: entra por la tabla de equivalencias")


def el_garden_to_table_ya_guardado_pasa_a_claro(c):
    """EL CAMINO DE PRODUCCION. Cambiar la tabla no arregla lo YA guardado.

    Se comprueba sobre una base que ya tiene GTT como tour propio, con su salida, su
    entrada del parque y su tiquete — que es como esta la del lodge.
    """
    import init_db
    conn = comun.base_limpia()
    conn.execute(
        """INSERT OR IGNORE INTO tour_catalogo
             (codigo, nombre, horario_inicio, horario_fin, max_pax_guia,
              requiere_entrada_sinac, requiere_bote, es_privado, activo)
           VALUES ('GTT','GTT','15:00','17:00',6,0,0,0,1)""")
    conn.execute("INSERT INTO reserva (conf_no, adl, chl, res_status, arr_date, dep_date) "
                 "VALUES ('R9',2,0,'EN CASA','01-05-26','06-05-26')")
    for cod, fecha in (("GTT", "2026-05-02"), ("CLARO", "2026-05-03"),
                       # y una que CHOCA: el mismo dia que su CLARO.
                       ("GTT", "2026-05-03")):
        conn.execute("INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax) "
                     "VALUES ('R9',?,?,2)", (fecha, cod))
    conn.execute("INSERT INTO entrada_sinac (tour_codigo, fecha, pax_total_grupo) "
                 "VALUES ('GTT','2026-05-02',3)")
    conn.execute("INSERT INTO tiquete_sinac (fecha, tour_codigo, archivo) "
                 "VALUES ('2026-05-02','GTT','x/y.pdf')")
    conn.commit()
    conn.close()

    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db()                      # el arranque, que es donde se unifica

    conn = comun.conexion()
    por_tour = {r["t"]: r["n"] for r in conn.execute(
        "SELECT tour_codigo t, COUNT(*) n FROM tour_asignado GROUP BY t")}
    c.igual(por_tour.get("GTT"), None, "no queda ninguna salida con el codigo viejo")
    c.igual(por_tour.get("CLARO"), 2,
            "CLARO suma la suya y la de GTT, sin la duplicada del mismo dia")
    c.igual({r["codigo"] for r in conn.execute(
        "SELECT codigo FROM tour_catalogo WHERE codigo = 'GTT'")}, set(),
        "GTT se retiro del catalogo, para que no se vuelva a usar")

    c.igual(conn.execute("SELECT tour_codigo FROM entrada_sinac").fetchone()[0], "CLARO",
            "la entrada del parque se va con el")
    # El tiquete NO tiene clave foranea —se ancla a la fecha— asi que nadie lo arrastra
    # solo. Si se quedara con el codigo viejo dejaria de emparejar con su entrada, sin
    # dar ningun error, y el boton del guia saldria vacio en el puesto del parque.
    c.igual(conn.execute("SELECT tour_codigo FROM tiquete_sinac").fetchone()[0], "CLARO",
            "y el comprobante del SINAC tambien")

    fila = dict(conn.execute(
        "SELECT * FROM tour_catalogo WHERE codigo = 'CLARO'").fetchone())
    c.igual(fila["horario_inicio"], None,
            "CLARO se queda como el hotel lo configuro: sin hora fija, la pone recepcion")
    c.igual(fila["max_pax_guia"], 10, "y con su cupo por guia, no el del codigo retirado")
    c.igual(fila["requiere_bote"], 0, "sigue sin pedir bote: es una actividad del lodge")
    conn.close()


def la_isla_y_el_snorkel_son_uno_solo(c):
    """Lo pidio el lodge: «esta duplicando ISLA y SNORKEL».

    Son el mismo tour —el snorkel en la Isla del Caño, a las 7:15, con el mismo bote y la
    misma entrada del parque— y el sistema ya lo sabia A MEDIAS: el paquete de Opera
    («CIS») entraba como SNORKEL y el itinerario escrito a mano entraba como ISLA. La
    reserva que traia las dos cosas salia DOS VECES el mismo dia.

    SOBREVIVE SNORKEL. Medido sobre la base del lodge: 147 salidas contra 4, 61 entradas
    del SINAC contra 2, y es a donde ya apuntaban CIS y SCI.
    """
    import pdf_parser
    for texto in ("ISLA", "SNORKEL", "CIS", "SNK", "Cano Island", "Caño Island",
                  "Snorkeling"):
        c.igual(pdf_parser.cross_reference_tours(texto), ["SNORKEL"],
                f"«{texto}» es el snorkel de Isla del Caño, y uno solo")
    c.igual(op.TOURS_POR_RAIZ.get("CIS"), "SNORKEL", "y el paquete de Opera tambien")
    c.cierto("ISLA" not in pdf_parser.TOUR_CODES,
             "ISLA ya no es un codigo propio: entra por la tabla de equivalencias")
    # La reserva que trae las DOS formas en el mismo renglon tiene que dar UN tour, no
    # dos: es el caso que el lodge vio en pantalla.
    c.igual(pdf_parser.cross_reference_tours("PNC e ISLA, tambien CIS"),
            ["PNC", "SNORKEL"], "las dos formas juntas siguen siendo una sola salida")


def la_isla_ya_guardada_pasa_a_snorkel(c):
    """EL CAMINO DE PRODUCCION: cambiar la tabla no arregla lo YA guardado.

    Se comprueba sobre una base que ya tiene ISLA como tour propio —con su variante
    privada, su salida, su entrada del parque y su tiquete—, que es como esta la del
    lodge.
    """
    import init_db
    conn = comun.base_limpia()
    for cod, base, priv in (("ISLA", None, 0), ("ISLA PRIVADO", "ISLA", 1)):
        conn.execute(
            """INSERT OR IGNORE INTO tour_catalogo
                 (codigo, nombre, horario_inicio, horario_fin, max_pax_guia,
                  requiere_entrada_sinac, requiere_bote, es_privado, tour_base, activo)
               VALUES (?, ?, '07:15','12:30',8,1,1,?,?,1)""", (cod, cod, priv, base))
    conn.execute("INSERT INTO reserva (conf_no, adl, chl, res_status, arr_date, dep_date) "
                 "VALUES ('R7',2,0,'EN CASA','01-05-26','06-05-26')")
    for cod, fecha, privado in (("ISLA", "2026-05-02", 0),
                                ("SNORKEL", "2026-05-03", 0),
                                # y una que CHOCA: el mismo dia que su SNORKEL.
                                ("ISLA", "2026-05-03", 0),
                                # la privada, que NO es la misma salida que la compartida
                                ("ISLA PRIVADO", "2026-05-04", 0)):
        conn.execute("INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax, "
                     "es_privado) VALUES ('R7',?,?,2,?)", (fecha, cod, privado))
    conn.execute("INSERT INTO entrada_sinac (tour_codigo, fecha, pax_total_grupo) "
                 "VALUES ('ISLA','2026-05-02',3)")
    conn.execute("INSERT INTO tiquete_sinac (fecha, tour_codigo, archivo) "
                 "VALUES ('2026-05-02','ISLA','x/y.pdf')")
    conn.commit()
    conn.close()

    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db()                      # el arranque, que es donde se unifica

    conn = comun.conexion()
    por_tour = {r["t"]: r["n"] for r in conn.execute(
        "SELECT tour_codigo t, COUNT(*) n FROM tour_asignado GROUP BY t")}
    c.igual(por_tour.get("ISLA"), None, "no queda ninguna salida con el codigo viejo")
    c.igual(por_tour.get("ISLA PRIVADO"), None, "ni con el de su variante privada")
    c.igual(por_tour.get("SNORKEL"), 3,
            "SNORKEL suma la suya, la de ISLA y la privada, sin la duplicada del mismo dia")
    # LA MARCA DE PRIVADO NO SE PIERDE. Moverla a secas convertiria una salida privada en
    # una compartida: un bote y un guia menos, sin un solo error en pantalla.
    c.igual(conn.execute("SELECT es_privado FROM tour_asignado WHERE fecha = '2026-05-04'"
                         ).fetchone()[0], 1,
            "la salida que era «ISLA PRIVADO» sigue siendo privada")
    c.igual({r["codigo"] for r in conn.execute(
        "SELECT codigo FROM tour_catalogo WHERE codigo LIKE 'ISLA%'")}, set(),
        "ISLA y su privada se retiraron del catalogo, para que no se vuelvan a usar")

    c.igual(conn.execute("SELECT tour_codigo FROM entrada_sinac").fetchone()[0], "SNORKEL",
            "la entrada del parque se va con el")
    c.igual(conn.execute("SELECT tour_codigo FROM tiquete_sinac").fetchone()[0], "SNORKEL",
            "y el comprobante del SINAC tambien")
    conn.close()


def al_unificar_se_recalcula_la_entrada_del_parque(c):
    """La entrada del SINAC se compra POR CABEZA, y unificar cambia cuánta gente va.

    La entrada que sobrevive se quedaba con el pax que tenía ANTES de recibir las salidas
    del otro codigo: sobre la base del lodge decia 7 el 23 de diciembre cuando ya eran 15.
    Eso no da ningun error — se descubre en la taquilla del parque, con el plazo de 15
    dias encima.

    Dos reservas distintas, el mismo dia, una escrita ISLA y la otra SNORKEL: son la
    misma salida y el total tiene que cubrirlas a las dos, mas el guia.
    """
    import init_db
    conn = comun.base_limpia()
    conn.execute(
        """INSERT OR IGNORE INTO tour_catalogo
             (codigo, nombre, horario_inicio, horario_fin, max_pax_guia,
              requiere_entrada_sinac, requiere_bote, es_privado, activo)
           VALUES ('ISLA','Isla','07:15','12:30',8,1,1,0,1)""")
    for conf, pax in (("R1", 4), ("R2", 3)):
        conn.execute("INSERT INTO reserva (conf_no, adl, chl, res_status, arr_date, "
                     "dep_date) VALUES (?,?,0,'EN CASA','01-05-26','06-05-26')",
                     (conf, pax))
    conn.execute("INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax) "
                 "VALUES ('R1','2026-05-05','ISLA',4)")
    conn.execute("INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax) "
                 "VALUES ('R2','2026-05-05','SNORKEL',3)")
    # Cada codigo con SU entrada pendiente, como las tiene la base del lodge.
    for cod, pax in (("ISLA", 5), ("SNORKEL", 4)):
        conn.execute("""INSERT INTO entrada_sinac
                          (tour_codigo, fecha, conf_entrada, pax_total_grupo, estado)
                        VALUES (?, '2026-05-05', NULL, ?, 'SIN_COMPRAR')""", (cod, pax))
    conn.commit()
    conn.close()

    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db()

    conn = comun.conexion()
    entradas = [dict(r) for r in conn.execute(
        "SELECT tour_codigo, pax_total_grupo FROM entrada_sinac WHERE fecha='2026-05-05'")]
    c.igual(len(entradas), 1, "las dos entradas del mismo dia quedan en una")
    c.igual(entradas[0]["tour_codigo"], "SNORKEL", "con el codigo bueno")
    # 4 + 3 de las dos reservas, mas 1 del guia. Sin el recalculo se quedaba en 4.
    c.igual(entradas[0]["pax_total_grupo"], 8,
            "y el total cubre a TODA la gente que va, mas el guia")
    conn.close()


def unificar_no_puede_tumbar_el_arranque(c):
    """ESTO PASO. La unificacion choco contra el UNIQUE de las entradas del parque, la
    excepcion subio por init_db —que corre al arrancar— y el hotel se quedo SIN SISTEMA:
    502 en todas las pantallas, con la operacion del dia en marcha.

    Dos cosas se fijan aqui: que ese choque concreto ya no pase, y que NINGUNA limpieza
    pueda impedir el arranque aunque falle por otra razon."""
    import init_db
    conn = comun.base_limpia()
    conn.execute("""INSERT OR IGNORE INTO tour_catalogo
                      (codigo, nombre, max_pax_guia, requiere_entrada_sinac,
                       requiere_bote, es_privado, activo)
                    VALUES ('CIS','Cano Island',8,1,1,0,1)""")
    # La MISMA entrada del parque anotada dos veces, una con cada codigo.
    for cod in ("SNORKEL", "CIS"):
        conn.execute("""INSERT INTO entrada_sinac
                          (tour_codigo, fecha, conf_entrada, pax_total_grupo, estado)
                        VALUES (?, '2026-05-01', NULL, 4, 'SIN_COMPRAR')""", (cod,))
    conn.commit()
    conn.close()

    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db()                      # antes reventaba aqui

    conn = comun.conexion()
    entradas = [dict(r) for r in conn.execute(
        "SELECT tour_codigo, fecha FROM entrada_sinac")]
    c.igual(len(entradas), 1, "las dos entradas del mismo dia quedan en una")
    c.igual(entradas[0]["tour_codigo"], "SNORKEL", "con el codigo bueno")
    conn.close()

    # La red de seguridad: una limpieza que falle NO puede impedir el arranque.
    def limpieza_que_revienta(_conn):
        raise sqlite3.IntegrityError("fallo inventado para la prueba")

    salida = io.StringIO()
    otra = comun.conexion()
    with contextlib.redirect_stdout(salida):
        init_db._sin_tumbar_el_arranque(otra, limpieza_que_revienta)
    otra.close()
    c.cierto("AVISO" in salida.getvalue(),
             "una limpieza que falla lo dice en el registro")
    c.cierto("no se pudo aplicar" in salida.getvalue(),
             "y explica que se dejo para despues")


def una_entrada_ya_comprada_no_se_pierde_al_unificar(c):
    """La entrada COMPRADA esta pagada y su numero de confirmacion es lo unico que no se
    puede volver a conseguir. Si el choque se resolviera quedandose con la otra, el hotel
    perderia una entrada que ya pago."""
    import init_db
    conn = comun.base_limpia()
    conn.execute("""INSERT OR IGNORE INTO tour_catalogo
                      (codigo, nombre, max_pax_guia, requiere_entrada_sinac,
                       requiere_bote, es_privado, activo)
                    VALUES ('CIS','Cano Island',8,1,1,0,1)""")
    conn.execute("""INSERT INTO entrada_sinac
                      (tour_codigo, fecha, conf_entrada, pax_total_grupo, estado)
                    VALUES ('SNORKEL','2026-05-02',NULL,4,'SIN_COMPRAR')""")
    conn.execute("""INSERT INTO entrada_sinac
                      (tour_codigo, fecha, conf_entrada, pax_total_grupo, estado)
                    VALUES ('CIS','2026-05-02',NULL,6,'COMPRADA')""")
    conn.commit()
    conn.close()

    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db()

    conn = comun.conexion()
    filas = [dict(r) for r in conn.execute("SELECT * FROM entrada_sinac")]
    c.igual(len(filas), 1, "queda una sola entrada")
    c.igual(filas[0]["tour_codigo"], "SNORKEL", "con el codigo bueno")
    c.igual(filas[0]["estado"], "COMPRADA", "y CONSERVA que estaba comprada")
    c.igual(filas[0]["pax_total_grupo"], 6, "con el pax de la que se habia pagado")
    conn.close()


def un_alias_creado_a_mano_no_vuelve_a_entrar(c):
    """Aunque el alias exista como tour en el catalogo, la equivalencia manda: si no,
    la importacion seguiria llenando los dos tours con la misma gente."""
    import loader
    catalogo = {"SNORKEL", "PAJAREO", "SAN JOSECITO", "CIS", "EBT", "KSJ"}
    c.igual(loader._codigo_del_catalogo("CIS", catalogo), "SNORKEL",
            "CIS entra como SNORKEL aunque CIS exista como tour")
    c.igual(loader._codigo_del_catalogo("C-CIS", catalogo), "SNORKEL",
            "y con el prefijo de cortesia tambien")
    c.igual(loader._codigo_del_catalogo("SNORKEL", catalogo), "SNORKEL",
            "el codigo propio se respeta")
    c.igual(loader._codigo_del_catalogo("INVENTADO", catalogo), None,
            "y lo que no se reconoce devuelve None, para avisar en vez de escribir")


def la_hora_del_catalogo_llega_al_itinerario_del_huesped(c):
    """Agregar un tour desde la pantalla de Catalogo le pone su horario a la agenda, pero
    el texto del itinerario vive en otro archivo: el huesped seguia recibiendo un
    documento que decia «at ___» aunque la hora estuviera puesta. Quien lo agregara daria
    el trabajo por terminado sin saberlo."""
    import catalogo_itinerario as cat

    sin_hora = cat.texto_tour("DSD")
    c.cierto("___" in sin_hora["horario"], "sin hora en el catalogo queda el hueco")
    c.igual(sin_hora["requiere_revision"], True, "y marcado para revisar")

    con_hora = cat.texto_tour("DSD", horario_del_catalogo="07:15")
    c.cierto("7:15 a.m." in con_hora["horario"],
             "con la hora puesta, el itinerario la trae")
    c.igual("___" in con_hora["horario"], False, "y ya no queda el hueco")
    c.igual(con_hora["requiere_revision"], False, "ni la marca de revisar")

    # Lo que NO debe pasar: pisar una hora que la ficha ya trae escrita. La del catalogo
    # es la de operacion; la del itinerario dice a que hora estar en la casa de guias, y
    # no son la misma.
    pnc = cat.texto_tour("PNC", horario_del_catalogo="09:00")
    c.cierto("7:00 a.m." in pnc["horario"],
             "una ficha con hora propia NO se deja pisar por el catalogo")
    c.igual("9:00" in pnc["horario"], False, "de ninguna forma")

    # Y la hora se escribe como el resto del documento, no como un horario de tren.
    c.igual(cat.hora_legible("07:30"), "7:30 a.m.", "la manana")
    c.igual(cat.hora_legible("14:00"), "2:00 p.m.", "la tarde")
    c.igual(cat.hora_legible("12:15"), "12:15 p.m.", "el mediodia")
    c.igual(cat.hora_legible("00:30"), "12:30 a.m.", "la medianoche")
    c.igual(cat.hora_legible(None), "", "y lo que no es una hora no revienta")


# ---------------------------------------------------------------------------
# El orden del documento que recibe el huesped
# ---------------------------------------------------------------------------

def _datos(tours=(), spa=(), llega="2026-11-16", sale="2026-11-20",
           entrada="Drake", salida="Drake"):
    return {
        "nombre_bienvenida": "Prueba",
        "arr_date_iso": llega, "dep_date_iso": sale,
        "punto_entrada": entrada, "punto_salida": salida,
        "vuelo_entrada": "RZ1068", "hora_vuelo_entrada": "12:50 p.m.",
        "vuelo_salida": "RZ1069", "hora_vuelo_salida": "9:00 a.m.",
        "tours": list(tours), "spa": list(spa),
    }


def _tour(fecha, codigo, horario_inicio=None):
    return {"fecha": fecha, "tour_codigo": codigo, "guia_nombre": None,
            "es_privado": 0, "horario_inicio": horario_inicio}


def _actividades(filas):
    return [" ".join(info["nombre"].split()) for _fecha, info in filas]


def el_dia_con_dos_tours_va_de_la_hora_mas_temprana_a_la_mas_tarde(c):
    """LO PIDIO EL LODGE: «cuando hay 2 tours el mismo dia, que se ordenen o aparezcan
    por horario, el mas temprano al mas tarde, para que se vea mucho mejor y mas claro».

    Y tenia razon: los tours salian en el orden que los devuelve la base —por fecha, sin
    mirar la hora—, asi que la caminata NOCTURNA de las 5:45 p.m. se imprimia encima del
    pajareo de las 6:00 a.m. del MISMO dia. El huesped lee su itinerario como la agenda
    del dia, y asi leido el pajareo parece del dia siguiente.

    Medido en la base del lodge: de 270 itinerarios guardados, 15 tienen dos actividades
    el mismo dia y 2 estaban en desorden por esto.
    """
    import itinerario as itin
    filas = itin.construir_filas(_datos(tours=[
        _tour("2026-11-17", "NW"),        # 5:45 p.m.
        _tour("2026-11-17", "PAJAREO"),   # 6:00 a.m.
    ]))
    c.igual(_actividades(filas),
            ["Arrival Day", "Bird Watching Tour", "Night Walk", "Departure Day"],
            "el pajareo de las 6 va antes que la caminata nocturna")

    # Y el orden no depende de como vengan: al reves da lo mismo.
    al_reves = itin.construir_filas(_datos(tours=[
        _tour("2026-11-17", "PAJAREO"), _tour("2026-11-17", "NW")]))
    c.igual(_actividades(al_reves), _actividades(filas),
            "venga como venga de la base, sale igual")

    # Lo que NO cambia: los dias siguen en orden de fecha.
    tres = itin.construir_filas(_datos(tours=[
        _tour("2026-11-19", "PNC"), _tour("2026-11-17", "NW"),
        _tour("2026-11-18", "SNORKEL")]))
    c.igual([f for f, _ in tres][1:-1], ["November 17", "November 18", "November 19"],
            "y los dias en su orden")


def la_cita_de_spa_cae_en_su_dia_y_no_al_final(c):
    """El otro desorden, que estaba ahi desde siempre: las citas de spa se pegaban TODAS
    al final de la lista, despues del ultimo tour, aunque fueran del segundo dia. Una
    reserva con masaje el martes y caminata el jueves recibia el masaje escrito debajo
    de la caminata."""
    import itinerario as itin
    filas = itin.construir_filas(_datos(
        tours=[_tour("2026-11-19", "PNC")],                       # 7:00 a.m.
        spa=[{"fecha": "2026-11-17", "hora": "14:00", "minutos": 60,
              "tratamiento": "Deep Connection"}]))
    c.igual(_actividades(filas),
            ["Arrival Day", "Spa Treatment", "Hike in Corcovado National Park\nSan Pedrillo"
             .replace("\n", " "), "Departure Day"],
            "el masaje del martes va antes que la caminata del jueves")

    # Y el mismo dia, el masaje de la tarde despues del tour de la manana.
    mismo = itin.construir_filas(_datos(
        tours=[_tour("2026-11-17", "PAJAREO")],                   # 6:00 a.m.
        spa=[{"fecha": "2026-11-17", "hora": "14:00", "minutos": 60,
              "tratamiento": "Deep Connection"}]))
    c.igual(_actividades(mismo)[1:3], ["Bird Watching Tour", "Spa Treatment"],
            "el pajareo de las 6 y despues el masaje de las 2")


def la_llegada_abre_y_la_salida_cierra_aunque_la_hora_diga_otra_cosa(c):
    """El documento empieza el dia que el huesped llega y termina el dia que se va. Si
    se ordenara SOLO por hora no seria asi, y no es un caso inventado: en la base del
    lodge hay una reserva con el snorkel de las 7:15 a.m. el mismo dia que el bote de
    Sierpe de las 11:30, y el itinerario abriria con el snorkel — como si lo hiciera
    antes de llegar.

    El dia de salida es lo mismo al reves: el pajareo de las 6:00 a.m. se hace ANTES de
    irse, aunque el equipaje se recoja a las 5:45.
    """
    import itinerario as itin
    llega = itin.construir_filas(_datos(
        entrada="Sierpe", tours=[_tour("2026-11-16", "SNORKEL")]))   # el dia de llegada
    c.igual(_actividades(llega)[0], "Arrival Day",
            "la llegada abre el itinerario aunque el tour sea mas temprano")

    sale = itin.construir_filas(_datos(tours=[_tour("2026-11-20", "PAJAREO")]))
    c.igual(_actividades(sale)[-1], "Departure Day",
            "y la salida lo cierra, aunque el equipaje se recoja antes del pajareo")
    c.igual(_actividades(sale)[-2], "Bird Watching Tour",
            "con el pajareo del dia de salida justo encima")


def el_fin_de_ano_no_da_vuelta_el_itinerario(c):
    """BUG QUE YA ESTABA: las filas dicen «December 29» y «January 01» —sin el año,
    porque asi se imprime— y al reordenarlas enero se iba antes que diciembre. El
    itinerario de quien pasa el Fin de Año aqui salia al reves: primero el dia de salida.

    Se veia al mover un tour de fecha, que es cuando las filas se reordenan. Medido en la
    base del lodge: 20 reservas de esta temporada cruzan el 31 de diciembre.
    """
    import itinerario as itin
    filas = [
        {"dia": "December 29", "actividad": "Arrival Day",
         "horario": "Boat departure around\n11:30 a.m."},
        {"dia": "December 31", "actividad": "Snorkeling at Caño Island",
         "horario": "Be at the dive center at 7:15 a.m."},
        {"dia": "January 01", "actividad": "Departure Day",
         "horario": "Luggage pick-up in your room at 7:00 a.m."},
    ]
    puestas = itin.incorporar_faltantes(filas, [])
    c.igual([f["dia"] for f in puestas], ["December 29", "December 31", "January 01"],
            "diciembre antes que enero")

    # Y una estadia que NO cruza el año se sigue ordenando igual que siempre.
    normal = itin.incorporar_faltantes([
        {"dia": "January 05", "actividad": "Departure Day", "horario": "7:00 a.m."},
        {"dia": "January 02", "actividad": "Arrival Day", "horario": "11:30 a.m."}], [])
    c.igual([f["dia"] for f in normal], ["January 02", "January 05"],
            "enero con enero, en su orden")


def la_hora_se_lee_del_texto_que_ve_el_huesped(c):
    """El orden sale de la hora IMPRESA en la columna de la derecha, no del catalogo:
    asi se puede comprobar leyendo el documento, y asi tambien caen en su sitio las filas
    que recepcion escribio a mano.

    Lo delicado es lo que NO es una hora: el numero de vuelo, la duracion del tour o el
    numero de un bungalow. Si alguno se leyera como hora, el orden saldria peor que antes.
    """
    import horas
    c.igual(horas.primera_en("Be at the guide house at 6:00 a.m."), 360, "6:00 a.m.")
    c.igual(horas.primera_en("Be at the guide house at 5:45 p.m.\n"
                             "Dinner will be around 7:30 p.m."), 1065,
            "manda la PRIMERA: la hora de estar ahi, no la de la cena")
    c.igual(horas.primera_en("Be at Terra Kitchen at 9:00 a.m. / 4:00 p.m."), 540,
            "con dos horarios, el primero")
    c.igual(horas.primera_en("14:00"), 840, "la cita del spa, en 24 horas")
    c.igual(horas.primera_en("12:50 p.m."), 770, "el mediodia no se va a la madrugada")
    c.igual(horas.primera_en("12:30 a.m."), 30, "ni la medianoche al mediodia")

    # Lo que no es una hora
    c.igual(horas.primera_en("Flight: RZ1070\n12:50 p.m."), 770,
            "el numero de vuelo no es una hora")
    c.igual(horas.primera_en("(5 HOURS TOUR)"), None, "la duracion tampoco")
    c.igual(horas.primera_en("Be at Bungalow #29 at ___"), None,
            "ni el numero del bungalow")
    c.igual(horas.primera_en("Be at the guide house at ___"), None,
            "y un tour sin hora no se inventa una")
    c.igual(horas.primera_en(""), None, "el vacio no revienta")
    c.igual(horas.primera_en(None), None, "ni la falta de texto")

    # Y lo que no dice hora va al FINAL de su dia, no al principio.
    import itinerario as itin
    filas = itin.construir_filas(_datos(tours=[
        _tour("2026-11-17", "CLARO"),     # «at ___»: la coordina recepcion
        _tour("2026-11-17", "PAJAREO")]))
    c.igual(_actividades(filas)[1:3],
            ["Bird Watching Tour", "Claro del Bosque Experience"],
            "lo que todavia no tiene hora queda de ultimo en su dia")


def los_itinerarios_ya_guardados_tambien_se_ponen_en_hora(c):
    """El itinerario se guarda UNA vez y despues se lee de la base: el PDF, la pagina del
    QR y la pantalla salen todos de ahi. Arreglar solo el armado dejaria en desorden a los
    que ya existen hasta que alguien le diera a «Rehacer automatico» — y nadie se lo da,
    porque el desorden no se ve en la pantalla de recepcion, se ve en el documento que
    recibe el huesped.

    La migracion solo REORDENA: no toca una palabra de lo que dice cada fila, asi que lo
    que recepcion escribio a mano se conserva igual.
    """
    import json
    import init_db
    conn = comun.base_limpia()

    def _guardar(conf, filas):
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                    dep_date, adl, chl, rooms, res_status)
               VALUES (?,'12','Prueba/Ana','16-11-26','20-11-26',2,0,1,'POR INGRESAR')""",
            (conf,))
        conn.execute(
            """INSERT INTO itinerario (conf_no, nombre_bienvenida, filas_json, editado)
               VALUES (?,'Prueba',?,1)""", (conf, json.dumps(filas)))

    def _leer(conf):
        return json.loads(conn.execute(
            "SELECT filas_json FROM itinerario WHERE conf_no = ?", (conf,)).fetchone()[0])

    _guardar("940101", [
        {"dia": "November 16", "actividad": "Arrival Day",
         "horario": "Flight: RZ1068\n12:50 p.m."},
        {"dia": "November 17", "actividad": "Night Walk",
         "horario": "Be at the guide house at 5:45 p.m.",
         "detalles": "LO QUE ESCRIBIO RECEPCION"},
        {"dia": "November 17", "actividad": "Bird Watching Tour",
         "horario": "Be at the guide house at 6:00 a.m."},
        {"dia": "November 20", "actividad": "Departure Day",
         "horario": "Luggage pick-up in your room at 6:00 a.m."},
    ])
    # EL CASO REAL de la base del lodge: un tour de las 7:15 a.m. el MISMO dia que el
    # bote de llegada de las 11:30. Ordenando solo por hora, el itinerario abriria con
    # el snorkel — como si el huesped lo hiciera antes de llegar.
    _guardar("940102", [
        {"dia": "November 24", "actividad": "Arrival Day",
         "horario": "Boat departure around\n11:30 a.m."},
        {"dia": "November 24", "actividad": "Snorkeling at Caño Island",
         "horario": "Be at the dive center at 7:15 a.m."},
        {"dia": "November 27", "actividad": "Departure Day",
         "horario": "Luggage pick-up in your room at 7:00 a.m."},
    ])
    conn.commit()

    # Por _migrar, que es por donde pasa de verdad: corre en cada arranque. Llamando a
    # la funcion a mano la prueba pasaria igual aunque nadie la hubiera conectado.
    with contextlib.redirect_stdout(io.StringIO()):
        init_db._migrar(conn)

    guardado = _leer("940101")
    c.igual([f["actividad"] for f in guardado],
            ["Arrival Day", "Bird Watching Tour", "Night Walk", "Departure Day"],
            "al arrancar queda en hora en la base, no solo en la pantalla")
    c.igual([f for f in guardado if f["actividad"] == "Night Walk"][0].get("detalles"),
            "LO QUE ESCRIBIO RECEPCION",
            "con el texto de recepcion intacto: solo se movio de sitio")

    c.igual([f["actividad"] for f in _leer("940102")][0], "Arrival Day",
            "y la llegada sigue abriendo el documento, aunque el tour sea mas temprano")

    c.igual(init_db._ordenar_los_itinerarios_por_hora(conn), 0,
            "y correrla de nuevo no cambia nada")
    conn.close()


def la_modalidad_no_se_pierde_al_reconocer_por_alias(c):
    """El «C-» se leia buscando el codigo CANONICO en la linea: «SNORKEL» en «14: C-CIS».
    No estaba, asi que TODOS los codigos de la nomenclatura 2027 perdian su privado y su
    cortesia — el servicio entraba como compartido y de pago."""
    import pdf_parser as pp
    NOTA = "OPERACION:\n13: INGRESO\n14: C-CIS 201770\n15: PRV-EBT\n16: PRV|C-SIR\n"
    ops = {o["tour"]: o for o in pp.leer_texto_de_reserva(NOTA)["operacion"]
           if o.get("tour")}
    c.igual((ops["SNORKEL"]["privado"], ops["SNORKEL"]["cortesia"]), (False, True),
            "C-CIS es cortesia aunque el tour se llame SNORKEL")
    c.igual((ops["PAJAREO"]["privado"], ops["PAJAREO"]["cortesia"]), (True, False),
            "PRV-EBT es privado aunque el tour se llame PAJAREO")
    c.igual((ops["SIRENA"]["privado"], ops["SIRENA"]["cortesia"]), (True, True),
            "PRV|C-SIR es las dos cosas aunque el tour se llame SIRENA")


def la_pesca_deportiva_es_privada_aunque_no_lo_diga(c):
    """El comunicado: «SFH y SFF se comercializan unicamente en modalidad privada. Por lo
    tanto, no es necesario que lleven el prefijo de PRV». Sin esto, un «SFF» a secas se
    registra como compartido y en la hoja del dia se ve una salida abierta donde hay un
    charter de una sola familia."""
    for cod in ("SFH", "SFF"):
        base, privado, cortesia = op.descomponer(cod)
        c.igual(privado, True, f"{cod} es privado aunque no lleve prefijo")
        c.igual(cortesia, False, f"y {cod} a secas no es cortesia")
        c.igual(op.descomponer(f"C-{cod}"), (base, True, True),
                f"C-{cod} es privado Y cortesia")
        c.igual(op.descomponer(f"PRV-{cod}"), (base, True, False),
                f"y el PRV de mas en PRV-{cod} no cambia nada, ya lo era")
    # El resto NO se vuelve privado por esto.
    c.igual(op.descomponer("PNC"), ("PNC", False, False),
            "un PNC a secas sigue siendo compartido")


def la_tarifa_de_nino_no_esconde_el_servicio(c):
    """Al reabrir la temporada, el 1 de noviembre, Opera empezo a mandar codigos con un
    sufijo de TARIFA pegado al final: KID (niño) y AGY (agencia).
    'BRF3027KID' = Breakfast Included NIÑO 30%.

    raiz() solo sabia quitar el descuento, asi que ninguno de los cinco se reconocia. El
    costo, medido sobre las 10 reservas que los traen: las TRES comidas venian con el
    sufijo, ninguna se reconocia y el regimen quedaba EN BLANCO —la pantalla no sabia que
    era pension completa—; y el snorkel de Isla del Caño y la caminata a San Pedrillo no
    llegaban a la lista de tours vendidos.

    El sufijo sale del plan tarifario, no de que haya un niño alojado: las 10 dicen
    childCount 0 en Opera. No sirve para contar gente; solo dice que esta incluido."""
    esperado = {
        "BRF3027KID": ("comida", "desayuno"),
        "LUN3027KID": ("comida", "almuerzo"),
        "DIN3027KID": ("comida", "cena"),
        "CIS3027KID": ("tour", "SNORKEL"),
        "TSP30KID":   ("tour", "PNC"),
    }
    for cod, (tipo, valor) in esperado.items():
        cl = op.clasificar(cod)
        c.igual(cl["tipo"], tipo, f"{cod} es {tipo}")
        c.igual(cl["valor"], valor, f"y es {valor}, no un servicio aparte")

    # El de niño y el de adulto son EL MISMO servicio, no dos.
    c.igual(op.clasificar("BRF3027KID")["valor"], op.clasificar("BRF")["valor"],
            "el desayuno de un niño es el mismo desayuno")
    c.igual(op.clasificar("CIS3027KID")["valor"], op.clasificar("CIS")["valor"],
            "y su snorkel es el mismo snorkel")

    # AGY es la tarifa de agencia, y tampoco cambia que es.
    c.igual(op.raiz("CISAGY"), "CIS", "AGY tambien se quita")
    c.igual(op.raiz("CIS3027AGY"), "CIS", "y junto con el descuento")

    # Lo que NO debe pasar: quitar de mas y dejar la raiz vacia.
    for cod in ("KID", "AGY", "WEB", "30"):
        c.igual(op.raiz(cod), cod, f"'{cod}' a secas se queda como esta")

    # Y un codigo que termina parecido pero NO es un modificador no se toca.
    c.igual(op.raiz("SFAG"), "SFAG", "SFAG no termina en AGY: no se le quita nada")


def lo_que_no_es_tour_ni_amenidad_va_a_las_notas(c):
    """Lo dijo la operacion del lodge: la hielera de San Pedrillo, la lavanderia, el
    sundowner y el guia incluido NO son amenidades, son notas de la reserva.

    La diferencia no es cosmetica. Una amenidad abre una tarea para un departamento, y
    la pantalla de amenidades existe para que no se olvide un vino o una cuna. Metidas
    ahi, estas seis habrian abierto tareas que nadie tiene que hacer y habrian llenado
    esa pantalla de ruido. En las notas, recepcion las ve y no le piden nada."""
    esperado = {
        "COOLERAGY":    "Hielera",
        "DRINKSAGY":    "Refrescos",
        "GUIDEAGY":     "Guia",
        "LAUNDRYAGY":   "Lavanderia",
        "SUNDOWNERAGY": "Sundowner",
        "TOURFREE":     "cortesia",
        "RFDP":         "RainForest",
    }
    for cod in esperado:
        cl = op.clasificar(cod)
        c.igual(cl["tipo"], "nota", f"{cod} va a las notas")
        c.cierto(bool(cl["valor"]), f"y {cod} trae un texto que leer")
        c.cierto(cl["tipo"] != "amenidad",
                 f"{cod} NO es una amenidad: no abre tarea de nadie")
        c.cierto(cl["tipo"] != "desconocido", f"{cod} ya no es un aviso sin resolver")

    # El texto es NUESTRO, no el de Opera: los codigos son estables y las
    # descripciones cambian.
    c.cierto("Hielera" in op.clasificar("COOLERAGY")["valor"],
             "la hielera se lee como hielera")
    c.cierto("San Pedrillo" in op.clasificar("COOLERAGY")["valor"],
             "y dice para que caminata es")

    # La tarifa de agencia no cambia que es: con o sin AGY, la misma nota.
    c.igual(op.clasificar("COOLERAGY")["valor"], op.clasificar("COOLER")["valor"],
            "COOLER y COOLERAGY son la misma nota")

    # Y lo que SI es tour sigue siendo tour: la tabla de notas va despues.
    c.igual(op.clasificar("CIS")["tipo"], "tour", "un tour sigue siendo tour")
    c.igual(op.clasificar("BRF")["tipo"], "comida", "y una comida, comida")


def leer_paquetes_devuelve_las_notas_sin_repetir(c):
    """El paquete viene repetido por noche. A recepcion le sirve saber que hay lavanderia
    incluida, no leerlo cuatro veces seguidas."""
    detalle = {"reservationPackages": [
        {"packageCode": "LAUNDRYAGY",
         "packageHeaderType": {"primaryDetails": {"description": "Lavanderia"}},
         "scheduleList": [{"consumptionDate": "2026-11-02"},
                          {"consumptionDate": "2026-11-03"},
                          {"consumptionDate": "2026-11-04"}]},
        {"packageCode": "COOLERAGY",
         "packageHeaderType": {"primaryDetails": {"description": "Hielera"}},
         "scheduleList": [{"consumptionDate": "2026-11-03"}]},
    ]}
    leido = op.leer_paquetes(detalle)
    c.igual(len(leido["notas"]), 2, "dos notas, no cuatro")
    c.igual(len(leido["desconocidos"]), 0, "y ninguna queda como desconocida")
    c.igual(len(leido["amenidades"]), 0, "ni como amenidad")
    c.igual(len(leido["tours"]), 0, "ni como tour")


def los_codigos_que_aparecieron_en_octubre_caen_en_su_tour(c):
    """NQ y SPS salieron del aviso de «paquete sin reconocer» al sincronizar 264 reservas
    el 11 de octubre. Los dos son tours que el lodge YA hace, con un codigo nuevo de
    Opera, y sin esto sus salidas no entraban a la hoja del dia: la reserva 601141382
    traia su Night Walk y se cargo con CERO tours.

    Opera manda el nombre completo con el codigo y en los dos es literal:
    'Night Walk' y 'Sirena Park Station (Private Tour)'."""
    c.igual(op.clasificar("NQ")["tipo"], "tour", "NQ es un tour")
    c.igual(op.clasificar("NQ")["valor"], "NW", "y es la caminata nocturna que ya existe")
    c.igual(op.clasificar("NQ")["valor"], op.clasificar("CNW")["valor"],
            "NQ y CNW son el mismo tour, no dos")

    c.igual(op.clasificar("SPS")["tipo"], "tour", "SPS es un tour")
    c.igual(op.clasificar("SPS")["valor"], "SIRENA", "y es la caminata a Sirena")
    # Lo privado va APARTE, no crea otro tour: si lo creara, la hoja del dia mostraria
    # dos salidas donde hay una.
    c.igual(op.clasificar("SPS")["privado"], True,
            "SPS es privado aunque no lleve el prefijo PRV")
    c.cierto("SIRENA PRIVADO" not in op.TOURS_POR_RAIZ.values(),
             "y no se invento un tour 'SIRENA PRIVADO' en el catalogo")

    # Ninguno de los dos puede quedar como desconocido nunca mas.
    for cod in ("NQ", "SPS"):
        c.cierto(op.clasificar(cod)["tipo"] != "desconocido",
                 f"{cod} ya no es un paquete sin reconocer")


def las_dos_estaciones_de_corcovado_son_distintas(c):
    """El documento avisa: «Usar SIR para evitar que ambas estaciones queden registradas
    como PNC». Son caminatas distintas, con horarios distintos."""
    c.igual(op.clasificar("PNC")["valor"], "PNC", "PNC es San Pedrillo")
    c.igual(op.clasificar("SIR")["valor"], "SIRENA", "SIR es Sirena")
    c.cierto(op.clasificar("PNC")["valor"] != op.clasificar("SIR")["valor"],
             "y no son el mismo tour")


def el_discovery_scuba_no_es_el_buceo_de_isla(c):
    """El documento: «Actividad distinta de CID; no requiere usar el mismo codigo»."""
    c.igual(op.clasificar("CID")["valor"], "BUCEO", "CID es el buceo de Isla del Caño")
    c.igual(op.clasificar("DSD")["valor"], "DSD", "DSD es otra actividad")


def los_transportes_no_son_tours(c):
    """Un traslado no lleva guia ni ocupa cupo de tour. Metido en la agenda, apartaria
    recursos para una salida que no existe."""
    for cod in ("TT", "BT", "TRB", "MGX"):
        c.igual(op.clasificar(cod)["tipo"], "traslado", f"{cod} es traslado")


# ---------------------------------------------------------------------------
# Los nombres
# ---------------------------------------------------------------------------

def cada_codigo_tiene_nombre_legible(c):
    c.igual(op.nombre_de("SIR"),
            "Caminata al Parque Nacional Corcovado · Sirena", "en español")
    c.igual(op.nombre_de("SIR", "en"),
            "Hiking to Corcovado National Park · Sirena Station", "en inglés")
    c.cierto("cortesía" in op.nombre_de("C-PNC"), "la cortesia se dice")
    c.cierto("privado" in op.nombre_de("PRV-PNC"), "y lo privado tambien")
    n = op.nombre_de("PRV|CPL-PNC")
    c.cierto("privado" in n and "cortesía" in n, "y las dos juntas")
    c.igual(op.nombre_de("XXNOEXISTE"), "", "un codigo que no existe no inventa nombre")


def los_tours_nuevos_entran_al_catalogo(c):
    """Sin fila en el catalogo, un tour detectado no tiene horario ni capacidad y no se
    puede asignar. Van SIN horario a proposito: el documento da el nombre, no la
    operacion, y un horario inventado es peor que uno vacio que alguien completa."""
    import init_db
    catalogo = {t[0] for t in init_db.TOURS}
    for cod, nombre in init_db.TOURS_2027_NUEVOS:
        c.cierto(cod in catalogo, f"{cod} ({nombre}) esta en el catalogo")
    fila = {t[0]: t for t in init_db.TOURS}["DSD"]
    c.igual(fila[2], None, "y sin horario de inicio inventado")
    c.igual(fila[8], 0, "ni bote supuesto")
    c.igual(fila[7], 0, "ni entrada del SINAC supuesta")


def todo_tour_reconocido_existe_en_el_catalogo(c):
    """Si clasificar() devuelve un tour que no esta en el catalogo, esa salida no se
    puede asignar y nadie se entera."""
    import init_db
    catalogo = {t[0] for t in init_db.TOURS}
    faltan = sorted({v for v in op.TOURS_POR_RAIZ.values()} - catalogo)
    c.igual(faltan, [], "todo tour al que se traduce un codigo existe en el catalogo")


def los_codigos_se_reconocen_en_el_COMENTARIO(c):
    """Donde de verdad van. El documento lo dice: «La nomenclatura no modifica la
    estructura del comentario de la reserva», o sea que los codigos se escriben ahi.
    Reconocerlos solo en los paquetes de Opera habria dejado fuera el caso real."""
    import pdf_parser as pp
    for cod, equivalente, _, _ in op.CATALOGO_2027:
        c.igual(pp.TOUR_ALIASES.get(cod), equivalente or cod,
                f"«{cod}» se reconoce leyendo el comentario")


def la_modalidad_se_lee_pegada_al_codigo(c):
    """'C-CIS' es una cortesia. Un 'CPL' suelto tres palabras antes puede estar
    hablando de otra cosa de la reserva, asi que solo cuenta lo pegado."""
    import pdf_parser as pp
    texto = "11: C-CIS 12: PRV-PNC 13: CPL en hospedaje y luego NW"
    c.igual(pp.modalidad_antes_de(texto, texto.index("CIS")), (False, True),
            "C-CIS es cortesia")
    c.igual(pp.modalidad_antes_de(texto, texto.index("PNC")), (True, False),
            "PRV-PNC es privado")
    c.igual(pp.modalidad_antes_de(texto, texto.index("NW")), (False, False),
            "un CPL lejos NO convierte el NW en cortesia")


def una_sola_tabla_de_equivalencias(c):
    """Dos listas que digan lo mismo se separan, y entonces el mismo codigo significa
    una cosa leyendo el comentario y otra leyendo el paquete."""
    import pdf_parser as pp
    for cod, equivalente, _, _ in op.CATALOGO_2027:
        c.igual(pp.TOUR_ALIASES.get(cod), op.TOURS_POR_RAIZ.get(cod),
                f"«{cod}» significa lo mismo en los dos caminos")


PRUEBAS = [
    se_leen_las_cuatro_modalidades,
    los_codigos_se_reconocen_en_el_COMENTARIO,
    la_modalidad_se_lee_pegada_al_codigo,
    una_sola_tabla_de_equivalencias,
    se_aceptan_las_dos_formas_del_cuarto_caso,
    el_prefijo_no_convierte_un_tour_en_otro,
    el_sufijo_de_descuento_se_sigue_quitando,
    la_tarifa_de_nino_no_esconde_el_servicio,
    lo_que_no_es_tour_ni_amenidad_va_a_las_notas,
    leer_paquetes_devuelve_las_notas_sin_repetir,
    un_codigo_que_solo_es_prefijo_no_inventa_un_tour,
    los_codigos_de_la_reserva_real_se_reconocen,
    ninguno_de_los_23_codigos_queda_como_desconocido,
    el_manglar_del_traslado_no_es_el_tour_de_manglar,
    la_descripcion_del_MGX_no_crea_un_tour_de_manglar,
    un_servicio_privado_de_cortesia_es_las_dos_cosas,
    un_codigo_nuevo_no_crea_un_tour_que_ya_existe,
    los_tours_ya_guardados_se_unifican_al_arrancar,
    el_claro_del_bosque_y_el_garden_to_table_son_uno_solo,
    el_garden_to_table_ya_guardado_pasa_a_claro,
    la_isla_y_el_snorkel_son_uno_solo,
    la_isla_ya_guardada_pasa_a_snorkel,
    al_unificar_se_recalcula_la_entrada_del_parque,
    unificar_no_puede_tumbar_el_arranque,
    una_entrada_ya_comprada_no_se_pierde_al_unificar,
    un_alias_creado_a_mano_no_vuelve_a_entrar,
    todo_tour_reconocido_tiene_ficha_de_itinerario,
    la_hora_del_catalogo_llega_al_itinerario_del_huesped,
    el_dia_con_dos_tours_va_de_la_hora_mas_temprana_a_la_mas_tarde,
    la_cita_de_spa_cae_en_su_dia_y_no_al_final,
    la_llegada_abre_y_la_salida_cierra_aunque_la_hora_diga_otra_cosa,
    el_fin_de_ano_no_da_vuelta_el_itinerario,
    la_hora_se_lee_del_texto_que_ve_el_huesped,
    los_itinerarios_ya_guardados_tambien_se_ponen_en_hora,
    la_modalidad_no_se_pierde_al_reconocer_por_alias,
    la_pesca_deportiva_es_privada_aunque_no_lo_diga,
    los_codigos_que_aparecieron_en_octubre_caen_en_su_tour,
    las_dos_estaciones_de_corcovado_son_distintas,
    el_discovery_scuba_no_es_el_buceo_de_isla,
    los_transportes_no_son_tours,
    cada_codigo_tiene_nombre_legible,
    los_tours_nuevos_entran_al_catalogo,
    todo_tour_reconocido_existe_en_el_catalogo,
]


if __name__ == "__main__":
    sys.exit(comun.correr("codigos de tours", PRUEBAS))
