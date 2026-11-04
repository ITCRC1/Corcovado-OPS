"""
Valida capacidad de botes y guías al asignar tours, generando alertas
y recomendaciones tal como se definió en el Documento de Requerimientos (9.1, 9.6).
"""
from init_db import get_connection


def sugerir_bote_alterno(conn, tour_codigo, fecha, pax_necesarios, bote_actual=None):
    """Busca un bote con capacidad suficiente para el pax restante, excluyendo el actual."""
    botes = conn.execute(
        "SELECT nombre, capacidad_max FROM bote WHERE gestionado_por_hotel = 1 AND capacidad_max >= ? "
        "AND nombre != COALESCE(?, '') ORDER BY capacidad_max ASC",
        (pax_necesarios, bote_actual),
    ).fetchall()
    return botes[0]["nombre"] if botes else None


def validar_tour_asignado(tour_asignado_id):
    """Revisa un tour_asignado contra capacidad de bote y de guía; crea alertas si aplica."""
    conn = get_connection()
    ta = conn.execute(
        "SELECT * FROM tour_asignado WHERE id = ?", (tour_asignado_id,)
    ).fetchone()
    if not ta:
        conn.close()
        return []

    alertas_creadas = []
    tour = conn.execute(
        "SELECT * FROM tour_catalogo WHERE codigo = ?", (ta["tour_codigo"],)
    ).fetchone()

    # LA MODALIDAD SEPARA LAS CUENTAS. Un tour privado es otra salida: lleva su propio
    # guía y su propio bote, que es para lo que se vende. Sumarlo con el compartido del
    # mismo día inventaría un sobrecupo que no existe —o taparía uno que sí—, y las dos
    # formas de equivocarse acaban igual: alguien en el muelle sin quien lo lleve.
    privado = 1 if ta["es_privado"] else 0

    # Capacidad de GUÍA: se valida por grupo operativo, porque cada grupo tiene su
    # propio guía (aunque compartan bote). Si la salida es privada se acota además a SU
    # reserva: privado quiere decir que va sola, así que dos privados del mismo día son
    # dos guías y sumarlos inventaría un sobrecupo.
    cond_priv = " AND conf_no = ?" if privado else ""
    args_priv = (ta["conf_no"],) if privado else ()
    pax_grupo = conn.execute(
        f"""SELECT COALESCE(SUM(pax),0) total FROM tour_asignado
            WHERE tour_codigo=? AND fecha=? AND grupo_operativo=?
              AND COALESCE(es_privado,0)=?{cond_priv}""",
        (ta["tour_codigo"], ta["fecha"], ta["grupo_operativo"], privado, *args_priv),
    ).fetchone()["total"]

    # Capacidad de BOTE: se valida sumando TODOS los grupos que van en ese mismo bote,
    # ya que dos grupos con guías distintos pueden viajar juntos en un solo bote.
    pax_bote = conn.execute(
        """SELECT COALESCE(SUM(pax),0) total FROM tour_asignado
           WHERE tour_codigo=? AND fecha=? AND bote_nombre IS ?
             AND COALESCE(es_privado,0)=?""",
        (ta["tour_codigo"], ta["fecha"], ta["bote_nombre"], privado),
    ).fetchone()["total"]

    privado_txt = " privado" if privado else ""
    grupo_txt = f" (grupo {ta['grupo_operativo']})" if ta["grupo_operativo"] != "A" else ""

    if ta["bote_nombre"]:
        bote = conn.execute(
            "SELECT * FROM bote WHERE nombre = ?", (ta["bote_nombre"],)
        ).fetchone()
        if bote and bote["capacidad_max"] and pax_bote > bote["capacidad_max"]:
            sugerido = sugerir_bote_alterno(conn, ta["tour_codigo"], ta["fecha"], pax_bote, ta["bote_nombre"])
            grupos_en_bote = conn.execute(
                """SELECT COUNT(DISTINCT grupo_operativo) c FROM tour_asignado
                   WHERE tour_codigo=? AND fecha=? AND bote_nombre IS ?
                     AND COALESCE(es_privado,0)=?""",
                (ta["tour_codigo"], ta["fecha"], ta["bote_nombre"], privado),
            ).fetchone()["c"]
            compartido = f" (compartido por {grupos_en_bote} grupos)" if grupos_en_bote > 1 else ""
            msg = (
                f"Bote {ta['bote_nombre']} (máx. {bote['capacidad_max']} pax) recibe {pax_bote} pax "
                f"en {ta['tour_codigo']}{privado_txt} el {ta['fecha']}{compartido}."
            )
            if sugerido:
                msg += f" Se sugiere el bote {sugerido}, o usar un segundo bote para otro grupo."
            else:
                msg += " Se sugiere usar un segundo bote para otro grupo."
            ya_existe = conn.execute(
                "SELECT 1 FROM alerta WHERE tipo='CAPACIDAD_BOTE' AND mensaje=? AND resuelto=0", (msg,)
            ).fetchone()
            if not ya_existe:
                conn.execute(
                    "INSERT INTO alerta (tipo, referencia_id, mensaje) VALUES ('CAPACIDAD_BOTE', ?, ?)",
                    (tour_asignado_id, msg),
                )
            alertas_creadas.append(msg)

    if tour and pax_grupo > tour["max_pax_guia"]:
        guias_necesarios = -(-pax_grupo // tour["max_pax_guia"])  # redondeo hacia arriba
        msg = (
            f"{ta['tour_codigo']}{privado_txt} el {ta['fecha']}{grupo_txt} tiene {pax_grupo} pax, "
            f"pero el máximo por guía es {tour['max_pax_guia']}. "
            f"Se necesitan {guias_necesarios} guías — divide el tour en {guias_necesarios} grupos."
        )
        ya_existe = conn.execute(
            "SELECT 1 FROM alerta WHERE tipo='CAPACIDAD_GUIA' AND mensaje=? AND resuelto=0", (msg,)
        ).fetchone()
        if not ya_existe:
            conn.execute(
                "INSERT INTO alerta (tipo, referencia_id, mensaje) VALUES ('CAPACIDAD_GUIA', ?, ?)",
                (tour_asignado_id, msg),
            )
        alertas_creadas.append(msg)

    conn.commit()
    conn.close()
    return alertas_creadas


def _iso(ddmmyy):
    """'30-01-26' -> '2026-01-30'. None si no tiene la forma del PMS."""
    texto = (ddmmyy or "").strip()
    if len(texto) != 8 or texto.count("-") != 2:
        return None
    d, m, y = texto.split("-")
    if not (d.isdigit() and m.isdigit() and y.isdigit()):
        return None
    return f"20{y}-{m}-{d}"


def minutos_del_reloj(texto):
    """'06:00' y '8:00 a.m.' -> minutos desde medianoche. None si no se entiende.

    Hacen falta los dos formatos porque vienen de sitios distintos: el catálogo de tours
    guarda la hora en 24 h y los horarios del día de salida se escriben como se le
    imprimen al huésped en su itinerario.
    """
    t = str(texto or "").strip().lower().replace(".", "").replace(" ", "")
    if not t:
        return None
    es_pm, es_am = t.endswith("pm"), t.endswith("am")
    reloj = t[:-2] if (es_pm or es_am) else t
    try:
        h, m = (int(x) for x in reloj.split(":"))
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    if es_pm and h < 12:
        h += 12
    if es_am and h == 12:
        h = 0
    return h * 60 + m


def revisar_tour_del_dia_de_salida(fila):
    """¿Este tour cae el día que el huésped se va y, si cae, le da tiempo de volver?

    LA REGLA LA DIO EL LODGE: el día de salida solo valen los tours cortos de la mañana,
    los que terminan ANTES de que salga el bote. Cualquier otro no es un tour: es un
    renglón que alguien va a leer en la hoja del día y va a contar para repartir guías.

    El caso real que lo destapó: hab. 30, 18→21 de noviembre, con PAJAREO el 21. El
    itinerario lo pone a las 6:00 a. m. y el pajareo dura dos horas — termina a las 8:00,
    que es justo la hora a la que sale el bote de Sierpe (equipaje 7:00, check-out 7:45).
    El huésped no llega. Y nada de eso daba error: el tour salía en la hoja como
    cualquier otro.

    SIN DATOS NO SE ESCONDE NADA. Si el tour no tiene hora en el catálogo, o no se sabe
    a qué hora sale el huésped, se deja a la vista y se avisa. Esconder por falta de
    datos es la forma de fallar que nadie revisa: la hoja sale tranquila y el renglón que
    faltaba no se echa de menos.

    Devuelve (cabe, motivo). 'motivo' es None cuando no hay nada que decir.
    """
    import traslados as _tras

    llega, sale = _iso(fila.get("arr_date")), _iso(fila.get("dep_date"))
    if not sale or fila.get("fecha") != sale:
        return True, None                      # no es del día de salida: no es asunto de aquí

    quien = (f"{fila.get('tour_codigo')} el {fila.get('fecha')} de "
             f"{fila.get('nombre_principal')} (hab. {fila.get('room_no')})")

    fin = minutos_del_reloj(fila.get("horario_fin"))
    hora_salida, _origen = _tras.hora_de_traslado(fila, es_entrada=False)
    salida = minutos_del_reloj(hora_salida)

    if fin is None:
        return True, (f"{quien} cae el día que se va y el catálogo no dice a qué hora "
                      f"termina, así que no se puede saber si llega al bote. "
                      f"Revisar con la agenda.")
    if salida is None:
        return True, (f"{quien} cae el día que se va y no se sabe a qué hora sale "
                      f"—falta el punto o la hora del vuelo—. Revisar con la agenda.")
    if fin < salida:
        return True, None                      # corto de la mañana: llega de sobra
    return False, (f"{quien} termina a las {fila.get('horario_fin')} y el bote sale a "
                   f"las {hora_salida}: no le da tiempo. No se cuenta en la hoja del "
                   f"día — si de verdad va, hay que mover el tour o la salida.")


def tours_del_dia_de_salida_que_no_caben(conn, fecha):
    """{id de tour_asignado: motivo} de los tours de ESA fecha que no llegan al bote.

    Lo usa el Resumen —y con él la hoja que se le manda al staff— para no contarlos. Es
    la MISMA función que usa el aviso, así que lo que se esconde y lo que se avisa no
    pueden decir cosas distintas.
    """
    dd = f"{fecha[8:10]}-{fecha[5:7]}-{fecha[2:4]}"      # ISO -> 'DD-MM-YY' del PMS
    filas = conn.execute(
        """SELECT ta.id, ta.fecha, ta.tour_codigo, tc.horario_fin,
                  r.room_no, r.nombre_principal, r.arr_date, r.dep_date,
                  r.punto_salida, r.hora_vuelo_salida
             FROM tour_asignado ta
             JOIN reserva r ON r.conf_no = ta.conf_no
             LEFT JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
            WHERE ta.fecha = ? AND r.dep_date = ?
              AND IFNULL(r.res_status,'') != 'CANCELADA'""", (fecha, dd)).fetchall()
    fuera = {}
    for f in filas:
        cabe, motivo = revisar_tour_del_dia_de_salida(dict(f))
        if not cabe:
            fuera[f["id"]] = motivo
    return fuera


def validar_tours_fuera_de_la_estadia():
    """Tours que caen antes de la llegada o después de la salida de su reserva.

    POR QUÉ EXISTE: los tours se reparten por fecha DESPUÉS de que entra la reserva.
    Si más adelante alguien mueve las fechas en el PMS —y eso pasa—, los tours ya
    repartidos se quedan en los días viejos. No da ningún error: el tour aparece en la
    agenda de un día en que el huésped no está en el lodge, y se descubre el día del
    tour, cuando ya no hay nada que hacer.

    Medido sobre la base real antes de escribir esto: de 1.164 tours, CERO caían fuera.
    Por eso este aviso sirve —está callado mientras todo esté bien y solo habla cuando
    de verdad pasó algo—. Un aviso que salta siempre se aprende a ignorar.

    Las canceladas se saltan: sus tours ya no importan y ensuciarían la lista.
    """
    conn = get_connection()
    filas = conn.execute(
        """SELECT t.id, t.fecha, t.tour_codigo, r.conf_no, r.room_no,
                  r.nombre_principal, r.arr_date, r.dep_date,
                  r.punto_salida, r.hora_vuelo_salida, tc.horario_fin
             FROM tour_asignado t
             JOIN reserva r ON r.conf_no = t.conf_no
             LEFT JOIN tour_catalogo tc ON tc.codigo = t.tour_codigo
            WHERE t.fecha IS NOT NULL
              AND IFNULL(r.res_status,'') != 'CANCELADA'""").fetchall()

    mensajes = []

    def avisar(tipo, id_tour, msg):
        ya = conn.execute(
            "SELECT 1 FROM alerta WHERE tipo=? AND mensaje=? AND resuelto=0",
            (tipo, msg)).fetchone()
        if not ya:
            conn.execute(
                "INSERT INTO alerta (tipo, referencia_id, mensaje) VALUES (?,?,?)",
                (tipo, id_tour, msg))
        mensajes.append(msg)

    for f in filas:
        f = dict(f)
        llega, sale = _iso(f["arr_date"]), _iso(f["dep_date"])
        if llega and f["fecha"] < llega:
            cuando = f"antes de que llegue ({f['arr_date']})"
        elif sale and f["fecha"] > sale:
            cuando = f"después de que se vaya ({f['dep_date']})"
        else:
            # EL BORDE DE ADENTRO. Caer DENTRO de la estadía no basta el día en que el
            # huésped se va: el último día solo hay sitio para los tours cortos de la
            # mañana. Se revisa aquí, con los demás tours fuera de sitio, porque es el
            # mismo fallo —un tour en un día en que el huésped no puede ir— y la única
            # diferencia es que este se nota menos.
            _cabe, motivo = revisar_tour_del_dia_de_salida(f)
            if motivo:
                avisar("TOUR_EL_DIA_QUE_SE_VA", f["id"], motivo)
            continue
        avisar("TOUR_FUERA_DE_ESTADIA", f["id"],
               f"{f['tour_codigo']} el {f['fecha']} le queda {cuando} a "
               f"{f['nombre_principal']} (hab. {f['room_no']}). "
               f"Revisar: cambiaron las fechas de la reserva después de repartir el tour.")

    conn.commit()
    conn.close()
    return mensajes


def validar_todos_los_tours(fecha=None):
    conn = get_connection()
    query = "SELECT id FROM tour_asignado"
    params = ()
    if fecha:
        query += " WHERE fecha = ?"
        params = (fecha,)
    ids = [row["id"] for row in conn.execute(query, params).fetchall()]
    conn.close()
    resultado = []
    for tid in ids:
        resultado.extend(validar_tour_asignado(tid))
    # Se revisa al final, una sola vez para toda la base: es una comparación de fechas
    # por reserva, no por tour, así que no tiene sentido repetirla en cada vuelta.
    resultado.extend(validar_tours_fuera_de_la_estadia())
    vistos = set()
    resultado_unico = []
    for msg in resultado:
        if msg not in vistos:
            vistos.add(msg)
            resultado_unico.append(msg)
    return resultado_unico


if __name__ == "__main__":
    conn = get_connection()
    conn.execute("DELETE FROM alerta")
    conn.commit()
    conn.close()
    alertas = validar_todos_los_tours()
    print(f"{len(alertas)} alertas generadas:")
    for a in alertas:
        print(" -", a)


# ---------------------------------------------------------------------------
# Conflictos de asignación: el mismo guía o bote en dos salidas que se solapan
# ---------------------------------------------------------------------------

def _a_minutos(hora):
    """'07:15' -> 435 minutos. Devuelve None si no hay hora definida."""
    if not hora:
        return None
    try:
        h, m = str(hora).strip().split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _se_solapan(inicio_a, fin_a, inicio_b, fin_b):
    """Dos tours se solapan si comparten cualquier momento. Si a alguno le falta
    horario definido, se asume que sí podrían coincidir (mejor avisar que callar)."""
    ia, fa = _a_minutos(inicio_a), _a_minutos(fin_a)
    ib, fb = _a_minutos(inicio_b), _a_minutos(fin_b)
    if ia is None or ib is None:
        return True
    fa = fa if fa is not None else ia + 60
    fb = fb if fb is not None else ib + 60
    return ia < fb and ib < fa


def detectar_conflictos_asignacion(fecha=None):
    """Busca guías o botes asignados a dos salidas distintas que coinciden en horario
    el mismo día. Es el error típico cuando la asignación se hace a mano y contra el
    reloj el día anterior a la operación."""
    conn = get_connection()
    filtro = "WHERE ta.fecha = ?" if fecha else ""
    params = (fecha,) if fecha else ()
    filas = [dict(r) for r in conn.execute(
        f"""SELECT ta.id, ta.fecha, ta.tour_codigo, ta.guia_nombre, ta.bote_nombre,
                   ta.grupo_operativo, ta.pax, ta.es_privado, ta.conf_no,
                   tc.horario_inicio, tc.horario_fin,
                   r.room_no, r.nombre_principal
            FROM tour_asignado ta
            JOIN reserva r ON r.conf_no = ta.conf_no
            LEFT JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
            {filtro}
            {'AND' if filtro else 'WHERE'} r.res_status != 'CANCELADA'
            ORDER BY ta.fecha, tc.horario_inicio""", params).fetchall()]
    conn.close()

    # Cada salida es una combinación de fecha + tour + modalidad + grupo operativo: varias
    # reservas en la misma salida no son conflicto, van juntas con el mismo guía.
    #
    # La MODALIDAD cuenta en la llave. Sin ella, el PNC privado y el PNC compartido del
    # mismo día caían en la misma casilla y el segundo pisaba al primero: dos salidas
    # distintas con el MISMO guía a la misma hora —que es el error que esta función
    # existe para encontrar— se leían como una sola y no se avisaba de nada.
    salidas = {}
    for f in filas:
        priv = 1 if f["es_privado"] else 0
        # Una salida privada es POR RESERVA: va sola, por definición. Dos privadas del
        # mismo día con el mismo guía son un choque de verdad y hay que avisarlo.
        clave = (f["fecha"], f["tour_codigo"], priv, f["grupo_operativo"],
                 f["conf_no"] if priv else "")
        if clave not in salidas:
            salidas[clave] = {**f, "reservas": [], "pax_total": 0}
        salidas[clave]["reservas"].append(f"{f['room_no']} {f['nombre_principal']}")
        salidas[clave]["pax_total"] += f["pax"] or 0

    conflictos = []
    lista = list(salidas.values())
    for i in range(len(lista)):
        for j in range(i + 1, len(lista)):
            a, b = lista[i], lista[j]
            if a["fecha"] != b["fecha"]:
                continue
            if not _se_solapan(a["horario_inicio"], a["horario_fin"],
                               b["horario_inicio"], b["horario_fin"]):
                continue
            for campo, etiqueta in (("guia_nombre", "guía"), ("bote_nombre", "bote")):
                valor = a.get(campo)
                # "EXTERNO" y los botes no gestionados pueden repetirse legítimamente
                if not valor or valor != b.get(campo) or valor.upper() in ("EXTERNO", "PRIVADO"):
                    continue
                # El aviso tiene que decir CUÁL de las dos es la privada: sin eso, un
                # choque entre el PNC privado y el PNC compartido se lee como «PNC y PNC»
                # y parece un error del sistema en vez de dos salidas de verdad.
                def como_se_llama(x):
                    priv = " privado" if x["es_privado"] else ""
                    gr = "" if x["grupo_operativo"] == "A" else f" grupo {x['grupo_operativo']}"
                    return f"{x['tour_codigo']}{priv}{gr}"

                conflictos.append({
                    "fecha": a["fecha"],
                    "tipo": etiqueta,
                    "nombre": valor,
                    "salida_a": como_se_llama(a),
                    "horario_a": f"{a['horario_inicio'] or '?'}–{a['horario_fin'] or '?'}",
                    "salida_b": como_se_llama(b),
                    "horario_b": f"{b['horario_inicio'] or '?'}–{b['horario_fin'] or '?'}",
                    "mensaje": (f"El {etiqueta} {valor} está asignado a dos salidas que coinciden "
                                f"el {a['fecha']}: {como_se_llama(a)} ({a['horario_inicio'] or '?'}) "
                                f"y {como_se_llama(b)} ({b['horario_inicio'] or '?'})."),
                })
    return conflictos


def guias_ocupados(fecha, hora_inicio, hora_fin, excluir_id=None):
    """Devuelve los guías (y botes) que ya están comprometidos en ese horario, para
    poder mostrar quién está libre al momento de asignar."""
    conn = get_connection()
    filas = [dict(r) for r in conn.execute(
        """SELECT DISTINCT ta.id, ta.tour_codigo, ta.guia_nombre, ta.bote_nombre,
                  tc.horario_inicio, tc.horario_fin
           FROM tour_asignado ta LEFT JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
           WHERE ta.fecha = ?""", (fecha,)).fetchall()]
    conn.close()
    guias, botes = set(), set()
    for f in filas:
        if excluir_id and f["id"] == excluir_id:
            continue
        if not _se_solapan(hora_inicio, hora_fin, f["horario_inicio"], f["horario_fin"]):
            continue
        if f["guia_nombre"] and f["guia_nombre"].upper() != "EXTERNO":
            guias.add(f["guia_nombre"])
        if f["bote_nombre"] and f["bote_nombre"].upper() not in ("PRIVADO", "EXTERNO"):
            botes.add(f["bote_nombre"])
    return {"guias_ocupados": sorted(guias), "botes_ocupados": sorted(botes)}
