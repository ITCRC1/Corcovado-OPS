"""La ocupación del lodge: cuántas habitaciones y cuánta gente, día por día.

POR QUÉ ESTÁ APARTE. Esta cuenta vivía DENTRO del endpoint `/api/ocupacion`, y ahora la
necesita también Proveeduría: el pedido sugerido depende de cuánta gente viene, y es
justo lo único que la hoja de cálculo no podía saber —ahí la ocupación es un número
escrito a mano en `INVENTARIO_GENERAL!C1`—.

Copiarla habría sido la quinta vez en este sistema que una regla se escribe dos veces: ya
pasó con el muelle, con la hora del Claro, con la casilla NOTAS y con el BT. Y aquí la
consecuencia sería peor de lo normal: la pantalla de Analítica diría una ocupación y el
pedido de bodega se calcularía con otra, sin que nada avisara.

LA REGLA QUE IMPORTA, y que ya estaba resuelta: el CUARTO DE GUÍAS no se vende, así que no
cuenta para el porcentaje. Con 31 ocupados sobre 30 vendibles el informe pasaba del 100%
sin que nadie hubiera vendido de más. El guía SÍ cuenta en el pax —duerme y come aquí—,
que es lo que mide la otra cifra.

(informe.py tiene todavía su propia versión de esta cuenta, para el informe del periodo.
Queda anotado: si alguien la toca, lo que vale es esto.)
"""
import datetime

import habitaciones as _habs

DIAS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _a_fecha(ddmmyy):
    try:
        d, m, y = ddmmyy.split("-")
        return datetime.date(2000 + int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def habitaciones_vendibles():
    """Cuántas habitaciones tiene el lodge para vender. 30 si no hay nada configurado."""
    import publicador as _pub
    return len(_pub.cargar_config().get("habitaciones") or []) or 30


def por_dia(conn, desde, hasta, total_habitaciones=None):
    """Una fila por día: habitaciones ocupadas, pax, quién entra y quién sale.

    Las fechas de cada reserva se convierten UNA vez y no una por cada día del rango:
    sobre 780 reservas, tres meses hacían 140.000 conversiones de texto a fecha, todas
    repetidas.
    """
    total = total_habitaciones or habitaciones_vendibles()
    reservas = [dict(r) for r in conn.execute(
        """SELECT room_no, arr_date, dep_date, adl, chl FROM reserva
           WHERE res_status != 'CANCELADA'""").fetchall()]

    preparadas = []
    for r in reservas:
        llega = _a_fecha(r["arr_date"])
        if not llega:
            continue
        preparadas.append((llega, _a_fecha(r["dep_date"]), r["room_no"],
                           (r["adl"] or 0) + (r["chl"] or 0)))

    inicio = datetime.date.fromisoformat(desde)
    fin = datetime.date.fromisoformat(hasta)
    dias, dia = [], inicio
    while dia <= fin:
        cuartos, pax, entran, salen = set(), 0, 0, 0
        for llega, sale, room_no, personas in preparadas:
            # Ocupada la noche que el huésped duerme ahí: desde su llegada hasta el día
            # antes de su salida.
            if llega <= dia and (sale is None or dia < sale):
                cuartos.add(room_no)
                pax += personas
            if llega == dia:
                entran += 1
            if sale == dia:
                salen += 1
        cuartos = _habs.solo_las_que_se_venden(cuartos)
        dias.append({
            "fecha": dia.isoformat(),
            "dia_semana": DIAS_ES[dia.weekday()],
            "habitaciones": len(cuartos),
            "pax": pax,
            "entran": entran,
            "salen": salen,
            "porcentaje": round(100 * len(cuartos) / total) if total else 0,
        })
        dia += datetime.timedelta(days=1)
    return dias, total


def fraccion(conn, desde, hasta):
    """La ocupación media del periodo como número de 0 a 1.

    Es lo que necesita el pedido sugerido: la hoja interpola el mínimo y el máximo de
    cada producto con un factor de ocupación, y este es ese factor — solo que medido y no
    escrito a mano.

    SE TOPA EN 1. Un fin de semana con el lodge lleno y un cuarto de guías de más daría
    1,03 y el pedido saldría un 3% más alto por una habitación que no se vende; el tope
    es el mismo que ya tiene la hoja (`MIN(1, …)`).
    """
    dias, total = por_dia(conn, desde, hasta)
    if not dias or not total:
        return 0.0
    ocupadas = sum(d["habitaciones"] for d in dias)
    return max(0.0, min(1.0, ocupadas / (total * len(dias))))
