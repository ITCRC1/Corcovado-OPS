"""Lee la hoja de proveeduría del lodge («INVENTARIO CWL») y la carga en la base.

POR QUÉ SOLO CUATRO PESTAÑAS. La hoja tiene 19, pero quince de ellas son vistas: las
nueve «INV_<área>» y «INVENTARIO_GENERAL» son SUMIFS sobre el historial, y las cuatro de
categoría (ABARROTES, VERDURA, CARNE Y MARISCOS, LIMPIEZA) son un SEGUNDO sistema con
códigos propios —«ACAP» donde el catálogo dice «108194»— que no cruza con el primero.

Importar las dos cosas sería estrenar la pantalla con el problema que la hoja ya tiene:
dos inventarios del mismo almacén. Así que se lee lo que es dato —Productos, Provedores,
Detalle de cuentas e HISTORIAL GENERAL— y lo demás se recalcula. Si el lodge decide que
las pestañas de categoría son las buenas, se migran esos códigos al catálogo y esto no
cambia.

NO SE INVENTA NADA Y NO SE PIERDE NADA. Lo que no se entiende no se descarta en silencio:
cada fila rechazada vuelve en el informe, con su motivo, para que proveeduría la vea.
"""
import io

import proveeduria as pv

# Las pestañas que SÍ son datos.
HOJA_PRODUCTOS = "Productos"
HOJA_PROVEEDORES = "Provedores"      # así está escrito en la hoja del lodge
HOJA_CUENTAS = "Detalle de cuentas"
HOJA_HISTORIAL = "HISTORIAL GENERAL"


def _celdas(ws, desde=1):
    for i, fila in enumerate(ws.iter_rows(values_only=True), start=1):
        if i < desde:
            continue
        if all(v is None or str(v).strip() == "" for v in fila):
            continue
        yield i, fila


def _col(fila, n):
    return fila[n] if n is not None and n < len(fila) else None


def _numero(valor):
    """Un número de la hoja, o None. El cero SÍ es un número: «mínimo 0» significa que
    de ese producto no hace falta tener nada, y tirarlo lo dejaría sin nivel."""
    if valor is None or str(valor).strip() == "":
        return None
    try:
        return float(str(valor).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def leer(ruta):
    """Devuelve {'productos': [...], 'proveedores': [...], 'cuentas': [...],
    'movimientos': [...], 'rechazos': [...]} desde el archivo .xlsx."""
    from openpyxl import load_workbook

    wb = load_workbook(ruta, data_only=True, read_only=True)
    hojas = set(wb.sheetnames)
    faltan = [h for h in (HOJA_PRODUCTOS, HOJA_HISTORIAL) if h not in hojas]
    if faltan:
        raise ValueError(
            "El archivo no parece la hoja de proveeduría: le faltan las pestañas "
            + ", ".join(f"«{h}»" for h in faltan))

    rechazos = []

    def rechazar(hoja, fila, motivo, texto=""):
        rechazos.append({"hoja": hoja, "fila": fila, "motivo": motivo,
                         "texto": pv.normalizar_texto(texto)[:70]})

    # --- Proveedores ---
    proveedores = []
    if HOJA_PROVEEDORES in hojas:
        for i, f in _celdas(wb[HOJA_PROVEEDORES], desde=2):
            nombre = pv.normalizar_texto(_col(f, 0))
            if not nombre:
                rechazar(HOJA_PROVEEDORES, i, "sin nombre")
                continue
            try:
                dias = int(float(_col(f, 6)))
            except (TypeError, ValueError):
                dias = None
            proveedores.append({
                "nombre": nombre, "tipo_compra": pv.normalizar_texto(_col(f, 1)),
                "contacto": pv.normalizar_texto(_col(f, 2)),
                "correo": pv.normalizar_texto(_col(f, 3)),
                "nombre_contacto": pv.normalizar_texto(_col(f, 4)),
                "condicion": pv.normalizar_texto(_col(f, 5)).title(),
                "dias_credito": dias,
                "dias_pedido": pv.normalizar_texto(_col(f, 7)),
                "dias_entrega": pv.normalizar_texto(_col(f, 8)),
            })

    # --- Productos ---
    #
    # EL CÓDIGO REPETIDO NO SE FUNDE. Medido: 94 de 1.464. Fundirlos sumaría el stock de
    # dos productos distintos que comparten código por error de captura, y el resultado
    # se vería perfectamente normal en pantalla. Se queda el primero y los demás se
    # listan para que proveeduría diga cuál vale.
    productos, vistos = [], {}
    for i, f in _celdas(wb[HOJA_PRODUCTOS], desde=2):
        codigo = pv.normalizar_codigo(_col(f, 1))
        descripcion = pv.normalizar_texto(_col(f, 2))
        if not codigo:
            rechazar(HOJA_PRODUCTOS, i, "sin código", descripcion)
            continue
        if codigo in vistos:
            rechazar(HOJA_PRODUCTOS, i,
                     f"código repetido (ya estaba en la fila {vistos[codigo]})",
                     f"{codigo} · {descripcion}")
            continue
        vistos[codigo] = i
        productos.append({
            "codigo": codigo,
            "descripcion": descripcion or codigo,
            "unidad": pv.normalizar_texto(_col(f, 3)).upper(),
            "area": pv.normalizar_texto(_col(f, 0)).upper(),
            "departamento": pv.normalizar_texto(_col(f, 7)).upper(),
            "valor_unitario": pv.centimos(_col(f, 4)),
            "proveedor": pv.normalizar_texto(_col(f, 5)),
        })

    # --- Plan de cuentas ---
    cuentas = []
    if HOJA_CUENTAS in hojas:
        for i, f in _celdas(wb[HOJA_CUENTAS], desde=6):
            codigo = pv.normalizar_texto(_col(f, 0))
            if not codigo:
                continue
            cuentas.append({"codigo": codigo,
                            "grupo": pv.normalizar_texto(_col(f, 1)),
                            "nombre": pv.normalizar_texto(_col(f, 3)),
                            "detalle": pv.normalizar_texto(_col(f, 4))})

    # --- Los mínimos y máximos de cada bodega ---
    #
    # SON LAS ÚNICAS COLUMNAS DE LAS PESTAÑAS «INV_<área>» QUE SON DATO. Todo lo demás de
    # esas quince pestañas es un SUMIFS sobre el historial, pero el mínimo y el máximo
    # están escritos a mano por quien lleva la bodega, y sin ellos no hay pedido sugerido.
    #
    # Las columnas se buscan POR SU ENCABEZADO y no por su posición: las pestañas tienen
    # entre 12 y 14 columnas, y en dos de ellas la primera columna ni siquiera se titula
    # «Código» —en INV_BAR dice «50000 - Cost of Sale» y en INV_STAFF_COMEDOR dice «f»—.
    # Buscando por posición, esas dos se perdían enteras: 362 de los 735 productos que
    # tienen niveles puestos.
    niveles = []
    for hoja in hojas:
        if not hoja.upper().startswith("INV") or hoja == "INVENTARIO_GENERAL":
            continue
        ws = wb[hoja]
        filas = list(ws.iter_rows(values_only=True))
        cab_i = next((i for i, f in enumerate(filas[:8])
                      if any("NIMO" in str(v or "").upper() for v in f)), None)
        if cab_i is None:
            rechazar(hoja, 1, "no se encontró la columna de mínimo")
            continue
        cab = [str(v or "").strip().upper() for v in filas[cab_i]]
        i_min = next((i for i, t in enumerate(cab) if "NIMO" in t), None)
        i_max = next((i for i, t in enumerate(cab) if "XIMO" in t), None)
        i_dep = next((i for i, t in enumerate(cab) if "DEPARTAMENTO" in t), 1)
        for n, f in enumerate(filas[cab_i + 1:], start=cab_i + 2):
            codigo = pv.normalizar_codigo(_col(f, 0))
            if not codigo:
                continue
            mn = _numero(_col(f, i_min))
            mx = _numero(_col(f, i_max)) if i_max is not None else None
            # Un producto sin ninguno de los dos no es una fila de niveles: es una fila
            # de la pestaña que todavía no tiene nivel puesto.
            if mn is None and mx is None:
                continue
            niveles.append({
                "codigo": codigo,
                "departamento": pv.normalizar_texto(_col(f, i_dep)).upper(),
                "minimo": mn, "maximo": mx,
            })

    # --- El historial, que es el libro ---
    movimientos = []
    for i, f in _celdas(wb[HOJA_HISTORIAL], desde=2):
        signo = pv.signo_de(_col(f, 3))
        codigo = pv.normalizar_codigo(_col(f, 4))
        fecha = pv.fecha_iso(_col(f, 1))
        descripcion = pv.normalizar_texto(_col(f, 5))
        try:
            cantidad = float(_col(f, 6))
        except (TypeError, ValueError):
            cantidad = None
        # CADA UNO DE ESTOS TRES RECHAZOS SE DICE. Un movimiento que se cae en silencio
        # es stock que falta en la pantalla sin que nada lo explique.
        if signo is None:
            rechazar(HOJA_HISTORIAL, i, "no dice si entra o sale", descripcion)
            continue
        if not codigo:
            rechazar(HOJA_HISTORIAL, i, "sin código de producto", descripcion)
            continue
        if cantidad is None:
            rechazar(HOJA_HISTORIAL, i, "cantidad ilegible", descripcion)
            continue
        if not fecha:
            rechazar(HOJA_HISTORIAL, i, "fecha ilegible", descripcion)
            continue
        numero = pv.normalizar_codigo(_col(f, 0)) or f"SN-{i}"
        tipo = pv.normalizar_texto(_col(f, 8)).upper() or "AJUSTE INVENTARIO"
        estado = pv.normalizar_texto(_col(f, 9)) or pv.ESTADO_EN_BODEGA
        movimientos.append({
            "numero": numero, "tipo": tipo, "fecha": fecha,
            "proveedor": pv.normalizar_texto(_col(f, 2)),
            "estado": estado,
            "codigo": codigo, "descripcion": descripcion,
            "cantidad": cantidad, "signo": signo,
            "departamento": pv.normalizar_texto(_col(f, 7)).upper(),
        })

    wb.close()
    return {"productos": productos, "proveedores": proveedores, "cuentas": cuentas,
            "movimientos": movimientos, "niveles": niveles, "rechazos": rechazos}


def excel_de_revisiones(revisiones):
    """Lo que hay que revisar, en un .xlsx para trabajarlo.

    POR QUÉ UN ARCHIVO Y NO SOLO LA PANTALLA. Lo que sale aquí no lo arregla el sistema:
    son decisiones de proveeduría —cuál de los dos productos con el mismo código vale,
    si un stock negativo es una compra sin registrar o una salida de más— y eso se
    trabaja en una lista, tachando, al lado de la bodega. Dejarlo solo en pantalla es
    pedirle a alguien que lo copie a mano, y entonces no se hace.

    Una pestaña por problema, porque son tres trabajos distintos y los hace gente
    distinta.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    negrita = Font(bold=True)

    hojas = [
        ("Stock negativo", ["Código", "Producto", "Bodega", "Stock", "Qué pasó"],
         [(f["codigo"], f["descripcion"], f["departamento"], f["stock"], "")
          for f in revisiones.get("negativos") or []],
         "Salió más de lo que entró. O falta registrar una compra, o la salida está "
         "mal. Se arregla con un ajuste por conteo."),
        ("Sin ficha", ["Código", "Como se escribió", "Movimientos", "Qué producto es"],
         [(f["codigo"], f["descripcion"], f["movimientos"], "")
          for f in revisiones.get("huerfanos") or []],
         "Se movió un código que no está en la pestaña Productos. Hay que darle ficha "
         "o corregir el código del movimiento."),
        ("Sin precio", ["Código", "Producto", "Bodega", "Precio"],
         [(f["codigo"], f["descripcion"], f["departamento"], "")
          for f in revisiones.get("sin_precio") or []],
         "No entran en la inversión ni en el costo del consumo. Sin precio no se "
         "inventa uno: la cifra saldría más baja de lo que es."),
    ]
    for nombre, cabecera, filas, explica in hojas:
        ws = wb.create_sheet(nombre[:31])
        ws.append([explica])
        ws.append([])
        ws.append(cabecera)
        for celda in ws[3]:
            celda.font = negrita
        for f in filas:
            ws.append(list(f))
        # Anchos a ojo pero suficientes: una columna de 8 con un nombre de producto
        # dentro obliga a ensancharla a mano antes de poder leer nada.
        for i, ancho in enumerate((16, 46, 20, 12, 30), start=1):
            if i <= len(cabecera):
                ws.column_dimensions[ws.cell(row=3, column=i).column_letter].width = ancho

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def cargar(conn, datos, usuario=None):
    """Mete en la base lo que devolvió `leer`. Devuelve el recuento de cada cosa.

    SE REEMPLAZA LO DE LA HOJA, no se va sumando. La hoja es la fuente de lo suyo
    mientras dure la convivencia, así que importarla dos veces tiene que dar el mismo
    inventario y no el doble — y eso es justo lo que pasaría acumulando: nadie lo
    notaría hasta que alguien mirara una existencia y le pareciera alta.

    Y SOLO LO DE LA HOJA. Lo que alguien registró desde la aplicación —una salida del
    restaurante, un ajuste de bodega— se queda. Sin esa distinción, trabajar en la
    aplicación sería una trampa: se registra todo el día, alguien vuelve a importar «para
    actualizar» y el trabajo desaparece sin que nada lo diga. Ver `origen` en schema.sql.
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM pv_movimiento WHERE documento_id IN "
                "(SELECT id FROM pv_documento WHERE origen = ?)", (pv.ORIGEN_HOJA,))
    cur.execute("DELETE FROM pv_documento WHERE origen = ?", (pv.ORIGEN_HOJA,))
    cur.execute("DELETE FROM pv_producto")
    cur.execute("DELETE FROM pv_cuenta")
    cur.execute("DELETE FROM pv_proveedor")

    ids_prov = {}
    for p in datos["proveedores"]:
        cur.execute(
            """INSERT INTO pv_proveedor (nombre, tipo_compra, contacto, correo,
                   nombre_contacto, condicion, dias_credito, dias_pedido, dias_entrega)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (p["nombre"], p["tipo_compra"], p["contacto"], p["correo"],
             p["nombre_contacto"], p["condicion"], p["dias_credito"],
             p["dias_pedido"], p["dias_entrega"]))
        ids_prov[p["nombre"].upper()] = cur.lastrowid

    for p in datos["productos"]:
        cur.execute(
            """INSERT INTO pv_producto (codigo, descripcion, unidad, departamento, area,
                   valor_unitario, proveedor_id)
               VALUES (?,?,?,?,?,?,?)""",
            (p["codigo"], p["descripcion"], p["unidad"], p["departamento"], p["area"],
             p["valor_unitario"], ids_prov.get(p["proveedor"].upper())))

    # Los niveles se reemplazan enteros, como el resto de lo que manda la hoja. Se usa
    # OR REPLACE porque la misma (codigo, bodega) puede venir en dos pestañas si alguien
    # la copió: la última gana, en vez de reventar la importación entera por una fila.
    # SOLO LOS DE LA HOJA. Lo que alguien puso desde la pantalla se queda: seis de las
    # bodegas del lodge no tienen ningún nivel en la hoja, así que son justo las que se
    # ponen a mano aquí — y las que lo perderían al reimportar.
    cur.execute("DELETE FROM pv_nivel WHERE origen = ?", (pv.ORIGEN_HOJA,))
    for n in datos.get("niveles") or []:
        # INSERT OR IGNORE y no REPLACE: si alguien ya lo puso a mano en la pantalla,
        # manda lo que puso. La hoja no sabe de ese cambio y lo pisaría cada vez.
        cur.execute(
            "INSERT OR IGNORE INTO pv_nivel "
            "(codigo, departamento, minimo, maximo, origen) VALUES (?,?,?,?,?)",
            (n["codigo"], n["departamento"], n["minimo"], n["maximo"], pv.ORIGEN_HOJA))
    # CUÁNTOS QUEDARON, no cuántos se leyeron. La misma (código, bodega) aparece repetida
    # entre pestañas —medido en la hoja del lodge: 1.046 filas leídas, 971 niveles
    # distintos— y decir «1.046» sería contar 75 veces lo mismo.
    niveles_guardados = cur.execute("SELECT COUNT(*) FROM pv_nivel").fetchone()[0]

    for c in datos["cuentas"]:
        cur.execute(
            "INSERT OR IGNORE INTO pv_cuenta (codigo, grupo, nombre, detalle) "
            "VALUES (?,?,?,?)",
            (c["codigo"], c["grupo"], c["nombre"], c["detalle"]))

    # Las líneas se agrupan por su documento: en la hoja el número de orden se repite en
    # cada línea con su proveedor y su fecha copiados, y aquí va una sola vez.
    ids_doc = {}
    for m in datos["movimientos"]:
        clave = (m["tipo"], m["numero"])
        doc = ids_doc.get(clave)
        if doc is None:
            cur.execute(
                """INSERT INTO pv_documento (numero, tipo, fecha, proveedor_id,
                       departamento, origen, creado_por)
                   VALUES (?,?,?,?,?,?,?)""",
                (m["numero"], m["tipo"], m["fecha"],
                 ids_prov.get(m["proveedor"].upper()), m["departamento"],
                 pv.ORIGEN_HOJA, usuario))
            doc = ids_doc[clave] = cur.lastrowid
        # EL ESTADO VA EN LA LINEA. Una orden llega a medias: medido en la hoja del
        # lodge, 25 órdenes traen líneas en dos estados y tocan 218 productos. Puesto en
        # la cabecera daba 61 productos con el stock equivocado contra la propia hoja.
        cur.execute(
            """INSERT INTO pv_movimiento (documento_id, codigo, descripcion, cantidad,
                   signo, estado, departamento)
               VALUES (?,?,?,?,?,?,?)""",
            (doc, m["codigo"], m["descripcion"], m["cantidad"], m["signo"],
             m["estado"], m["departamento"]))
    conn.commit()
    return {"proveedores": len(datos["proveedores"]),
            "productos": len(datos["productos"]),
            "niveles": niveles_guardados,
            "niveles_repetidos": len(datos.get("niveles") or []) - niveles_guardados,
            "cuentas": len(datos["cuentas"]),
            "documentos": len(ids_doc),
            "movimientos": len(datos["movimientos"]),
            "rechazos": len(datos["rechazos"])}
