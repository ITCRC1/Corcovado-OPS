"""
Distribución de huéspedes entre los dos restaurantes del lodge.

Reglas de la operación (definidas con el hotel):

  Capacidades      Terra Kitchen   Vitrales
    Cena                30            45      (75 es el techo de la propiedad)
    Almuerzo            35            —

  1. Asignación base
       · Quien entra hoy: almuerza en Vitrales y cena en Terra Kitchen
       · Quien está en casa: almuerza en Terra Kitchen y cena en Vitrales
       · Quien sale hoy no cuenta para ninguna comida (el bote sale de madrugada)

  2. La cena en Terra Kitchen se llena por prioridad
       1º rezagados  — quienes no alcanzaron su cena de bienvenida, empezando por
                       el que se va antes (si no, se irían sin recibirla nunca)
       2º entradas de hoy
       3º en casa     — los que entren por rotación para equilibrar
     Se genera un rezagado tanto por capacidad como por balanceo.

  3. Los grupos y familias no se separan nunca, aunque no quepan.

  4. Balanceo (solo cena): diferencia máxima de 4 pax entre restaurantes.
     Por encima de 64 pax es imposible cumplirlo (Terra Kitchen topa en 30) y el
     sistema lo informa en vez de fallar en silencio.

  5. La cena privada queda fija en Vitrales y cuenta para sus 45 lugares: aunque
     se sirva en la piscina, ocupa servicio.

  6. El cambio manual afecta una sola fecha y una sola reserva, pero sí queda en
     el historial para que la rotación de los días siguientes lo tome en cuenta.

La rotación no alterna de forma rígida: se mide por proporción de cenas en cada
restaurante, así se autocorrige cuando una noche no se pudo cumplir.
"""

import datetime

TERRA = "Terra Kitchen"
VITRALES = "Vitrales"

CAP_CENA_TK = 30
CAP_CENA_VIT = 45
CAP_ALMUERZO_TK = 35
MARGEN_BALANCE = 4

# Por encima de este total es imposible respetar el margen, porque Terra Kitchen
# no puede tomar la mitad: 30 es su tope y (total - 4) / 2 debe caber ahí.
TOTAL_MAX_BALANCEABLE = CAP_CENA_TK * 2 + MARGEN_BALANCE


def _a_fecha(ddmmyy):
    """'13-08-26' -> date(2026, 8, 13)"""
    try:
        d, m, y = ddmmyy.split("-")
        return datetime.date(2000 + int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _iso(f):
    return f.isoformat() if hasattr(f, "isoformat") else str(f)


# ---------------------------------------------------------------------------
# Lectura de los datos que ya tiene el sistema
# ---------------------------------------------------------------------------

def _reservas_del_dia(conn, fecha):
    """Clasifica las reservas de esa fecha en entradas, en casa y salidas.

    Se apoya en los datos que el sistema ya carga del PDF: no hay que llenar
    ninguna hoja aparte.
    """
    filas = [dict(r) for r in conn.execute(
        """SELECT conf_no, room_no, nombre_principal, adl, chl, arr_date, dep_date,
                  grupo_id, block_code, forzar_restaurante
           FROM reserva WHERE res_status != 'CANCELADA'""").fetchall()]

    entradas, en_casa, salidas = [], [], []
    for r in filas:
        llega, sale = _a_fecha(r["arr_date"]), _a_fecha(r["dep_date"])
        if not llega:
            continue
        r["pax"] = (r["adl"] or 0) + (r["chl"] or 0)
        r["noches"] = (sale - llega).days if sale else 1
        # La clave de grupo: el grupo detectado por notas, o el código de bloque
        # del PMS, o la reserva sola si no pertenece a ninguno.
        r["clave_grupo"] = (f"g{r['grupo_id']}" if r["grupo_id"]
                            else (f"b{r['block_code']}" if r["block_code"]
                                  else f"r{r['conf_no']}"))
        if llega == fecha:
            r["tipo"] = "ENTRA"
            r["noche_estadia"] = 1
            r["noches_restantes"] = (sale - fecha).days if sale else 1
            entradas.append(r)
        elif sale and llega < fecha < sale:
            r["tipo"] = "EN_CASA"
            r["noche_estadia"] = (fecha - llega).days + 1
            r["noches_restantes"] = (sale - fecha).days
            en_casa.append(r)
        elif sale == fecha:
            r["tipo"] = "SALE"
            salidas.append(r)
    return entradas, en_casa, salidas


def _historial(conn, hasta_fecha):
    """Cuántas cenas tuvo cada reserva en cada restaurante hasta esa fecha.

    Se lee del histórico congelado, que es la única fuente confiable: recalcular
    el pasado daría resultados distintos si entre medio cambió la ocupación.
    """
    conteo = {}
    for r in conn.execute(
        "SELECT conf_no, cena, era_entrada, fecha FROM restaurante_historico WHERE fecha < ?",
        (_iso(hasta_fecha),),
    ).fetchall():
        d = dict(r)
        c = conteo.setdefault(d["conf_no"], {"tk": 0, "vit": 0, "noches": 0,
                                             "debe_bienvenida": False})
        if d["cena"] == TERRA:
            c["tk"] += 1
        elif d["cena"] == VITRALES:
            c["vit"] += 1
        if d["cena"]:
            c["noches"] += 1
        # Si el día que entró no cenó en Terra Kitchen, quedó debiendo su
        # cena de bienvenida, sin importar si fue por capacidad o por balanceo.
        if d["era_entrada"] and d["cena"] and d["cena"] != TERRA:
            c["debe_bienvenida"] = True
    return conteo


def _cambios_manuales(conn, fecha):
    return {(dict(r)["conf_no"], dict(r)["comida"]): dict(r)
            for r in conn.execute(
                "SELECT conf_no, comida, restaurante, motivo FROM restaurante_cambio WHERE fecha = ?",
                (_iso(fecha),)).fetchall()}


def _filtro_privada(prefijo=""):
    """Cómo se reconoce una cena privada entre las amenidades.

    En un solo lugar porque se consulta desde varios sitios y tiene que coincidir
    siempre: si aquí se reconoce y allá no, la mesa se cuenta mal.
    """
    p = f"{prefijo}." if prefijo else ""
    return (f"({p}amenidad LIKE '%privada%' OR {p}tarea LIKE '%privada%' "
            f"OR {p}amenidad LIKE '%private%dinner%')")


def _cenas_privadas(conn, fecha):
    """Reservas con cena privada declarada esa noche. Van fijas a Vitrales."""
    return {dict(r)["conf_no"] for r in conn.execute(
        f"""SELECT conf_no FROM amenidad_tarea
            WHERE fecha = ? AND {_filtro_privada()}""",
        (_iso(fecha),)).fetchall()}


def _privadas_sin_noche(conn, conf_nos):
    """Cenas privadas contratadas a las que todavía nadie les puso noche.

    El PDF avisa que el huésped la tiene contratada, pero casi nunca dice el día, así
    que la amenidad entra sin fecha. Y mientras no tenga fecha no entra en el reparto:
    Vitrales no le guarda la mesa, no cuenta para sus 45 lugares y cocina no la ve
    venir. Antes eso no se mostraba en ninguna parte y la pantalla decía "sin cenas
    privadas esta noche", que es justo lo contrario de lo que pasaba.

    Se devuelven las de los huéspedes que están en casa esa noche, para que la pantalla
    las reclame mientras el huésped todavía está en el lodge.
    """
    if not conf_nos:
        return []
    marcas = ",".join("?" * len(conf_nos))
    filas = conn.execute(
        f"""SELECT DISTINCT a.conf_no, r.room_no, r.nombre_principal, a.detalle,
                   r.arr_date, r.dep_date
            FROM amenidad_tarea a JOIN reserva r ON r.conf_no = a.conf_no
            WHERE a.fecha IS NULL AND {_filtro_privada('a')}
              AND a.conf_no IN ({marcas})
            ORDER BY CAST(r.room_no AS INTEGER)""",
        tuple(conf_nos)).fetchall()
    return [dict(f) for f in filas]


# ---------------------------------------------------------------------------
# Cálculo de la distribución
# ---------------------------------------------------------------------------

def _agrupar(reservas):
    """Junta las reservas que no se pueden separar. Cada bloque se mueve completo."""
    bloques = {}
    for r in reservas:
        b = bloques.setdefault(r["clave_grupo"], {"clave": r["clave_grupo"],
                                                  "reservas": [], "pax": 0})
        b["reservas"].append(r)
        b["pax"] += r["pax"]
    return list(bloques.values())


def _pax(bloques):
    return sum(b["pax"] for b in bloques)


def distribuir(conn, fecha):
    """Devuelve la distribución de almuerzo y cena para esa fecha.

    No guarda nada: la asignación se calcula cada vez a partir de las reservas,
    los cambios manuales y el histórico. Solo las excepciones se persisten.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    entradas, en_casa, salidas = _reservas_del_dia(conn, fecha)
    hist = _historial(conn, fecha)
    manuales = _cambios_manuales(conn, fecha)
    privadas = _cenas_privadas(conn, fecha)

    notas = []          # movimientos explicados, para que el salonero tenga el contexto
    avisos = []

    # ---------- CENA ----------
    # Fijos: cena privada, restaurante forzado de la estadía y cambios manuales
    fijos = {}
    for r in entradas + en_casa:
        cn = r["conf_no"]
        if cn in privadas:
            fijos[cn] = (VITRALES, "cena privada")
        elif r.get("forzar_restaurante"):
            fijos[cn] = (r["forzar_restaurante"], "restaurante fijo de la estadía")
        m = manuales.get((cn, "CENA"))
        if m:
            fijos[cn] = (m["restaurante"], m.get("motivo") or "cambio manual")

    libres = [r for r in entradas + en_casa if r["conf_no"] not in fijos]
    tk_fijo = [r for r in entradas + en_casa if fijos.get(r["conf_no"], ("",))[0] == TERRA]
    vit_fijo = [r for r in entradas + en_casa if fijos.get(r["conf_no"], ("",))[0] == VITRALES]

    # Prioridad para Terra Kitchen: rezagados, entradas, en casa por rotación
    def prioridad(r):
        h = hist.get(r["conf_no"], {})
        debe = h.get("debe_bienvenida", False)
        if debe:
            # Entre rezagados, primero el que se va antes
            return (0, r.get("noches_restantes", 99), 0)
        if r["tipo"] == "ENTRA":
            return (1, 0, 0)
        # En casa: primero quien lleva más noches sin cenar en Terra Kitchen y
        # quien tiene menos noches por delante
        tk, noches = h.get("tk", 0), max(h.get("noches", 0), 1)
        proporcion = tk / noches
        return (2, r.get("noches_restantes", 99), proporcion)

    bloques = sorted(_agrupar(libres), key=lambda b: min(prioridad(r) for r in b["reservas"]))

    total_cena = _pax(entradas) + _pax(en_casa)
    objetivo_tk = max(0, min(CAP_CENA_TK, (total_cena + 1) // 2))

    tk, vit = list(tk_fijo), list(vit_fijo)
    pax_tk, pax_vit = _pax(_agrupar(tk_fijo)), _pax(_agrupar(vit_fijo))

    for b in bloques:
        cabe_tk = pax_tk + b["pax"] <= CAP_CENA_TK
        # Se llena Terra Kitchen hasta el objetivo; el resto va a Vitrales
        if cabe_tk and pax_tk < objetivo_tk:
            tk.extend(b["reservas"]); pax_tk += b["pax"]
        else:
            vit.extend(b["reservas"]); pax_vit += b["pax"]
            for r in b["reservas"]:
                if r["tipo"] == "ENTRA":
                    motivo = ("Terra Kitchen al tope" if not cabe_tk
                              else "para equilibrar los restaurantes")
                    notas.append({
                        "room_no": r["room_no"], "nombre": r["nombre_principal"],
                        "pax": r["pax"], "de": TERRA, "a": VITRALES,
                        "motivo": motivo, "rezagado": True,
                    })

    # Los en casa que entraron a Terra Kitchen: se explica por qué
    for r in tk:
        if r["tipo"] == "EN_CASA" and r["conf_no"] not in fijos:
            notas.append({
                "room_no": r["room_no"], "nombre": r["nombre_principal"],
                "pax": r["pax"], "de": VITRALES, "a": TERRA,
                "motivo": "para equilibrar los restaurantes", "rezagado": False,
            })

    diferencia = abs(pax_tk - pax_vit)
    if total_cena > TOTAL_MAX_BALANCEABLE:
        avisos.append(
            f"Noche de {total_cena} pax: no se puede equilibrar porque Terra Kitchen "
            f"topa en {CAP_CENA_TK}. Diferencia inevitable de {diferencia} pax.")
    elif diferencia > MARGEN_BALANCE:
        avisos.append(
            f"La diferencia quedó en {diferencia} pax (margen {MARGEN_BALANCE}). "
            f"Los grupos no se dividen, así que no siempre se puede ajustar más.")
    if pax_vit > CAP_CENA_VIT:
        avisos.append(f"Vitrales queda con {pax_vit} pax y su tope es {CAP_CENA_VIT}.")
    if total_cena > CAP_CENA_TK + CAP_CENA_VIT:
        avisos.append(f"{total_cena} pax superan la capacidad total de la propiedad "
                      f"({CAP_CENA_TK + CAP_CENA_VIT}).")

    # ---------- ALMUERZO ----------
    # Los de tour almuerzan en el hotel al regresar, así que cuentan como en casa.
    alm_tk, alm_vit = [], []
    for r in en_casa:
        m = manuales.get((r["conf_no"], "ALMUERZO"))
        (alm_vit if (m and m["restaurante"] == VITRALES) else alm_tk).append(r)
    for r in entradas:
        m = manuales.get((r["conf_no"], "ALMUERZO"))
        (alm_tk if (m and m["restaurante"] == TERRA) else alm_vit).append(r)

    # Si el almuerzo en Terra Kitchen se pasa del tope, el sobrante va a Vitrales
    # con el mismo criterio de prioridad.
    if _pax(_agrupar(alm_tk)) > CAP_ALMUERZO_TK:
        sobra = _pax(_agrupar(alm_tk)) - CAP_ALMUERZO_TK
        movibles = sorted(_agrupar([r for r in alm_tk if r["tipo"] == "EN_CASA"]),
                          key=lambda b: -b["pax"])
        for b in movibles:
            if sobra <= 0:
                break
            for r in b["reservas"]:
                alm_tk.remove(r); alm_vit.append(r)
            sobra -= b["pax"]
            notas.append({
                "room_no": ", ".join(x["room_no"] or "?" for x in b["reservas"]),
                "nombre": b["reservas"][0]["nombre_principal"],
                "pax": b["pax"], "de": TERRA, "a": VITRALES,
                "motivo": f"almuerzo en Terra Kitchen al tope ({CAP_ALMUERZO_TK})",
                "rezagado": False, "comida": "almuerzo",
            })
        avisos.append(f"El almuerzo en Terra Kitchen superaba el tope de {CAP_ALMUERZO_TK} pax.")

    # Horas de mesa que registró el salonero
    horas = {dict(r)["conf_no"]: dict(r)["hora"] for r in conn.execute(
        "SELECT conf_no, hora FROM restaurante_hora WHERE fecha = ?", (_iso(fecha),))}

    def salida(lista, comida):
        out = []
        for r in sorted(lista, key=lambda x: int(x["room_no"]) if (x["room_no"] or "").isdigit() else 999):
            fijo = fijos.get(r["conf_no"]) if comida == "cena" else None
            out.append({
                "conf_no": r["conf_no"], "room_no": r["room_no"],
                "nombre": r["nombre_principal"], "pax": r["pax"], "tipo": r["tipo"],
                "noche_estadia": r.get("noche_estadia"), "noches": r["noches"],
                "grupo": r["clave_grupo"] if not r["clave_grupo"].startswith("r") else None,
                "hora": horas.get(r["conf_no"]) if comida == "cena" else None,
                "fijo": fijo[1] if fijo else None,
                "manual": (r["conf_no"], comida.upper()) in manuales,
            })
        return out

    return {
        "fecha": _iso(fecha),
        "cena": {
            "terra_kitchen": salida(tk, "cena"), "vitrales": salida(vit, "cena"),
            "pax_tk": pax_tk, "pax_vit": pax_vit, "total": total_cena,
            "cap_tk": CAP_CENA_TK, "cap_vit": CAP_CENA_VIT,
            "diferencia": diferencia, "dentro_margen": diferencia <= MARGEN_BALANCE,
        },
        "almuerzo": {
            "terra_kitchen": salida(alm_tk, "almuerzo"), "vitrales": salida(alm_vit, "almuerzo"),
            "pax_tk": _pax(_agrupar(alm_tk)), "pax_vit": _pax(_agrupar(alm_vit)),
            "total": _pax(_agrupar(alm_tk)) + _pax(_agrupar(alm_vit)),
            "cap_tk": CAP_ALMUERZO_TK,
        },
        "notas": notas,
        "avisos": avisos,
        "salen": [{"room_no": r["room_no"], "nombre": r["nombre_principal"],
                   "pax": r["pax"]} for r in salidas],
        "cenas_privadas": sorted(privadas),
        # Contratadas pero sin noche puesta: no entran en el reparto todavía, y por eso
        # hay que reclamarlas en pantalla mientras el huésped está en casa.
        "cenas_privadas_sin_noche": _privadas_sin_noche(
            conn, [r["conf_no"] for r in entradas + en_casa]),
    }


# ---------------------------------------------------------------------------
# Congelado del pasado y avisos anticipados
# ---------------------------------------------------------------------------

def congelar_dias_pasados(conn, hasta=None):
    """Guarda la asignación de los días que ya terminaron.

    Sin esto, al importar un PDF nuevo el pasado se recalcularía y podría cambiar:
    la rotación quedaría mal y una deuda de cena de bienvenida podría desaparecer
    después de que recepción ya se lo prometió al huésped.
    """
    hoy = hasta or datetime.date.today()
    ultimo = conn.execute("SELECT MAX(fecha) f FROM restaurante_historico").fetchone()["f"]
    if ultimo:
        desde = datetime.date.fromisoformat(ultimo) + datetime.timedelta(days=1)
    else:
        prim = conn.execute(
            "SELECT MIN(arr_date) a FROM reserva WHERE res_status != 'CANCELADA'").fetchone()["a"]
        desde = _a_fecha(prim) if prim else hoy
    if not desde:
        return 0

    guardados = 0
    d = desde
    while d < hoy:
        dist = distribuir(conn, d)
        for lugar, restaurante in ((dist["cena"]["terra_kitchen"], TERRA),
                                   (dist["cena"]["vitrales"], VITRALES)):
            for x in lugar:
                alm = TERRA if any(y["conf_no"] == x["conf_no"]
                                   for y in dist["almuerzo"]["terra_kitchen"]) else VITRALES
                conn.execute(
                    """INSERT INTO restaurante_historico (fecha, conf_no, almuerzo, cena, era_entrada)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(fecha, conf_no) DO UPDATE SET
                         almuerzo=excluded.almuerzo, cena=excluded.cena,
                         era_entrada=excluded.era_entrada""",
                    (_iso(d), x["conf_no"], alm, restaurante, 1 if x["tipo"] == "ENTRA" else 0))
                guardados += 1
        d += datetime.timedelta(days=1)
    conn.commit()
    return guardados


def avisos_anticipados(conn, dias=30, desde=None):
    """Noches futuras que no van a caber o no se van a poder equilibrar.

    Igual que el aviso de entradas al SINAC: mejor saberlo con semanas de
    anticipación que descubrirlo el mismo día.
    """
    inicio = desde or datetime.date.today()
    problemas = []
    for i in range(dias):
        f = inicio + datetime.timedelta(days=i)
        entradas, en_casa, _ = _reservas_del_dia(conn, f)
        total = sum(r["pax"] for r in entradas + en_casa)
        if not total:
            continue
        if total > CAP_CENA_TK + CAP_CENA_VIT:
            problemas.append({"fecha": _iso(f), "total": total, "gravedad": "NO_CABE",
                              "mensaje": f"{total} pax superan la capacidad total "
                                         f"({CAP_CENA_TK + CAP_CENA_VIT}). Hay que abrir otro turno."})
        elif total > TOTAL_MAX_BALANCEABLE:
            problemas.append({"fecha": _iso(f), "total": total, "gravedad": "SIN_BALANCE",
                              "mensaje": f"{total} pax: no se podrá equilibrar, "
                                         f"Terra Kitchen quedará al tope de {CAP_CENA_TK}."})
    return problemas


def resumen_dia(conn, fecha):
    """Totales para la hoja de operación, que es la que consulta cocina."""
    d = distribuir(conn, fecha)
    return {
        "fecha": d["fecha"],
        "almuerzo_tk": d["almuerzo"]["pax_tk"], "almuerzo_vit": d["almuerzo"]["pax_vit"],
        "cena_tk": d["cena"]["pax_tk"], "cena_vit": d["cena"]["pax_vit"],
        "avisos": d["avisos"],
    }
