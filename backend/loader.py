"""Inserta el resultado de importer.build_review_batch() en la base de datos."""
from init_db import get_connection


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


def load_batch(batch, fuente_pdf="Arrivals__Detailed.PDF", marcar_ausentes_como_canceladas=True):
    conn = get_connection()
    cur = conn.cursor()

    grupo_cache = {}
    confs_en_pdf = []
    fechas_en_pdf = set()

    for item in batch["reservas"]:
        r = item["reserva"]
        confs_en_pdf.append(r["conf_no"])
        if r.get("arr_date"):
            fechas_en_pdf.add(r["arr_date"])
        link = r.get("grupo_link")
        grupo_id = None
        if link:
            referencias = link.get("referencias_conf_no") or []
            key = referencias[0] if referencias else r["conf_no"]
            if key not in grupo_cache:
                cur.execute(
                    "INSERT INTO grupo (conf_no_principal, origen_vinculo, confianza, confirmado_por_recepcion) VALUES (?,?,?,0)",
                    (key, "texto_explicito" if link["tipo"] == "ALTA" else "coincidencia_nombre", link["tipo"]),
                )
                grupo_cache[key] = cur.lastrowid
            grupo_id = grupo_cache[key]

        cur.execute(
            """INSERT OR REPLACE INTO reserva
               (conf_no, grupo_id, room_no, nombre_principal, company_travel_agent,
                arr_date, dep_date, arr_time, room_type, adl, chl, rooms, mkt_code,
                src_code, res_status, guia_sugerido, guia_confirmado, punto_entrada,
                punto_salida, punto_entrada_sin_confirmar, punto_salida_sin_confirmar,
                hora_vuelo_entrada, hora_vuelo_salida, vuelo_entrada, vuelo_salida, nota_ingreso,
                nota_en_casa, nota_salida, notas_operacion, notas_libres, fuente_pdf)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
        # actualizaciones diarias), estos registros se vuelven a generar. Se borran
        # los anteriores de esta reserva para que no se acumulen duplicados.
        # IMPORTANTE: antes de borrar los tours, se guardan las asignaciones de guía
        # y bote que recepción ya hizo manualmente, para restaurarlas después y no
        # perder ese trabajo.
        # Asignaciones que recepción ya hizo (guía, bote, grupo operativo). Se guardan
        # por fecha+tour y también agrupadas solo por tour, porque si el PDF actualizado
        # mueve el tour de día la asignación seguía siendo válida y antes se perdía:
        # recepción tenía que volver a asignar todo.
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

        cur.execute("DELETE FROM huesped WHERE conf_no = ?", (r["conf_no"],))
        cur.execute("DELETE FROM tour_asignado WHERE conf_no = ?", (r["conf_no"],))
        # Solo se borran las detectadas del PDF; las agregadas a mano por recepción se conservan.
        cur.execute("DELETE FROM amenidad_tarea WHERE conf_no = ? AND origen = 'PDF'", (r["conf_no"],))

        for amenidad in r.get("amenidades_detectadas", []):
            catalog_row = cur.execute(
                "SELECT nombre, tarea_automatica, area_responsable FROM amenidad_catalogo WHERE nombre = ?",
                (amenidad,),
            ).fetchone()
            if catalog_row:
                cur.execute(
                    "INSERT INTO amenidad_tarea (conf_no, amenidad, tarea, area_responsable) VALUES (?,?,?,?)",
                    (r["conf_no"], catalog_row["nombre"], catalog_row["tarea_automatica"], catalog_row["area_responsable"]),
                )

        for g in r["rooming"]:
            cur.execute(
                "INSERT INTO huesped (conf_no, nombre_completo, pasaporte) VALUES (?,?,?)",
                (r["conf_no"], g["nombre"], g.get("pasaporte")),
            )

        for a in r["agenda"]:
            asignacion = asignaciones_previas.pop((a["fecha"], a["tour"]), None)
            if asignacion is None:
                # No hay coincidencia exacta de fecha: el tour probablemente se movió
                # de día en el PDF actualizado. Se recupera la asignación por tour, en
                # orden, para no obligar a recepción a reasignar guía y bote.
                pendientes_tour = asignaciones_por_tour.get(a["tour"])
                if pendientes_tour:
                    asignacion = pendientes_tour.pop(0)
            guia_prev, bote_prev, grupo_prev = asignacion or (None, None, "A")
            cur.execute(
                """INSERT INTO tour_asignado
                   (conf_no, fecha, tour_codigo, pax, conf_entrada_sinac, guia_nombre, bote_nombre, grupo_operativo)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (r["conf_no"], a["fecha"], a["tour"], r["adl"] + r["chl"],
                 a.get("conf_entrada"), guia_prev, bote_prev, grupo_prev),
            )

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

    for e in batch["entradas_sinac"]:
        cur.execute(
            """INSERT OR REPLACE INTO entrada_sinac
               (tour_codigo, fecha, conf_entrada, pax_total_grupo, estado, nota)
               VALUES (?,?,?,?,?,?)""",
            (
                e["tour"], e["fecha"], e["conf_entrada"], e["pax_total_grupo"], e["estado"],
                "Contradicción detectada en notas — revisar antes de confirmar" if e["estado"] == "VER_NOTA" else None,
            ),
        )

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
