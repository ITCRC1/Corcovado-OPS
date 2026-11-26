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
import json
import os

# ---------------------------------------------------------------------------
# Los datos del lodge que van en la orden de compra
# ---------------------------------------------------------------------------
#
# Salen de la cabecera de la pestaña «Orden de compra» de la hoja, que es la que el
# proveedor recibe hoy. Van aquí como valores por defecto y se pueden cambiar sin tocar
# el código: si el lodge se muda o cambia el teléfono, se edita el archivo de
# configuración y la orden siguiente ya sale bien.
CONFIG_POR_DEFECTO = {
    "razon_social": "Corcovado Wilderness Lodge",
    "cedula_juridica": "3-102-865727",
    "direccion": ("Puntarenas, Osa, Sierpe, 400 metros Este de Estación Playa "
                  "San Pedrillo."),
    "correo": "proveduria.cwl@gmail.com",
    "telefono1": "+506 86756555",
    "telefono2": "+506 84257901",
    # A dónde se le dice al proveedor que entregue. No es la misma que la de arriba: la
    # mercadería no llega al lodge, llega al muelle de Sierpe y de ahí sube en bote.
    "direccion_entrega": ("Puntarenas, Osa, Sierpe, Hacienda Corcovado, 50 metros oeste "
                          "del Hotel Oleaje Sereno (Perla del Sur), mano izquierda, "
                          "tapia color blanco con negro."),
}

_CONFIG_PATH = os.path.join(
    os.environ.get("HOTEL_DATA_DIR")
    or os.path.join(os.path.dirname(__file__), "..", "data"),
    "config_proveeduria.json")


def cargar_config():
    """Los datos del lodge para la orden de compra, con lo guardado encima."""
    cfg = dict(CONFIG_POR_DEFECTO)
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            guardado = json.load(f)
        if isinstance(guardado, dict):
            cfg.update({k: v for k, v in guardado.items() if k in CONFIG_POR_DEFECTO})
    except (OSError, ValueError):
        pass
    return cfg


def guardar_config(cambios):
    cfg = cargar_config()
    cfg.update({k: normalizar_texto(v) for k, v in (cambios or {}).items()
                if k in CONFIG_POR_DEFECTO})
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


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
# El consumo: qué se gastó y por cuánta gente
# ---------------------------------------------------------------------------
#
# CIERRA EL CÍRCULO QUE ABRIÓ EL PEDIDO SUGERIDO. La fase anterior predice cuánto hará
# falta según la gente que viene; esta mira hacia atrás y dice cuánto se gastó de verdad
# por cada huésped. Sin eso, el pedido sugerido es una cuenta que nadie puede contrastar.
#
# LA CIFRA QUE IMPORTA NO ES EL TOTAL, ES EL TOTAL POR PERSONA. Una semana llena gasta
# más que una vacía y eso no dice nada; lo que dice algo es que el costo por
# huésped-noche suba un 40% con la misma ocupación. Esa pregunta no se podía hacer en la
# hoja: habría que cruzar a mano el historial con una ocupación que está escrita en otra
# celda y que nadie actualiza.

# De qué se compone el consumo. El AJUSTE NO ENTRA, y es la decisión que hace que la
# cifra sirva: un ajuste es una corrección de conteo —aparece una caja olvidada, o
# faltaba registrar una compra— y meterlo en el consumo le echa a la cocina la culpa de
# un error de inventario. Se cuenta aparte, para que no desaparezca.
TIPOS_DE_CONSUMO = ("ORDEN INTERNA",)
TIPOS_DE_MERMA = ("MERMA",)

# Con qué se divide el gasto de cada bodega. Es lo que convierte un total en una cifra
# que se puede comparar entre semanas.
#
# STAFF COMEDOR NO TIENE DENOMINADOR y se deja sin él a propósito: se divide entre el
# personal, y cuánto personal hay ese día no está en este sistema. Inventar que se
# divide entre los huéspedes daría un número que parece bueno y no significa nada —el
# comedor del staff no se come más porque el hotel esté lleno.
DENOMINADOR = {
    "F&B": "pax", "RESTAURANTE": "pax", "BAR": "pax", "BAR EL BOSQUE": "pax",
    "COCINA": "pax", "COMEDOR": "pax",
    "HOUSEKEEPING": "habitacion", "ROOMS": "habitacion", "LAUNDRY": "habitacion",
}


def _gasto_de(conn, desde, hasta, tipos, departamento=None):
    """Lo que salió de bodega en ese periodo, por departamento y por producto.

    SE VALORA CON EL PRECIO DEL CATÁLOGO, que es el mismo con el que esta pantalla
    calcula la inversión. No es el precio que se pagó cada vez —para eso haría falta
    llevar un costo promedio— pero es coherente con el resto: dos cifras de la misma
    pantalla calculadas con bases distintas no se pueden ni sumar ni comparar.
    """
    marcas = ",".join("?" * len(tipos))
    donde, params = "", [desde, hasta] + list(tipos)
    if departamento:
        donde = " AND m.departamento = ?"
        params.append(normalizar_texto(departamento).upper())
    return [dict(r) for r in conn.execute(f"""
        SELECT m.departamento, m.codigo,
               COALESCE(p.descripcion, m.descripcion) AS descripcion,
               p.unidad, p.valor_unitario,
               SUM(m.cantidad) AS unidades
          FROM pv_movimiento m
          JOIN pv_documento d ON d.id = m.documento_id
          LEFT JOIN pv_producto p ON p.codigo = m.codigo
         WHERE m.signo = -1 AND d.fecha BETWEEN ? AND ?
           AND d.tipo IN ({marcas}){donde}
         GROUP BY m.departamento, m.codigo""", params)]


def _resumir(filas):
    """Agrupa las filas de gasto por departamento, sumando lo que tiene precio."""
    por_depto = {}
    for f in filas:
        d = por_depto.setdefault(f["departamento"] or "—",
                                 {"departamento": f["departamento"] or "—",
                                  "unidades": 0.0, "costo": 0, "sin_precio": 0,
                                  "productos": 0})
        d["productos"] += 1
        d["unidades"] += f["unidades"] or 0
        if f["valor_unitario"] is None:
            d["sin_precio"] += 1
        else:
            d["costo"] += int(round(f["valor_unitario"] * (f["unidades"] or 0)))
    for d in por_depto.values():
        d["unidades"] = round(d["unidades"], 2)
    return por_depto


def consumo(conn, desde=None, hasta=None, dias=7, departamento=None):
    """Qué se gastó, por cuánta gente, y cómo va contra el periodo anterior.

    `desde`/`hasta` por omisión los últimos `dias` días terminando ayer: hoy todavía no
    terminó, y meterlo haría que la cifra de la mañana pareciera siempre buenísima.
    """
    import datetime as _dt

    import ocupacion as _ocu

    hoy = _dt.date.today()
    if not hasta:
        hasta = (hoy - _dt.timedelta(days=1)).isoformat()
    if not desde:
        desde = (_dt.date.fromisoformat(hasta)
                 - _dt.timedelta(days=max(1, dias) - 1)).isoformat()
    largo = (_dt.date.fromisoformat(hasta) - _dt.date.fromisoformat(desde)).days + 1

    def medir(d1, d2):
        dias_ocu, _total = _ocu.por_dia(conn, d1, d2)
        pax = sum(x["pax"] for x in dias_ocu)
        hab = sum(x["habitaciones"] for x in dias_ocu)
        gasto = _resumir(_gasto_de(conn, d1, d2, TIPOS_DE_CONSUMO, departamento))
        merma = _resumir(_gasto_de(conn, d1, d2, TIPOS_DE_MERMA, departamento))
        for nombre, d in gasto.items():
            d["merma_costo"] = merma.get(nombre, {}).get("costo", 0)
            base = DENOMINADOR.get(nombre)
            cuantos = pax if base == "pax" else hab if base == "habitacion" else 0
            d["base"] = base
            d["cuantos"] = cuantos
            # SIN DENOMINADOR NO SE INVENTA UNO: se deja en None y la pantalla enseña
            # solo el total. Un número que parece comparable y no lo es es peor que no
            # tenerlo, porque se usa para decidir.
            d["por_unidad"] = (int(round(d["costo"] / cuantos))
                               if base and cuantos else None)
        # Las bodegas que SOLO tuvieron merma también se enseñan: tirar producto es
        # gasto aunque no haya salido nada por la puerta de la cocina.
        for nombre, m in merma.items():
            if nombre not in gasto:
                gasto[nombre] = {**m, "merma_costo": m["costo"], "costo": 0,
                                 "unidades": 0.0, "base": DENOMINADOR.get(nombre),
                                 "cuantos": 0, "por_unidad": None}
        return {
            "desde": d1, "hasta": d2, "pax_noche": pax, "habitacion_noche": hab,
            "bodegas": sorted(gasto.values(), key=lambda x: -x["costo"]),
            "costo": sum(x["costo"] for x in gasto.values()),
            "merma": sum(x["merma_costo"] for x in gasto.values()),
        }

    ahora = medir(desde, hasta)
    fin_antes = (_dt.date.fromisoformat(desde) - _dt.timedelta(days=1))
    antes = medir((fin_antes - _dt.timedelta(days=largo - 1)).isoformat(),
                  fin_antes.isoformat())

    # LA COMPARACIÓN SE HACE POR PERSONA, no por total: dos semanas con ocupación
    # distinta tienen totales distintos y eso no dice nada. Lo que dice algo es que el
    # costo por huésped suba con la misma gente.
    def por_pax(m):
        return (m["costo"] / m["pax_noche"]) if m["pax_noche"] else None

    a, b = por_pax(ahora), por_pax(antes)
    variacion = round(100 * (a - b) / b) if (a is not None and b) else None

    # Los productos que más pesan: es donde mirar primero si la cifra se disparó.
    productos = []
    for f in _gasto_de(conn, desde, hasta, TIPOS_DE_CONSUMO, departamento):
        if f["valor_unitario"] is None:
            continue
        productos.append({**f, "costo": int(round(f["valor_unitario"] * f["unidades"]))})
    productos.sort(key=lambda x: -x["costo"])

    # Los ajustes, aparte y a la vista: no son consumo, pero un periodo con muchos
    # ajustes dice que el inventario no está cuadrando, y eso también hay que verlo.
    ajustes = _resumir(_gasto_de(conn, desde, hasta, ("AJUSTE INVENTARIO",),
                                 departamento))
    return {
        **ahora, "dias": largo, "departamento": departamento or "",
        "anterior": antes,
        "costo_por_pax": int(round(a)) if a is not None else None,
        "costo_por_pax_antes": int(round(b)) if b is not None else None,
        "variacion_pct": variacion,
        "productos": productos[:20],
        "ajustes_costo": sum(x["costo"] for x in ajustes.values()),
    }


# ---------------------------------------------------------------------------
# El pedido sugerido
# ---------------------------------------------------------------------------
#
# ES LA RAZÓN POR LA QUE ESTO MERECE DEJAR DE SER UNA HOJA DE CÁLCULO. Todo lo demás
# —registrar, sumar, imprimir— Excel lo hacía bien. Pero el pedido sugerido depende de
# CUÁNTA GENTE VIENE, y en la hoja la ocupación es un número escrito a mano en
# `INVENTARIO_GENERAL!C1`: alguien tiene que acordarse de actualizarlo, y el día que no
# lo haga el pedido sale calculado con la ocupación de la semana pasada.
#
# Esta aplicación ya sabe la ocupación de verdad, día por día. Ver ocupacion.py.
#
# LA FÓRMULA ES LA DE LA HOJA — la de INV_GUIAS, que es la única de las tres que usa la
# ocupación:
#
#     objetivo  = mínimo + (máximo − mínimo) × ocupación
#     sugerido  = objetivo − lo que hay − lo que ya viene en camino
#
# LAS TRES FÓRMULAS DE LA HOJA. INV_RESTAURANTE usa «si stock < mínimo, pedir hasta el
# máximo»; INV_GUIAS la de arriba; y ABARROTES interpola entre 360 y 898 pax con
# constantes escritas a mano. Tres respuestas a la misma pregunta, y hay que elegir una:
# se eligió la que mira la ocupación, porque es la que el lodge quiso y la única que
# sabe que una semana llena gasta más que una vacía.
#
# LO QUE SE AÑADE A LA HOJA: restar lo que YA ESTÁ PEDIDO. Sin eso, el lunes se sugiere
# comprar 20, se pide, y el martes se vuelve a sugerir lo mismo porque todavía no ha
# llegado — y se compra dos veces.

DIAS_SEMANA = {
    "LUNES": 0, "MARTES": 1, "MIERCOLES": 2, "MIÉRCOLES": 2, "JUEVES": 3,
    "VIERNES": 4, "SABADO": 5, "SÁBADO": 5, "DOMINGO": 6,
}


def _sin_tildes(texto):
    import unicodedata
    base = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(ch for ch in base if unicodedata.category(ch) != "Mn").upper()


def dias_de_pedido(texto):
    """Los días de la semana que nombra un texto como «Martes y viernes». [] si ninguno.

    El lodge los escribe en texto libre en la ficha del proveedor —«Martes y viernes»,
    «Jueves», «No aplica»— y así se importan: convertirlos a una lista cerrada al cargar
    habría tirado lo que no se entendiera, que es justo lo que hay que poder leer.
    """
    limpio = _sin_tildes(texto)
    return sorted({n for nombre, n in DIAS_SEMANA.items()
                   if _sin_tildes(nombre) in limpio})


def a_quien_toca_pedirle(conn, cuando=None):
    """Los proveedores a los que hoy toca pedirles, según sus días de pedido.

    POR QUÉ IMPORTA: un proveedor que recibe pedidos los martes y entrega los miércoles
    no acepta uno el jueves. Pedirle tarde no se nota el jueves, se nota el domingo
    cuando no llegó. El dato ya está en su ficha y hasta ahora no lo miraba nadie.
    """
    hoy = cuando or datetime.date.today()
    salida = []
    for r in conn.execute(
            "SELECT id, nombre, dias_pedido, dias_entrega, condicion, dias_credito "
            "FROM pv_proveedor WHERE activo = 1 ORDER BY nombre"):
        d = dict(r)
        dias = dias_de_pedido(d["dias_pedido"])
        if hoy.weekday() in dias:
            salida.append(d)
    return salida


def guardar_nivel(conn, codigo, departamento, minimo, maximo, usuario=None):
    """Pone (o quita) el mínimo y el máximo de un producto en una bodega.

    HACE FALTA PORQUE LA HOJA NO LOS TIENE TODOS. Medido: de las once bodegas, solo
    cuatro traen niveles —RESTAURANTE, BAR, STAFF COMEDOR y HOUSEKEEPING—; las otras
    seis no tienen ninguno, y sin niveles el pedido sugerido no puede decir nada de
    ellas. Hasta ahora la única forma de ponerlos era editar el Excel y reimportar.

    Lo que se escriba aquí queda marcado como de la aplicación y la importación ya no se
    lo lleva por delante. Ver `origen` en schema.sql.

    LOS DOS VACÍOS BORRAN EL NIVEL, igual que una nota vacía borra la nota: «sin nivel»
    y «nivel cero» no son lo mismo —el primero quiere decir que nadie lo ha decidido— y
    con un cero el pedido sugerido diría que de ese producto no hace falta tener nada.
    """
    codigo = normalizar_codigo(codigo)
    departamento = normalizar_texto(departamento).upper()
    if not codigo or not departamento:
        raise ValueError("Falta el producto o la bodega.")
    if not _producto(conn, codigo):
        raise ValueError(f"El código «{codigo}» no está en el catálogo.")

    def numero(v):
        if v is None or str(v).strip() == "":
            return None
        try:
            n = float(str(v).replace(",", ".").strip())
        except (TypeError, ValueError):
            raise ValueError("El mínimo y el máximo tienen que ser números.")
        if n < 0:
            raise ValueError("El mínimo y el máximo no pueden ser negativos.")
        return n

    mn, mx = numero(minimo), numero(maximo)
    if mn is None and mx is None:
        conn.execute("DELETE FROM pv_nivel WHERE codigo = ? AND departamento = ?",
                     (codigo, departamento))
        conn.commit()
        return None
    # EL MÁXIMO NO PUEDE SER MENOR QUE EL MÍNIMO: el objetivo interpola entre los dos, y
    # al revés el pedido BAJA cuanto más lleno esté el lodge, que es lo contrario de lo
    # que nadie espera y no da ningún error.
    if mn is not None and mx is not None and mx < mn:
        raise ValueError(
            f"El máximo ({mx:g}) no puede ser menor que el mínimo ({mn:g}): el pedido "
            "bajaría cuanto más lleno estuviera el lodge.")
    conn.execute(
        """INSERT INTO pv_nivel (codigo, departamento, minimo, maximo, origen,
               actualizado_en, actualizado_por)
           VALUES (?,?,?,?,?,datetime('now'),?)
           ON CONFLICT(codigo, departamento) DO UPDATE SET
             minimo = excluded.minimo, maximo = excluded.maximo,
             origen = excluded.origen, actualizado_en = excluded.actualizado_en,
             actualizado_por = excluded.actualizado_por""",
        (codigo, departamento, mn, mx, ORIGEN_APP, usuario))
    conn.commit()
    return {"codigo": codigo, "departamento": departamento, "minimo": mn, "maximo": mx}


def niveles_de(conn, departamento):
    """{codigo: {minimo, maximo, origen}} de esa bodega, para pintarlos en la lista."""
    return {r["codigo"]: dict(r) for r in conn.execute(
        "SELECT codigo, minimo, maximo, origen FROM pv_nivel WHERE departamento = ?",
        (normalizar_texto(departamento).upper(),))}


def pedido_sugerido(conn, departamento=None, desde=None, hasta=None, dias=7):
    """Qué conviene pedir, y por qué. Devuelve {ocupacion, filas, sin_nivel, …}.

    `desde`/`hasta` es el periodo que se va a cubrir; por omisión los próximos `dias`
    días, que es lo que dura un ciclo de pedido en el lodge.

    SOLO SUGIERE LO QUE TIENE NIVELES PUESTOS. Medido en la hoja: 735 productos los
    tienen y el resto no. Inventarle un mínimo a un producto sería decidir por el lodge
    cuánto tiene que haber de algo, y eso lo sabe quien lleva la bodega; lo que se hace
    es DECIR cuántos quedan fuera, para que no parezca que no hace falta pedir nada.
    """
    import ocupacion as _ocu

    hoy = datetime.date.today()
    desde = desde or hoy.isoformat()
    hasta = hasta or (hoy + datetime.timedelta(days=max(1, dias) - 1)).isoformat()
    factor = _ocu.fraccion(conn, desde, hasta)

    hay = {(f["codigo"], f["departamento"]): f
           for f in existencias(conn, desglosar=True)}
    donde, params = ("WHERE n.departamento = ?", [departamento]) if departamento \
        else ("", [])
    niveles = [dict(r) for r in conn.execute(f"""
        SELECT n.codigo, n.departamento, n.minimo, n.maximo,
               p.descripcion, p.unidad, p.valor_unitario, p.proveedor_id,
               pr.nombre AS proveedor
          FROM pv_nivel n
          LEFT JOIN pv_producto p ON p.codigo = n.codigo
          LEFT JOIN pv_proveedor pr ON pr.id = p.proveedor_id
          {donde}
         ORDER BY p.descripcion""", params)]

    filas = []
    for n in niveles:
        minimo = n["minimo"] or 0
        maximo = n["maximo"] if n["maximo"] is not None else minimo
        objetivo = minimo + (maximo - minimo) * factor
        actual = hay.get((n["codigo"], n["departamento"]))
        stock = actual["stock"] if actual else 0
        en_camino = (actual["en_camino"] or 0) if actual else 0
        sugerido = objetivo - stock - en_camino
        # Se redondea HACIA ARRIBA: medio tarro de algo no se compra, y quedarse corto
        # cuesta más que el medio tarro de más.
        import math
        sugerido = max(0, int(math.ceil(round(sugerido, 3))))
        if not sugerido:
            continue
        filas.append({
            "codigo": n["codigo"], "departamento": n["departamento"],
            "descripcion": n["descripcion"] or n["codigo"],
            # UN NIVEL DE ALGO QUE NO ESTÁ EN EL CATÁLOGO. Medido en la hoja: pasa, y
            # entonces la fila solo puede enseñar el código. No se puede comprar —la
            # orden exige ficha— así que se marca para que la pantalla lo diga en vez de
            # ofrecer un botón que después falla.
            "huerfano": n["descripcion"] is None,
            "unidad": n["unidad"], "minimo": minimo, "maximo": maximo,
            "objetivo": round(objetivo, 2), "stock": stock, "en_camino": en_camino,
            "sugerido": sugerido,
            "valor_unitario": n["valor_unitario"],
            "costo": (int(round(n["valor_unitario"] * sugerido))
                      if n["valor_unitario"] is not None else None),
            "proveedor_id": n["proveedor_id"], "proveedor": n["proveedor"],
        })

    # Cuántos productos de esa bodega se quedan fuera por no tener niveles puestos. Sin
    # esta cifra, una bodega sin niveles enseñaría una lista vacía que se lee como «no
    # hace falta pedir nada».
    con_nivel = {(n["codigo"], n["departamento"]) for n in niveles}
    sin_nivel = sum(1 for (cod, dep) in hay
                    if (not departamento or dep == departamento)
                    and (cod, dep) not in con_nivel)
    con_costo = [f for f in filas if f["costo"] is not None]
    return {
        "desde": desde, "hasta": hasta,
        "ocupacion": round(factor, 4),
        "ocupacion_pct": round(100 * factor),
        "filas": filas,
        "sin_nivel": sin_nivel,
        # Los que tienen nivel puesto pero no ficha: se sugieren, pero no se pueden
        # comprar desde aquí hasta que alguien les dé ficha en el catálogo.
        "sin_ficha": sum(1 for f in filas if f["huerfano"]),
        "costo": sum(f["costo"] for f in con_costo),
        "sin_precio": len(filas) - len(con_costo),
        "proveedores_de_hoy": a_quien_toca_pedirle(conn),
    }


# ---------------------------------------------------------------------------
# La orden de compra
# ---------------------------------------------------------------------------
#
# TIENE SU PROPIO CAMINO y no entra en `registrar`, a propósito: una orden de compra es
# lo único de proveeduría que NO mueve el inventario en el momento de escribirla. Se
# pide, se manda al proveedor, y la mercadería aparece en bodega cuando llega — a veces
# a medias, porque el bote trae lo que cabe.
#
# De ahí que el estado viva en la LÍNEA: medido en la hoja del lodge, 25 órdenes de 1.165
# traen líneas en dos estados a la vez.

TIPO_COMPRA = "ORDEN DE COMPRA"


def crear_orden_compra(conn, proveedor_id, departamento, lineas, fecha=None,
                       solicitado_por="", observaciones="", usuario=None):
    """Arma una orden de compra. Nace como «Solicitado» y NO suma stock todavía.

    `lineas` es [{'codigo', 'cantidad', 'precio'(opcional), 'cuenta_id'(opcional)}]. El
    precio se guarda EN LA LÍNEA y no se lee del catálogo cada vez: lo que se le pidió al
    proveedor es lo que decía la orden ese día, y el catálogo cambia. Si no se escribe,
    se copia el del catálogo como punto de partida.
    """
    departamento = normalizar_texto(departamento).upper()
    if not departamento:
        raise ValueError("Falta el departamento que pide la compra.")
    if not lineas:
        raise ValueError("La orden no tiene ninguna línea.")
    prov = conn.execute("SELECT id, nombre FROM pv_proveedor WHERE id = ?",
                        (proveedor_id,)).fetchone() if proveedor_id else None
    if not prov:
        raise ValueError("Elegí el proveedor al que se le compra.")

    preparadas = []
    for linea in lineas:
        codigo = normalizar_codigo(linea.get("codigo"))
        prod = _producto(conn, codigo) if codigo else None
        if not prod:
            raise ValueError(
                f"El código «{codigo}» no está en el catálogo. Revisalo, o agregá el "
                "producto antes de comprarlo.")
        try:
            cantidad = float(linea.get("cantidad"))
        except (TypeError, ValueError):
            raise ValueError(f"«{codigo}»: la cantidad no se entiende.")
        if cantidad <= 0:
            raise ValueError(f"«{codigo}»: la cantidad tiene que ser mayor que cero.")
        precio = (centimos(linea.get("precio"))
                  if str(linea.get("precio") or "").strip() != ""
                  else prod["valor_unitario"])
        preparadas.append((codigo, prod["descripcion"], cantidad, precio,
                           linea.get("cuenta_id")))

    numero = siguiente_numero(conn)
    cur = conn.execute(
        """INSERT INTO pv_documento (numero, tipo, fecha, proveedor_id, departamento,
               solicitado_por, observaciones, origen, creado_por)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (numero, TIPO_COMPRA, fecha or datetime.date.today().isoformat(), prov["id"],
         departamento, normalizar_texto(solicitado_por),
         normalizar_texto(observaciones), ORIGEN_APP, usuario))
    doc_id = cur.lastrowid
    for codigo, descripcion, cantidad, precio, cuenta_id in preparadas:
        conn.execute(
            """INSERT INTO pv_movimiento (documento_id, codigo, descripcion, cantidad,
                   signo, estado, departamento, valor_unitario, cuenta_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (doc_id, codigo, descripcion, cantidad, ENTRA, "Solicitado", departamento,
             precio, cuenta_id))
    conn.commit()
    return orden(conn, doc_id)


def orden(conn, doc_id):
    """Una orden de compra entera: cabecera, líneas, estado y total."""
    d = conn.execute(
        """SELECT d.*, p.nombre AS proveedor, p.correo AS proveedor_correo,
                  p.contacto AS proveedor_telefono,
                  p.nombre_contacto AS proveedor_contacto, p.condicion, p.dias_credito
             FROM pv_documento d LEFT JOIN pv_proveedor p ON p.id = d.proveedor_id
            WHERE d.id = ?""", (doc_id,)).fetchone()
    if not d or d["tipo"] != TIPO_COMPRA:
        return None
    salida = dict(d)
    salida["lineas"] = [dict(x) for x in conn.execute(
        """SELECT m.id, m.codigo, m.descripcion, m.cantidad, m.estado,
                  m.valor_unitario, m.cuenta_id, p.unidad, c.codigo AS cuenta
             FROM pv_movimiento m
             LEFT JOIN pv_producto p ON p.codigo = m.codigo
             LEFT JOIN pv_cuenta c ON c.id = m.cuenta_id
            WHERE m.documento_id = ? ORDER BY m.id""", (doc_id,))]
    for l in salida["lineas"]:
        l["total"] = (int(round(l["valor_unitario"] * l["cantidad"]))
                      if l["valor_unitario"] is not None else None)
    con_precio = [l for l in salida["lineas"] if l["total"] is not None]
    salida["total"] = sum(l["total"] for l in con_precio)
    # CUÁNTAS LÍNEAS QUEDAN SIN PRECIO. El total de una orden de compra es lo que el
    # lodge se compromete a pagar: enseñarlo como si estuviera completo cuando falta el
    # precio de tres renglones es la clase de cifra que se firma sin mirar.
    salida["lineas_sin_precio"] = len(salida["lineas"]) - len(con_precio)
    estados = {l["estado"] for l in salida["lineas"]}
    # El estado de la ORDEN se deriva de sus líneas; no se guarda, por lo mismo de
    # siempre: con los dos, el día que una línea cambie los dos dirían cosas distintas.
    salida["estado"] = (estados.pop() if len(estados) == 1
                        else "Recibida a medias")
    salida["recibidas"] = sum(1 for l in salida["lineas"]
                              if l["estado"] == ESTADO_EN_BODEGA)
    # Va en la cabecera y no se cuenta en la pantalla: la lista de órdenes no trae las
    # líneas —serían cientos— y aun así tiene que poder decir «3 de 7 recibidas».
    salida["lineas_total"] = len(salida["lineas"])
    return salida


def ordenes(conn, estado=None, limite=60):
    """Las órdenes de compra, con su estado derivado de las líneas."""
    filas = [dict(r) for r in conn.execute(
        f"""SELECT d.id FROM pv_documento d
             WHERE d.tipo = ? ORDER BY d.fecha DESC, d.id DESC LIMIT ?""",
        (TIPO_COMPRA, max(1, min(limite, 300))))]
    salida = []
    for f in filas:
        o = orden(conn, f["id"])
        if o and (not estado or o["estado"] == estado):
            # La lista no necesita cada línea: solo cuántas y cómo van.
            o.pop("lineas", None)
            salida.append(o)
    return salida


def recibir(conn, doc_id, lineas_ids=None, factura=None, usuario=None):
    """Da por RECIBIDAS unas líneas de una orden: a partir de ahí son stock.

    SE PUEDE RECIBIR A MEDIAS, y es el caso normal, no la excepción: el bote trae lo que
    cabe y el resto queda para el viaje siguiente. `lineas_ids` dice cuáles llegaron;
    sin él, llegaron todas.

    RECIBIR ES LO QUE SUMA EL STOCK. Hasta ese momento la orden existe, se puede imprimir
    y se le puede mandar al proveedor, pero en la bodega no hay nada — que es la verdad.
    """
    o = orden(conn, doc_id)
    if not o:
        raise ValueError("Esa orden de compra no existe.")
    if o["origen"] != ORIGEN_APP:
        raise ValueError("Esa orden vino de la hoja de cálculo: se recibe en la hoja.")
    ids = {int(x) for x in (lineas_ids or [])} or {l["id"] for l in o["lineas"]}
    pendientes = [l for l in o["lineas"]
                  if l["id"] in ids and l["estado"] != ESTADO_EN_BODEGA]
    if not pendientes:
        return o, ["Esas líneas ya estaban recibidas."]
    for l in pendientes:
        conn.execute("UPDATE pv_movimiento SET estado = ? WHERE id = ?",
                     (ESTADO_EN_BODEGA, l["id"]))
    if factura is not None:
        conn.execute("UPDATE pv_documento SET factura = ? WHERE id = ?",
                     (normalizar_texto(factura), doc_id))
    conn.commit()
    return orden(conn, doc_id), []


def marcar_pedida(conn, doc_id):
    """De «Solicitado» a «Pendiente de Ingreso»: ya se le mandó al proveedor.

    Son dos cosas distintas y la hoja las distingue —69 solicitadas y 449 pendientes de
    ingreso—: una está pedida dentro de la casa y la otra está en manos del proveedor. A
    quien persigue un pedido le cambia a quién llamar.
    """
    o = orden(conn, doc_id)
    if not o:
        raise ValueError("Esa orden de compra no existe.")
    conn.execute(
        "UPDATE pv_movimiento SET estado = 'Pendiente de Ingreso' "
        "WHERE documento_id = ? AND estado = 'Solicitado'", (doc_id,))
    conn.commit()
    return orden(conn, doc_id)


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
