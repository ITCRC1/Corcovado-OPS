"""Fija los tiquetes del SINAC: que no se despeguen de su dia y que lleguen al parque.

POR QUE ESTA SUITE. Las entradas de Corcovado, Sirena y la Isla del Cano se compran en
linea y el SINAC devuelve un comprobante. Vivia en el correo de recepcion: el guia salia
con una impresion, con una captura, o sin nada. En el puesto del parque no hay senal, asi
que "lo busco en el correo" no existe como opcion.

LO QUE DE VERDAD VIGILA, que son los sitios donde esto se rompe EN SILENCIO:

  1. QUE EL TIQUETE NO SE DESPEGUE DE SU ENTRADA. Las entradas pendientes SE BORRAN
     —sinac.limpiar_huerfanas() quita las que se quedan sin reservas detras cuando un
     tour cambia de fecha o se cancela— y el importador las vuelve a crear con otro id.
     Colgar el comprobante de ese id lo habria dejado apuntando a una fila que ya no
     existe, sin un solo error: el archivo seguiria en el disco, el boton del guia
     saldria vacio, y nadie lo notaria hasta el puesto del parque.
  2. QUE LA REGLA DE "ESTE TIQUETE SIRVE PARA ESTA ENTRADA" ESTE ESCRITA UNA VEZ. Si se
     repite en JavaScript, dentro de seis meses las dos dicen cosas distintas.
  3. QUE EL GUIA PUEDA ABRIRLO. El perfil «Guias» no tenia 'sinac': el boton se habria
     desplegado, recepcion habria subido los comprobantes, y el guia no veria nada. Es
     exactamente el fallo que ya paso con la pantalla del Spa.
  4. QUE SE PUEDA ENSENAR SIN SENAL. El archivo tiene que servirse del telefono, no de
     la red, o todo lo demas sobra.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                      # noqa: E402

import auth                                       # noqa: E402
import pasaportes as P                            # noqa: E402
import sinac                                      # noqa: E402
import tiquetes as T                              # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Archivos de verdad en lo que importa: sus primeros bytes. El servidor decide que es un
# archivo por su firma, no por el nombre.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 600 + b"\xff\xd9"
PDF = b"%PDF-1.4\n" + b"\x00" * 400 + b"%%EOF"


def _entrada(conn, tour, fecha, conf=None, pax=4, estado="SIN_COMPRAR"):
    cur = conn.execute(
        """INSERT INTO entrada_sinac (tour_codigo, fecha, conf_entrada, pax_total_grupo,
                                      estado)
           VALUES (?,?,?,?,?)""", (tour, fecha, conf, pax, estado))
    conn.commit()
    return cur.lastrowid


def _fila(conn, entrada_id):
    return dict(conn.execute("SELECT * FROM entrada_sinac WHERE id = ?",
                             (entrada_id,)).fetchone())


def _html():
    with open(os.path.join(RAIZ, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# A que se engancha el tiquete
# ---------------------------------------------------------------------------

def el_tiquete_sobrevive_a_que_se_borre_su_entrada(c):
    """LA PRUEBA QUE JUSTIFICA EL DISENO DE LA TABLA.

    Se sube el comprobante de una entrada, y despues esa entrada desaparece: es lo que
    hace sinac.limpiar_huerfanas() cuando el tour cambia de fecha o la reserva se
    cancela, y el importador la vuelve a crear con OTRO id.

    Si el tiquete colgara de entrada_sinac.id, aqui quedaria apuntando a una fila que ya
    no existe —y el guia llegaria al puesto del parque con un boton vacio—. Al colgar de
    la FECHA, sigue ahi y se sigue encontrando.
    """
    conn = comun.base_limpia()
    try:
        entrada_id = _entrada(conn, "SIRENA", "2026-12-20", conf="SIN-1")
        fila = T.guardar(conn, "2026-12-20", PDF, tour_codigo="SIRENA",
                         conf_entrada="SIN-1", titulo="Comprobante Sirena")

        # Una reserva CANCELADA con ese tour: asi es como una entrada se queda huerfana
        # de verdad. (Con tour_asignado vacio, limpiar_huerfanas no toca nada a
        # proposito — ver su comentario.)
        conn.execute(
            """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date,
                                    dep_date, adl, chl, rooms, res_status)
               VALUES ('999999','12','Huesped/999999','18-12-26','22-12-26',
                       2,0,1,'CANCELADA')""")
        conn.execute(
            """INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax, origen)
               VALUES ('999999','2026-12-20','SIRENA',4,'PDF')""")
        conn.commit()
        borradas, _ = sinac.limpiar_huerfanas(conn)
        c.igual(borradas, 1, "la entrada pendiente se borro, como hace el importador")
        c.igual(conn.execute("SELECT COUNT(*) FROM entrada_sinac WHERE id = ?",
                             (entrada_id,)).fetchone()[0], 0, "ya no esta")

        quedan = T.del_rango(conn, "2026-12-20", "2026-12-20")
        c.igual(len(quedan), 1, "pero el comprobante sigue ahi")
        c.igual(quedan[0]["id"], fila["id"], "y es el mismo")
        c.cierto(T.ruta_de(fila), "con su archivo en el disco")

        # Y cuando el importador la vuelve a crear con otro id, el tiquete la cubre igual.
        nuevo_id = _entrada(conn, "SIRENA", "2026-12-20", conf="SIN-1")
        c.cierto(nuevo_id != entrada_id, "la entrada nueva tiene otro id")
        c.cierto(T.cubre(quedan[0], _fila(conn, nuevo_id)),
                 "y el comprobante la sigue cubriendo")
    finally:
        conn.close()


def la_regla_de_a_quien_cubre_esta_escrita_una_vez(c):
    """Un tiquete sin tour cubre todo el dia; con tour, solo ese.

    Recepcion compra de una sola vez las entradas de varios tours del mismo dia, y a
    veces el comprobante no dice a cual corresponde. Exigir el tour para poder subirlo
    significaria que no se sube.
    """
    conn = comun.base_limpia()
    pnc = _fila(conn, _entrada(conn, "PNC", "2026-12-20", conf="A-1"))
    snorkel = _fila(conn, _entrada(conn, "SNORKEL", "2026-12-20", conf="B-2"))
    otro_dia = _fila(conn, _entrada(conn, "PNC", "2026-12-21", conf="A-1"))

    del_dia = {"fecha": "2026-12-20", "tour_codigo": None, "conf_entrada": None}
    c.cierto(T.cubre(del_dia, pnc), "el de todo el dia cubre el PNC")
    c.cierto(T.cubre(del_dia, snorkel), "y tambien el snorkel de Isla del Caño")
    c.cierto(not T.cubre(del_dia, otro_dia), "pero no el dia siguiente")

    solo_pnc = {"fecha": "2026-12-20", "tour_codigo": "PNC", "conf_entrada": None}
    c.cierto(T.cubre(solo_pnc, pnc), "el del PNC cubre el PNC")
    c.cierto(not T.cubre(solo_pnc, snorkel), "y no el snorkel")

    con_numero = {"fecha": "2026-12-20", "tour_codigo": "PNC", "conf_entrada": "A-1"}
    c.cierto(T.cubre(con_numero, pnc), "con numero, cubre la entrada de ese numero")
    otra_conf = dict(pnc, conf_entrada="Z-9")
    c.cierto(not T.cubre(con_numero, otra_conf), "y no la de otro numero")
    conn.close()


def la_pantalla_no_repite_la_regla_en_javascript(c):
    """Si se escribe otra vez en el navegador, dentro de seis meses dicen cosas
    distintas. La tabla lee lo que el servidor ya decidio: e.tiquetes."""
    html = _html()
    c.cierto("marcaTiquete(e)" in html, "la fila usa la lista que vino del servidor")
    marca = html.split("function marcaTiquete(", 1)[1].split("\nfunction ", 1)[0]
    c.cierto("e.tiquetes" in marca, "lee e.tiquetes y no vuelve a comparar")
    for senal in ("tour_codigo ===", "conf_entrada ===", ".fecha ==="):
        c.cierto(senal not in marca, f"no rehace la comparacion ({senal})")

    with open(os.path.join(RAIZ, "backend", "main.py"), encoding="utf-8") as f:
        main = f.read()
    c.cierto("tiquetes.cubre(t, r)" in main, "la regla se aplica en el servidor")


# ---------------------------------------------------------------------------
# El archivo
# ---------------------------------------------------------------------------

def el_pdf_entra_aqui_aunque_no_entre_en_los_pasaportes(c):
    """El SINAC manda el comprobante en PDF casi siempre. Rechazarlo obligaria a
    recepcion a convertirlo antes de subirlo, que es el paso que hace que la gente deje
    de usar una herramienta.

    En los pasaportes sigue sin entrar, y es deliberado: aquello es una foto tomada con
    la camara del telefono. Por eso cada modulo elige su lista."""
    conn = comun.base_limpia()
    fila = T.guardar(conn, "2026-12-20", PDF)
    c.cierto(fila["archivo"].endswith(".pdf"), "el PDF se guarda como .pdf")
    c.igual(T.tipo_de(fila), "application/pdf", "y se sirve como PDF")

    foto = T.guardar(conn, "2026-12-20", JPEG)
    c.cierto(foto["archivo"].endswith(".jpg"), "una foto del comprobante tambien entra")

    c.cierto(b"%PDF-" not in P.TIPOS, "y en los pasaportes el PDF sigue fuera")
    conn.close()


def lo_que_no_es_un_comprobante_se_rechaza(c):
    """Se decide por los PRIMEROS BYTES, no por la extension."""
    conn = comun.base_limpia()
    for datos, que in ((b"no soy nada", "un texto"),
                       (b"", "nada"),
                       (b"%PDF-" + b"0" * (T.LIMITE_BYTES + 1), "mas del tope")):
        try:
            T.guardar(conn, "2026-12-20", datos)
            c.cierto(False, f"{que} tendria que rebotar")
        except T.TiqueteInvalido:
            c.ok += 1
    conn.close()


def una_fecha_que_no_se_entiende_se_rechaza(c):
    """La fecha es obligatoria Y ADEMAS es un nombre de carpeta.

    Sin validarla pasarian dos cosas malas a la vez: se crearia un directorio con
    cualquier texto dentro del volumen, y se guardaria un tiquete que el filtro por
    fechas no va a encontrar nunca — el peor fallo posible aqui, porque no da error y
    solo se nota en el puesto del parque.
    """
    conn = comun.base_limpia()
    for mala in ("", None, "manana", "20/12/2026", "../../etc"):
        try:
            T.guardar(conn, mala, PDF)
            c.cierto(False, f"{mala!r} tendria que rebotar")
        except T.TiqueteInvalido:
            c.ok += 1
    fila = T.guardar(conn, "2026-12-20", PDF)
    c.cierto(fila["archivo"].startswith("2026-12-20/"),
             "y la buena manda la carpeta donde se guarda")
    conn.close()


def la_ruta_no_se_escapa_del_volumen(c):
    """La comprobacion vive en archivos.seguro(), que es la MISMA que usan los
    pasaportes: tenerla escrita dos veces es como una se corrige y la otra no."""
    import archivos
    c.igual(archivos.seguro("../../etc"), "etc", "los dos puntos se van")
    c.igual(archivos.seguro("2026-12-20"), "2026-12-20", "una fecha se respeta")
    c.igual(archivos.seguro(""), "sin_clasificar", "y vacio tiene su propio sitio")
    c.igual(P._seguro("../../etc"), "etc", "los pasaportes usan la misma")


def borrar_quita_la_fila_y_el_archivo(c):
    conn = comun.base_limpia()
    fila = T.guardar(conn, "2026-12-20", PDF, titulo="Sirena")
    ruta = T.ruta_de(fila)
    c.cierto(ruta and os.path.exists(ruta), "el archivo se escribio")

    c.igual(T.borrar(conn, fila["id"]), True, "se borra")
    c.cierto(not os.path.exists(ruta), "y el archivo ya no esta")
    c.igual(T.del_rango(conn), [], "ni la fila")
    c.igual(T.borrar(conn, fila["id"]), False, "borrar dos veces no revienta")
    conn.close()


def una_fila_sin_archivo_no_miente(c):
    """Si el archivo desaparece, la fila tiene que decirlo: el boton del guia que no
    abre nada es peor que un hueco que avisa."""
    conn = comun.base_limpia()
    fila = T.guardar(conn, "2026-12-20", PDF)
    os.remove(T.ruta_de(fila))
    c.igual(T.ruta_de(fila), None, "la ruta dice que no esta")
    c.igual(T.borrar(conn, fila["id"]), True, "y la fila se puede quitar igual")
    conn.close()


def el_listado_no_lleva_el_archivo_dentro(c):
    """El archivo va por su propia direccion, con su permiso. Dentro del listado, una
    pantalla de dos meses bajaria cincuenta PDF que nadie pidio."""
    conn = comun.base_limpia()
    T.guardar(conn, "2026-12-20", PDF, titulo="Uno")
    fila = T.del_rango(conn)[0]
    c.cierto("archivo" not in fila, "la ruta del servidor no sale en el listado")
    c.igual(fila["tipo"], "application/pdf", "pero si de que tipo es, para saber abrirlo")
    conn.close()


def el_filtro_de_fechas_es_el_de_la_pantalla(c):
    """El mismo rango que ya filtra Entradas SINAC: no hay un segundo filtro que
    mantener de acuerdo con el primero."""
    conn = comun.base_limpia()
    for f in ("2026-12-18", "2026-12-20", "2026-12-25"):
        T.guardar(conn, f, PDF)
    c.igual(len(T.del_rango(conn, "2026-12-19", "2026-12-21")), 1, "solo el del rango")
    c.igual(len(T.del_rango(conn, "2026-12-18", "2026-12-25")), 3, "los tres si cabe")
    c.igual(len(T.del_rango(conn)), 3, "y sin rango, todos")
    fechas = [t["fecha"] for t in T.del_rango(conn)]
    c.igual(fechas, sorted(fechas), "ordenados por dia, que es como se usan")
    conn.close()


# ---------------------------------------------------------------------------
# Quien lo ve
# ---------------------------------------------------------------------------

def el_guia_lo_abre_y_no_lo_sube(c):
    """'sinac' en VER: el guia tiene que poder ensenarlo en el puesto del parque, donde
    el guardaparques lo pide. Comprar la entrada y subir el comprobante sigue siendo de
    recepcion."""
    c.igual(auth.PERFILES["Guías"].get("sinac"), "ver", "el perfil «Guias» lo lleva")
    guia = {"rol": "staff",
            "permisos_json": json.dumps(auth.PERFILES["Guías"], ensure_ascii=False)}
    c.cierto(auth.puede(guia, "sinac"), "puede abrirlo")
    c.cierto(not auth.puede(guia, "sinac", escribir=True), "y no puede subir ni borrar")
    recepcion = {"rol": "recepcion",
                 "permisos_json": json.dumps(auth.PERFILES["Recepción"],
                                             ensure_ascii=False)}
    c.cierto(auth.puede(recepcion, "sinac", escribir=True), "recepcion si")
    # Y lo que el guia TIENE que seguir pudiendo hacer no se toca. La agenda la lleva en
    # 'ver' desde que el lodge pidio que el reparto de guias y grupos quede en recepcion
    # —ver probar_permisos_de_guia— pero los pasaportes siguen en escribir: es quien toma
    # la foto al recibir al huesped.
    c.igual(auth.PERFILES["Guías"].get("agenda"), "ver", "la agenda, en solo lectura")
    c.igual(auth.PERFILES["Guías"].get("pasaportes"), "escribir",
            "y los pasaportes en escribir, que es quien toma la foto")


def la_migracion_se_lo_da_a_los_guias_que_ya_existen(c):
    """EL FALLO QUE EVITA, que ya paso con la pantalla del Spa: el boton se despliega,
    recepcion sube los comprobantes, y el guia no ve nada.

    No basta con cambiar auth.PERFILES: _sembrar_perfiles usa INSERT OR IGNORE, asi que
    el perfil «Guias» que ya esta en la base se queda como estaba; y
    _pantallas_nuevas_a_las_rejillas solo agrega pantallas NUEVAS, y 'sinac' lleva ahi
    desde el principio.
    """
    import init_db
    conn = comun.base_limpia()

    # Un guia de los de antes: con agenda y sin sinac. Y dos que NO se deben tocar.
    viejo = {"agenda": "escribir", "transporte": "ver", "pasaportes": "escribir"}
    a_mano = {"agenda": "escribir", "sinac": "escribir"}
    sin_agenda = {"spa": "escribir", "reservas": "ver"}
    for usuario, permisos in (("guia_viejo", viejo), ("jefe", a_mano),
                              ("spa", sin_agenda)):
        conn.execute(
            "INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol, "
            "                     permisos_json) VALUES (?,?,?,?,?,?)",
            (usuario, "x", "x", usuario.title(), "staff",
             json.dumps(permisos, ensure_ascii=False)))
    # El perfil guardado TAL COMO ESTA en la base del lodge: se quedo como el dia que se
    # creo, sin 'pasaportes' y sin 'sinac'.
    perfil_viejo = {"agenda": "escribir", "transporte": "ver", "resumen": "ver"}
    conn.execute("UPDATE perfil_permisos SET permisos_json = ? WHERE nombre = 'Guías'",
                 (json.dumps(perfil_viejo, ensure_ascii=False),))
    # Se borra la marca: la base recien creada ya corrio la migracion.
    conn.execute("DELETE FROM sistema_meta WHERE clave = 'sinac_ver_a_los_guias'")
    conn.commit()

    init_db._tiquetes_del_sinac_a_los_guias(conn)

    def rejilla(usuario):
        return json.loads(dict(conn.execute(
            "SELECT permisos_json FROM usuario WHERE username = ?",
            (usuario,)).fetchone())["permisos_json"])

    c.igual(rejilla("guia_viejo").get("sinac"), "ver", "el guia que ya existia lo gana")
    c.igual(rejilla("guia_viejo").get("agenda"), "escribir", "y no pierde lo que tenia")
    c.igual(rejilla("jefe").get("sinac"), "escribir",
            "a quien ya escribia NO se le baja a ver")
    c.cierto("sinac" not in rejilla("spa"),
             "y a quien no lleva agenda no se le da nada")

    perfil = json.loads(dict(conn.execute(
        "SELECT permisos_json FROM perfil_permisos WHERE nombre = 'Guías'"
    ).fetchone())["permisos_json"])
    c.igual(perfil.get("sinac"), "ver", "el perfil guardado tambien queda corregido")
    # Y se completa ENTERO, no solo la linea del SINAC. Medido en la base del lodge: el
    # perfil guardado era {agenda, transporte, resumen} y le faltaba 'pasaportes' desde
    # que se pusieron las fotos — un guia creado desde ese perfil no habria podido abrir
    # ni un pasaporte, y se habria visto como «la funcion no sirve».
    c.igual(perfil.get("pasaportes"), "escribir",
            "y lo que se le habia quedado viejo tambien se completa")
    c.igual(perfil.get("agenda"), "escribir", "sin pisar lo que ya tenia")

    # Corre una sola vez: si manana alguien se lo quita a un guia a proposito, el
    # siguiente arranque no se lo devuelve.
    conn.execute("UPDATE usuario SET permisos_json = ? WHERE username = 'guia_viejo'",
                 (json.dumps(viejo, ensure_ascii=False),))
    conn.commit()
    init_db._tiquetes_del_sinac_a_los_guias(conn)
    c.cierto("sinac" not in rejilla("guia_viejo"), "la segunda vez ya no hace nada")
    conn.close()


# ---------------------------------------------------------------------------
# Que llegue al parque
# ---------------------------------------------------------------------------

def el_tiquete_se_sirve_del_telefono_y_no_de_la_red(c):
    """En el puesto del parque no hay senal, y un comprobante solo se puede ensenar si
    sus bytes ya estan en el telefono. Eso no se puede esquivar; lo que si se quita es el
    paso que habia que acordarse de dar."""
    with open(os.path.join(RAIZ, "frontend", "sw.js"), encoding="utf-8") as f:
        sw = f.read()
    c.cierto("esTiqueteDelSinac" in sw, "el programa de servicio los reconoce")
    estatico = sw.split("function esEstatico(", 1)[1].split("}", 1)[0]
    c.cierto("esTiqueteDelSinac" in estatico, "y los sirve del telefono primero")
    no_guardar = sw.split("function noGuardar(", 1)[1].split("}", 1)[0]
    c.cierto("tiquetes-sinac" not in no_guardar, "nunca en la lista de «no guardar»")
    c.cierto('VERSION = "cwl-v3"' not in sw,
             "y la version subio: un telefono con la copia vieja los pediria a la red")

    html = _html()
    c.cierto("precargarTiquetes(" in html, "la pantalla los pide calladamente")
    entradas = html.split("async function loadEntradas(", 1)[1].split("\nfunction ", 1)[0]
    c.cierto("precargarTiquetes(tiquetes)" in entradas, "al abrirse, con senal")
    c.cierto("await precargarTiquetes" not in entradas,
             "sin esperarla: la pantalla no puede quedarse colgada bajando PDF")
    precarga = html.split("async function precargarTiquetes(", 1)[1].split("\nasync function ", 1)[0]
    # Sin los comentarios: ahi se EXPLICA por que no se usa toISOString, y buscar la
    # palabra a secas haria fallar la prueba por la explicacion que la justifica.
    codigo = "\n".join(l for l in precarga.splitlines()
                       if not l.strip().startswith("//"))
    c.cierto("hoyISO()" in codigo,
             "con la fecha de aqui, no la de UTC: el lodge va seis horas por detras")
    c.cierto("toISOString" not in codigo, "nada de fechas en UTC")


def el_boton_esta_en_la_pantalla_del_sinac_y_se_llama_como_pidieron(c):
    """No es una pantalla nueva: es un recuadro mas, al lado de «Ya compradas», donde
    recepcion ya mira que falta comprar."""
    html = _html()
    entradas = html.split("async function loadEntradas(", 1)[1].split("\nfunction detalleSinac", 1)[0]
    c.cierto("Tiquets adquiridos" in entradas, "el recuadro se llama como lo pidieron")
    c.cierto('onclick="detalleTiquetes()"' in entradas, "y abre el panel")
    c.cierto("repeat(5,1fr)" in entradas, "la rejilla pasa a cinco recuadros")
    c.cierto("detalleSinac('OK')" in entradas, "sin quitar los cuatro de antes")
    # El filtro de fechas es el mismo, no uno nuevo.
    c.cierto("api/tiquetes-sinac?desde=${desde}&hasta=${hasta}" in entradas,
             "y usa el rango que ya tiene la pantalla")


def el_guia_no_descarga_nada(c):
    """Lo mismo que con los pasaportes: se abre para ensenarlo. El boton de pantalla
    completa del PDF no es una descarga —es la misma copia que ya esta en el telefono—,
    y esta porque en iPhone el marco a menudo sale en blanco."""
    html = _html()
    ver = html.split("async function verTiquete(", 1)[1].split("\nfunction cerrarTiquete", 1)[0]
    c.cierto("a.download" not in ver, "no hay ningun enlace de descarga")
    c.cierto("URL.createObjectURL" in ver, "se abre desde la copia del telefono")
    c.cierto("fetchAuth" in ver, "y se pide con la sesion puesta, no con <img src>")
    cerrar = html.split("function cerrarTiquete(", 1)[1].split("}", 1)[0]
    c.cierto("revokeObjectURL" in cerrar, "y al cerrar se suelta la memoria")


PRUEBAS = [
    el_tiquete_sobrevive_a_que_se_borre_su_entrada,
    la_regla_de_a_quien_cubre_esta_escrita_una_vez,
    la_pantalla_no_repite_la_regla_en_javascript,
    el_pdf_entra_aqui_aunque_no_entre_en_los_pasaportes,
    lo_que_no_es_un_comprobante_se_rechaza,
    una_fecha_que_no_se_entiende_se_rechaza,
    la_ruta_no_se_escapa_del_volumen,
    borrar_quita_la_fila_y_el_archivo,
    una_fila_sin_archivo_no_miente,
    el_listado_no_lleva_el_archivo_dentro,
    el_filtro_de_fechas_es_el_de_la_pantalla,
    el_guia_lo_abre_y_no_lo_sube,
    la_migracion_se_lo_da_a_los_guias_que_ya_existen,
    el_tiquete_se_sirve_del_telefono_y_no_de_la_red,
    el_boton_esta_en_la_pantalla_del_sinac_y_se_llama_como_pidieron,
    el_guia_no_descarga_nada,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Tiquetes del SINAC", PRUEBAS))
