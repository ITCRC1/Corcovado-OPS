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

    # Capacidad de GUÍA: se valida por grupo operativo, porque cada grupo tiene su
    # propio guía (aunque compartan bote).
    pax_grupo = conn.execute(
        """SELECT COALESCE(SUM(pax),0) total FROM tour_asignado
           WHERE tour_codigo=? AND fecha=? AND grupo_operativo=?""",
        (ta["tour_codigo"], ta["fecha"], ta["grupo_operativo"]),
    ).fetchone()["total"]

    # Capacidad de BOTE: se valida sumando TODOS los grupos que van en ese mismo bote,
    # ya que dos grupos con guías distintos pueden viajar juntos en un solo bote.
    pax_bote = conn.execute(
        """SELECT COALESCE(SUM(pax),0) total FROM tour_asignado
           WHERE tour_codigo=? AND fecha=? AND bote_nombre IS ?""",
        (ta["tour_codigo"], ta["fecha"], ta["bote_nombre"]),
    ).fetchone()["total"]

    grupo_txt = f" (grupo {ta['grupo_operativo']})" if ta["grupo_operativo"] != "A" else ""

    if ta["bote_nombre"]:
        bote = conn.execute(
            "SELECT * FROM bote WHERE nombre = ?", (ta["bote_nombre"],)
        ).fetchone()
        if bote and bote["capacidad_max"] and pax_bote > bote["capacidad_max"]:
            sugerido = sugerir_bote_alterno(conn, ta["tour_codigo"], ta["fecha"], pax_bote, ta["bote_nombre"])
            grupos_en_bote = conn.execute(
                """SELECT COUNT(DISTINCT grupo_operativo) c FROM tour_asignado
                   WHERE tour_codigo=? AND fecha=? AND bote_nombre IS ?""",
                (ta["tour_codigo"], ta["fecha"], ta["bote_nombre"]),
            ).fetchone()["c"]
            compartido = f" (compartido por {grupos_en_bote} grupos)" if grupos_en_bote > 1 else ""
            msg = (
                f"Bote {ta['bote_nombre']} (máx. {bote['capacidad_max']} pax) recibe {pax_bote} pax "
                f"en {ta['tour_codigo']} el {ta['fecha']}{compartido}."
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
            f"{ta['tour_codigo']} el {ta['fecha']}{grupo_txt} tiene {pax_grupo} pax, "
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
                   ta.grupo_operativo, ta.pax, tc.horario_inicio, tc.horario_fin,
                   r.room_no, r.nombre_principal
            FROM tour_asignado ta
            JOIN reserva r ON r.conf_no = ta.conf_no
            LEFT JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
            {filtro}
            ORDER BY ta.fecha, tc.horario_inicio""", params).fetchall()]
    conn.close()

    # Cada salida es una combinación de fecha + tour + grupo operativo: varias reservas
    # en la misma salida no son conflicto, van juntas con el mismo guía.
    salidas = {}
    for f in filas:
        clave = (f["fecha"], f["tour_codigo"], f["grupo_operativo"])
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
                conflictos.append({
                    "fecha": a["fecha"],
                    "tipo": etiqueta,
                    "nombre": valor,
                    "salida_a": f"{a['tour_codigo']}{'' if a['grupo_operativo']=='A' else ' grupo '+a['grupo_operativo']}",
                    "horario_a": f"{a['horario_inicio'] or '?'}–{a['horario_fin'] or '?'}",
                    "salida_b": f"{b['tour_codigo']}{'' if b['grupo_operativo']=='A' else ' grupo '+b['grupo_operativo']}",
                    "horario_b": f"{b['horario_inicio'] or '?'}–{b['horario_fin'] or '?'}",
                    "mensaje": (f"El {etiqueta} {valor} está asignado a dos salidas que coinciden "
                                f"el {a['fecha']}: {a['tour_codigo']} ({a['horario_inicio'] or '?'}) "
                                f"y {b['tour_codigo']} ({b['horario_inicio'] or '?'})."),
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
