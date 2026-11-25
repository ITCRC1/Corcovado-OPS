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
    el_boton_no_le_aparece_a_nadie_hasta_que_se_enciende,
    al_arrancar_se_le_enciende_SOLO_a_quien_administra,
    la_pantalla_pide_las_dos_vistas_y_enseña_lo_que_hay_que_revisar,
]


if __name__ == "__main__":
    sys.exit(comun.correr("proveeduria", PRUEBAS))
