"""Sospechas de que varias habitaciones son familia o vienen juntas.

El sistema une habitaciones solo cuando el dato lo pone el PMS: el código de bloque de
una agencia. Todo lo demás —una nota escrita a mano en el reporte, un apellido que se
repite— no agrupa solo: se PROPONE y recepción decide.

La razón no es formal. Unir dos reservas por error no es un detalle de pantalla: esas
habitaciones quedan sentadas juntas en el comedor, comparten la hora de cena y se
cuentan juntas en la entrada del SINAC. Dos familias Rodríguez que llegaron el mismo
día terminarían en la misma mesa. Preguntar cuesta un toque; deshacer el enredo, no.

Cada sospecha se guarda con una clave estable —los números de reserva ordenados—, así
la que se descarta no vuelve a preguntarse nunca y la pendiente no se duplica cada vez
que se sube el reporte.
"""
import datetime
import json
import re
import unicodedata

import grupos


# ---------------------------------------------------------------------------
# Utilidades de lectura
# ---------------------------------------------------------------------------

def _fecha(ddmmyy):
    """'13-08-26' -> date(2026, 8, 13). Devuelve None si no se puede leer."""
    try:
        d, m, y = str(ddmmyy).split("-")
        return datetime.date(2000 + int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                   if not unicodedata.combining(c))


# El apellido se lee igual que en el resto del sistema, desde grupos.py.
apellido_de = grupos.apellido_de


def _se_solapan(a, b):
    """Si comparten al menos una noche en el lodge.

    Quien sale el día que el otro entra no coincidió con él: no comparten noche y no
    tienen por qué ser el mismo grupo.
    """
    la, sa = _fecha(a["arr_date"]), _fecha(a["dep_date"])
    lb, sb = _fecha(b["arr_date"]), _fecha(b["dep_date"])
    if not (la and lb):
        return False
    sa = sa or la + datetime.timedelta(days=1)
    sb = sb or lb + datetime.timedelta(days=1)
    return la < sb and lb < sa


def _agencia(reserva):
    return " ".join(_sin_tildes(reserva.get("company_travel_agent") or "").upper().split())


def _notas(reserva):
    return " ".join(x for x in (reserva.get("notas_libres"),
                                reserva.get("notas_operacion")) if x)


def clave_de(conf_nos):
    return "+".join(sorted(conf_nos))


# ---------------------------------------------------------------------------
# Detección
# ---------------------------------------------------------------------------

# El reporte anota el vínculo como 'Viene con rsv 594008465' o 'Viene con la rsv de la
# hab 12'. Se toma el fragmento que sigue a 'viene con' y de ahí se saca la referencia.
_VINCULO = re.compile(r"viene con[^.;\n]{0,120}", re.IGNORECASE)
_NUMERO_RSV = re.compile(r"\d{6,}")
_HABITACION = re.compile(r"\bhab\.?\s*(?:n[°º]\s*)?(\d{1,3})\b", re.IGNORECASE)


def _reservas(conn):
    return [dict(r) for r in conn.execute(
        """SELECT conf_no, room_no, nombre_principal, arr_date, dep_date, adl, chl,
                  grupo_id, block_code, company_travel_agent, notas_libres, notas_operacion
           FROM reserva WHERE res_status != 'CANCELADA'""").fetchall()]


def _propuestas(filas):
    """Los conjuntos sospechosos, sin mirar todavía qué se guardó antes.

    Devuelve una lista de (conf_nos, motivo, detalle, confianza).
    """
    por_conf = {r["conf_no"]: r for r in filas}
    por_hab = {}
    for r in filas:
        por_hab.setdefault((r["room_no"] or "").lstrip("0"), []).append(r)

    salida = []

    for r in filas:
        texto = _notas(r)
        m = _VINCULO.search(texto or "")
        if not m:
            continue
        fragmento = m.group(0).strip()

        # 1) La nota cita un número de reserva: es lo más explícito que puede haber.
        citados = [n for n in _NUMERO_RSV.findall(fragmento)
                   if n != r["conf_no"] and n in por_conf]
        if citados:
            for otro in citados:
                salida.append(([r["conf_no"], otro], "nota_rsv", fragmento, "ALTA"))
            continue

        # 2) La nota cita una habitación. Vale solo si esa habitación está ocupada por
        #    alguien que coincide en fechas: el mismo número se reutiliza todo el año.
        for hab in _HABITACION.findall(fragmento):
            candidatos = [o for o in por_hab.get(hab.lstrip("0"), [])
                          if o["conf_no"] != r["conf_no"] and _se_solapan(r, o)]
            if len(candidatos) == 1:
                salida.append(([r["conf_no"], candidatos[0]["conf_no"]],
                               "nota_hab", fragmento, "ALTA"))

    # 3) Mismo apellido. Por sí solo no dice nada —hay muchos Rodríguez—, así que además
    #    tienen que compartir noches y, encima, llegar el mismo día o venir por la misma
    #    agencia. Sin ese filtro la pantalla se llena de ruido y deja de revisarse.
    por_apellido = {}
    for r in filas:
        ap = apellido_de(r["nombre_principal"])
        if len(ap) >= 3:
            por_apellido.setdefault(ap, []).append(r)

    for ap, miembros in por_apellido.items():
        if len(miembros) < 2:
            continue
        for i, a in enumerate(miembros):
            for b in miembros[i + 1:]:
                if not _se_solapan(a, b):
                    continue
                misma_llegada = a["arr_date"] == b["arr_date"]
                misma_agencia = bool(_agencia(a)) and _agencia(a) == _agencia(b)
                if not (misma_llegada or misma_agencia):
                    continue
                razon = "llegan el mismo día" if misma_llegada else "vienen por la misma agencia"
                salida.append(([a["conf_no"], b["conf_no"]], "apellido",
                               f"Mismo apellido {ap.title()}, {razon}", "MEDIA"))
    return salida


def detectar(conn):
    """Anota las sospechas nuevas. Devuelve cuántas se agregaron.

    No propone nada que ya esté resuelto: ni lo que el sistema ya agrupa, ni lo que
    recepción ya contestó alguna vez.
    """
    filas = _reservas(conn)
    if len(filas) < 2:
        return 0
    por_conf = {r["conf_no"]: r for r in filas}
    conocidas = {r["clave"] for r in conn.execute("SELECT clave FROM sugerencia_grupo")}

    nuevas = 0
    for conf_nos, motivo, detalle, confianza in _propuestas(filas):
        conf_nos = sorted(set(conf_nos))
        if len(conf_nos) < 2 or any(c not in por_conf for c in conf_nos):
            continue
        # Ya viajan juntas (mismo bloque del PMS o grupo ya confirmado): nada que preguntar.
        if len({grupos.clave_de(por_conf[c]) for c in conf_nos}) == 1:
            continue
        clave = clave_de(conf_nos)
        if clave in conocidas:
            continue
        conn.execute(
            """INSERT INTO sugerencia_grupo (clave, conf_nos, motivo, detalle, confianza)
               VALUES (?,?,?,?,?)""",
            (clave, json.dumps(conf_nos), motivo, detalle, confianza))
        conocidas.add(clave)
        nuevas += 1
    return nuevas


# ---------------------------------------------------------------------------
# Lo que ve la pantalla
# ---------------------------------------------------------------------------

TEXTO_MOTIVO = {
    "nota_rsv": "El reporte dice que vienen juntas y cita el número de reserva",
    "nota_hab": "El reporte dice que vienen juntas y cita la habitación",
    "apellido": "Mismo apellido y coinciden las fechas",
    "manual": "Ligadas a mano por recepción",
}


def pendientes(conn):
    """Las sospechas sin contestar, con los datos de cada habitación."""
    filas = {r["conf_no"]: dict(r) for r in conn.execute(
        """SELECT conf_no, room_no, nombre_principal, arr_date, dep_date, adl, chl
           FROM reserva WHERE res_status != 'CANCELADA'""").fetchall()}

    salida = []
    for s in conn.execute(
            "SELECT * FROM sugerencia_grupo WHERE estado = 'PENDIENTE' ORDER BY confianza, id"):
        confs = json.loads(s["conf_nos"])
        # Si alguna reserva se canceló o desapareció, la sospecha ya no tiene sentido.
        if any(c not in filas for c in confs):
            continue
        miembros = [filas[c] for c in confs]
        miembros.sort(key=lambda x: int(x["room_no"]) if (x["room_no"] or "").isdigit() else 999)
        salida.append({
            "id": s["id"],
            "motivo": s["motivo"],
            "motivo_texto": TEXTO_MOTIVO.get(s["motivo"], s["motivo"]),
            "detalle": s["detalle"],
            "confianza": s["confianza"],
            "pax": sum((m["adl"] or 0) + (m["chl"] or 0) for m in miembros),
            "miembros": [{"conf_no": m["conf_no"], "room_no": m["room_no"],
                          "nombre": m["nombre_principal"],
                          "arr_date": m["arr_date"], "dep_date": m["dep_date"],
                          "pax": (m["adl"] or 0) + (m["chl"] or 0)} for m in miembros],
        })
    return salida


# ---------------------------------------------------------------------------
# Decisiones de recepción
# ---------------------------------------------------------------------------

def ligar(conn, conf_nos, motivo="manual", confianza="ALTA"):
    """Une estas reservas en un grupo confirmado y devuelve su id.

    Si alguna ya pertenece a un grupo se usa ESE, y si hay varios se absorben en uno
    solo: de otra forma ligar la 12 con la 14 podría partir en dos un grupo que ya
    existía, y el comedor las sentaría separadas.
    """
    conf_nos = sorted(set(conf_nos))
    marcas = ",".join("?" * len(conf_nos))
    existentes = sorted({r["grupo_id"] for r in conn.execute(
        f"SELECT grupo_id FROM reserva WHERE conf_no IN ({marcas})", conf_nos)
        if r["grupo_id"]})

    if existentes:
        grupo_id = existentes[0]
        for otro in existentes[1:]:
            conn.execute("UPDATE reserva SET grupo_id = ? WHERE grupo_id = ?", (grupo_id, otro))
            conn.execute("DELETE FROM grupo WHERE id = ?", (otro,))
        conn.execute("UPDATE grupo SET confirmado_por_recepcion = 1 WHERE id = ?", (grupo_id,))
    else:
        cur = conn.execute(
            """INSERT INTO grupo (conf_no_principal, origen_vinculo, confianza,
                                  confirmado_por_recepcion)
               VALUES (?,?,?,1)""", (conf_nos[0], motivo, confianza))
        grupo_id = cur.lastrowid

    conn.execute(f"UPDATE reserva SET grupo_id = ? WHERE conf_no IN ({marcas})",
                 [grupo_id] + conf_nos)
    return grupo_id


def confirmar(conn, sugerencia_id, usuario=None):
    """Recepción dice que sí: quedan ligadas con todo lo que eso implica."""
    s = conn.execute("SELECT * FROM sugerencia_grupo WHERE id = ?",
                     (sugerencia_id,)).fetchone()
    if not s or s["estado"] != "PENDIENTE":
        return None
    conf_nos = json.loads(s["conf_nos"])
    grupo_id = ligar(conn, conf_nos, motivo=s["motivo"], confianza=s["confianza"])
    conn.execute(
        """UPDATE sugerencia_grupo SET estado = 'CONFIRMADA', grupo_id = ?,
           resuelto_en = datetime('now'), resuelto_por = ? WHERE id = ?""",
        (grupo_id, usuario, sugerencia_id))
    return grupo_id


def descartar(conn, sugerencia_id, usuario=None):
    """Recepción dice que no. No se vuelve a preguntar."""
    conn.execute(
        """UPDATE sugerencia_grupo SET estado = 'DESCARTADA',
           resuelto_en = datetime('now'), resuelto_por = ? WHERE id = ?""",
        (usuario, sugerencia_id))


def deshacer(conn, grupo_id, usuario=None):
    """Deshace un grupo ligado a mano o confirmado.

    La sospecha que lo originó queda descartada: si alguien lo deshizo es porque estaba
    mal, y volver a proponerlo mañana sería discutirle a quien ya decidió.
    """
    conn.execute(
        """UPDATE sugerencia_grupo SET estado = 'DESCARTADA',
           resuelto_en = datetime('now'), resuelto_por = ? WHERE grupo_id = ?""",
        (usuario, grupo_id))
    conn.execute("UPDATE reserva SET grupo_id = NULL WHERE grupo_id = ?", (grupo_id,))
    conn.execute("DELETE FROM grupo WHERE id = ?", (grupo_id,))
