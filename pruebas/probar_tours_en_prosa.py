"""Fija la lectura del itinerario cuando recepción lo escribe en prosa, y la modalidad.

POR QUE ESTA SUITE. El lodge reportó que faltaban tours —«sirena privado»— y que había
nomenclaturas que el sistema no leía. Medido sobre las 376 reservas de la base real:

  · 71 líneas nombraban un tour con su fecha y NO producían ninguno. Ahí estaban
    «PRV-CID 26/11», «PRV-PNC 11/12», «PRIV-SIR 03/12», «25/11 PRIVADO SIRENA» y días
    enteros de itinerario escritos en una frase.
  · «22:PRV-MGS» —sin espacio tras los dos puntos— se perdía entero.
  · 'PRIV-' perdía el privado en los 19 tours del catálogo: el servicio entraba como
    compartido y salía en un bote con otra gente.
  · Los códigos de opera_paquetes (CEBT, SPS, SCI, TSP…) solo valían leyendo el paquete,
    no el texto.

Pasado por el camino real contra Opera: 357 -> 432 tours, 0 perdidos, 12 -> 22 privados.

LO QUE DE VERDAD VIGILA, que es lo contrario de lo que parece: que NO se invente nada.
Leer de más es peor que leer de menos — un tour que nadie pidió se lleva un guía, un
bote y una entrada del parque, y nadie lo descubre hasta ese día. Por eso la mitad de
esta suite son frases que NO tienen que producir tours.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402

import importer                                  # noqa: E402
import opera_paquetes as op                      # noqa: E402
import pdf_parser                                # noqa: E402


def _leer(texto):
    """{(tour, dia, mes): (privado, cortesia)} de lo que saca el lector de prosa."""
    return {(t["tour"], t["dia"], t["mes"]): (t["privado"], t["cortesia"])
            for t in pdf_parser.tours_en_prosa(texto)}


def _tours(texto):
    return sorted({t["tour"] for t in pdf_parser.tours_en_prosa(texto)})


def _itinerario(lineas):
    """Lo que el lector saca de una nota con su sección de Operación."""
    texto = "Operacion:\n" + "\n".join(lineas)
    return pdf_parser.leer_texto_de_reserva(texto).get("operacion") or []


# ---------------------------------------------------------------------------
# Lo que SÍ hay que leer — frases copiadas de la base real
# ---------------------------------------------------------------------------

def el_codigo_con_su_fecha_se_lee(c):
    """La forma más común de todas, y la que el lodge echó en falta."""
    casos = [
        ("PRV-CID 26/11", "BUCEO", 26, 11, True),
        ("PRV-PNC 11/12", "PNC", 11, 12, True),
        ("PRIV-SIR 03/12", "SIRENA", 3, 12, True),
        ("NW 9/11", "NW", 9, 11, False),
        ("MGS 05/12", "MANGLAR", 5, 12, False),
        ("C-EBT 07/11", "PAJAREO", 7, 11, False),
    ]
    for texto, tour, dia, mes, privado in casos:
        leido = _leer(texto)
        c.igual(list(leido), [(tour, dia, mes)], f"«{texto}» da {tour} el {dia}/{mes}")
        if leido:
            c.igual(leido[(tour, dia, mes)][0], privado,
                    f"«{texto}»: privado = {privado}")


def varios_tours_en_una_frase_van_cada_uno_a_su_dia(c):
    """Tantas fechas como tours: van en orden. Es como recepción escribe el itinerario
    completo en una línea."""
    leido = _leer("A solicitud del cliente PNC 17/12 - CIS 18/12")
    c.igual(leido.get(("PNC", 17, 12)), (False, False), "PNC al 17")
    c.igual(leido.get(("SNORKEL", 18, 12)), (False, False), "CIS al 18")

    # La fecha puede ir DELANTE del código, y mezclada con la otra forma.
    leido = _leer("AGENCIA SOLICITA 19/12 PNC + CIS 20/12")
    c.igual(leido.get(("PNC", 19, 12)), (False, False), "PNC al 19")
    c.igual(leido.get(("SNORKEL", 20, 12)), (False, False), "CIS al 20")

    # Cinco de una, con un privado en medio y el prefijo escrito sin guion.
    leido = _leer("A SOLICITUD DE LA CLIENTA: NW 13/12 - PRIV|CPLEBT 14/12 "
                  "+ PNC 15/12 + MGS 16/12 + SIR 17/12")
    c.igual(len(leido), 5, "los cinco tours de la frase")
    c.igual(leido.get(("PAJAREO", 14, 12)), (True, True),
            "PRIV|CPLEBT es privado Y cortesia, con el prefijo pegado al codigo")
    c.igual(leido.get(("SIRENA", 17, 12)), (False, False), "y el SIR del final")


def una_fecha_manda_sobre_todos_los_codigos_pegados(c):
    """«07/12: C-EBT + CLW» son dos tours el mismo día. El «|» separa los grupos."""
    leido = _leer("KATIANA SOLICITA - 07/12: C-EBT + CLW | 08/12: CIS | 09/12: HBR + NW")
    c.igual(sorted(leido), sorted([("PAJAREO", 7, 12), ("CLW", 7, 12),
                                   ("SNORKEL", 8, 12), ("CABALGATA", 9, 12),
                                   ("NW", 9, 12)]),
            "cada grupo va a su dia")


def el_dia_sin_mes_tambien_vale(c):
    """«CIS el 26», «PNC para el 18»: recepción escribe el día suelto, como en el
    itinerario. El mes lo deduce la estadía, igual que siempre."""
    # El C- de C-EBT es cortesia, y eso no se pierde por estar escrito en una frase.
    c.igual(_leer("Cliente solicita C-EBT el 09"), {("PAJAREO", 9, None): (False, True)},
            "«el 09», y el C- sigue siendo cortesia")
    c.igual(_leer("Cliente solicita PNC para el 18"), {("PNC", 18, None): (False, False)},
            "«para el 18»")
    leido = _leer("Cliente solicita PNC el 9, CIS el 10, KSJ el 11")
    c.igual(sorted(leido), sorted([("PNC", 9, None), ("SNORKEL", 10, None),
                                   ("SAN JOSECITO", 11, None)]),
            "tres dias sueltos, cada uno con el suyo")
    # Y «el 01/03» sigue siendo una fecha entera, no el día 1.
    c.igual(_leer("spa para el 01/03"), {("SPA", 1, 3): (False, False)},
            "«el 01/03» es el 1 de marzo, no el dia 1")
    # Un porcentaje no es un día.
    c.igual(_leer("PNC con el 15% de descuento"), {}, "«el 15%» no es el dia 15")


def la_palabra_privado_marca_el_tour_de_al_lado(c):
    """«25/11 PRIVADO SIRENA» — lo que el lodge reportó. Antes la palabra cortaba el
    camino entre la fecha y el código, así que no salía ni el tour ni el privado."""
    c.igual(_leer("25/11 PRIVADO SIRENA"), {("SIRENA", 25, 11): (True, False)},
            "delante del codigo")
    c.igual(_leer("SIRENA PRIVADO 25/11"), {("SIRENA", 25, 11): (True, False)},
            "y detras tambien")
    c.igual(_leer("PNC PRIVATE 03/12"), {("PNC", 3, 12): (True, False)},
            "en ingles igual")


# ---------------------------------------------------------------------------
# Lo que NO hay que leer — también copiado de la base real
# ---------------------------------------------------------------------------

def una_frase_no_es_un_itinerario(c):
    """LA MITAD QUE IMPORTA. Un tour que nadie pidió se lleva un guía, un bote y una
    entrada del parque, y no se descubre hasta ese día.

    Lo que separa una instrucción de una frase es la ADYACENCIA: en «PNC 22/11» el
    código y la fecha están pegados; en las de abajo hay palabras por medio.
    """
    no_son_tours = [
        # El caso que lo justifica: 11/08 leído al derecho es agosto, y la estadía es
        # de noviembre. Además nadie pidió ese PNC: es una inspección.
        "PNC E INSPECCIÓN 11/08 Sin restricciones alimenticias",
        "Para el 25 solicitan BT roundtrip a un bote de unos amigos que van para Sirena",
        "Ocupan servicio de niñera para el día 26/11 que realizaran snorkeling",
        "SE LE COBRA MGS POR 4 PAX PARA CUMPLIR EL MINIMO",
        "INTERESADOS EN RESERVAR CIS EN EL HOTEL",
        "AGENCIA INDICA: No quieren hacer el tour de snorkeling",
        "ATENCION FRONT DESK: LOS CLIENTES VAN A OVERNIGHT 2 NOCHES EN SIRENA",
        "SE LES CAMBIO CIS POR EL TOUR DE BALLENAS, DIFERENCIA DE 356 + TAXES",
        "Precio por el manglar de $150 pp + taxes.",
        # «o» no es «y»: no se sabe cuál de los dos.
        "CPL EN TRANSPORTE EN BOTE/PENSIÓN COMPLETA/ HOSPEDAJE/ CIS O PNC",
    ]
    for texto in no_son_tours:
        c.igual(_tours(texto), [], f"no inventa nada en «{texto[:50]}»")


def lo_que_no_cuadra_no_se_reparte(c):
    """Con dos fechas y tres tours no se sabe cuál va con cuál. El ejemplo lo trae el
    propio comentario del lector, de una nota real."""
    c.igual(_tours("08/08 SNK para bruce - shared DIVING 09/08 PNC"), [],
            "tres tours y dos fechas: no se adivina")


def el_transporte_no_es_un_tour(c):
    """BT, TT y TRB son traslados. Meterlos aquí pondría una salida de bote en la
    agenda de guías; tienen su propio camino."""
    for texto in ("BT 12/12", "TT 12/12", "TRB 12/12", "MGX 12/12"):
        c.igual(_tours(texto), [], f"«{texto}» no es un tour")


# ---------------------------------------------------------------------------
# Todas las nomenclaturas del catálogo
# ---------------------------------------------------------------------------

def los_23_codigos_del_catalogo_se_reconocen(c):
    """El catálogo maestro del lodge: 23 códigos base y cuatro modalidades cada uno.

    Se comprueban las cuatro del documento MÁS las dos formas que la base tiene escritas
    de verdad y que el documento no contempla: 'PRIV-' y el prefijo pegado sin guion.
    """
    tours = [cod for cod, _e, _s, _n in op.CATALOGO_2027]
    c.cierto(len(tours) >= 19, f"hay {len(tours)} codigos base en la tabla")
    for cod in tours:
        for pref, privado, cortesia in (("", False, False),
                                        ("C-", False, True),
                                        ("CPL-", False, True),
                                        ("PRV-", True, False),
                                        ("PRIV-", True, False),
                                        ("PRV|CPL-", True, True),
                                        ("PRV|CPL", True, True)):
            leido = pdf_parser.tours_en_prosa(f"{pref}{cod} 05/12")
            c.igual(len(leido), 1, f"«{pref}{cod}» se reconoce")
            if leido:
                c.igual((leido[0]["privado"], leido[0]["cortesia"]), (privado, cortesia),
                        f"«{pref}{cod}» es privado={privado} cortesia={cortesia}")


def los_codigos_de_los_paquetes_tambien_se_leen_en_el_texto(c):
    """EL HUECO QUE TAPA: CEBT vivía en opera_paquetes.TOURS_POR_RAIZ y esa tabla no
    llegaba al lector de texto, así que «CEBT Y PNC 09/12» perdía el CEBT.

    Son las formas que el lodge escribe de verdad: la misma tabla que ya traduce el
    paquete tiene que traducir el comentario."""
    for codigo, esperado in (("CEBT", "PAJAREO"), ("SPS", "SIRENA"), ("SCI", "SNORKEL"),
                             ("TSP", "PNC"), ("NQ", "NW"), ("WWE", "BALLENAS")):
        c.igual(_tours(f"{codigo} 05/12"), [esperado],
                f"«{codigo}» se lee como {esperado} tambien en el texto")
    c.igual(sorted(_tours("CEBT Y PNC 09/12")), ["PAJAREO", "PNC"],
            "y los dos de la frase real salen")


# ---------------------------------------------------------------------------
# El itinerario con formato, que es el camino de siempre
# ---------------------------------------------------------------------------

def el_dia_sin_espacio_tras_los_dos_puntos_se_lee(c):
    """«22:PRV-MGS» es una línea real de una reserva real, y se perdía entera: el patrón
    exigía un espacio detrás de los dos puntos.

    Esa reserva —seis tours, todos privados— llegaba al lodge con tres."""
    ops = _itinerario(["21: PRV-PNC 203133", "22:PRV-MGS", "23: PRV-CIS",
                       "24: C-EBT-PRV-NW", "25: PRV-SIR"])
    por_tour = {o["tour"]: o for o in ops}
    for tour in ("PNC", "MANGLAR", "SNORKEL", "NW", "PAJAREO", "SIRENA"):
        c.cierto(tour in por_tour, f"{tour} se lee")
    c.igual(por_tour.get("MANGLAR", {}).get("dia"), "22", "el MGS pegado va al dia 22")
    c.igual(por_tour.get("MANGLAR", {}).get("privado"), True, "y es privado")
    c.igual(por_tour.get("PAJAREO", {}).get("cortesia"), True,
            "el C-EBT de la linea compartida es cortesia")
    c.igual(por_tour.get("NW", {}).get("privado"), True, "y el PRV-NW de la misma, privado")


def una_hora_no_es_un_dia(c):
    """El (?=[^\\d]) que protege el cambio de arriba: sin él «14:30» sería el día 14, y
    el 30 acabaría buscándose como número de entrada del parque."""
    ops = _itinerario(["14:30 el guia pasa por la habitacion"])
    c.igual([o for o in ops if o.get("tour")], [], "«14:30» no crea ningun tour")


# ---------------------------------------------------------------------------
# Cómo se junta con lo que ya se sabía
# ---------------------------------------------------------------------------

def el_itinerario_manda_sobre_la_frase(c):
    """Si los dos colocan el mismo tour el mismo día, la frase solo aporta la modalidad.
    Si lo ponen en días distintos, no se elige: se deja el del itinerario y se avisa."""
    leido = pdf_parser.leer_texto_de_reserva(
        "Operacion:\n22: PNC\nNOTAS:\nPRV-PNC 22/11")
    pncs = [o for o in leido["operacion"] if o.get("tour") == "PNC"]
    c.igual(len(pncs), 1, "no se duplica el PNC")
    c.igual(pncs[0].get("privado"), True, "pero la frase le pone el privado")

    leido = pdf_parser.leer_texto_de_reserva(
        "Operacion:\n22: PNC\nNOTAS:\nPNC 25/11")
    pncs = [o for o in leido["operacion"] if o.get("tour") == "PNC"]
    c.igual(len(pncs), 1, "con dias distintos no se crea un segundo PNC")
    c.igual(pncs[0]["dia"], "22", "manda el del itinerario")
    avisos = " ".join(a["texto"] for a in leido.get("actividades_no_reconocidas") or [])
    c.cierto("Revisar" in avisos, "y queda avisado para que recepcion lo mire")


def una_frase_suma_a_los_paquetes_y_no_los_borra(c):
    """EL FALLO QUE ESTO EVITA, y que no se ve hasta que pasa.

    El itinerario escrito reemplaza a los paquetes de Opera a propósito: es lo que
    recepción corrigió a mano. Pero una frase suelta NO es un itinerario. Si reemplazara,
    una reserva con tres tours en sus paquetes y un «NW 11/11» escrito de paso se
    quedaría con el NW y perdería los otros tres, sin dar ningún error.
    """
    import opera_mapeo
    reserva = {"operacion": [
        {"dia": "21", "tour": "PNC", "privado": False},
        {"dia": "23", "tour": "SNORKEL", "privado": False},
        {"dia": "25", "tour": "SIRENA", "privado": False},
    ]}
    opera_mapeo.incorporar_texto_de_nota(reserva, "NOTAS:\nNW 24/11")
    tours = sorted(o["tour"] for o in reserva["operacion"])
    c.igual(tours, ["NW", "PNC", "SIRENA", "SNORKEL"],
            "el NW se suma y los tres de los paquetes siguen")

    # Y si la frase habla de un tour que el paquete ya trae, no lo duplica: le pone la
    # marca de privado, que es lo que el paquete no sabe.
    reserva = {"operacion": [{"dia": "25", "tour": "SIRENA", "privado": False}]}
    opera_mapeo.incorporar_texto_de_nota(reserva, "NOTAS:\n25/11 PRIVADO SIRENA")
    c.igual(len(reserva["operacion"]), 1, "no se duplica la SIRENA")
    c.igual(reserva["operacion"][0]["privado"], True, "y queda privada")


def con_itinerario_de_verdad_sigue_mandando_la_nota(c):
    """La regla de siempre no cambia: un itinerario escrito reemplaza a los paquetes."""
    import opera_mapeo
    reserva = {"operacion": [{"dia": "21", "tour": "PNC", "privado": False},
                             {"dia": "23", "tour": "SNORKEL", "privado": False}]}
    opera_mapeo.incorporar_texto_de_nota(
        reserva, "Operacion:\n22: ISLA\n23: NW")
    c.igual(sorted(o["tour"] for o in reserva["operacion"]), ["ISLA", "NW"],
            "el itinerario de la nota reemplaza a los paquetes, como siempre")


# ---------------------------------------------------------------------------
# De día a fecha
# ---------------------------------------------------------------------------

def el_mes_escrito_manda_sobre_el_deducido(c):
    """Cuando la nota dice el mes, no se deduce. Deducirlo teniendo el dato delante es
    como se acaba poniendo el tour en el mes que no era."""
    # Llega el 28 de noviembre: el día 3 suelto se deduce como diciembre.
    c.igual(importer.to_iso_date("28-11-26", "3"), "2026-12-03", "sin mes, se deduce")
    # Con el mes escrito, manda lo escrito.
    c.igual(importer.to_iso_date("28-11-26", "3", 12), "2026-12-03", "con mes, diciembre")
    c.igual(importer.to_iso_date("28-11-26", "29", 11), "2026-11-29", "y noviembre")
    # Fin de año: llega el 29/12 y la nota dice 01/01.
    c.igual(importer.to_iso_date("29-12-26", "1", 1), "2027-01-01", "cruza el año")
    # Un día que no existe no revienta.
    c.igual(importer.to_iso_date("28-11-26", "31", 11), None, "el 31 de noviembre no es")


def un_tour_fuera_de_la_estadia_no_entra(c):
    """Lo que caza una fecha escrita al revés. «SNK 26/11» en una reserva que sale el 25
    no es un tour: es una nota de otra cosa, o un error que recepción tiene que ver."""
    r = {"arr_date": "24-11-26", "dep_date": "25-11-26"}
    c.igual(importer._dentro_de_la_estadia(r, "2026-11-24"), True, "el dia de llegada si")
    c.igual(importer._dentro_de_la_estadia(r, "2026-11-25"), True, "el de salida tambien")
    c.igual(importer._dentro_de_la_estadia(r, "2026-11-26"), False, "el siguiente no")
    c.igual(importer._dentro_de_la_estadia(r, "2026-08-11"), False, "ni agosto")
    # Sin fechas claras no se descarta nada: es mejor un tour de mas que uno perdido
    # cuando ni siquiera se sabe cuando viene el huesped.
    c.igual(importer._dentro_de_la_estadia({}, "2026-11-26"), True,
            "sin estadia conocida no se descarta")


def el_camino_completo_de_una_nota_real(c):
    """De la nota tal cual la manda Opera hasta los tours guardados, sin saltarse pasos.

    Es la reserva 595019418 de la base real: seis tours, todos privados, de los que el
    lodge estaba viendo tres."""
    nota = """Paquete 6N/7D + Full board
PRV-NW + PRV-CIS + C-EBT + PRV-PNC + PRV-MGS + PRV-SIR
-------------------------------------------
Rooming:
Kyle Lauret A73209212
-------------------------------------------
Operacion:
20: In
21: PRV-PNC 203133
22:PRV-MGS
23: PRV-CIS
24: C-EBT-PRV-NW
25: PRV-SIR
26: Out
--------------------------------------------
NOTAS:
CLIENTES SE HIPER CUIDAN CON EL COVID, Y POR ESO RESERVARON TODO PRIVADO."""
    leido = pdf_parser.leer_texto_de_reserva(nota)
    por_tour = {o["tour"]: o for o in leido["operacion"] if o.get("tour")}
    c.igual(sorted(por_tour),
            ["MANGLAR", "NW", "PAJAREO", "PNC", "SIRENA", "SNORKEL"],
            "los seis tours de la nota")
    for tour in ("PNC", "MANGLAR", "SNORKEL", "NW", "SIRENA"):
        c.igual(por_tour[tour].get("privado"), True, f"{tour} es privado")
    c.igual(por_tour["PAJAREO"].get("privado"), False,
            "el C-EBT NO es privado: es cortesia, y son cosas distintas")

    # Y de ahi a la fecha, con la llegada de verdad.
    fechas = {t: importer.to_iso_date("20-11-26", o["dia"], o.get("mes"))
              for t, o in por_tour.items()}
    c.igual(fechas["PNC"], "2026-11-21", "el PNC cae el 21")
    c.igual(fechas["MANGLAR"], "2026-11-22", "y el manglar el 22")
    c.igual(fechas["SIRENA"], "2026-11-25", "y la sirena el 25")


PRUEBAS = [
    el_codigo_con_su_fecha_se_lee,
    varios_tours_en_una_frase_van_cada_uno_a_su_dia,
    una_fecha_manda_sobre_todos_los_codigos_pegados,
    el_dia_sin_mes_tambien_vale,
    la_palabra_privado_marca_el_tour_de_al_lado,
    una_frase_no_es_un_itinerario,
    lo_que_no_cuadra_no_se_reparte,
    el_transporte_no_es_un_tour,
    los_23_codigos_del_catalogo_se_reconocen,
    los_codigos_de_los_paquetes_tambien_se_leen_en_el_texto,
    el_dia_sin_espacio_tras_los_dos_puntos_se_lee,
    una_hora_no_es_un_dia,
    el_itinerario_manda_sobre_la_frase,
    una_frase_suma_a_los_paquetes_y_no_los_borra,
    con_itinerario_de_verdad_sigue_mandando_la_nota,
    el_mes_escrito_manda_sobre_el_deducido,
    un_tour_fuera_de_la_estadia_no_entra,
    el_camino_completo_de_una_nota_real,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Tours escritos en prosa", PRUEBAS))
