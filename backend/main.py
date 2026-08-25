from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from init_db import get_connection
import os
import sys
import secrets
import tempfile
import datetime

sys.path.insert(0, os.path.dirname(__file__))
from importer import build_review_batch
from loader import load_batch as _load_batch
from validations import (validar_todos_los_tours, validar_tour_asignado,
                         detectar_conflictos_asignacion, guias_ocupados)
import auth

app = FastAPI(title="Sistema de Operación Hotelera - Sierpe/Drake")

# El sistema sirve su propia pantalla desde esta misma dirección (ver el app.mount del
# final), así que el navegador nunca hace una petición de origen cruzado y no hace falta
# permitir ninguno. Antes estaba en "*", que le daba permiso a cualquier página de
# internet para llamar a esta API con la sesión del usuario abierta.
#
# Solo se abre si HOTEL_CORS_ORIGINS lo pide, separando las direcciones por coma. Hace
# falta únicamente si algún día la pantalla se sirve desde otro dominio.
_origenes = [o.strip() for o in (os.environ.get("HOTEL_CORS_ORIGINS") or "").split(",") if o.strip()]
if _origenes:
    app.add_middleware(CORSMiddleware, allow_origins=_origenes,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/salud")
def salud():
    """Comprobación de estado para el servidor donde está instalado el sistema.

    No pide usuario ni contraseña: es la dirección que consulta la plataforma para
    saber si el programa quedó bien levantado después de un despliegue. Si falla,
    la plataforma da por mala la versión nueva y no la publica.

    Se abre la base de datos a propósito: si el programa responde pero no puede
    leer el disco, no está sano y es mejor que el despliegue se detenga.
    """
    try:
        c = get_connection()
        reservas = c.execute("SELECT COUNT(*) n FROM reserva").fetchone()["n"]
        c.close()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Base de datos no disponible: {e}")
    return {"estado": "ok", "reservas": reservas}


# Crear usuarios por defecto la primera vez que arranca el sistema
_auth_conn = get_connection()
auth.seed_default_users(_auth_conn)
_auth_conn.close()


def current_user(authorization: str = Header(None)):
    return auth.get_current_user(authorization, get_connection)


def exige(*pantallas, escribir=False):
    """Dependencia que exige permiso sobre una pantalla concreta.

    El permiso queda declarado en la firma del endpoint, a la vista, en vez de
    escondido en una línea del cuerpo. Se usa así:

        def reservas(..., user: dict = Depends(exige("reservas"))):
        def asignar(..., user: dict = Depends(exige("agenda", escribir=True))):

    Antes de esto, casi todas las escrituras preguntaban solo por el ROL del usuario
    ("¿es recepción o gerencia?"), así que la configuración por pantalla no se
    aplicaba: a un usuario con solo lectura en Agenda se le ocultaba el botón, pero el
    servidor le aceptaba igual el cambio. Y casi todas las lecturas se conformaban con
    tener sesión, así que cualquiera podía leer los datos de los huéspedes.

    Con varias pantallas alcanza con tener permiso en una: es para los datos que
    consulta más de una pantalla, como el catálogo de guías y botes.
    """
    def dependencia(user: dict = Depends(current_user)):
        if not auth.puede_alguna(user, pantallas, escribir=escribir):
            donde = " o ".join(pantallas)
            raise HTTPException(
                status_code=403,
                detail=(f"Tu usuario no tiene permiso para {'modificar' if escribir else 'ver'} "
                        f"{donde}."))
        return user
    return dependencia


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
async def login(payload: dict):
    conn = get_connection()
    # El nombre de usuario se compara sin distinguir mayúsculas y sin espacios de más:
    # en el celular el teclado escribe la primera letra en mayúscula por su cuenta, y
    # el ingreso fallaba con un "usuario o contraseña incorrectos" que no explicaba nada.
    # La contraseña sí distingue mayúsculas, como corresponde.
    usuario = (payload.get("username") or "").strip()
    user = conn.execute(
        "SELECT * FROM usuario WHERE username = ? COLLATE NOCASE AND activo = 1", (usuario,)
    ).fetchone()
    if not user or not auth.verify_password(payload.get("password", ""), user["password_hash"], user["salt"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = auth.crear_sesion(conn, user["id"])
    conn.close()
    return {"token": token, "username": user["username"],
            "nombre_completo": user["nombre_completo"], "rol": user["rol"],
            "permisos": auth.permisos_de(dict(user))}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {**user, "permisos": auth.permisos_de(user)}


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
def dashboard(fecha: str, user: dict = Depends(exige("dashboard"))):
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
def resumen_operacion(fecha: str, user: dict = Depends(exige("resumen"))):
    """Resumen del día pensado para que cada departamento encuentre lo suyo:
    recepción, cocina, housekeeping, guías y transporte."""
    conn = get_connection()
    dd = ddmmyy(fecha)
    yy = yymmdd(fecha)

    def lista(sql, params=()):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # --- Movimiento de huéspedes ---
    # conf_no viene en las cuatro listas para poder marcar en pantalla las habitaciones
    # que viajan juntas (grupos de agencia y familias con varios cuartos).
    ingresos = lista(
        """SELECT conf_no, room_no, nombre_principal, adl, chl, arr_time, punto_entrada,
                  vuelo_entrada, hora_vuelo_entrada, nota_ingreso, notas_libres
           FROM reserva WHERE arr_date = ? AND res_status != 'CANCELADA'
           ORDER BY CAST(room_no AS INTEGER)""", (dd,))
    salidas = lista(
        """SELECT conf_no, room_no, nombre_principal, adl, chl, punto_salida,
                  vuelo_salida, hora_vuelo_salida, nota_salida
           FROM reserva WHERE dep_date = ? AND res_status != 'CANCELADA'
           ORDER BY CAST(room_no AS INTEGER)""", (dd,))
    desayunos = lista(
        f"""SELECT conf_no, room_no, nombre_principal, adl, chl FROM reserva
           WHERE res_status != 'CANCELADA' AND (
             dep_date = ? OR ({sql_fecha('arr_date')} < ?
                              AND (dep_date IS NULL OR {sql_fecha('dep_date')} >= ?)))
           ORDER BY CAST(room_no AS INTEGER)""", (dd, yy, yy))
    en_casa = lista(
        f"""SELECT conf_no, room_no, nombre_principal, adl, chl, punto_salida, dep_date FROM reserva
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

    # Se calcula ANTES de cerrar la conexión. Estaba dentro del return, o sea después
    # del close, así que siempre fallaba por dentro y _restaurantes_resumen devolvía
    # None sin decir nada: el bloque de restaurantes de esta hoja nunca se mostró.
    resumen_restaurantes = _restaurantes_resumen(conn, fecha)

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
        "restaurantes": resumen_restaurantes,
    }


def _restaurantes_resumen(conn, fecha):
    """Totales de cada restaurante, para que cocina los vea en la hoja del día."""
    try:
        import restaurantes as rest
        return rest.resumen_dia(conn, fecha)
    except Exception:
        return None


@app.get("/api/ocupacion")
def ocupacion(desde: str, hasta: str, user: dict = Depends(exige("analitica"))):
    """Ocupación día por día: cuántas habitaciones ocupadas, pax y porcentaje.
    Útil para gerencia, y para ver de un vistazo los días fuertes del mes."""
    conn = get_connection()
    # Se importa aquí para no depender del orden de las importaciones del archivo
    import publicador as _pub
    total_habitaciones = len(_pub.cargar_config().get("habitaciones") or []) or 30

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
def reservas(desde: str = None, hasta: str = None, user: dict = Depends(exige("reservas"))):
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
def entradas_sinac(desde: str = None, hasta: str = None, user: dict = Depends(exige("sinac"))):
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
    # corresponde cada entrada. La relación sale de los tours asignados, y quién
    # corresponde a quién lo define sinac.py: la limpieza de entradas sin dueño usa esa
    # misma regla, y cuando no coincidían sobrevivían entradas fantasma.
    import sinac
    conn = get_connection()
    hoy = datetime.date.today()
    for r in rows:
        reservas_rel = sinac.reservas_de(conn, r["tour_codigo"], r["fecha"], r["conf_entrada"])
        r["reservas"] = reservas_rel
        r["pax_huespedes"] = sum(x["adl"] + x["chl"] for x in reservas_rel)
        # Sin reservas detrás, la fila salía con todo en cero y sin habitación, y parecía
        # una entrada por comprar. Se marca para que la pantalla explique qué pasó: son
        # entradas ya compradas que se quedaron sin nadie porque el tour cambió de fecha
        # o la reserva se canceló. Las pendientes en esa situación ya se limpian al
        # importar, así que aquí solo deberían quedar compradas.
        r["huerfana"] = not reservas_rel

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
def agenda(fecha: str = None, desde: str = None, hasta: str = None, user: dict = Depends(exige("agenda"))):
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


def _hora_traslado(fila, es_entrada):
    """Hora a la que de verdad se mueve el huésped, según lo ya dispuesto por el lodge.

    La pantalla de Transporte mostraba solo lo que viniera escrito en el PDF, y por eso
    salían tantas líneas en blanco: por Sierpe el bote sale a la misma hora todos los
    días y el PDF no la repite, y en las salidas por Sierpe la hora estaba fija en "—".

    El orden es: lo que diga el PDF manda; si no dice nada, se aplica la regla del punto.

      · Sierpe → horario fijo del bote (llegada y salida).
      · Drake, llegada → la hora del vuelo; sin vuelo no se puede saber.
      · Drake, salida  → el bote, calculado hacia atrás desde el vuelo, la misma cuenta
        que se le imprime al huésped en su itinerario.

    Devuelve (hora, origen). El origen sirve para que recepción distinga de un vistazo
    lo confirmado de lo que sigue pendiente de verdad.
    """
    import catalogo_itinerario as cat
    import itinerario as _itin

    if es_entrada:
        punto = (fila.get("punto_entrada") or "").lower()
        if fila.get("hora_vuelo_entrada"):
            return fila["hora_vuelo_entrada"], "del PDF"
        if fila.get("arr_time"):
            return fila["arr_time"], "del PDF"
        if punto == "sierpe":
            return cat.SIERPE_BOTE_LLEGADA, "horario fijo de Sierpe"
        if punto == "drake":
            return None, "falta la hora del vuelo"
        return None, "falta el punto"

    punto = (fila.get("punto_salida") or "").lower()
    if punto == "sierpe":
        return cat.SIERPE_SALIDA["bote"], "horario fijo de Sierpe"
    if punto == "drake":
        logistica = _itin.calcular_logistica_salida(fila.get("hora_vuelo_salida"))
        if logistica:
            return logistica["bote"], "calculado del vuelo"
        return None, "falta la hora del vuelo"
    return None, "falta el punto"


@app.get("/api/transporte")
def transporte(fecha: str = None, desde: str = None, hasta: str = None, user: dict = Depends(exige("transporte"))):
    conn = get_connection()
    if fecha:
        cond_e, params_e = "arr_date = ?", (ddmmyy(fecha),)
        cond_s, params_s = "dep_date = ?", (ddmmyy(fecha),)
    else:
        cond_e = f"{sql_fecha('arr_date')} BETWEEN ? AND ?"
        cond_s = f"{sql_fecha('dep_date')} BETWEEN ? AND ?"
        params_e = params_s = (yymmdd(desde), yymmdd(hasta))
    entradas = conn.execute(
        # conf_no viene para poder marcar en pantalla si esa habitación viaja con otras.
        f"SELECT conf_no, room_no, nombre_principal, punto_entrada, arr_time, hora_vuelo_entrada, adl, chl, arr_date FROM reserva WHERE {cond_e}",
        params_e,
    ).fetchall()
    salidas = conn.execute(
        f"SELECT conf_no, room_no, nombre_principal, punto_salida, hora_vuelo_salida, adl, chl, dep_date FROM reserva WHERE {cond_s}",
        params_s,
    ).fetchall()
    conn.close()

    def con_hora(filas, es_entrada):
        salida = []
        for f in filas:
            d = dict(f)
            d["hora_efectiva"], d["hora_origen"] = _hora_traslado(d, es_entrada)
            salida.append(d)
        return salida

    return {
        "entradas": con_hora(entradas, True),
        "salidas": con_hora(salidas, False),
    }


@app.get("/api/analitica")
def analitica(desde: str, hasta: str, user: dict = Depends(exige("analitica"))):
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
def analitica_bote_detalle(nombre: str, desde: str, hasta: str, user: dict = Depends(exige("analitica"))):
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
def analitica_guia_detalle(nombre: str, desde: str, hasta: str, user: dict = Depends(exige("analitica"))):
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
def catalogo(todos: bool = False, user: dict = Depends(exige("agenda", "catalogo", "amenidades", "restaurantes"))):
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
async def pdf_preview(file: UploadFile = File(...), user: dict = Depends(exige("importar", escribir=True))):
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
async def pdf_confirm(file: UploadFile = File(...), user: dict = Depends(exige("importar", escribir=True))):
    batch = _analizar_pdf(await file.read(), file.filename)
    _load_batch(batch, fuente_pdf=file.filename)
    alertas = validar_todos_los_tours()

    # La publicación del sitio de itinerarios se hace en segundo plano: genera 30
    # páginas con sus PDF y sube unos 13 MB, y con el internet del lodge eso puede
    # tardar minutos. No tiene por qué hacer esperar a recepción.
    publicacion = _publicar_en_segundo_plano()

    return {"status": "ok", "reservas_cargadas": len(batch["reservas"]),
            "alertas_generadas": len(alertas), "publicacion": publicacion}


@app.get("/api/buzon/estado")
def buzon_estado(user: dict = Depends(exige("importar"))):
    """Cómo viene funcionando la importación automática del reporte del PMS."""
    import buzon_pdf
    conn = get_connection()
    try:
        return buzon_pdf.resumen_estado(conn)
    finally:
        conn.close()


@app.post("/api/buzon/revisar")
def buzon_revisar(user: dict = Depends(exige("importar", escribir=True))):
    """Mira el buzón ahora mismo, sin esperar el turno del reloj.

    Sirve para el día que alguien reenvía el reporte a mano y quiere verlo ya.
    """
    import buzon_pdf
    if not buzon_pdf.configurado():
        raise HTTPException(
            status_code=400,
            detail=("El buzón no está configurado. Hacen falta las variables "
                    "BUZON_HOST, BUZON_USUARIO y BUZON_CLAVE en el servidor."))
    return buzon_pdf.revisar(get_connection)


def _revisar_buzon_periodicamente():
    """Revisa el buzón cada cierto tiempo, en segundo plano.

    Se arranca solo si el buzón está configurado, así que en una instalación sin correo
    —o en las pruebas— este hilo no existe y nadie intenta conectarse a nada.
    """
    import time as _time
    import buzon_pdf
    # Un momento de gracia al arrancar: primero que el servidor quede sirviendo.
    _time.sleep(45)
    while True:
        try:
            r = buzon_pdf.revisar(get_connection)
            if r.get("importados"):
                print(f"[buzón] {r['importados']} reporte(s) importado(s), "
                      f"{r['reservas']} reservas")
            elif r.get("fallo"):
                print(f"[buzón] no se pudo revisar: {r['fallo']}")
        except Exception as e:
            # Una caída del correo no puede tumbar el sistema: se reintenta después.
            print(f"[buzón] error inesperado: {type(e).__name__}: {e}")
        _time.sleep(buzon_pdf.MINUTOS * 60)


def _arrancar_buzon():
    import threading
    import buzon_pdf
    if not buzon_pdf.configurado():
        return
    threading.Thread(target=_revisar_buzon_periodicamente, daemon=True).start()
    print(f"[buzón] importación automática activa: {buzon_pdf.USUARIO} "
          f"cada {buzon_pdf.MINUTOS} min")


_arrancar_buzon()


def _publicar_en_segundo_plano():
    """Se mantiene por compatibilidad: ya no hay nada que publicar.

    El itinerario se arma en el instante en que el huésped escanea su código, así que
    cualquier cambio —editar el itinerario, mover un tour, cambiar de restaurante—
    se ve de inmediato sin que nadie tenga que hacer nada.
    """
    return "en vivo"
@app.post("/api/tours/agenda/{tour_id}/asignar")
def asignar_guia_bote(tour_id: int, guia: str = None, bote: str = None, user: dict = Depends(exige("agenda", escribir=True))):
    """Asigna guía y bote a una salida.

    Se distingue "no me mandaron el dato" de "lo dejaron en Sin asignar":

      · parámetro ausente  → el valor anterior se queda como estaba.
      · parámetro vacío    → se borra la asignación y queda en NULL.

    Lo segundo antes no se podía: se usaba COALESCE, así que elegir "Sin asignar" no
    hacía nada y no había forma de dejar una salida sin guía desde la pantalla. Tiene
    que quedar en NULL y no en texto vacío, porque los avisos de "sin guía" y "sin
    bote" buscan justamente NULL y una cadena vacía se les escaparía.
    """
    conn = get_connection()
    anterior = conn.execute(
        "SELECT fecha, guia_nombre, bote_nombre FROM tour_asignado WHERE id = ?", (tour_id,)
    ).fetchone()

    campos, valores = [], []
    nuevo_guia = None if guia is None else (guia.strip() or None)
    nuevo_bote = None if bote is None else (bote.strip() or None)
    if guia is not None:
        campos.append("guia_nombre = ?")
        valores.append(nuevo_guia)
    if bote is not None:
        campos.append("bote_nombre = ?")
        valores.append(nuevo_bote)
    if campos:
        conn.execute(
            f"UPDATE tour_asignado SET {', '.join(campos)} WHERE id = ?",
            (*valores, tour_id),
        )

    cambio_ultimo_momento = None
    if anterior:
        hoy = datetime.date.today().isoformat()
        # Quitar un guía el mismo día del tour también es un cambio de último momento.
        cambio_real = ((guia is not None and nuevo_guia != anterior["guia_nombre"])
                       or (bote is not None and nuevo_bote != anterior["bote_nombre"]))
        if anterior["fecha"] == hoy and cambio_real:
            conn.execute("UPDATE tour_asignado SET es_cambio_ultimo_momento = 1 WHERE id = ?", (tour_id,))
            info = conn.execute(
                """SELECT ta.tour_codigo, r.nombre_principal, r.room_no FROM tour_asignado ta
                   JOIN reserva r ON r.conf_no = ta.conf_no WHERE ta.id = ?""",
                (tour_id,),
            ).fetchone()
            guia_final = nuevo_guia if guia is not None else anterior["guia_nombre"]
            bote_final = nuevo_bote if bote is not None else anterior["bote_nombre"]
            mensaje = (
                f"Cambio de último momento: {info['tour_codigo']} de {info['nombre_principal']} "
                f"(hab. {info['room_no']}) modificado el mismo día del tour "
                f"(guía: {anterior['guia_nombre'] or '—'} → {guia_final or 'sin asignar'}, "
                f"bote: {anterior['bote_nombre'] or '—'} → {bote_final or 'sin asignar'})."
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
def confirmar_grupo(grupo_id: int, confirmar: bool = True, user: dict = Depends(exige("reservas", escribir=True))):
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
def confirmar_guia_reserva(conf_no: str, guia: str = None, confirmar: bool = True, user: dict = Depends(exige("reservas", escribir=True))):
    conn = get_connection()
    if guia:
        conn.execute("UPDATE reserva SET guia_sugerido = ?, guia_confirmado = 1 WHERE conf_no = ?", (guia, conf_no))
    elif confirmar:
        conn.execute("UPDATE reserva SET guia_confirmado = 1 WHERE conf_no = ?", (conf_no,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/entradas-sinac/{entrada_id}/marcar")
def marcar_entrada(entrada_id: int, estado: str = "COMPRADA", user: dict = Depends(exige("sinac", escribir=True))):
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
_startup_conn.commit()
_startup_conn.close()
sync_engine.iniciar_sync_en_segundo_plano()


@app.get("/api/cambios")
def cambios(user: dict = Depends(current_user)):
    """Huella del estado de los datos compartidos, para refrescar solo si hace falta.

    Todas las computadoras la piden cada pocos segundos, así que tiene que ser barata:
    son agregados sobre índices o sobre tablas chicas, nunca un recorrido de reserva
    ni de tour_asignado. Si el número que devuelve cambió, alguien tocó algo.

    Lo que se vigila:
      · sync_log      — reservas, tours, guías, botes, grupos y entradas SINAC, que ya
                        anotan cada cambio ahí por medio de los disparadores.
      · itinerario    — su fecha de actualización cambia con cada edición.
      · amenidad_tarea, alerta — cuántas hay y cuántas están cerradas.
      · restaurantes  — cambios de mesa y horas de cena; la hora se suma en número
                        ('19:30' → 1930) porque cambiar la hora no cambia el total.
      · entrada_sinac — cuántas hay. Hace falta contarlas aparte porque los disparadores
                        solo anotan altas y modificaciones: cuando el sistema BORRA
                        entradas duplicadas o sin dueño, sync_log no se mueve y una
                        pantalla abierta seguía mostrando filas que ya no existen.
    """
    conn = get_connection()
    fila = conn.execute("""
        SELECT (SELECT COALESCE(MAX(id), 0)              FROM sync_log)            AS operacion,
               (SELECT COUNT(*)                          FROM itinerario)          AS itinerarios,
               (SELECT COALESCE(MAX(actualizado_en), '') FROM itinerario)          AS itin_fecha,
               (SELECT COUNT(*)                          FROM amenidad_tarea)      AS amenidades,
               (SELECT COUNT(*) FROM amenidad_tarea WHERE estado = 'HECHA')        AS amen_hechas,
               (SELECT COALESCE(MAX(id), 0)              FROM alerta)              AS alertas,
               (SELECT COUNT(*) FROM alerta WHERE resuelto = 0)                    AS alertas_abiertas,
               (SELECT COUNT(*)                          FROM restaurante_cambio)  AS rest_cambios,
               (SELECT COUNT(*)                          FROM restaurante_hora)    AS rest_horas,
               (SELECT COALESCE(SUM(CAST(REPLACE(COALESCE(hora, '0'), ':', '') AS INTEGER)), 0)
                  FROM restaurante_hora)                                           AS rest_suma,
               (SELECT COUNT(*)                          FROM entrada_sinac)        AS sinac
    """).fetchone()
    conn.close()
    # Se manda también la versión del sistema, aprovechando que esta consulta ya va y
    # viene cada pocos segundos: así la pantalla puede avisar sola si el servidor fue
    # actualizado mientras alguien tenía el sistema abierto.
    return {"version": "-".join(str(v) for v in tuple(fila)),
            "version_sistema": _version_sistema()["version"]}


@app.get("/api/sync/estado")
def sync_estado(user: dict = Depends(exige("usuarios"))):
    conn = get_connection()
    pendientes = conn.execute("SELECT COUNT(*) c FROM sync_log WHERE sincronizado = 0").fetchone()["c"]
    ultimo = conn.execute("SELECT MAX(creado_en) t FROM sync_log WHERE sincronizado = 1").fetchone()["t"]
    conn.close()
    cfg = sync_engine.load_sync_config()
    return {"estacion": cfg.get("nombre_estacion"), "peer_configurado": bool(cfg.get("peer_url")),
            "cambios_pendientes": pendientes, "ultimo_cambio_sincronizado": ultimo}


@app.post("/api/sync/ahora")
def sync_ahora(user: dict = Depends(exige("usuarios", escribir=True))):
    return sync_engine.intentar_sincronizar()


# Estas dos las llama la OTRA estación, no una persona, así que no llevan sesión de
# usuario: se identifican con el secreto compartido HOTEL_SYNC_TOKEN. Sin esa variable
# quedan apagadas (404), que es lo correcto ahora que el sistema corre en un solo
# servidor: si no hay una segunda estación con la que sincronizar, no hay motivo para
# tener abierta una puerta que lee todas las reservas y escribe en la base.
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


# ---------- OPERA CLOUD (traer reservas del PMS automáticamente) ----------
import opera_sync

# El hilo arranca siempre, esté o no configurado: por dentro comprueba en cada vuelta
# y no hace nada hasta que haya credenciales y alguien lo encienda desde la pantalla.
# Así encender la sincronización no obliga a reiniciar el servidor.
opera_sync.iniciar_en_segundo_plano()


@app.get("/api/opera/estado")
def opera_estado(user: dict = Depends(exige("importar"))):
    """Cómo va la conexión con Opera, para la pantalla de Importar."""
    cfg = opera_sync.cargar_config()
    desde, hasta = opera_sync.ventana(cfg)
    faltan = opera_sync.faltantes()
    return {
        "configurado": not faltan,
        # Solo los NOMBRES de las variables que faltan. Los valores son credenciales y
        # no salen nunca del servidor, ni siquiera hacia un usuario con permisos.
        "faltantes": faltan,
        "config": cfg,
        "ventana": {"desde": desde, "hasta": hasta},
        "ultimo_ciclo": opera_sync.estado(),
    }


@app.post("/api/opera/config")
async def opera_config(payload: dict, user: dict = Depends(exige("importar", escribir=True))):
    """Guarda el encendido, el intervalo y la ventana de fechas.

    Se aceptan solo esos cuatro valores y se acotan a rangos con sentido: esta
    configuración la escribe una pantalla, y un intervalo de 0 minutos o una ventana de
    tres años dejarían al sistema llamando a Opera sin parar.
    """
    cfg = opera_sync.cargar_config()
    if "activo" in payload:
        cfg["activo"] = bool(payload["activo"])
    for clave, minimo, maximo in (("intervalo_minutos", 5, 1440),
                                  ("dias_atras", 0, 30),
                                  ("dias_adelante", 1, 365)):
        if clave in payload:
            try:
                cfg[clave] = max(minimo, min(int(payload[clave]), maximo))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{clave} debe ser un número")
    opera_sync.guardar_config(cfg)
    return {"guardado": True, "config": cfg}


@app.post("/api/opera/probar")
def opera_probar(user: dict = Depends(exige("importar", escribir=True))):
    """Comprueba que las credenciales sirven, sin tocar la base."""
    import opera_cloud
    faltan = opera_sync.faltantes()
    if faltan:
        return {"estado": "SIN_CONFIGURAR", "faltantes": faltan}
    try:
        opera_cloud.obtener_token()
    except Exception as e:
        return {"estado": "FALLO", "detalle": str(e).splitlines()[0][:300]}
    return {"estado": "OK", "esquema": opera_cloud.tipo_de_autenticacion()}


@app.post("/api/opera/vista-previa")
def opera_vista_previa(user: dict = Depends(exige("importar", escribir=True))):
    """Descarga de Opera y muestra qué llegaría, SIN escribir nada en la base.

    Es el paso previo obligado antes de encender la sincronización: los nombres de
    campo de OHIP cambian entre instalaciones, y así se ve si algún dato viene vacío
    antes de que entre a la operación.
    """
    return opera_sync.sincronizar(cargar=False)


@app.post("/api/opera/sincronizar")
def opera_sincronizar(user: dict = Depends(exige("importar", escribir=True))):
    """Ejecuta un ciclo completo ahora mismo, sin esperar al automático."""
    return opera_sync.sincronizar(cargar=True)


@app.get("/api/usuarios")
def listar_usuarios(user: dict = Depends(exige("usuarios"))):
    conn = get_connection()
    # permisos_json hace falta aquí: es lo que la pantalla de Usuarios muestra y lo que
    # el editor de permisos precarga. Sin esta columna el editor abría siempre en
    # blanco y, al guardar, borraba lo que el usuario ya tenía configurado.
    rows = conn.execute(
        """SELECT id, username, nombre_completo, rol, activo, permisos_json
           FROM usuario ORDER BY username""").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/usuarios")
async def crear_usuario(payload: dict, user: dict = Depends(exige("usuarios", escribir=True))):
    if payload.get("rol") not in ("recepcion", "gerencia", "staff"):
        raise HTTPException(status_code=400, detail="Rol inválido")
    conn = get_connection()
    # Sin distinguir mayúsculas: si existiera "transporte" y se creara "Transporte", el
    # ingreso —que ya no distingue— no sabría a cuál de los dos corresponde.
    existe = conn.execute("SELECT id FROM usuario WHERE username = ? COLLATE NOCASE",
                          (payload["username"],)).fetchone()
    if existe:
        conn.close()
        raise HTTPException(status_code=400, detail="Ese nombre de usuario ya existe")
    h, salt = auth.hash_password(payload["password"])
    # Los permisos por pantalla se pueden fijar al crear, sin tener que abrir después el
    # editor: es cuando se sabe para qué se está creando el usuario.
    permisos = auth.limpiar_permisos(payload.get("permisos"))
    if not permisos:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=("Marca al menos una pantalla en los permisos, o aplica un perfil. "
                    "El rol por sí solo no da acceso a nada."))
    conn.execute(
        """INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol, permisos_json)
           VALUES (?,?,?,?,?,?)""",
        (payload["username"], h, salt, payload["nombre_completo"], payload["rol"],
         _json.dumps(permisos, ensure_ascii=False) if permisos else None),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "permisos": permisos}


@app.post("/api/usuarios/{usuario_id}/estado")
def cambiar_estado_usuario(usuario_id: int, activo: bool, user: dict = Depends(exige("usuarios", escribir=True))):
    if usuario_id == user["id"] and not activo:
        raise HTTPException(status_code=400,
                            detail="No puedes desactivar tu propia cuenta.")
    conn = get_connection()
    conn.execute("UPDATE usuario SET activo = ? WHERE id = ?", (1 if activo else 0, usuario_id))
    # Desactivar al último que administra usuarios deja el sistema igual de trabado que
    # quitarle el permiso, así que se comprueba lo mismo.
    _sin_dejar_sin_administrador(conn, "desactivar este usuario")
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/usuarios/{usuario_id}/password")
async def cambiar_password_usuario(usuario_id: int, payload: dict, user: dict = Depends(exige("usuarios", escribir=True))):
    h, salt = auth.hash_password(payload["password"])
    conn = get_connection()
    conn.execute("UPDATE usuario SET password_hash = ?, salt = ? WHERE id = ?", (h, salt, usuario_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/guia")
async def crear_guia(payload: dict, user: dict = Depends(exige("catalogo", escribir=True))):
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
def estado_guia(nombre: str, activo: bool, user: dict = Depends(exige("catalogo", escribir=True))):
    conn = get_connection()
    conn.execute("UPDATE guia SET activo = ? WHERE nombre = ?", (1 if activo else 0, nombre))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/bote")
async def crear_bote(payload: dict, user: dict = Depends(exige("catalogo", escribir=True))):
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
def estado_bote(nombre: str, activo: bool, user: dict = Depends(exige("catalogo", escribir=True))):
    conn = get_connection()
    conn.execute("UPDATE bote SET activo = ? WHERE nombre = ?", (1 if activo else 0, nombre))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/catalogo/tour")
async def crear_tour(payload: dict, user: dict = Depends(exige("catalogo", escribir=True))):
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
def estado_tour(codigo: str, activo: bool, user: dict = Depends(exige("catalogo", escribir=True))):
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
def export_reservas(desde: str = None, hasta: str = None, formato: str = "xlsx", user: dict = Depends(exige("reservas"))):
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
def export_agenda(fecha: str = None, desde: str = None, hasta: str = None, formato: str = "xlsx", user: dict = Depends(exige("agenda"))):
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
def export_transporte(fecha: str = None, desde: str = None, hasta: str = None, formato: str = "xlsx", user: dict = Depends(exige("transporte"))):
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
    # La hora sale de la misma regla que usa la pantalla: por Sierpe el horario fijo
    # del bote, por Drake el vuelo (o el bote calculado desde él). Antes el Excel
    # copiaba solo lo escrito en el PDF y salía en blanco en casi todas las salidas.
    for r in entradas:
        r["fecha"] = r["arr_date"]; r["punto"] = r["punto_entrada"]
        hora, origen = _hora_traslado(r, True)
        r["hora"], r["hora_origen"] = hora or "—", origen
    for r in salidas:
        r["fecha"] = r["dep_date"]; r["punto"] = r["punto_salida"]
        hora, origen = _hora_traslado(r, False)
        r["hora"], r["hora_origen"] = hora or "—", origen
    rows = entradas + salidas
    columns = [("fecha", "Fecha"), ("tipo", "Tipo"), ("room_no", "Hab."), ("nombre_principal", "Huésped"),
               ("punto", "Punto"), ("hora", "Hora"), ("hora_origen", "Según"), ("pax", "Pax")]
    titulo = "Transporte — Corcovado Wilderness Lodge"
    subt = fecha or f"{desde} a {hasta}"
    buf = exports.to_xlsx(columns, rows, titulo) if formato == "xlsx" else exports.to_pdf(columns, rows, titulo, subt)
    return export_response(buf, "transporte", formato)


@app.get("/api/export/entradas-sinac")
def export_entradas(desde: str = None, hasta: str = None, formato: str = "xlsx", user: dict = Depends(exige("sinac"))):
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
def export_resumen(fecha: str, formato: str = "xlsx", user: dict = Depends(exige("resumen"))):
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


@app.get("/api/export/restaurantes")
def export_restaurantes(fecha: str, formato: str = "xlsx", user: dict = Depends(exige("restaurantes"))):
    """Distribución del día para imprimir o pasarle a cocina y al salonero."""
    import restaurantes as rest
    conn = get_connection()
    try:
        d = rest.distribuir(conn, fecha)
    finally:
        conn.close()

    filas = []
    for comida, bloque in (("Almuerzo", d["almuerzo"]), ("Cena", d["cena"])):
        for restaurante, clave in ((rest.TERRA, "terra_kitchen"), (rest.BOSQUE, "bar_el_bosque")):
            for x in bloque[clave]:
                filas.append({
                    "comida": comida, "restaurante": restaurante,
                    "room_no": x["room_no"], "nombre": x["nombre"], "pax": x["pax"],
                    "tipo": "Entra" if x["tipo"] == "ENTRA" else "En casa",
                    "noche": f"{x.get('noche_estadia') or 1} de {x['noches']}",
                    "hora": x.get("hora") or "",
                    "nota": x.get("fijo") or ("cambio manual" if x.get("manual") else ""),
                })
    columns = [
        ("comida", "Comida"), ("restaurante", "Restaurante"), ("room_no", "Hab."),
        ("nombre", "Huésped"), ("pax", "Pax"), ("tipo", "Situación"),
        ("noche", "Noche"), ("hora", "Hora mesa"), ("nota", "Observación"),
    ]
    titulo = "Distribución de restaurantes — Corcovado Wilderness Lodge"
    c = d["cena"]
    subt = (f"{fecha} · Cena: Terra Kitchen {c['pax_tk']} / Bar el Bosque {c['pax_bosque']} "
            f"(diferencia {c['diferencia']}) · Almuerzo: Terra Kitchen "
            f"{d['almuerzo']['pax_tk']} / Bar el Bosque {d['almuerzo']['pax_bosque']}")
    buf = (exports.to_xlsx(columns, filas, titulo) if formato == "xlsx"
           else exports.to_pdf(columns, filas, titulo, subt))
    return export_response(buf, f"restaurantes_{fecha}", formato)


@app.get("/api/export/analitica")
def export_analitica(desde: str, hasta: str, formato: str = "xlsx", user: dict = Depends(exige("analitica"))):
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
def confirmar_transporte(conf_no: str, tipo: str, punto: str, user: dict = Depends(exige("transporte", escribir=True))):
    """Permite a recepción fijar manualmente el punto (Sierpe/Drake) cuando el PDF
    no lo indicaba con claridad."""
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
def transporte_pendientes(user: dict = Depends(exige("transporte"))):
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
def detalle_reserva(conf_no: str, user: dict = Depends(exige("reservas"))):
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
def cambiar_grupo_operativo(tour_id: int, grupo: str, user: dict = Depends(exige("agenda", escribir=True))):
    """Mueve un tour a otro grupo operativo (A, B, C...). Sirve para dividir un tour
    grande en grupos separados, cada uno con su propio guía y bote."""
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
def grupos_disponibles(fecha: str, tour_codigo: str, user: dict = Depends(exige("agenda"))):
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
async def crear_amenidad_manual(payload: dict, user: dict = Depends(exige("amenidades", escribir=True))):
    """Permite a recepción/gerencia agregar un requerimiento del huésped que no venía
    en el PDF: alergias reportadas por teléfono, preferencias, peticiones especiales."""
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
def eliminar_amenidad(amenidad_id: int, user: dict = Depends(exige("amenidades", escribir=True))):
    """Solo se pueden eliminar los requerimientos agregados manualmente; los detectados
    del PDF se vuelven a generar en cada importación."""
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
                      user: dict = Depends(exige("amenidades"))):
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
def cambiar_estado_amenidad(amenidad_id: int, estado: str, user: dict = Depends(exige("amenidades", escribir=True))):
    if estado not in ("PENDIENTE", "HECHA"):
        raise HTTPException(status_code=400, detail="Estado inválido")
    conn = get_connection()
    conn.execute("UPDATE amenidad_tarea SET estado = ? WHERE id = ?", (estado, amenidad_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/api/export/amenidades")
def export_amenidades(desde: str = None, hasta: str = None, formato: str = "xlsx",
                      user: dict = Depends(exige("amenidades"))):
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
def cambiar_fecha_tour(tour_id: int, fecha: str, user: dict = Depends(exige("agenda", escribir=True))):
    """Cambia la fecha de un tour. La fecha que trae la reserva es una intención, pero
    la operación real puede moverla (clima, mareas, cupos, decisión del huésped).

    Al mover un tour se actualiza todo lo que dependa de esa fecha:
      · la entrada al SINAC, cuyo plazo de compra se recalcula
      · el itinerario del huésped, para que reciba la fecha correcta
      · las validaciones de capacidad y los conflictos de horario de ambos días
    """
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

    _publicar_en_segundo_plano()
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
def obtener_itinerario(conf_no: str, user: dict = Depends(exige("reservas"))):
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
async def guardar_itinerario(conf_no: str, payload: dict, user: dict = Depends(exige("reservas", escribir=True))):
    conn = get_connection()
    _guardar_itinerario(conn, conf_no, payload.get("nombre_bienvenida"),
                        payload.get("filas", []), editado=1, aviso=None,
                        idioma=payload.get("idioma"))
    conn.commit()
    conn.close()
    # El huésped debe ver el cambio de inmediato al escanear su código
    _publicar_en_segundo_plano()
    return {"status": "ok"}


@app.post("/api/reservas/{conf_no}/itinerario/regenerar")
def regenerar_itinerario(conf_no: str, user: dict = Depends(exige("reservas", escribir=True))):
    """Descarta las ediciones manuales y vuelve a armarlo desde la reserva."""
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
def incorporar_cambios_itinerario(conf_no: str, user: dict = Depends(exige("reservas", escribir=True))):
    """Agrega al itinerario editado lo que la reserva trae de nuevo, conservando
    todas las ediciones manuales que recepción ya había hecho."""
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
def descargar_itinerario(conf_no: str, user: dict = Depends(exige("reservas"))):
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


@app.get("/api/grupos")
def grupos_del_sistema(user: dict = Depends(exige(
        "dashboard", "reservas", "agenda", "transporte", "amenidades", "restaurantes",
        "resumen", "publicacion"))):
    """Qué reservas viajan juntas, para marcarlo donde se vea la habitación.

    Es informativo: una sola consulta, indexada por número de reserva, que cada pantalla
    pide una vez y usa para poner la etiqueta de grupo en sus filas. Así no hay que
    agregar el dato a cada endpoint, y todas las pantallas dicen lo mismo.

    Alcanza con tener acceso a cualquiera de las pantallas que muestran habitaciones,
    porque son las que ponen la etiqueta. Devuelve nombres de huéspedes, así que no se
    deja con solo tener sesión: alguien con acceso únicamente a Analítica o a Catálogo
    no tiene por qué leer la lista de reservas.
    """
    import grupos as _grupos
    conn = get_connection()
    try:
        return _grupos.resumen(conn)
    finally:
        conn.close()


@app.get("/api/itinerarios/estados")
def estados_itinerarios(desde: str = None, hasta: str = None, user: dict = Depends(exige("reservas"))):
    """Estado del itinerario de cada reserva, para pintarlo en la lista de Reservas."""
    conn = get_connection()
    q = "SELECT conf_no, editado, aviso_cambios, idioma FROM itinerario"
    filas = {r["conf_no"]: dict(r) for r in conn.execute(q).fetchall()}
    conn.close()
    return filas


import qr_huesped as qrh
import publicador as pub
from fastapi.responses import HTMLResponse


def _pagina_huesped(room_no: str):
    """Arma la página del huésped de esa habitación.

    Quien puede verla se decide en las rutas de abajo; aquí solo se construye.
    """
    conn = get_connection()
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
    # Los restaurantes se calculan aquí mismo, así el huésped ve la distribución
    # vigente aunque haya cambiado hoy. Por eso no van en el PDF impreso.
    comidas = pub.comidas_de(conn, reserva, idioma_pag) if reserva else None
    conn.close()
    import catalogo_itinerario as _cat
    html = qrh.pagina_huesped_html(reserva, filas, nombre,
                                   _cat.HORARIOS_LODGE, _cat.WHATSAPP_RECEPCION,
                                   room_no=room_no, idioma=idioma_pag, comidas=comidas)
    return HTMLResponse(content=html)


@app.get("/i/{room_no}", response_class=HTMLResponse)
def itinerario_publico(room_no: str):
    """Página que ve el huésped al escanear el QR de su habitación.

    NO requiere iniciar sesión: es la única parte pública del sistema, y solo
    muestra el itinerario de quien ocupa esa habitación hoy — ningún otro dato.

    Si están activados los enlaces con código, esta dirección corta deja de servir:
    de nada valdría el código secreto si bastara con quitarlo de la dirección para
    ver el itinerario de cualquier otro cuarto.
    """
    if pub.cargar_config().get("enlaces_con_codigo"):
        raise HTTPException(status_code=404, detail="Enlace no válido")
    return _pagina_huesped(room_no)


@app.get("/i/{room_no}/{token}", response_class=HTMLResponse)
def itinerario_publico_con_codigo(room_no: str, token: str):
    """Misma página, cuando están activados los enlaces con código secreto.

    Sirve para que un huésped no pueda adivinar el enlace de otra habitación
    cambiando el número en la dirección.
    """
    conn = get_connection()
    esperado = pub.token_habitacion(conn, room_no)
    conn.close()
    if not secrets.compare_digest(token, esperado):
        raise HTTPException(status_code=404, detail="Enlace no válido")
    return _pagina_huesped(room_no)


@app.get("/api/qr/config")
def qr_config(user: dict = Depends(exige("publicacion"))):
    cfg = qrh.cargar_config()
    conn = get_connection()
    habs = [dict(r)["room_no"] for r in conn.execute(
        "SELECT DISTINCT room_no FROM reserva WHERE room_no IS NOT NULL "
        "ORDER BY CAST(room_no AS INTEGER)")]
    conn.close()
    if not cfg.get("habitaciones"):
        cfg["habitaciones"] = habs
    cfg["habitaciones_detectadas"] = habs
    return cfg


@app.post("/api/qr/config")
async def guardar_qr_config(payload: dict, user: dict = Depends(exige("publicacion", escribir=True))):
    cfg = qrh.cargar_config()
    if "base_url" in payload:
        cfg["base_url"] = (payload["base_url"] or "").strip()
    if "habitaciones" in payload:
        cfg["habitaciones"] = [str(h).strip() for h in payload["habitaciones"] if str(h).strip()]
    qrh.guardar_config(cfg)
    return {"status": "ok", **cfg}


@app.get("/api/qr/hoja")
def qr_hoja(user: dict = Depends(exige("publicacion"))):
    """PDF con el QR de cada habitación, para imprimir una sola vez."""
    cfg = qrh.cargar_config()
    if not cfg.get("base_url"):
        raise HTTPException(status_code=400,
                            detail="Primero configura la dirección base de los códigos QR")
    conn = get_connection()
    habs = cfg.get("habitaciones") or [dict(r)["room_no"] for r in conn.execute(
        "SELECT DISTINCT room_no FROM reserva WHERE room_no IS NOT NULL "
        "ORDER BY CAST(room_no AS INTEGER)")]
    # Las direcciones las arma publicador, que es quien sabe si los enlaces llevan
    # código secreto; si no, el QR impreso apuntaría a una página que no existe.
    pares = [(h, pub.url_habitacion(conn, h)) for h in habs]
    conn.close()
    buf = qrh.hoja_qr_pdf_urls(pares)
    return Response(content=buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="Codigos_QR_habitaciones.pdf"'})


@app.get("/api/qr/estado")
def qr_estado(user: dict = Depends(exige("publicacion"))):
    """Muestra qué huésped vería hoy cada habitación al escanear su QR."""
    cfg = qrh.cargar_config()
    conn = get_connection()
    habs = cfg.get("habitaciones") or [dict(r)["room_no"] for r in conn.execute(
        "SELECT DISTINCT room_no FROM reserva WHERE room_no IS NOT NULL "
        "ORDER BY CAST(room_no AS INTEGER)")]
    resultado = []
    for h in habs:
        r = qrh.ocupante_actual(conn, h)
        resultado.append({
            "room_no": h,
            "url": pub.url_habitacion(conn, h),
            "huesped": r["nombre_principal"] if r else None,
            "conf_no": r["conf_no"] if r else None,
            "arr_date": r["arr_date"] if r else None,
            "dep_date": r["dep_date"] if r else None,
        })
    conn.close()
    return {"base_url": cfg.get("base_url", ""), "habitaciones": resultado}


@app.get("/api/publicacion/estado")
def publicacion_estado(fecha: str = None, filtro: str = "todas",
                       user: dict = Depends(exige("publicacion"))):
    """Qué muestra el código QR de cada habitación.

    Ya no hay estados de publicación: la página se arma en el momento en que el
    huésped escanea su código, así que siempre refleja lo que hay en el sistema.
    Esta lista sirve para revisar y para ver los movimientos de una fecha.

    filtro: 'todas' | 'movimiento' (entran o salen ese día) | 'con_huesped'
    """
    conn = get_connection()
    cfg = pub.cargar_config()
    por_hab = {h["room_no"]: h for h in pub.estado_por_habitacion(conn)}
    hoy = fecha or datetime.date.today().isoformat()
    y, m, d = hoy.split("-")
    dd = f"{d}-{m}-{y[2:]}"

    detalle = []
    for room in cfg.get("habitaciones") or []:
        h = por_hab.get(room, {})
        r = qrh.ocupante_actual(conn, room, hoy)
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
            "room_no": room, "url": h.get("url", ""),
            "huesped": r["nombre_principal"] if r else None,
            "conf_no": r["conf_no"] if r else None,
            "arr_date": r["arr_date"] if r else None,
            "dep_date": r["dep_date"] if r else None,
            "movimiento": movimiento,
            "idioma": h.get("idioma", "en"), "editado": h.get("editado", False),
        })

    if filtro == "movimiento":
        detalle = [x for x in detalle if x["movimiento"] in ("ENTRA", "SALE")]
    elif filtro == "con_huesped":
        detalle = [x for x in detalle if x["huesped"]]

    conn.close()
    return {
        "fecha": hoy, "filtro": filtro,
        "base_url": cfg.get("base_url", ""),
        "habitaciones": cfg.get("habitaciones") or [],
        "enlaces_con_codigo": bool(cfg.get("enlaces_con_codigo")),
        "configurado": pub.esta_configurado(),
        "detalle": detalle,
        "resumen": {"habitaciones": len(por_hab),
                    "con_huesped": sum(1 for x in por_hab.values() if x["huesped"]),
                    "sin_ocupante": sum(1 for x in por_hab.values() if not x["huesped"])},
    }


@app.post("/api/publicacion/config")
async def publicacion_config(payload: dict, user: dict = Depends(current_user)):
    """Dirección por la que se alcanza el sistema y habitaciones del hotel.

    Ya no hace falta cuenta externa, Site ID ni token de acceso: los itinerarios los
    sirve este mismo programa cuando el huésped escanea su código.
    """
    auth.requiere_permiso(user, "publicacion")
    # Se pasa tal cual lo que llegue: lo que el formulario no mande se queda como
    # estaba. Antes un guardado incompleto borraba la lista de habitaciones.
    cfg = pub.guardar_config({
        "base_url": payload.get("base_url"),
        "habitaciones": payload.get("habitaciones"),
        "enlaces_con_codigo": payload.get("enlaces_con_codigo"),
    })
    return {"status": "ok", "configurado": pub.esta_configurado(),
            "habitaciones": cfg.get("habitaciones")}


@app.get("/api/publicacion/qr")
def publicacion_qr(user: dict = Depends(exige("publicacion"))):
    """Hoja imprimible con el QR de cada habitación. Se imprime una sola vez:
    el enlace de cada habitación no cambia nunca."""
    conn = get_connection()
    cfg = pub.cargar_config()
    if not cfg.get("base_url"):
        conn.close()
        raise HTTPException(status_code=400, detail="Primero configura la dirección del sitio")
    pares = [(room, pub.url_habitacion(conn, room)) for room in cfg.get("habitaciones", [])]
    conn.close()
    buf = qrh.hoja_qr_pdf_urls(pares)
    return Response(content=buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="Codigos_QR_habitaciones.pdf"'})


@app.get("/api/publicacion/vista-previa/{room_no}", response_class=HTMLResponse)
def publicacion_vista_previa(room_no: str, user: dict = Depends(exige("publicacion"))):
    """Permite a recepción ver exactamente lo que verá el huésped de esa habitación.

    Se salta el código secreto a propósito: quien mira ya inició sesión en el sistema.
    """
    return _pagina_huesped(room_no)


@app.get("/api/buscar")
def buscar(q: str, user: dict = Depends(exige("reservas"))):
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
def agenda_conflictos(fecha: str = None, user: dict = Depends(exige("dashboard", "agenda"))):
    """Guías o botes asignados a dos salidas que coinciden en horario."""
    return {"conflictos": detectar_conflictos_asignacion(fecha)}


@app.get("/api/agenda/disponibilidad")
def agenda_disponibilidad(fecha: str, tour_codigo: str = None, excluir_id: int = None,
                          user: dict = Depends(exige("agenda"))):
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
def pendientes_manana(fecha: str = None, user: dict = Depends(exige("dashboard"))):
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


# ---------------------------------------------------------------------------
# Restaurantes
# ---------------------------------------------------------------------------

def _administradores_activos(conn):
    """Cuántos usuarios activos pueden administrar usuarios.

    Si llegara a cero, nadie podría volver a dar permisos ni crear cuentas, y habría
    que entrar a la base de datos a mano. Por eso todo cambio que pueda dejarlo en cero
    se deshace antes de confirmarse.
    """
    filas = conn.execute("SELECT rol, permisos_json FROM usuario WHERE activo = 1").fetchall()
    return sum(1 for f in filas if auth.puede(dict(f), "usuarios", escribir=True))


def _sin_dejar_sin_administrador(conn, que_paso):
    """Deshace el cambio si dejó al sistema sin nadie que administre usuarios."""
    if _administradores_activos(conn) == 0:
        conn.rollback()
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=(f"No se puede {que_paso}: quedaría sin ningún usuario capaz de "
                    "administrar usuarios, y nadie podría volver a dar permisos."))


def _perfiles_guardados(conn):
    filas = conn.execute(
        "SELECT nombre, permisos_json FROM perfil_permisos ORDER BY nombre").fetchall()
    salida = {}
    for f in filas:
        try:
            salida[f["nombre"]] = _json.loads(f["permisos_json"])
        except (ValueError, TypeError):
            continue
    return salida


@app.get("/api/permisos/catalogo")
def permisos_catalogo(user: dict = Depends(exige("usuarios"))):
    """Pantallas disponibles y perfiles guardados, para la pantalla de Usuarios."""
    conn = get_connection()
    try:
        return {"pantallas": [{"clave": k, "nombre": n} for k, n in auth.PANTALLAS],
                "perfiles": _perfiles_guardados(conn),
                "administradores": _administradores_activos(conn)}
    finally:
        conn.close()


@app.post("/api/permisos/perfiles")
def guardar_perfil(payload: dict, user: dict = Depends(exige("usuarios", escribir=True))):
    """Guarda un perfil de permisos con el nombre que le ponga el hotel.

    Sirve para no marcar trece pantallas cada vez: se arma una combinación una sola vez
    ("Salonero", "Housekeeping") y después se aplica a quien haga falta.
    """
    nombre = (payload.get("nombre") or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Ponle un nombre al perfil")
    if len(nombre) > 40:
        raise HTTPException(status_code=400, detail="El nombre del perfil es muy largo")
    permisos = auth.limpiar_permisos(payload.get("permisos"))
    if not permisos:
        raise HTTPException(status_code=400,
                            detail="El perfil no tiene ninguna pantalla marcada")
    conn = get_connection()
    conn.execute(
        """INSERT INTO perfil_permisos (nombre, permisos_json) VALUES (?,?)
           ON CONFLICT(nombre) DO UPDATE SET permisos_json = excluded.permisos_json""",
        (nombre, _json.dumps(permisos, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return {"status": "ok", "nombre": nombre, "permisos": permisos}


@app.delete("/api/permisos/perfiles/{nombre}")
def borrar_perfil(nombre: str, user: dict = Depends(exige("usuarios", escribir=True))):
    """Borra un perfil. No toca a los usuarios que ya lo tenían aplicado."""
    conn = get_connection()
    conn.execute("DELETE FROM perfil_permisos WHERE nombre = ?", (nombre,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/usuarios/{usuario_id}/editar")
async def editar_usuario(usuario_id: int, payload: dict,
                         user: dict = Depends(exige("usuarios", escribir=True))):
    """Cambia el nombre de usuario, el nombre completo o el rol de una cuenta.

    El rol es solo una etiqueta, así que cambiarlo no altera lo que la persona puede
    hacer: eso está en su rejilla de permisos.
    """
    conn = get_connection()
    actual = conn.execute("SELECT * FROM usuario WHERE id = ?", (usuario_id,)).fetchone()
    if not actual:
        conn.close()
        raise HTTPException(status_code=404, detail="Ese usuario no existe")

    campos, valores = [], []
    if payload.get("username") is not None:
        nuevo = (payload["username"] or "").strip()
        if not nuevo or " " in nuevo:
            conn.close()
            raise HTTPException(status_code=400, detail="El usuario no puede ir vacío ni llevar espacios")
        repetido = conn.execute(
            "SELECT id FROM usuario WHERE username = ? COLLATE NOCASE AND id != ?",
            (nuevo, usuario_id)).fetchone()
        if repetido:
            conn.close()
            raise HTTPException(status_code=400, detail="Ya existe otro usuario con ese nombre")
        campos.append("username = ?")
        valores.append(nuevo)
    if payload.get("nombre_completo") is not None:
        nombre = (payload["nombre_completo"] or "").strip()
        if not nombre:
            conn.close()
            raise HTTPException(status_code=400, detail="El nombre completo no puede ir vacío")
        campos.append("nombre_completo = ?")
        valores.append(nombre)
    if payload.get("rol") is not None:
        if payload["rol"] not in ("recepcion", "gerencia", "staff"):
            conn.close()
            raise HTTPException(status_code=400, detail="Rol inválido")
        campos.append("rol = ?")
        valores.append(payload["rol"])

    if not campos:
        conn.close()
        return {"status": "ok", "sin_cambios": True}

    conn.execute(f"UPDATE usuario SET {', '.join(campos)} WHERE id = ?", (*valores, usuario_id))
    _sin_dejar_sin_administrador(conn, "cambiar este usuario")
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/usuarios/{user_id}/permisos")
def guardar_permisos(user_id: int, payload: dict,
                     user: dict = Depends(exige("usuarios", escribir=True))):
    """Define a qué pantallas entra un usuario y si puede modificar en ellas."""
    limpios = auth.limpiar_permisos(payload.get("permisos"))
    # Quitarse a uno mismo el permiso de administrar usuarios deja la pantalla cerrada
    # en el acto y hay que pedirle a otra persona que lo devuelva. Es un tropiezo fácil
    # y sin ninguna ventaja, así que no se permite.
    if user_id == user["id"] and limpios.get("usuarios") != "escribir":
        raise HTTPException(
            status_code=400,
            detail=("No puedes quitarte a ti mismo el permiso de administrar usuarios. "
                    "Pídele a otra persona con ese permiso que lo haga."))
    conn = get_connection()
    conn.execute("UPDATE usuario SET permisos_json = ? WHERE id = ?",
                 (_json.dumps(limpios, ensure_ascii=False) if limpios else None, user_id))
    _sin_dejar_sin_administrador(conn, "guardar estos permisos")
    conn.commit()
    conn.close()
    return {"status": "ok", "permisos": limpios}


@app.get("/api/restaurantes")
def restaurantes_dia(fecha: str, user: dict = Depends(exige("restaurantes"))):
    """Distribución de almuerzo y cena de esa fecha."""
    import restaurantes as rest
    conn = get_connection()
    try:
        rest.congelar_dias_pasados(conn)
        datos = rest.distribuir(conn, fecha)
    finally:
        conn.close()
    return datos


@app.post("/api/restaurantes/cambiar")
def restaurantes_cambiar(payload: dict, user: dict = Depends(current_user)):
    """Cambia de restaurante a una reserva en una fecha concreta.

    Afecta solo ese día y esa reserva. Se permite aunque el restaurante quede por
    encima de su tope: recepción sabe si la cocina puede absorberlo, pero el
    sistema lo advierte.
    """
    auth.requiere_permiso(user, "restaurantes")
    import restaurantes as rest
    fecha = payload.get("fecha")
    conf_no = payload.get("conf_no")
    comida = (payload.get("comida") or "CENA").upper()
    restaurante = payload.get("restaurante")
    if not (fecha and conf_no and restaurante in (rest.TERRA, rest.BOSQUE)):
        raise HTTPException(status_code=400, detail="Faltan datos o el restaurante no es válido")

    conn = get_connection()
    conn.execute(
        """INSERT INTO restaurante_cambio (fecha, conf_no, comida, restaurante, motivo)
           VALUES (?,?,?,?,?)
           ON CONFLICT(fecha, conf_no, comida) DO UPDATE SET
             restaurante = excluded.restaurante, motivo = excluded.motivo,
             creado_en = datetime('now')""",
        (fecha, conf_no, comida, restaurante, payload.get("motivo") or "solicitud del huésped"))
    conn.commit()
    datos = rest.distribuir(conn, fecha)
    conn.close()

    # El itinerario del huésped cambió, así que se republica el sitio del QR
    _publicar_en_segundo_plano()
    aviso = None
    bloque = datos["cena"] if comida == "CENA" else datos["almuerzo"]
    if restaurante == rest.TERRA and bloque["pax_tk"] > bloque["cap_tk"]:
        aviso = (f"Terra Kitchen queda con {bloque['pax_tk']} pax y su tope es "
                 f"{bloque['cap_tk']}. Avisa a cocina.")
    return {"status": "ok", "distribucion": datos, "aviso_capacidad": aviso}


@app.delete("/api/restaurantes/cambiar")
def restaurantes_quitar_cambio(fecha: str, conf_no: str, comida: str = "CENA",
                               user: dict = Depends(current_user)):
    """Deshace un cambio manual y devuelve la reserva a la asignación automática."""
    auth.requiere_permiso(user, "restaurantes")
    conn = get_connection()
    conn.execute(
        "DELETE FROM restaurante_cambio WHERE fecha=? AND conf_no=? AND comida=?",
        (fecha, conf_no, comida.upper()))
    conn.commit()
    conn.close()
    _publicar_en_segundo_plano()
    return {"status": "ok"}


def _hora_guardada(conn, fecha, conf_no):
    fila = conn.execute("SELECT hora FROM restaurante_hora WHERE fecha=? AND conf_no=?",
                        (fecha, conf_no)).fetchone()
    return (dict(fila)["hora"] or None) if fila else None


def _guardar_hora_mesa(conn, fecha, conf_no, hora):
    """Guarda la hora de una mesa, o la borra si viene vacía.

    Vaciar la casilla en pantalla es quitar la reserva de mesa, así que se borra la
    fila en vez de dejarla en blanco: una hora vacía guardada y una hora sin poner
    tendrían que significar lo mismo, y guardándola ya no se sabría cuál es cuál.
    """
    if hora:
        conn.execute(
            """INSERT INTO restaurante_hora (fecha, conf_no, hora) VALUES (?,?,?)
               ON CONFLICT(fecha, conf_no) DO UPDATE SET hora = excluded.hora""",
            (fecha, conf_no, hora))
    else:
        conn.execute("DELETE FROM restaurante_hora WHERE fecha=? AND conf_no=?",
                     (fecha, conf_no))


@app.post("/api/restaurantes/hora")
def restaurantes_hora(payload: dict, user: dict = Depends(current_user)):
    """Hora reservada de la mesa. La registra el salonero en la mañana.

    Si la reserva viaja en grupo o en familia, la hora se le pone también al resto de
    las habitaciones del grupo que cenan esa noche: el reparto ya las sienta juntas,
    así que ponerle la hora a una y dejar las otras en blanco solo servía para que la
    cocina viera cuatro mesas donde hay una. Borrar la hora se propaga igual.

    Lo único que no se toca es la habitación a la que alguien le puso a mano una hora
    distinta: eso es una excepción deliberada —el abuelo que baja más temprano— y el
    sistema no está para deshacerla sin avisar. Se devuelve en 'excepciones' para que
    la pantalla lo diga y el salonero decida.

    Con 'solo_esta' se guarda únicamente esa habitación. Hace falta porque una mesa
    grande a veces se parte en dos turnos, y si el grupo arrastrara siempre no habría
    forma de darle otra hora a una sola habitación.
    """
    auth.requiere_permiso(user, "restaurantes")
    import restaurantes as rest
    fecha = payload.get("fecha")
    conf_no = payload.get("conf_no")
    hora = (payload.get("hora") or "").strip() or None
    if not (fecha and conf_no):
        raise HTTPException(status_code=400, detail="Faltan la fecha o la reserva")

    conn = get_connection()
    try:
        # La hora que tenía ANTES sirve para saber quién estaba sincronizado con ella:
        # si un compañero la tenía igual, venía siguiendo al grupo y se le actualiza.
        anterior = _hora_guardada(conn, fecha, conf_no)
        _guardar_hora_mesa(conn, fecha, conf_no, hora)

        aplicadas, excepciones = [], []
        companeros = [] if payload.get("solo_esta") else rest.companeros_de_mesa(
            conn, fecha, conf_no)
        for c in companeros:
            suya = _hora_guardada(conn, fecha, c["conf_no"])
            if suya and suya != anterior and suya != hora:
                excepciones.append(dict(c, hora=suya))
                continue
            _guardar_hora_mesa(conn, fecha, c["conf_no"], hora)
            aplicadas.append(c)
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "hora": hora, "grupo": aplicadas, "excepciones": excepciones}


@app.post("/api/restaurantes/cena-privada")
def restaurantes_cena_privada(payload: dict, user: dict = Depends(current_user)):
    """Marca (o desmarca) la noche de una cena privada.

    El PDF avisa que la reserva tiene cena privada pero casi nunca dice el día, así
    que recepción confirma la fecha aquí. Queda fija en Bar el Bosque.
    """
    auth.requiere_permiso(user, "restaurantes")
    conf_no, fecha = payload.get("conf_no"), payload.get("fecha")
    conn = get_connection()
    if payload.get("quitar"):
        conn.execute(
            "UPDATE amenidad_tarea SET fecha = NULL WHERE conf_no = ? AND fecha = ? "
            "AND (amenidad LIKE '%privada%' OR tarea LIKE '%privada%')", (conf_no, fecha))
    else:
        fila = conn.execute(
            "SELECT id FROM amenidad_tarea WHERE conf_no = ? "
            "AND (amenidad LIKE '%privada%' OR tarea LIKE '%privada%') LIMIT 1",
            (conf_no,)).fetchone()
        if fila:
            conn.execute("UPDATE amenidad_tarea SET fecha = ? WHERE id = ?",
                         (fecha, dict(fila)["id"]))
        else:
            # No venía en el PDF: recepción la registra ahora
            conn.execute(
                """INSERT INTO amenidad_tarea (conf_no, amenidad, origen, detalle, tarea,
                                               area_responsable, fecha)
                   VALUES (?,?,'MANUAL',?,?,?,?)""",
                (conf_no, "Cena privada", payload.get("detalle"),
                 "Preparar cena privada", "Cocina", fecha))
    conn.commit()
    conn.close()
    _publicar_en_segundo_plano()
    return {"status": "ok"}


@app.get("/api/restaurantes/regimen")
def restaurantes_regimen(fecha: str = None, desde: str = None, hasta: str = None,
                         user: dict = Depends(exige("restaurantes"))):
    """Quiénes tienen las comidas incluidas y quiénes no, día por día.

    Para un solo día basta con lo que ya devuelve /api/restaurantes; esto existe para
    poder mirar un rango: cuántos huéspedes con pensión completa hay cada día de la
    semana entrante, que es lo que sirve para compras y para planear el servicio.

    Se cuentan los que comen ese día —quien entra y quien está en casa—, igual que el
    reparto. Los que salen no cuentan: el bote se va de madrugada.
    """
    import restaurantes as rest

    hoy = datetime.date.today()
    if fecha:
        inicio = fin = datetime.date.fromisoformat(fecha)
    else:
        inicio = datetime.date.fromisoformat(desde) if desde else hoy
        fin = datetime.date.fromisoformat(hasta) if hasta else inicio
    if fin < inicio:
        inicio, fin = fin, inicio
    # Tope de tres meses: cada día es una lectura aparte y nadie planea más allá.
    TOPE_DIAS = 92
    recortado = (fin - inicio).days + 1 > TOPE_DIAS
    if recortado:
        fin = inicio + datetime.timedelta(days=TOPE_DIAS - 1)

    conn = get_connection()
    try:
        dias, totales = [], {}
        d = inicio
        while d <= fin:
            entradas, en_casa, _ = rest._reservas_del_dia(conn, d)
            categorias = {}
            for r in entradas + en_casa:
                clave = r.get("regimen") or "SIN_DATO"
                categorias.setdefault(clave, []).append({
                    "conf_no": r["conf_no"], "room_no": r["room_no"],
                    "nombre": r["nombre_principal"], "pax": r["pax"],
                    "tipo": r["tipo"],
                })
            resumen = {k: {"habitaciones": len(v), "pax": sum(x["pax"] for x in v)}
                       for k, v in categorias.items()}
            for k, v in resumen.items():
                acum = totales.setdefault(k, {"habitaciones": 0, "pax": 0})
                acum["habitaciones"] += v["habitaciones"]
                acum["pax"] += v["pax"]
            dias.append({"fecha": d.isoformat(), "resumen": resumen,
                         "categorias": categorias})
            d += datetime.timedelta(days=1)
    finally:
        conn.close()

    return {
        "desde": inicio.isoformat(), "hasta": fin.isoformat(),
        "dias": dias,
        # En un rango los totales suman noche-huésped, no personas distintas: alguien
        # que se queda tres noches cuenta tres veces. Es lo que sirve para el servicio.
        "totales": totales,
        "textos": rest.TEXTO_REGIMEN,
        "recortado": recortado,
    }


@app.get("/api/restaurantes/avisos")
def restaurantes_avisos(dias: int = 30, user: dict = Depends(exige("restaurantes"))):
    """Noches futuras que no van a caber o no se van a poder equilibrar."""
    import restaurantes as rest
    conn = get_connection()
    try:
        return {"avisos": rest.avisos_anticipados(conn, dias)}
    finally:
        conn.close()


_resource_dir = os.environ.get("HOTEL_RESOURCE_DIR")
if _resource_dir:
    frontend_dir = os.path.join(_resource_dir, "frontend")
else:
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")

INDEX_PATH = os.path.join(frontend_dir, "index.html")

# ---------------------------------------------------------------------------
# Sello de versión
# ---------------------------------------------------------------------------
# Sirve para responder de un vistazo la pregunta que aparece cada vez que se
# despliega algo: "¿el sistema que estoy viendo ya trae el cambio?". El sello se saca
# de la fecha de los propios archivos, así que no hay que acordarse de subirlo a mano
# ni hace falta un paso de compilación.
#
# Se inyecta ADEMÁS dentro del index.html que se entrega, para que la página sepa con
# qué versión se cargó: si el navegador tiene una copia vieja, el sello de la página y
# el del servidor no coinciden y el propio sistema lo avisa.

def _version_sistema():
    """Fecha del archivo más nuevo entre el frontend y el backend, en UTC.

    La hora se devuelve en ISO para que la muestre el navegador en la hora de quien
    mira, y no en la del servidor (que en Railway va en UTC).
    """
    rutas = [INDEX_PATH] + [os.path.join(os.path.dirname(__file__), f)
                            for f in ("main.py", "restaurantes.py", "publicador.py",
                                      "itinerario.py", "importer.py", "loader.py")]
    reciente = 0.0
    for r in rutas:
        try:
            reciente = max(reciente, os.path.getmtime(r))
        except OSError:
            continue
    sello = datetime.datetime.fromtimestamp(
        reciente, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "")[:7]
    return {"version": sello, "commit": commit}


@app.get("/api/version")
def version():
    """Qué versión tiene el servidor. Sin sesión: la usa la propia pantalla de ingreso."""
    return _version_sistema()


_index_cache = {"version": None, "html": None}


def _index_con_version():
    """El index.html con su sello de versión puesto.

    Se guarda en memoria usando como llave el propio sello, no la fecha del archivo:
    si se despliega un cambio solo del backend, el index no cambia pero el sello sí, y
    con la fecha del archivo como llave se habría seguido entregando la página con el
    sello anterior. El navegador la habría visto siempre en desacuerdo con el servidor
    y habría avisado "versión nueva" sin fin, incluso recién recargada.
    """
    v = _version_sistema()
    if _index_cache["version"] != v["version"]:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            html = f.read()
        marca = f'<meta name="version-sistema" content="{v["version"]}" data-commit="{v["commit"]}">'
        _index_cache["html"] = html.replace("<!--VERSION-->", marca)
        _index_cache["version"] = v["version"]
    return _index_cache["html"]


@app.get("/manifest.webmanifest")
def manifest():
    """Datos de la app para el teléfono: nombre, icono y colores.

    Se sirve desde aquí y no como archivo estático porque el navegador necesita el tipo
    de contenido correcto para ofrecer "Instalar aplicación".
    """
    with open(os.path.join(frontend_dir, "manifest.webmanifest"), "r", encoding="utf-8") as f:
        return Response(content=f.read(), media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def service_worker():
    """El programa que hace que la app abra sin señal.

    Tiene que servirse desde la raíz: un programa de servicio solo controla las
    direcciones que están por debajo de la suya. Y sin caché, o un cambio aquí no
    llegaría nunca a los teléfonos que ya lo tienen instalado.
    """
    with open(os.path.join(frontend_dir, "sw.js"), "r", encoding="utf-8") as f:
        return Response(content=f.read(), media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def index():
    """Entrega la aplicación con el sello de versión dentro.

    Va antes del montaje de archivos estáticos, así que gana sobre él; el resto de
    los archivos (fuentes, fotos, logo) los sigue sirviendo el montaje de abajo.
    """
    return HTMLResponse(content=_index_con_version(),
                        headers={"Cache-Control": "no-cache, must-revalidate"})


class _FrontendSinCache(StaticFiles):
    """Sirve el frontend pidiendo al navegador que revise si hay versión nueva.

    Toda la aplicación es un solo index.html. Si el navegador se lo guarda en caché,
    después de un despliegue se sigue viendo la pantalla vieja y parece que el cambio
    no funcionó — y no hay forma de darse cuenta desde el sistema. Las fuentes y las
    fotos sí se dejan cachear: pesan y casi nunca cambian.
    """

    async def get_response(self, path, scope):
        respuesta = await super().get_response(path, scope)
        es_html = path.endswith((".html", "/")) or path in ("", ".") or \
            (respuesta.headers.get("content-type") or "").startswith("text/html")
        if es_html:
            respuesta.headers["Cache-Control"] = "no-cache, must-revalidate"
        return respuesta


app.mount("/", _FrontendSinCache(directory=frontend_dir, html=True), name="frontend")
