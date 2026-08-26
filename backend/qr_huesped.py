"""
Acceso del huésped al itinerario mediante código QR.

Cada habitación tiene UN código QR fijo que nunca cambia. El código apunta a una
dirección que siempre muestra el itinerario de quien ocupa esa habitación hoy, de
modo que al cambiar de huésped no hay que reimprimir nada.
"""
import io
import os
import json
import datetime

import qrcode
from qrcode.image.pil import PilImage

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as canvas_mod
from reportlab.lib.utils import ImageReader

VERDE = colors.Color(0.1216, 0.2275, 0.1804)

# Archivo propio que este módulo usaba antes. Ya no se escribe: la configuración
# es una sola, la de publicador.py. Se sigue leyendo por si quedó de una versión
# anterior, para no perder la dirección que alguien ya había dejado puesta.
CONFIG_ANTIGUA_PATH = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "config_qr.json",
)


def _config_antigua():
    try:
        with open(CONFIG_ANTIGUA_PATH, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (ValueError, OSError):
        return {}


def cargar_config():
    """Dirección base a la que apuntan los QR, compartida con la pantalla de Publicación.

    Antes había dos archivos de configuración distintos —uno de este módulo y otro de
    publicador.py—, así que la dirección se dejaba puesta en una pantalla y la otra
    seguía diciendo que faltaba. Ahora hay una sola. Si quedó un archivo viejo con la
    dirección, se aprovecha una única vez y a partir de ahí manda la compartida.
    """
    import publicador as pub
    cfg = pub.cargar_config()
    if not cfg.get("base_url"):
        heredada = (_config_antigua().get("base_url") or "").strip()
        if heredada:
            cfg = pub.guardar_config({"base_url": heredada})
    return cfg


def guardar_config(cfg):
    import publicador as pub
    return pub.guardar_config(cfg)


def ocupante_actual(conn, room_no, fecha=None, dias_adelante=2):
    """Devuelve la reserva que ocupa la habitación en la fecha dada (hoy por defecto).

    Si nadie la ocupa, se mira la próxima llegada pero solo dentro de los siguientes
    `dias_adelante` días: así el huésped que llega mañana ya puede ver su itinerario,
    sin que aparezca en el QR alguien que llega la semana entrante.
    """
    hoy = fecha or datetime.date.today().isoformat()
    y, m, d = hoy.split("-")
    ddmmyy = f"{d}-{m}-{y[2:]}"

    def sql_fecha(col):
        return f"(substr({col},7,2)||'-'||substr({col},4,2)||'-'||substr({col},1,2))"

    objetivo = f"{y[2:]}-{m}-{d}"
    # El 'rowid' del desempate: si la misma habitación tiene DOS reservas activas que
    # empiezan el mismo día —no debería pasar, pero pasa cuando se duplica una reserva o
    # se mueve a alguien de cuarto sin cerrar la anterior—, el 'ORDER BY' de la fecha
    # sola no decide cuál gana, y el motor devolvía una cualquiera de las dos: la que
    # saliera según cómo hubiera recorrido la tabla. Con el índice de habitación esa
    # elección arbitraria habría cambiado, y el QR del cuarto mostraría al otro huésped.
    # Se fija en la más antigua, que es la que venía saliendo, y así deja de ser azar.
    fila = conn.execute(
        f"""SELECT * FROM reserva
            WHERE room_no = ? AND res_status != 'CANCELADA'
              AND {sql_fecha('arr_date')} <= ? AND {sql_fecha('dep_date')} >= ?
            ORDER BY {sql_fecha('arr_date')} DESC, rowid ASC LIMIT 1""",
        (room_no, objetivo, objetivo),
    ).fetchone()
    if fila:
        return dict(fila)

    # Nadie la ocupa: se busca la próxima llegada, pero solo si es dentro de pocos días
    limite = (datetime.date.fromisoformat(hoy) + datetime.timedelta(days=dias_adelante))
    ly, lm, ld = limite.isoformat().split("-")
    tope = f"{ly[2:]}-{lm}-{ld}"
    fila = conn.execute(
        f"""SELECT * FROM reserva
            WHERE room_no = ? AND res_status != 'CANCELADA'
              AND {sql_fecha('arr_date')} > ? AND {sql_fecha('arr_date')} <= ?
            ORDER BY {sql_fecha('arr_date')} ASC, rowid ASC LIMIT 1""",
        (room_no, objetivo, tope),
    ).fetchone()
    return dict(fila) if fila else None


def generar_qr_png(texto, tamano=10):
    qr = qrcode.QRCode(version=None, box_size=tamano, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage, fill_color="#1F3A2E", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def hoja_qr_pdf_urls(pares):
    """Hoja imprimible con el QR de cada habitación, para pegar en el cuarto.
    Se imprime una sola vez: el código no cambia aunque cambie el huésped.

    Recibe los pares (habitación, url) ya resueltos por publicador.url_habitacion,
    que es el único lugar que arma la dirección: si los enlaces llevan código
    secreto, hay que respetarlo o el QR impreso apuntaría a una página inexistente.
    """
    return _hoja_qr(pares)


def _hoja_qr(pares):
    buf = io.BytesIO()
    c = canvas_mod.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    cols, filas = 3, 4
    margen_x, margen_y = 0.6 * inch, 0.7 * inch
    ancho_celda = (ancho - 2 * margen_x) / cols
    alto_celda = (alto - 2 * margen_y) / filas

    for i, (room, url) in enumerate(pares):
        pos = i % (cols * filas)
        if i and pos == 0:
            c.showPage()
        col, fila = pos % cols, pos // cols
        x = margen_x + col * ancho_celda
        y = alto - margen_y - (fila + 1) * alto_celda

        img = ImageReader(generar_qr_png(url, tamano=8))
        lado = min(ancho_celda, alto_celda) - 52
        c.drawImage(img, x + (ancho_celda - lado) / 2, y + 34, width=lado, height=lado)

        c.setFillColor(VERDE)
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(x + ancho_celda / 2, y + 18, f"Room {room}")
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.grey)
        c.drawCentredString(x + ancho_celda / 2, y + 7, "Scan for your itinerary")

    c.save()
    buf.seek(0)
    return buf


def pagina_huesped_html(reserva, filas, nombre_bienvenida, horarios, whatsapp,
                        enlace_pdf=None, room_no=None, para_web=False, idioma="en",
                        comidas=None):
    """Página que ve el huésped al escanear el QR.

    Mantiene el formato oficial del lodge: fondo fotográfico, tarjeta blanca,
    verde institucional, las mismas tipografías y la misma tabla Day/Activity/
    Schedule/Details. En pantallas angostas la tabla se reordena en tarjetas para
    que siga siendo legible en el celular, conservando los mismos colores y estilo.
    """
    import traducciones as tr
    T = lambda k: tr.t(k, idioma)

    # En el sitio publicado los recursos viven un nivel arriba de la carpeta de la
    # habitación; sirviendo desde el propio sistema van en la raíz.
    pre = "../../assets" if para_web else "/assets"
    fnt = tr.fuentes_para(idioma)

    if not reserva:
        cuerpo = f"""<div class="aviso">
            <p>{T('sin_itinerario')}</p>
            <p class="chico">{T('consultar_recepcion')}</p></div>"""
    else:
        filas_html = "".join(f"""
          <tr>
            <td class="c-dia"><span class="et">{T('dia')}</span>{tr.formatear_horas(_dia_idioma(f.get('dia',''), idioma), idioma)}</td>
            <td class="c-act"><span class="et">{T('actividad')}</span>
                {tr.traducir_actividad(f.get('actividad') or '', idioma).replace(chr(10),'<br>')}
                {f'<div class="dur">{tr.traducir_texto(f["duracion"], idioma)}</div>' if f.get('duracion') else ''}
            </td>
            <td class="c-hor"><span class="et">{T('horario')}</span>{tr.formatear_horas(tr.traducir_texto(f.get('horario') or '', idioma), idioma).replace(chr(10),'<br>')}</td>
            <td class="c-det"><span class="et">{T('detalles')}</span>{tr.formatear_horas(tr.traducir_texto(f.get('detalles') or '', idioma), idioma).replace(chr(10),'<br>')}</td>
          </tr>""" for f in filas)

        cuerpo = f"""
          {f'<p class="hab">{T("habitacion")} {room_no}</p>' if room_no else ''}
          <h1>{T('bienvenida')} {nombre_bienvenida}</h1>
          <p class="sub">{T('sub1')}<br>{T('sub2')}</p>
          <table class="itin">
            <thead><tr><th>{T('dia')}</th><th>{T('actividad')}</th><th>{T('horario')}</th><th>{T('detalles')}</th></tr></thead>
            <tbody>{filas_html}</tbody>
          </table>
          {f'<p class="descarga"><a href="{enlace_pdf}" download>{T("descargar_pdf")}</a></p>' if enlace_pdf else ''}
          <p class="lema">{T('lema')}</p>
          <img class="logo" src="{pre}/logo.jpg" alt="Corcovado Wilderness Lodge">

          {_bloque_comidas(comidas, idioma) if comidas else ""}
          <h2>{T('titulo_horarios')}</h2>
          <div class="horarios">
            {"".join(f'<div><span>{tr.traducir_servicio(n, idioma)}</span><span>{tr.formatear_horas(h, idioma)}</span></div>' for n, h in horarios if n)}
          </div>
          <p class="wsp">{T('snacks')}<br><br>
             {T('whatsapp')}<br>
             <strong>{whatsapp}</strong></p>
          <p class="cierre">{T('cierre').replace(chr(10), '<br>')}</p>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your Itinerary — Corcovado Wilderness Lodge</title>
<style>
  @font-face {{ font-family:'Titulo'; src:url('{pre}/fonts/{fnt["titulo"]}'); }}
  @font-face {{ font-family:'TituloReg'; src:url('{pre}/fonts/{fnt["encabezado"]}'); }}
  @font-face {{ font-family:'Cuerpo'; src:url('{pre}/fonts/{fnt["cuerpo"]}'); }}
  @font-face {{ font-family:'Italica'; src:url('{pre}/fonts/{fnt["italica"]}'); }}

  :root {{ --verde:#1F3A2E; --verde-claro:#2C4A3E; --borde:#D9D2C2; }}
  * {{ box-sizing:border-box; }}
  html, body {{ margin:0; padding:0; }}
  body {{
    font-family:'Cuerpo', -apple-system, "Segoe UI", Arial, sans-serif;
    color:#24291F;
    background:url('{pre}/itinerario/fondo.jpg') center top / cover no-repeat fixed #1D332A;
    padding:18px 12px 34px;
  }}
  .marco {{
    max-width:820px; margin:0 auto; background:#fff;
    border-radius:34px 34px 26px 26px;   /* arco superior, como la tarjeta del PDF */
    padding:26px 20px 24px;
    box-shadow:0 6px 26px rgba(0,0,0,.28);
  }}
  h1 {{ font-family:'Titulo', Georgia, serif; font-size:26px; text-align:center;
        color:#000; margin:2px 0 8px; font-weight:400; }}
  .sub {{ font-family:'Italica', Georgia, serif; text-align:center; font-size:14px;
          color:#24291F; margin:0 0 18px; line-height:1.55; }}

  table.itin {{ width:100%; border-collapse:collapse; }}
  table.itin th {{
    background:var(--verde); color:#fff; font-family:'TituloReg', Georgia, serif;
    font-weight:400; font-size:15px; padding:9px 6px; border:1px solid var(--borde);
  }}
  table.itin td {{ border:1px solid var(--borde); padding:9px 8px; font-size:13.5px;
                   vertical-align:middle; text-align:center; line-height:1.45; }}
  td.c-dia {{ background:var(--verde); color:#fff; font-family:'TituloReg', Georgia, serif;
              font-size:15px; white-space:nowrap; }}
  td.c-act {{ font-weight:600; color:var(--verde); }}
  .dur {{ font-size:11px; font-weight:400; color:#55534B; margin-top:2px; }}
  .et {{ display:none; }}   /* etiquetas solo visibles en celular */

  .lema {{ font-family:'Titulo', Georgia, serif; text-align:center; font-size:17px;
           color:#1D332A; margin:22px 0 12px; font-weight:400; }}
  .logo {{ display:block; margin:0 auto; max-width:190px; }}

  h2 {{ font-family:'Titulo', Georgia, serif; font-size:23px; text-align:center;
        color:#1D332A; margin:30px 0 14px; font-weight:400; letter-spacing:1px; }}
  .horarios {{ max-width:420px; margin:0 auto; }}
  .horarios div {{ display:flex; justify-content:space-between; gap:14px; font-size:14px;
                   padding:6px 2px; border-bottom:1px solid var(--borde); }}
  .wsp {{ text-align:center; font-size:14px; margin-top:22px; line-height:1.6; }}
  .cierre {{ font-family:'Titulo', Georgia, serif; text-align:center; font-size:13px;
             color:#1D332A; margin-top:22px; line-height:1.6; font-weight:400; }}
  .descarga {{ text-align:center; margin:18px 0 4px; }}
  .descarga a {{ display:inline-block; background:var(--verde); color:#fff;
                 text-decoration:none; font-size:13px; letter-spacing:.4px;
                 padding:9px 20px; border-radius:22px; }}
  .hab {{ text-align:center; font-size:11px; letter-spacing:1.4px; text-transform:uppercase;
          color:#6E6A5C; margin:0 0 6px; }}
  .aviso {{ text-align:center; padding:46px 10px; color:#6E6A5C; }}
  .chico {{ font-size:12.5px; }}

  /* En celular la tabla se reordena en tarjetas, manteniendo los mismos colores */
  @media (max-width: 640px) {{
    body {{ padding:10px 8px 26px; }}
    .marco {{ border-radius:24px; padding:20px 14px; }}
    h1 {{ font-size:22px; }}
    table.itin thead {{ display:none; }}
    table.itin, table.itin tbody, table.itin tr, table.itin td {{ display:block; width:100%; }}
    table.itin tr {{ border:1px solid var(--borde); border-radius:10px;
                     overflow:hidden; margin-bottom:13px; }}
    table.itin td {{ border:none; border-bottom:1px solid var(--borde);
                     text-align:left; padding:9px 12px; }}
    table.itin td:last-child {{ border-bottom:none; }}
    td.c-dia {{ font-size:15px; padding:9px 12px; }}
    .et {{ display:block; font-family:'Cuerpo',sans-serif; font-size:10px;
           text-transform:uppercase; letter-spacing:.8px; opacity:.6; margin-bottom:3px; }}
    td.c-dia .et {{ color:#DCE6DF; opacity:.85; }}
  }}
</style></head>
<body><div class="marco">{cuerpo}</div></body></html>"""


def _dia_idioma(texto_dia, idioma):
    """Adapta 'August 05' al idioma. Si recepción escribió otra cosa, se deja igual."""
    if idioma == "en" or not texto_dia:
        return texto_dia
    import traducciones as tr
    meses_en = ["January","February","March","April","May","June","July",
                "August","September","October","November","December"]
    mes = dia = None
    for p in texto_dia.replace(",", " ").split():
        if p in meses_en:
            mes = meses_en.index(p) + 1
        elif p.isdigit():
            dia = int(p)
    if not mes or not dia:
        return texto_dia
    nombre = tr.MESES.get(idioma, tr.MESES["en"])[mes - 1]
    return tr.FORMATO_FECHA.get(idioma, tr.FORMATO_FECHA["en"]).format(dia=dia, mes=nombre)


def _bloque_comidas(comidas, idioma):
    """Dónde almuerza y cena el huésped en los próximos días.

    Va solo en la página del código QR, no en el PDF impreso: la distribución de
    los restaurantes se recalcula cuando entra un PDF nuevo, así que un papel
    impreso quedaría desactualizado. El QR siempre muestra el dato vigente.
    """
    import traducciones as tr
    titulos = {
        "en": ("Your restaurants", "Day", "Lunch", "Dinner", "Time"),
        "es": ("Sus restaurantes", "Día", "Almuerzo", "Cena", "Hora"),
        "pt": ("Seus restaurantes", "Dia", "Almoço", "Jantar", "Hora"),
        "fr": ("Vos restaurants", "Jour", "Déjeuner", "Dîner", "Heure"),
        "ru": ("Ваши рестораны", "День", "Обед", "Ужин", "Время"),
    }
    t = titulos.get(idioma, titulos["en"])
    filas = "".join(
        f"""<tr><td class="c-dia"><span class="et">{t[1]}</span>{c.get('dia','')}</td>
            <td><span class="et">{t[2]}</span>{c.get('almuerzo') or '—'}</td>
            <td><span class="et">{t[3]}</span>{c.get('cena') or '—'}</td>
            <td><span class="et">{t[4]}</span>{c.get('hora') or '—'}</td></tr>"""
        for c in comidas)
    return f"""<h2>{t[0]}</h2>
      <table class="itin"><thead><tr><th>{t[1]}</th><th>{t[2]}</th><th>{t[3]}</th>
        <th>{t[4]}</th></tr></thead><tbody>{filas}</tbody></table>"""
