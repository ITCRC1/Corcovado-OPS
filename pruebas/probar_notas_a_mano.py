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
USUARIO = {"usuario": "pruebas", "username": "pruebas", "rol": "ADMIN"}


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
    """El recorte existe para que la nota libre de Opera no se coma el renglon, y alcanza
    SOLO a esa parte. Lo escrito a mano va delante porque es lo que no esta en ningun
    otro sitio -- y porque es lo primero que se lee."""
    import hoja_dia
    larga = "OPERA " + "x" * 200
    auto = hoja_dia._componer_nota({"nota_opera": larga})
    c.igual(len(auto), hoja_dia.TOPE_NOTA_AUTO,
            "la nota libre de Opera se recorta a su tope")

    f = {"nota_mano": "AVISAR AL MUELLE", "notas": auto}
    texto = hoja_dia.nota_de_la_fila(f)
    c.cierto(texto.startswith("AVISAR AL MUELLE · "), "lo de la mano va primero")
    c.igual(len(texto), len("AVISAR AL MUELLE · ") + hoja_dia.TOPE_NOTA_AUTO,
            "y lo escrito a mano no entra en el recorte")

    marcado = hoja_dia._notas_con_marcado(f, lambda x: x)
    c.cierto(marcado.startswith("<b>AVISAR AL MUELLE</b>"),
             "en el PDF sale en negrita, para distinguir quien lo escribio")

    # Sin nada escrito a mano, la casilla es exactamente la de siempre.
    c.igual(hoja_dia.nota_de_la_fila({"notas": "VUELO RZ1116"}), "VUELO RZ1116",
            "sin nota a mano, la casilla no cambia")
    c.igual(hoja_dia.nota_de_la_fila({"nota_mano": "", "notas": ""}), "",
            "y vacia sigue vacia, sin separadores colgando")


def la_nota_del_sistema_se_puede_corregir(c):
    """LO PIDIO EL LODGE: «tambien debes habilitar poder modificar las notas ya
    existentes del sistema».

    Hasta ahora la nota a mano solo se podia AÑADIR: la que trae Opera se enseñaba en
    gris, de solo lectura. Una frase equivocada se quedaba ahi y lo unico que se podia
    hacer era escribir la correccion al lado — dejando el renglon diciendo las dos cosas,
    la buena y la mala, en el papel que alguien lee en el muelle.

    Con la marca puesta, en la casilla sale SOLO lo que escribio la persona.

    LA RESERVA NO SE TOCA, que es la regla entera de este modulo: lo que cambia es lo que
    sale en ESTA hoja y ESTE dia. Escribir encima de la nota de la reserva la borraria en
    la siguiente carga de Opera, y ademas saldria los otros cuatro dias de la estadia.
    """
    import hoja_dia
    import notas_hoja

    f = {"nota_mano": "SALE A LAS 6, NO A LAS 7", "notas": "VUELO RZ1069 · avión 9:00"}
    c.igual(hoja_dia.nota_de_la_fila(dict(f, nota_mano_reemplaza=False)),
            "SALE A LAS 6, NO A LAS 7 · VUELO RZ1069 · avión 9:00",
            "sin la marca, lo escrito va DELANTE, como siempre")
    c.igual(hoja_dia.nota_de_la_fila(dict(f, nota_mano_reemplaza=True)),
            "SALE A LAS 6, NO A LAS 7",
            "con la marca, sustituye a lo que la hoja decia")

    # Una marca sin texto no deja la casilla en blanco: sin nada escrito no hay nada que
    # sustituir, y el renglon tiene que seguir diciendo lo suyo.
    c.igual(hoja_dia.nota_de_la_fila({"nota_mano": "", "notas": "VUELO RZ1069",
                                      "nota_mano_reemplaza": True}),
            "VUELO RZ1069", "una marca sin texto no borra el renglon")

    # Y de punta a punta, por donde se guarda de verdad.
    comun.base_limpia().close()
    cargar([reserva("93001", "07", ddmmyy(HOY), ddmmyy(MANANA), estado="EN CASA")])
    conn = comun.conexion()
    notas_hoja.guardar_varias(conn, HOY.isoformat(),
                              filas={"93001": "LO CORREGIDO"},
                              reemplazan={"93001"}, usuario="pruebas")
    leido = notas_hoja.leer(conn, HOY.isoformat())
    c.igual(leido["filas"]["93001"], "LO CORREGIDO", "se guarda el texto")
    c.cierto("93001" in leido["reemplazan"], "y la marca de que sustituye")

    notas_hoja.guardar_varias(conn, HOY.isoformat(), filas={"93001": "LO CORREGIDO"},
                              reemplazan=set(), usuario="pruebas")
    c.cierto("93001" not in notas_hoja.leer(conn, HOY.isoformat())["reemplazan"],
             "quitar la marca devuelve el renglon a lo de siempre")

    # BORRAR LA NOTA DEVUELVE EL RENGLON A LO AUTOMATICO, marca incluida. Si la marca
    # sobreviviera, el renglon se quedaria con la casilla en blanco para siempre y sin
    # nada que tocar para recuperarla.
    notas_hoja.guardar_varias(conn, HOY.isoformat(), filas={"93001": "X"},
                              reemplazan={"93001"}, usuario="pruebas")
    notas_hoja.guardar_varias(conn, HOY.isoformat(), filas={"93001": ""},
                              reemplazan={"93001"}, usuario="pruebas")
    vacio = notas_hoja.leer(conn, HOY.isoformat())
    c.cierto("93001" not in vacio["filas"], "borrar el texto borra la nota")
    c.cierto("93001" not in vacio["reemplazan"], "y se lleva la marca con ella")
    conn.close()


def la_hoja_imprime_la_nota_corregida(c):
    """El camino completo: lo corregido es lo que sale en la hoja, y lo que decia el
    sistema NO. Probar solo nota_de_la_fila se detendria antes de la hoja."""
    import hoja_dia
    import main
    import notas_hoja

    comun.base_limpia().close()
    cargar([reserva("93101", "09", ddmmyy(HOY), ddmmyy(MANANA), estado="EN CASA")])

    conn = comun.conexion()
    # La nota se escribe en la reserva como la deja Opera, para comprobar despues que
    # corregir la hoja NO la toca.
    conn.execute("UPDATE reserva SET nota_salida = ? WHERE conf_no = '93101'",
                 ("REVISAR CON RECEPCION",))
    conn.commit()
    notas_hoja.guardar_varias(conn, HOY.isoformat(),
                              filas={"93101": "LA VERSION BUENA"},
                              reemplazan={"93101"}, usuario="pruebas")
    d = hoja_dia.definicion(conn, HOY.isoformat(),
                            main._datos_del_resumen(HOY.isoformat()))
    conn.close()
    nueva = hoja_dia.nota_de_la_fila(
        [f for f in d["filas"] if f["conf_no"] == "93101"][0])
    c.igual(nueva, "LA VERSION BUENA", "la hoja imprime SOLO lo corregido")

    # La RESERVA no se toco: la nota sigue en la base tal como vino de Opera.
    conn = comun.conexion()
    guardado = conn.execute(
        "SELECT nota_salida FROM reserva WHERE conf_no = '93101'").fetchone()[0]
    conn.close()
    c.igual(guardado, "REVISAR CON RECEPCION",
            "la nota de la reserva queda intacta: solo cambia lo que sale en la hoja")

    # Y la pantalla recibe las dos cosas para poder dibujar el boton.
    datos = main._notas_de_la_hoja(HOY.isoformat())
    suya = [f for f in datos["filas"] if f["conf_no"] == "93101"][0]
    c.igual(suya["reemplaza"], True, "la pantalla sabe que ese renglon esta corregido")
    c.cierto(suya["auto"], "y sigue recibiendo lo que decia el sistema, para enseñarlo")

    # POR EL ENDPOINT, que es por donde entra desde la pantalla. Probar solo
    # guardar_varias se detiene un paso antes: la marca viaja en el cuerpo del POST, y si
    # ahi se perdiera, todo lo de abajo seguiria pasando y el boton no haria nada.
    respuesta = main.notas_hoja_guardar(
        {"fecha": HOY.isoformat(), "filas": {"93101": "DESDE LA PANTALLA"},
         "reemplazan": ["93101"]}, user=USUARIO)
    fila = [f for f in respuesta["filas"] if f["conf_no"] == "93101"][0]
    c.igual(fila["nota"], "DESDE LA PANTALLA", "el endpoint guarda el texto")
    c.igual(fila["reemplaza"], True, "y la marca que viene con el")

    # Y sin la marca en el cuerpo, el mismo texto vuelve a ir delante.
    respuesta = main.notas_hoja_guardar(
        {"fecha": HOY.isoformat(), "filas": {"93101": "DESDE LA PANTALLA"}},
        user=USUARIO)
    fila = [f for f in respuesta["filas"] if f["conf_no"] == "93101"][0]
    c.igual(fila["reemplaza"], False, "sin la marca, el endpoint no la inventa")


def el_PDF_tambien_sustituye_la_nota_del_sistema(c):
    """LO REPORTO EL LODGE: «cuando se agrega una nota sobre la que ya existe del
    sistema, eliminar la del sistema, que no se refleje mas».

    La casilla NOTAS se armaba en DOS sitios —en texto plano para los Excel y con
    negritas para los PDF— y cada uno tenia escrita su propia version de la regla. El
    plano aprendio a sustituir la nota corregida; el de los PDF no:

        Excel : «SALE POR SIERPE, NO DRAKE»
        PDF   : «SALE POR SIERPE, NO DRAKE · VUELO RZ1071 @1:00 PM»

    O sea el renglon diciendo las dos cosas —la buena y la que se vino a corregir— que es
    exactamente lo que la correccion existe para evitar; y encima solo en el papel, que es
    el que se mira en la previsualizacion y se manda por WhatsApp al muelle.

    LA PRUEBA DE ANTES SE DETENIA UN PASO ANTES: comprobaba `nota_de_la_fila`, que ya lo
    hacia bien. Esta llega hasta el PDF de verdad.

    Las palabras son inventadas a proposito: en una columna de 46 mm el texto se parte en
    varias lineas, y buscar una frase no la encontraria; una palabra que no aparezca en
    ningun otro sitio de la hoja, si.
    """
    import hoja_dia
    import notas_hoja

    conn = comun.base_limpia()
    cargar([reserva("93201", "11", ddmmyy(HOY), ddmmyy(MANANA), estado="EN CASA")])
    conn.close()

    conn = comun.conexion()
    # La reserva LLEGA hoy, asi que el renglon es ENTRA y la nota que la hoja enseña es
    # la de ingreso: cada dia enseña lo suyo. Ver _nota_del_estado.
    conn.execute("UPDATE reserva SET nota_ingreso = ? WHERE conf_no = '93201'",
                 ("NOTAVIEJA DEL SISTEMA",))
    conn.commit()
    notas_hoja.guardar_varias(conn, HOY.isoformat(), filas={"93201": "NOTACORREGIDA"},
                              reemplazan={"93201"}, usuario="pruebas")
    d = _hoja(conn, HOY.isoformat())
    conn.close()

    fila = [f for f in d["filas"] if f["conf_no"] == "93201"][0]
    c.cierto("NOTAVIEJA" in (fila.get("notas") or ""),
             "el sistema SI tiene su nota: lo que se prueba es que no se imprima")

    _, texto = _paginas(hoja_dia.pdf(d))
    c.cierto("NOTACORREGIDA" in texto, "el PDF imprime lo corregido")
    c.cierto("NOTAVIEJA" not in texto, "y YA NO imprime lo que decia el sistema")

    celdas = _celdas(hoja_dia.excel(d))
    c.cierto(any("NOTACORREGIDA" in x for x in celdas), "el Excel dice lo mismo")
    c.cierto(not any("NOTAVIEJA" in x for x in celdas), "y tampoco el viejo")

    # SIN LA MARCA SIGUEN SALIENDO LAS DOS. Añadir no es corregir: quien escribe al lado
    # de la nota del sistema quiere sumar algo, y borrarle el vuelo seria peor que el
    # fallo que se vino a arreglar.
    conn = comun.conexion()
    notas_hoja.guardar_varias(conn, HOY.isoformat(), filas={"93201": "NOTACORREGIDA"},
                              reemplazan=set(), usuario="pruebas")
    d = _hoja(conn, HOY.isoformat())
    conn.close()
    _, texto = _paginas(hoja_dia.pdf(d))
    c.cierto("NOTACORREGIDA" in texto and "NOTAVIEJA" in texto,
             "sin la marca, el PDF sigue enseñando las dos")


def las_dos_formas_de_escribir_la_casilla_dicen_lo_mismo(c):
    """La regla vive en UN sitio y las dos salidas solo la visten.

    Esta es la comprobacion que impide que vuelvan a separarse. Es la cuarta vez en este
    sistema que una regla escrita dos veces acaba diciendo dos cosas: el muelle que
    repartia «si no es Sierpe, es Drake», la hora del Claro que una pantalla sabia y la
    otra no, y el BT que una tabla pintaba como salida. Comparando las dos salidas sobre
    los mismos casos, separarlas vuelve a fallar aqui."""
    import hoja_dia

    casos = [
        ({"nota_mano": "A MANO", "notas": "DEL SISTEMA"},
         "añadida: salen las dos"),
        ({"nota_mano": "A MANO", "notas": "DEL SISTEMA", "nota_mano_reemplaza": True},
         "corregida: sale solo la de la mano"),
        ({"nota_mano": "", "notas": "DEL SISTEMA", "nota_mano_reemplaza": True},
         "marca sin texto: el renglon conserva lo suyo"),
        ({"nota_mano": "A MANO", "notas": "", "nota_mano_reemplaza": True},
         "sin nota del sistema que sustituir"),
        ({"nota_mano": "", "notas": ""},
         "vacia: sin separadores colgando"),
    ]
    for f, que in casos:
        plano = hoja_dia.nota_de_la_fila(f)
        marcado = hoja_dia._notas_con_marcado(f, lambda x: x)
        c.igual(marcado.replace("<b>", "").replace("</b>", ""), plano,
                f"el Excel y el PDF dicen lo mismo — {que}")

    # Y la negrita sigue distinguiendo quien escribio que, que es para lo que esta.
    c.igual(hoja_dia._notas_con_marcado(
        {"nota_mano": "A MANO", "notas": "DEL SISTEMA"}, lambda x: x),
        "<b>A MANO</b> · DEL SISTEMA", "con lo de la mano en negrita")


def la_pantalla_deja_corregir_la_nota_del_sistema(c):
    """El boton tiene que estar donde se lee la nota, no en otra pantalla."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    c.cierto("editarNotaDelSistema(" in pantalla, "existe el boton")
    i = pantalla.find("function editarNotaDelSistema(")
    c.cierto(i > 0, "y su manejador")
    fn = pantalla[i:i + 1600]
    c.cierto("f.auto" in fn, "trae la nota del sistema al cuadro para corregirla")
    c.cierto("f.reemplaza = true" in fn, "y marca el renglon")
    c.cierto('f.nota = ""' in fn,
             "volver a la del sistema borra lo escrito: dejarlo lo pondria DELANTE de "
             "la nota que se queria corregir, o sea las dos cosas a la vez")
    j = pantalla.find("async function guardarNotasDeLaHoja")
    c.cierto("reemplazan" in pantalla[j:j + 700], "y se manda al guardar")


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


def la_hoja_dice_cuantos_de_los_pax_son_ninos(c):
    """LO PIDIO EL LODGE con la reserva 601049123: la de Opera dice «2 adultos, 2 niños
    (4, 10)» y en la hoja los cuatro se leian igual, como «4 pax».

    Cambia cosas concretas: el chaleco que se sube al bote, la porcion que manda cocina y
    que tour pueden hacer. Va pegado al nombre y no en la columna de PAX porque esa mide
    8 mm —solo cabe el numero— y la del huesped tiene 54.
    """
    import hoja_dia
    conn = comun.base_limpia()
    lote = [
        dict(reserva(601049123, "12", ddmmyy(HOY),
                     ddmmyy(HOY + datetime.timedelta(days=5)), adl=2, chl=2)),
        dict(reserva(601049124, "14", ddmmyy(HOY),
                     ddmmyy(HOY + datetime.timedelta(days=3)), adl=2, chl=0)),
        dict(reserva(601049125, "16", ddmmyy(HOY),
                     ddmmyy(HOY + datetime.timedelta(days=3)), adl=2, chl=1)),
    ]
    cargar(lote, vistas=lote)

    d = _hoja(conn, HOY.isoformat())
    conn.close()
    por_hab = {f["hab"]: f for f in d["filas"]}
    c.igual(por_hab["12"]["pax"], 4, "el pax sigue siendo el total de la habitacion")
    c.igual(por_hab["12"]["ninos"], 2, "y se sabe cuantos de esos son niños")
    c.cierto("2 niños" in por_hab["12"]["huesped"],
             "la hoja lo dice junto al nombre")
    c.cierto("1 niño" in por_hab["16"]["huesped"] and "niños" not in por_hab["16"]["huesped"],
             "y en singular cuando es uno solo")
    c.cierto("niño" not in por_hab["14"]["huesped"],
             "la que viaja sin niños no dice nada: no se agrega ruido a la hoja")

    # Y llega al PDF, que es lo que se reparte por WhatsApp.
    buf = hoja_dia.pdf(d)
    _paginas_n, texto = _paginas(buf)
    c.cierto("2 niños" in texto, "sale impreso en la hoja del dia")


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
    la_nota_del_sistema_se_puede_corregir,
    la_hoja_imprime_la_nota_corregida,
    el_PDF_tambien_sustituye_la_nota_del_sistema,
    las_dos_formas_de_escribir_la_casilla_dicen_lo_mismo,
    la_pantalla_deja_corregir_la_nota_del_sistema,
    el_texto_se_limpia_y_se_recorta_al_guardar,
    las_notas_salen_en_la_hoja_y_siguen_cabiendo_en_una_pagina,
    sin_notas_la_hoja_es_exactamente_la_de_siempre,
    el_rango_lleva_las_notas_de_cada_dia_con_su_fecha,
    la_pantalla_recibe_los_renglones_del_dia_para_escribir,
    la_hoja_dice_cuantos_de_los_pax_son_ninos,
    una_nota_sin_renglon_se_enseña_en_vez_de_desaparecer,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Notas escritas a mano sobre la hoja", PRUEBAS))
