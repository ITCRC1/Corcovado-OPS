"""Fija la nomenclatura de abreviaturas de tours del lodge (catalogo 2027).

POR QUE ESTA SUITE. El lodge definio codigos nuevos para los tours y cuatro modalidades
por cada uno:

    PNC           regular / compartido
    C-PNC         cortesia (Complementary)
    PRV-PNC       privado, con cargo
    PRV|CPL-PNC   privado y ademas cortesia

YA SE ESTAN USANDO. En las reservas de Opera de hoy aparece
«PAQUETE 4D/3N+PENSION COMPLETA CPL C-BT+C-CIS+C-NGW». Sin entender el prefijo, el
sistema daba esos codigos por DESCONOCIDOS y esas reservas se quedaban sin sus tours en
la hoja del dia — sin dar ningun error.

Y falla en silencio en las dos direcciones: un prefijo mal leido puede convertir un tour
en otro, y entonces la hoja del dia manda el bote y el guia equivocados.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402
import opera_paquetes as op                      # noqa: E402


# ---------------------------------------------------------------------------
# Los prefijos
# ---------------------------------------------------------------------------

def se_leen_las_cuatro_modalidades(c):
    """Las cuatro formas del documento, sobre el ejemplo que el propio documento usa."""
    c.igual(op.descomponer("PNC"), ("PNC", False, False), "PNC: regular")
    c.igual(op.descomponer("C-PNC"), ("PNC", False, True), "C-PNC: cortesia")
    c.igual(op.descomponer("PRV-PNC"), ("PNC", True, False), "PRV-PNC: privado")
    c.igual(op.descomponer("PRV|CPL-PNC"), ("PNC", True, True),
            "PRV|CPL-PNC: privado y cortesia")


def se_aceptan_las_dos_formas_del_cuarto_caso(c):
    """El documento lo escribe de dos maneras: 'PRV|CPL-PNC' en la tabla de reglas y
    'PRV|CPLPNC' en la tabla maestra. Discutir cual es la buena no le sirve a nadie; lo
    que sirve es que ninguna de las dos se pierda."""
    for escrito in ("PRV|CPL-PNC", "PRV|CPLPNC", "PRV|C-PNC", "PRV |CPL- PNC"):
        c.igual(op.descomponer(escrito), ("PNC", True, True),
                f"«{escrito}» se entiende igual")


def el_prefijo_no_convierte_un_tour_en_otro(c):
    """Un PNC privado sigue siendo la caminata a San Pedrillo: mismo horario, mismo
    bote, misma entrada del SINAC. Si el prefijo cambiara el tour, la hoja del dia
    mostraria dos salidas donde hay una."""
    for codigo in ("PNC", "C-PNC", "PRV-PNC", "PRV|CPL-PNC"):
        c.igual(op.clasificar(codigo)["valor"], "PNC", f"«{codigo}» es el tour PNC")


def el_sufijo_de_descuento_se_sigue_quitando(c):
    """Los codigos traen el descuento comercial pegado al final ('CIS30'), y eso ya
    funcionaba. Tiene que seguir funcionando CON prefijo."""
    c.igual(op.descomponer("CIS30"), ("CIS", False, False), "CIS30 -> CIS")
    c.igual(op.descomponer("C-CIS30"), ("CIS", False, True), "C-CIS30 -> CIS, cortesia")
    c.igual(op.descomponer("PRV-CIS3027"), ("CIS", True, False), "PRV-CIS3027 -> CIS")


def un_codigo_que_solo_es_prefijo_no_inventa_un_tour(c):
    """'PRV-' sin nada detras no es un tour. Quedarse con una base vacia haria que
    cualquier cosa empatara con cualquier cosa."""
    for raro in ("PRV-", "C-", "PRV|CPL-"):
        base, _, _ = op.descomponer(raro)
        c.cierto(base and base != "", f"«{raro}» no deja una base vacia")
        c.igual(op.clasificar(raro)["tipo"], "desconocido",
                f"«{raro}» se avisa como desconocido")


# ---------------------------------------------------------------------------
# Los codigos reales que YA aparecen en Opera
# ---------------------------------------------------------------------------

def los_codigos_de_la_reserva_real_se_reconocen(c):
    """De una reserva de verdad: «PENSION COMPLETA CPL C-BT+C-CIS+C-NGW»."""
    bt = op.clasificar("C-BT")
    c.igual(bt["tipo"], "traslado", "C-BT es un traslado en bote, no un tour")
    c.igual(bt["cortesia"], True, "y es cortesia")

    cis = op.clasificar("C-CIS")
    c.igual(cis["tipo"], "tour", "C-CIS es un tour")
    c.igual(cis["valor"], "SNORKEL", "el snorkel de Isla del Caño")
    c.igual(cis["cortesia"], True, "de cortesia")

    ngw = op.clasificar("C-NGW")
    c.igual(ngw["tipo"], "tour", "C-NGW es un tour")
    c.igual(ngw["valor"], "NGW", "la caminata naturalista, que es nueva")
    c.igual(ngw["cortesia"], True, "de cortesia")


def ninguno_de_los_23_codigos_queda_como_desconocido(c):
    """Es el punto de todo esto: que una reserva con la nomenclatura nueva no se quede
    sin sus tours."""
    sueltos = []
    for cod, _, _, _ in op.CATALOGO_2027:
        for forma in (cod, f"C-{cod}", f"PRV-{cod}", f"PRV|CPL-{cod}"):
            if op.clasificar(forma)["tipo"] == "desconocido":
                sueltos.append(forma)
    for cod in op.TRASLADOS_2027:
        for forma in (cod, f"C-{cod}"):
            if op.clasificar(forma)["tipo"] == "desconocido":
                sueltos.append(forma)
    c.igual(sueltos, [], "ningun codigo del catalogo queda sin reconocer")


# ---------------------------------------------------------------------------
# Lo que el documento pide distinguir
# ---------------------------------------------------------------------------

def el_manglar_del_traslado_no_es_el_tour_de_manglar(c):
    """El documento lo subraya: «No usar MGS y MGX como sinonimos». MGX viene incluido
    en el traslado; tratarlo como tour pondria una salida de manglar en la hoja del dia
    que no existe, con su guia y su bote apartados."""
    c.igual(op.clasificar("MGS")["tipo"], "tour", "MGS es el tour completo")
    c.igual(op.clasificar("MGS")["valor"], "MANGLAR", "y es el manglar de siempre")
    c.igual(op.clasificar("MGX")["tipo"], "traslado",
            "MGX es parte del traslado, NO un tour")


def las_dos_estaciones_de_corcovado_son_distintas(c):
    """El documento avisa: «Usar SIR para evitar que ambas estaciones queden registradas
    como PNC». Son caminatas distintas, con horarios distintos."""
    c.igual(op.clasificar("PNC")["valor"], "PNC", "PNC es San Pedrillo")
    c.igual(op.clasificar("SIR")["valor"], "SIRENA", "SIR es Sirena")
    c.cierto(op.clasificar("PNC")["valor"] != op.clasificar("SIR")["valor"],
             "y no son el mismo tour")


def el_discovery_scuba_no_es_el_buceo_de_isla(c):
    """El documento: «Actividad distinta de CID; no requiere usar el mismo codigo»."""
    c.igual(op.clasificar("CID")["valor"], "BUCEO", "CID es el buceo de Isla del Caño")
    c.igual(op.clasificar("DSD")["valor"], "DSD", "DSD es otra actividad")


def los_transportes_no_son_tours(c):
    """Un traslado no lleva guia ni ocupa cupo de tour. Metido en la agenda, apartaria
    recursos para una salida que no existe."""
    for cod in ("TT", "BT", "TRB", "MGX"):
        c.igual(op.clasificar(cod)["tipo"], "traslado", f"{cod} es traslado")


# ---------------------------------------------------------------------------
# Los nombres
# ---------------------------------------------------------------------------

def cada_codigo_tiene_nombre_legible(c):
    c.igual(op.nombre_de("SIR"),
            "Caminata al Parque Nacional Corcovado · Sirena", "en español")
    c.igual(op.nombre_de("SIR", "en"),
            "Hiking to Corcovado National Park · Sirena Station", "en inglés")
    c.cierto("cortesía" in op.nombre_de("C-PNC"), "la cortesia se dice")
    c.cierto("privado" in op.nombre_de("PRV-PNC"), "y lo privado tambien")
    n = op.nombre_de("PRV|CPL-PNC")
    c.cierto("privado" in n and "cortesía" in n, "y las dos juntas")
    c.igual(op.nombre_de("XXNOEXISTE"), "", "un codigo que no existe no inventa nombre")


def los_tours_nuevos_entran_al_catalogo(c):
    """Sin fila en el catalogo, un tour detectado no tiene horario ni capacidad y no se
    puede asignar. Van SIN horario a proposito: el documento da el nombre, no la
    operacion, y un horario inventado es peor que uno vacio que alguien completa."""
    import init_db
    catalogo = {t[0] for t in init_db.TOURS}
    for cod, nombre in init_db.TOURS_2027_NUEVOS:
        c.cierto(cod in catalogo, f"{cod} ({nombre}) esta en el catalogo")
    fila = {t[0]: t for t in init_db.TOURS}["KSJ"]
    c.igual(fila[2], None, "y sin horario de inicio inventado")
    c.igual(fila[8], 0, "ni bote supuesto")
    c.igual(fila[7], 0, "ni entrada del SINAC supuesta")


def todo_tour_reconocido_existe_en_el_catalogo(c):
    """Si clasificar() devuelve un tour que no esta en el catalogo, esa salida no se
    puede asignar y nadie se entera."""
    import init_db
    catalogo = {t[0] for t in init_db.TOURS}
    faltan = sorted({v for v in op.TOURS_POR_RAIZ.values()} - catalogo)
    c.igual(faltan, [], "todo tour al que se traduce un codigo existe en el catalogo")


def los_codigos_se_reconocen_en_el_COMENTARIO(c):
    """Donde de verdad van. El documento lo dice: «La nomenclatura no modifica la
    estructura del comentario de la reserva», o sea que los codigos se escriben ahi.
    Reconocerlos solo en los paquetes de Opera habria dejado fuera el caso real."""
    import pdf_parser as pp
    for cod, equivalente, _, _ in op.CATALOGO_2027:
        c.igual(pp.TOUR_ALIASES.get(cod), equivalente or cod,
                f"«{cod}» se reconoce leyendo el comentario")


def la_modalidad_se_lee_pegada_al_codigo(c):
    """'C-CIS' es una cortesia. Un 'CPL' suelto tres palabras antes puede estar
    hablando de otra cosa de la reserva, asi que solo cuenta lo pegado."""
    import pdf_parser as pp
    texto = "11: C-CIS 12: PRV-PNC 13: CPL en hospedaje y luego NW"
    c.igual(pp.modalidad_antes_de(texto, texto.index("CIS")), (False, True),
            "C-CIS es cortesia")
    c.igual(pp.modalidad_antes_de(texto, texto.index("PNC")), (True, False),
            "PRV-PNC es privado")
    c.igual(pp.modalidad_antes_de(texto, texto.index("NW")), (False, False),
            "un CPL lejos NO convierte el NW en cortesia")


def una_sola_tabla_de_equivalencias(c):
    """Dos listas que digan lo mismo se separan, y entonces el mismo codigo significa
    una cosa leyendo el comentario y otra leyendo el paquete."""
    import pdf_parser as pp
    for cod, equivalente, _, _ in op.CATALOGO_2027:
        c.igual(pp.TOUR_ALIASES.get(cod), op.TOURS_POR_RAIZ.get(cod),
                f"«{cod}» significa lo mismo en los dos caminos")


PRUEBAS = [
    se_leen_las_cuatro_modalidades,
    los_codigos_se_reconocen_en_el_COMENTARIO,
    la_modalidad_se_lee_pegada_al_codigo,
    una_sola_tabla_de_equivalencias,
    se_aceptan_las_dos_formas_del_cuarto_caso,
    el_prefijo_no_convierte_un_tour_en_otro,
    el_sufijo_de_descuento_se_sigue_quitando,
    un_codigo_que_solo_es_prefijo_no_inventa_un_tour,
    los_codigos_de_la_reserva_real_se_reconocen,
    ninguno_de_los_23_codigos_queda_como_desconocido,
    el_manglar_del_traslado_no_es_el_tour_de_manglar,
    las_dos_estaciones_de_corcovado_son_distintas,
    el_discovery_scuba_no_es_el_buceo_de_isla,
    los_transportes_no_son_tours,
    cada_codigo_tiene_nombre_legible,
    los_tours_nuevos_entran_al_catalogo,
    todo_tour_reconocido_existe_en_el_catalogo,
]


if __name__ == "__main__":
    sys.exit(comun.correr("codigos de tours", PRUEBAS))
