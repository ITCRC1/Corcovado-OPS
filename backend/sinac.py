"""Qué reservas le corresponden a cada entrada del SINAC, en un solo lugar.

Una entrada del SINAC no cubre a "todos los que van a ese tour ese día": cubre a los
que llevan SU MISMO número de confirmación. Un mismo tour y fecha puede tener varias
entradas —una comprada por cada grupo, más una pendiente por los que todavía no la
tienen—, y cada una corresponde a habitaciones distintas.

Esa comparación estaba escrita dos veces, y no decían lo mismo: la pantalla emparejaba
por número de confirmación, y la limpieza de entradas sin dueño lo ignoraba. Por eso
sobrevivían entradas fantasma: cuando se compraba la entrada de un grupo, el reporte
traía la nueva entrada con su número y la vieja "sin comprar" se quedaba para siempre
—la limpieza veía que el tour sí tenía reservas y la dejaba, mientras la pantalla no le
encontraba ninguna y la mostraba en cero, sin habitación, como si faltara comprarla.

Aquí está la única definición, para que las dos usen la misma.
"""

# La ausencia de número se compara como cadena vacía a propósito: en SQLite NULL no es
# igual a NULL, así que 'sin número = sin número' solo funciona normalizando los dos
# lados. Es el mismo motivo por el que el índice único usa IFNULL.
MISMA_ENTRADA = "IFNULL(ta.conf_entrada_sinac,'') = IFNULL(e.conf_entrada,'')"


def reservas_de(conn, tour_codigo, fecha, conf_entrada):
    """Las reservas que cubre esta entrada. Vacío significa que no le corresponde nadie."""
    return [dict(x) for x in conn.execute(
        """SELECT DISTINCT r.conf_no, r.room_no, r.nombre_principal, r.adl, r.chl
           FROM tour_asignado ta JOIN reserva r ON r.conf_no = ta.conf_no
           WHERE ta.tour_codigo = ? AND ta.fecha = ?
             AND IFNULL(ta.conf_entrada_sinac,'') = ?
             AND r.res_status != 'CANCELADA'
           ORDER BY CAST(r.room_no AS INTEGER)""",
        (tour_codigo, fecha, conf_entrada or "")).fetchall()]


NOTA_HUERFANA = ("Comprada pero sin reservas asignadas: el tour cambió de fecha o la "
                 "reserva se canceló. Revisar si la entrada se puede reutilizar.")


def limpiar_huerfanas(conn):
    """Quita las entradas que ya no le corresponden a ninguna reserva.

    Las pendientes de comprar se borran: no hay nada que comprar si no hay nadie
    detrás, y en pantalla aparecían como una fila en cero sin habitación que parecía
    una compra por hacer. Las que ya se pagaron NO se borran —sería tirar plata a la
    basura—: se les deja una nota para que alguien revise si se pueden reutilizar.

    Devuelve (borradas, anotadas).
    """
    # Con la tabla de tours asignados vacía, TODAS parecerían huérfanas. Pasa en una base
    # recién restaurada o antes de la primera importación, y borrarlas ahí sería un
    # destrozo: sin tours cargados no hay con qué comparar, así que no se toca nada.
    if not conn.execute("SELECT 1 FROM tour_asignado LIMIT 1").fetchone():
        return 0, 0

    huerfanas = conn.execute(
        f"""SELECT id, estado, nota FROM entrada_sinac e
            WHERE NOT EXISTS (
              SELECT 1 FROM tour_asignado ta JOIN reserva r ON r.conf_no = ta.conf_no
              WHERE ta.tour_codigo = e.tour_codigo AND ta.fecha = e.fecha
                AND r.res_status != 'CANCELADA' AND {MISMA_ENTRADA})""").fetchall()

    borradas = anotadas = 0
    for h in huerfanas:
        if h["estado"] == "COMPRADA":
            if h["nota"] != NOTA_HUERFANA:
                conn.execute("UPDATE entrada_sinac SET nota = ? WHERE id = ?",
                             (NOTA_HUERFANA, h["id"]))
                anotadas += 1
        else:
            conn.execute("DELETE FROM entrada_sinac WHERE id = ?", (h["id"],))
            borradas += 1
    return borradas, anotadas
