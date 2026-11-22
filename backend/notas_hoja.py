"""Las notas que alguien escribe A MANO sobre la hoja de operación.

POR QUÉ EXISTE. Lo pidió el lodge: «que también sea editable en la parte de notas, ahí
mismo [en la previsualización] … que sea capaz de guardar todo lo editado en fechas
posteriores — las notas escritas ahí permanecen solo ahí, no en ninguna otra parte de la
app».

ESA ÚLTIMA FRASE ES LA REGLA ENTERA, y es la razón de que esto sea una tabla aparte en
vez de un campo más de la reserva. La columna NOTAS de la hoja se llena sola con lo que
viene de Opera —la nota de la reserva, el vuelo, el BT— y escribir encima de eso tendría
dos fallos, los dos callados:

  · la siguiente importación de Opera lo borraría sin avisar, porque la nota de la
    reserva es un campo que la carga reescribe;
  · lo escrito para UN día aparecería en los otros cuatro que el huésped está alojado,
    porque la nota de la reserva no tiene fecha.

Aquí una nota es de un DÍA y de una RESERVA, y nada de lo que trae Opera la toca.

SE GUARDA POR RESERVA, NO POR HABITACIÓN. Es la misma lección que ya está escrita tres
veces en hoja_dia.py: el número de cuarto se reutiliza, y el día que cambia de huésped
—55 veces en los próximos cuatro meses— el que SE VA y el que LLEGA tienen el mismo. Una
nota pegada al número de cuarto saldría en los dos renglones, y la mitad de las veces en
el equivocado: en el del huésped a quien no le toca.

LOS TOPES DE LARGO NO SON MANÍA DE ORDEN. La hoja del día cabe en una página porque la
letra encoge hasta que quepa; una nota de mil caracteres en un renglón obligaría a toda
la hoja a encoger por un solo cuarto, y lo que se pierde es la letra de los otros
veintitrés. Con 200 por renglón entran tres líneas largas, que es lo que el lodge escribe
a mano en su Excel.
"""
import datetime

# Lo que cabe escrito a mano. Ver el porqué arriba.
LIMITE_FILA = 200
LIMITE_DIA = 700

# El destino de la nota del día entero. Vacío y no NULL para que el UNIQUE de la tabla
# sirva: en SQLite dos NULL no chocan entre sí, así que con NULL se podrían guardar
# catorce notas del mismo día sin que nada se quejara.
DIA = ""


def limpiar(texto, limite):
    """El texto tal como se guarda: sin saltos de línea y recortado al tope.

    Los saltos se quitan porque la casilla de la tabla es UNA casilla: un salto ahí no se
    ve como un renglón nuevo, se ve como un espacio raro, y en el Excel rompe la altura
    de toda la fila.
    """
    return " ".join(str(texto or "").split())[:limite]


def _ahora():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def leer(conn, fecha):
    """Lo escrito a mano para un día: {'dia': texto, 'filas': {conf_no: texto}, …}."""
    filas, dia, cuando, quien = {}, "", None, None
    reemplazan = set()
    for f in conn.execute(
            """SELECT destino, texto, reemplaza, actualizado_en, actualizado_por
                 FROM nota_hoja WHERE fecha = ?""", (fecha,)):
        if f["destino"] == DIA:
            dia = f["texto"]
        else:
            filas[str(f["destino"])] = f["texto"]
            if f["reemplaza"]:
                reemplazan.add(str(f["destino"]))
        if not cuando or (f["actualizado_en"] or "") > cuando:
            cuando, quien = f["actualizado_en"], f["actualizado_por"]
    return {"fecha": fecha, "dia": dia, "filas": filas, "reemplazan": reemplazan,
            "actualizado_en": cuando, "actualizado_por": quien}


def leer_varias(conn, fechas):
    """{fecha: leer(…)} en UNA consulta, para la hoja de un rango.

    Un rango puede ser de 400 días y la hoja se arma día por día; preguntando dentro del
    bucle serían 400 consultas para traer, casi siempre, ninguna fila.
    """
    salida = {f: {"fecha": f, "dia": "", "filas": {}, "reemplazan": set(),
                  "actualizado_en": None, "actualizado_por": None} for f in fechas}
    if not fechas:
        return salida
    marcas = ",".join("?" * len(fechas))
    for f in conn.execute(
            f"""SELECT fecha, destino, texto, reemplaza, actualizado_en, actualizado_por
                  FROM nota_hoja WHERE fecha IN ({marcas})""", list(fechas)):
        d = salida.get(f["fecha"])
        if d is None:
            continue
        if f["destino"] == DIA:
            d["dia"] = f["texto"]
        else:
            d["filas"][str(f["destino"])] = f["texto"]
            if f["reemplaza"]:
                d["reemplazan"].add(str(f["destino"]))
        if not d["actualizado_en"] or (f["actualizado_en"] or "") > d["actualizado_en"]:
            d["actualizado_en"], d["actualizado_por"] = (f["actualizado_en"],
                                                         f["actualizado_por"])
    return salida


def guardar(conn, fecha, destino, texto, usuario=None, reemplaza=False):
    """Escribe una nota. Vacía BORRA la fila, que es lo que significa borrar una nota.

    Guardar la cadena vacía dejaría una fila que no dice nada y que la pantalla tendría
    que aprender a ignorar; y peor, la hoja llevaría un « · » colgando delante de la nota
    automática, un separador sin nada a la izquierda.

    `reemplaza` dice si lo escrito SUSTITUYE a lo que la hoja ya decía de ese renglón, en
    vez de ir delante. Lo pidió el lodge para poder corregir una nota del sistema que
    está mal, sin tener que dejarla puesta y escribir la corrección al lado.

    BORRAR LA NOTA DEVUELVE EL RENGLÓN A LO AUTOMÁTICO. Se borra la fila entera, marca
    incluida: si no, un renglón sin texto y con la marca puesta dejaría la casilla NOTAS
    en blanco para siempre y sin nada que tocar para recuperarla.
    """
    destino = str(destino or DIA)
    texto = limpiar(texto, LIMITE_DIA if destino == DIA else LIMITE_FILA)
    if not texto:
        conn.execute("DELETE FROM nota_hoja WHERE fecha = ? AND destino = ?",
                     (fecha, destino))
        return ""
    # La nota del DÍA va en su propia caja al pie de la hoja: ahí no hay nada automático
    # a lo que sustituir, así que la marca no significaría nada.
    marca = 1 if (reemplaza and destino != DIA) else 0
    conn.execute(
        """INSERT INTO nota_hoja (fecha, destino, texto, reemplaza,
                                  actualizado_en, actualizado_por)
                VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT (fecha, destino) DO UPDATE
                SET texto = excluded.texto,
                    reemplaza = excluded.reemplaza,
                    actualizado_en = excluded.actualizado_en,
                    actualizado_por = excluded.actualizado_por""",
        (fecha, destino, texto, marca, _ahora(), usuario))
    return texto


def guardar_varias(conn, fecha, dia=None, filas=None, usuario=None, reemplazan=None):
    """Guarda la nota del día y las de los renglones que vengan. Devuelve `leer()`.

    Solo toca lo que viene: mandar `{"filas": {"73001": "…"}}` no borra la nota del día ni
    la de las otras habitaciones. Así la pantalla puede guardar un renglón suelto sin
    tener que reenviar —y arriesgarse a pisar— lo que no estaba editando.

    `reemplazan` es el conjunto de renglones cuya nota sustituye a la automática. Va
    aparte del texto y no pegado a él para que la pantalla pueda mandar las dos cosas sin
    inventarse una marca dentro de la cadena: una marca dentro del texto acabaría saliendo
    impresa el día que alguien escribiera esos caracteres a propósito.
    """
    if dia is not None:
        guardar(conn, fecha, DIA, dia, usuario)
    marcados = {str(x) for x in (reemplazan or ())}
    for destino, texto in (filas or {}).items():
        guardar(conn, fecha, destino, texto, usuario,
                reemplaza=str(destino) in marcados)
    conn.commit()
    return leer(conn, fecha)
