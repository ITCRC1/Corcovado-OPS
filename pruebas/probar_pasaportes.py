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

def un_guia_ve_solo_sus_salidas(c):
    conn = comun.base_limpia()
    mio, ajeno = _un_guia(conn, 0), _un_guia(conn, 1)
    _reserva(conn, "960010", room="12")
    _reserva(conn, "960011", room="14")
    _rooming(conn, "960010", [("Ana Uno", "A1")])
    _rooming(conn, "960011", [("Beto Dos", "B1")])
    _tour(conn, "960010", "2027-01-02", "PNC", mio)
    _tour(conn, "960011", "2027-01-02", "SNORKEL", ajeno)

    suyas = P.salidas_del_dia(conn, "2027-01-02", guia=mio)
    c.igual([s["tour_codigo"] for s in suyas], ["PNC"], "solo la suya")
    c.igual([h["room_no"] for h in suyas[0]["habitaciones"]], ["12"],
            "y solo la habitacion de esa salida")

    todas = P.salidas_del_dia(conn, "2027-01-02")
    c.igual(sorted(s["tour_codigo"] for s in todas), ["PNC", "SNORKEL"],
            "sin filtrar salen las dos, que es lo que ve recepcion")
    conn.close()


def un_guia_no_puede_tocar_una_reserva_ajena(c):
    """Esconder el boton no es protegerlo: la direccion se escribe a mano."""
    import main
    conn = comun.base_limpia()
    mio, ajeno = _un_guia(conn, 0), _un_guia(conn, 1)
    _reserva(conn, "960020", room="12")
    _reserva(conn, "960021", room="14")
    _tour(conn, "960020", "2027-01-02", "PNC", mio)
    _tour(conn, "960021", "2027-01-02", "SNORKEL", ajeno)

    guia = {"id": 9, "username": "g", "rol": "staff", "guia_nombre": mio,
            "permisos_json": '{"pasaportes":"escribir"}'}
    recepcion = {"id": 1, "username": "r", "rol": "recepcion", "guia_nombre": None,
                 "permisos_json": None}
    c.igual(main._reserva_al_alcance(conn, guia, "960020"), True, "la suya si")
    c.igual(main._reserva_al_alcance(conn, guia, "960021"), False, "la ajena no")
    c.igual(main._reserva_al_alcance(conn, recepcion, "960021"), True,
            "recepcion no es guia y llega a todas")
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


def la_pantalla_nueva_quedo_alineada(c):
    """EL FALLO QUE NO DA ERROR: abre la pantalla equivocada.

    El menu resuelve cada pantalla por POSICION en cuatro listas paralelas —los botones,
    los cargadores, las claves de permiso y los filtros— y ademas tiene que coincidir con
    auth.PANTALLAS del servidor. Ya paso con el Spa: se desplego bien y el boton no le
    aparecia a nadie.
    """
    html = _html()
    indice_servidor = [k for k, _ in auth.PANTALLAS].index("pasaportes")

    claves = html.split("const CLAVE_PANTALLA = ", 1)[1].split("];", 1)[0]
    lista_claves = [t.strip(' "\n') for t in claves.replace("[", "").split(",") if t.strip()]
    c.igual(lista_claves.index("pasaportes"), indice_servidor,
            "la clave de permiso esta en la MISMA posicion que en el servidor")

    filtros = html.split("const FILTRO_DE_PANTALLA = ", 1)[1].split("];", 1)[0]
    lista_filtros = [t.strip(' "\n') for t in filtros.replace("[", "").split(",") if t.strip()]
    c.igual(len(lista_filtros), len(lista_claves), "las dos listas miden lo mismo")
    c.igual(lista_filtros[indice_servidor], "pasaportes", "y el filtro cae en su sitio")

    cargadores = html.split("function cargadoresPantalla()", 1)[1].split("];", 1)[0]
    lista_carg = [t.strip() for t in cargadores.split("[", 1)[1].split(",") if t.strip()]
    c.igual(len(lista_carg), len(lista_claves), "y los cargadores tambien")
    c.igual(lista_carg[indice_servidor], "loadPasaportes", "el cargador es el que toca")

    # Solo los del MENU: hay otros «irAPantalla» sueltos por la aplicacion —el boton de
    # «Ver Entradas SINAC» del dashboard, por ejemplo— y contarlos todos haria que esta
    # prueba fallara cada vez que alguien agrega un atajo.
    menu = html.split("<nav>", 1)[1].split("</nav>", 1)[0]
    c.igual(menu.count('onclick="irAPantalla('), len(lista_claves),
            "hay un boton de menu por pantalla, ni uno mas ni uno menos")
    c.cierto(f'irAPantalla({indice_servidor})' in menu,
             "y el boton de Pasaportes lleva a su indice")


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


def se_puede_bajar_para_usar_sin_senal(c):
    """En el puesto del parque no hay internet. Sin esto la pantalla funciona en el lodge
    y falla justo donde hace falta."""
    html = _html()
    f = html.split("async function bajarParaSinSenal(", 1)[1].split("\n// ---", 1)[0]
    c.cierto("/imagen" in f, "pide cada foto una vez, para que el telefono la guarde")
    c.cierto("de ${ids.length}" in f, "y dice cuantas van")
    # El programa de servicio tiene que poder guardarlas: si estuvieran en la lista de
    # «no guardar», el boton no serviria de nada.
    with open(os.path.join(RAIZ, "frontend", "sw.js"), encoding="utf-8") as x:
        sw = x.read()
    no_guardar = sw.split("function noGuardar(", 1)[1].split("}", 1)[0]
    c.cierto("pasaportes" not in no_guardar,
             "y el programa de servicio NO las excluye de la copia")


def el_respaldo_dice_que_las_fotos_van_aparte(c):
    """El respaldo de la base no incluye las fotos. Dejarlo implicito seria construir una
    perdida de datos con fecha: alguien respalda, cree que respaldo todo, y no."""
    html = _html()
    c.cierto("respaldo/pasaportes" in html, "hay un respaldo de fotos")
    c.cierto("NO incluye las fotos" in html, "y la pantalla lo dice")


PRUEBAS = [
    la_foto_sobrevive_a_que_se_regenere_el_rooming,
    el_nombre_se_empareja_aunque_se_escriba_distinto,
    se_puede_fotografiar_a_quien_no_esta_en_el_rooming,
    un_guia_ve_solo_sus_salidas,
    un_guia_no_puede_tocar_una_reserva_ajena,
    el_permiso_de_pasaportes_no_se_reparte_solo,
    lo_que_no_es_una_foto_se_rechaza,
    la_ruta_no_se_escapa_del_volumen,
    borrar_quita_la_fila_y_el_archivo,
    una_fila_sin_archivo_no_miente,
    la_pantalla_nueva_quedo_alineada,
    la_pantalla_no_ensena_el_documento_en_la_lista,
    se_puede_bajar_para_usar_sin_senal,
    el_respaldo_dice_que_las_fotos_van_aparte,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Pasaportes", PRUEBAS))
