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
    # Con el régimen van las bebidas incluidas y la cortesía: las tres dicen qué trae
    # pagado la reserva y las tres salen del mismo texto, así que se escriben juntas.
    #
    # Estar en esta lista NO es opcional. Hay dos caminos de escritura: el INSERT OR
    # REPLACE de abajo, que usa la fuente completa, y este, que arma las columnas según
    # lo que la fuente manda y es el que usa Opera. Una columna que falte aquí se guarda
    # por el primer camino y se queda en NULL por el segundo —sin dar ningún error—, que
    # es exactamente lo que pasó con estas dos.
    "regimen": ("regimen", "bebidas_incluidas", "cortesia"),
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
        """SELECT id, amenidad, fecha, detalle, tarea, estado, editado_a_mano, oculta
           FROM amenidad_tarea WHERE conf_no = ? AND origen = ? ORDER BY id""",
        (r["conf_no"], origen),
    ).fetchall():
        # 'oculta' se guarda igual que lo editado a mano, y por la misma razón: es una
        # decisión de una persona. Si no se conservara, la alergia que alguien quitó
        # porque no aplicaba volvería en la siguiente sincronización y el botón de
        # «quitar» parecería no haber hecho nada.
        if prev["editado_a_mano"] or prev["oculta"] or prev["estado"] != "PENDIENTE":
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
        # El trozo de texto por el que se reconoció la amenidad. Antes esto quedaba en
        # None y a cocina le llegaba «Restricción alimentaria / alergia» sin decir de
        # qué: el dato venía en el reporte y se perdía aquí. Lo que recepción haya
        # escrito a mano sigue mandando —se resuelve unas líneas más abajo—.
        detalle = (r.get("detalles_de_amenidad") or {}).get(nombre)
        estado = "PENDIENTE"
        editado = 0
        oculta = 0
        # Lo que recepción ya había hecho sobre esta misma amenidad manda sobre lo que
        # dice el reporte: el reporte no sabe qué noche se acordó la cena, ni que la
        # alergia resultó ser también a la lactosa, ni que la cuna ya está puesta.
        areas_previas = None
        guardado = trabajo_previo.get(nombre)
        if guardado:
            p = guardado.pop(0)
            estado = p["estado"]
            oculta = 1 if p["oculta"] else 0
            if p["editado_a_mano"]:
                editado = 1
                fecha = p["fecha"]
                detalle = p["detalle"]
                tarea = p["tarea"] or tarea
                # Los departamentos que recepción le puso a mano. El catálogo solo sabe
                # de uno; si alguien decidió que esto también le toca a cocina, el
                # reporte no tiene por qué deshacerlo.
                areas_previas = p.get("areas")
        # LA MISMA AMENIDAD VISTA POR DOS FUENTES ES UNA SOLA.
        #
        # Cada fuente borra y regenera SOLO sus filas —por lo que dice el docstring— y
        # eso dejaba un duplicado en cuanto la misma alergia la veían el PDF y Opera: dos
        # filas de «Restricción alimentaria / alergia» para la misma reserva, con recortes
        # distintos del mismo texto. Es lo que el lodge vio en la hoja de cocina: la
        # habitación 09 con «Lactose, hazelnut and peanut allergy Mr.» y «Lactose,
        # hazelnut and peanut allergy», una debajo de la otra.
        #
        # Se borra la de la OTRA fuente, no la de esta: la que acaba de escribir es la
        # que está al día. Si el huésped cambió su alergia, Opera lo sabe y el PDF
        # importado hace meses no.
        #
        # NO se toca la que alguien editó a mano o ya marcó hecha: eso es trabajo de
        # recepción o de cocina, y el principio de no pisarlo sigue mandando. En ese caso
        # se hereda aquí abajo, igual que si fuera de esta misma fuente.
        gemela = cur.execute(
            """SELECT id, estado, editado_a_mano, oculta, fecha, detalle, tarea
               FROM amenidad_tarea
               WHERE conf_no = ? AND amenidad = ? AND origen <> ?
               ORDER BY id LIMIT 1""",
            (r["conf_no"], nombre, origen)).fetchone()
        if gemela:
            if gemela["oculta"]:
                oculta = 1
            if gemela["editado_a_mano"] or gemela["estado"] != "PENDIENTE":
                # Se adopta su trabajo y se queda UNA sola fila, la de esta fuente.
                estado = gemela["estado"]
                if gemela["editado_a_mano"]:
                    editado = 1
                    fecha = gemela["fecha"]
                    detalle = gemela["detalle"]
                    tarea = gemela["tarea"] or tarea
                    areas_previas = [(x["area"], x["estado"]) for x in cur.execute(
                        "SELECT area, estado FROM amenidad_area WHERE amenidad_id = ? "
                        "ORDER BY rowid", (gemela["id"],))] or areas_previas
            cur.execute("DELETE FROM amenidad_area WHERE amenidad_id = ?",
                        (gemela["id"],))
            cur.execute("DELETE FROM amenidad_tarea WHERE id = ?", (gemela["id"],))

        cur.execute(
            """INSERT INTO amenidad_tarea (conf_no, amenidad, detalle, tarea,
                                           area_responsable, fecha, estado,
                                           editado_a_mano, oculta, origen)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (r["conf_no"], nombre, detalle, tarea,
             (areas_previas or [(area, estado)])[0][0], fecha, estado, editado,
             oculta, origen),
        )
        nueva_id = cur.lastrowid
        # Su fila de departamento. Sin esto la amenidad no le aparecería a nadie en la
        # pantalla, que agrupa por departamento.
        for nombre_area, estado_area in (areas_previas or [(area, estado)]):
            cur.execute(
                """INSERT OR IGNORE INTO amenidad_area (amenidad_id, area, estado)
                   VALUES (?,?,?)""", (nueva_id, nombre_area, estado_area))

        # LA ALERGIA QUE NO ES DE COMIDA VA COMO ALERTA DE LA RESERVA, y nada más.
        #
        # Lo decidió el lodge: no sale en la hoja de amenidades —no se prepara desde
        # ahí— ni en la pestaña de cocina —no pueden hacer nada con ella—. Lo que hace
        # falta es que alguien la vea al abrir la reserva, y para eso está el aviso.
        #
        # La fila de amenidad se guarda igual: es donde vive el texto y el estado. El
        # aviso la señala; no la reemplaza.
        if _rest.es_alergia_no_alimentaria(nombre, tarea, detalle):
            mensaje = (f"Alergia NO alimentaria en la hab. {r.get('room_no') or '—'} "
                       f"(reserva {r['conf_no']}, llega {r.get('arr_date')}): "
                       f"«{(detalle or nombre).strip()[:160]}». "
                       f"No es de cocina — revisar almohadas y ropa de cama.")
            ya = cur.execute(
                "SELECT 1 FROM alerta WHERE tipo='ALERGIA_NO_ALIMENTARIA' "
                "AND mensaje=? AND resuelto=0", (mensaje,)).fetchone()
            if not ya:
                cur.execute(
                    "INSERT INTO alerta (tipo, referencia_id, mensaje) "
                    "VALUES ('ALERGIA_NO_ALIMENTARIA', ?, ?)", (nueva_id, mensaje))


def _sacar_de_la_operacion(cur, conf_no):
    """Una reserva cancelada deja de ocupar la operación. Devuelve cuánto se quitó.

    Lo pidió el lodge: «todas las reservas que estén canceladas, es mejor que no
    aparezcan en la operación». Y tenía más razón de la que parece. Medido sobre la
    ventana de hoy: la alerta «PNC el 27 de noviembre tiene 14 pax, hacen falta 2 guías»
    salía de SIETE reservas canceladas y NINGUNA viva. Recepción iba a repartir dos guías
    para un tour al que no va nadie.

    Tres tablas, y solo esas tres:

      · los tours, que son los que arman la hoja del día, el bote y el guía;
      · las tareas de amenidad, que le piden trabajo a un departamento;
      · el itinerario, que es la página que ve el huésped.

    NO se tocan las entradas del SINAC. Van por tour+fecha y no por reserva, así que
    pueden estar YA COMPRADAS y cubriendo además a huéspedes vivos de ese mismo día
    —medido: hoy hay 2 así—. Borrarlas tiraría una entrada pagada.

    Tampoco se destruye trabajo hecho: una amenidad que recepción ya editó o ya dio por
    hecha se queda. Si alguien preparó el vino, el registro de que lo preparó no
    desaparece porque la reserva se caiga.

    Es reversible: si la reserva vuelve a estar viva, el siguiente ciclo la vuelve a
    cargar y regenera todo desde la nota. Ya existe `_retirar_aviso_de_cancelacion` para
    el aviso, por la misma razón.
    """
    quitado = 0
    quitado += cur.execute(
        "DELETE FROM tour_asignado WHERE conf_no = ?", (conf_no,)).rowcount
    quitado += cur.execute(
        """DELETE FROM amenidad_tarea
           WHERE conf_no = ? AND estado = 'PENDIENTE'
             AND (editado_a_mano IS NULL OR editado_a_mano = 0)""",
        (conf_no,)).rowcount
    quitado += cur.execute(
        "DELETE FROM itinerario WHERE conf_no = ?", (conf_no,)).rowcount
    return quitado


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
        "SELECT fecha, tour_codigo, guia_nombre, bote_nombre, grupo_operativo, "
        "       pax, pax_editado_a_mano "
        "FROM tour_asignado WHERE conf_no = ? ORDER BY fecha",
        (r["conf_no"],),
    ).fetchall():
        # El pax puesto a mano viaja con el guía y el bote, y por la misma razón: es
        # trabajo de recepción que el reporte no sabe y que volvería a quedar en «la
        # habitación entera» en cada importación. Si el tour se corrió de día, se mueve
        # con él —quien no iba a ir tampoco va el día nuevo—.
        pax_a_mano = prev["pax"] if prev["pax_editado_a_mano"] else None
        if (prev["guia_nombre"] or prev["bote_nombre"]
                or prev["grupo_operativo"] != "A" or pax_a_mano is not None):
            datos_prev = (prev["guia_nombre"], prev["bote_nombre"],
                          prev["grupo_operativo"], pax_a_mano)
            asignaciones_previas[(prev["fecha"], prev["tour_codigo"])] = datos_prev
            asignaciones_por_tour.setdefault(prev["tour_codigo"], []).append(datos_prev)

    # Los tours agregados a mano desde el itinerario NO están en el reporte, así que
    # regenerar los borraría. Se conservan: el huésped ya los tiene prometidos y la
    # operación ya les asignó guía y bote.
    cur.execute("DELETE FROM tour_asignado WHERE conf_no = ? "
                "AND IFNULL(origen, 'PDF') <> 'MANUAL'", (r["conf_no"],))

    # Los códigos que el catálogo conoce. tour_asignado.tour_codigo tiene clave foránea
    # contra tour_catalogo, así que un código que no exista NO da un tour perdido: revienta
    # el INSERT con IntegrityError y tumba la carga ENTERA de la sincronización —todas las
    # reservas del ciclo, no solo esta—. Un código nuevo en la nomenclatura, o una errata
    # de Reservaciones, bastaba para dejar al hotel sin actualizar y sin saber por qué.
    del_catalogo = {x["codigo"] for x in cur.execute("SELECT codigo FROM tour_catalogo")}
    # Los códigos que el catálogo ya marca como privados («PNC PRIVADO»). Es la otra vía
    # por la que llega la modalidad: Opera la manda pegada al código y un PDF la escribe
    # en el nombre del tour. Las dos acaban en tour_asignado.es_privado.
    privados_del_catalogo = {x["codigo"] for x in cur.execute(
        "SELECT codigo FROM tour_catalogo WHERE es_privado = 1")}

    for a in r.get("agenda") or []:
        # Se traduce AQUÍ, en la última puerta antes de escribir. Los códigos ya vienen
        # traducidos por el lector de notas, pero no todos los caminos pasan por él —los
        # paquetes de Opera, un tour agregado a mano, una importación futura—, y basta con
        # que uno entregue «CIS» en crudo para que la agenda muestre un tour NUEVO al lado
        # del SNORKEL de siempre, con el mismo huésped contado dos veces.
        a["tour"] = _codigo_del_catalogo(a["tour"], del_catalogo) or a["tour"]
        if a["tour"] not in del_catalogo:
            # Se avisa y se sigue. Perder un tour con aviso es malo; perder la
            # sincronización del hotel sin decir por qué es mucho peor.
            cur.execute(
                "INSERT INTO alerta (tipo, referencia_id, mensaje) VALUES (?,NULL,?)",
                ("TOUR_SIN_CATALOGO",
                 f"La reserva {r['conf_no']} pide «{a['tour']}» el {a['fecha']} y ese "
                 f"código no está en el catálogo de tours. Agrégalo desde Catálogo o "
                 f"corrige la nota en Opera."))
            continue
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
        guia_prev, bote_prev, grupo_prev, pax_prev = asignacion or (None, None, "A", None)
        # El pax de recepción manda sobre el del reporte: lo escribió alguien que habló
        # con el huésped. Si baja el número de gente de la habitación, se recorta, porque
        # no pueden ir a un tour más personas de las que hay en la reserva.
        pax_a_mano = 0
        if pax_prev is not None:
            pax_del_tour = min(pax_prev, r["adl"] + r["chl"]) or pax_prev
            pax_a_mano = 1
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
        # LA MODALIDAD, por sus dos vías. Opera la manda pegada al código («PRV-PNC») y
        # llega en a["privado"]; un PDF escribe el código privado del catálogo («PNC
        # PRIVADO»). Las dos acaban en la misma columna para que ninguna pantalla tenga
        # que mirar en dos sitios y puedan contradecirse.
        # Tres vías, porque hay tres formas de que un tour llegue privado: el paquete de
        # Opera lo dice con el prefijo, el PDF lo dice en el código del catálogo, y hay
        # servicios que el lodge solo vende en privado —la pesca deportiva— y que por la
        # nota del itinerario llegarían sin decirlo.
        import opera_paquetes as _op_priv
        es_privado = 1 if (a.get("privado")
                           or a["tour"] in privados_del_catalogo
                           or a["tour"] in _op_priv.TOURS_SIEMPRE_PRIVADOS) else 0
        if ya_manual:
            # El pax puesto a mano NO se pisa: el reporte solo sabe cuánta gente hay en la
            # habitación, y aquí ya alguien anotó cuántos van de verdad. La modalidad SÍ
            # se refresca: la pone la fuente, no recepción, y si el huésped pasó su tour a
            # privado hay que enterarse.
            cur.execute(
                """UPDATE tour_asignado
                      SET origen = 'PDF',
                          pax = CASE WHEN pax_editado_a_mano THEN pax ELSE ? END,
                          conf_entrada_sinac = COALESCE(conf_entrada_sinac, ?),
                          es_privado = ?
                   WHERE id = ?""",
                (pax_del_tour, a.get("conf_entrada"), es_privado, ya_manual["id"]))
            continue
        cur.execute(
            """INSERT INTO tour_asignado
               (conf_no, fecha, tour_codigo, pax, pax_editado_a_mano, conf_entrada_sinac,
                guia_nombre, bote_nombre, grupo_operativo, es_privado, origen)
               VALUES (?,?,?,?,?,?,?,?,?,?,'PDF')""",
            (r["conf_no"], a["fecha"], a["tour"], pax_del_tour, pax_a_mano,
             a.get("conf_entrada"), guia_prev, bote_prev, grupo_prev, es_privado),
        )


def _guardar_traslados_extra(cur, r, origen="PDF"):
    """Los BT («boat transfer») que pide la reserva, para que salgan en Transporte.

    Se regeneran como las amenidades —se borran los de esta fuente y se vuelven a leer—
    porque lo que manda es lo que diga la reserva: si recepción corrige el día en Opera,
    la corrida tiene que moverse con él.

    La ASIGNACIÓN no se toca: vive en 'traslado', con la misma clave que las demás
    corridas, así que mover el día deja la corrida nueva sin cubrir —que es justo lo que
    hay que ver— en vez de arrastrar un bote que nadie confirmó para la fecha nueva.
    """
    import boat_transfer as _bt

    llegada = _iso_de_ddmmyy(r.get("arr_date"))
    salida = _iso_de_ddmmyy(r.get("dep_date"))
    # EL DÍA sale del itinerario («08: BT»), que es donde la reserva lo escribe. El
    # texto solo aporta la hora y el contexto. Deducir el día de una frase suelta ponía
    # botes en fechas inventadas y repetía el mismo viaje una vez por cada campo donde
    # la nota aparecía: medido, la habitación 09 salía con 5 corridas donde hay 2.
    dias = [x.get("dia") for x in (r.get("traslados_extra") or []) if x.get("dia")]
    # 'notas_operacion' va el PRIMERO y no puede faltar: es donde el lodge escribe la
    # frase que pide el BT («Clientes solicitan BT para tour con Pacheco. Llegan a las
    # 6:25 AM»). Sin ella, el trozo que se enseñaba en la corrida acababa siendo el del
    # rooming —que está al lado y tiene números de pasaporte— y quien iba a coordinar el
    # bote leía «Rooming: Donna Hoyle 644669711…» en vez de con quién se engancha.
    def _plano(valor):
        """Algunos de estos campos son LISTAS de renglones, no texto.

        Con str() se colaban los corchetes de Python y la corrida mostraba
        «['Clientes solicitan BT…']» en la pantalla del muelle.
        """
        if isinstance(valor, (list, tuple)):
            return " ".join(_plano(x) for x in valor)
        return str(valor or "")

    texto = " ".join(_plano(r.get(c)) for c in
                     ("notas_operacion", "notas", "texto_completo", "adicionales_raw",
                      "nota_ingreso", "nota_en_casa", "nota_salida"))
    viajes, avisos = _bt.leer(dias, texto, llegada, salida)

    cur.execute("DELETE FROM traslado_extra WHERE conf_no = ? AND origen = ?",
                (r["conf_no"], origen))
    for v in viajes:
        cur.execute(
            """INSERT INTO traslado_extra (conf_no, fecha, hora, nota, origen)
               VALUES (?,?,?,?,?)""",
            (r["conf_no"], v["fecha"], v["hora"], v["nota"], origen))

    # Un BT sin día NO se inventa: se avisa. Un bote preparado el día que no era cuesta
    # lo mismo que no prepararlo, y encima nadie lo revisa porque la pantalla ya decía
    # que estaba cubierto.
    # UN aviso por reserva, no uno por frase. El mismo BT se nombra en varios campos y
    # el texto del aviso cambia un poco entre ellos, así que deduplicar por el mensaje
    # exacto dejaba pasar dos y tres avisos del mismo viaje.
    for aviso in avisos[:1]:
        mensaje = (f"Hab. {r.get('room_no') or '—'} (reserva {r['conf_no']}): {aviso}")
        ya = cur.execute(
            "SELECT 1 FROM alerta WHERE tipo='BT_SIN_FECHA' AND resuelto=0 "
            "AND mensaje LIKE ?", (f"Hab.%(reserva {r['conf_no']}):%",)).fetchone()
        if not ya:
            cur.execute(
                "INSERT INTO alerta (tipo, referencia_id, mensaje) "
                "VALUES ('BT_SIN_FECHA', NULL, ?)", (mensaje,))


def _codigo_del_catalogo(codigo, del_catalogo):
    """El código del lodge para lo que venga, o None si no se reconoce.

    Acepta el código propio («SNORKEL»), el de la nomenclatura 2027 («CIS»), el mismo con
    prefijo de modalidad («C-CIS», «PRV|C-PNC») y los alias de siempre. Una sola tabla de
    equivalencias, la de opera_paquetes: si aquí se tradujera distinto, el mismo código
    significaría una cosa al importar y otra al leer la nota.
    """
    limpio = (codigo or "").strip().upper()
    import opera_paquetes as op

    # La EQUIVALENCIA va primero, incluso si el alias existe como tour en el catálogo.
    # Pasa de verdad: recepción puede haber creado «CIS» a mano desde la pantalla de
    # Catálogo antes de que el sistema lo reconociera. Si aquí se aceptara tal cual, la
    # agenda seguiría llenando dos tours —CIS y SNORKEL— con la misma gente repartida
    # entre los dos, que es justo lo que se quiere unificar.
    clasificado = op.clasificar(limpio)
    if (clasificado["tipo"] == "tour" and clasificado["valor"]
            and clasificado["valor"] != limpio
            and clasificado["valor"] in del_catalogo):
        return clasificado["valor"]
    if limpio in del_catalogo:
        return limpio
    if clasificado["tipo"] == "tour" and clasificado["valor"] in del_catalogo:
        return clasificado["valor"]
    import pdf_parser
    alias = pdf_parser.TOUR_ALIASES.get(limpio)
    return alias if alias in del_catalogo else None


def _aviso_de_cancelacion(nombre, hab, llegada, conf_no):
    """El texto del aviso de cancelación. En un solo sitio, para poder retirarlo.

    Lleva el número de reserva porque es lo único que no cambia: el nombre se corrige,
    la habitación se cambia, la fecha se mueve. Sin él no había manera de reconocer el
    aviso cuando la reserva volvía, y quedaba colgado para siempre.
    """
    return (f"Reserva cancelada: {nombre} (hab. {hab}, {llegada}, conf {conf_no}) "
            f"ya no aparece en la información actualizada. "
            f"Revisar tours y entradas asociadas.")


def _retirar_aviso_de_cancelacion(cur, r, previo):
    """Retira el aviso de cancelación de una reserva que volvió a estar viva.

    Una reserva que la base tenía por CANCELADA y la fuente reporta viva es una
    resurrección: o la cancelación era falsa, o en Opera la reinstalaron. En los dos
    casos el aviso que quedó colgado ya no dice nada cierto, y una lista llena de avisos
    falsos consigue que nadie mire los verdaderos.

    Se retiran los avisos que llevan el número de reserva —el formato de ahora— y
    también los que escribió la versión anterior, que no lo llevaban: esos se reconocen
    por el nombre, la habitación y la fecha con los que la reserva estaba guardada.
    """
    if not previo or str(previo["estado"] or "").upper() != "CANCELADA":
        return
    if str(r.get("res_status") or "").upper() == "CANCELADA":
        return
    cur.execute(
        """UPDATE alerta SET resuelto = 1
           WHERE tipo = 'RESERVA_CANCELADA' AND resuelto = 0
             AND (mensaje LIKE ? OR mensaje LIKE ?)""",
        (f"%conf {r['conf_no']})%",
         f"Reserva cancelada: {previo['nombre']} (hab. {previo['hab']}, "
         f"{previo['llegada']})%"))


def load_batch(batch, fuente_pdf="Arrivals__Detailed.PDF", marcar_ausentes_como_canceladas=True,
               manda_en="TODO", origen_parcial="OPERA", vistas_por_la_fuente=None):
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

    'vistas_por_la_fuente' son TODAS las reservas que la fuente vio, no solo las que
    trae este lote. Solo lo usa la regla de cancelación, y es la diferencia entre
    cancelar bien y borrar el día de la operación: ver el comentario largo de esa regla,
    más abajo. Una fuente que trae la hoja completa —el PDF— no lo pasa: su lote ya es
    todo lo que vio.

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

    # Lo que trae ESTE lote, que es lo que se va a escribir. Ojo: no es lo mismo que
    # todo lo que la fuente vio. La regla de cancelación necesita eso otro.
    confs_del_lote = []
    fechas_del_lote = set()

    for item in batch["reservas"]:
        r = item["reserva"]
        confs_del_lote.append(r["conf_no"])
        if r.get("arr_date"):
            fechas_del_lote.add(r["arr_date"])

        # El grupo NO se arma desde la nota del reporte. Un texto escrito a mano no une
        # habitaciones solo: se propone en Reservas y recepción decide (sugerencias.py).
        # Antes se armaba aquí, y salía mal: el grupo se le ponía a la reserva que TRAÍA
        # la nota y no a la nombrada, así que quedaba un grupo de una sola habitación
        # que ninguna pantalla mostraba.
        #
        # Lo único que se conserva es la decisión ya tomada: si recepción confirmó el
        # grupo, el reporte no la pisa. Sin esto, cada importación borraría el trabajo
        # de recepción, porque la reserva se reescribe entera.
        # Se leen también el estado y los datos con los que la reserva estaba guardada.
        # Sirven para reconocer una RESURRECCIÓN —la base la tenía por cancelada y la
        # fuente la reporta viva— y retirar el aviso de cancelación que quedó colgado.
        previo = cur.execute(
            """SELECT r.grupo_id AS gid, g.confirmado_por_recepcion AS confirmado,
                      r.res_status AS estado, r.nombre_principal AS nombre,
                      r.room_no AS hab, r.arr_date AS llegada
               FROM reserva r LEFT JOIN grupo g ON g.id = r.grupo_id
               WHERE r.conf_no = ?""", (r["conf_no"],)).fetchone()
        grupo_id = previo["gid"] if previo and previo["confirmado"] else None
        _retirar_aviso_de_cancelacion(cur, r, previo)

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
            #
            # LA CANCELADA SALE DE LA OPERACIÓN TAMBIÉN POR AQUÍ. Este es el camino que
            # usa Opera, o sea por donde pasan casi todas. El guardia tiene que estar en
            # los DOS caminos de escritura: puesto solo en el otro, no se disparaba nunca
            # en producción. Y aquí no se mira 'manda': que una reserva esté cancelada no
            # es un área que una fuente administre, es un hecho sobre la reserva entera.
            if str(r.get("res_status") or "").upper() == "CANCELADA":
                _sacar_de_la_operacion(cur, r["conf_no"])
                continue
            if "rooming" in manda and r.get("rooming"):
                _guardar_rooming(cur, r)
            if "amenidades" in manda:
                _guardar_amenidades(cur, r, _iso_de_ddmmyy(r.get("arr_date")),
                                    origen=origen_parcial)
            # El BT va con el transporte, que es lo que es: un viaje de bote.
            if "transporte" in manda:
                _guardar_traslados_extra(cur, r, origen=origen_parcial)
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
                regimen, bebidas_incluidas, cortesia)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                r.get("bebidas_incluidas"), r.get("cortesia"),
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
        if str(r.get("res_status") or "").upper() == "CANCELADA":
            _sacar_de_la_operacion(cur, r["conf_no"])
        else:
            _guardar_amenidades(cur, r, _iso_de_ddmmyy(r.get("arr_date")))
            _guardar_traslados_extra(cur, r)
            _guardar_rooming(cur, r)
            _guardar_tours(cur, r)

    # --- Reservas que la fuente ya no reporta: se marcan como CANCELADA ---
    #
    # LA DISTINCIÓN QUE IMPORTA, y que costó un día de operación: el LOTE son las
    # reservas que se escriben; el UNIVERSO son TODAS las que la fuente vio. Esta regla
    # necesita el universo. Confundirlos hace exactamente lo contrario de lo que se
    # busca: en vez de reflejar las cancelaciones de la fuente, inventa cancelaciones.
    #
    # Cómo se rompió. Opera carga solo lo que cambió, a propósito —reescribir las 70
    # reservas cada media hora borraría la marca de "esto cambió" que mira recepción—,
    # así que su lote es un puñado de reservas. Con el lote como universo bastaba que
    # UNA reserva de hoy cambiara para que la fecha de hoy entrara en la lista y todas
    # las demás llegadas del día, intactas y solo sin cambios, quedaran CANCELADA. Fue
    # lo que vio el hotel: un cambio de habitación por la mañana y media lista de
    # llegadas del día en cancelada.
    #
    # El PDF no pasa 'vistas_por_la_fuente' y no le hace falta: trae la hoja completa,
    # así que su lote ES su universo. Solo se miran las fechas de llegada que la fuente
    # cubre, para no tocar periodos de los que no sabe nada.
    if vistas_por_la_fuente is None:
        confs_presentes, fechas_cubiertas = confs_del_lote, fechas_del_lote
    else:
        confs_presentes = [x["conf_no"] for x in vistas_por_la_fuente if x.get("conf_no")]
        fechas_cubiertas = {x["arr_date"] for x in vistas_por_la_fuente if x.get("arr_date")}

    if marcar_ausentes_como_canceladas and confs_presentes and fechas_cubiertas:
        marcadores_fecha = ",".join("?" for _ in fechas_cubiertas)
        marcadores_conf = ",".join("?" for _ in confs_presentes)
        ausentes = cur.execute(
            f"""SELECT conf_no, room_no, nombre_principal, arr_date FROM reserva
                WHERE arr_date IN ({marcadores_fecha})
                  AND conf_no NOT IN ({marcadores_conf})
                  AND res_status != 'CANCELADA'""",
            list(fechas_cubiertas) + list(confs_presentes),
        ).fetchall()

        # LA VÁLVULA. Si desaparecieron más reservas de las que la fuente reportó, el
        # universo está mal y no hay nada que cancelar: hay algo que arreglar. Se avisa
        # y no se toca ninguna.
        #
        # Con datos buenos no se dispara nunca: en un ciclo normal desaparecen cero o
        # una sobre las setenta que sí vinieron. Está aquí como segunda línea, para que
        # un error de este tipo no vuelva a llegar callado a la operación — una reserva
        # borrada de la agenda no la nota nadie hasta que el huésped está en la puerta.
        if len(ausentes) > len(confs_presentes):
            mensaje = (
                f"No se cancelaron {len(ausentes)} reservas que dejaron de aparecer: "
                f"la fuente solo reportó {len(confs_presentes)} en esas fechas, así que "
                f"la lista venía incompleta. Las reservas se dejaron como estaban. "
                f"Revisar la sincronización antes de darlas por canceladas."
            )
            ya = cur.execute(
                "SELECT 1 FROM alerta WHERE tipo='CANCELACION_SOSPECHOSA' AND mensaje=? "
                "AND resuelto=0", (mensaje,)).fetchone()
            if not ya:
                cur.execute(
                    "INSERT INTO alerta (tipo, referencia_id, mensaje) "
                    "VALUES ('CANCELACION_SOSPECHOSA', NULL, ?)", (mensaje,))
            ausentes = []

        for a in ausentes:
            cur.execute("UPDATE reserva SET res_status = 'CANCELADA' WHERE conf_no = ?", (a["conf_no"],))
            # Y sale de la operación, igual que las que llegan ya canceladas en el lote.
            # Este camino es el otro: la reserva no viene en la fuente y se deduce que se
            # cayó. Sin esto, las canceladas por ausencia seguían con sus tours puestos.
            _sacar_de_la_operacion(cur, a["conf_no"])
            mensaje = _aviso_de_cancelacion(a["nombre_principal"], a["room_no"],
                                            a["arr_date"], a["conf_no"])
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
    if confs_del_lote:
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
        # Las canceladas se saltan. Sin esto el itinerario se volvía a escribir aquí
        # justo después de que `_sacar_de_la_operacion` lo borrara, y la reserva caída
        # seguía teniendo su página de bienvenida como si el huésped viniera.
        cancelados = {x["conf_no"] for x in cur.execute(
            "SELECT conf_no FROM reserva WHERE res_status = 'CANCELADA'")}
        for conf_no in confs_del_lote:
            if conf_no in cancelados:
                continue
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
