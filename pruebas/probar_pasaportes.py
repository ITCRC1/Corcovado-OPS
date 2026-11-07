"""Fija las fotos de pasaporte: a quien pertenecen, quien las ve y que no se pierdan.

POR QUE ESTA SUITE. El guardaparques pide identificacion en San Pedrillo, Sirena y la
Isla del Cano, y hasta ahora eso significaba que el huesped se llevara el documento a la
selva o a un bote. Se fotografia una vez y el guia lo ensena desde el telefono.

LO QUE DE VERDAD VIGILA, que son los tres sitios donde esto se rompe en silencio:

  1. QUE LA FOTO NO SE DESPEGUE DE SU DUENO. El rooming se borra y se vuelve a escribir
     ENTERO en cada importacion —loader._guardar_rooming— asi que huesped.id cambia cada
     media hora. Colgar la foto de ese id habria dejado todas las fotos apuntando a filas
     que ya no existen, sin un solo error: el archivo seguiria en el disco, la pantalla
     del guia saldria vacia, y nadie lo notaria hasta el puesto del parque.
  2. QUE UN GUIA NO VEA MAS DE LO SUYO. El lodge lo definio asi, y esconder botones no
     es protegerlo: la direccion se escribe a mano y un documento de identidad no se
     guarda con un boton oculto.
  3. QUE LA PANTALLA NUEVA QUEDE ALINEADA. El menu resuelve la pantalla por POSICION en
     cuatro listas paralelas. Una desalineacion ahi no da error: abre la pantalla
     equivocada. Ya paso con el Spa.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                      # noqa: E402

import auth                                       # noqa: E402
import pasaportes as P                            # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Una imagen de verdad en lo que importa: sus primeros bytes. El servidor decide que es
# un archivo por su firma, no por el nombre.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 600 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def _reserva(conn, conf_no, room="12", adl=2):
    conn.execute(
        """INSERT INTO reserva (conf_no, room_no, nombre_principal, arr_date, dep_date,
                                adl, chl, rooms, res_status)
           VALUES (?,?,?, '01-01-27','05-01-27', ?,0,1,'POR INGRESAR')""",
        (conf_no, room, f"Huesped/{conf_no}", adl))
    conn.commit()


def _rooming(conn, conf_no, gente):
    conn.execute("DELETE FROM huesped WHERE conf_no = ?", (conf_no,))
    conn.executemany(
        "INSERT INTO huesped (conf_no, nombre_completo, pasaporte) VALUES (?,?,?)",
        [(conf_no, n, p) for n, p in gente])
    conn.commit()


def _tour(conn, conf_no, fecha, codigo, guia):
    conn.execute(
        """INSERT INTO tour_asignado (conf_no, fecha, tour_codigo, pax, grupo_operativo,
                                      guia_nombre, origen)
           VALUES (?,?,?,2,'A',?,'PDF')""", (conf_no, fecha, codigo, guia))
    conn.commit()


def _un_guia(conn, n=0):
    return [r[0] for r in conn.execute(
        "SELECT nombre FROM guia WHERE activo = 1 ORDER BY nombre")][n]


# ---------------------------------------------------------------------------
# A quien pertenece la foto
# ---------------------------------------------------------------------------

def la_foto_sobrevive_a_que_se_regenere_el_rooming(c):
    """LA PRUEBA QUE JUSTIFICA EL DISENO DE LA TABLA.

    Se simula exactamente lo que hace el cargador en cada sincronizacion: borrar el
    rooming entero y volver a escribirlo. Con una clave foranea a huesped.id, despues de
    esto la foto no la encontraria nadie.
    """
    conn = comun.base_limpia()
    _reserva(conn, "960001")
    _rooming(conn, "960001", [("Derek Johnson", "A001"), ("Andrea Ogg", "A002")])
    P.guardar(conn, "960001", "Derek Johnson", JPEG, quien="recepcion", pasaporte="A001")

    antes = {g["nombre"]: len(g["fotos"]) for g in P.de_la_reserva(conn, "960001")}
    c.igual(antes, {"Derek Johnson": 1, "Andrea Ogg": 0}, "la foto esta donde debe")

    # El cargador pasa otra vez: mismo rooming, filas nuevas, id nuevos.
    viejos = [r[0] for r in conn.execute("SELECT id FROM huesped WHERE conf_no='960001'")]
    _rooming(conn, "960001", [("Derek Johnson", "A001"), ("Andrea Ogg", "A002")])
    nuevos = [r[0] for r in conn.execute("SELECT id FROM huesped WHERE conf_no='960001'")]
    c.cierto(set(viejos).isdisjoint(nuevos), "los id del rooming SI cambiaron")

    despues = {g["nombre"]: len(g["fotos"]) for g in P.de_la_reserva(conn, "960001")}
    c.igual(despues, antes, "y la foto sigue colgada de la persona correcta")
    conn.close()


def el_nombre_se_empareja_aunque_se_escriba_distinto(c):
    """El rooming escribe «Sanne Catharina Beckers» y quien toma la foto puede escribir
    «BECKERS, Sanne Catharina». Sin normalizar, la foto quedaria colgada de un huesped
    que la pantalla nunca volveria a encontrar."""
    conn = comun.base_limpia()
    _reserva(conn, "960002")
    _rooming(conn, "960002", [("Sanne Catharina Beckers", "NMD2795C5")])
    P.guardar(conn, "960002", "BECKERS,  Sánne   Catharina", JPEG)

    gente = P.de_la_reserva(conn, "960002")
    c.igual(len(gente), 1, "es UNA persona, no dos")
    c.igual(len(gente[0]["fotos"]), 1, "y la foto es suya")
    c.igual(P.clave("Beckers/Sanne Catharina"), P.clave("sanne catharina beckers"),
            "la normalizacion aguanta el orden y los separadores del PMS")
    c.cierto(P.clave("Ana Lopez") != P.clave("Ana Mora"),
             "pero dos personas distintas siguen siendo distintas")
    conn.close()


def se_puede_fotografiar_a_quien_no_esta_en_el_rooming(c):
    """Medido sobre la base real: 19 reservas vivas sin rooming, y una cuyo unico
    «huesped» se llama «LISTA DE PASAPORTES EN ATTACHMENTS». Si solo se pudiera
    fotografiar a quien ya esta en la tabla, esas reservas —las que mas falta hacen—
    quedarian fuera."""
    conn = comun.base_limpia()
    _reserva(conn, "960003")
    # Sin rooming ninguno.
    P.guardar(conn, "960003", "Nino Healey", JPEG, quien="recepcion")

    gente = P.de_la_reserva(conn, "960003")
    c.igual(len(gente), 1, "aparece igual")
    c.igual(gente[0]["en_rooming"], False, "marcado como agregado a mano")
    c.igual(len(gente[0]["fotos"]), 1, "con su foto")
    conn.close()


# ---------------------------------------------------------------------------
# Quien ve que
# ---------------------------------------------------------------------------

def cada_salida_trae_su_gente_y_lo_que_le_falta(c):
    """Es lo que dibuja el boton de la tarjeta del tour: cuantas listas y cuantas no."""
    conn = comun.base_limpia()
    uno, otro = _un_guia(conn, 0), _un_guia(conn, 1)
    _reserva(conn, "960010", room="12")
    _reserva(conn, "960011", room="14")
    _rooming(conn, "960010", [("Ana Uno", "A1"), ("Bea Dos", "A2")])
    _rooming(conn, "960011", [("Beto Tres", "B1")])
    _tour(conn, "960010", "2027-01-02", "PNC", uno)
    _tour(conn, "960011", "2027-01-02", "SNORKEL", otro)
    P.guardar(conn, "960010", "Ana Uno", JPEG)

    salidas = {s["tour_codigo"]: s for s in P.salidas_del_dia(conn, "2027-01-02")}
    c.igual(sorted(salidas), ["PNC", "SNORKEL"], "salen las dos del dia")
    c.igual((salidas["PNC"]["con_foto"], salidas["PNC"]["sin_foto"]), (1, 1),
            "una lista y una pendiente")
    c.igual(salidas["PNC"]["requiere_entrada_sinac"], True,
            "y PNC viene marcado como que entra al parque")
    c.igual([h["room_no"] for h in salidas["PNC"]["habitaciones"]], ["12"],
            "cada salida trae solo SU habitacion")
    conn.close()


def una_salida_de_otro_dia_no_se_cuela(c):
    """El boton sigue el filtro de fechas de la Agenda, asi que lo que decide es el dia."""
    conn = comun.base_limpia()
    guia = _un_guia(conn, 0)
    _reserva(conn, "960012", room="12")
    _rooming(conn, "960012", [("Ana Uno", "A1")])
    _tour(conn, "960012", "2027-01-02", "PNC", guia)

    c.igual([s["tour_codigo"] for s in P.salidas_del_dia(conn, "2027-01-02")], ["PNC"],
            "el dia del tour si")
    c.igual(P.salidas_del_dia(conn, "2027-01-03"), [], "el dia siguiente no")
    conn.close()


def el_permiso_de_pasaportes_no_se_reparte_solo(c):
    """Son documentos de identidad. Un perfil de conveniencia no los reparte sin que
    nadie lo haya decidido, y el staff de campo no los recibe por ser staff."""
    c.cierto("pasaportes" not in auth.POR_ROL["staff"],
             "el staff no lo tiene por omision")
    c.cierto("pasaportes" not in auth.PERFILES["Solo lectura"],
             "el perfil de solo lectura tampoco")
    c.igual(auth.PERFILES["Guías"].get("pasaportes"), "escribir",
            "el guia SI, porque toma la foto y la ensena")
    c.igual(auth.POR_ROL["recepcion"].get("pasaportes"), "escribir", "recepcion tambien")


# ---------------------------------------------------------------------------
# El archivo
# ---------------------------------------------------------------------------

def lo_que_no_es_una_foto_se_rechaza(c):
    """Se decide por los PRIMEROS BYTES, no por la extension: el nombre lo pone quien
    sube y un '.jpg' no garantiza nada."""
    conn = comun.base_limpia()
    _reserva(conn, "960030")
    for datos, que in ((b"no soy una imagen", "un texto"),
                       (b"", "nada"),
                       (b"\xff\xd8\xff" + b"0" * (P.LIMITE_BYTES + 1), "mas del tope")):
        try:
            P.guardar(conn, "960030", "X", datos)
            c.cierto(False, f"{que} tendria que rebotar")
        except P.FotoInvalida:
            c.ok += 1
    # Y lo que si es una imagen entra, en los tres formatos que se aceptan.
    for datos, ext in ((JPEG, "jpg"), (PNG, "png")):
        fila = P.guardar(conn, "960030", f"Persona {ext}", datos)
        c.cierto(fila["archivo"].endswith("." + ext), f"se guarda como .{ext}")
    conn.close()


def la_ruta_no_se_escapa_del_volumen(c):
    """El numero de reserva viene de Opera y acaba siendo un nombre de carpeta."""
    c.igual(P._seguro("../../etc"), "etc", "los dos puntos se van")
    c.igual(P._seguro("950001"), "950001", "un numero normal se respeta")
    c.igual(P._seguro(""), "sin_reserva", "y vacio tiene su propio sitio")


def borrar_quita_la_fila_y_el_archivo(c):
    conn = comun.base_limpia()
    _reserva(conn, "960040")
    fila = P.guardar(conn, "960040", "Ana Uno", JPEG)
    ruta = P.ruta_de(fila)
    c.cierto(ruta and os.path.exists(ruta), "el archivo se escribio")

    c.igual(P.borrar(conn, fila["id"]), True, "se borra")
    c.cierto(not os.path.exists(ruta), "y el archivo ya no esta")
    c.igual(P.de_la_reserva(conn, "960040"), [], "ni la fila")
    c.igual(P.borrar(conn, fila["id"]), False, "borrar dos veces no revienta")
    conn.close()


def una_fila_sin_archivo_no_miente(c):
    """Si el archivo desaparece, la fila tiene que decirlo. Una fila que promete una foto
    perdida es peor que no tener fila: la pantalla la cuenta como hecha y el guia se
    entera en el puesto del parque."""
    conn = comun.base_limpia()
    _reserva(conn, "960050")
    fila = P.guardar(conn, "960050", "Ana Uno", JPEG)
    os.remove(P.ruta_de(fila))
    c.igual(P.ruta_de(fila), None, "el modulo dice que el archivo no esta")
    # La fila se borra igual, que es lo que deja la pantalla en un estado honesto.
    c.igual(P.borrar(conn, fila["id"]), True, "y se puede quitar la fila huerfana")
    conn.close()


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------

def _html():
    with open(os.path.join(RAIZ, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


def pasaportes_es_un_permiso_y_no_una_pantalla(c):
    """Lo pidio el lodge asi: nada de una pantalla aparte. Se entra por la columna de
    Reservas y por el boton de cada tour en la Agenda, que son los sitios donde la gente
    ya esta.

    Y DE PASO VIGILA LA ALINEACION, que es el fallo que no da error. El menu resuelve
    cada pantalla por POSICION en cuatro listas paralelas —los botones, los cargadores,
    las claves de permiso y los filtros—. Pasaportes NO entra en esas listas por no tener
    boton, asi que lo que hay que comprobar es que las cuatro siguen midiendo lo mismo y
    que ninguna se quedo con la entrada vieja. Ya paso con el Spa: se desplego bien y el
    boton no le aparecia a nadie.
    """
    html = _html()
    c.cierto("pasaportes" in [k for k, _ in auth.PANTALLAS],
             "sigue siendo un permiso que se puede dar")

    claves = html.split("const CLAVE_PANTALLA = ", 1)[1].split("];", 1)[0]
    lista_claves = [t.strip(' "\n') for t in claves.replace("[", "").split(",") if t.strip()]
    c.cierto("pasaportes" not in lista_claves, "pero no es una pantalla del menu")

    filtros = html.split("const FILTRO_DE_PANTALLA = ", 1)[1].split("];", 1)[0]
    lista_filtros = [t.strip(' "\n') for t in filtros.replace("[", "").split(",") if t.strip()]
    cargadores = html.split("function cargadoresPantalla()", 1)[1].split("];", 1)[0]
    lista_carg = [t.strip() for t in cargadores.split("[", 1)[1].split(",") if t.strip()]
    menu = html.split("<nav>", 1)[1].split("</nav>", 1)[0]

    c.igual(len(lista_filtros), len(lista_claves), "las claves y los filtros miden lo mismo")
    c.igual(len(lista_carg), len(lista_claves), "y los cargadores tambien")
    c.igual(menu.count('onclick="irAPantalla('), len(lista_claves),
            "hay un boton de menu por pantalla, ni uno mas ni uno menos")
    c.cierto("loadPasaportes" not in html, "no quedo ningun resto del cargador viejo")


def la_pantalla_no_ensena_el_documento_en_la_lista(c):
    """Una fila de miniaturas de pasaportes es exponer documentos a quien pase por
    delante del mostrador —y a ese tamano no se lee nada—. La lista dice el ESTADO; el
    documento se abre uno por uno."""
    html = _html()
    lista = html.split("function lineaPersonaPasaporte(", 1)[1].split("\nfunction ", 1)[0]
    c.cierto("<img" not in lista, "la lista no trae imagenes")
    c.cierto("sin foto" in lista, "pero si dice a quien le falta")
    c.cierto("verPasaporte(" in lista, "y el documento se abre a proposito")

    visor = html.split("async function verPasaporte(", 1)[1].split("\nfunction ", 1)[0]
    # Con <img src> la imagen viajaria sin la sesion: una direccion que se abra sola
    # serviria un documento de identidad a quien tenga el enlace.
    c.cierto("fetchAuth(" in visor, "el visor pide la imagen CON la sesion")
    c.cierto("createObjectURL" in visor, "y la dibuja desde la respuesta")


def las_fotos_quedan_en_el_telefono_sin_botones(c):
    """EN EL PUESTO DEL PARQUE NO HAY INTERNET, y una foto solo se enseña si sus bytes ya
    estan en el telefono: eso no se puede esquivar. Lo que si se quita es el PASO que
    habia que acordarse de dar.

    Tres piezas tienen que estar las tres, o no sirve de nada:
      · la Agenda las pide calladamente al abrirse con señal,
      · el programa de servicio las guarda,
      · y las sirve del TELEFONO, no de la red — con la estrategia normal se volverian a
        bajar en cada vuelta y gastarian los megas del lodge para acabar con la misma
        copia.
    """
    html = _html()
    c.cierto("async function precargarPasaportes(" in html, "existe la carga silenciosa")
    agenda = html.split("async function loadAgenda(", 1)[1].split("\n// ---", 1)[0]
    c.cierto("precargarPasaportes(" in agenda, "y la Agenda la dispara")
    c.cierto("await precargarPasaportes" not in agenda,
             "sin esperarla: la Agenda no puede quedarse colgada bajando fotos")
    c.cierto("bajarParaSinSenal" not in html, "y no quedo ningun boton de descarga")

    with open(os.path.join(RAIZ, "frontend", "sw.js"), encoding="utf-8") as x:
        sw = x.read()
    c.cierto("esFotoDePasaporte" in sw, "el programa de servicio las reconoce")
    estatico = sw.split("function esEstatico(", 1)[1].split("}", 1)[0]
    c.cierto("esFotoDePasaporte" in estatico,
             "y las sirve del telefono primero, como las fuentes y las fotos")
    no_guardar = sw.split("function noGuardar(", 1)[1].split("}", 1)[0]
    c.cierto("pasaportes" not in no_guardar, "nunca en la lista de «no guardar»")


def el_respaldo_dice_que_las_fotos_van_aparte(c):
    """El respaldo de la base no incluye las fotos. Dejarlo implicito seria construir una
    perdida de datos con fecha: alguien respalda, cree que respaldo todo, y no.

    El ZIP pasó a llevar tambien los tiquetes del SINAC: son lo mismo desde el punto de
    vista del respaldo —archivos del volumen que la copia de la base no incluye— y dos
    botones serian dos sitios del que acordarse."""
    html = _html()
    c.cierto("respaldo/archivos" in html, "hay un respaldo de los archivos del volumen")
    c.cierto("NO incluye las fotos" in html, "y la pantalla lo dice")
    c.cierto("tiquetes" in html.split("Respaldo de los archivos", 1)[1][:900],
             "y dice que ahi van tambien los tiquetes del SINAC")


def se_entra_por_reservas_y_por_la_agenda(c):
    """Los dos sitios donde la gente ya esta: recepcion toma la foto desde la columna de
    Reservas, el guia la ensena desde el boton de su tour en la Agenda."""
    html = _html()
    # La columna de Reservas, al lado de la del itinerario.
    c.cierto("<th>Pasaportes</th>" in html, "hay columna en la tabla de Reservas")
    c.cierto("botonPasaportes(r.conf_no" in html, "con su boton por reserva")
    c.cierto("abrirPasaportesReserva(" in html, "que abre la ficha de esa reserva")
    # El boton de cada tarjeta del resumen de tours.
    resumen = html.split("function resumenPorTour(", 1)[1].split("\n// '2026-09-12'", 1)[0]
    c.cierto("botonPasaportesTour(" in resumen,
             "y hay un boton en la tarjeta de cada tour del resumen")
    boton = html.split("function botonPasaportesTour(", 1)[1].split("\nfunction ", 1)[0]
    c.cierto("event.stopPropagation()" in boton,
             "que no abre ademas el detalle del tour: la tarjeta entera ya es un boton")
    c.cierto('puedeVer("pasaportes")' in boton,
             "y no se le ensena a quien no tiene el permiso")


PRUEBAS = [
    la_foto_sobrevive_a_que_se_regenere_el_rooming,
    el_nombre_se_empareja_aunque_se_escriba_distinto,
    se_puede_fotografiar_a_quien_no_esta_en_el_rooming,
    cada_salida_trae_su_gente_y_lo_que_le_falta,
    una_salida_de_otro_dia_no_se_cuela,
    el_permiso_de_pasaportes_no_se_reparte_solo,
    lo_que_no_es_una_foto_se_rechaza,
    la_ruta_no_se_escapa_del_volumen,
    borrar_quita_la_fila_y_el_archivo,
    una_fila_sin_archivo_no_miente,
    pasaportes_es_un_permiso_y_no_una_pantalla,
    se_entra_por_reservas_y_por_la_agenda,
    la_pantalla_no_ensena_el_documento_en_la_lista,
    las_fotos_quedan_en_el_telefono_sin_botones,
    el_respaldo_dice_que_las_fotos_van_aparte,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Pasaportes", PRUEBAS))
