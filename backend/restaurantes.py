"""
Distribución de huéspedes entre los dos restaurantes del lodge.

Reglas de la operación (definidas con el hotel):

  Capacidades      Terra Kitchen   Bar el Bosque
    Cena                30            45      (75 es el techo de la propiedad)
    Almuerzo            35            —

  1. Asignación base
       · Quien entra hoy: almuerza en Bar el Bosque y cena en Terra Kitchen
       · Quien está en casa: almuerza en Terra Kitchen y cena en Bar el Bosque
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

  5. La cena privada queda fija en Bar el Bosque y cuenta para sus 45 lugares: aunque
     se sirva en la piscina, ocupa servicio.

  6. El cambio manual afecta una sola fecha y una sola reserva, pero sí queda en
     el historial para que la rotación de los días siguientes lo tome en cuenta.

La rotación no alterna de forma rígida: se mide por proporción de cenas en cada
restaurante, así se autocorrige cuando una noche no se pudo cumplir.
"""

import datetime

import grupos

TERRA = "Terra Kitchen"
# Antes se llamaba "Vitrales". El nombre viejo quedó guardado en los cambios manuales,
# en el histórico de rotación y en los restaurantes fijos de estadía, así que init_db
# lo renombra en la base al arrancar (ver _renombrar_bar_el_bosque).
BOSQUE = "Bar el Bosque"
NOMBRE_ANTERIOR_BOSQUE = "Vitrales"

CAP_CENA_TK = 30
CAP_CENA_BOSQUE = 45
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

def _reservas_base(conn, cache=None):
    """Las reservas vivas, ya con su fecha convertida y su clave de grupo calculada.

    Esto es lo que costaba caro: cada día que se quería repartir volvía a leer la tabla
    de reservas COMPLETA y a convertir de texto a fecha las dos fechas de cada una. Mirar
    un mes en la pantalla de régimen eran 30 lecturas de toda la tabla; la página que ve
    el huésped al escanear su QR hacía una por cada noche de su estadía.

    Con `cache` (un diccionario cualquiera que pase el llamante) se lee UNA vez y se
    reutiliza. El alcance lo decide quien llama, a propósito: así nadie se queda con datos
    viejos sin haberlo pedido. Se guardan solo las reservas —nunca el histórico ni los
    cambios manuales— porque congelar_dias_pasados() escribe en el histórico mientras
    recorre los días, y una copia de eso sí quedaría desactualizada.

    Las filas se devuelven como plantillas de solo lectura: quien las use hace su propia
    copia, porque _reservas_del_dia() les agrega campos distintos según el día.
    """
    if cache is not None and "base" in cache:
        return cache["base"]

    base = []
    for fila in conn.execute(
        """SELECT conf_no, room_no, nombre_principal, adl, chl, arr_date, dep_date,
                  grupo_id, block_code, forzar_restaurante, regimen
           FROM reserva WHERE res_status != 'CANCELADA'""").fetchall():
        r = dict(fila)
        llega, sale = _a_fecha(r["arr_date"]), _a_fecha(r["dep_date"])
        if not llega:
            continue          # sin fecha de llegada no se puede ubicar: se descarta
        r["pax"] = (r["adl"] or 0) + (r["chl"] or 0)
        r["noches"] = (sale - llega).days if sale else 1
        # La clave de grupo vive en grupos.py: es la MISMA que usan las pantallas para
        # mostrar que varias habitaciones viajan juntas. Si aquí se separaran de otra
        # forma, el comedor y la pantalla se contradirían.
        r["clave_grupo"] = grupos.clave_de(r)
        base.append((r, llega, sale))

    if cache is not None:
        cache["base"] = base
    return base


def _reservas_del_dia(conn, fecha, cache=None):
    """Clasifica las reservas de esa fecha en entradas, en casa y salidas.

    Se apoya en los datos que el sistema ya carga del PDF: no hay que llenar
    ninguna hoja aparte.
    """
    entradas, en_casa, salidas = [], [], []
    for plantilla, llega, sale in _reservas_base(conn, cache):
        # Solo se copia lo que este día usa. Los campos que se agregan abajo dependen de
        # la fecha, así que cada día necesita su propia copia y no se puede tocar la
        # plantilla compartida.
        if llega == fecha:
            r = dict(plantilla)
            r["tipo"] = "ENTRA"
            r["noche_estadia"] = 1
            r["noches_restantes"] = (sale - fecha).days if sale else 1
            entradas.append(r)
        elif sale and llega < fecha < sale:
            r = dict(plantilla)
            r["tipo"] = "EN_CASA"
            r["noche_estadia"] = (fecha - llega).days + 1
            r["noches_restantes"] = (sale - fecha).days
            en_casa.append(r)
        elif sale == fecha:
            r = dict(plantilla)
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
        c = conteo.setdefault(d["conf_no"], {"tk": 0, "bosque": 0, "noches": 0,
                                             "debe_bienvenida": False})
        if d["cena"] == TERRA:
            c["tk"] += 1
        elif d["cena"] == BOSQUE:
            c["bosque"] += 1
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


# ---------------------------------------------------------------------------
# Régimen de comidas, para el salonero
# ---------------------------------------------------------------------------

TEXTO_REGIMEN = {
    "PENSION_COMPLETA":     "comidas incluidas",
    "DESAYUNO_CENA":        "solo desayuno y cena",
    "SOLO_DESAYUNO":        "solo desayuno",
    "COMEDOR_TRABAJADORES": "come en el comedor de trabajadores",
}


def texto_regimen(regimen):
    """Cómo se le dice al salonero. Sin dato se deja vacío: no es lo mismo que no tener."""
    return TEXTO_REGIMEN.get(regimen or "", "")


def incluye_comida(regimen, comida):
    """Si esta comida en concreto le corresponde al huésped.

    Devuelve None cuando el PDF no dijo el régimen, que no es lo mismo que un "no":
    es "no se sabe", y en pantalla se muestra distinto para que nadie le niegue el
    almuerzo a alguien por un dato que el reporte no traía.
    """
    from importer import COMIDAS_DE_REGIMEN
    if not regimen or regimen not in COMIDAS_DE_REGIMEN:
        return None
    clave = "almuerzo" if comida == "almuerzo" else "cena"
    return COMIDAS_DE_REGIMEN[regimen][clave]


def _filtro_privada(prefijo=""):
    """Cómo se reconoce una cena privada entre las amenidades.

    En un solo lugar porque se consulta desde varios sitios y tiene que coincidir
    siempre: si aquí se reconoce y allá no, la mesa se cuenta mal.
    """
    p = f"{prefijo}." if prefijo else ""
    return (f"({p}amenidad LIKE '%privada%' OR {p}tarea LIKE '%privada%' "
            f"OR {p}amenidad LIKE '%private%dinner%')")


def es_cena_privada(amenidad, tarea=None):
    """La MISMA regla que _filtro_privada, pero en Python.

    Hace falta porque al importar el PDF hay que decidir en Python si una amenidad es
    cena privada, y ahí no se puede usar SQL. Las dos versiones tienen que decir lo
    mismo: si esta reconociera algo que la de SQL no —o al revés—, una cena privada
    quedaría fechada sola sin aparecer en el comedor, o al contrario.

    Por eso están pegadas una a la otra: quien cambie una ve la otra.
    """
    a = (amenidad or "").lower()
    t = (tarea or "").lower()
    if "privada" in a or "privada" in t:
        return True
    # 'private dinner', 'private  dinner', 'private in-villa dinner'...
    if "private" in a and "dinner" in a and a.index("private") < a.index("dinner"):
        return True
    return False


# Palabras por las que se reconoce una restricción alimentaria.
#
# La lista es GENEROSA a propósito, y esa es la decisión importante: una alergia que no
# se muestra puede mandar a alguien al hospital; una fila de más solo estorba un poco.
# Ante la duda, se muestra.
#
# Van en español y en inglés porque el reporte del PMS llega en inglés y recepción
# escribe en español, así que las dos formas conviven en la misma tabla.
PALABRAS_RESTRICCION = (
    "alergi", "alérgi", "alerg", "allerg",
    "restricc", "restrict", "dietary", "diet",
    "intoleran", "celia", "celíac", "gluten",
    "vegan", "vegetarian", "vegetarian",
    "lactosa", "lactose", "marisco", "shellfish", "nuez", "nuts", "maní", "peanut",
    "kosher", "halal", "sin azúcar", "sugar free", "diabet",
)


def es_restriccion_alimentaria(amenidad, tarea=None, detalle=None):
    """Si esta amenidad es algo que la cocina TIENE que saber antes de servir.

    Mira el nombre, la tarea y el detalle: recepción a veces escribe la amenidad como
    "Preferencia del huésped" y pone "alérgico a mariscos" en el detalle, y esa también
    tiene que aparecer.

    La cena privada queda fuera aunque sea de cocina: tiene su propio sitio en la
    pantalla y mezclarlas escondería lo que aquí importa.
    """
    if es_cena_privada(amenidad, tarea):
        return False
    texto = " ".join(str(x or "") for x in (amenidad, tarea, detalle)).lower()
    return any(p in texto for p in PALABRAS_RESTRICCION)


def restricciones_del_dia(conn, fecha, distribucion=None, cache=None):
    """Las restricciones alimentarias de todo el que come ese día.

    NO se filtra por la fecha de la amenidad, y es deliberado: una alergia no es de un
    día, es de toda la estadía. Filtrarla por fecha la mostraría solo el día que el
    huésped llega, que es justo cuando menos falta hace — lo que la cocina necesita es
    saberla cada noche que esa persona se sienta a comer.

    Quien sale ese día no aparece: el bote se va de madrugada y no desayuna aquí. Es el
    mismo criterio que usa el reparto de mesas.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    if distribucion is None:
        entradas, en_casa, _ = _reservas_del_dia(conn, fecha, cache)
        comen = entradas + en_casa
    else:
        # Se reutiliza lo que ya calculó distribuir(), para no releer las reservas.
        comen = distribucion
    por_conf = {r["conf_no"]: r for r in comen}
    if not por_conf:
        return []

    salida = []
    for i in range(0, len(por_conf), 400):
        lote = list(por_conf)[i:i + 400]
        marcas = ",".join("?" * len(lote))
        for f in conn.execute(
            f"""SELECT a.id, a.conf_no, a.amenidad, a.tarea, a.detalle, a.estado,
                       a.area_responsable
                FROM amenidad_tarea a
                WHERE a.conf_no IN ({marcas}) ORDER BY a.id""", lote).fetchall():
            d = dict(f)
            if not es_restriccion_alimentaria(d["amenidad"], d["tarea"], d["detalle"]):
                continue
            r = por_conf[d["conf_no"]]
            salida.append({
                "conf_no": d["conf_no"],
                "room_no": r.get("room_no"),
                # Los dos nombres del campo conviven: las filas crudas de
                # _reservas_del_dia() traen 'nombre_principal', y las que ya pasaron por
                # distribuir() traen 'nombre'. Esta función se llama con las dos.
                "nombre": r.get("nombre_principal") or r.get("nombre"),
                "pax": r.get("pax"),
                "amenidad": d["amenidad"],
                "detalle": d["detalle"],
                "tarea": d["tarea"],
                "estado": d["estado"],
                "tipo": r.get("tipo"),
            })
    salida.sort(key=lambda x: int(x["room_no"]) if (x["room_no"] or "").isdigit() else 999)
    return salida


def _cenas_privadas(conn, fecha):
    """Reservas con cena privada declarada esa noche. Van fijas a Bar el Bosque."""
    return {dict(r)["conf_no"] for r in conn.execute(
        f"""SELECT conf_no FROM amenidad_tarea
            WHERE fecha = ? AND {_filtro_privada()}""",
        (_iso(fecha),)).fetchall()}


def _privadas_sin_noche(conn, conf_nos):
    """Cenas privadas contratadas a las que todavía nadie les puso noche.

    El PDF avisa que el huésped la tiene contratada, pero casi nunca dice el día, así
    que la amenidad entra sin fecha. Y mientras no tenga fecha no entra en el reparto:
    Bar el Bosque no le guarda la mesa, no cuenta para sus 45 lugares y cocina no la ve
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


def companeros_de_mesa(conn, fecha, conf_no):
    """Las otras reservas que esa noche se sientan con esta por ser del mismo grupo.

    El reparto nunca separa a un grupo ni a una familia (ver _agrupar): las ocho
    habitaciones de una agencia caen siempre en el mismo restaurante. Si comparten
    mesa, comparten hora, así que el salonero pone la hora una vez y le sirve para
    todas. Se usa la MISMA clave de grupo que el reparto, para que no pueda pasar que
    la hora se copie a un conjunto de habitaciones distinto del que se sienta junto.

    Solo se devuelve a quien cena esa noche: un compañero de grupo que salió en la
    mañana no tiene mesa que reservar, y el que llega mañana tampoco.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    entradas, en_casa, _ = _reservas_del_dia(conn, fecha)
    cenan = entradas + en_casa
    yo = next((r for r in cenan if r["conf_no"] == conf_no), None)
    # Clave que empieza con 'r' = la reserva va sola, no hay grupo que sincronizar.
    if not yo or yo["clave_grupo"].startswith("r"):
        return []
    return [{"conf_no": r["conf_no"], "room_no": r["room_no"],
             "nombre": r["nombre_principal"]}
            for r in cenan
            if r["clave_grupo"] == yo["clave_grupo"] and r["conf_no"] != conf_no]


def distribuir(conn, fecha, cache=None):
    """Devuelve la distribución de almuerzo y cena para esa fecha.

    No guarda nada: la asignación se calcula cada vez a partir de las reservas,
    los cambios manuales y el histórico. Solo las excepciones se persisten.

    `cache` es opcional y solo evita releer la tabla de reservas cuando se piden varios
    días seguidos (ver _reservas_base). No cambia el resultado de ningún día.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    entradas, en_casa, salidas = _reservas_del_dia(conn, fecha, cache)
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
            fijos[cn] = (BOSQUE, "cena privada")
        elif r.get("forzar_restaurante"):
            fijos[cn] = (r["forzar_restaurante"], "restaurante fijo de la estadía")
        m = manuales.get((cn, "CENA"))
        if m:
            fijos[cn] = (m["restaurante"], m.get("motivo") or "cambio manual")

    libres = [r for r in entradas + en_casa if r["conf_no"] not in fijos]
    tk_fijo = [r for r in entradas + en_casa if fijos.get(r["conf_no"], ("",))[0] == TERRA]
    bosque_fijo = [r for r in entradas + en_casa if fijos.get(r["conf_no"], ("",))[0] == BOSQUE]

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

    tk, bosque = list(tk_fijo), list(bosque_fijo)
    pax_tk, pax_bosque = _pax(_agrupar(tk_fijo)), _pax(_agrupar(bosque_fijo))

    for b in bloques:
        cabe_tk = pax_tk + b["pax"] <= CAP_CENA_TK
        # Se llena Terra Kitchen hasta el objetivo; el resto va a Bar el Bosque
        if cabe_tk and pax_tk < objetivo_tk:
            tk.extend(b["reservas"]); pax_tk += b["pax"]
        else:
            bosque.extend(b["reservas"]); pax_bosque += b["pax"]
            for r in b["reservas"]:
                if r["tipo"] == "ENTRA":
                    motivo = ("Terra Kitchen al tope" if not cabe_tk
                              else "para equilibrar los restaurantes")
                    notas.append({
                        "room_no": r["room_no"], "nombre": r["nombre_principal"],
                        "pax": r["pax"], "de": TERRA, "a": BOSQUE,
                        "motivo": motivo, "rezagado": True,
                    })

    # Los en casa que entraron a Terra Kitchen: se explica por qué
    for r in tk:
        if r["tipo"] == "EN_CASA" and r["conf_no"] not in fijos:
            notas.append({
                "room_no": r["room_no"], "nombre": r["nombre_principal"],
                "pax": r["pax"], "de": BOSQUE, "a": TERRA,
                "motivo": "para equilibrar los restaurantes", "rezagado": False,
            })

    diferencia = abs(pax_tk - pax_bosque)
    if total_cena > TOTAL_MAX_BALANCEABLE:
        avisos.append(
            f"Noche de {total_cena} pax: no se puede equilibrar porque Terra Kitchen "
            f"topa en {CAP_CENA_TK}. Diferencia inevitable de {diferencia} pax.")
    elif diferencia > MARGEN_BALANCE:
        avisos.append(
            f"La diferencia quedó en {diferencia} pax (margen {MARGEN_BALANCE}). "
            f"Los grupos no se dividen, así que no siempre se puede ajustar más.")
    if pax_bosque > CAP_CENA_BOSQUE:
        avisos.append(f"Bar el Bosque queda con {pax_bosque} pax y su tope es {CAP_CENA_BOSQUE}.")
    if total_cena > CAP_CENA_TK + CAP_CENA_BOSQUE:
        avisos.append(f"{total_cena} pax superan la capacidad total de la propiedad "
                      f"({CAP_CENA_TK + CAP_CENA_BOSQUE}).")

    # ---------- ALMUERZO ----------
    # Los de tour almuerzan en el hotel al regresar, así que cuentan como en casa.
    alm_tk, alm_bosque = [], []
    for r in en_casa:
        m = manuales.get((r["conf_no"], "ALMUERZO"))
        (alm_bosque if (m and m["restaurante"] == BOSQUE) else alm_tk).append(r)
    for r in entradas:
        m = manuales.get((r["conf_no"], "ALMUERZO"))
        (alm_tk if (m and m["restaurante"] == TERRA) else alm_bosque).append(r)

    # Si el almuerzo en Terra Kitchen se pasa del tope, el sobrante va a Bar el Bosque
    # con el mismo criterio de prioridad.
    if _pax(_agrupar(alm_tk)) > CAP_ALMUERZO_TK:
        sobra = _pax(_agrupar(alm_tk)) - CAP_ALMUERZO_TK
        movibles = sorted(_agrupar([r for r in alm_tk if r["tipo"] == "EN_CASA"]),
                          key=lambda b: -b["pax"])
        for b in movibles:
            if sobra <= 0:
                break
            for r in b["reservas"]:
                alm_tk.remove(r); alm_bosque.append(r)
            sobra -= b["pax"]
            notas.append({
                "room_no": ", ".join(x["room_no"] or "?" for x in b["reservas"]),
                "nombre": b["reservas"][0]["nombre_principal"],
                "pax": b["pax"], "de": TERRA, "a": BOSQUE,
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
                # Para el salonero: qué trae pagado y si ESTA comida le corresponde.
                "regimen": r.get("regimen"),
                "regimen_texto": texto_regimen(r.get("regimen")),
                "incluye_esta_comida": incluye_comida(r.get("regimen"), comida),
            })
        return out

    return {
        "fecha": _iso(fecha),
        "cena": {
            "terra_kitchen": salida(tk, "cena"), "bar_el_bosque": salida(bosque, "cena"),
            "pax_tk": pax_tk, "pax_bosque": pax_bosque, "total": total_cena,
            "cap_tk": CAP_CENA_TK, "cap_bosque": CAP_CENA_BOSQUE,
            "diferencia": diferencia, "dentro_margen": diferencia <= MARGEN_BALANCE,
        },
        "almuerzo": {
            "terra_kitchen": salida(alm_tk, "almuerzo"), "bar_el_bosque": salida(alm_bosque, "almuerzo"),
            "pax_tk": _pax(_agrupar(alm_tk)), "pax_bosque": _pax(_agrupar(alm_bosque)),
            "total": _pax(_agrupar(alm_tk)) + _pax(_agrupar(alm_bosque)),
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
    # Una sola lectura de reservas para todos los días que falten congelar. El histórico
    # NO se guarda en caché: es justo lo que este bucle va escribiendo, y cada día tiene
    # que ver lo que dejó el anterior.
    cache = {}
    while d < hoy:
        dist = distribuir(conn, d, cache)
        for lugar, restaurante in ((dist["cena"]["terra_kitchen"], TERRA),
                                   (dist["cena"]["bar_el_bosque"], BOSQUE)):
            for x in lugar:
                alm = TERRA if any(y["conf_no"] == x["conf_no"]
                                   for y in dist["almuerzo"]["terra_kitchen"]) else BOSQUE
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
    cache = {}          # una lectura de reservas para los 30 días, no 30 lecturas
    for i in range(dias):
        f = inicio + datetime.timedelta(days=i)
        entradas, en_casa, _ = _reservas_del_dia(conn, f, cache)
        total = sum(r["pax"] for r in entradas + en_casa)
        if not total:
            continue
        if total > CAP_CENA_TK + CAP_CENA_BOSQUE:
            problemas.append({"fecha": _iso(f), "total": total, "gravedad": "NO_CABE",
                              "mensaje": f"{total} pax superan la capacidad total "
                                         f"({CAP_CENA_TK + CAP_CENA_BOSQUE}). Hay que abrir otro turno."})
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
        "almuerzo_tk": d["almuerzo"]["pax_tk"], "almuerzo_bosque": d["almuerzo"]["pax_bosque"],
        "cena_tk": d["cena"]["pax_tk"], "cena_bosque": d["cena"]["pax_bosque"],
        "avisos": d["avisos"],
    }
