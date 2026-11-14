"""Las notas que alguien escribe A MANO sobre la hoja de operacion.

Lo pidio el lodge: «que tambien sea editable en la parte de notas, ahi mismo [en la
previsualizacion] ... que sea capaz de guardar todo lo editado en fechas posteriores --
las notas escritas ahi permanecen solo ahi, no en ninguna otra parte de la app».

Lo que estas pruebas fijan, que es lo que falla CALLADO:

  1. UNA NOTA ES DE UN DIA. Si se pegara a la reserva, lo escrito para el martes saldria
     tambien el miercoles y el jueves, en las hojas de todos los dias que el huesped esta
     alojado.
  2. UNA NOTA ES DE UNA RESERVA, no de una habitacion. El cuarto se reutiliza: el dia que
     cambia de huesped, el que SALE y el que ENTRA tienen el mismo numero, y una nota
     pegada al numero saldria en los dos renglones -- la mitad de las veces en el
     equivocado.
  3. NO VIVE EN NINGUNA OTRA PARTE, y en particular la carga de Opera no la toca. Si se
     hubiera escrito encima de la nota de la reserva, la siguiente importacion se la
     llevaria por delante sin que nadie se entere.
  4. LO ESCRITO A MANO VA DELANTE Y ENTERO. La casilla recorta a 110 caracteres lo que
     viene de Opera; si el recorte alcanzara tambien a lo escrito hoy, se perderia justo
     lo que alguien decidio añadir.
  5. LA HOJA SIGUE CABIENDO EN UNA PAGINA. La hoja se fotografia para mandarla al grupo y
     nadie manda dos fotos.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun                                     # noqa: E402
from comun import cargar, reserva                # noqa: E402

HOY = datetime.date.today()
MANANA = HOY + datetime.timedelta(days=1)
EN_UN_MES = HOY + datetime.timedelta(days=30)


def ddmmyy(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def _paginas(buf):
    import pdfplumber
    buf.seek(0)
    with pdfplumber.open(buf) as pdf:
        return len(pdf.pages), "\n".join((p.extract_text() or "") for p in pdf.pages)


def _celdas(buf):
    """Todo el texto de un Excel, para buscar dentro sin saber en que fila cayo."""
    from openpyxl import load_workbook
    buf.seek(0)
    ws = load_workbook(buf).active
    return [str(c.value) for fila in ws.iter_rows() for c in fila if c.value is not None]


def _hoja(conn, fecha):
    import hoja_dia
    import main
    return hoja_dia.definicion(conn, fecha, main._datos_del_resumen(fecha))


def _sembrar(conn):
    """El caso que importa: dos reservas en LA MISMA habitacion el mismo dia.

    Una se va hoy y la otra llega hoy -- 55 veces en los proximos cuatro meses, segun la
    base del lodge. Es el dia en que una nota pegada al numero de cuarto se equivoca de
    huesped.
    """
    lote = [
        dict(reserva(91001, "12", ddmmyy(HOY), ddmmyy(HOY + datetime.timedelta(days=3)),
                     adl=2), punto_entrada="Sierpe"),
        dict(reserva(91002, "12", ddmmyy(HOY - datetime.timedelta(days=2)), ddmmyy(HOY),
                     adl=2, estado="EN CASA"), punto_salida="Drake"),
        dict(reserva(91003, "07", ddmmyy(HOY - datetime.timedelta(days=1)),
                     ddmmyy(HOY + datetime.timedelta(days=4)), adl=2, estado="EN CASA")),
    ]
    cargar(lote, vistas=lote)
    return lote


# ---------------------------------------------------------------------------
# De un dia y de una reserva
# ---------------------------------------------------------------------------

def la_nota_es_de_un_dia_y_no_se_repite_en_los_demas(c):
    """Si se pegara a la reserva, lo escrito para hoy saldria en las hojas de los cuatro
    dias que el huesped esta alojado. Y al reves: la nota de mañana no es de hoy."""
    import notas_hoja
    conn = comun.base_limpia()
    _sembrar(conn)

    notas_hoja.guardar_varias(conn, HOY.isoformat(),
                              filas={"91003": "Cumpleanos: queque a las 7"},
                              usuario="pruebas")
    notas_hoja.guardar_varias(conn, MANANA.isoformat(),
                              filas={"91003": "Pide taxi para el aeropuerto"},
                              usuario="pruebas")

    hoy = {f["conf_no"]: f.get("nota_mano") for f in _hoja(conn, HOY.isoformat())["filas"]}
    man = {f["conf_no"]: f.get("nota_mano")
           for f in _hoja(conn, MANANA.isoformat())["filas"]}
    c.igual(hoy.get("91003"), "Cumpleanos: queque a las 7", "la de hoy sale hoy")
    c.igual(man.get("91003"), "Pide taxi para el aeropuerto", "la de mañana sale mañana")
    c.cierto("queque" not in (man.get("91003") or ""), "y la de hoy NO sale mañana")

    pasado = _hoja(conn, (HOY + datetime.timedelta(days=2)).isoformat())
    c.igual([f.get("nota_mano") for f in pasado["filas"] if f.get("nota_mano")], [],
            "ni en los demas dias que el huesped esta alojado")
    conn.close()


def la_nota_es_de_la_reserva_y_no_del_numero_de_cuarto(c):
    """EL FALLO QUE ESTA PRUEBA EVITA NO DA ERROR: pone la nota en el renglon del
    huesped equivocado.

    Hoy la 12 la dejan y la toman: 91002 se va y 91001 llega. Son dos renglones con el
    mismo numero en la misma hoja.
    """
    import notas_hoja
    conn = comun.base_limpia()
    _sembrar(conn)
    notas_hoja.guardar_varias(conn, HOY.isoformat(),
                              filas={"91001": "Llega en silla de ruedas"},
                              usuario="pruebas")

    filas = {f["conf_no"]: f for f in _hoja(conn, HOY.isoformat())["filas"]}
    c.igual(filas["91001"]["hab"], "12", "quien llega esta en la 12")
    c.igual(filas["91002"]["hab"], "12", "y quien se va tambien")
    c.igual(filas["91001"].get("nota_mano"), "Llega en silla de ruedas",
            "la nota cae en el renglon de quien llega")
    c.igual(filas["91002"].get("nota_mano"), "",
            "y NO en el de quien se va, que comparte cuarto")
    conn.close()


def la_carga_de_opera_no_se_lleva_por_delante_lo_escrito(c):
    """La regla que pidio el lodge: «permanecen solo ahi, no en ninguna otra parte».

    Es lo que separa esto de escribir en la nota de la reserva. Esa columna la reescribe
    cada importacion, asi que lo que alguien escribio el lunes desapareceria el martes a
    las seis de la mañana, sin un error y sin que nadie lo note hasta buscarlo.
    """
    import notas_hoja
    conn = comun.base_limpia()
    lote = _sembrar(conn)
    notas_hoja.guardar_varias(conn, HOY.isoformat(),
                              dia="Viene el inspector del SINAC a las 10",
                              filas={"91001": "Llega en silla de ruedas"},
                              usuario="pruebas")

    # La reserva no guarda nada de esto.
    r = conn.execute("""SELECT nota_ingreso, nota_salida, nota_en_casa, notas_libres,
                               notas_operacion
                          FROM reserva WHERE conf_no = '91001'""").fetchone()
    for campo in ("nota_ingreso", "nota_salida", "nota_en_casa", "notas_libres",
                  "notas_operacion"):
        c.cierto("silla de ruedas" not in (r[campo] or ""),
                 f"la reserva no guarda la nota en «{campo}»")

    # Y otra importacion completa no la toca.
    cargar(lote, vistas=lote)
    d = _hoja(conn, HOY.isoformat())
    filas = {f["conf_no"]: f for f in d["filas"]}
    c.igual(filas["91001"].get("nota_mano"), "Llega en silla de ruedas",
            "despues de volver a importar, la nota sigue ahi")
    c.igual(d.get("nota_dia"), "Viene el inspector del SINAC a las 10",
            "y la del dia tambien")
    conn.close()


def se_puede_escribir_para_un_dia_que_todavia_no_llego(c):
    """Lo pidio asi: «que sea capaz de guardar todo lo editado en fechas posteriores».

    No es un detalle: la hoja se prepara el dia antes, y lo que se escribe para dentro de
    un mes tiene que seguir ahi cuando llegue ese dia.
    """
    import notas_hoja
    conn = comun.base_limpia()
    lote = [dict(reserva(91010, "05", ddmmyy(EN_UN_MES),
                         ddmmyy(EN_UN_MES + datetime.timedelta(days=2)), adl=2))]
    cargar(lote, vistas=lote)
    notas_hoja.guardar_varias(conn, EN_UN_MES.isoformat(),
                              dia="Ese dia cierra el muelle de Sierpe por mantenimiento",
                              filas={"91010": "Luna de miel: flores en la habitacion"},
                              usuario="pruebas")

    d = _hoja(conn, EN_UN_MES.isoformat())
    c.igual(d.get("nota_dia"),
            "Ese dia cierra el muelle de Sierpe por mantenimiento",
            "la nota del dia de dentro de un mes se guarda")
    c.igual([f.get("nota_mano") for f in d["filas"] if f["conf_no"] == "91010"],
            ["Luna de miel: flores en la habitacion"],
            "y la del renglon tambien")
    _, texto = _paginas(__import__("hoja_dia").pdf(d))
    c.cierto("Luna de miel" in texto, "y salen en la hoja de ese dia")
    conn.close()


# ---------------------------------------------------------------------------
# Como se escribe en la casilla
# ---------------------------------------------------------------------------

def lo_escrito_a_mano_va_delante_y_no_lo_recorta_el_tope(c):
    """El recorte a 110 existe para que la nota de Opera no se coma el renglon, y alcanza
    SOLO a esa parte. Lo escrito a mano va delante porque es lo que no esta en ningun
    otro sitio -- y porque es lo primero que se lee."""
    import hoja_dia
    larga = "OPERA " + "x" * 200
    f = {"nota_mano": "AVISAR AL MUELLE", "notas": larga}
    texto = hoja_dia.nota_de_la_fila(f)
    c.cierto(texto.startswith("AVISAR AL MUELLE · "), "lo de la mano va primero")
    c.igual(len(texto), len("AVISAR AL MUELLE · ") + 110,
            "y el recorte alcanza solo a lo que trae Opera")

    marcado = hoja_dia._notas_con_marcado(f, lambda x: x)
    c.cierto(marcado.startswith("<b>AVISAR AL MUELLE</b>"),
             "en el PDF sale en negrita, para distinguir quien lo escribio")

    # Sin nada escrito a mano, la casilla es exactamente la de siempre.
    c.igual(hoja_dia.nota_de_la_fila({"notas": "VUELO RZ1116"}), "VUELO RZ1116",
            "sin nota a mano, la casilla no cambia")
    c.igual(hoja_dia.nota_de_la_fila({"nota_mano": "", "notas": ""}), "",
            "y vacia sigue vacia, sin separadores colgando")


def el_texto_se_limpia_y_se_recorta_al_guardar(c):
    """Un salto de linea dentro de una casilla de tabla no se ve como un renglon nuevo:
    se ve como un espacio raro, y en el Excel descuadra la altura de toda la fila. Y un
    texto sin tope obligaria a encoger la letra de la hoja entera por un solo cuarto."""
    import notas_hoja
    conn = comun.base_limpia()
    guardado = notas_hoja.guardar(conn, HOY.isoformat(), "91001",
                                  "  dos\nrenglones   y   espacios  ", "pruebas")
    c.igual(guardado, "dos renglones y espacios", "se limpia al guardar")
    largo = notas_hoja.guardar(conn, HOY.isoformat(), "91002", "y" * 500, "pruebas")
    c.igual(len(largo), notas_hoja.LIMITE_FILA, "y se recorta al tope del renglon")
    dia = notas_hoja.guardar(conn, HOY.isoformat(), notas_hoja.DIA, "z" * 2000, "pruebas")
    c.igual(len(dia), notas_hoja.LIMITE_DIA, "con su propio tope para la del dia")
    conn.commit()

    vacia = notas_hoja.guardar(conn, HOY.isoformat(), "91001", "   ", "pruebas")
    c.igual(vacia, "", "vaciarla devuelve vacio")
    c.igual(notas_hoja.leer(conn, HOY.isoformat())["filas"].get("91001"), None,
            "y BORRA la fila, en vez de dejar uno que no dice nada")
    conn.close()


# ---------------------------------------------------------------------------
# En el papel
# ---------------------------------------------------------------------------

def las_notas_salen_en_la_hoja_y_siguen_cabiendo_en_una_pagina(c):
    """La hoja se fotografia para mandarla al grupo y nadie manda dos fotos. La caja de
    notas entra en la MEDIDA, no se pega despues: pegandola fuera, un dia con nota larga
    se iria a la segunda pagina con la hoja ya decidida."""
    import hoja_dia
    import notas_hoja
    conn = comun.base_limpia()
    _sembrar(conn)
    notas_hoja.guardar_varias(
        conn, HOY.isoformat(),
        dia=("Viene el inspector del SINAC a las 10 y hay que tener listos los tiquetes "
             "de los tres grupos del parque, mas la lista de pasaportes."),
        filas={"91001": "Llega en silla de ruedas, avisar al muelle",
               "91003": "Cumpleanos: queque a las 7"},
        usuario="pruebas")
    d = _hoja(conn, HOY.isoformat())

    paginas, texto = _paginas(hoja_dia.pdf(d))
    c.igual(paginas, 1, "la hoja con notas sigue siendo UNA pagina")
    c.cierto("NOTAS DEL" in texto, "con su caja al pie")
    c.cierto("inspector del SINAC" in texto, "la nota del dia esta")
    c.cierto("silla de ruedas" in texto, "y la del renglon tambien")

    celdas = _celdas(hoja_dia.excel(d))
    c.cierto(any("inspector del SINAC" in x for x in celdas),
             "el Excel dice lo mismo que el PDF: la nota del dia")
    c.cierto(any("silla de ruedas" in x for x in celdas),
             "y la del renglon, en su columna de NOTAS")
    conn.close()


def sin_notas_la_hoja_es_exactamente_la_de_siempre(c):
    """Una caja con el titulo y nada dentro ocuparia hoja para decir que no hay nada que
    decir -- y en una hoja que encoge hasta caber, eso se paga en tamaño de letra."""
    import hoja_dia
    conn = comun.base_limpia()
    _sembrar(conn)
    d = _hoja(conn, HOY.isoformat())
    c.igual(d.get("nota_dia"), "", "sin notas, la definicion trae la del dia vacia")
    _, texto = _paginas(hoja_dia.pdf(d))
    c.cierto("NOTAS DEL DÍA" not in texto, "y el papel no dibuja la caja")
    conn.close()


def el_rango_lleva_las_notas_de_cada_dia_con_su_fecha(c):
    """Sueltas no se entenderian: en una hoja de quince dias, «llega el inspector» sin
    fecha no dice que dia hay que esperarlo.

    Y UN RENGLON CON NOTA A MANO NO SE CAE del resumen aunque solo este alojado: el rango
    deja fuera a quien no entra ni sale, pero si alguien escribio algo sobre ese renglon
    es justo lo que no esta en ningun otro sitio.
    """
    import hoja_dia
    import notas_hoja
    conn = comun.base_limpia()
    _sembrar(conn)
    notas_hoja.guardar_varias(conn, MANANA.isoformat(),
                              dia="Llega el inspector",
                              filas={"91003": "Cumpleanos: queque a las 7"},
                              usuario="pruebas")
    dias = [_hoja(conn, (HOY + datetime.timedelta(days=i)).isoformat())
            for i in range(3)]
    d = hoja_dia.definicion_rango(dias)

    c.igual([n for _, n in d["notas_dia"]], ["Llega el inspector"],
            "el rango junta las notas del dia de sus dias")
    c.igual(d["notas_dia"][0][0], hoja_dia._dmy(MANANA.isoformat()),
            "cada una con su fecha delante")

    _, texto = _paginas(hoja_dia.pdf_rango(d))
    c.cierto("NOTAS DE CADA" in texto, "y salen en una caja al final de la hoja")
    c.cierto("Llega el inspector" in texto, "con su texto")
    c.cierto("queque" in texto,
             "y el renglon de quien solo esta alojado sale PORQUE tiene nota a mano")

    # El que no tiene nota sigue sin aparecer: el rango es un resumen.
    en_casa = [f for f in d["filas"] if f["estado"] == "EN CASA"]
    c.igual(len(en_casa), 1, "los demas EN CASA siguen fuera del resumen")
    c.igual([t for t in d["movimientos"] if t[0] == "EN CASA"], [],
            "y no se cuenta como movimiento, porque no se movio")

    celdas = _celdas(hoja_dia.excel_rango(d))
    c.cierto(any("Llega el inspector" in x for x in celdas),
             "el Excel del rango dice lo mismo")
    conn.close()


# ---------------------------------------------------------------------------
# Lo que ve la pantalla
# ---------------------------------------------------------------------------

def la_pantalla_recibe_los_renglones_del_dia_para_escribir(c):
    """La caja de notas tiene que enseñar una casilla por habitacion, con el nombre del
    huesped y con lo que la hoja YA dice de el -- si no, se escribe a mano lo que la hoja
    iba a poner sola. Y quien la abre puede estar mirando una fecha que la pantalla de
    atras no ha cargado nunca."""
    import main
    import notas_hoja
    conn = comun.base_limpia()
    _sembrar(conn)
    notas_hoja.guardar_varias(conn, HOY.isoformat(),
                              filas={"91001": "Llega en silla de ruedas"},
                              usuario="pruebas")
    conn.close()

    d = main._notas_de_la_hoja(HOY.isoformat())
    porconf = {f["conf_no"]: f for f in d["filas"]}
    c.igual(sorted(porconf), ["91001", "91002", "91003"],
            "vienen los tres renglones del dia")
    c.cierto(all(f["huesped"] and f["hab"] and f["estado"] for f in d["filas"]),
             "cada uno con su habitacion, su huesped y su estado")
    c.igual(porconf["91001"]["nota"], "Llega en silla de ruedas",
            "con lo que ya estaba escrito")
    c.cierto("VUELO" in porconf["91002"]["auto"] or porconf["91002"]["auto"] == "",
             "y con lo que la hoja ya dice de ese renglon")
    c.igual(d["limite_fila"], notas_hoja.LIMITE_FILA,
            "y los topes, para que la pantalla no deje escribir de mas")


def una_nota_sin_renglon_se_enseña_en_vez_de_desaparecer(c):
    """La reserva se cancelo, se movio de dia o cambio de numero. Lo escrito sigue
    guardado pero ya no sale en la hoja: callarlo haria pensar que no se guardo."""
    import main
    import notas_hoja
    conn = comun.base_limpia()
    _sembrar(conn)
    notas_hoja.guardar_varias(conn, HOY.isoformat(),
                              filas={"99999": "De una reserva que ya no esta"},
                              usuario="pruebas")
    conn.close()

    d = main._notas_de_la_hoja(HOY.isoformat())
    c.igual([h["texto"] for h in d["huerfanas"]], ["De una reserva que ya no esta"],
            "la nota sin renglon se devuelve aparte")
    c.cierto(all(f["nota"] != "De una reserva que ya no esta" for f in d["filas"]),
             "y no se cuela en ningun renglon de la hoja")


PRUEBAS = [
    la_nota_es_de_un_dia_y_no_se_repite_en_los_demas,
    la_nota_es_de_la_reserva_y_no_del_numero_de_cuarto,
    la_carga_de_opera_no_se_lleva_por_delante_lo_escrito,
    se_puede_escribir_para_un_dia_que_todavia_no_llego,
    lo_escrito_a_mano_va_delante_y_no_lo_recorta_el_tope,
    el_texto_se_limpia_y_se_recorta_al_guardar,
    las_notas_salen_en_la_hoja_y_siguen_cabiendo_en_una_pagina,
    sin_notas_la_hoja_es_exactamente_la_de_siempre,
    el_rango_lleva_las_notas_de_cada_dia_con_su_fecha,
    la_pantalla_recibe_los_renglones_del_dia_para_escribir,
    una_nota_sin_renglon_se_enseña_en_vez_de_desaparecer,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Notas escritas a mano sobre la hoja", PRUEBAS))
