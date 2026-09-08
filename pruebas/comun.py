"""Andamiaje mínimo para las pruebas. Sin dependencias y sin red.

Ninguna prueba habla con Opera. Se le entregan al cargador reservas ya traducidas
—la misma forma que devuelve `opera_mapeo.mapear()`— porque lo que hay que fijar son
las REGLAS de carga, y esas tienen que poder comprobarse sin credenciales, sin
internet y sin depender de qué huéspedes haya hoy en el hotel.

Cada suite corre en su propio proceso con su propia carpeta de datos: ver
correr_todo.py y el porqué que está escrito ahí.
"""
import contextlib
import io
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "backend"))


# ---------------------------------------------------------------------------
# Comprobaciones
# ---------------------------------------------------------------------------

class Cuenta:
    """Lleva la cuenta de comprobaciones. Se imprime el fallo, no se corta la suite.

    Cortar en el primer fallo esconde los demás, y cuando algo se rompe de verdad lo
    que se quiere ver es TODO lo que se rompió: dice mucho más de la causa que el
    primer síntoma solo.
    """

    def __init__(self):
        self.ok = 0
        self.fallos = []

    def igual(self, obtenido, esperado, que):
        if obtenido == esperado:
            self.ok += 1
        else:
            self.fallos.append(f"{que}\n      esperaba: {esperado!r}\n      obtuvo:   {obtenido!r}")

    def cierto(self, condicion, que):
        self.igual(bool(condicion), True, que)

    def resumen(self, nombre):
        total = self.ok + len(self.fallos)
        if self.fallos:
            print(f"\n  {len(self.fallos)} FALLOS en {nombre}:")
            for f in self.fallos:
                print(f"    · {f}")
        print(f"\n  {nombre}: {self.ok}/{total} comprobaciones")
        return not self.fallos


# ---------------------------------------------------------------------------
# La base
# ---------------------------------------------------------------------------

def base_limpia():
    """Borra la base y la recrea con el catálogo. Devuelve una conexión nueva.

    Se llama al empezar CADA prueba de la suite. Sin esto, una prueba que deja una
    reserva cancelada hace fallar a la siguiente por un motivo que no tiene nada que
    ver, y se pierde media hora buscando una regresión que no existe.
    """
    import init_db
    with contextlib.redirect_stdout(io.StringIO()):
        init_db.init_db(reset=True)
    return init_db.get_connection()


def conexion():
    import init_db
    return init_db.get_connection()


# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------

def reserva(conf_no, room_no, arr_date, dep_date, estado="POR INGRESAR",
            adl=2, chl=0, marca="2026-09-01T10:00:00Z", **extra):
    """Una reserva con la MISMA forma que devuelve opera_mapeo.mapear().

    Las llaves están todas, incluso las vacías, a propósito: el cargador lee unas por
    índice y otras con .get(), y una prueba que solo ponga las que le interesan
    pasaría mientras el código de verdad recibe otra cosa.
    """
    r = {
        "conf_no": str(conf_no),
        "room_no": room_no,
        "nombre_principal": f"Huesped {conf_no}",
        "company_travel_agent": None,
        "arr_date": arr_date,
        "dep_date": dep_date,
        "arr_time": None,
        "room_type": "STD",
        "adl": adl,
        "chl": chl,
        "rooms": 1,
        "mkt_code": None,
        "src_code": None,
        "res_status": estado,
        "block_code": None,
        "opera_modificado_en": marca,
        "opera_id": str(conf_no),

        "adicionales_raw": "",
        "notas": "",
        "texto_completo": "",
        "operacion": [],
        "rooming": [],

        "punto_entrada": None,
        "punto_salida": None,
        "punto_entrada_sin_confirmar": None,
        "punto_salida_sin_confirmar": None,
        "hora_vuelo_entrada": None,
        "hora_vuelo_salida": None,
        "vuelo_entrada": None,
        "vuelo_salida": None,

        "guia_sugerido": None,
        "vinculo_texto": None,
    }
    r.update(extra)
    return r


# Lo que manda Opera cuando entrega todo (ver opera_sync.alcance_de_opera).
MANDA_OPERA = frozenset({"nucleo", "tours", "regimen", "amenidades", "rooming",
                         "textos", "transporte"})


def cargar(lote, vistas=None, completo=True, manda_en=MANDA_OPERA,
           fuente="Opera Cloud prueba"):
    """Pasa unas reservas por el camino REAL de carga.

    'lote' es lo que la fuente trae en este ciclo (lo que cambió); 'vistas' es todo lo
    que la fuente vio. Son cosas distintas y confundirlas es justo el fallo que estas
    pruebas fijan, así que la firma obliga a nombrarlas por separado.
    """
    import importer
    import loader
    with contextlib.redirect_stdout(io.StringIO()):
        batch = importer.build_review_batch_desde_reservas([dict(r) for r in lote])
        loader.load_batch(batch, fuente_pdf=fuente,
                          marcar_ausentes_como_canceladas=completo,
                          manda_en=manda_en,
                          vistas_por_la_fuente=vistas)


def estados(conn):
    """{conf_no: res_status} de todo lo que hay en la base."""
    return {str(f["conf_no"]): f["res_status"]
            for f in conn.execute("SELECT conf_no, res_status FROM reserva")}


def alertas(conn, tipo):
    return [dict(f)["mensaje"] for f in conn.execute(
        "SELECT mensaje FROM alerta WHERE tipo = ? AND resuelto = 0", (tipo,))]


def correr(suite, pruebas):
    """Corre las pruebas de una suite, cada una en base limpia."""
    print(f"=== {suite} ===")
    cuenta = Cuenta()
    for prueba in pruebas:
        nombre = prueba.__name__.replace("_", " ")
        try:
            prueba(cuenta)
            print(f"  · {nombre}")
        except Exception as e:
            cuenta.fallos.append(f"{nombre} lanzo {type(e).__name__}: {e}")
            print(f"  · {nombre}  -- EXCEPCION")
    bien = cuenta.resumen(suite)
    return 0 if bien else 1
