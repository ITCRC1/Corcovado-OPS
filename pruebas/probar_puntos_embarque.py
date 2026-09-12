"""De donde entra y por donde sale cada huesped, leido de la nota de la reserva.

Mandar un bote al lugar equivocado, o a la hora equivocada, es de los errores mas caros
que puede cometer el sistema: el huesped se queda en un muelle sin senal. Por eso lo que
no se reconoce NO se adivina, se marca como pendiente y lo resuelve recepcion.

Los textos de aqui son REALES, copiados de las notas de Opera del lodge. Importa: las
formas que usa Reservaciones no son las que uno inventaria —«INGRESO: PTE», «Entrada:»
vacia, «Recogerlos en Punta Marenco 03:00 pm»— y son justo las que rompian el lector.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: F401  (fija la ruta de backend/)

import pdf_parser as pp


def _leer(texto):
    return pp.leer_texto_de_reserva(texto)


# ---------------------------------------------------------------------------
# Lo que se reconoce bien
# ---------------------------------------------------------------------------

def los_dos_puntos_se_leen_de_la_nota(c):
    d = _leer("CPL Paquete 2N/3D+Pension completa\nPNC\n"
              "Entrada: Via Sierpe ocupan parqueo\nSalida: Via Sierpe\n"
              "--------\nRooming:\nAlexander Mcintosch")
    c.igual(d["punto_entrada"], "Sierpe", "entra por Sierpe")
    c.igual(d["punto_salida"], "Sierpe", "y sale por Sierpe")
    c.igual(d["punto_entrada_sin_confirmar"], None, "sin nada pendiente")


def la_entrada_y_la_salida_pueden_ser_distintas(c):
    """Caso real: llega en avioneta a Drake y sale por Sierpe con transporte terrestre."""
    d = _leer("PAQUETE 4D/3N+PENSION COMPLETA\nBT INCLUDED\n"
              "INGRESO: DRAKE - Sansa Flight #1116 @ 09:00\n"
              "SALIDA: SIERPE - TIENEN TT DE SIERPE A HOTEL DEL MAR EN JACO\n")
    c.igual(d["punto_entrada"], "Drake", "entra por Drake")
    c.igual(d["punto_salida"], "Sierpe", "y sale por Sierpe")


def cada_hora_es_la_de_su_propio_campo(c):
    """El fallo: la hora se buscaba en la LINEA entera. En una nota escrita seguida, la
    linea lleva las dos horas y las dos se leian como la primera, asi que el bote de
    salida se apartaba para la hora de llegada."""
    seguido = ("PAQUETE 4D/3N+FULL BOARD PNC+C-CIS C-BT ----------------------------- "
               "INGRESO: Drake Bay (DRK) Sansa 2:45 PM "
               "SALIDA: Drake Bay (DRK) Sansa 9:25 AM "
               "----------------------------- ROOMING: SANDRA HOWARD")
    d = _leer(seguido)
    c.igual(d["punto_entrada"], "Drake", "el punto de entrada se lee igual")
    c.igual(d["punto_salida"], "Drake", "y el de salida")
    c.igual(d["hora_vuelo_entrada"], "2:45 p.m.", "llega a las 2:45 p.m.")
    c.igual(d["hora_vuelo_salida"], "9:25 a.m.", "y SALE a las 9:25 a.m., no a las 2:45")

    # En varias lineas, que es como llega hoy de Opera, tiene que dar lo mismo.
    en_lineas = _leer("INGRESO: Drake Bay (DRK) Sansa 2:45 PM\n"
                      "SALIDA: Drake Bay (DRK) Sansa  9:25 AM\n")
    c.igual(en_lineas["hora_vuelo_entrada"], "2:45 p.m.", "igual en varias lineas")
    c.igual(en_lineas["hora_vuelo_salida"], "9:25 a.m.", "igual en varias lineas")


# ---------------------------------------------------------------------------
# Lo que queda pendiente. No se adivina.
# ---------------------------------------------------------------------------

def punta_marenco_es_una_recogida_de_drake(c):
    """Decision de operacion: el bote que recoge en Punta Marenco es el de Drake. Es un
    punto de RECOGIDA, no un punto de embarque aparte. Antes quedaba pendiente y
    recepcion tenia que resolver a mano las tres habitaciones del mismo grupo."""
    d = _leer("Reserva CPL de inspeccion\n"
              "Entrada: Recogerlos en Punta Marenco 03:00 pm\n"
              "Salida: Via Drake drop off en playa agujitas salida 07:30 am desde el hotel\n")
    c.igual(d["punto_entrada"], "Drake", "entra por Drake")
    c.igual(d["punto_entrada_sin_confirmar"], None, "y ya no queda pendiente")
    c.igual(d["punto_salida"], "Drake", "la salida tambien")
    c.igual(d["hora_vuelo_entrada"], "3:00 p.m.", "con la hora de la recogida")
    c.igual(d["hora_vuelo_salida"], "7:30 a.m.", "y la de salida es la suya, no la otra")


def el_punto_no_tiene_que_ser_la_primera_palabra(c):
    """Se leia solo la primera palabra del valor, asi que «Recogerlos en Punta Marenco» o
    «drop off en playa agujitas» quedaban pendientes aunque nombraran el sitio."""
    for texto, espera in (("Recogerlos en Punta Marenco", "Drake"),
                          ("drop off en playa agujitas", "Drake"),
                          ("Drake Bay (DRK) Sansa 2:45 PM", "Drake"),
                          ("Via Sierpe ocupan parqueo", "Sierpe")):
        c.igual(pp.punto_de(texto), espera, f"«{texto}» es {espera}")


def dos_puntos_distintos_no_se_deciden_solos(c):
    """Si la frase nombra los dos, no hay una respuesta: hay un texto que alguien tiene
    que leer. Mandar el bote por suposicion es el error caro."""
    c.igual(pp.punto_de("no por Sierpe, finalmente por Drake"), None,
            "con dos puntos distintos no se elige")
    d = _leer("Entrada: cambio de Sierpe a Drake, confirmar con la agencia\n")
    c.igual(d["punto_entrada"], None, "queda sin confirmar")
    c.cierto(d["punto_entrada_sin_confirmar"], "y con el texto a la vista")


def la_hora_sirve_aunque_el_punto_no_se_reconozca(c):
    """Era lo que mas costaba: de un texto con hora pero sin punto reconocido, el sistema
    se quedaba con el texto y TIRABA la hora, asi que recepcion tenia que volver a abrir
    Opera para leer una hora que el sistema ya habia leido."""
    d = _leer("Entrada: Recogerlos en el muelle viejo 03:00 pm\n"
              "Salida: lo confirma la agencia, sale 07:30 am\n")
    c.igual(d["punto_entrada"], None, "el punto sigue sin confirmarse")
    c.igual(d["hora_vuelo_entrada"], "3:00 p.m.", "pero la hora se conserva")
    c.igual(d["hora_vuelo_salida"], "7:30 a.m.", "y la de salida es la suya, no la otra")


def el_campo_vacio_se_marca_como_vacio(c):
    """«Entrada:» sin nada detras es pendiente de verdad: Reservaciones todavia no lo
    sabe. Tiene que decirlo asi y no quedar en blanco, que se confunde con no leido."""
    d = _leer("cpl autorizado por isaac\nEntrada:\nSalida:\n--------\nRooming:\nKemly")
    c.igual(d["punto_entrada_sin_confirmar"], "(vacío en la reserva)",
            "dice que la reserva lo trae vacio")
    c.igual(d["punto_salida_sin_confirmar"], "(vacío en la reserva)", "las dos")
    c.cierto("PDF" not in (d["punto_entrada_sin_confirmar"] or ""),
             "y no habla de un PDF: hoy esto viene de Opera")


def el_pte_se_guarda_limpio(c):
    """«PTE» es como Reservaciones escribe «pendiente». El valor que ve recepcion tiene
    que ser eso y no el resto de la nota arrastrado detras."""
    d = _leer("PAQUETE 4D/3N+PENSION COMPLETA CPL\nC-BT+C-CIS+C-NGW\n"
              "------------------------------\nINGRESO: PTE\nSALIDA: PTE\n"
              "-----------------------------\nROOMING: PAM CRUSE")
    c.igual(d["punto_entrada_sin_confirmar"], "PTE", "entrada pendiente, y solo eso")
    c.igual(d["punto_salida_sin_confirmar"], "PTE", "salida pendiente, y solo eso")


def el_valor_no_se_come_el_resto_de_la_nota(c):
    """Escrito seguido, «Entrada:» llegaba hasta el final del texto y recepcion veia un
    parrafo entero donde tendria que ver un lugar."""
    d = _leer("INGRESO: PTE SALIDA: PTE ----------------------------- ROOMING: PAM CRUSE")
    c.igual(d["punto_entrada_sin_confirmar"], "PTE",
            "el valor se corta en el rotulo siguiente")
    c.cierto("ROOMING" not in (d["punto_entrada_sin_confirmar"] or ""),
             "y no arrastra el rooming")


def una_linea_de_salida_no_cuenta_como_entrada(c):
    """«SALIDA:» contiene «IDA» y otras trampas parecidas; la entrada solo se lee de una
    linea que sea de entrada."""
    d = _leer("SALIDA: Via Sierpe\n")
    c.igual(d["punto_salida"], "Sierpe", "la salida se lee")
    c.igual(d["punto_entrada"], None, "y no se confunde con una entrada")


PRUEBAS = [
    los_dos_puntos_se_leen_de_la_nota,
    la_entrada_y_la_salida_pueden_ser_distintas,
    cada_hora_es_la_de_su_propio_campo,
    punta_marenco_es_una_recogida_de_drake,
    el_punto_no_tiene_que_ser_la_primera_palabra,
    dos_puntos_distintos_no_se_deciden_solos,
    la_hora_sirve_aunque_el_punto_no_se_reconozca,
    el_campo_vacio_se_marca_como_vacio,
    el_pte_se_guarda_limpio,
    el_valor_no_se_come_el_resto_de_la_nota,
    una_linea_de_salida_no_cuenta_como_entrada,
]


if __name__ == "__main__":
    sys.exit(comun.correr("puntos de embarque", PRUEBAS))
