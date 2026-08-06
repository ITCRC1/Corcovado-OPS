from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from init_db import get_connection
import os
import sys
import tempfile
import datetime

sys.path.insert(0, os.path.dirname(__file__))
from importer import build_review_batch
from loader import load_batch as _load_batch
from validations import (validar_todos_los_tours, validar_tour_asignado,
                         detectar_conflictos_asignacion, guias_ocupados)
import auth

app = FastAPI(title="Sistema de Operación Hotelera - Sierpe/Drake")

# El frontend lo sirve este mismo proceso, así que normalmente NO hace falta CORS.
# Antes estaba abierto a cualquier origen ("*"), lo que permitía a cualquier sitio
# web hacer llamadas a la API desde el navegador de un usuario. Si alguna vez se
# sirve el frontend desde otro dominio, se listan aquí separados por coma.
_cors_origins = [o.strip() for o in os.environ.get("HOTEL_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=_cors_origins,
                       allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    respuesta.headers.setdefault("Referrer-Policy", "same-origin")
    return respuesta


# Crear el usuario inicial la primera vez que arranca el sistema
_auth_conn = get_connection()
auth.seed_default_users(_auth_conn)
_auth_conn.close()


def current_user(authorization: str = Header(None)):
    return auth.get_current_user(authorization, get_connection)


@app.get("/api/salud")
def salud():
    """Comprobación para el hosting: responde 200 solo si la base de datos está
    accesible. Railway la usa para decidir si un despliegue quedó sano; si falla,
    mantiene arriba la versión anterior en vez de dejar el sistema caído.
    No expone ningún dato."""
    try:
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return {"estado": "ok"}


def ddmmyy(iso_date):
    y, m, d = iso_date.split("-")
    return f"{d}-{m}-{y[2:]}"


def sql_fecha_py(ddmmyy_str):
    """'05-08-26' -> '2026-08-05', para comparar fechas en Python."""
    try:
        d, m, y = ddmmyy_str.split("-")
        return f"20{y}-{m}-{d}"
    except (ValueError, AttributeError):
        return ""


def sql_fecha(col):
    """Las fechas se guardan como texto 'DD-MM-YY', que al compararse como texto da
    resultados incorrectos cuando el rango cruza de un mes a otro. Esta expresión las
    reordena a 'YY-MM-DD' dentro del SQL, que sí se compara correctamente."""
    return f"(substr({col},7,2)||'-'||substr({col},4,2)||'-'||substr({col},1,2))"


def yymmdd(iso_date):
    """Convierte '2026-08-01' a '26-08-01', el formato que produce sql_fecha()."""
    y, m, d = iso_date.split("-")
    return f"{y[2:]}-{m}-{d}"


def reserva_resumen(row):
    return {
        "conf_no": row["conf_no"], "room_no": row["room_no"], "nombre_principal": row["nombre_principal"],
        "arr_date": row["arr_date"], "dep_date": row["dep_date"],
        "notas_libres": row["notas_libres"], "adl": row["adl"], "chl": row["chl"],
    }


# ---------- AUTENTICACIÓN ----------
@app.post("/api/auth/login")
async def login(payload: dict, request: Request):
    # Freno a la fuerza bruta: varios fallos seguidos desde el mismo origen y para
    # el mismo usuario bloquean el intento durante unos minutos.
    origen = request.client.host if request.client else "?"
    clave_intentos = f"{origen}|{payload.get('username', '')}"
    auth.verificar_intentos(clave_intentos)

    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM usuario WHERE username = ? AND activo = 1", (payload.get("username", ""),)
    ).fetchone()
    if not user or not auth.verify_password(payload.get("password", ""), user["password_hash"], user["salt"]):
        conn.close()
        auth.registrar_fallo(clave_intentos)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    auth.limpiar_intentos(clave_intentos)
    token = auth.crear_sesion(conn, user["id"])
    conn.close()
    return {"token": token, "username": user["username"], "nombre_completo": user["nombre_completo"], "rol": user["rol"]}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@app.post("/api/auth/logout")
def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        conn = get_connection()
        conn.execute("DELETE FROM sesion WHERE token = ?", (authorization.split(" ", 1)[1],))
        conn.commit()
        conn.close()
    return {"status": "ok"}


# ---------- LECTURA (cualquier rol autenticado) ----------
@app.get("/api/dashboard/{fecha}")
def dashboard(fecha: str, user: dict = Depends(current_user)):
    conn = get_connection()
    dd = ddmmyy(fecha)
    yy = yymmdd(fecha)   # formato comparable cronológicamente
    entran = conn.execute("SELECT * FROM reserva WHERE arr_date = ?", (dd,)).fetchall()
    salen = conn.execute("SELECT * FROM reserva WHERE dep_date = ?", (dd,)).fetchall()
    en_casa = conn.execute(
        # Se cuenta por fechas de estadía, no por estado: el PMS marca CKIN solo
        # cuando el huésped ya ingresó, así que exigirlo dejaba en cero cualquier
        # día futuro y volvía inútil la planificación.
        f"""SELECT * FROM reserva WHERE res_status != 'CANCELADA'
             AND {sql_fecha('arr_date')} <= ?
             AND (dep_date IS NULL OR {sql_fecha('dep_date')} >= ?)""",
        (yy, yy),
    ).fetchall()

    tours = conn.execute(
        """SELECT ta.fecha, ta.tour_codigo, ta.grupo_operativo, tc.horario_inicio,
                  tc.horario_fin, tc.requiere_bote, ta.pax, ta.guia_nombre,
                  ta.bote_nombre, r.nombre_principal, r.room_no
           FROM tour_asignado ta
           JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
           JOIN reserva r ON r.conf_no = ta.conf_no
           WHERE ta.fecha = ?
           ORDER BY tc.horario_inicio""",
        (fecha,),
    ).fetchall()

    alertas = conn.execute("SELECT tipo, mensaje FROM alerta WHERE resuelto = 0").fetchall()

    # Resumen de entradas SINAC cuyo plazo de compra (15 días antes) está vencido o
    # por vencer, para avisarlo en el dashboard sin tener que entrar a esa pantalla.
    hoy_d = datetime.date.today()
    pendientes = conn.execute(
        "SELECT fecha, tour_codigo, pax_total_grupo FROM entrada_sinac WHERE estado != 'COMPRADA'"
    ).fetchall()
    sinac_vencidas, sinac_urgentes = [], []
    for p in pendientes:
        try:
            ft = datetime.date.fromisoformat(p["fecha"])
        except (ValueError, TypeError):
            continue
        if ft < hoy_d:
            continue
        dias = (ft - datetime.timedelta(days=15) - hoy_d).days
        item = {"fecha": p["fecha"], "tour": p["tour_codigo"], "pax": p["pax_total_grupo"], "dias": dias}
        if dias < 0:
            sinac_vencidas.append(item)
        elif dias <= 7:
            sinac_urgentes.append(item)

    conn.close()
    return {
        "fecha": fecha,
        "sinac_vencidas": sinac_vencidas,
        "sinac_urgentes": sinac_urgentes,
        "entran_hoy": [reserva_resumen(r) for r in entran],
        "salen_hoy": [reserva_resumen(r) for r in salen],
        "en_casa": [reserva_resumen(r) for r in en_casa],
        "tours": [dict(t) for t in tours],
        "alertas": [dict(a) for a in alertas],
    }


@app.get("/api/resumen-operacion")
def resumen_operacion(fecha: str, user: dict = Depends(current_user)):
    """Resumen del día pensado para que cada departamento encuentre lo suyo:
    recepción, cocina, housekeeping, guías y transporte."""
    conn = get_connection()
    dd = ddmmyy(fecha)
    yy = yymmdd(fecha)

    def lista(sql, params=()):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # --- Movimiento de huéspedes ---
    ingresos = lista(
        """SELECT room_no, nombre_principal, adl, chl, arr_time, punto_entrada,
                  vuelo_entrada, hora_vuelo_entrada, nota_ingreso, notas_libres
           FROM reserva WHERE arr_date = ? AND res_status != 'CANCELADA'
           ORDER BY CAST(room_no AS INTEGER)""", (dd,))
    salidas = lista(
        """SELECT room_no, nombre_principal, adl, chl, punto_salida,
                  vuelo_salida, hora_vuelo_salida, nota_salida
           FROM reserva WHERE dep_date = ? AND res_status != 'CANCELADA'
           ORDER BY CAST(room_no AS INTEGER)""", (dd,))
    desayunos = lista(
        f"""SELECT room_no, nombre_principal, adl, chl FROM reserva
           WHERE res_status != 'CANCELADA' AND (
             dep_date = ? OR ({sql_fecha('arr_date')} < ?
                              AND (dep_date IS NULL OR {sql_fecha('dep_date')} >= ?)))
           ORDER BY CAST(room_no AS INTEGER)""", (dd, yy, yy))
    en_casa = lista(
        f"""SELECT room_no, nombre_principal, adl, chl, punto_salida, dep_date FROM reserva
           WHERE res_status != 'CANCELADA' AND (
             arr_date = ? OR ({sql_fecha('arr_date')} < ?
                              AND (dep_date IS NULL OR {sql_fecha('dep_date')} > ?)))
           ORDER BY CAST(room_no AS INTEGER)""", (dd, yy, yy))

    def pax(l):
        return sum((x["adl"] or 0) + (x["chl"] or 0) for x in l)

    # --- Movimiento por punto de embarque (Sierpe / Drake) ---
    puntos = {}
    for tipo, filas, campo in (("entradas", ingresos, "punto_entrada"),
                               ("salidas", salidas, "punto_salida")):
        for f in filas:
            p = f.get(campo) or "Sin definir"
            k = puntos.setdefault(p, {"punto": p, "entradas": 0, "salidas": 0,
                                      "pax_entradas": 0, "pax_salidas": 0, "detalle": []})
            k[tipo] += 1
            k[f"pax_{tipo}"] += (f["adl"] or 0) + (f["chl"] or 0)
            hora = f.get("hora_vuelo_entrada") or f.get("arr_time") if tipo == "entradas" \
                   else f.get("hora_vuelo_salida")
            vuelo = f.get("vuelo_entrada") if tipo == "entradas" else f.get("vuelo_salida")
            k["detalle"].append({
                "tipo": "Entrada" if tipo == "entradas" else "Salida",
                "room_no": f["room_no"], "nombre": f["nombre_principal"],
                "pax": (f["adl"] or 0) + (f["chl"] or 0),
                "hora": hora, "vuelo": vuelo,
            })

    # --- Tours del día (para guías y operación) ---
    tours = lista(
        """SELECT ta.tour_codigo, ta.grupo_operativo, ta.guia_nombre, ta.bote_nombre,
                  SUM(ta.pax) pax_total, tc.horario_inicio, tc.horario_fin,
                  GROUP_CONCAT(r.room_no) habitaciones
           FROM tour_asignado ta
           JOIN reserva r ON r.conf_no = ta.conf_no
           LEFT JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
           WHERE ta.fecha = ? AND r.res_status != 'CANCELADA'
           GROUP BY ta.tour_codigo, ta.grupo_operativo, ta.guia_nombre, ta.bote_nombre
           ORDER BY tc.horario_inicio""", (fecha,))

    # --- Cocina: restricciones alimentarias de quienes están en el hotel ---
    habitaciones_en_casa = {x["room_no"] for x in en_casa} | {x["room_no"] for x in desayunos}
    restricciones = [x for x in lista(
        """SELECT r.room_no, r.nombre_principal, a.amenidad, a.detalle, a.tarea, a.estado
           FROM amenidad_tarea a JOIN reserva r ON r.conf_no = a.conf_no
           WHERE a.area_responsable = 'Cocina'""")
        if x["room_no"] in habitaciones_en_casa]

    # --- Amenidades a preparar para quienes llegan ese día ---
    habitaciones_ingresan = {x["room_no"] for x in ingresos}
    amenidades = [x for x in lista(
        """SELECT r.room_no, r.nombre_principal, a.amenidad, a.detalle, a.tarea,
                  a.area_responsable, a.estado
           FROM amenidad_tarea a JOIN reserva r ON r.conf_no = a.conf_no
           WHERE a.estado = 'PENDIENTE'""")
        if x["room_no"] in habitaciones_ingresan]

    conn.close()
    return {
        "fecha": fecha,
        "total_ingresos": len(ingresos), "pax_ingresos": pax(ingresos),
        "total_salidas": len(salidas), "pax_salidas": pax(salidas),
        "total_desayunos": len(desayunos), "pax_desayunos": pax(desayunos),
        "total_en_casa": len(en_casa), "pax_en_casa": pax(en_casa),
        "ingresos": ingresos, "salidas": salidas,
        "desayunos": desayunos, "en_casa": en_casa,
        "puntos": sorted(puntos.values(), key=lambda x: x["punto"]),
        "tours": tours,
        "restricciones_cocina": restricciones,
        "amenidades": amenidades,
    }


@app.get("/api/ocupacion")
def ocupacion(desde: str, hasta: str, user: dict = Depends(current_user)):
    """Ocupación día por día: cuántas habitaciones ocupadas, pax y porcentaje.
    Útil para gerencia, y para ver de un vistazo los días fuertes del mes."""
    conn = get_connection()
    # Se importa aquí para no depender del orden de las importaciones del archivo
    import qr_huesped as _qrh
    total_habitaciones = len(_qrh.cargar_config().get("habitaciones") or []) or 30

    reservas = [dict(r) for r in conn.execute(
        """SELECT room_no, arr_date, dep_date, adl, chl FROM reserva
           WHERE res_status != 'CANCELADA'""").fetchall()]
    conn.close()

    def a_fecha(dd):
        try:
            d, m, y = dd.split("-")
            return datetime.date(2000 + int(y), int(m), int(d))
        except (ValueError, AttributeError):
            return None

    inicio, fin = datetime.date.fromisoformat(desde), datetime.date.fromisoformat(hasta)
    dias = []
    dia = inicio
    while dia <= fin:
        habitaciones, pax, entran, salen = set(), 0, 0, 0
        for r in reservas:
            llega, sale = a_fecha(r["arr_date"]), a_fecha(r["dep_date"])
            if not llega:
                continue
            # Se cuenta ocupada la noche que el huésped duerme ahí: desde su llegada
            # hasta el día antes de su salida.
            if llega <= dia and (sale is None or dia < sale):
                habitaciones.add(r["room_no"])
                pax += (r["adl"] or 0) + (r["chl"] or 0)
            if llega == dia:
                entran += 1
            if sale == dia:
                salen += 1
        dias.append({
            "fecha": dia.isoformat(),
            "dia_semana": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][dia.weekday()],
            "habitaciones": len(habitaciones),
            "pax": pax,
            "entran": entran,
            "salen": salen,
            "porcentaje": round(100 * len(habitaciones) / total_habitaciones),
        })
        dia += datetime.timedelta(days=1)

    con_datos = [d for d in dias if d["habitaciones"] > 0]
    return {
        "desde": desde, "hasta": hasta,
        "total_habitaciones": total_habitaciones,
        "dias": dias,
        "resumen": {
            "ocupacion_promedio": round(sum(d["porcentaje"] for d in dias) / len(dias)) if dias else 0,
            "noches_habitacion": sum(d["habitaciones"] for d in dias),
            "dia_mas_alto": max(dias, key=lambda d: d["habitaciones"]) if con_datos else None,
            "dia_mas_bajo": min(con_datos, key=lambda d: d["habitaciones"]) if con_datos else None,
            "pax_promedio": round(sum(d["pax"] for d in con_datos) / len(con_datos)) if con_datos else 0,
        },
    }


@app.get("/api/reservas")
def reservas(desde: str = None, hasta: str = None, user: dict = Depends(current_user)):
    conn = get_connection()
    query = """SELECT r.*, g.confianza, g.confirmado_por_recepcion
               FROM reserva r LEFT JOIN grupo g ON g.id = r.grupo_id"""
    params = ()
    if desde and hasta:
        # Se incluyen todas las reservas que "tocan" el rango: las que llegan dentro,
        # las que salen dentro, y las que estuvieron en casa todo el periodo (llegaron
        # antes y salen después). Antes solo se mostraban las que llegaban en el rango,
        # dejando fuera a huéspedes que ya estaban hospedados.
        query += f""" WHERE (
            ({sql_fecha('r.arr_date')} BETWEEN ? AND ?)
            OR ({sql_fecha('r.dep_date')} BETWEEN ? AND ?)
            OR ({sql_fecha('r.arr_date')} <= ? AND {sql_fecha('r.dep_date')} >= ?)
        )"""
        d, h = yymmdd(desde), yymmdd(hasta)
        params = (d, h, d, h, d, h)
    query += " ORDER BY r.arr_date, r.room_no"
    rows = conn.execute(query, params).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        amenidades = conn.execute(
            "SELECT amenidad, tarea, area_responsable, estado FROM amenidad_tarea WHERE conf_no = ?",
            (r["conf_no"],),
        ).fetchall()
        d["amenidades"] = [dict(a) for a in amenidades]
        result.append(d)
    conn.close()
    return result


@app.get("/api/entradas-sinac")
def entradas_sinac(desde: str = None, hasta: str = None, user: dict = Depends(current_user)):
    conn = get_connection()
    query = "SELECT * FROM entrada_sinac"
    params = ()
    if desde and hasta:
        query += " WHERE fecha BETWEEN ? AND ?"
        params = (desde, hasta)
    query += " ORDER BY fecha"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()

    # Se buscan las reservas que tienen ese tour en esa fecha, para saber a quiénes
    # corresponde cada entrada. La relación sale de los tours asignados.
    conn = get_connection()
    hoy = datetime.date.today()
    for r in rows:
        # Se listan solo las reservas que corresponden a ESTA entrada: las que comparten
        # el mismo número de confirmación, o las que no tienen ninguno cuando la entrada
        # está pendiente de comprar. Sin este filtro se mezclarían reservas ya cubiertas
        # por otra entrada del mismo tour y fecha.
        if r["conf_entrada"]:
            cond_conf, param_conf = "ta.conf_entrada_sinac = ?", (r["conf_entrada"],)
        else:
            cond_conf, param_conf = "ta.conf_entrada_sinac IS NULL", ()
        reservas_rel = conn.execute(
            f"""SELECT DISTINCT res.conf_no, res.room_no, res.nombre_principal, res.adl, res.chl
               FROM tour_asignado ta JOIN reserva res ON res.conf_no = ta.conf_no
               WHERE ta.tour_codigo = ? AND ta.fecha = ? AND {cond_conf}
                 AND res.res_status != 'CANCELADA'
               ORDER BY res.room_no""",
            (r["tour_codigo"], r["fecha"]) + param_conf,
        ).fetchall()
        r["reservas"] = [dict(x) for x in reservas_rel]
        r["pax_huespedes"] = sum(x["adl"] + x["chl"] for x in reservas_rel)

        try:
            fecha_tour = datetime.date.fromisoformat(r["fecha"])
        except (ValueError, TypeError):
            r["fecha_limite_compra"] = None
            r["dias_para_limite"] = None
            r["urgencia"] = "SIN_FECHA"
            continue
        limite = fecha_tour - datetime.timedelta(days=15)
        dias = (limite - hoy).days
        r["fecha_limite_compra"] = limite.isoformat()
        r["dias_para_limite"] = dias
        if r["estado"] == "COMPRADA":
            r["urgencia"] = "OK"
        elif fecha_tour < hoy:
            r["urgencia"] = "PASADA"          # el tour ya ocurrió
        elif dias < 0:
            r["urgencia"] = "VENCIDA"         # ya pasó el plazo de 15 días
        elif dias <= 7:
            r["urgencia"] = "URGENTE"         # quedan 7 días o menos
        else:
            r["urgencia"] = "A_TIEMPO"
    conn.close()
    return rows


@app.get("/api/tours/agenda")
def agenda(fecha: str = None, desde: str = None, hasta: str = None, user: dict = Depends(current_user)):
    conn = get_connection()
    query = """SELECT ta.*, r.nombre_principal, r.room_no, tc.horario_inicio, tc.horario_fin, tc.max_pax_guia
               FROM tour_asignado ta
               JOIN reserva r ON r.conf_no = ta.conf_no
               JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo"""
    params = ()
    if fecha:
        query += " WHERE ta.fecha = ?"
        params = (fecha,)
    elif desde and hasta:
        query += " WHERE ta.fecha BETWEEN ? AND ?"
        params = (desde, hasta)
    query += " ORDER BY ta.fecha, tc.horario_inicio, ta.conf_no"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()

    agrupado = {}
    orden = []
    for r in rows:
        # Se agrupa solo por reserva: los tours de un mismo huésped pueden estar en
        # fechas distintas, y cada uno lleva su propia fecha editable.
        key = r["conf_no"]
        entry = {"id": r["id"], "tour_codigo": r["tour_codigo"], "fecha": r["fecha"],
                 "guia_nombre": r["guia_nombre"], "bote_nombre": r["bote_nombre"],
                 "horario_inicio": r["horario_inicio"], "horario_fin": r["horario_fin"],
                 "grupo_operativo": r.get("grupo_operativo", "A")}
        if key not in agrupado:
            agrupado[key] = {**r, "tours": [entry]}
            orden.append(key)
        else:
            agrupado[key]["tours"].append(entry)
    return [agrupado[k] for k in orden]


@app.get("/api/transporte")
def transporte(fecha: str = None, desde: str = None, hasta: str = None, user: dict = Depends(current_user)):
    conn = get_connection()
    if fecha:
        cond_e, params_e = "arr_date = ?", (ddmmyy(fecha),)
        cond_s, params_s = "dep_date = ?", (ddmmyy(fecha),)
    else:
        cond_e = f"{sql_fecha('arr_date')} BETWEEN ? AND ?"
        cond_s = f"{sql_fecha('dep_date')} BETWEEN ? AND ?"
        params_e = params_s = (yymmdd(desde), yymmdd(hasta))
    entradas = conn.execute(
        f"SELECT room_no, nombre_principal, punto_entrada, arr_time, hora_vuelo_entrada, adl, chl, arr_date FROM reserva WHERE {cond_e}",
        params_e,
    ).fetchall()
    salidas = conn.execute(
        f"SELECT room_no, nombre_principal, punto_salida, hora_vuelo_salida, adl, chl, dep_date FROM reserva WHERE {cond_s}",
        params_s,
    ).fetchall()
    conn.close()
    return {
        "entradas": [dict(r) for r in entradas],
        "salidas": [dict(r) for r in salidas],
    }


@app.get("/api/analitica")
def analitica(desde: str, hasta: str, user: dict = Depends(current_user)):
    conn = get_connection()
    uso_botes = conn.execute(
        """SELECT bote_nombre, COUNT(*) tours FROM tour_asignado
           WHERE fecha BETWEEN ? AND ? AND bote_nombre IS NOT NULL
           GROUP BY bote_nombre ORDER BY tours DESC""",
        (desde, hasta),
    ).fetchall()
    por_guia = conn.execute(
        """SELECT guia_nombre, COUNT(*) tours FROM tour_asignado
           WHERE fecha BETWEEN ? AND ? AND guia_nombre IS NOT NULL
           GROUP BY guia_nombre ORDER BY tours DESC""",
        (desde, hasta),
    ).fetchall()
    movimiento = conn.execute(
        f"""SELECT punto_entrada AS punto, SUM(adl + chl) pax FROM reserva
           WHERE {sql_fecha('arr_date')} BETWEEN ? AND ? AND punto_entrada IS NOT NULL
           GROUP BY punto_entrada""",
        (yymmdd(desde), yymmdd(hasta)),
    ).fetchall()
    conn.close()
    return {
        "uso_botes": [dict(r) for r in uso_botes],
        "actividades_por_guia": [dict(r) for r in por_guia],
        "movimiento_por_punto": [dict(r) for r in movimiento],
    }


@app.get("/api/analitica/bote/{nombre}")
def analitica_bote_detalle(nombre: str, desde: str, hasta: str, user: dict = Depends(current_user)):
    conn = get_connection()
    rows = conn.execute(
        """SELECT ta.fecha, ta.tour_codigo, ta.pax, ta.guia_nombre, r.nombre_principal, r.room_no
           FROM tour_asignado ta JOIN reserva r ON r.conf_no = ta.conf_no
           WHERE ta.bote_nombre = ? AND ta.fecha BETWEEN ? AND ?
           ORDER BY ta.fecha""",
        (nombre, desde, hasta),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/analitica/guia/{nombre}")
def analitica_guia_detalle(nombre: str, desde: str, hasta: str, user: dict = Depends(current_user)):
    conn = get_connection()
    rows = conn.execute(
        """SELECT ta.fecha, ta.tour_codigo, ta.pax, ta.bote_nombre, r.nombre_principal, r.room_no
           FROM tour_asignado ta JOIN reserva r ON r.conf_no = ta.conf_no
           WHERE ta.guia_nombre = ? AND ta.fecha BETWEEN ? AND ?
           ORDER BY ta.fecha""",
        (nombre, desde, hasta),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/catalogo")
def catalogo(todos: bool = False, user: dict = Depends(current_user)):
    conn = get_connection()
    cond = "" if todos else "WHERE activo = 1"
    tours = conn.execute(f"SELECT * FROM tour_catalogo {cond} ORDER BY codigo").fetchall()
    botes = conn.execute(f"SELECT * FROM bote {cond} ORDER BY nombre").fetchall()
    guias = conn.execute(f"SELECT * FROM guia {cond} ORDER BY nombre").fetchall()
    conn.close()
    return {
        "tours": [dict(t) for t in tours],
        "botes": [dict(b) for b in botes],
        "guias": [dict(g) for g in guias],
    }


# Análisis del último PDF revisado, para no volver a leerlo al confirmar.
# Leer un PDF de 77 reservas toma unos segundos; hacerlo dos veces (vista previa y
# confirmación) duplicaba la espera sin necesidad.
_ultimo_analisis = {"huella": None, "batch": None}


def _huella_archivo(datos):
    import hashlib
    return hashlib.sha256(datos).hexdigest()


def _analizar_pdf(datos, nombre="archivo.pdf"):
    """Analiza el PDF, reutilizando el resultado si es el mismo archivo de la vista previa."""
    huella = _huella_archivo(datos)
    if _ultimo_analisis["huella"] == huella and _ultimo_analisis["batch"] is not None:
        return _ultimo_analisis["batch"]
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(datos)
        tmp_path = tmp.name
    try:
        batch = build_review_batch(tmp_path)
    finally:
        os.unlink(tmp_path)
    _ultimo_analisis["huella"] = huella
    _ultimo_analisis["batch"] = batch
    return batch


# ---------- ESCRITURA (solo rol recepción) ----------
@app.post("/api/pdf/preview")
async def pdf_preview(file: UploadFile = File(...), user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    batch = _analizar_pdf(await file.read(), file.filename)
    simplified = []
    for item in batch["reservas"]:
        r = item["reserva"]
        simplified.append({
            "conf_no": r["conf_no"], "room_no": r["room_no"], "nombre": r["nombre_principal"],
            "arr_date": r["arr_date"], "dep_date": r["dep_date"], "adl": r["adl"], "chl": r["chl"],
            "punto_entrada": r["punto_entrada"], "punto_salida": r["punto_salida"],
            "tours_detectados": r["tours_detectados"], "guia_sugerido": r["guia_sugerido"],
            "grupo_link": r["grupo_link"], "agenda": r["agenda"], "needs_review": item["needs_review"],
            "amenidades_detectadas": r.get("amenidades_detectadas", []),
        })
    return {"reservas": simplified, "entradas_sinac": batch["entradas_sinac"]}


@app.post("/api/pdf/confirm")
async def pdf_confirm(file: UploadFile = File(...), user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    batch = _analizar_pdf(await file.read(), file.filename)
    _load_batch(batch, fuente_pdf=file.filename)
    alertas = validar_todos_los_tours()

    # Los itinerarios que ven los huéspedes no hay que publicarlos: se arman en el
    # momento en que se escanea el QR, así que quedan al día apenas termina esto.
    return {"status": "ok", "reservas_cargadas": len(batch["reservas"]),
            "alertas_generadas": len(alertas)}


@app.post("/api/tours/agenda/{tour_id}/asignar")
def asignar_guia_bote(tour_id: int, guia: str = None, bote: str = None, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    anterior = conn.execute(
        "SELECT fecha, guia_nombre, bote_nombre FROM tour_asignado WHERE id = ?", (tour_id,)
    ).fetchone()

    conn.execute(
        "UPDATE tour_asignado SET guia_nombre = COALESCE(?, guia_nombre), bote_nombre = COALESCE(?, bote_nombre) WHERE id = ?",
        (guia, bote, tour_id),
    )

    cambio_ultimo_momento = None
    if anterior:
        hoy = datetime.date.today().isoformat()
        cambio_real = (guia and guia != anterior["guia_nombre"]) or (bote and bote != anterior["bote_nombre"])
        if anterior["fecha"] == hoy and cambio_real:
            conn.execute("UPDATE tour_asignado SET es_cambio_ultimo_momento = 1 WHERE id = ?", (tour_id,))
            info = conn.execute(
                """SELECT ta.tour_codigo, r.nombre_principal, r.room_no FROM tour_asignado ta
                   JOIN reserva r ON r.conf_no = ta.conf_no WHERE ta.id = ?""",
                (tour_id,),
            ).fetchone()
            mensaje = (
                f"Cambio de último momento: {info['tour_codigo']} de {info['nombre_principal']} "
                f"(hab. {info['room_no']}) modificado el mismo día del tour "
                f"(guía: {anterior['guia_nombre'] or '—'} → {guia or anterior['guia_nombre']}, "
                f"bote: {anterior['bote_nombre'] or '—'} → {bote or anterior['bote_nombre']})."
            )
            conn.execute(
                "INSERT INTO alerta (tipo, referencia_id, mensaje) VALUES ('CAMBIO_ULTIMO_MOMENTO', ?, ?)",
                (tour_id, mensaje),
            )
            cambio_ultimo_momento = mensaje

    conn.commit()
    conn.close()
    alertas = validar_tour_asignado(tour_id)
    if cambio_ultimo_momento:
        alertas.append(cambio_ultimo_momento)
    # Se avisa si el guía o el bote quedaron en dos salidas que coinciden en horario
    if anterior:
        for cf in detectar_conflictos_asignacion(anterior["fecha"]):
            if cf["mensaje"] not in alertas:
                alertas.append(cf["mensaje"])
    return {"status": "ok", "alertas": alertas}


@app.post("/api/grupos/{grupo_id}/confirmar")
def confirmar_grupo(grupo_id: int, confirmar: bool = True, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    if confirmar:
        conn.execute("UPDATE grupo SET confirmado_por_recepcion = 1 WHERE id = ?", (grupo_id,))
    else:
        conn.execute("UPDATE reserva SET grupo_id = NULL WHERE grupo_id = ?", (grupo_id,))
        conn.execute("DELETE FROM grupo WHERE id = ?", (grupo_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/reservas/{conf_no}/guia")
def confirmar_guia_reserva(conf_no: str, guia: str = None, confirmar: bool = True, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    if guia:
        conn.execute("UPDATE reserva SET guia_sugerido = ?, guia_confirmado = 1 WHERE conf_no = ?", (guia, conf_no))
    elif confirmar:
        conn.execute("UPDATE reserva SET guia_confirmado = 1 WHERE conf_no = ?", (conf_no,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/entradas-sinac/{entrada_id}/marcar")
def marcar_entrada(entrada_id: int, estado: str = "COMPRADA", user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    conn.execute("UPDATE entrada_sinac SET estado = ? WHERE id = ?", (estado, entrada_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


# ---------- SINCRONIZACIÓN (máquina a máquina, sin login de usuario) ----------
import sync_engine

_startup_conn = get_connection()
_cfg = sync_engine.load_sync_config()
sync_engine.ensure_station_name(_startup_conn, _cfg.get("nombre_estacion", "Sierpe"))
_startup_conn.execute(
    "UPDATE sync_log SET origen_estacion = ? WHERE origen_estacion IS NULL",
    (_cfg.get("nombre_estacion", "Sierpe"),),
)
# Los disparadores del esquema anotan en sync_log cada escritura de la base. Con una
# sola instalación (el caso normal: todos entran al mismo servidor) nadie consume
# esas filas y la tabla crece para siempre. Se podan al arrancar; si hay otra
# estación configurada no se toca nada, porque ahí sí están pendientes de enviar.
if not _cfg.get("peer_url", "").strip():
    _startup_conn.execute("DELETE FROM sync_log WHERE creado_en <= datetime('now', '-7 days')")
_startup_conn.commit()
_startup_conn.close()
# El hilo de sincronización solo se levanta si de verdad hay otra estación
# configurada; si no, era un bucle despertándose cada 30 s sin hacer nada.
if _cfg.get("peer_url", "").strip():
    sync_engine.iniciar_sync_en_segundo_plano()


@app.get("/api/sync/estado")
def sync_estado(user: dict = Depends(current_user)):
    conn = get_connection()
    pendientes = conn.execute("SELECT COUNT(*) c FROM sync_log WHERE sincronizado = 0").fetchone()["c"]
    ultimo = conn.execute("SELECT MAX(creado_en) t FROM sync_log WHERE sincronizado = 1").fetchone()["t"]
    conn.close()
    cfg = sync_engine.load_sync_config()
    return {"estacion": cfg.get("nombre_estacion"), "peer_configurado": bool(cfg.get("peer_url")),
            "cambios_pendientes": pendientes, "ultimo_cambio_sincronizado": ultimo}


@app.post("/api/sync/ahora")
def sync_ahora(user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    return sync_engine.intentar_sincronizar()


@app.get("/api/sync/pending")
def sync_pending(x_sync_token: str = Header(None)):
    sync_engine.exigir_token(x_sync_token)
    conn = get_connection()
    cfg = sync_engine.load_sync_config()
    changes = sync_engine.get_pending_changes(conn, cfg.get("nombre_estacion"))
    conn.close()
    return {"changes": changes}


@app.post("/api/sync/apply")
async def sync_apply(payload: dict, x_sync_token: str = Header(None)):
    sync_engine.exigir_token(x_sync_token)
    conn = get_connection()
    aplicados = sync_engine.apply_remote_changes(conn, payload.get("changes", []))
    conn.close()
    return {"aplicados": aplicados}


@app.get("/api/usuarios")
def listar_usuarios(user: dict = Depends(current_user)):
    auth.requiere_admin(user)
    conn = get_connection()
    rows = conn.execute("SELECT id, username, nombre_completo, rol, activo FROM usuario ORDER BY username").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/usuarios")
async def crear_usuario(payload: dict, user: dict = Depends(current_user)):
    auth.requiere_admin(user)
    if payload.get("rol") not in ("recepcion", "gerencia", "staff"):
        raise HTTPException(status_code=400, detail="Rol inválido")
    auth.validar_password(payload.get("password"))
    conn = get_connection()
    existe = conn.execute("SELECT id FROM usuario WHERE username = ?", (payload["username"],)).fetchone()
    if existe:
        conn.close()
        raise HTTPException(status_code=400, detail="Ese nombre de usuario ya existe")
    h, salt = auth.hash_password(payload["password"])
    conn.execute(
        "INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol) VALUES (?,?,?,?,?)",
        (payload["username"], h, salt, payload["nombre_completo"], payload["rol"]),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/usuarios/{usuario_id}/estado")
def cambiar_estado_usuario(usuario_id: int, activo: bool, user: dict = Depends(current_user)):
    auth.requiere_admin(user)
    conn = get_connection()
    if not activo:
        # Sin esta comprobación era posible desactivar la última cuenta de recepción
        # y quedarse sin nadie que pueda administrar el sistema.
        quedan = conn.execute(
            "SELECT COUNT(*) c FROM usuario WHERE rol = 'recepcion' AND activo = 1 AND id != ?",
            (usuario_id,),
        ).fetchone()["c"]
        if quedan == 0:
            conn.close()
            raise HTTPException(status_code=400,
                                detail="Debe quedar al menos una cuenta de Recepción activa")
    conn.execute("UPDATE usuario SET activo = ? WHERE id = ?", (1 if activo else 0, usuario_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/usuarios/{usuario_id}/password")
async def cambiar_password_usuario(usuario_id: int, payload: dict, user: dict = Depends(current_user)):
    auth.requiere_admin(user)
    auth.validar_password(payload.get("password"))
    h, salt = auth.hash_password(payload["password"])
    conn = get_connection()
    conn.execute("UPDATE usuario SET password_hash = ?, salt = ? WHERE id = ?", (h, salt, usuario_id))
    # Cambiar la contraseña cierra las sesiones abiertas de esa cuenta.
    conn.execute("DELETE FROM sesion WHERE usuario_id = ?", (usuario_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/guia")
async def crear_guia(payload: dict, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    existe = conn.execute("SELECT nombre FROM guia WHERE nombre = ?", (payload["nombre"],)).fetchone()
    if existe:
        conn.close()
        raise HTTPException(status_code=400, detail="Ya existe un guía con ese nombre")
    conn.execute(
        "INSERT INTO guia (nombre, es_externo) VALUES (?, ?)",
        (payload["nombre"], 1 if payload.get("es_externo") else 0),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/guia/{nombre}/estado")
def estado_guia(nombre: str, activo: bool, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    conn.execute("UPDATE guia SET activo = ? WHERE nombre = ?", (1 if activo else 0, nombre))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/bote")
async def crear_bote(payload: dict, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    existe = conn.execute("SELECT nombre FROM bote WHERE nombre = ?", (payload["nombre"],)).fetchone()
    if existe:
        conn.close()
        raise HTTPException(status_code=400, detail="Ya existe un bote con ese nombre")
    conn.execute(
        "INSERT INTO bote (nombre, capacidad_max, gestionado_por_hotel) VALUES (?, ?, ?)",
        (payload["nombre"], payload.get("capacidad_max"), 1 if payload.get("gestionado_por_hotel", True) else 0),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/bote/{nombre}/estado")
def estado_bote(nombre: str, activo: bool, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    conn.execute("UPDATE bote SET activo = ? WHERE nombre = ?", (1 if activo else 0, nombre))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/tour")
async def crear_tour(payload: dict, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    existe = conn.execute("SELECT codigo FROM tour_catalogo WHERE codigo = ?", (payload["codigo"],)).fetchone()
    if existe:
        conn.close()
        raise HTTPException(status_code=400, detail="Ya existe un tour con ese código")
    conn.execute(
        """INSERT INTO tour_catalogo
           (codigo, nombre, horario_inicio, horario_fin, max_pax_guia, requiere_entrada_sinac, es_privado, tour_base)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            payload["codigo"].upper(), payload["nombre"], payload.get("horario_inicio"), payload.get("horario_fin"),
            payload["max_pax_guia"], 1 if payload.get("requiere_entrada_sinac") else 0,
            1 if payload.get("es_privado") else 0, payload.get("tour_base"),
        ),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/tour/{codigo}/estado")
def estado_tour(codigo: str, activo: bool, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    conn.execute("UPDATE tour_catalogo SET activo = ? WHERE codigo = ?", (1 if activo else 0, codigo))
    conn.commit()
    conn.close()
    return {"status": "ok"}


from fastapi.responses import Response
import exports


def export_response(buf, filename, formato):
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if formato == "xlsx" else "application/pdf"
    return Response(
        content=buf.getvalue(), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{formato}"'},
    )


@app.get("/api/export/reservas")
def export_reservas(desde: str = None, hasta: str = None, formato: str = "xlsx", user: dict = Depends(current_user)):
    conn = get_connection()
    query = """SELECT r.*, g.confianza FROM reserva r LEFT JOIN grupo g ON g.id = r.grupo_id"""
    params = ()
    if desde and hasta:
        query += f" WHERE {sql_fecha('r.arr_date')} BETWEEN ? AND ?"
        params = (yymmdd(desde), yymmdd(hasta))
    query += " ORDER BY r.arr_date, r.room_no"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()
    for r in rows:
        r["pax"] = r["adl"] + r["chl"]
    columns = [
        ("conf_no", "N° Reserva"), ("room_no", "Hab."), ("nombre_principal", "Huésped"),
        ("arr_date", "Ingreso"), ("dep_date", "Salida"), ("pax", "Pax"),
        ("res_status", "Estatus"), ("confianza", "Grupo"),
    ]
    titulo = "Reservas — Corcovado Wilderness Lodge"
    subt = f"{desde or '(todas)'} a {hasta or ''}"
    buf = exports.to_xlsx(columns, rows, titulo) if formato == "xlsx" else exports.to_pdf(columns, rows, titulo, subt)
    return export_response(buf, "reservas", formato)


@app.get("/api/export/agenda")
def export_agenda(fecha: str = None, desde: str = None, hasta: str = None, formato: str = "xlsx", user: dict = Depends(current_user)):
    conn = get_connection()
    query = """SELECT ta.fecha, ta.tour_codigo, ta.guia_nombre, ta.bote_nombre, ta.pax,
                      r.nombre_principal, r.room_no
               FROM tour_asignado ta JOIN reserva r ON r.conf_no = ta.conf_no"""
    params = ()
    if fecha:
        query += " WHERE ta.fecha = ?"
        params = (fecha,)
    elif desde and hasta:
        query += " WHERE ta.fecha BETWEEN ? AND ?"
        params = (desde, hasta)
    query += " ORDER BY ta.fecha, ta.tour_codigo"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()
    columns = [
        ("fecha", "Fecha"), ("tour_codigo", "Tour"), ("nombre_principal", "Huésped"), ("room_no", "Hab."),
        ("guia_nombre", "Guía"), ("bote_nombre", "Bote"), ("pax", "Pax"),
    ]
    titulo = "Agenda de Tours — Corcovado Wilderness Lodge"
    subt = fecha or f"{desde} a {hasta}"
    buf = exports.to_xlsx(columns, rows, titulo) if formato == "xlsx" else exports.to_pdf(columns, rows, titulo, subt)
    return export_response(buf, "agenda_tours", formato)


@app.get("/api/export/transporte")
def export_transporte(fecha: str = None, desde: str = None, hasta: str = None, formato: str = "xlsx", user: dict = Depends(current_user)):
    conn = get_connection()
    if fecha:
        cond_e, params_e = "arr_date = ?", (ddmmyy(fecha),)
        cond_s, params_s = "dep_date = ?", (ddmmyy(fecha),)
    else:
        cond_e = f"{sql_fecha('arr_date')} BETWEEN ? AND ?"
        cond_s = f"{sql_fecha('dep_date')} BETWEEN ? AND ?"
        params_e = params_s = (yymmdd(desde), yymmdd(hasta))
    entradas = [dict(r) for r in conn.execute(
        f"SELECT room_no, nombre_principal, punto_entrada, arr_time, hora_vuelo_entrada, adl, chl, arr_date FROM reserva WHERE {cond_e}", params_e).fetchall()]
    salidas = [dict(r) for r in conn.execute(
        f"SELECT room_no, nombre_principal, punto_salida, hora_vuelo_salida, adl, chl, dep_date FROM reserva WHERE {cond_s}", params_s).fetchall()]
    conn.close()
    for r in entradas + salidas:
        r["pax"] = r["adl"] + r["chl"]
        r["tipo"] = "Entrada" if "arr_date" in r else "Salida"
    for r in entradas:
        r["fecha"] = r["arr_date"]; r["punto"] = r["punto_entrada"]; r["hora"] = r.get("hora_vuelo_entrada") or r.get("arr_time")
    for r in salidas:
        r["fecha"] = r["dep_date"]; r["punto"] = r["punto_salida"]; r["hora"] = r.get("hora_vuelo_salida")
    rows = entradas + salidas
    columns = [("fecha", "Fecha"), ("tipo", "Tipo"), ("room_no", "Hab."), ("nombre_principal", "Huésped"),
               ("punto", "Punto"), ("hora", "Hora"), ("pax", "Pax")]
    titulo = "Transporte — Corcovado Wilderness Lodge"
    subt = fecha or f"{desde} a {hasta}"
    buf = exports.to_xlsx(columns, rows, titulo) if formato == "xlsx" else exports.to_pdf(columns, rows, titulo, subt)
    return export_response(buf, "transporte", formato)


@app.get("/api/export/entradas-sinac")
def export_entradas(desde: str = None, hasta: str = None, formato: str = "xlsx", user: dict = Depends(current_user)):
    conn = get_connection()
    query = "SELECT * FROM entrada_sinac"
    params = ()
    if desde and hasta:
        query += " WHERE fecha BETWEEN ? AND ?"
        params = (desde, hasta)
    query += " ORDER BY fecha"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()
    columns = [("fecha", "Fecha"), ("tour_codigo", "Actividad"), ("pax_total_grupo", "Pax + guía"),
               ("conf_entrada", "Conf."), ("estado", "Estado")]
    titulo = "Entradas SINAC — Corcovado Wilderness Lodge"
    subt = f"{desde or '(todas)'} a {hasta or ''}"
    buf = exports.to_xlsx(columns, rows, titulo) if formato == "xlsx" else exports.to_pdf(columns, rows, titulo, subt)
    return export_response(buf, "entradas_sinac", formato)


@app.get("/api/export/resumen-operacion")
def export_resumen(fecha: str, formato: str = "xlsx", user: dict = Depends(current_user)):
    conn = get_connection()
    tours = [dict(r) for r in conn.execute(
        """SELECT ta.tour_codigo, ta.guia_nombre, ta.bote_nombre, SUM(ta.pax) pax_total
           FROM tour_asignado ta WHERE ta.fecha = ?
           GROUP BY ta.tour_codigo, ta.guia_nombre, ta.bote_nombre""", (fecha,)).fetchall()]
    conn.close()
    columns = [("tour_codigo", "Tour"), ("guia_nombre", "Guía"), ("bote_nombre", "Bote"), ("pax_total", "Pax total")]
    titulo = "Resumen de Operación — Corcovado Wilderness Lodge"
    buf = exports.to_xlsx(columns, tours, titulo) if formato == "xlsx" else exports.to_pdf(columns, tours, titulo, fecha)
    return export_response(buf, f"resumen_operacion_{fecha}", formato)


@app.get("/api/export/analitica")
def export_analitica(desde: str, hasta: str, formato: str = "xlsx", user: dict = Depends(current_user)):
    conn = get_connection()
    uso_botes = [dict(r) for r in conn.execute(
        """SELECT bote_nombre, COUNT(*) tours FROM tour_asignado
           WHERE fecha BETWEEN ? AND ? AND bote_nombre IS NOT NULL
           GROUP BY bote_nombre ORDER BY tours DESC""", (desde, hasta)).fetchall()]
    por_guia = [dict(r) for r in conn.execute(
        """SELECT guia_nombre, COUNT(*) tours FROM tour_asignado
           WHERE fecha BETWEEN ? AND ? AND guia_nombre IS NOT NULL
           GROUP BY guia_nombre ORDER BY tours DESC""", (desde, hasta)).fetchall()]
    movimiento = [dict(r) for r in conn.execute(
        f"""SELECT punto_entrada AS punto, SUM(adl + chl) pax FROM reserva
           WHERE {sql_fecha('arr_date')} BETWEEN ? AND ? AND punto_entrada IS NOT NULL
           GROUP BY punto_entrada""", (yymmdd(desde), yymmdd(hasta))).fetchall()]
    conn.close()

    combinado = (
        [{"seccion": "Uso de botes", "item": r["bote_nombre"], "valor": r["tours"]} for r in uso_botes]
        + [{"seccion": "Actividades por guía", "item": r["guia_nombre"], "valor": r["tours"]} for r in por_guia]
        + [{"seccion": "Movimiento por punto", "item": r["punto"], "valor": r["pax"]} for r in movimiento]
    )
    columns = [("seccion", "Sección"), ("item", "Detalle"), ("valor", "Valor")]
    titulo = "Analítica Operativa — Corcovado Wilderness Lodge"
    subt = f"{desde} a {hasta}"
    buf = exports.to_xlsx(columns, combinado, titulo) if formato == "xlsx" else exports.to_pdf(columns, combinado, titulo, subt)
    return export_response(buf, "analitica", formato)


@app.post("/api/reservas/{conf_no}/transporte")
def confirmar_transporte(conf_no: str, tipo: str, punto: str, user: dict = Depends(current_user)):
    """Permite a recepción fijar manualmente el punto (Sierpe/Drake) cuando el PDF
    no lo indicaba con claridad."""
    auth.requiere_escritura(user)
    if tipo not in ("entrada", "salida") or punto not in ("Sierpe", "Drake"):
        raise HTTPException(status_code=400, detail="Tipo o punto inválido")
    conn = get_connection()
    if tipo == "entrada":
        conn.execute(
            "UPDATE reserva SET punto_entrada = ?, punto_entrada_sin_confirmar = NULL WHERE conf_no = ?",
            (punto, conf_no),
        )
    else:
        conn.execute(
            "UPDATE reserva SET punto_salida = ?, punto_salida_sin_confirmar = NULL WHERE conf_no = ?",
            (punto, conf_no),
        )
    # Resolver la alerta correspondiente
    conn.execute(
        "UPDATE alerta SET resuelto = 1 WHERE tipo='TRANSPORTE_SIN_CONFIRMAR' AND mensaje LIKE ?",
        (f"%de {tipo} de%",),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/api/transporte/pendientes")
def transporte_pendientes(user: dict = Depends(current_user)):
    conn = get_connection()
    rows = conn.execute(
        """SELECT conf_no, room_no, nombre_principal, arr_date, dep_date,
                  punto_entrada_sin_confirmar, punto_salida_sin_confirmar
           FROM reserva
           WHERE punto_entrada_sin_confirmar IS NOT NULL OR punto_salida_sin_confirmar IS NOT NULL
           ORDER BY arr_date"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/reservas/{conf_no}/detalle")
def detalle_reserva(conf_no: str, user: dict = Depends(current_user)):
    """Devuelve toda la información de una reserva: datos, huéspedes, tours,
    amenidades y notas — para mostrarla en un cuadro de detalle."""
    conn = get_connection()
    r = conn.execute(
        """SELECT r.*, g.confianza, g.confirmado_por_recepcion
           FROM reserva r LEFT JOIN grupo g ON g.id = r.grupo_id
           WHERE r.conf_no = ?""",
        (conf_no,),
    ).fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    huespedes = conn.execute(
        "SELECT nombre_completo, pasaporte, nacionalidad FROM huesped WHERE conf_no = ?", (conf_no,)
    ).fetchall()
    tours = conn.execute(
        """SELECT ta.fecha, ta.tour_codigo, ta.guia_nombre, ta.bote_nombre, ta.pax,
                  ta.conf_entrada_sinac, tc.horario_inicio, tc.horario_fin
           FROM tour_asignado ta LEFT JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
           WHERE ta.conf_no = ? ORDER BY ta.fecha, tc.horario_inicio""",
        (conf_no,),
    ).fetchall()
    amenidades = conn.execute(
        "SELECT amenidad, tarea, area_responsable, estado FROM amenidad_tarea WHERE conf_no = ?",
        (conf_no,),
    ).fetchall()
    # Reservas del mismo grupo (si aplica)
    grupo_reservas = []
    if r["grupo_id"]:
        grupo_reservas = conn.execute(
            "SELECT conf_no, room_no, nombre_principal FROM reserva WHERE grupo_id = ? AND conf_no != ?",
            (r["grupo_id"], conf_no),
        ).fetchall()
    conn.close()

    d = dict(r)
    d["huespedes"] = [dict(h) for h in huespedes]
    d["tours"] = [dict(t) for t in tours]
    d["amenidades"] = [dict(a) for a in amenidades]
    d["grupo_reservas"] = [dict(g) for g in grupo_reservas]
    return d


@app.post("/api/tours/agenda/{tour_id}/grupo")
def cambiar_grupo_operativo(tour_id: int, grupo: str, user: dict = Depends(current_user)):
    """Mueve un tour a otro grupo operativo (A, B, C...). Sirve para dividir un tour
    grande en grupos separados, cada uno con su propio guía y bote."""
    auth.requiere_escritura(user)
    grupo = (grupo or "A").strip().upper()
    if not grupo or len(grupo) > 2:
        raise HTTPException(status_code=400, detail="Grupo inválido (usa A, B, C...)")
    conn = get_connection()
    ta = conn.execute("SELECT * FROM tour_asignado WHERE id = ?", (tour_id,)).fetchone()
    if not ta:
        conn.close()
        raise HTTPException(status_code=404, detail="Tour no encontrado")
    # Al mover a otro grupo se limpia el guía (cada grupo lleva el suyo), pero se
    # CONSERVA el bote: dos grupos con guías distintos pueden viajar en el mismo bote.
    # Si se necesita un bote aparte, se cambia manualmente desde la agenda.
    conn.execute(
        "UPDATE tour_asignado SET grupo_operativo = ?, guia_nombre = NULL WHERE id = ?",
        (grupo, tour_id),
    )
    # Resolver alertas previas de este tour/fecha, ya que la división cambia el escenario
    conn.execute(
        "UPDATE alerta SET resuelto = 1 WHERE referencia_id = ? AND tipo IN ('CAPACIDAD_GUIA','CAPACIDAD_BOTE')",
        (tour_id,),
    )
    conn.commit()
    conn.close()
    alertas = validar_tour_asignado(tour_id)
    return {"status": "ok", "grupo": grupo, "alertas": alertas}


@app.get("/api/tours/grupos-disponibles")
def grupos_disponibles(fecha: str, tour_codigo: str, user: dict = Depends(current_user)):
    """Devuelve los grupos operativos ya usados para un tour en una fecha, con su
    pax total, guía y bote — para mostrar el panorama al dividir."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT grupo_operativo, SUM(pax) pax_total,
                  GROUP_CONCAT(DISTINCT guia_nombre) guias,
                  GROUP_CONCAT(DISTINCT bote_nombre) botes
           FROM tour_asignado WHERE fecha = ? AND tour_codigo = ?
           GROUP BY grupo_operativo ORDER BY grupo_operativo""",
        (fecha, tour_codigo),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/amenidades")
async def crear_amenidad_manual(payload: dict, user: dict = Depends(current_user)):
    """Permite a recepción/gerencia agregar un requerimiento del huésped que no venía
    en el PDF: alergias reportadas por teléfono, preferencias, peticiones especiales."""
    auth.requiere_escritura(user)
    if not payload.get("conf_no") or not payload.get("amenidad"):
        raise HTTPException(status_code=400, detail="Falta la reserva o la descripción")
    conn = get_connection()
    existe = conn.execute("SELECT 1 FROM reserva WHERE conf_no = ?", (payload["conf_no"],)).fetchone()
    if not existe:
        conn.close()
        raise HTTPException(status_code=404, detail="No existe una reserva con ese número")
    conn.execute(
        """INSERT INTO amenidad_tarea (conf_no, amenidad, detalle, tarea, area_responsable, origen)
           VALUES (?,?,?,?,?,'MANUAL')""",
        (payload["conf_no"], payload["amenidad"], payload.get("detalle"),
         payload.get("tarea") or payload["amenidad"],
         payload.get("area_responsable") or "Recepción"),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.delete("/api/amenidades/{amenidad_id}")
def eliminar_amenidad(amenidad_id: int, user: dict = Depends(current_user)):
    """Solo se pueden eliminar los requerimientos agregados manualmente; los detectados
    del PDF se vuelven a generar en cada importación."""
    auth.requiere_escritura(user)
    conn = get_connection()
    row = conn.execute("SELECT origen FROM amenidad_tarea WHERE id = ?", (amenidad_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="No encontrado")
    if row["origen"] != "MANUAL":
        conn.close()
        raise HTTPException(status_code=400, detail="Solo se pueden eliminar los agregados manualmente")
    conn.execute("DELETE FROM amenidad_tarea WHERE id = ?", (amenidad_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/api/amenidades")
def listar_amenidades(desde: str = None, hasta: str = None, estado: str = None,
                      user: dict = Depends(current_user)):
    """Lista las amenidades a preparar, filtradas por la fecha de llegada del huésped
    (que es cuando normalmente hay que tenerlas listas)."""
    conn = get_connection()
    query = f"""SELECT a.id, a.amenidad, a.tarea, a.area_responsable, a.estado, a.origen, a.detalle,
                       r.conf_no, r.room_no, r.nombre_principal, r.arr_date, r.dep_date
                FROM amenidad_tarea a JOIN reserva r ON r.conf_no = a.conf_no"""
    condiciones, params = [], []
    if desde and hasta:
        condiciones.append(f"{sql_fecha('r.arr_date')} BETWEEN ? AND ?")
        params += [yymmdd(desde), yymmdd(hasta)]
    if estado in ("PENDIENTE", "HECHA"):
        condiciones.append("a.estado = ?")
        params.append(estado)
    if condiciones:
        query += " WHERE " + " AND ".join(condiciones)
    query += f" ORDER BY {sql_fecha('r.arr_date')}, r.room_no"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/amenidades/{amenidad_id}/estado")
def cambiar_estado_amenidad(amenidad_id: int, estado: str, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    if estado not in ("PENDIENTE", "HECHA"):
        raise HTTPException(status_code=400, detail="Estado inválido")
    conn = get_connection()
    conn.execute("UPDATE amenidad_tarea SET estado = ? WHERE id = ?", (estado, amenidad_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/api/export/amenidades")
def export_amenidades(desde: str = None, hasta: str = None, formato: str = "xlsx",
                      user: dict = Depends(current_user)):
    conn = get_connection()
    query = f"""SELECT r.arr_date, r.room_no, r.nombre_principal, a.amenidad,
                       a.tarea, a.area_responsable, a.estado
                FROM amenidad_tarea a JOIN reserva r ON r.conf_no = a.conf_no"""
    params = []
    if desde and hasta:
        query += f" WHERE {sql_fecha('r.arr_date')} BETWEEN ? AND ?"
        params = [yymmdd(desde), yymmdd(hasta)]
    query += f" ORDER BY {sql_fecha('r.arr_date')}, r.room_no"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()
    columns = [("arr_date", "Llegada"), ("room_no", "Hab."), ("nombre_principal", "Huésped"),
               ("amenidad", "Amenidad"), ("tarea", "Tarea"), ("area_responsable", "Área"), ("estado", "Estado")]
    titulo = "Amenidades y Tareas — Corcovado Wilderness Lodge"
    subt = f"{desde or '(todas)'} a {hasta or ''}"
    buf = exports.to_xlsx(columns, rows, titulo) if formato == "xlsx" else exports.to_pdf(columns, rows, titulo, subt)
    return export_response(buf, "amenidades", formato)


import json as _json
import itinerario as itin


def _guardar_itinerario(conn, conf_no, nombre, filas, editado=0, aviso=None, idioma=None):
    if idioma is None:
        prev = conn.execute("SELECT idioma FROM itinerario WHERE conf_no = ?", (conf_no,)).fetchone()
        idioma = dict(prev)["idioma"] if prev else "en"
    conn.execute(
        """INSERT INTO itinerario (conf_no, nombre_bienvenida, filas_json, editado,
                                   aviso_cambios, idioma, actualizado_en)
           VALUES (?,?,?,?,?,?,datetime('now'))
           ON CONFLICT(conf_no) DO UPDATE SET
             nombre_bienvenida=excluded.nombre_bienvenida, filas_json=excluded.filas_json,
             editado=excluded.editado, aviso_cambios=excluded.aviso_cambios,
             idioma=excluded.idioma, actualizado_en=datetime('now')""",
        (conf_no, nombre, _json.dumps(filas, ensure_ascii=False), editado, aviso, idioma),
    )


@app.post("/api/tours/agenda/{tour_id}/fecha")
def cambiar_fecha_tour(tour_id: int, fecha: str, user: dict = Depends(current_user)):
    """Cambia la fecha de un tour. La fecha que trae la reserva es una intención, pero
    la operación real puede moverla (clima, mareas, cupos, decisión del huésped).

    Al mover un tour se actualiza todo lo que dependa de esa fecha:
      · la entrada al SINAC, cuyo plazo de compra se recalcula
      · el itinerario del huésped, para que reciba la fecha correcta
      · las validaciones de capacidad y los conflictos de horario de ambos días
    """
    auth.requiere_escritura(user)
    try:
        datetime.date.fromisoformat(fecha)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida (usa AAAA-MM-DD)")

    conn = get_connection()
    ta = conn.execute("SELECT * FROM tour_asignado WHERE id = ?", (tour_id,)).fetchone()
    if not ta:
        conn.close()
        raise HTTPException(status_code=404, detail="Tour no encontrado")
    ta = dict(ta)
    fecha_anterior = ta["fecha"]
    if fecha_anterior == fecha:
        conn.close()
        return {"status": "ok", "sin_cambios": True}

    conn.execute("UPDATE tour_asignado SET fecha = ? WHERE id = ?", (fecha, tour_id))

    # La entrada al SINAC va atada al tour y a su fecha: si el tour se mueve, la
    # entrada también, y con ella el plazo de compra de 15 días.
    entrada_movida = None
    if ta.get("conf_entrada_sinac"):
        otros = conn.execute(
            """SELECT COUNT(*) c FROM tour_asignado
               WHERE fecha = ? AND tour_codigo = ? AND conf_entrada_sinac = ? AND id != ?""",
            (fecha_anterior, ta["tour_codigo"], ta["conf_entrada_sinac"], tour_id)).fetchone()["c"]
        if otros == 0:
            # Nadie más queda en la fecha vieja con esa entrada: se mueve
            conn.execute(
                """UPDATE entrada_sinac SET fecha = ?
                   WHERE tour_codigo = ? AND fecha = ? AND conf_entrada IS ?""",
                (fecha, ta["tour_codigo"], fecha_anterior, ta["conf_entrada_sinac"]))
            entrada_movida = ta["conf_entrada_sinac"]

    # Si el tour se mueve al día de hoy o a mañana, es un cambio de último momento
    hoy = datetime.date.today()
    try:
        nueva = datetime.date.fromisoformat(fecha)
        if (nueva - hoy).days <= 1:
            conn.execute("UPDATE tour_asignado SET es_cambio_ultimo_momento = 1 WHERE id = ?", (tour_id,))
    except ValueError:
        pass

    conn.commit()

    # El itinerario del huésped debe reflejar la fecha nueva
    aviso_itinerario = _actualizar_itinerario_por_fecha(
        conn, ta["conf_no"], ta["tour_codigo"], fecha_anterior, fecha)
    conn.commit()
    conn.close()

    # Se revalidan los dos días: el que se libera y el que recibe el tour
    alertas = validar_tour_asignado(tour_id)
    for f in (fecha_anterior, fecha):
        for cf in detectar_conflictos_asignacion(f):
            if cf["mensaje"] not in alertas:
                alertas.append(cf["mensaje"])

    return {"status": "ok", "de": fecha_anterior, "a": fecha,
            "entrada_sinac_movida": entrada_movida,
            "itinerario": aviso_itinerario, "alertas": alertas}


def _actualizar_itinerario_por_fecha(conn, conf_no, tour_codigo, fecha_vieja, fecha_nueva):
    """Mueve la fila del itinerario que corresponde a ese tour a la fecha nueva,
    conservando cualquier texto que recepción haya ajustado a mano."""
    fila = conn.execute("SELECT * FROM itinerario WHERE conf_no = ?", (conf_no,)).fetchone()
    if not fila:
        return "sin itinerario"
    d = dict(fila)
    filas = _json.loads(d["filas_json"])

    import catalogo_itinerario as cat
    nombre_en = cat.texto_tour(tour_codigo)["nombre"].replace("\n", " ").strip().lower()
    dia_viejo = itin._fecha_larga(fecha_vieja).lower()
    dia_nuevo = itin._fecha_larga(fecha_nueva)

    movida = False
    for f in filas:
        actividad = " ".join((f.get("actividad") or "").split()).lower()
        if (f.get("dia") or "").strip().lower() != dia_viejo:
            continue
        # Coincidencia flexible: recepción puede haberle agregado texto al nombre
        # (ej. "Scuba Diving — SALIDA ESPECIAL"), y aun así es el mismo tour.
        if actividad == nombre_en or nombre_en in actividad or actividad.startswith(nombre_en[:14]):
            f["dia"] = dia_nuevo
            movida = True
            break

    if movida:
        filas = itin.incorporar_faltantes(filas, [])   # reordena por fecha
        _guardar_itinerario(conn, conf_no, d["nombre_bienvenida"], filas,
                            editado=d["editado"], aviso=None)
        return "actualizado"

    # No se encontró la fila (itinerario editado con otro texto): se avisa
    if d["editado"]:
        aviso = (f"El tour {tour_codigo} se movió del {fecha_vieja} al {fecha_nueva}, "
                 f"pero el itinerario fue editado a mano y no se pudo ajustar solo. "
                 f"Revísalo antes de enviarlo.")
        conn.execute("UPDATE itinerario SET aviso_cambios = ? WHERE conf_no = ?", (aviso, conf_no))
        return "requiere revisión manual"

    # Si no está editado se rearma completo
    datos = itin.datos_de_reserva(conn, conf_no)
    if datos:
        nuevas, _ = itin.construir_itinerario(datos)
        _guardar_itinerario(conn, conf_no, datos["nombre_bienvenida"], nuevas, editado=0)
        return "regenerado"
    return "sin cambios"


@app.get("/api/reservas/{conf_no}/itinerario")
def obtener_itinerario(conf_no: str, user: dict = Depends(current_user)):
    """Devuelve el itinerario de la reserva. Si aún no existe, lo genera al momento."""
    conn = get_connection()
    fila = conn.execute("SELECT * FROM itinerario WHERE conf_no = ?", (conf_no,)).fetchone()
    datos = itin.datos_de_reserva(conn, conf_no)
    if not datos:
        conn.close()
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    filas_auto, avisos = itin.construir_itinerario(datos)

    if fila:
        d = dict(fila)
        filas = _json.loads(d["filas_json"])
        editado = bool(d["editado"])
        aviso_cambios = d["aviso_cambios"]
        # Si recepción ya lo editó, se compara contra lo que saldría hoy para avisar
        # si la reserva cambió después (ej. se agregó un tour en el PDF actualizado).
        if editado:
            dias_actuales = {f["dia"] + "|" + f["actividad"] for f in filas}
            nuevos = [f for f in filas_auto if f["dia"] + "|" + f["actividad"] not in dias_actuales]
            if nuevos:
                aviso_cambios = ("La reserva cambió después de editar el itinerario. "
                                 "No está incluido: "
                                 + "; ".join(f"{f['dia']} {f['actividad']}".replace("\n", " ") for f in nuevos))
            else:
                aviso_cambios = None
            conn.execute("UPDATE itinerario SET aviso_cambios = ? WHERE conf_no = ?", (aviso_cambios, conf_no))
            conn.commit()
    else:
        filas, editado, aviso_cambios = filas_auto, False, None
        _guardar_itinerario(conn, conf_no, datos["nombre_bienvenida"], filas)
        conn.commit()

    conn.close()
    if aviso_cambios:
        estado = "CAMBIOS"
    elif editado:
        estado = "EDITADO"
    elif avisos:
        estado = "REVISAR"
    else:
        estado = "LISTO"
    import traducciones as _tr
    idioma = dict(fila)["idioma"] if fila else "en"
    return {"conf_no": conf_no, "nombre_bienvenida": datos["nombre_bienvenida"],
            "filas": filas, "editado": editado, "estado": estado,
            "avisos": avisos, "aviso_cambios": aviso_cambios,
            "idioma": idioma, "idiomas": _tr.IDIOMAS}


@app.put("/api/reservas/{conf_no}/itinerario")
async def guardar_itinerario(conf_no: str, payload: dict, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    conn = get_connection()
    _guardar_itinerario(conn, conf_no, payload.get("nombre_bienvenida"),
                        payload.get("filas", []), editado=1, aviso=None,
                        idioma=payload.get("idioma"))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/reservas/{conf_no}/itinerario/regenerar")
def regenerar_itinerario(conf_no: str, user: dict = Depends(current_user)):
    """Descarta las ediciones manuales y vuelve a armarlo desde la reserva."""
    auth.requiere_escritura(user)
    conn = get_connection()
    datos = itin.datos_de_reserva(conn, conf_no)
    if not datos:
        conn.close()
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    filas, _ = itin.construir_itinerario(datos)
    _guardar_itinerario(conn, conf_no, datos["nombre_bienvenida"], filas, editado=0)
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/reservas/{conf_no}/itinerario/incorporar")
def incorporar_cambios_itinerario(conf_no: str, user: dict = Depends(current_user)):
    """Agrega al itinerario editado lo que la reserva trae de nuevo, conservando
    todas las ediciones manuales que recepción ya había hecho."""
    auth.requiere_escritura(user)
    conn = get_connection()
    fila = conn.execute("SELECT * FROM itinerario WHERE conf_no = ?", (conf_no,)).fetchone()
    datos = itin.datos_de_reserva(conn, conf_no)
    if not fila or not datos:
        conn.close()
        raise HTTPException(status_code=404, detail="No encontrado")
    guardadas = _json.loads(dict(fila)["filas_json"])
    actuales, _ = itin.construir_itinerario(datos)
    faltantes = itin.detectar_faltantes(guardadas, actuales)
    combinadas = itin.incorporar_faltantes(guardadas, faltantes)
    _guardar_itinerario(conn, conf_no, dict(fila)["nombre_bienvenida"], combinadas,
                        editado=1, aviso=None)
    conn.execute("UPDATE alerta SET resuelto = 1 WHERE tipo='ITINERARIO_DESACTUALIZADO' "
                 "AND mensaje LIKE ?", (f"%{conf_no}%",))
    conn.commit()
    conn.close()
    return {"status": "ok", "incorporadas": len(faltantes)}


@app.get("/api/reservas/{conf_no}/itinerario/pdf")
def descargar_itinerario(conf_no: str, user: dict = Depends(current_user)):
    conn = get_connection()
    fila = conn.execute("SELECT * FROM itinerario WHERE conf_no = ?", (conf_no,)).fetchone()
    datos = itin.datos_de_reserva(conn, conf_no)
    conn.close()
    if not datos:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    if fila:
        d = dict(fila)
        buf = itin.generar_pdf_de_filas(d["nombre_bienvenida"] or datos["nombre_bienvenida"],
                                        _json.loads(d["filas_json"]), d.get("idioma") or "en")
    else:
        buf = itin.generar_pdf(datos)
    nombre = (datos["nombre_bienvenida"] or conf_no).replace(" ", "_").replace("&", "y")
    return Response(content=buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Itinerary_{nombre}.pdf"'})


@app.get("/api/itinerarios/estados")
def estados_itinerarios(desde: str = None, hasta: str = None, user: dict = Depends(current_user)):
    """Estado del itinerario de cada reserva, para pintarlo en la lista de Reservas."""
    conn = get_connection()
    q = "SELECT conf_no, editado, aviso_cambios, idioma FROM itinerario"
    filas = {r["conf_no"]: dict(r) for r in conn.execute(q).fetchall()}
    conn.close()
    return filas


import qr_huesped as qrh
from fastapi.responses import HTMLResponse


def _itinerario_de_habitacion(conn, ruta):
    """Resuelve el enlace público y devuelve (reserva, filas, nombre, idioma).

    Lanza 404 si el enlace no es válido. Lo comparten la página del huésped y la
    descarga de su PDF, para que ambas muestren exactamente lo mismo.
    """
    room_no = qrh.resolver_habitacion(conn, ruta)
    if room_no is None:
        raise HTTPException(status_code=404, detail="Enlace no válido")
    reserva = qrh.ocupante_actual(conn, room_no)
    filas, nombre, idioma_pag = [], "", "en"
    if reserva:
        it = conn.execute("SELECT * FROM itinerario WHERE conf_no = ?",
                          (reserva["conf_no"],)).fetchone()
        if it:
            d = dict(it)
            filas = _json.loads(d["filas_json"])
            nombre = d["nombre_bienvenida"] or ""
            idioma_pag = d.get("idioma") or "en"
        else:
            datos = itin.datos_de_reserva(conn, reserva["conf_no"])
            if datos:
                filas, _ = itin.construir_itinerario(datos)
                nombre = datos["nombre_bienvenida"]
    return reserva, filas, nombre, idioma_pag


@app.get("/i/{ruta}", response_class=HTMLResponse)
def itinerario_publico(ruta: str):
    """Página que ve el huésped al escanear el QR de su habitación.

    NO requiere iniciar sesión: es la única parte pública del sistema, y solo
    muestra el itinerario de quien ocupa esa habitación hoy — ningún otro dato.

    `ruta` es el número de habitación (`05`), o `05-a1b2c3d4` si está activada la
    opción de enlaces con código. El itinerario se arma en el momento, así que
    siempre refleja lo que hay ahora mismo en el sistema.
    """
    conn = get_connection()
    try:
        reserva, filas, nombre, idioma_pag = _itinerario_de_habitacion(conn, ruta)
    finally:
        conn.close()
    import catalogo_itinerario as _cat
    html = qrh.pagina_huesped_html(
        reserva, filas, nombre, _cat.HORARIOS_LODGE, _cat.WHATSAPP_RECEPCION,
        # El enlace es relativo a esta página, así que /i/05 y /i/05-a1b2c3d4
        # llevan cada uno a su propio PDF sin tener que repetir la ruta.
        enlace_pdf="itinerary.pdf" if (reserva and filas) else None,
        idioma=idioma_pag)
    return HTMLResponse(content=html)


@app.get("/i/{ruta}/itinerary.pdf")
def itinerario_publico_pdf(ruta: str):
    """El itinerario del huésped en PDF, con el formato oficial del lodge.

    Es el botón de descarga de la página anterior. Se genera en el momento, así que
    siempre coincide con lo que muestra la página."""
    conn = get_connection()
    try:
        reserva, filas, nombre, idioma_pag = _itinerario_de_habitacion(conn, ruta)
    finally:
        conn.close()
    if not reserva or not filas:
        raise HTTPException(status_code=404, detail="No hay itinerario para esta habitación")
    buf = itin.generar_pdf_de_filas(nombre, filas, idioma_pag)
    return Response(content=buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="itinerary.pdf"'})


@app.get("/api/qr/estado")
def qr_estado(fecha: str = None, filtro: str = "todas",
              user: dict = Depends(current_user)):
    """Qué vería hoy cada habitación al escanear su código QR.

    Permite revisar por fecha qué habitaciones entran, salen o están ocupadas, y
    detectar las que quedarían sin itinerario que mostrar.

    filtro: 'todas' | 'movimiento' (entran o salen ese día) | 'sin_itinerario'
    """
    conn = get_connection()
    cfg = qrh.cargar_config()
    hoy = fecha or datetime.date.today().isoformat()
    y, m, d = hoy.split("-")
    dd = f"{d}-{m}-{y[2:]}"

    detalle = []
    for room in cfg.get("habitaciones", []):
        r = qrh.ocupante_actual(conn, room, hoy)
        # Movimiento de esa habitación en la fecha consultada. Se distingue el caso
        # de una llegada futura: si la habitación está vacía ese día, el sistema
        # muestra la próxima reserva, y decir "en casa" sería falso.
        movimiento = None
        if r:
            if r["arr_date"] == dd:
                movimiento = "ENTRA"
            elif r["dep_date"] == dd:
                movimiento = "SALE"
            elif sql_fecha_py(r["arr_date"]) > hoy:
                movimiento = "PROXIMO"
            else:
                movimiento = "EN_CASA"
        detalle.append({
            "room_no": room,
            "url": qrh.url_habitacion(conn, room, cfg.get("base_url")),
            "huesped": r["nombre_principal"] if r else None,
            "conf_no": r["conf_no"] if r else None,
            "arr_date": r["arr_date"] if r else None,
            "dep_date": r["dep_date"] if r else None,
            "movimiento": movimiento,
        })
    conn.close()

    con_huesped = [x for x in detalle if x["huesped"]]
    if filtro == "movimiento":
        mostrados = [x for x in detalle if x["movimiento"] in ("ENTRA", "SALE")]
    elif filtro == "sin_itinerario":
        mostrados = [x for x in detalle if not x["huesped"]]
    else:
        mostrados = detalle

    return {
        "configurado": qrh.esta_configurado(),
        "base_url": cfg.get("base_url", ""),
        "enlaces_con_codigo": bool(cfg.get("enlaces_con_codigo")),
        "habitaciones": cfg.get("habitaciones", []),
        "fecha": hoy,
        "filtro": filtro,
        "detalle": mostrados,
        "resumen": {
            "total": len(detalle),
            "con_huesped": len(con_huesped),
            "sin_ocupante": len(detalle) - len(con_huesped),
        },
    }


@app.post("/api/qr/config")
async def qr_config(payload: dict, user: dict = Depends(current_user)):
    auth.requiere_escritura(user)
    cfg = qrh.cargar_config()
    if "base_url" in payload:
        cfg["base_url"] = (payload["base_url"] or "").strip().rstrip("/")
    if "enlaces_con_codigo" in payload:
        cfg["enlaces_con_codigo"] = bool(payload["enlaces_con_codigo"])
    if "habitaciones" in payload:
        cfg["habitaciones"] = [str(h).strip() for h in payload["habitaciones"] if str(h).strip()]
    qrh.guardar_config(cfg)
    return {"status": "ok", "configurado": qrh.esta_configurado(), **cfg}


@app.get("/api/qr/hoja")
def qr_hoja(user: dict = Depends(current_user)):
    """Hoja imprimible con el QR de cada habitación. Se imprime una sola vez:
    el enlace de cada habitación no cambia nunca."""
    cfg = qrh.cargar_config()
    if not cfg.get("base_url"):
        raise HTTPException(status_code=400,
                            detail="Primero configura la dirección del sistema")
    conn = get_connection()
    pares = [(room, qrh.url_habitacion(conn, room, cfg.get("base_url")))
             for room in cfg.get("habitaciones", [])]
    conn.close()
    buf = qrh.hoja_qr_pdf_urls(pares)
    return Response(content=buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="Codigos_QR_habitaciones.pdf"'})


@app.get("/api/buscar")
def buscar(q: str, user: dict = Depends(current_user)):
    """Busca por nombre de huésped, número de habitación o número de reserva.
    Pensado para el mostrador: se escribe cualquier dato y aparece la reserva."""
    termino = (q or "").strip()
    # Se permite 1 carácter solo si es un número (para buscar habitación 5, 7...);
    # para texto se piden 2 para no devolver media lista.
    if len(termino) < 2 and not termino.isdigit():
        return {"resultados": [], "mensaje": "Escribe al menos 2 caracteres"}

    conn = get_connection()
    like = f"%{termino}%"
    # Las habitaciones se guardan con cero adelante ("05"), pero el usuario puede
    # escribir "5" o "05". Se comparan ambas formas.
    es_numero = termino.strip().isdigit()
    num_hab = termino.strip().zfill(2) if es_numero else termino.strip()
    # Se ordena por relevancia: primero la habitación exacta, luego el nombre del
    # titular, después los acompañantes y por último el número de reserva. Sin esto,
    # buscar "26" devolvía reservas cuyo número contenía 26 antes que la habitación 26.
    filas = conn.execute(
        f"""SELECT DISTINCT r.conf_no, r.room_no, r.nombre_principal, r.arr_date, r.dep_date,
                   r.adl, r.chl, r.res_status, r.punto_entrada, r.punto_salida,
                   CASE
                     WHEN r.room_no = ? THEN 1
                     WHEN r.nombre_principal LIKE ? COLLATE NOCASE THEN 2
                     WHEN EXISTS (SELECT 1 FROM huesped h2 WHERE h2.conf_no = r.conf_no
                                  AND h2.nombre_completo LIKE ? COLLATE NOCASE) THEN 3
                     ELSE 4
                   END AS relevancia
            FROM reserva r
            LEFT JOIN huesped h ON h.conf_no = r.conf_no
            WHERE r.nombre_principal LIKE ? COLLATE NOCASE
               OR h.nombre_completo LIKE ? COLLATE NOCASE
               OR r.conf_no LIKE ?
               OR r.room_no = ?
            ORDER BY relevancia, {sql_fecha('r.arr_date')} DESC
            LIMIT 40""",
        (num_hab, like, like, like, like, like, num_hab),
    ).fetchall()

    hoy = datetime.date.today()
    resultados = []
    for f in filas:
        d = dict(f)
        acompanantes = [dict(x)["nombre_completo"] for x in conn.execute(
            "SELECT nombre_completo FROM huesped WHERE conf_no = ?", (d["conf_no"],))]
        tours = conn.execute(
            "SELECT COUNT(*) c FROM tour_asignado WHERE conf_no = ?", (d["conf_no"],)
        ).fetchone()["c"]

        # Estado respecto a hoy, para ubicar rápido de qué reserva se trata
        def a_fecha(dd):
            try:
                p = dd.split("-")
                return datetime.date(2000 + int(p[2]), int(p[1]), int(p[0]))
            except (ValueError, AttributeError, IndexError):
                return None
        llega, sale = a_fecha(d["arr_date"]), a_fecha(d["dep_date"])
        if d["res_status"] == "CANCELADA":
            estado = "Cancelada"
        elif sale and sale < hoy:
            estado = "Ya salió"
        elif llega and llega > hoy:
            estado = "Por ingresar"
        elif llega == hoy:
            estado = "Entra hoy"
        elif sale == hoy:
            estado = "Sale hoy"
        else:
            estado = "En casa"

        resultados.append({**d, "pax": d["adl"] + d["chl"], "tours": tours,
                           "acompanantes": acompanantes, "estado_estadia": estado})
    conn.close()
    return {"resultados": resultados, "total": len(resultados)}


@app.get("/api/agenda/conflictos")
def agenda_conflictos(fecha: str = None, user: dict = Depends(current_user)):
    """Guías o botes asignados a dos salidas que coinciden en horario."""
    return {"conflictos": detectar_conflictos_asignacion(fecha)}


@app.get("/api/agenda/disponibilidad")
def agenda_disponibilidad(fecha: str, tour_codigo: str = None, excluir_id: int = None,
                          user: dict = Depends(current_user)):
    """Quién está libre y quién ocupado en el horario de ese tour, para asignar sin
    tener que revisarlo mentalmente."""
    conn = get_connection()
    horario = (None, None)
    if tour_codigo:
        t = conn.execute(
            "SELECT horario_inicio, horario_fin FROM tour_catalogo WHERE codigo = ?",
            (tour_codigo,)).fetchone()
        if t:
            horario = (t["horario_inicio"], t["horario_fin"])
    todos_guias = [dict(g)["nombre"] for g in conn.execute(
        "SELECT nombre FROM guia WHERE activo = 1 ORDER BY nombre")]
    todos_botes = [dict(b)["nombre"] for b in conn.execute(
        "SELECT nombre FROM bote WHERE activo = 1 AND gestionado_por_hotel = 1 ORDER BY nombre")]
    conn.close()

    ocupados = guias_ocupados(fecha, horario[0], horario[1], excluir_id)
    return {
        "fecha": fecha, "tour_codigo": tour_codigo,
        "horario": f"{horario[0] or '?'}–{horario[1] or '?'}",
        "guias_libres": [g for g in todos_guias if g not in ocupados["guias_ocupados"]],
        "guias_ocupados": ocupados["guias_ocupados"],
        "botes_libres": [b for b in todos_botes if b not in ocupados["botes_ocupados"]],
        "botes_ocupados": ocupados["botes_ocupados"],
    }


@app.get("/api/pendientes-manana")
def pendientes_manana(fecha: str = None, user: dict = Depends(current_user)):
    """Lo que falta asignar para la operación del día siguiente. Se cuenta solo el día
    relevante, no el mes: '3 tours de mañana sin guía' es útil, '74 del mes' es ruido."""
    objetivo = fecha or (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    conn = get_connection()
    filas = [dict(r) for r in conn.execute(
        """SELECT ta.id, ta.tour_codigo, ta.grupo_operativo, ta.guia_nombre, ta.bote_nombre,
                  ta.pax, tc.horario_inicio, r.room_no, r.nombre_principal
           FROM tour_asignado ta
           JOIN reserva r ON r.conf_no = ta.conf_no
           LEFT JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
           WHERE ta.fecha = ? AND r.res_status != 'CANCELADA'
           ORDER BY tc.horario_inicio""", (objetivo,)).fetchall()]
    conn.close()

    # Se agrupa por salida (tour + grupo), que es la unidad que lleva guía y bote
    salidas = {}
    for f in filas:
        k = (f["tour_codigo"], f["grupo_operativo"])
        if k not in salidas:
            salidas[k] = {"tour_codigo": f["tour_codigo"], "grupo": f["grupo_operativo"],
                          "horario": f["horario_inicio"], "guia": f["guia_nombre"],
                          "bote": f["bote_nombre"], "pax": 0, "habitaciones": []}
        salidas[k]["pax"] += f["pax"] or 0
        salidas[k]["habitaciones"].append(f["room_no"])
    lista = list(salidas.values())
    return {
        "fecha": objetivo,
        "salidas": lista,
        "total_salidas": len(lista),
        "sin_guia": [s for s in lista if not s["guia"]],
        "sin_bote": [s for s in lista if not s["bote"]],
        "conflictos": detectar_conflictos_asignacion(objetivo),
    }


_resource_dir = os.environ.get("HOTEL_RESOURCE_DIR")
if _resource_dir:
    frontend_dir = os.path.join(_resource_dir, "frontend")
else:
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
