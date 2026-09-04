"""Inserta el resultado de importer.build_review_batch() en la base de datos."""
from init_db import get_connection


def _iso_de_ddmmyy(valor):
    """'05-08-26' -> '2026-08-05'. None si no tiene esa forma.

    Las fechas de la reserva se guardan como 'DD-MM-YY', pero amenidad_tarea.fecha va
    en ISO (es la que compara la pantalla de restaurantes). Se convierte aquí y se
    devuelve None ante cualquier cosa rara, para que un dato torcido del PDF no deje
    una amenidad con una fecha inventada.
    """
    try:
        d, m, y = str(valor).strip().split("-")
        if len(y) != 2 or not (d.isdigit() and m.isdigit() and y.isdigit()):
            return None
        dia, mes = int(d), int(m)
        if not (1 <= dia <= 31 and 1 <= mes <= 12):
            return None
        return f"20{y}-{mes:02d}-{dia:02d}"
    except (ValueError, AttributeError):
        return None


def _filas_fuera_de_estadia(filas, arr_date, dep_date):
    """Actividades cuya fecha quedó fuera de la estadía del huésped. Pasa cuando
    recepción agregó algo a mano y después la reserva se movió de fechas."""
    import itinerario as _it

    def a_par(iso):
        """'2026-08-05' -> (8, 5), comparable con el orden de las filas."""
        try:
            _y, m, d = iso.split("-")
            return (int(m), int(d))
        except (ValueError, AttributeError):
            return None

    ini, fin = a_par(arr_date), a_par(dep_date)
    if not ini or not fin:
        return []
    fuera = []
    for f in filas:
        clave = _it._clave_orden(f)
        if clave == (0, 0):
            continue
        if clave < ini or clave > fin:
            fuera.append(f"{f.get('dia')} {' '.join((f.get('actividad') or '').split())}")
    return fuera


# Las columnas de 'reserva' que Opera Cloud SÍ entrega en esta propiedad y por lo tanto
# puede mandar. Todo lo que no esté en esta lista lo sigue mandando el PDF.
#
# POR QUÉ HACE FALTA ESTA LISTA: el PDF trae la reserva COMPLETA, así que reescribir la
# fila entera es correcto para él. Opera, en cambio, entrega solo el núcleo —Oracle no
# concede los bloques de paquetes ni de comentarios—, y reescribir la fila entera con lo
# que Opera trae dejaría en blanco todo lo demás.
#
# Medido antes de existir esta lista, sobre una reserva real con trabajo hecho: al correr
# la sincronización se perdían sus 3 tours, sus 2 amenidades, el régimen de comidas, las
# notas de operación y el punto de embarque. Y no daba ningún error: la reserva quedaba
# ahí, con los datos correctos y el resto vacío.
COLUMNAS_DEL_NUCLEO = (
    "room_no", "nombre_principal", "company_travel_agent", "arr_date", "dep_date",
    "arr_time", "room_type", "adl", "chl", "rooms", "mkt_code", "src_code",
    "res_status", "block_code",
    # La marca de Opera. Se guarda junto al núcleo para que el próximo ciclo sepa que
    # esta reserva ya está al día.
    "opera_modificado_en",
)

# Qué columnas de 'reserva' pertenecen a cada área. Solo se escriben las de las áreas
# que la fuente manda; las demás se quedan como estaban.
COLUMNAS_POR_AREA = {
    "nucleo": COLUMNAS_DEL_NUCLEO,
    "regimen": ("regimen",),
    "textos": ("nota_ingreso", "nota_en_casa", "nota_salida", "notas_operacion",
               "notas_libres", "guia_sugerido"),
    "transporte": ("punto_entrada", "punto_salida", "punto_entrada_sin_confirmar",
                   "punto_salida_sin_confirmar", "hora_vuelo_entrada",
                   "hora_vuelo_salida", "vuelo_entrada", "vuelo_salida"),
}

# Todas las áreas que existen. Las tres últimas no son columnas: son tablas aparte.
AREAS = frozenset(COLUMNAS_POR_AREA) | {"tours", "amenidades", "rooming"}


def _valor_de_columna(r, columna):
    """El valor que va en esa columna, tomado del diccionario de la reserva.

    Dos columnas no se llaman igual que su llave, y confundirlas no da error: escribe
    NULL y borra el dato.
      notas_libres    <- r['notas']            (la llave nunca se llamó igual)
      notas_operacion <- lista, hay que unirla (SQLite no acepta una lista)
    """
    if columna == "notas_libres":
        return r.get("notas")
    if columna == "notas_operacion":
        return " · ".join(r.get("notas_operacion") or []) or None
    return r.get(columna)

# El PDF trae la hoja completa, así que manda en todo. Es el comportamiento de siempre.
MANDA_TODO = frozenset(AREAS)


def _areas_que_manda(manda_en):
    """Normaliza 'manda_en' a un conjunto de áreas.

    Se aceptan los nombres cortos "TODO" y "NUCLEO" además del conjunto explícito,
    porque son los dos casos de siempre y así quien llama no tiene que enumerar.
    """
    if manda_en == "TODO":
        return MANDA_TODO
    if manda_en == "NUCLEO":
        return frozenset({"nucleo"})
    if isinstance(manda_en, (set, frozenset, list, tuple)):
        pedidas = frozenset(manda_en)
        desconocidas = pedidas - AREAS
        if desconocidas:
            raise ValueError(f"areas no reconocidas: {sorted(desconocidas)}")
        if "nucleo" not in pedidas:
            # Sin el núcleo no hay reserva que actualizar: casi seguro es un error de
            # quien llama, y fallar aquí es mejor que escribir a medias.
            raise ValueError("manda_en tiene que incluir 'nucleo'")
        return pedidas
    raise ValueError(f"manda_en no reconocido: {manda_en!r}")


def _guardar_amenidades(cur, r, llegada_iso, origen="PDF"):
    """Regenera las amenidades de esta reserva, conservando el trabajo hecho a mano.

    'origen' dice de qué filas es dueña esta fuente. CADA FUENTE ADMINISTRA SOLO LAS
    SUYAS, y esto no es un detalle: las amenidades casi siempre están escritas en las
    notas de la reserva, y esas notas no se pueden leer por el API. Si la
    sincronización con Opera borrara las del PDF para poner las suyas, borraría casi
    todas —medido: los paquetes de Opera traen una amenidad en 1 de 223 reservas—.
    Así, Opera agrega la cena privada y el detalle de bienvenida que sí conoce, y no
    toca nada más.

    Lo que recepción hizo a mano sobre las amenidades del reporte —el día que les puso,
    el texto que corrigió, si ya están hechas y qué departamentos le asignó— se guarda
    ANTES de borrarlas, porque enseguida se regeneran. Sin esto ese trabajo se perdía en
    silencio: la noche que recepción le había asignado a una cena privada volvía a
    quedar vacía, y la amenidad que housekeeping ya había marcado hecha volvía a
    aparecer pendiente. Medido: se perdía en la primera reimportación.

    Se guarda por NOMBRE de amenidad porque es lo único estable entre una importación y
    la siguiente —la fila se borra, así que el id no sirve—. Si la misma reserva trae
    dos veces la misma amenidad, se restauran en orden.
    """
    import restaurantes as _rest

    trabajo_previo = {}
    for prev in cur.execute(
        """SELECT id, amenidad, fecha, detalle, tarea, estado, editado_a_mano
           FROM amenidad_tarea WHERE conf_no = ? AND origen = ? ORDER BY id""",
        (r["conf_no"], origen),
    ).fetchall():
        if prev["editado_a_mano"] or prev["estado"] != "PENDIENTE":
            d = dict(prev)
            # Los departamentos con el estado de cada uno, para poder devolverlos tal
            # cual: si cocina ya hizo su parte y housekeeping no, reimportar no debe
            # reabrir la de cocina ni cerrar la de housekeeping.
            d["areas"] = [(x["area"], x["estado"]) for x in cur.execute(
                "SELECT area, estado FROM amenidad_area WHERE amenidad_id = ? "
                "ORDER BY rowid", (prev["id"],))]
            trabajo_previo.setdefault(prev["amenidad"], []).append(d)

    # Al borrar las de esta fuente se van también sus filas de departamento.
    cur.execute(
        """DELETE FROM amenidad_area WHERE amenidad_id IN
             (SELECT id FROM amenidad_tarea WHERE conf_no = ? AND origen = ?)""",
        (r["conf_no"], origen))
    # Solo las de esta fuente; las de las otras y las que agregó recepción a mano se
    # conservan.
    cur.execute("DELETE FROM amenidad_tarea WHERE conf_no = ? AND origen = ?",
                (r["conf_no"], origen))

    # Fechas que la fuente sí conoce, por nombre de amenidad. El PDF no manda ninguna;
    # Opera sí trae la fecha de la cena privada y del detalle de bienvenida, y una
    # fecha real siempre es mejor que la de llegada por omisión.
    fechas_conocidas = r.get("fechas_de_amenidad") or {}

    for amenidad in r.get("amenidades_detectadas", []):
        catalog_row = cur.execute(
            "SELECT nombre, tarea_automatica, area_responsable FROM amenidad_catalogo WHERE nombre = ?",
            (amenidad,),
        ).fetchone()
        if catalog_row:
            nombre = catalog_row["nombre"]
            tarea = catalog_row["tarea_automatica"]
            area = catalog_row["area_responsable"]
        else:
            # Detectada pero sin fila en el catálogo (porque se renombró, se borró, o la
            # base es anterior a esa amenidad). Antes se descartaba en silencio y nadie
            # se enteraba de que el huésped la tenía pedida. Se guarda igual, con una
            # tarea genérica, para que alguien la vea.
            nombre = amenidad
            tarea = (f"Revisar con recepción: se menciona «{amenidad}» "
                     "y no está en el catálogo")
            area = "Recepción"

        # La fecha en que hay que tener lista la amenidad. Por omisión, el día de
        # llegada: el sofá cama, la cuna, la decoración, la canasta de frutas y la
        # tarjeta de bienvenida tienen que estar puestas ANTES del check-in, y a cocina
        # la alergia le sirve saberla antes de que el huésped se siente a comer.
        #
        # La CENA PRIVADA es la excepción, y se deja sin fecha a propósito cuando la
        # fuente no la sabe: el PDF avisa que existe pero casi nunca dice qué noche.
        # Ponerle la llegada sería inventarle un día, y además apagaría el aviso de
        # "contratadas sin noche asignada", que hoy es lo que hace que recepción
        # pregunte y lo confirme. Un dato inventado es peor que un dato faltante que
        # alguien está vigilando.
        if nombre in fechas_conocidas and fechas_conocidas[nombre]:
            fecha = fechas_conocidas[nombre]
        elif _rest.es_cena_privada(nombre, tarea):
            fecha = None
        else:
            fecha = llegada_iso
        detalle = None
        estado = "PENDIENTE"
        editado = 0
        # Lo que recepción ya había hecho sobre esta misma amenidad manda sobre lo que
        # dice el reporte: el reporte no sabe qué noche se acordó la cena, ni que la
        # alergia resultó ser también a la lactosa, ni que la cuna ya está puesta.
        areas_previas = None
        guardado = trabajo_previo.get(nombre)
        if guardado:
            p = guardado.pop(0)
            estado = p["estado"]
            if p["editado_a_mano"]:
                editado = 1
                fecha = p["fecha"]
                detalle = p["detalle"]
                tarea = p["tarea"] or tarea
                # Los departamentos que recepción le puso a mano. El catálogo solo sabe
                # de uno; si alguien decidió que esto también le toca a cocina, el
                # reporte no tiene por qué deshacerlo.
                areas_previas = p.get("areas")
        cur.execute(
            """INSERT INTO amenidad_tarea (conf_no, amenidad, detalle, tarea,
                                           area_responsable, fecha, estado,
                                           editado_a_mano, origen)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (r["conf_no"], nombre, detalle, tarea,
             (areas_previas or [(area, estado)])[0][0], fecha, estado, editado,
             origen),
        )
        nueva_id = cur.lastrowid
        # Su fila de departamento. Sin esto la amenidad no le aparecería a nadie en la
        # pantalla, que agrupa por departamento.
        for nombre_area, estado_area in (areas_previas or [(area, estado)]):
            cur.execute(
                """INSERT OR IGNORE INTO amenidad_area (amenidad_id, area, estado)
                   VALUES (?,?,?)""", (nueva_id, nombre_area, estado_area))


def _guardar_rooming(cur, r):
    """Los acompañantes de la reserva. Se regeneran enteros en cada importación."""
    cur.execute("DELETE FROM huesped WHERE conf_no = ?", (r["conf_no"],))
    for g in r.get("rooming") or []:
        cur.execute(
            "INSERT INTO huesped (conf_no, nombre_completo, pasaporte) VALUES (?,?,?)",
            (r["conf_no"], g["nombre"], g.get("pasaporte")),
        )


def _guardar_tours(cur, r, borrar_si_vacio=True):
    """Regenera los tours de esta reserva, conservando guía, bote y los manuales.

    Antes de borrar se guardan las asignaciones de guía y bote que recepción ya hizo,
    por fecha+tour y también agrupadas solo por tour: si el reporte actualizado mueve
    el tour de día, la asignación seguía siendo válida y antes se perdía —recepción
    tenía que volver a asignar todo—.

    'borrar_si_vacio' es la diferencia entre las dos fuentes, y es importante:

      El PDF trae la hoja completa. Si en el PDF una reserva no tiene tours, ES que no
      tiene: borrar los que hubiera es lo correcto.

      Opera solo ve los tours que están cargados como paquete, y no todos lo están
      —medido: 145 de 223 reservas activas traen paquetes de tour—. Para las otras, "no
      veo tours" NO significa "no tiene tours": significa que no puedo saberlo, porque
      esa parte vive en las notas de la reserva y el API no las entrega. Así que si
      Opera no trae ninguno, se dejan los que estén.
    """
    if not (r.get("agenda") or []) and not borrar_si_vacio:
        return

    asignaciones_previas = {}
    asignaciones_por_tour = {}
    for prev in cur.execute(
        "SELECT fecha, tour_codigo, guia_nombre, bote_nombre, grupo_operativo "
        "FROM tour_asignado WHERE conf_no = ? ORDER BY fecha",
        (r["conf_no"],),
    ).fetchall():
        if prev["guia_nombre"] or prev["bote_nombre"] or prev["grupo_operativo"] != "A":
            datos_prev = (prev["guia_nombre"], prev["bote_nombre"], prev["grupo_operativo"])
            asignaciones_previas[(prev["fecha"], prev["tour_codigo"])] = datos_prev
            asignaciones_por_tour.setdefault(prev["tour_codigo"], []).append(datos_prev)

    # Los tours agregados a mano desde el itinerario NO están en el reporte, así que
    # regenerar los borraría. Se conservan: el huésped ya los tiene prometidos y la
    # operación ya les asignó guía y bote.
    cur.execute("DELETE FROM tour_asignado WHERE conf_no = ? "
                "AND IFNULL(origen, 'PDF') <> 'MANUAL'", (r["conf_no"],))

    for a in r.get("agenda") or []:
        # Cuánta gente va a este tour. Si la fuente lo dice, se respeta; si no, se
        # asume que va toda la habitación, que es lo que hacía el PDF.
        pax_del_tour = a.get("pax")
        if not (isinstance(pax_del_tour, int) and pax_del_tour > 0):
            pax_del_tour = r["adl"] + r["chl"]
        asignacion = asignaciones_previas.pop((a["fecha"], a["tour"]), None)
        if asignacion is None:
            # No hay coincidencia exacta de fecha: el tour probablemente se movió de
            # día. Se recupera la asignación por tour, en orden, para no obligar a
            # recepción a reasignar guía y bote.
            pendientes_tour = asignaciones_por_tour.get(a["tour"])
            if pendientes_tour:
                asignacion = pendientes_tour.pop(0)
        guia_prev, bote_prev, grupo_prev = asignacion or (None, None, "A")
        # Si recepción ya lo había agregado a mano y ahora el reporte lo trae, es el
        # MISMO tour: se le cambia el origen en vez de insertar otro. Sin esto la
        # reserva quedaría con el tour dos veces —dos veces en la agenda, doble pax en
        # la entrada del parque—, que es la trampa de conservar los manuales.
        ya_manual = cur.execute(
            """SELECT id FROM tour_asignado
               WHERE conf_no = ? AND fecha = ? AND tour_codigo = ?
                 AND IFNULL(origen,'PDF') = 'MANUAL'""",
            (r["conf_no"], a["fecha"], a["tour"]),
        ).fetchone()
        if ya_manual:
            cur.execute(
                """UPDATE tour_asignado SET origen = 'PDF', pax = ?,
                       conf_entrada_sinac = COALESCE(conf_entrada_sinac, ?)
                   WHERE id = ?""",
                (pax_del_tour, a.get("conf_entrada"), ya_manual["id"]))
            continue
        cur.execute(
            """INSERT INTO tour_asignado
               (conf_no, fecha, tour_codigo, pax, conf_entrada_sinac, guia_nombre,
                bote_nombre, grupo_operativo, origen)
               VALUES (?,?,?,?,?,?,?,?,'PDF')""",
            (r["conf_no"], a["fecha"], a["tour"], pax_del_tour,
             a.get("conf_entrada"), guia_prev, bote_prev, grupo_prev),
        )


def load_batch(batch, fuente_pdf="Arrivals__Detailed.PDF", marcar_ausentes_como_canceladas=True,
               manda_en="TODO", origen_parcial="OPERA"):
    """Carga un lote de reservas ya procesado por el importador.

    'manda_en' dice DE QUÉ es dueña la fuente, por áreas: 'nucleo', 'regimen',
    'textos', 'transporte', 'tours', 'amenidades', 'rooming'. Lo que la fuente no
    manda no se toca: se queda como lo dejó la otra fuente o recepción.

      "TODO"   — todas las áreas (el PDF, que trae la hoja completa).
      "NUCLEO" — solo la reserva.
      un conjunto — lo que esa fuente entrega de verdad. Opera Cloud, por ejemplo,
                    manda en el núcleo, los tours, el régimen, las amenidades y el
                    rooming, pero NO en los textos ni en el punto de embarque, que no
                    entrega.

    'origen_parcial' es la etiqueta con la que una fuente parcial marca SUS amenidades,
    para no pisar las de las otras.

    POR QUÉ ESTO EXISTE. Antes había un solo camino, el del PDF, que reescribe la
    reserva entera y regenera tours y amenidades. Correcto para el PDF; destructivo
    para cualquier fuente que traiga menos. Medido sobre una reserva real con trabajo
    hecho: al sincronizar con Opera se perdían sus 3 tours, sus 2 amenidades, el
    régimen, las notas y el punto de embarque. Y sin dar un solo error —la reserva
    quedaba ahí, correcta, y el resto en blanco—.
    """
    manda = _areas_que_manda(manda_en)

    # El camino del PDF se usa SOLO cuando quien llama dice literalmente "TODO". Una
    # fuente que enumera sus áreas usa siempre el camino selectivo, aunque las
    # enumere todas.
    #
    # No es un detalle de estilo. El camino del PDF reescribe la fila entera con una
    # lista fija de columnas, y ahí no está 'opera_modificado_en': al pasar por él,
    # Opera borraba su propia marca de cambios y al ciclo siguiente creía que TODAS
    # las reservas habían cambiado. Además ese camino borra los tours de una reserva
    # que llega sin ninguno, que es justo lo que no debe hacer con Opera.
    por_areas = manda_en != "TODO"

    conn = get_connection()
    cur = conn.cursor()

    confs_en_pdf = []
    fechas_en_pdf = set()

    for item in batch["reservas"]:
        r = item["reserva"]
        confs_en_pdf.append(r["conf_no"])
        if r.get("arr_date"):
            fechas_en_pdf.add(r["arr_date"])

        # El grupo NO se arma desde la nota del reporte. Un texto escrito a mano no une
        # habitaciones solo: se propone en Reservas y recepción decide (sugerencias.py).
        # Antes se armaba aquí, y salía mal: el grupo se le ponía a la reserva que TRAÍA
        # la nota y no a la nombrada, así que quedaba un grupo de una sola habitación
        # que ninguna pantalla mostraba.
        #
        # Lo único que se conserva es la decisión ya tomada: si recepción confirmó el
        # grupo, el reporte no la pisa. Sin esto, cada importación borraría el trabajo
        # de recepción, porque la reserva se reescribe entera.
        previo = cur.execute(
            """SELECT r.grupo_id AS gid, g.confirmado_por_recepcion AS confirmado
               FROM reserva r LEFT JOIN grupo g ON g.id = r.grupo_id
               WHERE r.conf_no = ?""", (r["conf_no"],)).fetchone()
        grupo_id = previo["gid"] if previo and previo["confirmado"] else None

        if por_areas:
            # Se escriben SOLO las columnas de las áreas que esta fuente manda. Si la
            # reserva es nueva se inserta; si ya existía se actualiza dejando el resto
            # intacto.
            #
            # Se usa INSERT ... ON CONFLICT y no INSERT OR REPLACE justo por eso:
            # REPLACE borra la fila y la vuelve a escribir, así que cualquier columna
            # que no se nombre queda en su valor por omisión.
            propias = []
            for area, columnas_area in COLUMNAS_POR_AREA.items():
                if area in manda:
                    propias.extend(columnas_area)
            columnas = ", ".join(propias)
            marcas = ", ".join("?" * len(propias))
            asignaciones = ", ".join(f"{c} = excluded.{c}" for c in propias)
            valores = [_valor_de_columna(r, c) for c in propias]
            cur.execute(
                f"""INSERT INTO reserva (conf_no, fuente_pdf, {columnas})
                    VALUES (?, ?, {marcas})
                    ON CONFLICT(conf_no) DO UPDATE SET
                      fuente_pdf = excluded.fuente_pdf, {asignaciones}""",
                [r["conf_no"], fuente_pdf] + valores)

            # Y ahora, solo las tablas aparte que esta fuente manda. Una fuente parcial
            # administra sus propias filas y no borra lo que no ve: ver los comentarios
            # de _guardar_amenidades y _guardar_tours, que es donde está el porqué.
            if "rooming" in manda and r.get("rooming"):
                _guardar_rooming(cur, r)
            if "amenidades" in manda:
                _guardar_amenidades(cur, r, _iso_de_ddmmyy(r.get("arr_date")),
                                    origen=origen_parcial)
            if "tours" in manda:
                # Solo se borran los tours si la fuente LEYÓ el itinerario y estaba
                # vacío. Si ni siquiera pudo leerlo, no sabe nada y no debe borrar.
                _guardar_tours(cur, r,
                               borrar_si_vacio=bool(r.get("itinerario_leido")))
            continue

        cur.execute(
            """INSERT OR REPLACE INTO reserva (conf_no, grupo_id, room_no, nombre_principal, company_travel_agent,
                arr_date, dep_date, arr_time, room_type, adl, chl, rooms, mkt_code,
                src_code, res_status, guia_sugerido, guia_confirmado, punto_entrada,
                punto_salida, punto_entrada_sin_confirmar, punto_salida_sin_confirmar,
                hora_vuelo_entrada, hora_vuelo_salida, vuelo_entrada, vuelo_salida, nota_ingreso,
                nota_en_casa, nota_salida, notas_operacion, notas_libres, fuente_pdf, block_code,
                regimen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                r["conf_no"], grupo_id, r["room_no"], r["nombre_principal"], r["company_travel_agent"],
                r["arr_date"], r["dep_date"], r["arr_time"], r["room_type"], r["adl"], r["chl"], r["rooms"],
                r["mkt_code"], r["src_code"], r["res_status"], r["guia_sugerido"],
                r["punto_entrada"], r["punto_salida"],
                r.get("punto_entrada_sin_confirmar"), r.get("punto_salida_sin_confirmar"),
                r.get("hora_vuelo_entrada"), r.get("hora_vuelo_salida"),
                r.get("vuelo_entrada"), r.get("vuelo_salida"),
                r.get("nota_ingreso"), r.get("nota_en_casa"), r.get("nota_salida"),
                " · ".join(r.get("notas_operacion") or []) or None, r["notas"], fuente_pdf,
                r.get("block_code"), r.get("regimen"),
            ),
        )

        # Si el PDF menciona un ingreso o salida sin un punto reconocido (Sierpe/Drake),
        # se crea una alerta para que recepción lo confirme manualmente.
        for tipo, texto in (("entrada", r.get("punto_entrada_sin_confirmar")),
                            ("salida", r.get("punto_salida_sin_confirmar"))):
            if texto:
                mensaje = (
                    f"Confirmar punto de {tipo} de {r['nombre_principal']} (hab. {r['room_no']}, "
                    f"{r['arr_date']}): el PDF dice \"{texto}\" — no indica Sierpe ni Drake."
                )
                ya = cur.execute(
                    "SELECT 1 FROM alerta WHERE tipo='TRANSPORTE_SIN_CONFIRMAR' AND mensaje=? AND resuelto=0",
                    (mensaje,),
                ).fetchone()
                if not ya:
                    cur.execute(
                        "INSERT INTO alerta (tipo, referencia_id, mensaje) VALUES ('TRANSPORTE_SIN_CONFIRMAR', NULL, ?)",
                        (mensaje,),
                    )

        # Al reimportar un PDF (algo normal: primero el mes completo, luego
        # actualizaciones diarias), estos registros se vuelven a generar. Las tres
        # funciones se encargan de borrar lo anterior sin perder el trabajo hecho a
        # mano; son las MISMAS que usa cualquier otra fuente, para que una corrección
        # aquí llegue también a las reservas de Opera.
        _guardar_amenidades(cur, r, _iso_de_ddmmyy(r.get("arr_date")))
        _guardar_rooming(cur, r)
        _guardar_tours(cur, r)

    # Reservas que ya no aparecen en el PDF: se marcan como CANCELADA.
    # Solo se revisan las fechas de llegada que SÍ vienen en este PDF, para no tocar
    # reservas de periodos que este archivo no cubre (ej. si el PDF es de un solo día,
    # no se cancelan las de todo el mes).
    if marcar_ausentes_como_canceladas and confs_en_pdf and fechas_en_pdf:
        marcadores_fecha = ",".join("?" for _ in fechas_en_pdf)
        marcadores_conf = ",".join("?" for _ in confs_en_pdf)
        ausentes = cur.execute(
            f"""SELECT conf_no, room_no, nombre_principal, arr_date FROM reserva
                WHERE arr_date IN ({marcadores_fecha})
                  AND conf_no NOT IN ({marcadores_conf})
                  AND res_status != 'CANCELADA'""",
            list(fechas_en_pdf) + confs_en_pdf,
        ).fetchall()
        for a in ausentes:
            cur.execute("UPDATE reserva SET res_status = 'CANCELADA' WHERE conf_no = ?", (a["conf_no"],))
            mensaje = (
                f"Reserva cancelada: {a['nombre_principal']} (hab. {a['room_no']}, {a['arr_date']}) "
                f"ya no aparece en el PDF actualizado. Revisar tours y entradas asociadas."
            )
            ya = cur.execute(
                "SELECT 1 FROM alerta WHERE tipo='RESERVA_CANCELADA' AND mensaje=? AND resuelto=0", (mensaje,)
            ).fetchone()
            if not ya:
                cur.execute(
                    "INSERT INTO alerta (tipo, referencia_id, mensaje) VALUES ('RESERVA_CANCELADA', NULL, ?)",
                    (mensaje,),
                )

    # --- Entradas del SINAC ---
    # Se busca la existente y se ACTUALIZA, en vez de insertar de nuevo. Antes se usaba
    # INSERT OR REPLACE confiando en la restricción de la tabla, pero en SQLite dos NULL
    # no se consideran iguales: las entradas pendientes de comprar —las que no tienen
    # número de confirmación— se duplicaban en cada reimportación del reporte.
    # Además, reemplazar la fila le cambiaba el id, y ese id es el que referencian los
    # avisos y el botón de "marcar comprada".
    for e in batch["entradas_sinac"]:
        nota = ("Contradicción detectada en notas — revisar antes de confirmar"
                if e["estado"] == "VER_NOTA" else None)
        previa = cur.execute(
            """SELECT id, estado FROM entrada_sinac
               WHERE tour_codigo = ? AND fecha = ?
                 AND IFNULL(conf_entrada,'') = IFNULL(?,'')""",
            (e["tour"], e["fecha"], e["conf_entrada"])).fetchone()
        if previa:
            # Una compra que recepción ya registró no se pisa: el reporte no sabe que
            # alguien fue al SINAC y la pagó.
            estado = "COMPRADA" if previa["estado"] == "COMPRADA" else e["estado"]
            cur.execute(
                """UPDATE entrada_sinac SET pax_total_grupo = ?, estado = ?, nota = ?
                   WHERE id = ?""",
                (e["pax_total_grupo"], estado, nota, previa["id"]))
        else:
            cur.execute(
                """INSERT INTO entrada_sinac
                   (tour_codigo, fecha, conf_entrada, pax_total_grupo, estado, nota)
                   VALUES (?,?,?,?,?,?)""",
                (e["tour"], e["fecha"], e["conf_entrada"], e["pax_total_grupo"],
                 e["estado"], nota))

    # Entradas que quedaron sin ninguna reserva detrás: pasa cuando el reporte
    # actualizado mueve el tour de día, cancela la reserva, o cuando se compra la
    # entrada de un grupo y la vieja "sin comprar" se queda sin nadie. Antes se
    # quedaban ahí para siempre y en pantalla aparecían como filas en cero, sin
    # habitación ni huésped, que parecían entradas por comprar cuando no lo eran.
    #
    # Se limpian solo si este reporte trajo reservas: con un PDF vacío o mal leído no se
    # borra nada.
    if confs_en_pdf:
        import sinac
        sinac.limpiar_huerfanas(conn)

    # Con las reservas ya guardadas se buscan las habitaciones que podrían ser familia
    # o venir juntas, para que recepción las tenga listas para revisar apenas termina
    # de subir el reporte.
    import sugerencias
    sugerencias.detectar(conn)

    conn.commit()

    # Se genera el itinerario de bienvenida de cada reserva importada, para que quede
    # listo sin que recepción tenga que pedirlo. Si recepción ya editó uno a mano,
    # NO se sobrescribe: se conserva y más adelante el sistema avisa si la reserva
    # cambió respecto a lo editado.
    try:
        import json as _json
        import itinerario as _itin
        for conf_no in confs_en_pdf:
            datos = _itin.datos_de_reserva(conn, conf_no)
            if not datos:
                continue
            filas, _avisos = _itin.construir_itinerario(datos)

            ya = cur.execute(
                "SELECT editado, filas_json FROM itinerario WHERE conf_no = ?", (conf_no,)
            ).fetchone()
            if ya and ya["editado"]:
                # El itinerario fue editado a mano: no se sobrescribe, pero SÍ se le
                # ajustan las fechas si la reserva cambió (cambio de habitación, de
                # check-in/check-out, o de día de un tour). Antes las filas quedaban
                # con la fecha vieja y el huésped recibía datos incorrectos; y al
                # "incorporar lo que falta" se duplicaban.
                guardadas = _json.loads(ya["filas_json"])
                ajustadas, movidas, faltantes = _itin.reconciliar_itinerario(guardadas, filas)

                if movidas:
                    cur.execute(
                        "UPDATE itinerario SET filas_json = ?, actualizado_en = datetime('now') "
                        "WHERE conf_no = ?",
                        (_json.dumps(ajustadas, ensure_ascii=False), conf_no))

                avisos_it = []
                if movidas:
                    avisos_it.append("Se ajustaron las fechas del itinerario: " + "; ".join(
                        f"{m['actividad']} {m['de']} → {m['a']}" for m in movidas[:4]) + ".")
                if faltantes:
                    avisos_it.append("Falta agregar: " + "; ".join(
                        f"{f['dia']} {' '.join((f.get('actividad') or '').split())}"
                        for f in faltantes) + ".")
                fuera = _filas_fuera_de_estadia(ajustadas, datos.get("arr_date_iso"),
                                                datos.get("dep_date_iso"))
                if fuera:
                    avisos_it.append("Quedaron fuera de la estadía: " + "; ".join(fuera) + ".")

                if avisos_it:
                    aviso = " ".join(avisos_it) + " Revisar antes de enviarlo al huésped."
                    cur.execute("UPDATE itinerario SET aviso_cambios = ? WHERE conf_no = ?",
                                (aviso, conf_no))
                    info = cur.execute(
                        "SELECT room_no, nombre_principal, arr_date FROM reserva WHERE conf_no = ?",
                        (conf_no,)).fetchone()
                    mensaje = (f"Itinerario por revisar: {info['nombre_principal']} "
                               f"(hab. {info['room_no']}, {info['arr_date']}) — {aviso}")
                    existe = cur.execute(
                        "SELECT 1 FROM alerta WHERE tipo='ITINERARIO_DESACTUALIZADO' "
                        "AND mensaje=? AND resuelto=0", (mensaje,)).fetchone()
                    if not existe:
                        cur.execute(
                            "INSERT INTO alerta (tipo, referencia_id, mensaje) "
                            "VALUES ('ITINERARIO_DESACTUALIZADO', NULL, ?)", (mensaje,))
                else:
                    cur.execute("UPDATE itinerario SET aviso_cambios = NULL WHERE conf_no = ?",
                                (conf_no,))
                continue
            cur.execute(
                """INSERT INTO itinerario (conf_no, nombre_bienvenida, filas_json, editado, actualizado_en)
                   VALUES (?,?,?,0,datetime('now'))
                   ON CONFLICT(conf_no) DO UPDATE SET
                     nombre_bienvenida=excluded.nombre_bienvenida,
                     filas_json=excluded.filas_json, actualizado_en=datetime('now')""",
                (conf_no, datos["nombre_bienvenida"], _json.dumps(filas, ensure_ascii=False)),
            )
        conn.commit()
    except Exception:
        # Si algo falla al armar itinerarios no se pierde la importación de reservas
        pass

    # Nota: la publicación del sitio de itinerarios NO se hace aquí. La dispara el
    # endpoint de importación en segundo plano, para que recepción no tenga que
    # esperar a que se generen 30 PDF y se suban ~13 MB.

    conn.close()


if __name__ == "__main__":
    from importer import build_review_batch
    batch = build_review_batch("/mnt/user-data/uploads/Arrivals__Detailed.PDF")
    load_batch(batch)
    print("Datos cargados en la base de datos.")
