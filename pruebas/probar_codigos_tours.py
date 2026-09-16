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
    un_codigo_que_solo_es_prefijo_no_inventa_un_tour,
    los_codigos_de_la_reserva_real_se_reconocen,
    ninguno_de_los_23_codigos_queda_como_desconocido,
    el_manglar_del_traslado_no_es_el_tour_de_manglar,
    la_descripcion_del_MGX_no_crea_un_tour_de_manglar,
    un_servicio_privado_de_cortesia_es_las_dos_cosas,
    un_codigo_nuevo_no_crea_un_tour_que_ya_existe,
    los_tours_ya_guardados_se_unifican_al_arrancar,
    unificar_no_puede_tumbar_el_arranque,
    una_entrada_ya_comprada_no_se_pierde_al_unificar,
    un_alias_creado_a_mano_no_vuelve_a_entrar,
    todo_tour_reconocido_tiene_ficha_de_itinerario,
    la_hora_del_catalogo_llega_al_itinerario_del_huesped,
    la_modalidad_no_se_pierde_al_reconocer_por_alias,
    la_pesca_deportiva_es_privada_aunque_no_lo_diga,
    las_dos_estaciones_de_corcovado_son_distintas,
    el_discovery_scuba_no_es_el_buceo_de_isla,
    los_transportes_no_son_tours,
    cada_codigo_tiene_nombre_legible,
    los_tours_nuevos_entran_al_catalogo,
    todo_tour_reconocido_existe_en_el_catalogo,
]


if __name__ == "__main__":
    sys.exit(comun.correr("codigos de tours", PRUEBAS))
