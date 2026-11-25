"""Proveeduría: el inventario del lodge.

QUÉ REEMPLAZA. Una hoja de cálculo de 19 pestañas («INVENTARIO CWL»). De esas 19, solo
cuatro tienen datos —el historial de movimientos, los productos, los proveedores y el
plan de cuentas—; las otras quince son vistas calculadas con SUMIFS sobre el historial.
Las nueve «INV_<área>» son literalmente la misma fórmula con el departamento cambiado.

De ahí la regla que ordena todo este módulo: EL STOCK NO ES UN DATO, ES UNA RESTA. No se
guarda en ninguna columna. En el momento en que existiera una columna `stock` y además el
libro de movimientos, los dos dirían cosas distintas y no habría forma de saber cuál
creer — que es exactamente lo que ya le pasa a la hoja consigo misma (ver `revisiones`).

LA FÓRMULA ES LA DE LA HOJA, sin cambiarla:

    stock = Σ(entradas RECIBIDAS de ese código en ese departamento)
          − Σ(salidas de ese código en ese departamento)

La asimetría es de la hoja y es correcta: una orden de compra pedida y no llegada no es
mercadería que haya en la bodega, pero una salida es una salida en cuanto se anota.

POR QUÉ MERECE DEJAR DE SER UNA HOJA. Por una sola cosa, y es la que Excel no puede
hacer: el pedido sugerido depende de la OCUPACIÓN, y en la hoja la ocupación es un número
escrito a mano en `INVENTARIO_GENERAL!C1`. Esta aplicación ya sabe la ocupación real, día
por día, y además cuántos desayunan, cuántos cenan en cada restaurante y cuánta ropa entra
a lavandería. Todo lo demás —registrar, sumar, imprimir— la hoja lo hacía bien.
"""
import datetime

# Los tipos de documento que mueven inventario, tal como los escribe la hoja.
TIPOS = ("ORDEN DE COMPRA", "ORDEN INTERNA", "AJUSTE INVENTARIO", "MERMA",
         "NOTA DE CREDITO")

# El ciclo de una orden, también de la hoja. SOLO «Recibido» cuenta como existencias.
ESTADOS = ("Solicitado", "Pendiente de Ingreso", "Recibido")
ESTADO_EN_BODEGA = "Recibido"

ENTRA, SALE = 1, -1


def centimos(valor):
    """Un precio a céntimos enteros. None si no hay precio.

    EN ENTEROS porque 395 de los 1.464 productos de la hoja vienen sin precio y los que
    sí lo traen tienen decimales: sumando en coma flotante, la inversión total no cuadra
    con la suma de cada línea. Es lo mismo que ya se hace con los precios de lavandería.
    """
    if valor is None or valor == "":
        return None
    try:
        return int(round(float(str(valor).replace(",", ".").strip()) * 100))
    except (TypeError, ValueError):
        return None


def normalizar_codigo(valor):
    """El código de un producto, comparable.

    Excel guarda los códigos numéricos como números, así que «108194» vuelve como
    «108194.0». Sin esto, el mismo producto es dos productos distintos según de qué
    pestaña venga, y el stock se parte en dos mitades que nadie suma.
    """
    texto = "" if valor is None else str(valor).strip()
    if texto.endswith(".0") and texto[:-2].replace("-", "").isdigit():
        texto = texto[:-2]
    return texto.upper()


def normalizar_texto(valor):
    return " ".join(str(valor or "").split())


def signo_de(valor):
    """«INGRESO»/«Ingreso» -> +1, «SALIDA»/«Salida» -> -1. None si no se entiende.

    SE GUARDA EL SIGNO Y NO EL TEXTO. En la hoja el tipo viene escrito de dos formas
    —«INGRESO» y «Ingreso» (308 filas), «SALIDA» y «Salida» (73)— y a Excel le da igual
    porque SUMIFS no distingue mayúsculas. Portado tal cual a SQL, esas 381 filas
    desaparecerían del stock sin dar ningún error: el inventario diría de menos y nadie
    sabría por qué. Con un signo numérico el problema no puede volver.
    """
    t = normalizar_texto(valor).upper()
    if t.startswith("INGRESO") or t in ("ENTRADA", "COMPRA"):
        return ENTRA
    if t.startswith("SALIDA") or t in ("CONSUMO", "EGRESO"):
        return SALE
    return None


def fecha_iso(valor):
    """La fecha de un movimiento en ISO. '' si no se entiende."""
    if isinstance(valor, datetime.datetime):
        return valor.date().isoformat()
    if isinstance(valor, datetime.date):
        return valor.isoformat()
    texto = normalizar_texto(valor)
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(texto[:19], formato).date().isoformat()
        except ValueError:
            continue
    return ""


# ---------------------------------------------------------------------------
# Las existencias
# ---------------------------------------------------------------------------

def existencias(conn, departamento=None, buscar=None, solo_con_stock=False,
                desglosar=False):
    """Lo que hay en bodega hoy. UNA fila por producto en el general; una fila por
    producto Y departamento cuando se pide el de un departamento.

    CADA DEPARTAMENTO LLEVA SU INVENTARIO APARTE, además del general — lo recordó el
    lodge y es como funciona la hoja: nueve pestañas «INV_<área>» más
    «INVENTARIO_GENERAL». Y el general NO es la lista de las nueve pegadas: es una fila
    por producto con todos sus departamentos sumados. Medido en la hoja: 1.464 filas en
    el general —exactamente el número de productos— contra 532 en RESTAURANTE y 338 en
    BAR. Si el general repitiera el mismo producto una vez por departamento, la pantalla
    enseñaría el aceite cuatro veces y la inversión total saldría bien pero ilegible.

    EN UNA SOLA FUNCIÓN las dos vistas, y aquí está el porqué: en la hoja esta cuenta
    está escrita diez veces, una por pestaña, y ya se separaron — «pedido sugerido» tiene
    TRES fórmulas distintas según dónde se mire. Es el fallo que este sistema lleva
    cuatro arreglos persiguiendo: una regla escrita dos veces acaba diciendo dos cosas.
    """
    # `desglosar` pide el detalle por bodega SIN filtrar por una: es lo que necesita la
    # revisión de stocks negativos, porque un departamento puede estar en rojo mientras
    # el general da positivo, y el que tiene que cuadrar la bodega es el departamento.
    por_departamento = bool(departamento) or desglosar
    donde, params = [], []
    if departamento:
        donde.append("m.departamento = ?")
        params.append(departamento)
    if buscar:
        donde.append("(m.codigo LIKE ? OR UPPER(COALESCE(p.descripcion, m.descripcion))"
                     " LIKE ?)")
        aguja = f"%{normalizar_texto(buscar).upper()}%"
        params += [aguja, aguja]
    filtro = (" WHERE " + " AND ".join(donde)) if donde else ""

    # En el general el departamento que se enseña es el del CATÁLOGO —a qué área
    # pertenece el producto—, no el del movimiento: el movimiento tiene uno por cada
    # bodega que lo tocó, y en una fila que los suma no hay un solo valor que sea cierto.
    columna_depto = "m.departamento" if por_departamento else "p.departamento"
    agrupar = "m.codigo, m.departamento" if por_departamento else "m.codigo"

    # El CASE es la fórmula de la hoja, entera y en un solo sitio: una entrada cuenta
    # SOLO si el documento está recibido; una salida cuenta siempre.
    filas = [dict(r) for r in conn.execute(f"""
        SELECT m.codigo,
               {columna_depto} AS departamento,
               COALESCE(p.descripcion, MAX(m.descripcion)) AS descripcion,
               p.unidad,
               p.valor_unitario,
               p.minimo, p.maximo,
               p.id AS producto_id,
               COUNT(DISTINCT m.departamento) AS bodegas,
               SUM(CASE WHEN m.signo = 1 AND m.estado = '{ESTADO_EN_BODEGA}'
                        THEN m.cantidad ELSE 0 END) AS entradas,
               SUM(CASE WHEN m.signo = -1 THEN m.cantidad ELSE 0 END) AS salidas,
               SUM(CASE WHEN m.signo = 1 AND m.estado != '{ESTADO_EN_BODEGA}'
                        THEN m.cantidad ELSE 0 END) AS en_camino
          FROM pv_movimiento m
          LEFT JOIN pv_producto p ON p.codigo = m.codigo
          {filtro}
         GROUP BY {agrupar}
         ORDER BY COALESCE(p.descripcion, MAX(m.descripcion))""", params)]

    salida = []
    for f in filas:
        f["stock"] = round((f["entradas"] or 0) - (f["salidas"] or 0), 3)
        if solo_con_stock and not f["stock"]:
            continue
        precio = f["valor_unitario"]
        f["inversion"] = int(round(precio * f["stock"])) if precio is not None else None
        # SIN PRECIO NO SE INVENTA UNO. 395 de los 1.464 productos de la hoja vienen sin
        # valor unitario; poniéndoles cero, la inversión total del lodge saldría más baja
        # de lo que es y nadie vería que falta un dato — diría «0» con toda seguridad.
        f["sin_precio"] = precio is None
        f["huerfano"] = f["producto_id"] is None
        salida.append(f)
    return salida


def resumen(filas):
    """Los totales de una lista de existencias, para la cabecera de la pantalla."""
    con_precio = [f for f in filas if f["inversion"] is not None]
    return {
        "productos": len(filas),
        "con_stock": sum(1 for f in filas if f["stock"] > 0),
        "en_cero": sum(1 for f in filas if f["stock"] == 0),
        "negativos": sum(1 for f in filas if f["stock"] < 0),
        "inversion": sum(f["inversion"] for f in con_precio),
        # Cuántos quedan fuera del total, para que la cifra no se lea como completa.
        "sin_precio": sum(1 for f in filas if f["sin_precio"]),
    }


def departamentos(conn):
    """Los departamentos que tienen movimiento, para los botones de la pantalla."""
    return [r[0] for r in conn.execute(
        """SELECT DISTINCT departamento FROM pv_movimiento
            WHERE departamento IS NOT NULL AND departamento != ''
            ORDER BY departamento""")]


# ---------------------------------------------------------------------------
# Registrar movimientos: lo que se hace a diario
# ---------------------------------------------------------------------------

# Lo que se puede registrar desde la pantalla. La ORDEN DE COMPRA no está: tiene su
# propio ciclo —proveedor, cuenta contable, factura, recibido a medias— y es la fase
# siguiente. Meterla aquí a medias sería peor que no tenerla.
TIPOS_QUE_SE_REGISTRAN = ("ORDEN INTERNA", "AJUSTE INVENTARIO", "MERMA")

ORIGEN_HOJA, ORIGEN_APP = "HOJA", "APP"


def siguiente_numero(conn):
    """El número que le toca al próximo documento.

    SIGUE LA NUMERACIÓN QUE YA HAY, no empieza de uno: quien lleva la bodega lee ese
    número en el papel y en la hoja, y que la aplicación arranque en «1» haría que
    convivieran dos series y hubiera que preguntar de cuál es cada documento.

    El choque con la hoja no puede pasar aunque después se reimporte: el origen entra en
    la llave (ver schema.sql).
    """
    fila = conn.execute(
        "SELECT MAX(CAST(numero AS INTEGER)) FROM pv_documento "
        "WHERE numero GLOB '[0-9]*'").fetchone()
    return str((fila[0] or 0) + 1)


def _producto(conn, codigo):
    return conn.execute(
        "SELECT * FROM pv_producto WHERE codigo = ?",
        (normalizar_codigo(codigo),)).fetchone()


def registrar(conn, tipo, departamento, lineas, fecha=None, observaciones="",
              usuario=None, solicitado_por=""):
    """Anota un movimiento de bodega. Devuelve (documento, avisos).

    `lineas` es [{'codigo', 'cantidad'}] para una salida o una merma —la cantidad es lo
    que SALE, en positivo— y [{'codigo', 'contado'}] para un ajuste, donde `contado` es
    lo que se contó físicamente y el sistema calcula la diferencia.

    EL AJUSTE SE ESCRIBE COMO LO QUE SE CONTÓ, no como la diferencia. Quien cuenta la
    bodega tiene delante doce latas, no «menos tres»: pedirle que reste es pedirle que
    haga una cuenta que el sistema puede hacer, y una resta mal hecha en un inventario no
    se descubre hasta el conteo siguiente. Es además lo que arregla los stocks negativos.

    NO BLOQUEA UNA SALIDA QUE DEJA LA BODEGA EN NEGATIVO; AVISA. En la hoja del lodge hay
    53 negativos vivos: si esto bloqueara, el primer día alguien no podría registrar una
    salida real y volvería al Excel. Lo que falta es el ingreso que nadie anotó, y eso se
    arregla con un ajuste, no impidiendo trabajar. Es la misma regla que el spa y los
    horarios del restaurante: avisar y dejar decidir.
    """
    tipo = normalizar_texto(tipo).upper()
    if tipo not in TIPOS_QUE_SE_REGISTRAN:
        raise ValueError("Ese tipo de movimiento no se registra desde aquí. Son: "
                         + ", ".join(TIPOS_QUE_SE_REGISTRAN))
    departamento = normalizar_texto(departamento).upper()
    if not departamento:
        raise ValueError("Falta la bodega: un movimiento sale o entra en alguna.")
    if not lineas:
        raise ValueError("No hay ninguna línea que registrar.")

    es_ajuste = tipo == "AJUSTE INVENTARIO"
    # El stock de esa bodega, de una vez: el ajuste lo necesita para sacar la diferencia.
    actual = {f["codigo"]: f["stock"]
              for f in existencias(conn, departamento=departamento)}

    preparadas, avisos = [], []
    for linea in lineas:
        codigo = normalizar_codigo(linea.get("codigo"))
        if not codigo:
            raise ValueError("Hay una línea sin código de producto.")
        prod = _producto(conn, codigo)
        if not prod:
            # NO SE CREA LA FICHA SOLA. Un código que no está en el catálogo es casi
            # siempre un código mal escrito, y dándole ficha automáticamente se crea un
            # producto fantasma que a partir de ahí parece legítimo.
            raise ValueError(
                f"El código «{codigo}» no está en el catálogo. Revisalo, o agregá el "
                "producto antes de moverlo.")
        if es_ajuste:
            try:
                contado = float(linea.get("contado"))
            except (TypeError, ValueError):
                raise ValueError(f"«{codigo}»: la cantidad contada no se entiende.")
            if contado < 0:
                raise ValueError(f"«{codigo}»: no se puede contar menos que cero.")
            diferencia = round(contado - (actual.get(codigo) or 0), 3)
            if not diferencia:
                continue          # lo contado coincide: no hay nada que anotar
            cantidad, signo = abs(diferencia), (ENTRA if diferencia > 0 else SALE)
        else:
            try:
                cantidad = float(linea.get("cantidad"))
            except (TypeError, ValueError):
                raise ValueError(f"«{codigo}»: la cantidad no se entiende.")
            if cantidad <= 0:
                raise ValueError(f"«{codigo}»: la cantidad tiene que ser mayor que cero.")
            signo = SALE
            queda = round((actual.get(codigo) or 0) - cantidad, 3)
            if queda < 0:
                avisos.append(
                    f"{prod['descripcion']} ({codigo}): quedan {actual.get(codigo) or 0} "
                    f"en {departamento} y salen {cantidad:g}. La bodega queda en "
                    f"{queda:g}. Falta registrar un ingreso, o la salida está de más.")
        preparadas.append((codigo, prod["descripcion"], cantidad, signo))

    if not preparadas:
        return None, ["Lo contado coincide con lo que dice el sistema: no hay nada que "
                      "ajustar."]

    numero = siguiente_numero(conn)
    cur = conn.execute(
        """INSERT INTO pv_documento (numero, tipo, fecha, departamento, solicitado_por,
               observaciones, origen, creado_por)
           VALUES (?,?,?,?,?,?,?,?)""",
        (numero, tipo, fecha or datetime.date.today().isoformat(), departamento,
         normalizar_texto(solicitado_por), normalizar_texto(observaciones),
         ORIGEN_APP, usuario))
    doc_id = cur.lastrowid
    for codigo, descripcion, cantidad, signo in preparadas:
        conn.execute(
            """INSERT INTO pv_movimiento (documento_id, codigo, descripcion, cantidad,
                   signo, estado, departamento)
               VALUES (?,?,?,?,?,?,?)""",
            (doc_id, codigo, descripcion, cantidad, signo, ESTADO_EN_BODEGA,
             departamento))
    conn.commit()
    return documento(conn, doc_id), avisos


def documento(conn, doc_id):
    """Un documento con sus líneas, como lo enseña la pantalla."""
    d = conn.execute("SELECT * FROM pv_documento WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        return None
    salida = dict(d)
    salida["lineas"] = [dict(x) for x in conn.execute(
        """SELECT codigo, descripcion, cantidad, signo, estado
             FROM pv_movimiento WHERE documento_id = ? ORDER BY id""", (doc_id,))]
    return salida


def documentos(conn, limite=40, departamento=None):
    """Los últimos movimientos registrados, para poder mirarlos y deshacerlos.

    SE ENSEÑAN LOS DE LA APLICACIÓN Y LOS DE LA HOJA JUNTOS, con su origen a la vista: la
    bodega es una sola, y dos listas separadas obligarían a mirar en dos sitios para
    saber qué pasó con un producto.
    """
    donde, params = [], []
    if departamento:
        donde.append("d.departamento = ?")
        params.append(normalizar_texto(departamento).upper())
    filtro = (" WHERE " + " AND ".join(donde)) if donde else ""
    params.append(limite)
    return [dict(r) for r in conn.execute(f"""
        SELECT d.id, d.numero, d.tipo, d.fecha, d.departamento, d.observaciones,
               d.origen, d.creado_por, d.creado_en,
               COUNT(m.id) AS lineas,
               SUM(CASE WHEN m.signo = 1 THEN m.cantidad ELSE 0 END) AS entra,
               SUM(CASE WHEN m.signo = -1 THEN m.cantidad ELSE 0 END) AS sale
          FROM pv_documento d
          LEFT JOIN pv_movimiento m ON m.documento_id = d.id
          {filtro}
         GROUP BY d.id
         ORDER BY d.fecha DESC, d.id DESC
         LIMIT ?""", params)]


def anular(conn, doc_id):
    """Borra un documento registrado AQUÍ, con sus líneas.

    SOLO LOS DE LA APLICACIÓN. Los que vinieron de la hoja los manda la hoja: borrar uno
    aquí haría que la siguiente importación lo trajera de vuelta, y entre medias el
    inventario diría una cosa distinta según cuándo se mire.

    SE BORRA Y NO SE COMPENSA CON UN CONTRAMOVIMIENTO, a propósito. Quien registra una
    salida de 100 donde eran 10 lo nota en el momento, y lo que necesita es quitarla, no
    dejar dos líneas falsas que se anulan entre sí y que el día del conteo hay que
    entender. Lo que ya no se puede deshacer así es lo de la hoja, que es historia.
    """
    d = conn.execute("SELECT origen, numero, tipo FROM pv_documento WHERE id = ?",
                     (doc_id,)).fetchone()
    if not d:
        raise ValueError("Ese movimiento ya no existe.")
    if d["origen"] != ORIGEN_APP:
        raise ValueError(
            "Ese movimiento vino de la hoja de cálculo y no se puede borrar desde aquí. "
            "Corregilo en la hoja, o registrá un ajuste de inventario.")
    conn.execute("DELETE FROM pv_movimiento WHERE documento_id = ?", (doc_id,))
    conn.execute("DELETE FROM pv_documento WHERE id = ?", (doc_id,))
    conn.commit()
    return {"numero": d["numero"], "tipo": d["tipo"]}


# ---------------------------------------------------------------------------
# Lo que hay que revisar
# ---------------------------------------------------------------------------

def revisiones(conn):
    """Lo que la hoja trae mal y nadie puede arreglar automáticamente.

    SE ENSEÑA EN VEZ DE CALLARSE, y es la decisión más importante de este módulo. Medido
    sobre la hoja del lodge: 94 códigos repetidos, 68 códigos movidos que no existen en el
    catálogo, 17 productos con stock negativo y 395 sin precio. Arreglarlo por mi cuenta
    sería inventar datos de bodega; esconderlo sería estrenar una pantalla que da cifras
    con toda seguridad y están mal.

    Así que la pantalla lo dice, y proveeduría decide. Es la misma regla que el resto del
    sistema: lo que no se sabe se señala, no se adivina.
    """
    def uno(sql, params=()):
        return [dict(r) for r in conn.execute(sql, params)]

    # Desglosado por bodega: quien tiene que cuadrar un stock negativo es el
    # departamento donde está, y en el general ese rojo puede quedar tapado por el
    # positivo de otra bodega del mismo producto.
    negativos = [f for f in existencias(conn, desglosar=True) if f["stock"] < 0]
    huerfanos = uno(
        """SELECT m.codigo, MAX(m.descripcion) AS descripcion,
                  COUNT(*) AS movimientos
             FROM pv_movimiento m
             LEFT JOIN pv_producto p ON p.codigo = m.codigo
            WHERE p.id IS NULL
            GROUP BY m.codigo ORDER BY COUNT(*) DESC""")
    sin_precio = uno(
        """SELECT codigo, descripcion, departamento FROM pv_producto
            WHERE valor_unitario IS NULL ORDER BY descripcion""")
    return {
        "negativos": [{"codigo": f["codigo"], "descripcion": f["descripcion"],
                       "departamento": f["departamento"], "stock": f["stock"]}
                      for f in negativos],
        "huerfanos": huerfanos,
        "sin_precio": sin_precio,
    }
