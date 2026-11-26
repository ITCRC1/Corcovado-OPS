"""Proveeduria: el inventario que reemplaza la hoja de calculo del lodge.

POR QUE ESTA SUITE. Lo que se esta sustituyendo es una hoja de 19 pestañas donde el stock
sale de SUMIFS sobre un historial de 11.506 movimientos. Casi todo lo que puede salir mal
aqui falla EN SILENCIO: el inventario no da error, simplemente dice otro numero. Y un
numero de bodega equivocado se descubre el dia que falta el producto.

Lo que hay que fijar, y por que cada cosa es cara si se rompe:

  · EL STOCK ES UNA RESTA, NO UN DATO. Guardado en una columna, el dia que alguien
    corrija un movimiento viejo la columna y el libro dirian cosas distintas.
  · UNA ORDEN PEDIDA NO ES MERCADERIA. Contar los ingresos no recibidos hincha el
    inventario y hace que no se pida lo que si hace falta.
  · CADA DEPARTAMENTO LLEVA SU BODEGA, y el general NO es la lista de todas pegada: es
    una fila por producto. Repitiendo el producto por bodega, el general enseñaria el
    mismo aceite cuatro veces.
  · «INGRESO» y «Ingreso» son lo mismo. A Excel le da igual; a SQL no, y son 381 filas
    de la hoja real que desaparecerian del stock sin dar ningun error.
  · LO QUE LA HOJA TRAE MAL SE ENSEÑA. 94 codigos repetidos, 68 movimientos sin ficha y
    17 stocks negativos. Arreglarlos solo seria inventar datos de bodega; esconderlos
    seria estrenar una pantalla que da cifras con toda seguridad y estan mal.
"""
import datetime
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USUARIO = {"id": 1, "usuario": "pruebas", "username": "pruebas", "rol": "ADMIN",
           "permisos_json": None}


# ---------------------------------------------------------------------------
# Una miniatura de la hoja de verdad, con TODAS sus trampas
# ---------------------------------------------------------------------------

PRODUCTOS = [
    # area, codigo, articulo, unidad, valor, proveedor, (vacio), departamento
    ["COCINA", 108194, "Aceite Canola Aerosol", "UNIDAD", 5279, "BELCA", "", "F&B"],
    ["COCINA", "ARSU", "Arroz Sushi", "KG", 3200, "BELCA", "", "F&B"],
    ["BAR", 111180, "Chile En Polvo Tajin", "UNIDAD", 2435, "BELCA", "", "BAR EL BOSQUE"],
    # SIN PRECIO: 395 de los 1.464 de la hoja real estan asi.
    ["COCINA", "SINPRE", "Producto sin precio", "UNIDAD", None, "BELCA", "", "F&B"],
    # CODIGO REPETIDO: 94 en la hoja real. No se funde con el de arriba.
    ["COCINA", 108194, "Aceite Canola DUPLICADO", "UNIDAD", 9999, "BELCA", "", "F&B"],
    # Sin codigo: tambien se rechaza, y se dice.
    ["COCINA", None, "Fila sin codigo", "UNIDAD", 100, "BELCA", "", "F&B"],
    # CODIGO CON ESPACIO AL FINAL. Pasa en la hoja real con «KALE »: el catalogo lo
    # escribe con espacio y el historial sin el, asi que Excel no los cruza y da 0.
    ["COCINA", "KALE ", "Kale Rizado", "UNIDAD", 1500, "BELCA", "", "F&B"],
    # Para la orden que llega a medias.
    ["COCINA", "MIXTO", "Producto de orden partida", "UNIDAD", 1000, "BELCA", "", "F&B"],
]

PROVEEDORES = [
    ["BELCA", "Abarrotes", "64845720", "", "Priscila", "Credito", 30,
     "Martes y viernes", "Miercoles"],
]

CUENTAS = [
    ["50000 - Cost of Sale - F&B", "F&B", "50000", "Costo de ventas", "Detalle"],
]

HOY = datetime.date.today()


def _mov(orden, tipo_mov, tipo, codigo, cantidad, depto, estado="Recibido",
         descripcion=""):
    """Una fila del HISTORIAL GENERAL, en el orden de columnas de la hoja."""
    return [orden, HOY, "BELCA", tipo, codigo, descripcion or str(codigo),
            cantidad, depto, tipo_mov, estado]


MOVIMIENTOS = [
    # El aceite: entran 10 a F&B, salen 3. Stock F&B = 7.
    _mov(1, "ORDEN DE COMPRA", "INGRESO", 108194, 10, "F&B"),
    _mov(2, "ORDEN INTERNA", "SALIDA", 108194, 3, "F&B"),
    # El MISMO aceite tambien vive en BAR EL BOSQUE: entran 4, no sale nada.
    # Stock BAR = 4, y el general del aceite tiene que ser 11 en UNA fila.
    _mov(3, "ORDEN DE COMPRA", "INGRESO", 108194, 4, "BAR EL BOSQUE"),
    # MAYUSCULAS MEZCLADAS, como en la hoja: 'Ingreso' y 'Salida'.
    _mov(4, "ORDEN DE COMPRA", "Ingreso", "ARSU", 20, "F&B"),
    _mov(5, "ORDEN INTERNA", "Salida", "ARSU", 5, "F&B"),
    # PEDIDO Y NO LLEGADO: no es mercaderia en bodega.
    _mov(6, "ORDEN DE COMPRA", "INGRESO", "ARSU", 50, "F&B",
         estado="Pendiente de Ingreso"),
    # STOCK NEGATIVO: sale sin haber entrado. 17 asi en la hoja real.
    _mov(7, "ORDEN INTERNA", "SALIDA", 111180, 2, "BAR EL BOSQUE"),
    # MOVIMIENTO HUERFANO: el codigo no esta en Productos. 68 en la hoja real.
    _mov(8, "ORDEN DE COMPRA", "INGRESO", "FANTASMA", 6, "F&B",
         descripcion="Algo que no tiene ficha"),
    # Sin cantidad legible: se rechaza y se dice.
    _mov(9, "ORDEN DE COMPRA", "INGRESO", "ARSU", "muchas", "F&B"),
    # El codigo que Excel devuelve como numero con coma: '108194.0' es el mismo aceite.
    _mov(10, "ORDEN DE COMPRA", "INGRESO", 108194.0, 1, "F&B"),
    # EL CODIGO CON ESPACIO: el movimiento dice «KALE» y el catalogo «KALE ».
    _mov(11, "ORDEN DE COMPRA", "INGRESO", "KALE", 9, "F&B"),
    # UNA ORDEN QUE LLEGA A MEDIAS: la misma orden, dos lineas, dos estados. 25 asi en
    # la hoja real, tocando 218 productos.
    _mov(12, "ORDEN DE COMPRA", "INGRESO", "MIXTO", 5, "F&B"),
    _mov(12, "ORDEN DE COMPRA", "INGRESO", "MIXTO", 7, "F&B",
         estado="Pendiente de Ingreso"),
]


def _hoja(ruta):
    """Escribe el .xlsx de prueba con las cuatro pestañas que la importacion lee."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Productos"
    ws.append(["0", "Codigo producto", "Articulos", "Und.medida", "Valor unitario",
               "S.A (BELCA)", "", "Lista Departamentos"])
    for f in PRODUCTOS:
        ws.append(f)

    ws = wb.create_sheet("Provedores")
    ws.append(["PROVEEDOR", "Tipo de compra", "CONTACTO", "CORREO",
               "NOMBRE DEL CONTACTO", "CONDICION", "DIAS DE CREDITO",
               "DIAS DE PEDIDO", "DIAS DE ENTREGA"])
    for f in PROVEEDORES:
        ws.append(f)

    ws = wb.create_sheet("Detalle de cuentas")
    for _ in range(5):
        ws.append([])
    for f in CUENTAS:
        ws.append(f)

    ws = wb.create_sheet("HISTORIAL GENERAL")
    ws.append(["Orden", "Fecha", "Proveedor", "Tipo", "Código", "Descripción",
               "Cantidad", "Departamento", "Tipo de Movimiento", "Estado"])
    for f in MOVIMIENTOS:
        ws.append(f)

    # LAS PESTAÑAS POR BODEGA. Todo en ellas es formula menos el minimo y el maximo,
    # que estan escritos a mano: son lo unico que se importa de aqui.
    #
    # La segunda lleva el encabezado de la primera columna MAL, como la hoja de verdad:
    # en INV_BAR dice «50000 - Cost of Sale» y en INV_STAFF_COMEDOR dice «f». Buscando
    # las columnas por posicion, esas dos pestañas se perdian enteras.
    def pestaña_de_bodega(nombre, titulo_primera, depto, filas):
        ws = wb.create_sheet(nombre)
        ws.append([titulo_primera, "Departamento", "Descripción", "Unidad",
                   "Valor Unitario", "Ingresos", "Salidas", "Stock Actual",
                   "Inversión", "Mínimo Base (0%)", "Máximo Base (100%)",
                   "Pedido Sugerido"])
        for codigo, mn, mx in filas:
            ws.append([codigo, depto, "", "UNIDAD", 0, 0, 0, 0, 0, mn, mx, 0])

    pestaña_de_bodega("INV_RESTAURANTE", "Código", "F&B",
                      [(108194, 4, 12), ("ARSU", 10, 50), ("SINNIVEL", None, None)])
    pestaña_de_bodega("INV_BAR", "50000 - Cost of Sale - F&B", "BAR EL BOSQUE",
                      [(108194, 20, 60), (111180, 2, 6)])

    # Una pestaña de las CALCULADAS, para comprobar que NO se importa como un segundo
    # inventario: en la hoja real esas cuatro tienen codigos propios que no cruzan.
    ws = wb.create_sheet("ABARROTES")
    ws.append(["", "OCUPACION SEMANAL", 500, "PAX"])
    ws.append([])
    ws.append(["CODIGO", "DESCRIPCIÓN", "UNIDAD DE MEDIDA", "EXISTENCIAS"])
    ws.append(["ACAP", "ACEITE CANOLA AEROSOL", "UNIDAD", 999])

    wb.save(ruta)
    return ruta


def _importar(c=None):
    """Base limpia + la hoja de prueba cargada. Devuelve (conn, recuento, datos)."""
    comun.base_limpia().close()
    import proveeduria_excel as pvx
    carpeta = os.environ.get("HOTEL_DATA_DIR") or "."
    ruta = _hoja(os.path.join(carpeta, "hoja_de_prueba.xlsx"))
    datos = pvx.leer(ruta)
    conn = comun.conexion()
    cuenta = pvx.cargar(conn, datos, usuario="pruebas")
    return conn, cuenta, datos


def _stock(filas):
    return {f["codigo"]: f["stock"] for f in filas}


def _celdas_excel(buf):
    """Todo el texto de un Excel, para buscar dentro sin saber en que fila cayo."""
    from openpyxl import load_workbook
    buf.seek(0)
    wb = load_workbook(buf)
    return [str(c.value) for ws in wb for fila in ws.iter_rows()
            for c in fila if c.value is not None]


def _paginas(buf):
    """El texto de un PDF, para comprobar lo que el proveedor va a LEER y no que la
    funcion devolvio algo."""
    import pdfplumber
    buf.seek(0)
    with pdfplumber.open(buf) as pdf:
        return len(pdf.pages), "\n".join((p.extract_text() or "") for p in pdf.pages)


# ---------------------------------------------------------------------------

def el_stock_es_una_resta_y_no_una_columna(c):
    """La regla que ordena todo el modulo. En la hoja el stock sale de restar los
    SUMIFS; aqui sale de restar el libro. Si existiera una columna 'stock' ademas del
    libro, el dia que alguien corrigiera un movimiento viejo los dos dirian cosas
    distintas y no habria forma de saber cual creer."""
    conn, _, _ = _importar()
    import proveeduria as pv

    # No hay ninguna columna que guarde el stock.
    columnas = {r[1] for r in conn.execute("PRAGMA table_info(pv_producto)")}
    c.cierto("stock" not in columnas, "el producto NO guarda su stock")
    columnas_mov = {r[1] for r in conn.execute("PRAGMA table_info(pv_movimiento)")}
    c.cierto("stock" not in columnas_mov, "el movimiento tampoco")

    fnb = _stock(pv.existencias(conn, departamento="F&B"))
    c.igual(fnb.get("108194"), 8, "aceite en F&B: entran 10 y 1, sale 3")
    c.igual(fnb.get("ARSU"), 15, "arroz en F&B: entran 20, salen 5")
    conn.close()


def una_orden_pedida_no_es_mercaderia_en_bodega(c):
    """La hoja ya lo hace bien y es la mitad que importa: el SUMIFS de los ingresos pide
    Estado = «Recibido», el de las salidas no. Contar lo pedido hincha el inventario y
    hace que no se pida lo que si hace falta — y nadie lo nota hasta que falta."""
    conn, _, _ = _importar()
    import proveeduria as pv

    fila = [f for f in pv.existencias(conn, departamento="F&B")
            if f["codigo"] == "ARSU"][0]
    c.igual(fila["stock"], 15, "los 50 pedidos y no llegados NO cuentan como stock")
    c.igual(fila["en_camino"], 50, "pero se enseñan aparte: estan pedidos")
    conn.close()


def cada_departamento_lleva_su_bodega_y_el_general_las_suma(c):
    """LO RECORDO EL LODGE: «cada departamento maneja su inventario por aparte, esto
    aparte del general».

    Y el general NO es la lista de las bodegas pegada: es UNA fila por producto. Medido
    en la hoja real: 1.464 filas en INVENTARIO_GENERAL —exactamente el numero de
    productos— contra 532 en RESTAURANTE y 338 en BAR. Repitiendo el producto una vez por
    bodega, el general enseñaria el mismo aceite cuatro veces y la inversion saldria bien
    pero ilegible."""
    conn, _, _ = _importar()
    import proveeduria as pv

    fnb = _stock(pv.existencias(conn, departamento="F&B"))
    bar = _stock(pv.existencias(conn, departamento="BAR EL BOSQUE"))
    c.igual(fnb.get("108194"), 8, "el aceite en F&B")
    c.igual(bar.get("108194"), 4, "y el mismo aceite en BAR, aparte")
    c.cierto("ARSU" not in bar, "lo de F&B no se cuela en la bodega del BAR")

    general = pv.existencias(conn)
    veces = [f for f in general if f["codigo"] == "108194"]
    c.igual(len(veces), 1, "en el general el aceite sale UNA vez")
    c.igual(veces[0]["stock"], 12, "con sus dos bodegas sumadas (8 + 4)")
    c.igual(veces[0]["bodegas"], 2, "y diciendo en cuantas bodegas esta")
    c.igual(veces[0]["departamento"], "F&B",
            "con el departamento del catalogo, que es el unico valor cierto de esa fila")

    # Y el desglose sigue existiendo para quien lo necesite.
    desglosado = pv.existencias(conn, desglosar=True)
    c.igual(sorted(f["departamento"] for f in desglosado if f["codigo"] == "108194"),
            ["BAR EL BOSQUE", "F&B"], "desglosado se ven las dos bodegas")
    conn.close()


def ingreso_y_Ingreso_son_lo_mismo(c):
    """A Excel le da igual porque SUMIFS no distingue mayusculas. A SQL no: en la hoja
    real son 308 filas «Ingreso» y 73 «Salida» que, portadas tal cual, desaparecerian del
    stock sin dar ningun error. Por eso se guarda un SIGNO y no el texto."""
    import proveeduria as pv
    for texto, esperado in (("INGRESO", 1), ("Ingreso", 1), ("ingreso", 1),
                            ("SALIDA", -1), ("Salida", -1), ("salida", -1)):
        c.igual(pv.signo_de(texto), esperado, f"«{texto}» se entiende")
    c.igual(pv.signo_de("cualquier cosa"), None, "lo que no se entiende se dice")
    c.igual(pv.signo_de(None), None, "y el vacio tambien")

    conn, _, _ = _importar()
    columnas = {r[1] for r in conn.execute("PRAGMA table_info(pv_movimiento)")}
    c.cierto("signo" in columnas and "tipo" not in columnas,
             "en la base vive el signo, no el texto")
    # El arroz entro con «Ingreso» y salio con «Salida»: si se hubieran perdido, su
    # stock seria 0 en vez de 15.
    fnb = _stock(pv.existencias(conn, departamento="F&B"))
    c.igual(fnb.get("ARSU"), 15, "las filas en minuscula cuentan igual")
    conn.close()


def el_codigo_que_excel_devuelve_con_coma_es_el_mismo_producto(c):
    """Excel guarda los codigos numericos como numeros, asi que «108194» vuelve como
    «108194.0». Sin normalizarlo, el mismo producto son dos y el stock se parte en dos
    mitades que nadie suma — y las dos se ven perfectamente normales."""
    import proveeduria as pv
    c.igual(pv.normalizar_codigo(108194.0), "108194", "el .0 se quita")
    c.igual(pv.normalizar_codigo("108194.0"), "108194", "tambien escrito como texto")
    c.igual(pv.normalizar_codigo("ARSU"), "ARSU", "y un codigo de letras no se toca")
    c.igual(pv.normalizar_codigo(" arsu "), "ARSU", "sin espacios y en mayuscula")

    conn, _, _ = _importar()
    filas = [f for f in pv.existencias(conn, departamento="F&B")
             if f["codigo"] == "108194"]
    c.igual(len(filas), 1, "el aceite es UN producto, no dos")
    c.igual(filas[0]["stock"], 8, "y el movimiento con coma suma en el mismo")
    conn.close()


def una_orden_puede_llegar_a_medias(c):
    """EL ESTADO ES DE LA LINEA, NO DE LA ORDEN. Medido en la hoja del lodge: 25 ordenes
    de 1.165 traen lineas en dos estados a la vez, y tocan 218 productos. Es lo normal
    cuando el bote trae media orden y el resto queda para el viaje siguiente.

    ESTE FALLO LO TUVE PUESTO. El estado estaba en la cabecera —parecia mas ordenado— y
    daba 61 productos con el stock equivocado contra la propia hoja. Se vio comparando
    producto por producto contra el Excel real; el recuento global lo daba por bueno,
    porque cuadraba el 91%."""
    conn, _, _ = _importar()
    import proveeduria as pv

    fila = [f for f in pv.existencias(conn, departamento="F&B")
            if f["codigo"] == "MIXTO"][0]
    c.igual(fila["stock"], 5, "solo cuenta la mitad que llego")
    c.igual(fila["en_camino"], 7, "y la otra mitad queda como pedida")

    # El estado vive en la linea, no en la cabecera: si volviera a la cabecera, las dos
    # lineas de la orden 12 tendrian el mismo y una de las dos cifras saldria mal.
    columnas_doc = {r[1] for r in conn.execute("PRAGMA table_info(pv_documento)")}
    columnas_mov = {r[1] for r in conn.execute("PRAGMA table_info(pv_movimiento)")}
    c.cierto("estado" in columnas_mov, "el estado esta en la linea")
    c.cierto("estado" not in columnas_doc,
             "y NO en la cabecera, para que no haya dos que puedan discrepar")

    estados = sorted(r[0] for r in conn.execute(
        """SELECT m.estado FROM pv_movimiento m JOIN pv_documento d
                ON d.id = m.documento_id
            WHERE d.numero = '12'"""))
    c.igual(estados, ["Pendiente de Ingreso", "Recibido"],
            "la misma orden guarda sus dos estados")
    conn.close()


def un_espacio_al_final_del_codigo_no_pierde_la_mercaderia(c):
    """PASA EN LA HOJA DE VERDAD. El catalogo escribe «KALE » con un espacio y el
    historial «KALE»; Excel no cruza los dos y da existencia CERO para un producto del
    que hay nueve. Lo encontre comparando los 694 codigos uno a uno: era el unico que no
    cuadraba, y el numero bueno resulto ser el de la aplicacion, no el de la hoja.

    Es la clase de fallo que justifica dejar la hoja: no da error, da un cero."""
    conn, _, _ = _importar()
    import proveeduria as pv

    fila = [f for f in pv.existencias(conn, departamento="F&B")
            if f["codigo"] == "KALE"]
    c.igual(len(fila), 1, "el producto aparece una vez, sin el espacio")
    c.igual(fila[0]["stock"], 9, "con las nueve unidades que la hoja perdia")
    c.igual(fila[0]["huerfano"], False,
            "y emparejado con su ficha, que es lo que a Excel no le cuadraba")
    c.igual(fila[0]["descripcion"], "Kale Rizado", "con el nombre del catalogo")
    conn.close()


def el_codigo_repetido_no_se_funde_en_silencio(c):
    """94 codigos repetidos en la hoja real. Fundirlos sumaria el stock de dos productos
    distintos que comparten codigo por error de captura, y el resultado se veria
    perfectamente normal. Se queda el primero y el otro se LISTA."""
    conn, cuenta, datos = _importar()

    c.igual(cuenta["productos"], len(PRODUCTOS) - 2,
            "entran todas menos dos: la repetida y la que no tiene codigo")
    motivos = [r["motivo"] for r in datos["rechazos"]]
    c.cierto(any("repetido" in m for m in motivos), "se dice que habia un repetido")
    c.cierto(any("sin código" in m for m in motivos), "y la que no tenia codigo")

    fila = conn.execute(
        "SELECT descripcion, valor_unitario FROM pv_producto WHERE codigo = '108194'"
    ).fetchone()
    c.igual(fila["descripcion"], "Aceite Canola Aerosol",
            "se queda el primero, no el duplicado")
    c.igual(fila["valor_unitario"], 527900, "con su precio, en centimos")
    conn.close()


def lo_que_la_hoja_trae_mal_se_enseña(c):
    """La decision mas importante del modulo. Arreglarlo solo seria inventar datos de
    bodega; esconderlo seria estrenar una pantalla que da cifras con toda seguridad y
    estan mal. Asi que se enseña y proveeduria decide."""
    conn, _, _ = _importar()
    import proveeduria as pv

    rev = pv.revisiones(conn)

    negativos = {f["codigo"]: f for f in rev["negativos"]}
    c.cierto("111180" in negativos, "el chile salio sin haber entrado: sale en negativo")
    c.igual(negativos["111180"]["stock"], -2, "con cuanto falta")
    c.igual(negativos["111180"]["departamento"], "BAR EL BOSQUE",
            "y en que bodega, que es quien tiene que cuadrarlo")

    huerfanos = {f["codigo"] for f in rev["huerfanos"]}
    c.cierto("FANTASMA" in huerfanos, "el movimiento sin ficha se lista")

    sin_precio = {f["codigo"] for f in rev["sin_precio"]}
    c.cierto("SINPRE" in sin_precio, "y el producto sin precio tambien")
    conn.close()


def sin_precio_no_se_inventa_un_cero(c):
    """395 de los 1.464 productos de la hoja no traen precio. Poniendoles cero, la
    inversion total del lodge saldria mas baja de lo que es y nadie veria que falta un
    dato: la pantalla diria «0» con toda seguridad."""
    conn, _, _ = _importar()
    import proveeduria as pv

    fila = [f for f in pv.existencias(conn, departamento="F&B")
            if f["codigo"] == "SINPRE"]
    c.igual(len(fila), 0, "sin movimientos no aparece")

    todas = pv.existencias(conn)
    con_precio = [f for f in todas if not f["sin_precio"]]
    r = pv.resumen(todas)
    c.igual(r["inversion"], sum(f["inversion"] for f in con_precio),
            "la inversion suma SOLO lo que tiene precio")
    # El huerfano no tiene ficha, asi que tampoco tiene precio: tiene que contarse como
    # lo que queda fuera del total.
    c.cierto(r["sin_precio"] >= 1, "y se dice cuantos quedan fuera de esa cifra")

    fantasma = [f for f in todas if f["codigo"] == "FANTASMA"][0]
    c.igual(fantasma["inversion"], None, "sin precio, la inversion es «no se sabe»")
    c.igual(fantasma["huerfano"], True, "y queda marcado como sin ficha")
    c.igual(fantasma["stock"], 6, "pero su stock SI cuenta: la mercaderia esta ahi")
    conn.close()


def importar_dos_veces_da_lo_mismo_y_no_el_doble(c):
    """La hoja manda mientras siga siendo la fuente. Acumulando, nadie lo notaria hasta
    que alguien mirara una existencia y le pareciera alta — y para entonces ya no se
    sabria cuantas veces se importo."""
    conn, cuenta1, _ = _importar()
    import proveeduria as pv
    import proveeduria_excel as pvx

    antes = _stock(pv.existencias(conn))
    ruta = os.path.join(os.environ.get("HOTEL_DATA_DIR") or ".", "hoja_de_prueba.xlsx")
    cuenta2 = pvx.cargar(conn, pvx.leer(ruta), usuario="pruebas")
    despues = _stock(pv.existencias(conn))

    c.igual(despues, antes, "el inventario es el mismo tras importar otra vez")
    c.igual(cuenta2["movimientos"], cuenta1["movimientos"], "y los movimientos tambien")
    c.igual(conn.execute("SELECT COUNT(*) FROM pv_producto").fetchone()[0],
            cuenta1["productos"], "sin productos duplicados")
    conn.close()


def las_pestañas_calculadas_no_entran_como_un_segundo_inventario(c):
    """La hoja tiene CUATRO pestañas de categoria (ABARROTES, VERDURA, CARNE Y MARISCOS,
    LIMPIEZA) con codigos propios —«ACAP» donde el catalogo dice «108194»— que no cruzan
    con el historial. Importarlas seria estrenar la pantalla con el problema que la hoja
    ya tiene: dos inventarios del mismo almacen."""
    conn, _, _ = _importar()
    hay = conn.execute(
        "SELECT COUNT(*) FROM pv_producto WHERE codigo = 'ACAP'").fetchone()[0]
    c.igual(hay, 0, "el codigo paralelo de ABARROTES no entra al catalogo")
    movs = conn.execute(
        "SELECT COUNT(*) FROM pv_movimiento WHERE codigo = 'ACAP'").fetchone()[0]
    c.igual(movs, 0, "ni como movimiento")
    conn.close()


def ninguna_fila_se_pierde_en_silencio(c):
    """Una fila que se cae sin decirlo es stock que falta en la pantalla sin que nada lo
    explique. Las que no se entienden vuelven en el informe, con su motivo."""
    conn, cuenta, datos = _importar()
    c.igual(cuenta["movimientos"], len(MOVIMIENTOS) - 1,
            "entra todo menos la fila de cantidad ilegible")
    motivos = [r["motivo"] for r in datos["rechazos"]]
    c.cierto(any("cantidad" in m for m in motivos),
             "y se dice por que se quedo fuera")
    c.igual(cuenta["rechazos"], len(datos["rechazos"]),
            "el recuento de rechazos es el de la lista, no otro numero")
    for r in datos["rechazos"]:
        c.cierto(r["hoja"] and r["fila"] and r["motivo"],
                 "cada rechazo dice pestaña, fila y motivo")
    conn.close()


def el_documento_se_guarda_una_vez_y_no_por_linea(c):
    """En la hoja el numero de orden se repite en cada linea con su proveedor y su fecha
    copiados: 11.506 filas para 1.161 ordenes. Aqui la cabecera va una vez."""
    conn, cuenta, _ = _importar()
    # Doce ordenes en la hoja de prueba, pero la 9 entera se rechaza por cantidad
    # ilegible; la 12 tiene DOS lineas y sigue siendo UN documento.
    c.igual(cuenta["documentos"], 11, "once documentos distintos")
    c.cierto(cuenta["movimientos"] > cuenta["documentos"],
             "con mas lineas que documentos: la orden partida tiene dos")
    dobles = conn.execute(
        """SELECT COUNT(*) FROM pv_movimiento m JOIN pv_documento d
                ON d.id = m.documento_id WHERE d.numero = '12'""").fetchone()[0]
    c.igual(dobles, 2, "las dos lineas de la orden 12 cuelgan de la misma cabecera")
    huerfanas = conn.execute(
        """SELECT COUNT(*) FROM pv_movimiento m
            LEFT JOIN pv_documento d ON d.id = m.documento_id
            WHERE d.id IS NULL""").fetchone()[0]
    c.igual(huerfanas, 0, "ninguna linea queda sin su cabecera")
    conn.close()


# ---------------------------------------------------------------------------
# Fase 2: registrar salidas, mermas y ajustes
# ---------------------------------------------------------------------------

def el_restaurante_registra_una_salida_de_bodega(c):
    """Es lo que se hace a diario, y lo que la hoja hacia escribiendo una fila a mano."""
    conn, _, _ = _importar()
    import proveeduria as pv

    antes = _stock(pv.existencias(conn, departamento="F&B")).get("ARSU")
    doc, avisos = pv.registrar(conn, "ORDEN INTERNA", "F&B",
                               [{"codigo": "ARSU", "cantidad": 4}],
                               usuario="bodega", observaciones="para el almuerzo")
    c.igual(avisos, [], "con existencia de sobra no hay nada que avisar")
    c.igual(doc["tipo"], "ORDEN INTERNA", "queda como orden interna")
    c.igual(doc["origen"], "APP", "y marcado como registrado aqui")
    c.igual(doc["creado_por"], "bodega", "con quien lo registro, para poder preguntarle")
    c.igual(doc["lineas"][0]["signo"], -1, "la linea SALE")

    despues = _stock(pv.existencias(conn, departamento="F&B")).get("ARSU")
    c.igual(despues, antes - 4, "y el stock baja justo lo que salio")
    # La OTRA bodega no se toca: se saco de F&B.
    c.igual(_stock(pv.existencias(conn, departamento="BAR EL BOSQUE")).get("ARSU"), None,
            "la bodega de al lado no se entera")
    conn.close()


def una_salida_que_deja_la_bodega_en_negativo_avisa_pero_no_bloquea(c):
    """EN LA HOJA DEL LODGE HAY 53 NEGATIVOS VIVOS. Si esto bloqueara, el primer dia
    alguien no podria registrar una salida que de verdad ocurrio y volveria al Excel.

    Lo que falta es el ingreso que nadie anoto, y eso se arregla con un ajuste, no
    impidiendo trabajar. Es la misma regla que el spa y los horarios del restaurante:
    avisar y dejar decidir."""
    conn, _, _ = _importar()
    import proveeduria as pv

    doc, avisos = pv.registrar(conn, "ORDEN INTERNA", "F&B",
                               [{"codigo": "ARSU", "cantidad": 999}], usuario="bodega")
    c.cierto(doc is not None, "la salida SE REGISTRA igual")
    c.igual(len(avisos), 1, "y se avisa")
    c.cierto("queda en" in avisos[0], "diciendo como queda la bodega")
    c.cierto("ARSU" in avisos[0], "y de que producto habla")
    c.cierto(_stock(pv.existencias(conn, departamento="F&B"))["ARSU"] < 0,
             "el negativo queda a la vista, que es el punto")
    conn.close()


def el_ajuste_se_escribe_como_lo_contado_y_no_como_la_diferencia(c):
    """Quien cuenta la bodega tiene delante doce latas, no «menos tres». Pedirle la resta
    es pedirle una cuenta que el sistema puede hacer, y una resta mal hecha en un
    inventario no se descubre hasta el conteo siguiente.

    Es ademas lo que arregla los 53 stocks negativos de la hoja."""
    conn, _, _ = _importar()
    import proveeduria as pv

    # El chile esta en -2 en BAR: se cuenta y hay 6.
    c.igual(_stock(pv.existencias(conn, departamento="BAR EL BOSQUE"))["111180"], -2,
            "parte del negativo que trae la hoja")
    doc, _ = pv.registrar(conn, "AJUSTE INVENTARIO", "BAR EL BOSQUE",
                          [{"codigo": "111180", "contado": 6}], usuario="bodega")
    c.igual(_stock(pv.existencias(conn, departamento="BAR EL BOSQUE"))["111180"], 6,
            "despues del conteo, la bodega dice lo que se conto")
    c.igual(doc["lineas"][0]["cantidad"], 8, "se anoto la diferencia (de -2 a 6 son 8)")
    c.igual(doc["lineas"][0]["signo"], 1, "como una entrada")

    # Y al reves: se cuenta menos de lo que decia.
    pv.registrar(conn, "AJUSTE INVENTARIO", "BAR EL BOSQUE",
                 [{"codigo": "111180", "contado": 2}], usuario="bodega")
    c.igual(_stock(pv.existencias(conn, departamento="BAR EL BOSQUE"))["111180"], 2,
            "tambien baja")

    # LO QUE COINCIDE NO SE ANOTA: un documento vacio ensuciaria el historial y haria
    # parecer que hubo movimiento donde no lo hubo.
    doc, avisos = pv.registrar(conn, "AJUSTE INVENTARIO", "BAR EL BOSQUE",
                               [{"codigo": "111180", "contado": 2}], usuario="bodega")
    c.igual(doc, None, "contar lo mismo no crea ningun documento")
    c.cierto(avisos and "coincide" in avisos[0], "y se dice por que")
    conn.close()


def no_se_mueve_un_codigo_que_no_esta_en_el_catalogo(c):
    """Un codigo que no esta es casi siempre un codigo mal escrito. Dandole ficha
    automaticamente se crea un producto fantasma que a partir de ahi parece legitimo —y
    la hoja ya tiene 68 movimientos asi."""
    conn, _, _ = _importar()
    import proveeduria as pv

    for mal in ({"codigo": "NOEXISTE", "cantidad": 1}, {"codigo": "", "cantidad": 1}):
        try:
            pv.registrar(conn, "ORDEN INTERNA", "F&B", [mal], usuario="bodega")
            c.cierto(False, f"tenia que rechazar {mal}")
        except ValueError as e:
            c.cierto("catálogo" in str(e) or "sin código" in str(e),
                     "y se dice por que se rechaza")

    for mala in (0, -3, "muchas"):
        try:
            pv.registrar(conn, "ORDEN INTERNA", "F&B",
                         [{"codigo": "ARSU", "cantidad": mala}], usuario="bodega")
            c.cierto(False, f"tenia que rechazar la cantidad {mala!r}")
        except ValueError:
            c.ok += 1
    # Y una bodega vacia tampoco: un movimiento sale o entra en alguna.
    try:
        pv.registrar(conn, "ORDEN INTERNA", "", [{"codigo": "ARSU", "cantidad": 1}])
        c.cierto(False, "tenia que exigir la bodega")
    except ValueError as e:
        c.cierto("bodega" in str(e), "se exige la bodega")
    conn.close()


def reimportar_la_hoja_no_borra_lo_registrado_en_la_app(c):
    """LA TRAMPA QUE ESTA FASE OBLIGABA A RESOLVER. Sin esto se trabaja todo el dia en la
    aplicacion, alguien vuelve a importar la hoja «para actualizar» y el trabajo
    desaparece sin que nada lo diga.

    La hoja manda sobre LO SUYO: se borra y se recarga lo que vino de ella, y lo que
    alguien registro aqui se queda."""
    conn, _, _ = _importar()
    import proveeduria as pv
    import proveeduria_excel as pvx

    pv.registrar(conn, "ORDEN INTERNA", "F&B", [{"codigo": "ARSU", "cantidad": 4}],
                 usuario="bodega")
    con_salida = _stock(pv.existencias(conn, departamento="F&B"))["ARSU"]

    ruta = os.path.join(os.environ.get("HOTEL_DATA_DIR") or ".", "hoja_de_prueba.xlsx")
    pvx.cargar(conn, pvx.leer(ruta), usuario="pruebas")

    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["ARSU"], con_salida,
            "la salida registrada aqui SIGUE descontada tras reimportar")
    origenes = {r[0]: r[1] for r in conn.execute(
        "SELECT origen, COUNT(*) FROM pv_documento GROUP BY origen")}
    c.igual(origenes.get("APP"), 1, "queda el documento de la aplicacion")
    c.cierto(origenes.get("HOJA", 0) > 1, "y los de la hoja, recargados")

    # Y LA HOJA SIGUE SIN DUPLICARSE: importar dos veces da lo mismo.
    pvx.cargar(conn, pvx.leer(ruta), usuario="pruebas")
    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["ARSU"], con_salida,
            "y a la tercera importacion, igual")
    conn.close()


def un_movimiento_mal_puesto_se_puede_borrar_y_el_de_la_hoja_no(c):
    """Quien anota una salida de 100 donde eran 10 lo nota en el momento y lo que
    necesita es quitarla, no dejar dos lineas falsas que se anulan entre si y que el dia
    del conteo hay que entender.

    Los de la hoja no: los manda la hoja. Borrar uno aqui haria que la siguiente
    importacion lo trajera de vuelta."""
    conn, _, _ = _importar()
    import proveeduria as pv

    antes = _stock(pv.existencias(conn, departamento="F&B"))["ARSU"]
    doc, _ = pv.registrar(conn, "ORDEN INTERNA", "F&B",
                          [{"codigo": "ARSU", "cantidad": 100}], usuario="bodega")
    c.cierto(_stock(pv.existencias(conn, departamento="F&B"))["ARSU"] < antes,
             "la salida equivocada baja el stock")

    pv.anular(conn, doc["id"])
    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["ARSU"], antes,
            "al borrarla, el inventario vuelve exactamente a como estaba")
    c.igual(conn.execute("SELECT COUNT(*) FROM pv_movimiento WHERE documento_id = ?",
                         (doc["id"],)).fetchone()[0], 0, "sin dejar lineas sueltas")

    de_la_hoja = conn.execute(
        "SELECT id FROM pv_documento WHERE origen = 'HOJA' LIMIT 1").fetchone()[0]
    try:
        pv.anular(conn, de_la_hoja)
        c.cierto(False, "un documento de la hoja no se tenia que poder borrar")
    except ValueError as e:
        c.cierto("hoja" in str(e), "y se explica que se corrige en la hoja")
    conn.close()


def la_numeracion_sigue_la_que_ya_hay(c):
    """Quien lleva la bodega lee ese numero en el papel y en la hoja. Empezar en «1»
    haria convivir dos series y habria que preguntar de cual es cada documento."""
    conn, _, _ = _importar()
    import proveeduria as pv

    maximo = conn.execute(
        "SELECT MAX(CAST(numero AS INTEGER)) FROM pv_documento "
        "WHERE numero GLOB '[0-9]*'").fetchone()[0]
    doc, _ = pv.registrar(conn, "ORDEN INTERNA", "F&B",
                          [{"codigo": "ARSU", "cantidad": 1}], usuario="bodega")
    c.igual(int(doc["numero"]), maximo + 1, "el siguiente numero continua la serie")
    doc2, _ = pv.registrar(conn, "MERMA", "F&B",
                           [{"codigo": "ARSU", "cantidad": 1}], usuario="bodega")
    c.igual(int(doc2["numero"]), maximo + 2, "y el siguiente tambien")
    conn.close()


def la_pantalla_deja_registrar_las_tres_cosas(c):
    """Las tres con la MISMA ventana, porque son el mismo gesto con otro nombre: elegir
    bodega, elegir productos y poner un numero. Lo que cambia es que significa el
    numero."""
    conn, _, _ = _importar()
    conn.close()
    import main

    # Por el endpoint, que es por donde entra desde la pantalla.
    r = main.proveeduria_registrar(
        {"tipo": "ORDEN INTERNA", "departamento": "F&B",
         "lineas": [{"codigo": "ARSU", "cantidad": 2}]}, user=USUARIO)
    c.igual(r["status"], "ok", "el endpoint registra")
    c.cierto(r["documento"]["numero"], "y devuelve el documento con su numero")

    docs = main.proveeduria_movimientos(user=USUARIO)["documentos"]
    c.cierto(any(d["origen"] == "APP" for d in docs), "sale en la lista de movimientos")
    c.cierto(any(d["origen"] == "HOJA" for d in docs), "junto a los de la hoja")

    # El buscador del formulario mira el CATALOGO, para llegar tambien a lo que esta en
    # cero: un producto que se acabo sigue existiendo y es justo el que hay que ajustar.
    hallados = main.proveeduria_buscar_productos(q="sin precio", departamento="F&B",
                                                 user=USUARIO)["productos"]
    c.igual([p["codigo"] for p in hallados], ["SINPRE"],
            "encuentra un producto que no tiene ningun movimiento")
    c.igual(hallados[0]["stock"], 0, "diciendo que hay cero en esa bodega")
    c.igual(main.proveeduria_buscar_productos(q="a", user=USUARIO)["productos"], [],
            "con una sola letra no busca")

    from fastapi import HTTPException
    try:
        main.proveeduria_registrar(
            {"tipo": "ORDEN DE COMPRA", "departamento": "F&B",
             "lineas": [{"codigo": "ARSU", "cantidad": 1}]}, user=USUARIO)
        c.cierto(False, "la orden de compra todavia no se registra aqui")
    except HTTPException as e:
        c.igual(e.status_code, 400, "y se rechaza con 400, no con un error raro")

    raiz = RAIZ
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    for tipo in ("ORDEN INTERNA", "AJUSTE INVENTARIO", "MERMA"):
        c.cierto(f"abrirMovimientoPv('{tipo}')" in pantalla, f"hay boton para {tipo}")
    c.cierto("function guardarMovimientoPv(" in pantalla, "y la ventana guarda")
    c.cierto("avisarDeLaBodegaPv" in pantalla,
             "los avisos de negativo se enseñan en un cartel que no se va solo")

    # CAMBIAR DE BODEGA VACIA LAS LINEAS, y se comprueba que lo HAGA, no que la funcion
    # exista: las cantidades se escribieron mirando lo que habia en la otra bodega, y
    # dejarlas puestas saca de una lo que se conto en la otra. Lo destape deshaciendolo
    # a mano — con la comprobacion anterior no caia nadie.
    i = pantalla.find("function cambiarBodegaPv(")
    c.cierto(i > 0, "existe el cambio de bodega")
    fn = pantalla[i:pantalla.find("\nlet _pvBuscaTimer", i)]
    c.cierto("window._pvMov.lineas = []" in fn, "al cambiar de bodega se vacian")
    c.cierto("avisar(" in fn, "y se dice, en vez de que desaparezcan en silencio")
    # Y la CONDICION, no solo las dos lineas de dentro: apagando el `if` el codigo sigue
    # ahi y la comprobacion de arriba pasa igual con las lineas sin vaciar.
    c.cierto(re.search(r"if \(\s*window\._pvMov\.lineas\.length\s*\)", fn) is not None,
             "y se vacian cuando hay lineas puestas, no nunca")


# ---------------------------------------------------------------------------
# Fase 3: la orden de compra
# ---------------------------------------------------------------------------

def _proveedor(conn):
    return conn.execute("SELECT id FROM pv_proveedor LIMIT 1").fetchone()[0]


def una_orden_de_compra_no_suma_al_inventario_hasta_que_llega(c):
    """ES LO UNICO DE PROVEEDURIA QUE NO MUEVE EL INVENTARIO AL ESCRIBIRLO. Se pide, se
    manda al proveedor, y la mercaderia aparece en bodega cuando llega.

    Si sumara al crearla, la pantalla diria que hay arroz desde el momento en que
    alguien escribe que lo va a pedir — y el cocinero bajaria a buscarlo."""
    conn, _, _ = _importar()
    import proveeduria as pv

    antes = _stock(pv.existencias(conn, departamento="F&B"))["ARSU"]
    o = pv.crear_orden_compra(conn, _proveedor(conn), "F&B",
                              [{"codigo": "ARSU", "cantidad": 30, "precio": "3200"}],
                              solicitado_por="Alejandro", usuario="bodega")
    c.igual(o["estado"], "Solicitado", "nace como solicitada")
    c.igual(o["lineas"][0]["signo"] if "signo" in o["lineas"][0] else 1, 1,
            "la linea es una entrada")
    fila = [f for f in pv.existencias(conn, departamento="F&B")
            if f["codigo"] == "ARSU"][0]
    c.igual(fila["stock"], antes, "pero el stock NO cambia todavia")
    c.igual(fila["en_camino"], 30 + 50, "y los 30 se suman a lo que ya venia en camino")

    # RECIBIR ES LO QUE SUMA.
    o2, _ = pv.recibir(conn, o["id"], usuario="bodega")
    c.igual(o2["estado"], "Recibido", "al recibirla queda recibida")
    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["ARSU"], antes + 30,
            "y AHI entra a la bodega")
    conn.close()


def una_orden_se_puede_recibir_a_medias(c):
    """ES EL CASO NORMAL, NO LA EXCEPCION: el bote trae lo que cabe y el resto queda para
    el viaje siguiente. Medido en la hoja del lodge: 25 ordenes de 1.165 traen lineas en
    dos estados a la vez."""
    conn, _, _ = _importar()
    import proveeduria as pv

    antes = _stock(pv.existencias(conn, departamento="F&B"))
    o = pv.crear_orden_compra(conn, _proveedor(conn), "F&B", [
        {"codigo": "ARSU", "cantidad": 10},
        {"codigo": "108194", "cantidad": 5},
    ], usuario="bodega")
    llego = o["lineas"][0]["id"]

    o2, _ = pv.recibir(conn, o["id"], lineas_ids=[llego], factura="F-001",
                       usuario="bodega")
    c.igual(o2["estado"], "Recibida a medias", "la orden queda a medias")
    c.igual(o2["recibidas"], 1, "con una linea recibida")
    c.igual(o2["lineas_total"], 2, "de dos")
    c.igual(o2["factura"], "F-001", "y queda el numero de factura")

    ahora = _stock(pv.existencias(conn, departamento="F&B"))
    c.igual(ahora["ARSU"], antes["ARSU"] + 10, "entra lo que llego")
    c.igual(ahora["108194"], antes["108194"], "y lo que no llego NO entra")

    # Lo que falta sigue en camino, que es lo que hay que perseguir.
    pendiente = [f for f in pv.existencias(conn, departamento="F&B")
                 if f["codigo"] == "108194"][0]
    c.igual(pendiente["en_camino"], 5, "lo que falta sigue contando como en camino")

    # Y al recibir el resto, se cierra.
    o3, _ = pv.recibir(conn, o["id"], usuario="bodega")
    c.igual(o3["estado"], "Recibido", "al llegar el resto, queda recibida entera")
    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["108194"],
            antes["108194"] + 5, "y entra el resto")

    # Recibir dos veces no duplica: ya estaban recibidas.
    o4, avisos = pv.recibir(conn, o["id"], usuario="bodega")
    c.cierto(avisos and "ya estaban" in avisos[0], "se avisa en vez de duplicar")
    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["108194"],
            antes["108194"] + 5, "y el stock no se mueve otra vez")
    conn.close()


def solicitada_y_pedida_al_proveedor_son_dos_cosas(c):
    """La hoja las distingue —69 solicitadas y 449 pendientes de ingreso— y es util: una
    esta pedida dentro de la casa y la otra esta en manos del proveedor. A quien
    persigue un pedido le cambia a quien llamar."""
    conn, _, _ = _importar()
    import proveeduria as pv

    o = pv.crear_orden_compra(conn, _proveedor(conn), "F&B",
                              [{"codigo": "ARSU", "cantidad": 3}], usuario="bodega")
    c.igual(o["estado"], "Solicitado", "nace solicitada")
    o2 = pv.marcar_pedida(conn, o["id"])
    c.igual(o2["estado"], "Pendiente de Ingreso", "y pasa a pedida al proveedor")
    # Ninguno de los dos estados es stock.
    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["ARSU"], 15,
            "ni solicitada ni pedida suman al inventario")
    conn.close()


def la_orden_guarda_el_precio_que_se_pidio(c):
    """Lo que se le pidio al proveedor es lo que decia la orden ESE dia. El catalogo
    cambia, y una orden que recalculara su total con el precio de hoy diria otra cosa
    que el papel que firmo alguien."""
    conn, _, _ = _importar()
    import proveeduria as pv

    o = pv.crear_orden_compra(conn, _proveedor(conn), "F&B", [
        {"codigo": "ARSU", "cantidad": 2, "precio": "1000"},
        {"codigo": "108194", "cantidad": 3},            # sin precio: toma el del catalogo
        {"codigo": "SINPRE", "cantidad": 1},            # el catalogo tampoco lo tiene
    ], usuario="bodega")
    por_codigo = {l["codigo"]: l for l in o["lineas"]}
    c.igual(por_codigo["ARSU"]["valor_unitario"], 100000, "el precio escrito, en centimos")
    c.igual(por_codigo["ARSU"]["total"], 200000, "y su total")
    c.igual(por_codigo["108194"]["valor_unitario"], 527900,
            "sin escribirlo, se copia el del catalogo")
    c.igual(por_codigo["SINPRE"]["valor_unitario"], None,
            "y si el catalogo no lo tiene, se queda sin precio: no se inventa un cero")
    c.igual(o["total"], 200000 + 527900 * 3, "el total suma solo lo que tiene precio")
    c.igual(o["lineas_sin_precio"], 1, "y se dice cuantas lineas quedan fuera")

    # El catalogo cambia y la orden NO se mueve.
    conn.execute("UPDATE pv_producto SET valor_unitario = 999999 WHERE codigo = 'ARSU'")
    conn.commit()
    c.igual(pv.orden(conn, o["id"])["lineas"][0]["valor_unitario"], 100000,
            "la orden sigue diciendo lo que se pidio")
    conn.close()


def una_orden_de_compra_no_se_arma_con_cualquier_cosa(c):
    """Sin proveedor no hay a quien comprarle, y un codigo que no esta en el catalogo es
    casi siempre un codigo mal escrito."""
    conn, _, _ = _importar()
    import proveeduria as pv

    casos = [
        ((None, "F&B", [{"codigo": "ARSU", "cantidad": 1}]), "proveedor"),
        ((_proveedor(conn), "", [{"codigo": "ARSU", "cantidad": 1}]), "departamento"),
        ((_proveedor(conn), "F&B", []), "línea"),
        ((_proveedor(conn), "F&B", [{"codigo": "NOEXISTE", "cantidad": 1}]), "catálogo"),
        ((_proveedor(conn), "F&B", [{"codigo": "ARSU", "cantidad": 0}]), "mayor que cero"),
    ]
    for (prov, depto, lineas), pedazo in casos:
        try:
            pv.crear_orden_compra(conn, prov, depto, lineas, usuario="bodega")
            c.cierto(False, f"tenia que rechazar: {pedazo}")
        except ValueError as e:
            c.cierto(pedazo in str(e), f"se explica el motivo ({pedazo})")
    conn.close()


def el_PDF_de_la_orden_lleva_la_direccion_de_ENTREGA(c):
    """EL DATO QUE UN PROVEEDOR NUEVO SE EQUIVOCA. La mercaderia no llega al lodge: llega
    al muelle de Sierpe y de ahi sube en bote. Un proveedor que lee la direccion del
    lodge intenta entregar en un sitio al que no se llega por carretera.

    Tambien tiene que llevar la cedula juridica —con eso factura— y el numero de orden,
    que es con lo que despues se cruza la factura."""
    conn, _, _ = _importar()
    import proveeduria as pv
    import proveeduria_pdf as pvpdf

    o = pv.crear_orden_compra(conn, _proveedor(conn), "F&B",
                              [{"codigo": "ARSU", "cantidad": 7, "precio": "3200"}],
                              solicitado_por="Alejandro",
                              observaciones="Mandar con el bote del jueves",
                              usuario="bodega")
    conn.close()

    cfg = pv.cargar_config()
    _, texto = _paginas(pvpdf.generar(o, cfg))

    c.cierto(cfg["cedula_juridica"] in texto, "lleva la cedula juridica")
    # La direccion se parte en renglones para que quepa, asi que se busca un trozo
    # inconfundible en vez de la frase entera.
    c.cierto("Hacienda Corcovado" in texto.replace("\n", " "),
             "lleva la direccion de ENTREGA, no solo la del lodge")
    c.cierto("ENTREGAR EN" in texto, "y dice claramente que es donde se entrega")
    c.cierto(o["numero"] in texto, "lleva el numero de orden")
    c.cierto("Arroz Sushi" in texto, "y la linea que se pidio")
    c.cierto("Alejandro" in texto, "con quien la pidio, que es a quien se le reclama")
    c.cierto("Mandar con el bote" in texto.replace("\n", " "),
             "y las observaciones")
    c.cierto("TOTAL" in texto, "con su total")
    # EN «CRC» Y NO EN «₡»: Helvetica no trae el simbolo del colon y reportlab lo dibuja
    # como un cuadro negro. Se vio en el papel, no en el codigo.
    c.cierto("CRC" in texto, "la moneda escrita con letras, que el PDF si puede dibujar")
    c.cierto("₡" not in texto, "y no el simbolo, que sale como un cuadro")

    # EL NOMBRE LARGO NO SE METE ENCIMA DE LA COLUMNA DE AL LADO. El proveedor real se
    # llama «CENTRO INTERNACIONAL DE INVERSIONES, S.A (BELCA)»: cabe en 48 caracteres y
    # NO cabe en media pagina, y se dibujaba sobre «SOLICITADO POR». Se recorta por
    # ancho medido.
    import proveeduria_pdf as _pdf
    from reportlab.pdfgen import canvas as _canvas
    lienzo = _canvas.Canvas(io.BytesIO())
    largo = "CENTRO INTERNACIONAL DE INVERSIONES, S.A (BELCA)"
    recortado = _pdf._cabe(lienzo, largo, 120, "Helvetica-Bold", 8.5)
    c.cierto(lienzo.stringWidth(recortado, "Helvetica-Bold", 8.5) <= 120,
             "lo que no cabe se recorta al ancho de verdad")
    c.cierto(recortado.endswith("…"), "y se dice que esta recortado")
    c.igual(_pdf._cabe(lienzo, "corto", 120, "Helvetica-Bold", 8.5), "corto",
            "lo que cabe no se toca")


def el_PDF_dice_cuando_el_total_esta_incompleto(c):
    """El total de una orden es lo que el lodge se compromete a pagar. Enseñarlo como si
    estuviera completo cuando falta el precio de tres renglones es la clase de cifra que
    se firma sin mirar."""
    conn, _, _ = _importar()
    import proveeduria as pv
    import proveeduria_pdf as pvpdf

    o = pv.crear_orden_compra(conn, _proveedor(conn), "F&B", [
        {"codigo": "ARSU", "cantidad": 1, "precio": "1000"},
        {"codigo": "SINPRE", "cantidad": 1},
    ], usuario="bodega")
    conn.close()
    _, texto = _paginas(pvpdf.generar(o, pv.cargar_config()))
    plano = " ".join(texto.split())
    # Se busca «no incluye», que SOLO esta en el renglon del total. Buscar «sin precio»
    # pasaba sola: el producto de prueba se llama «Producto sin precio» y su nombre sale
    # en la tabla. Lo destape al deshacer el renglon a mano — no caia nadie.
    c.cierto("no incluye" in plano,
             "el papel dice que el total no las incluye a todas")
    c.cierto("1 línea" in plano or "1 linea" in plano, "y cuantas quedan fuera")


def la_pantalla_tiene_el_ciclo_entero_de_la_compra(c):
    """De punta a punta por los endpoints, que es por donde entra desde la pantalla."""
    conn, _, _ = _importar()
    prov = _proveedor(conn)
    conn.close()
    import main

    d = main.proveeduria_compras(user=USUARIO)
    c.cierto(d["proveedores"], "la pantalla recibe los proveedores para elegir")
    c.cierto(d["config"]["cedula_juridica"], "y los datos del lodge para el papel")

    r = main.proveeduria_crear_compra(
        {"proveedor_id": prov, "departamento": "F&B",
         "lineas": [{"codigo": "ARSU", "cantidad": 5, "precio": "3200"}]}, user=USUARIO)
    doc_id = r["orden"]["id"]
    c.igual(r["orden"]["estado"], "Solicitado", "se crea solicitada")

    c.igual(main.proveeduria_marcar_pedida(doc_id, user=USUARIO)["orden"]["estado"],
            "Pendiente de Ingreso", "se marca como pedida")
    rec = main.proveeduria_recibir(doc_id, {"factura": "F-99"}, user=USUARIO)
    c.igual(rec["orden"]["estado"], "Recibido", "y se recibe")
    c.igual(rec["orden"]["factura"], "F-99", "con su factura")

    pdf = main.proveeduria_pdf_compra(doc_id, user=USUARIO)
    c.igual(pdf.media_type, "application/pdf", "el PDF se descarga")
    c.cierto(len(pdf.body) > 1000, "y no viene vacio")
    c.cierto(r["orden"]["numero"] in pdf.headers.get("content-disposition", ""),
             "con el numero en el nombre del archivo")

    ordenes = main.proveeduria_compras(user=USUARIO)["ordenes"]
    c.cierto(any(o["id"] == doc_id for o in ordenes), "sale en la lista")
    c.cierto(all("lineas" not in o for o in ordenes),
             "la lista no arrastra las lineas de cada orden")

    raiz = RAIZ
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    for pieza in ("function verComprasPv(", "function abrirNuevaCompraPv(",
                  "function recibirOrdenPv(", "function descargarOrdenPv(",
                  "function marcarPedidaPv("):
        c.cierto(pieza in pantalla, f"la pantalla tiene {pieza}")
    c.cierto("no suma al inventario" in pantalla.lower().replace("í", "i")
             or "NO suma al inventario" in pantalla,
             "y lo dice: una orden no suma hasta recibirla")


# ---------------------------------------------------------------------------
# Fase 4: el pedido sugerido, con la ocupacion de verdad
# ---------------------------------------------------------------------------

def _llenar_el_lodge(conn, cuantas, dias=7):
    """Mete reservas que cubren `dias` ANTES y DESPUES de hoy, para mover la ocupacion.

    Hacia los dos lados a proposito: «que pedir» mira hacia adelante y «consumo» mira
    hacia atras (termina ayer, porque hoy todavia no acabo). Llenando solo el futuro, el
    consumo se calculaba con cero huespedes y dividia entre cero.
    """
    import datetime as dt
    hoy = dt.date.today()
    inicio = hoy - dt.timedelta(days=dias)
    fin = hoy + dt.timedelta(days=dias)

    def dd(d):
        return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"

    conn.execute("DELETE FROM reserva WHERE conf_no LIKE 'OCU%'")
    for i in range(cuantas):
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                   dep_date, adl, chl, res_status)
               VALUES (?,?,?,?,?,2,0,'EN CASA')""",
            (f"OCU{i:03d}", f"{i + 1:02d}", f"Huesped {i}", dd(inicio), dd(fin)))
    conn.commit()


def _nivel(conn, codigo, depto, minimo, maximo):
    conn.execute(
        "INSERT OR REPLACE INTO pv_nivel (codigo, departamento, minimo, maximo) "
        "VALUES (?,?,?,?)", (codigo, depto, minimo, maximo))
    conn.commit()


def la_ocupacion_sale_de_UNA_funcion_para_las_dos_pantallas(c):
    """LA QUINTA VEZ QUE ESTO IBA A PASAR. La cuenta de la ocupacion vivia DENTRO del
    endpoint de Analitica, y el pedido sugerido la necesita. Copiada, la pantalla de
    Analitica diria una ocupacion y el pedido de bodega se calcularia con otra, sin que
    nada avisara — como ya paso con el muelle, la hora del Claro, la casilla NOTAS y el
    BT."""
    import datetime as dt

    import ocupacion as ocu

    conn, _, _ = _importar()
    try:
        _llenar_el_lodge(conn, 15)
        hoy = dt.date.today().isoformat()
        manana = (dt.date.today() + dt.timedelta(days=1)).isoformat()

        dias, total = ocu.por_dia(conn, hoy, manana)
        c.igual(len(dias), 2, "una fila por dia")
        c.igual(dias[0]["habitaciones"], 15, "cuenta las habitaciones ocupadas")
        c.cierto(total > 0, "y sabe cuantas se venden")
    finally:
        conn.close()

    # El endpoint de Analitica usa la MISMA funcion, no una copia.
    import main
    d = main.ocupacion(desde=hoy, hasta=manana, user=USUARIO)
    c.igual([x["habitaciones"] for x in d["dias"]],
            [x["habitaciones"] for x in dias],
            "Analitica y el modulo dicen lo mismo, porque son el mismo codigo")

    raiz = RAIZ
    with open(os.path.join(raiz, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()
    i = servidor.find("def ocupacion(")
    fn = servidor[i:servidor.find("\n@app.", i)]
    c.cierto("_ocu.por_dia(" in fn, "el endpoint llama a la funcion compartida")
    c.cierto("solo_las_que_se_venden" not in fn,
             "y ya no lleva su propia copia de la cuenta")


def el_cuarto_de_guias_no_sube_la_ocupacion(c):
    """Ya estaba resuelto y hay que no romperlo: con 31 ocupados sobre 30 vendibles el
    porcentaje pasaba del 100% sin que nadie hubiera vendido de mas."""
    import datetime as dt

    import ocupacion as ocu

    conn, _, _ = _importar()
    try:
        _llenar_el_lodge(conn, 3)
        hoy = dt.date.today()
        luego = hoy + dt.timedelta(days=3)

        def dd(d):
            return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"

        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                   dep_date, adl, chl, res_status)
               VALUES ('OCUG','G16','Guia', ?, ?, 1, 0, 'EN CASA')""",
            (dd(hoy), dd(luego)))
        conn.commit()

        dias, _ = ocu.por_dia(conn, hoy.isoformat(), hoy.isoformat())
        c.igual(dias[0]["habitaciones"], 3,
                "el cuarto de guias no cuenta como habitacion")
        c.igual(dias[0]["pax"], 3 * 2 + 1,
                "pero el guia SI cuenta en el pax: duerme y come")
    finally:
        conn.close()


def el_pedido_sugerido_se_mueve_con_la_ocupacion(c):
    """ES LA RAZON POR LA QUE ESTO MERECE DEJAR DE SER UNA HOJA. En la hoja la ocupacion
    es un numero escrito a mano en INVENTARIO_GENERAL!C1: el dia que nadie lo actualiza,
    el pedido sale calculado con la ocupacion de la semana pasada.

    La formula es la de la hoja (la de INV_GUIAS, la unica de las tres que mira la
    ocupacion): objetivo = minimo + (maximo - minimo) x ocupacion."""
    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        # El aceite: en F&B hay 8 y no tiene nada pedido. Minimo 5 con el lodge vacio,
        # maximo 40 lleno. (Se usa este y no el arroz porque el arroz trae 50 en camino
        # en la hoja de prueba, y entonces lo que se mide seria otra cosa.)
        _nivel(conn, "108194", "F&B", 5, 40)

        _llenar_el_lodge(conn, 0)
        vacio = pv.pedido_sugerido(conn, departamento="F&B")
        c.igual(vacio["ocupacion_pct"], 0, "lodge vacio: ocupacion cero")
        c.igual([f["sugerido"] for f in vacio["filas"] if f["codigo"] == "108194"], [],
                "con 8 en bodega y objetivo 5, no hay que pedir nada")

        _llenar_el_lodge(conn, 30)
        lleno = pv.pedido_sugerido(conn, departamento="F&B")
        c.cierto(lleno["ocupacion_pct"] > vacio["ocupacion_pct"],
                 "con el lodge lleno la ocupacion sube")
        fila = [f for f in lleno["filas"] if f["codigo"] == "108194"]
        c.igual(len(fila), 1, "y AHORA si hay que pedir aceite")
        if fila:
            c.cierto(fila[0]["objetivo"] > 5,
                     "porque el objetivo subio con la ocupacion, no por nada mas")
            c.igual(fila[0]["stock"], 8, "diciendo cuanto hay")
            c.igual((fila[0]["minimo"], fila[0]["maximo"]), (5, 40),
                    "y de que minimo y maximo sale")
    finally:
        conn.close()


def lo_que_ya_esta_pedido_no_se_vuelve_a_pedir(c):
    """LO QUE SE AÑADE A LA HOJA. Sin esto, el lunes se sugiere comprar 20, se pide, y
    el martes se vuelve a sugerir lo mismo porque todavia no ha llegado — y se compra
    dos veces."""
    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        _nivel(conn, "108194", "F&B", 5, 40)
        _llenar_el_lodge(conn, 30)

        def sugerido_de(codigo):
            return [f for f in pv.pedido_sugerido(conn, departamento="F&B")["filas"]
                    if f["codigo"] == codigo]

        antes = sugerido_de("108194")[0]
        c.cierto(antes["sugerido"] > 0, "hay algo que pedir")

        # Se pide justo eso, y queda en camino (no recibido).
        pv.crear_orden_compra(conn, _proveedor(conn), "F&B",
                              [{"codigo": "108194", "cantidad": antes["sugerido"]}],
                              usuario="bodega")
        c.igual(sugerido_de("108194"), [], "ya pedido, deja de sugerirse")

        # Y si se pide la mitad, se sugiere la otra mitad.
        conn.execute("DELETE FROM pv_movimiento WHERE documento_id IN "
                     "(SELECT id FROM pv_documento WHERE origen = 'APP')")
        conn.execute("DELETE FROM pv_documento WHERE origen = 'APP'")
        conn.commit()
        mitad = max(1, antes["sugerido"] // 2)
        pv.crear_orden_compra(conn, _proveedor(conn), "F&B",
                              [{"codigo": "108194", "cantidad": mitad}],
                              usuario="bodega")
        resto = sugerido_de("108194")
        c.igual(len(resto), 1, "vuelve a sugerirse lo que falta")
        if resto:
            c.igual(resto[0]["en_camino"], mitad, "se ve lo que viene en camino")
            c.igual(resto[0]["sugerido"], antes["sugerido"] - mitad,
                    "y se sugiere solo el resto")
    finally:
        conn.close()


def no_se_le_inventa_un_minimo_a_nadie(c):
    """Cuanto tiene que haber de algo lo decide quien lleva la bodega. Inventarlo seria
    decidir por el lodge; lo que se hace es DECIR cuantos quedan fuera, para que una
    lista vacia no se lea como «no hace falta pedir nada»."""
    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        # Se parte de una bodega SIN niveles: los de la hoja de prueba se quitan.
        conn.execute("DELETE FROM pv_nivel")
        conn.commit()
        _llenar_el_lodge(conn, 30)
        s = pv.pedido_sugerido(conn, departamento="F&B")
        c.igual(s["filas"], [], "sin niveles puestos no se sugiere nada")
        c.cierto(s["sin_nivel"] > 0, "pero se dice cuantos productos quedan fuera")

        _nivel(conn, "108194", "F&B", 5, 40)
        s2 = pv.pedido_sugerido(conn, departamento="F&B")
        c.cierto(s2["filas"], "al poner un nivel, ese si se sugiere")
        c.igual(s2["sin_nivel"], s["sin_nivel"] - 1, "y queda uno menos fuera")

        # UN NIVEL DE ALGO QUE NO ESTA EN EL CATALOGO se sugiere, pero no se puede
        # comprar: la orden exige ficha. Se marca para que la pantalla lo diga en vez de
        # ofrecer un boton que despues falla. Pasa en la hoja de verdad.
        _nivel(conn, "FANTASMA2", "F&B", 5, 40)
        s3 = pv.pedido_sugerido(conn, departamento="F&B")
        fila = [f for f in s3["filas"] if f["codigo"] == "FANTASMA2"]
        c.igual(len(fila), 1, "el nivel sin ficha se sugiere igual")
        if fila:
            c.igual(fila[0]["huerfano"], True, "marcado como sin ficha")
            c.igual(fila[0]["descripcion"], "FANTASMA2",
                    "y enseñando el codigo, que es lo unico que se sabe de el")
            c.igual(fila[0]["proveedor_id"], None,
                    "sin proveedor, asi que no cae en ningun grupo con boton de comprar")
        c.igual(s3["sin_ficha"], 1, "y se dice cuantos hay asi")
    finally:
        conn.close()


def los_niveles_vienen_de_la_hoja_y_son_por_bodega(c):
    """Del mismo refresco el BAR necesita 48 y el RESTAURANTE 6: el nivel es de
    (producto, bodega), no del producto.

    Y las columnas se buscan POR SU ENCABEZADO: en INV_BAR la primera columna se titula
    «50000 - Cost of Sale» y en INV_STAFF_COMEDOR dice «f». Buscandolas por posicion se
    perdian esas dos pestañas enteras — 362 de los 735 productos con nivel puesto."""
    conn, cuenta, datos = _importar()
    try:
        c.cierto(cuenta["niveles"] >= 2, "la importacion trae los niveles")
        filas = {(r[0], r[1]): (r[2], r[3]) for r in conn.execute(
            "SELECT codigo, departamento, minimo, maximo FROM pv_nivel")}
        c.igual(filas.get(("108194", "F&B")), (4.0, 12.0), "el nivel de F&B")
        c.igual(filas.get(("108194", "BAR EL BOSQUE")), (20.0, 60.0),
                "y el MISMO producto con otro nivel en la otra bodega, de la pestaña "
                "cuya primera columna tiene el encabezado mal")
        c.cierto(("SINNIVEL", "F&B") not in filas,
                 "una fila sin minimo ni maximo no es un nivel")
        # SE CUENTAN LOS QUE QUEDARON, no los que se leyeron: la misma (codigo, bodega)
        # viene repetida entre pestañas. Medido en la hoja del lodge: 1.046 filas
        # leidas, 971 niveles distintos. Decir «1.046» seria contar 75 veces lo mismo.
        c.igual(cuenta["niveles"],
                conn.execute("SELECT COUNT(*) FROM pv_nivel").fetchone()[0],
                "el recuento es el de los niveles guardados")

        # Reimportar no duplica ni acumula.
        import proveeduria_excel as pvx
        ruta = os.path.join(os.environ.get("HOTEL_DATA_DIR") or ".",
                            "hoja_de_prueba.xlsx")
        pvx.cargar(conn, pvx.leer(ruta), usuario="pruebas")
        c.igual(conn.execute("SELECT COUNT(*) FROM pv_nivel").fetchone()[0], len(filas),
                "reimportar deja los mismos niveles, no el doble")
    finally:
        conn.close()


def se_dice_a_que_proveedor_toca_pedirle_hoy(c):
    """Un proveedor que recibe pedidos los martes y entrega los miercoles no acepta uno
    el jueves. Pedirle tarde no se nota el jueves: se nota el domingo, cuando no llego.
    El dato ya estaba en su ficha y no lo miraba nadie."""
    import datetime as dt

    import proveeduria as pv

    c.igual(pv.dias_de_pedido("Martes y viernes"), [1, 4], "se leen los dos dias")
    c.igual(pv.dias_de_pedido("Miercoles"), [2], "sin tilde tambien")
    c.igual(pv.dias_de_pedido("Miércoles"), [2], "y con tilde")
    c.igual(pv.dias_de_pedido("No aplica"), [], "lo que no nombra dias no inventa ninguno")
    c.igual(pv.dias_de_pedido(None), [], "ni el vacio")

    conn, _, _ = _importar()
    try:
        conn.execute("UPDATE pv_proveedor SET dias_pedido = 'Martes y viernes'")
        conn.commit()
        martes = dt.date(2026, 11, 24)      # un martes
        jueves = dt.date(2026, 11, 26)
        c.cierto(pv.a_quien_toca_pedirle(conn, martes), "el martes si toca")
        c.igual(pv.a_quien_toca_pedirle(conn, jueves), [], "el jueves no")
    finally:
        conn.close()


def la_pantalla_lleva_del_sugerido_a_la_orden(c):
    """Una lista que hay que copiar a mano a la orden se deja de usar a la semana."""
    conn, _, _ = _importar()
    try:
        _nivel(conn, "108194", "F&B", 5, 40)
        _llenar_el_lodge(conn, 30)
    finally:
        conn.close()
    import main

    s = main.proveeduria_sugerido(departamento="F&B", user=USUARIO)
    c.cierto(s["filas"], "el endpoint sugiere")
    c.cierto(s["ocupacion_pct"] > 0, "con la ocupacion a la vista")
    c.cierto(s["desde"] and s["hasta"], "y las fechas con las que se calculo")

    # El periodo se puede cambiar: no es lo mismo pedir para una semana que para un mes.
    largo = main.proveeduria_sugerido(departamento="F&B", dias=30, user=USUARIO)
    c.cierto(largo["hasta"] > s["hasta"], "se puede pedir para mas dias")

    raiz = RAIZ
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    c.cierto("function verSugeridoPv(" in pantalla, "la pantalla tiene «Qué pedir»")
    c.cierto("function ordenDesdeSugeridoPv(" in pantalla,
             "y lleva de la sugerencia a la orden sin copiar nada a mano")
    i = pantalla.find("function pintarSugeridoPv(")
    fn = pantalla[i:pantalla.find("\n// De la sugerencia", i)]
    c.cierto("ocupacion_pct" in fn, "enseña con que ocupacion se calculo")
    c.cierto("s.desde" in fn and "s.hasta" in fn, "y para que fechas")
    c.cierto("sin_nivel" in fn, "y cuantos productos quedan fuera por no tener minimo")


# ---------------------------------------------------------------------------
# Fase 5: el consumo, enlazado con la operacion
# ---------------------------------------------------------------------------

def _salida_el_dia(conn, dia, codigo, cantidad, depto="F&B", tipo="ORDEN INTERNA"):
    """Una salida de bodega CON FECHA, que es lo que el consumo mira."""
    import proveeduria as pv
    doc, _ = pv.registrar(conn, tipo, depto, [{"codigo": codigo, "cantidad": cantidad}],
                          fecha=dia.isoformat(), usuario="bodega")
    return doc


def el_consumo_se_mide_POR_PERSONA_y_no_en_total(c):
    """LA CIFRA QUE IMPORTA NO ES EL TOTAL. Una semana llena gasta mas que una vacia y
    eso no dice nada; lo que dice algo es que el costo por huesped-noche suba con la
    misma ocupacion.

    Esa pregunta no se podia hacer en la hoja: habria que cruzar a mano el historial con
    una ocupacion que esta escrita en otra celda y que nadie actualiza."""
    import datetime as dt

    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        ayer = dt.date.today() - dt.timedelta(days=1)
        _llenar_el_lodge(conn, 10, dias=10)
        # El aceite vale 5279 colones. Salen 4.
        _salida_el_dia(conn, ayer, "108194", 4)

        d = pv.consumo(conn, dias=3)
        c.cierto(d["pax_noche"] > 0, "sabe cuanta gente hubo")
        c.igual(d["costo"], 527900 * 4, "valora lo que salio con el precio del catalogo")
        c.igual(d["costo_por_pax"], int(round(d["costo"] / d["pax_noche"])),
                "y lo divide entre los huesped-noche")

        # CON EL DOBLE DE GENTE Y EL MISMO GASTO, el costo por persona BAJA. Es lo que
        # el total no puede decir.
        por_pax_antes = d["costo_por_pax"]
        _llenar_el_lodge(conn, 20, dias=10)
        d2 = pv.consumo(conn, dias=3)
        c.igual(d2["costo"], d["costo"], "el total es el mismo")
        c.cierto(d2["costo_por_pax"] < por_pax_antes,
                 "pero el costo por persona baja, que es lo que se compara")
    finally:
        conn.close()


def el_ajuste_de_inventario_no_es_consumo(c):
    """UN AJUSTE ES UNA CORRECCION DE CONTEO: aparece una caja olvidada, o faltaba
    registrar una compra. Meterlo en el consumo le echa a la cocina la culpa de un error
    de inventario.

    Pero tampoco se esconde: un periodo con muchos ajustes dice que el inventario no
    esta cuadrando, y eso tambien hay que verlo."""
    import datetime as dt

    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        ayer = dt.date.today() - dt.timedelta(days=1)
        _llenar_el_lodge(conn, 10, dias=10)
        _salida_el_dia(conn, ayer, "108194", 2)
        solo_salida = pv.consumo(conn, dias=3)

        # Un ajuste hacia abajo: habia 6 y se cuentan 1.
        pv.registrar(conn, "AJUSTE INVENTARIO", "F&B",
                     [{"codigo": "108194", "contado": 1}],
                     fecha=ayer.isoformat(), usuario="bodega")
        con_ajuste = pv.consumo(conn, dias=3)

        c.igual(con_ajuste["costo"], solo_salida["costo"],
                "el ajuste NO sube el consumo")
        c.cierto(con_ajuste["ajustes_costo"] > 0,
                 "pero se enseña aparte, para que no desaparezca")
    finally:
        conn.close()


def la_merma_se_cuenta_aparte_del_consumo(c):
    """Tirar producto es gasto, pero no es lo mismo que haberlo servido. Juntarlos
    esconde justo lo que hay que mirar."""
    import datetime as dt

    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        ayer = dt.date.today() - dt.timedelta(days=1)
        _llenar_el_lodge(conn, 10, dias=10)
        _salida_el_dia(conn, ayer, "108194", 2)
        _salida_el_dia(conn, ayer, "108194", 1, tipo="MERMA")

        d = pv.consumo(conn, dias=3)
        c.igual(d["costo"], 527900 * 2, "el consumo es solo lo que salio para servir")
        c.igual(d["merma"], 527900 * 1, "y la merma va en su propia cifra")
        fnb = [b for b in d["bodegas"] if b["departamento"] == "F&B"][0]
        c.igual(fnb["merma_costo"], 527900, "tambien por bodega")
    finally:
        conn.close()


def cada_bodega_se_divide_entre_lo_que_le_toca(c):
    """La cocina se divide entre huespedes; housekeeping entre habitaciones. Y el
    comedor del STAFF no se divide entre nada: se reparte entre el personal, y cuanta
    gente trabaja ese dia no esta en este sistema.

    Inventar que se divide entre los huespedes daria un numero que parece bueno y no
    significa nada — el comedor del staff no come mas porque el hotel este lleno."""
    import datetime as dt

    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        ayer = dt.date.today() - dt.timedelta(days=1)
        _llenar_el_lodge(conn, 10, dias=10)
        # Se le da ficha a un producto en cada bodega para poder sacarlo.
        conn.execute("UPDATE pv_producto SET departamento = 'HOUSEKEEPING' "
                     "WHERE codigo = 'SINPRE'")
        conn.execute("UPDATE pv_producto SET valor_unitario = 100000 "
                     "WHERE codigo = 'SINPRE'")
        conn.commit()
        _salida_el_dia(conn, ayer, "108194", 2, depto="F&B")
        _salida_el_dia(conn, ayer, "SINPRE", 2, depto="HOUSEKEEPING")
        _salida_el_dia(conn, ayer, "ARSU", 2, depto="STAFF COMEDOR")

        d = pv.consumo(conn, dias=3)
        por_depto = {b["departamento"]: b for b in d["bodegas"]}
        c.igual(por_depto["F&B"]["base"], "pax", "la cocina se divide entre huespedes")
        c.igual(por_depto["HOUSEKEEPING"]["base"], "habitacion",
                "housekeeping entre habitaciones")
        c.igual(por_depto["STAFF COMEDOR"]["base"], None,
                "y el comedor del staff entre nada")
        c.igual(por_depto["STAFF COMEDOR"]["por_unidad"], None,
                "asi que no se le inventa una cifra por persona")
        c.cierto(por_depto["F&B"]["por_unidad"] > 0, "las otras si la tienen")
        c.cierto(por_depto["HOUSEKEEPING"]["por_unidad"] > 0, "")
        c.cierto(por_depto["HOUSEKEEPING"]["cuantos"] != por_depto["F&B"]["cuantos"],
                 "y cada una con su propio denominador, no el mismo")
    finally:
        conn.close()


def el_consumo_se_compara_con_el_periodo_anterior(c):
    """Un numero suelto no se puede juzgar. Lo que hace util la cifra es «subio un 40%
    por huesped contra los siete dias anteriores»."""
    import datetime as dt

    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        hoy = dt.date.today()
        _llenar_el_lodge(conn, 10, dias=20)
        # Mismo gasto en los dos periodos de 3 dias: la variacion tiene que ser 0.
        _salida_el_dia(conn, hoy - dt.timedelta(days=1), "108194", 3)
        _salida_el_dia(conn, hoy - dt.timedelta(days=5), "108194", 3)
        igual = pv.consumo(conn, dias=3)
        c.igual(igual["anterior"]["desde"],
                (dt.date.fromisoformat(igual["desde"]) - dt.timedelta(days=3)).isoformat(),
                "el periodo anterior es igual de largo y pegado al de ahora")
        c.igual(igual["variacion_pct"], 0, "mismo gasto por persona: 0%")

        # Se duplica el gasto del periodo de ahora.
        _salida_el_dia(conn, hoy - dt.timedelta(days=1), "108194", 3)
        doble = pv.consumo(conn, dias=3)
        c.igual(doble["variacion_pct"], 100, "el doble por persona: +100%")
    finally:
        conn.close()


def el_consumo_del_dia_de_hoy_no_entra(c):
    """Hoy todavia no termino. Metiendolo, la cifra de la mañana pareceria siempre
    buenisima y la de la noche siempre mala, sin que nada hubiera cambiado."""
    import datetime as dt

    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        hoy = dt.date.today()
        _llenar_el_lodge(conn, 10, dias=10)
        _salida_el_dia(conn, hoy, "108194", 9)       # hoy: no cuenta
        d = pv.consumo(conn, dias=3)
        c.igual(d["hasta"], (hoy - dt.timedelta(days=1)).isoformat(),
                "el periodo termina ayer")
        c.igual(d["costo"], 0, "lo de hoy todavia no cuenta")
    finally:
        conn.close()


def la_pantalla_de_consumo_dice_con_que_lo_calculo(c):
    """Una cifra de bodega que no dice de donde sale no se usa para decidir: se mira una
    vez y se deja de mirar."""
    conn, _, _ = _importar()
    conn.close()
    import main

    d = main.proveeduria_consumo(user=USUARIO)
    for clave in ("desde", "hasta", "pax_noche", "habitacion_noche", "costo",
                  "merma", "ajustes_costo", "anterior", "variacion_pct"):
        c.cierto(clave in d, f"el endpoint devuelve «{clave}»")

    raiz = RAIZ
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    c.cierto("function verConsumoPv(" in pantalla, "la pantalla tiene «Consumo»")
    i = pantalla.find("function pintarConsumoPv(")
    fn = pantalla[i:pantalla.find("\n// ---------- Qué pedir", i)]
    c.cierto("costo_por_pax" in fn, "enseña el costo por huesped-noche")
    c.cierto("variacion_pct" in fn, "y como va contra el periodo anterior")
    c.cierto("pax_noche" in fn and "habitacion_noche" in fn,
             "diciendo entre cuanta gente lo dividio")
    c.cierto("ajustes_costo" in fn, "los ajustes se enseñan aparte")
    c.cierto("precio del catálogo" in fn,
             "y se dice con que precio esta valorado todo")


# ---------------------------------------------------------------------------
# Los niveles puestos a mano, y la lista para trabajar fuera
# ---------------------------------------------------------------------------

def el_minimo_se_puede_poner_desde_la_pantalla(c):
    """LA HOJA NO LOS TIENE TODOS: de las once bodegas del lodge, solo cuatro traen
    niveles. Sin ellos el pedido sugerido no puede decir nada de las otras seis, y hasta
    ahora la unica forma de ponerlos era editar el Excel y reimportar."""
    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        conn.execute("DELETE FROM pv_nivel")
        conn.commit()
        _llenar_el_lodge(conn, 30)
        c.igual(pv.pedido_sugerido(conn, departamento="F&B")["filas"], [],
                "sin niveles no hay nada que sugerir")

        pv.guardar_nivel(conn, "108194", "F&B", 5, 40, usuario="bodega")
        s = pv.pedido_sugerido(conn, departamento="F&B")
        c.cierto([f for f in s["filas"] if f["codigo"] == "108194"],
                 "puesto desde la pantalla, el pedido ya lo sugiere")

        guardado = conn.execute(
            "SELECT minimo, maximo, origen, actualizado_por FROM pv_nivel "
            "WHERE codigo = '108194' AND departamento = 'F&B'").fetchone()
        c.igual((guardado["minimo"], guardado["maximo"]), (5.0, 40.0), "con sus numeros")
        c.igual(guardado["origen"], "APP", "marcado como puesto aqui")
        c.igual(guardado["actualizado_por"], "bodega", "y por quien")

        # LOS DOS VACIOS BORRAN EL NIVEL: «sin nivel» y «nivel cero» no son lo mismo. Con
        # un cero, el pedido diria que de ese producto no hace falta tener nada.
        c.igual(pv.guardar_nivel(conn, "108194", "F&B", "", "", usuario="bodega"), None,
                "los dos vacios borran el nivel")
        c.igual(conn.execute(
            "SELECT COUNT(*) FROM pv_nivel WHERE codigo = '108194'").fetchone()[0], 0,
            "y no queda un cero en su lugar")
    finally:
        conn.close()


def el_maximo_no_puede_ser_menor_que_el_minimo(c):
    """El objetivo interpola entre los dos. Al reves, el pedido BAJA cuanto mas lleno
    este el lodge — lo contrario de lo que nadie espera, y sin ningun error."""
    import proveeduria as pv

    conn, _, _ = _importar()
    try:
        for mn, mx, pedazo in ((10, 5, "menor que el mínimo"),
                               (-1, 5, "negativos"),
                               ("mucho", 5, "números")):
            try:
                pv.guardar_nivel(conn, "108194", "F&B", mn, mx, usuario="bodega")
                c.cierto(False, f"tenia que rechazar {mn}/{mx}")
            except ValueError as e:
                c.cierto(pedazo in str(e), f"y decir por que ({pedazo})")
        try:
            pv.guardar_nivel(conn, "NOEXISTE", "F&B", 1, 2, usuario="bodega")
            c.cierto(False, "un codigo que no esta en el catalogo tenia que rechazarse")
        except ValueError as e:
            c.cierto("catálogo" in str(e), "y se dice por que")
        # Iguales SI se puede: hay productos de los que siempre se tiene la misma
        # cantidad, llene o vacio. En la hoja del lodge los hay.
        c.cierto(pv.guardar_nivel(conn, "108194", "F&B", 6, 6, usuario="bodega"),
                 "minimo y maximo iguales se aceptan")
    finally:
        conn.close()


def reimportar_la_hoja_no_borra_los_niveles_puestos_a_mano(c):
    """EL MISMO FALLO QUE YA ESTABA ARREGLADO PARA LOS MOVIMIENTOS, y que estaba otra vez
    aqui: la importacion borraba pv_nivel ENTERA. Seis bodegas no tienen ningun nivel en
    la hoja, asi que son justo las que se ponen a mano — y las que lo perderian la
    siguiente vez que alguien importara «para actualizar»."""
    import proveeduria as pv
    import proveeduria_excel as pvx

    conn, _, _ = _importar()
    try:
        # Uno en una bodega que la hoja no trae, y otro PISANDO uno que si trae.
        pv.guardar_nivel(conn, "108194", "RECEPCION", 3, 9, usuario="bodega")
        pv.guardar_nivel(conn, "108194", "F&B", 99, 199, usuario="bodega")

        ruta = os.path.join(os.environ.get("HOTEL_DATA_DIR") or ".",
                            "hoja_de_prueba.xlsx")
        pvx.cargar(conn, pvx.leer(ruta), usuario="pruebas")

        puestos = {(r[0], r[1]): (r[2], r[3], r[4]) for r in conn.execute(
            "SELECT codigo, departamento, minimo, maximo, origen FROM pv_nivel")}
        c.igual(puestos.get(("108194", "RECEPCION")), (3.0, 9.0, "APP"),
                "el de la bodega que la hoja no trae SOBREVIVE")
        c.igual(puestos.get(("108194", "F&B")), (99.0, 199.0, "APP"),
                "y el puesto a mano manda sobre el de la hoja, que no sabe del cambio")
        c.cierto(puestos.get(("111180", "BAR EL BOSQUE")),
                 "los de la hoja se recargan igual")
    finally:
        conn.close()


def la_lista_de_lo_que_hay_que_revisar_se_puede_bajar(c):
    """NO LO ARREGLA EL SISTEMA: cual de los dos productos con el mismo codigo vale, o si
    un stock negativo es una compra sin registrar, lo decide proveeduria. Y eso se
    trabaja en una lista, tachando, al lado de la bodega. Dejarlo solo en pantalla es
    pedirle a alguien que lo copie a mano, y entonces no se hace."""
    import proveeduria as pv
    import proveeduria_excel as pvx

    conn, _, _ = _importar()
    try:
        rev = pv.revisiones(conn)
        buf = pvx.excel_de_revisiones(rev)
    finally:
        conn.close()

    celdas = _celdas_excel(buf)
    texto = " | ".join(celdas)
    c.cierto("Stock negativo" in texto or "111180" in texto,
             "lleva los stocks negativos")
    c.cierto("FANTASMA" in texto, "y los movimientos sin ficha")
    c.cierto("SINPRE" in texto, "y los productos sin precio")
    # CADA PROBLEMA EN SU PESTAÑA: son tres trabajos distintos y los hace gente distinta.
    from openpyxl import load_workbook
    buf.seek(0)
    wb = load_workbook(buf)
    c.igual(len(wb.sheetnames), 3, "una pestaña por problema")
    for ws in wb:
        c.cierto(len(str(ws["A1"].value or "")) > 30,
                 f"«{ws.title}» explica arriba que hay que hacer con esa lista")

    import main
    r = main.proveeduria_revisiones_excel(user=USUARIO)
    c.cierto("spreadsheetml" in r.media_type, "se descarga como Excel")
    c.cierto("por_revisar" in r.headers.get("content-disposition", ""),
             "con un nombre que dice lo que es")


def la_pantalla_deja_poner_el_nivel_donde_se_mira_el_stock(c):
    """En otra pantalla no se pondrian nunca. Se mira «cuanto hay» y se piensa «y cuanto
    deberia haber»: es el mismo momento."""
    conn, _, _ = _importar()
    conn.close()
    import main

    d = main.proveeduria_existencias(departamento="F&B", user=USUARIO)
    c.cierto(all("minimo" in f for f in d["filas"]),
             "pidiendo una bodega, cada fila trae su minimo")
    c.cierto(all("maximo" in f for f in d["filas"]), "y su maximo")
    general = main.proveeduria_existencias(user=USUARIO)
    c.cierto(all("minimo" not in f for f in general["filas"]),
             "en el general no, porque el nivel es de una bodega y no del producto")

    raiz = RAIZ
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    c.cierto("function guardarNivelPv(" in pantalla, "la pantalla guarda el nivel")
    c.cierto("function descargarRevisionesPv(" in pantalla,
             "y deja bajar la lista de lo que hay que revisar")
    i = pantalla.find("async function guardarNivelPv(")
    fn = pantalla[i:pantalla.find("\nasync function descargarRevisionesPv(", i)]
    # SE GUARDA SIN REDIBUJAR: poner niveles es teclear veinte numeros seguidos.
    c.cierto("loadProveeduria(" not in fn,
             "sin recargar la pantalla entre un numero y el siguiente")
    c.cierto("campo.value" in fn,
             "y si el servidor dice que no, el campo vuelve a lo que habia")


def el_boton_no_le_aparece_a_nadie_hasta_que_se_enciende(c):
    """LO PIDIO EL LODGE: «que sea un boton aparte, que mientras trabajemos en el la app
    pueda seguir funcionando de forma normal».

    Un permiso nuevo metido en PANTALLAS le sale de golpe a todo el que no tenga permisos
    propios, porque los roles dan «todo». Que a los catorce usuarios les aparezca una
    pantalla a medio hacer es justo lo contrario de lo que se pidio."""
    import auth

    claves = {k for k, _ in auth.PANTALLAS}
    c.cierto("proveeduria" in claves, "el permiso existe")
    c.cierto("proveeduria" in auth.NO_AUTOMATICAS, "y NO se reparte solo")
    for rol in ("recepcion", "gerencia", "staff"):
        c.cierto("proveeduria" not in auth.POR_ROL[rol],
                 f"el rol «{rol}» no lo recibe automaticamente")
    for perfil in ("Recepción", "Gerencia", "Solo lectura"):
        c.cierto("proveeduria" not in auth.PERFILES[perfil],
                 f"el perfil «{perfil}» tampoco")
    # Pero SE PUEDE encender, que es el punto: hay un perfil para quien lleva la bodega.
    c.igual(auth.PERFILES["Proveeduría"]["proveeduria"], "escribir",
            "y existe el perfil de Proveeduria para darselo a quien corresponde")
    # Y el permiso se limpia como cualquier otro, o no se podria guardar.
    c.igual(auth.limpiar_permisos({"proveeduria": "escribir"}),
            {"proveeduria": "escribir"}, "el permiso se puede guardar")


def al_arrancar_se_le_enciende_SOLO_a_quien_administra(c):
    """LO PIDIO EL LODGE: «haz que el boton solo me aparezca a mi como admin y luego
    otorgo permisos al resto».

    QUIEN ES ADMIN NO SE ADIVINA POR EL ROL: se mira quien puede administrar usuarios,
    que es la definicion que ya usa el resto del sistema y la unica que no depende de
    como se llame el rol en cada instalacion.

    Y NO BASTABA CON PONERLO EN POR_ROL: los usuarios de la base YA tienen su rejilla
    guardada, asi que POR_ROL no se mira. Sin esta migracion el boton no le aparece a
    nadie — que es justo lo contrario de lo que se pidio."""
    import json

    import init_db

    import contextlib
    import io

    import auth

    conn = comun.base_limpia()
    try:
        # Las cuentas iniciales NO las crea init_db: las siembra auth al arrancar el
        # servidor. En una base recien hecha no hay ninguna, asi que se siembran aqui.
        with contextlib.redirect_stdout(io.StringIO()):
            auth.seed_default_users(conn)
        # Se parte de las cuentas que el arranque ya creo y se les deja la rejilla como
        # la tiene el lodge: 'usuarios: escribir' solo para quien administra. No se
        # insertan usuarios a mano, para no depender de las columnas de esa tabla.
        def rejilla_de(nombre, administra):
            r = {"dashboard": "ver"}
            if administra:
                r["usuarios"] = "escribir"
            conn.execute("UPDATE usuario SET permisos_json = ? WHERE username = ?",
                         (json.dumps(r), nombre))

        rejilla_de("gerencia", True)
        rejilla_de("recepcion", True)
        rejilla_de("staff", False)
        conn.execute("DELETE FROM sistema_meta WHERE clave = 'proveeduria_repartida'")
        conn.commit()

        c.igual(init_db._proveeduria_para_quien_administra(conn), 2,
                "se le enciende a los dos que administran")

        def tiene(nombre):
            fila = conn.execute(
                "SELECT permisos_json FROM usuario WHERE username = ?",
                (nombre,)).fetchone()
            return json.loads(fila[0]).get("proveeduria")

        c.igual(tiene("gerencia"), "escribir", "quien administra la ve, y puede escribir")
        c.igual(tiene("recepcion"), "escribir", "el otro administrador tambien")
        c.igual(tiene("staff"), None, "quien NO administra no la recibe")

        # CORRE UNA SOLA VEZ. Sin la marca, el dia que alguien le QUITE Proveeduria a un
        # administrador el siguiente arranque se la devolveria.
        rejilla_de("recepcion", True)
        conn.commit()
        c.igual(init_db._proveeduria_para_quien_administra(conn), 0,
                "la segunda vez no toca a nadie")
        c.igual(tiene("recepcion"), None,
                "lo que un administrador quita NO vuelve en el siguiente arranque")
    finally:
        conn.close()


def la_pantalla_pide_las_dos_vistas_y_enseña_lo_que_hay_que_revisar(c):
    """La pantalla es UNA con selector de bodega, no quince. Y las revisiones viajan con
    las existencias: son cifras que estan mal, y quien las enseña tiene que poder decirlo
    en el mismo sitio donde las enseña."""
    conn, _, _ = _importar()
    conn.close()
    import main

    d = main.proveeduria_existencias(user=USUARIO)
    c.cierto(d["filas"], "el general trae filas")
    c.igual(d["departamento"], "", "y se sabe que es el general")
    c.cierto("F&B" in d["departamentos"] and "BAR EL BOSQUE" in d["departamentos"],
             "con la lista de bodegas para los botones")
    c.cierto(d["revisiones"]["negativos"], "y lo que hay que revisar, en la misma puerta")
    c.cierto(d["resumen"]["productos"] > 0, "con su resumen")

    solo_bar = main.proveeduria_existencias(departamento="BAR EL BOSQUE", user=USUARIO)
    c.igual(solo_bar["departamento"], "BAR EL BOSQUE", "y se puede pedir una bodega")
    c.cierto(all(f["departamento"] == "BAR EL BOSQUE" for f in solo_bar["filas"]),
             "que trae solo lo suyo")

    buscado = main.proveeduria_existencias(q="aceite", user=USUARIO)
    c.cierto(buscado["filas"] and all("ACEITE" in f["descripcion"].upper()
                                      for f in buscado["filas"]),
             "el buscador filtra por nombre")

    raiz = RAIZ
    with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    c.cierto("function loadProveeduria(" in pantalla, "la pantalla existe")
    c.cierto("irAPantalla(15)" in pantalla, "con su boton en el menu")
    c.cierto("verRevisionesProveeduria(" in pantalla,
             "y la lista de lo que hay que revisar")
    c.cierto("sin precio" in pantalla,
             "la inversion dice cuando un producto no tiene precio")


# ---------------------------------------------------------------------------
# Fase 6: recibir la orden del proveedor, y la lista por fecha
# ---------------------------------------------------------------------------

def _orden_de_la_hoja(conn, codigo="MIXTO"):
    """El id de una orden de compra de las que trajo la importacion."""
    return conn.execute(
        """SELECT d.id FROM pv_documento d JOIN pv_movimiento m ON m.documento_id = d.id
            WHERE d.tipo = 'ORDEN DE COMPRA' AND d.origen = 'HOJA' AND m.codigo = ?
            LIMIT 1""", (codigo,)).fetchone()[0]


def una_orden_de_la_hoja_se_recibe_desde_la_app(c):
    """ERA UN BOTON PUESTO Y MUERTO. Las 493 ordenes de compra del lodge vinieron de la
    hoja --no hay ni una nacida en la aplicacion-- y 73 esperan mercaderia, la mas vieja
    de agosto. Recibir solo las de la aplicacion dejaba fuera el 100% de lo que hay que
    recibir: el boton estaba en la pantalla y contestaba «se recibe en la hoja», o sea,
    seguir abriendo el Excel para lo unico que se hace a diario con una orden."""
    conn, _, _ = _importar()
    import proveeduria as pv

    doc = _orden_de_la_hoja(conn)
    o = pv.orden(conn, doc)
    c.igual(o["origen"], "HOJA", "la orden viene de la hoja")
    c.igual(o["estado"], "Recibida a medias", "y le falta una linea por llegar")
    antes = _stock(pv.existencias(conn, departamento="F&B"))["MIXTO"]

    pendiente = [l for l in o["lineas"] if l["estado"] != "Recibido"][0]
    o2, _ = pv.recibir(conn, doc, lineas_ids=[pendiente["id"]], usuario="bodega")
    c.igual(o2["estado"], "Recibido", "se recibe desde aqui")
    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["MIXTO"], antes + 7,
            "y la mercaderia entra de verdad a la bodega")

    linea = [l for l in o2["lineas"] if l["id"] == pendiente["id"]][0]
    c.igual(linea["recibido_por"], "bodega", "queda escrito quien la recibio")
    # La fecha de recibido no existe en ningun otro sitio: la hoja guarda la de la orden
    # y nada mas, asi que cuanto tarda un proveedor en entregar no se puede saber.
    c.cierto(linea["recibido_en"], "y cuando")
    conn.close()


def reimportar_la_hoja_no_borra_lo_recibido_aqui(c):
    """LA MISMA TRAMPA QUE YA TENIAN LOS MOVIMIENTOS Y LOS NIVELES, por tercera vez. La
    hoja no sabe de un recibo hecho aqui --se marco despues de exportarla--, asi que al
    recargarla la linea volveria a estar «en camino»: la mercaderia que ESTA en la bodega
    desaparece del inventario y nadie lo ve hasta que alguien mire esa existencia y le
    parezca baja."""
    conn, _, _ = _importar()
    import proveeduria as pv
    import proveeduria_excel as pvx

    doc = _orden_de_la_hoja(conn)
    pendiente = [l for l in pv.orden(conn, doc)["lineas"]
                 if l["estado"] != "Recibido"][0]
    pv.recibir(conn, doc, lineas_ids=[pendiente["id"]], usuario="bodega")
    con_mercaderia = _stock(pv.existencias(conn, departamento="F&B"))["MIXTO"]

    carpeta = os.environ.get("HOTEL_DATA_DIR") or "."
    datos = pvx.leer(os.path.join(carpeta, "hoja_de_prueba.xlsx"))
    cuenta = pvx.cargar(conn, datos, usuario="pruebas")

    c.igual(cuenta["recibos_previos"], 1, "se vio el recibo ANTES de borrar")
    c.igual(cuenta["recibos_conservados"], 1, "y se volvio a poner")
    c.igual(_stock(pv.existencias(conn, departamento="F&B"))["MIXTO"], con_mercaderia,
            "la mercaderia recibida aqui sigue en la bodega")

    o = pv.orden(conn, _orden_de_la_hoja(conn))
    c.igual(o["estado"], "Recibido", "y la orden sigue recibida entera")
    # LA LINEA BUENA, no la primera. Las dos lineas son del mismo producto y la misma
    # bodega: marcando la primera se marcaria la que la hoja YA daba por recibida y la
    # otra volveria a estar en camino, con el stock a medias y sin que nada lo diga.
    marcadas = [l for l in o["lineas"] if l["recibido_en"]]
    c.igual(len(marcadas), 1, "se marco una sola linea")
    c.igual(marcadas[0]["cantidad"], 7, "y es la que estaba esperando, no la otra")
    conn.close()


def la_mercaderia_entra_a_la_bodega_de_la_linea(c):
    """AL DEPARTAMENTO QUE CORRESPONDE. La orden tiene una bodega en la cabecera, pero la
    linea puede traer otra --27 asi en la hoja del lodge-- o no traer ninguna --19--.
    Recibiendo todo contra la cabecera, el jabon que pidio housekeeping aparece en el
    restaurante: el inventario cuadra en total y esta mal en las dos bodegas, que es el
    error que solo se descubre cuando alguien baja a buscar algo y no esta."""
    conn, _, _ = _importar()
    import proveeduria as pv

    # Una orden como las que trae la hoja: cabecera F&B y tres lineas distintas.
    doc = conn.execute(
        "INSERT INTO pv_documento (numero, tipo, fecha, departamento, origen) "
        "VALUES ('900', 'ORDEN DE COMPRA', ?, 'F&B', 'HOJA')",
        (HOY.isoformat(),)).lastrowid
    for codigo, cantidad, depto in (("ARSU", 2, "F&B"),
                                    ("108194", 3, "BAR EL BOSQUE"),
                                    ("KALE", 4, None)):
        conn.execute(
            """INSERT INTO pv_movimiento (documento_id, codigo, descripcion, cantidad,
                   signo, estado, departamento)
               VALUES (?,?,?,?,1,'Pendiente de Ingreso',?)""",
            (doc, codigo, codigo, cantidad, depto))
    conn.commit()

    destinos = {l["codigo"]: l["destino"] for l in pv.orden(conn, doc)["lineas"]}
    c.igual(destinos["108194"], "BAR EL BOSQUE", "la bodega de la linea manda")
    c.igual(destinos["KALE"], "F&B", "y sin bodega en la linea, la de la orden")

    antes_fb = _stock(pv.existencias(conn, departamento="F&B"))
    antes_bar = _stock(pv.existencias(conn, departamento="BAR EL BOSQUE"))
    pv.recibir(conn, doc, usuario="bodega")
    ahora_fb = _stock(pv.existencias(conn, departamento="F&B"))
    ahora_bar = _stock(pv.existencias(conn, departamento="BAR EL BOSQUE"))

    c.igual(ahora_bar["108194"], antes_bar["108194"] + 3, "el aceite entra AL BAR")
    c.igual(ahora_fb["108194"], antes_fb["108194"], "y no al restaurante")
    c.igual(ahora_fb["ARSU"], antes_fb["ARSU"] + 2, "lo del restaurante, al restaurante")
    c.igual(ahora_fb["KALE"], antes_fb["KALE"] + 4,
            "y lo que no decia bodega, a la de la orden")
    conn.close()


def una_linea_sin_bodega_ninguna_no_se_recibe(c):
    """Un ingreso sin departamento no entra en ninguna bodega: quedaria «recibido» y no
    aparecria en ningun inventario, asi que la mercaderia estaria dada por llegada y no se
    podria encontrar. Mejor negarse y decir por que."""
    conn, _, _ = _importar()
    import proveeduria as pv

    doc = conn.execute(
        "INSERT INTO pv_documento (numero, tipo, fecha, departamento, origen) "
        "VALUES ('901', 'ORDEN DE COMPRA', ?, NULL, 'HOJA')",
        (HOY.isoformat(),)).lastrowid
    conn.execute(
        """INSERT INTO pv_movimiento (documento_id, codigo, descripcion, cantidad,
               signo, estado, departamento)
           VALUES (?, 'ARSU', 'Arroz', 5, 1, 'Pendiente de Ingreso', NULL)""", (doc,))
    conn.commit()

    try:
        pv.recibir(conn, doc, usuario="bodega")
        c.cierto(False, "tenia que negarse a recibir sin bodega")
    except ValueError as e:
        c.cierto("bodega" in str(e), "y decir que no se sabe a que bodega entra")
    c.igual(pv.orden(conn, doc)["estado"], "Pendiente de Ingreso",
            "la orden se queda como estaba")
    conn.close()


def las_ordenes_se_piden_por_fecha_y_por_lo_que_falta(c):
    """CON 493 ORDENES LA LISTA NO SE LEE. Y la que habia se cortaba en las 60 ultimas sin
    decirlo: de las 73 que esperan mercaderia, 27 no cabian --y son justo las viejas, las
    que hay que perseguir--.

    Las dos preguntas son distintas y las dos se hacen a diario: «que pedi hoy» y «que
    estoy esperando». La segunda no se puede contestar con un filtro de fecha, porque una
    orden se pide un dia y llega otro."""
    conn, _, _ = _importar()
    import proveeduria as pv
    prov = _proveedor(conn)
    ayer = (HOY - datetime.timedelta(days=1)).isoformat()

    vieja = pv.crear_orden_compra(conn, prov, "F&B",
                                  [{"codigo": "ARSU", "cantidad": 1}],
                                  fecha=ayer, usuario="bodega")
    de_hoy = pv.crear_orden_compra(conn, prov, "F&B",
                                   [{"codigo": "ARSU", "cantidad": 2}], usuario="bodega")

    hoy_iso = HOY.isoformat()
    del_dia = pv.ordenes(conn, desde=hoy_iso, hasta=hoy_iso)
    c.cierto(any(o["id"] == de_hoy["id"] for o in del_dia), "la del dia sale")
    c.cierto(not any(o["id"] == vieja["id"] for o in del_dia), "la de ayer no")
    de_ayer = pv.ordenes(conn, desde=ayer, hasta=ayer)
    c.igual([o["id"] for o in de_ayer], [vieja["id"]], "y eligiendo el dia, aparece")

    pv.recibir(conn, de_hoy["id"], usuario="bodega")
    esperando = pv.ordenes(conn, pendientes=True, limite=300)
    c.cierto(any(o["id"] == vieja["id"] for o in esperando),
             "la de ayer sigue esperando mercaderia")
    c.cierto(not any(o["id"] == de_hoy["id"] for o in esperando),
             "y la que ya llego no")
    # ESTE ES EL MOTIVO DE QUE LA VISTA EXISTA: por fecha de hoy, la orden que hay que
    # recibir no esta en ningun sitio al que se llegue sin acordarse de cuando se pidio.
    c.cierto(not any(o["id"] == vieja["id"]
                     for o in pv.ordenes(conn, desde=hoy_iso, hasta=hoy_iso)),
             "con solo el filtro de fecha, lo pendiente de otro dia no se encuentra")

    cont = pv.conteo_de_ordenes(conn)
    c.igual(cont["total"], pv.cuantas_ordenes(conn), "el recuento cuenta todas")
    c.igual(cont["pendientes"], pv.cuantas_ordenes(conn, pendientes=True),
            "y las que esperan mercaderia")
    c.igual(cont["ultima_fecha"], hoy_iso, "con la fecha de la ultima orden")
    c.cierto(cont["ultima_pendiente"], "y la de la ultima que espera algo")
    c.igual(pv.cuantas_ordenes(conn, desde=ayer, hasta=ayer), 1,
            "el recuento usa el MISMO filtro que la lista")
    conn.close()


def la_lista_de_ordenes_dice_lo_que_deja_fuera(c):
    """UN FILTRO QUE VACIA LA LISTA SE LEE COMO «NO HAY ORDENES», y son dos cosas muy
    distintas. Con 493 ordenes y 73 esperando mercaderia, una pantalla que abre en el dia
    y no dice nada mas convierte en invisible todo lo demas."""
    conn, _, _ = _importar()
    conn.close()
    import main

    manana = (HOY + datetime.timedelta(days=1)).isoformat()
    d = main.proveeduria_compras(desde=manana, hasta=manana, user=USUARIO)
    c.igual(d["ordenes"], [], "manana todavia no hay ninguna")
    c.cierto(d["conteo"]["total"] > 0, "pero la pantalla sabe cuantas hay en total")
    c.igual(d["conteo"]["ultima_fecha"], HOY.isoformat(), "y de cuando es la ultima")
    c.cierto(d["conteo"]["pendientes"] > 0, "y cuantas esperan mercaderia")
    c.igual(d["filtro"]["desde"], manana, "la respuesta dice con que filtro se armo")

    d2 = main.proveeduria_compras(limite=1, user=USUARIO)
    c.igual(len(d2["ordenes"]), 1, "se puede pedir un tope")
    c.cierto(d2["hay_mas"], "y se avisa de que hay mas, en vez de parecer completa")
    c.cierto(not main.proveeduria_compras(limite=300, user=USUARIO)["hay_mas"],
             "sin corte, no se avisa de nada")

    pendientes = main.proveeduria_compras(pendientes=True, limite=300,
                                          user=USUARIO)["ordenes"]
    c.cierto(pendientes, "se pueden pedir solo las que esperan mercaderia")
    c.cierto(all(o["recibidas"] < o["lineas_total"] for o in pendientes),
             "y todas tienen algo sin recibir")


def la_pantalla_abre_en_el_dia_y_deja_llegar_a_lo_pendiente(c):
    """Lo que la pantalla tiene que hacer con todo esto: abrir en el dia, dejar elegir
    otra fecha, llegar a lo que espera mercaderia, y decir a que bodega va a entrar lo
    que se tilde ANTES de tocar el boton -- despues ya no sirve de nada."""
    with open(os.path.join(RAIZ, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()

    c.cierto('window._pvFiltroCompras = { vista: "dia"' in pantalla,
             "la lista abre en el dia")
    i = pantalla.find("function pintarComprasPv(")
    lista = pantalla[i:pantalla.find("async function descargarOrdenPv(", i)]
    c.cierto(i > 0 and "verComprasPv({vista:'dia', fecha:this.value})" in lista,
             "cambiar la fecha recarga la lista")
    c.cierto("boton(\"pendientes\"" in lista,
             "y hay por donde llegar a lo que espera mercaderia")
    c.cierto("c.ultima_fecha" in lista,
             "un dia sin ordenes dice de cuando es la ultima, en vez de parecer vacio")
    c.cierto("d.hay_mas" in lista, "y avisa cuando la lista se corta")
    # Las 493 ordenes de la hoja no traen precio en ninguna linea. Un «₡0» al lado de
    # «faltan 14 precios» se lee como que esa compra no cuesta nada.
    c.cierto("o.lineas_sin_precio >= o.lineas_total" in lista,
             "una orden sin ningun precio dice «sin precios», no cero")

    j = pantalla.find("async function abrirOrdenPv(")
    modal = pantalla[j:pantalla.find("async function marcarPedidaPv(", j)]
    # Que la IMPRIMA, no que la nombre. La misma celda usa `l.destino` en el estilo para
    # resaltar cuando no coincide con la cabecera, asi que buscar «l.destino» a secas
    # pasaba igual con la celda enseñando la bodega de la orden. Lo destape deshaciendolo.
    c.cierto(j > 0 and "escaparHTML(l.destino" in modal,
             "cada linea dice a que bodega entra")
    c.cierto('onchange="resumirRecibirPv()"' in modal,
             "y el recuento se rehace al tildar y destildar")
    c.cierto("function resumirRecibirPv(" in pantalla, "ese recuento existe")
    c.cierto("marcadas.bodegas.join" in pantalla,
             "y al recibir se dice a que bodega entro la mercaderia")

    # Y una orden recien creada tiene que SALIR en la lista. Con el filtro puesto en otro
    # dia, crearla dejaba un aviso de «orden creada» y una lista donde no estaba.
    for crear in ("guardarNuevaCompraPv", "ordenDesdeSugeridoPv"):
        i = pantalla.find(f"function {crear}(")
        cuerpo = pantalla[i:pantalla.find("\n}", pantalla.find("verComprasPv(", i))]
        c.cierto(i > 0 and 'verComprasPv({ vista: "dia"' in cuerpo,
                 f"{crear} deja la lista en el dia de la orden nueva")


PRUEBAS = [
    el_stock_es_una_resta_y_no_una_columna,
    una_orden_pedida_no_es_mercaderia_en_bodega,
    cada_departamento_lleva_su_bodega_y_el_general_las_suma,
    ingreso_y_Ingreso_son_lo_mismo,
    el_codigo_que_excel_devuelve_con_coma_es_el_mismo_producto,
    una_orden_puede_llegar_a_medias,
    un_espacio_al_final_del_codigo_no_pierde_la_mercaderia,
    el_codigo_repetido_no_se_funde_en_silencio,
    lo_que_la_hoja_trae_mal_se_enseña,
    sin_precio_no_se_inventa_un_cero,
    importar_dos_veces_da_lo_mismo_y_no_el_doble,
    las_pestañas_calculadas_no_entran_como_un_segundo_inventario,
    ninguna_fila_se_pierde_en_silencio,
    el_documento_se_guarda_una_vez_y_no_por_linea,
    el_restaurante_registra_una_salida_de_bodega,
    una_salida_que_deja_la_bodega_en_negativo_avisa_pero_no_bloquea,
    el_ajuste_se_escribe_como_lo_contado_y_no_como_la_diferencia,
    no_se_mueve_un_codigo_que_no_esta_en_el_catalogo,
    reimportar_la_hoja_no_borra_lo_registrado_en_la_app,
    un_movimiento_mal_puesto_se_puede_borrar_y_el_de_la_hoja_no,
    la_numeracion_sigue_la_que_ya_hay,
    la_pantalla_deja_registrar_las_tres_cosas,
    una_orden_de_compra_no_suma_al_inventario_hasta_que_llega,
    una_orden_se_puede_recibir_a_medias,
    solicitada_y_pedida_al_proveedor_son_dos_cosas,
    la_orden_guarda_el_precio_que_se_pidio,
    una_orden_de_compra_no_se_arma_con_cualquier_cosa,
    el_PDF_de_la_orden_lleva_la_direccion_de_ENTREGA,
    el_PDF_dice_cuando_el_total_esta_incompleto,
    la_pantalla_tiene_el_ciclo_entero_de_la_compra,
    la_ocupacion_sale_de_UNA_funcion_para_las_dos_pantallas,
    el_cuarto_de_guias_no_sube_la_ocupacion,
    el_pedido_sugerido_se_mueve_con_la_ocupacion,
    lo_que_ya_esta_pedido_no_se_vuelve_a_pedir,
    no_se_le_inventa_un_minimo_a_nadie,
    los_niveles_vienen_de_la_hoja_y_son_por_bodega,
    se_dice_a_que_proveedor_toca_pedirle_hoy,
    la_pantalla_lleva_del_sugerido_a_la_orden,
    el_consumo_se_mide_POR_PERSONA_y_no_en_total,
    el_ajuste_de_inventario_no_es_consumo,
    la_merma_se_cuenta_aparte_del_consumo,
    cada_bodega_se_divide_entre_lo_que_le_toca,
    el_consumo_se_compara_con_el_periodo_anterior,
    el_consumo_del_dia_de_hoy_no_entra,
    la_pantalla_de_consumo_dice_con_que_lo_calculo,
    el_minimo_se_puede_poner_desde_la_pantalla,
    el_maximo_no_puede_ser_menor_que_el_minimo,
    reimportar_la_hoja_no_borra_los_niveles_puestos_a_mano,
    la_lista_de_lo_que_hay_que_revisar_se_puede_bajar,
    la_pantalla_deja_poner_el_nivel_donde_se_mira_el_stock,
    el_boton_no_le_aparece_a_nadie_hasta_que_se_enciende,
    al_arrancar_se_le_enciende_SOLO_a_quien_administra,
    la_pantalla_pide_las_dos_vistas_y_enseña_lo_que_hay_que_revisar,
    una_orden_de_la_hoja_se_recibe_desde_la_app,
    reimportar_la_hoja_no_borra_lo_recibido_aqui,
    la_mercaderia_entra_a_la_bodega_de_la_linea,
    una_linea_sin_bodega_ninguna_no_se_recibe,
    las_ordenes_se_piden_por_fecha_y_por_lo_que_falta,
    la_lista_de_ordenes_dice_lo_que_deja_fuera,
    la_pantalla_abre_en_el_dia_y_deja_llegar_a_lo_pendiente,
]


if __name__ == "__main__":
    sys.exit(comun.correr("proveeduria", PRUEBAS))
