"""
La página que abre el huésped con su enlace para mandar su ropa a lavar.

Es pública —el código del enlace es lo que la abre— y solo muestra SU reserva.

QUÉ CAMBIA RESPECTO DEL FORMULARIO DE GOOGLE QUE SE USA HOY
-----------------------------------------------------------
El formulario tenía seis preguntas. Aquí quedan tres y media, y no es por recortar:

  · **Nombre** y **habitación** se van. El enlace ya sabe quién es, y eran justo las dos
    que se contestaban mal: quien escribía 23 en vez de 32 no recibía su ropa. Además, si
    el huésped se cambia de cuarto, housekeeping ve dónde está AHORA.
  · **La fecha** se queda, pero solo ofrece días de su estadía.
  · **La hora de recolección** se queda, y ahora sirve de verdad: la página le dice si con
    esa hora la ropa vuelve el mismo día. El formulario se lo preguntaba y no le
    contestaba nada; el reclamo llegaba al día siguiente.
  · **Las cantidades** dejan de ser una cuadrícula de 1 a 6. Ese tope era de Google Forms,
    no del hotel, y una familia de cuatro lo pasa fácil.

EL IDIOMA
---------
Igual que en el spa: por omisión INGLÉS, con botón EN / ES siempre visible. El enlace
puede traerlo puesto (`?idioma=es`) y la pantalla de Housekeeping lo arma con el idioma
del ITINERARIO de ese huésped, así que el que copia recepción ya sale en su idioma.

El HTML va aquí y no en un archivo aparte por lo mismo que el del spa: es una sola página
que se sirve sola, y un archivo más que desplegar no se paga.
"""
import json

TEXTOS = {
    "en": {
        "titulo": "Laundry",
        "cargando": "Loading…",
        "enlace_malo_t": "This link is no longer valid",
        "enlace_malo_d": "The reservation may have ended. Ask reception for a new one.",
        "hola": "Hello, {nombre}",
        "habitacion": "Room {hab} · {desde} to {hasta}",
        "ya_pedido": "What you've sent us",
        "pide_t": "Send your laundry",
        "pide_d": "We pick up between {abre} and {cierra}.",
        "dia": "Day",
        "hora": "Pick-up time",
        "hora_ayuda": "— tap the one that suits you",
        "prendas": "What are you sending?",
        "prendas_ayuda": "Tap + for each item. Leave the rest at zero.",
        "total": "Total",
        "total_ayuda": "Charged to your room.",
        "total_parcial": "Some items don't have a price listed — reception will confirm "
                         "those with you.",
        "a_consultar": "on request",
        "nota": "Anything else we should know",
        "nota_ayuda": "Stains, delicate fabrics, anything at all.",
        "enviar": "Send to housekeeping",
        "enviando": "Sending…",
        "mismo_dia_si": "Picked up at {hora}, your laundry comes back the same day.",
        "mismo_dia_no": "Picked up at {hora}, it comes back tomorrow. Before {tope} it "
                        "comes back the same day.",
        "elige_prenda": "Add at least one item.",
        "elige_dia": "Choose the day first.",
        "listo_t": "Got it — thank you",
        "listo_d": "Housekeeping will confirm and come by to collect. You'll see it "
                   "here.",
        "otro": "Send another bag",
        "aviso_no_es_firme": "This is a request. Housekeeping confirms it.",
        "estados": {
            "SOLICITADO": "awaiting confirmation",
            "CONFIRMADO": "confirmed",
            "RECOGIDO": "picked up",
            "ENTREGADO": "delivered",
        },
        "vuelve_hoy": "back today",
        "vuelve_manana": "back tomorrow",
        "pie": "Corcovado Wilderness Lodge",
    },
    "es": {
        "titulo": "Lavandería",
        "cargando": "Cargando…",
        "enlace_malo_t": "Este enlace ya no sirve",
        "enlace_malo_d": "Puede que la reserva haya terminado. Pedile uno nuevo a recepción.",
        "hola": "Hola, {nombre}",
        "habitacion": "Habitación {hab} · {desde} al {hasta}",
        "ya_pedido": "Lo que nos mandaste",
        "pide_t": "Mandá tu ropa",
        "pide_d": "Pasamos a recoger entre las {abre} y las {cierra}.",
        "dia": "Día",
        "hora": "Hora de recolección",
        "hora_ayuda": "— tocá la que te sirva",
        "prendas": "¿Qué nos mandás?",
        "prendas_ayuda": "Tocá + por cada prenda. El resto dejalo en cero.",
        "total": "Total",
        "total_ayuda": "Se carga a tu habitación.",
        "total_parcial": "Algunas prendas no tienen precio en la lista — recepción te las "
                         "confirma.",
        "a_consultar": "a consultar",
        "nota": "Algo que debamos saber",
        "nota_ayuda": "Manchas, telas delicadas, lo que sea.",
        "enviar": "Mandar a housekeeping",
        "enviando": "Mandando…",
        "mismo_dia_si": "Recogida a las {hora}, tu ropa vuelve el mismo día.",
        "mismo_dia_no": "Recogida a las {hora}, vuelve mañana. Antes de las {tope} "
                        "vuelve el mismo día.",
        "elige_prenda": "Agregá al menos una prenda.",
        "elige_dia": "Elegí primero el día.",
        "listo_t": "Listo — gracias",
        "listo_d": "Housekeeping lo confirma y pasa a recogerlo. Lo vas a ver acá.",
        "otro": "Mandar otra bolsa",
        "aviso_no_es_firme": "Esto es un pedido. Housekeeping lo confirma.",
        "estados": {
            "SOLICITADO": "por confirmar",
            "CONFIRMADO": "confirmado",
            "RECOGIDO": "recogida",
            "ENTREGADO": "entregada",
        },
        "vuelve_hoy": "vuelve hoy",
        "vuelve_manana": "vuelve mañana",
        "pie": "Corcovado Wilderness Lodge",
    },
}

IDIOMA_POR_DEFECTO = "en"


def idioma_valido(idioma):
    """El idioma pedido si la página lo tiene, y si no el inglés.

    Se acepta 'es-CR' o 'ES' y se queda con 'es', por lo mismo que en el spa: el idioma
    puede venir de un enlace escrito a mano o del navegador del huésped.
    """
    corto = str(idioma or "").strip().lower().replace("_", "-").split("-")[0]
    return corto if corto in TEXTOS else IDIOMA_POR_DEFECTO


def html(conf_no, token, idioma=None):
    return (_PLANTILLA
            .replace("{{CONF}}", conf_no)
            .replace("{{TOKEN}}", token)
            .replace("{{IDIOMA}}", idioma_valido(idioma))
            .replace("{{TEXTOS}}", json.dumps(TEXTOS, ensure_ascii=False)))


_PLANTILLA = r"""<!doctype html>
<html lang="{{IDIOMA}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Laundry · Corcovado Wilderness Lodge</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Karla:wght@400;600&display=swap">
<style>
  :root {
    --verde:#2E4034; --verde-claro:#5B7355; --arena:#F5F1E8; --texto:#24291F;
    --suave:#7A7566; --borde:#DED8C8; --aviso-f:#FBF3E0; --aviso-t:#7A5B18;
    --ok-f:#E8F0E4; --ok-t:#2E5A2E;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--arena); color:var(--texto);
         font-family:Karla,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         font-size:16px; line-height:1.55; }
  .envoltorio { max-width:640px; margin:0 auto; padding:0 18px 56px; }
  header { background:var(--verde); color:#fff; padding:26px 18px 22px; text-align:center;
           position:relative; }
  header p.lodge { font-family:"Cormorant Garamond",Georgia,serif; font-size:13px;
                   letter-spacing:.18em; text-transform:uppercase; margin:0; opacity:.85; }
  header h1 { font-family:"Cormorant Garamond",Georgia,serif; font-weight:600;
              font-size:30px; margin:6px 0 0; }
  .idiomas { position:absolute; top:14px; right:14px; display:flex; gap:4px; }
  .idiomas button { font-family:inherit; font-size:12.5px; font-weight:600;
    padding:5px 11px; border-radius:20px; cursor:pointer;
    border:1px solid rgba(255,255,255,.45); background:transparent; color:#fff; }
  .idiomas button.puesto { background:#fff; color:var(--verde); border-color:#fff; }
  .tarjeta { background:#fff; border:1px solid var(--borde); border-radius:12px;
             padding:18px; margin-top:18px; }
  h2 { font-family:"Cormorant Garamond",Georgia,serif; font-size:21px; font-weight:600;
       margin:0 0 4px; color:var(--verde); }
  .sub { color:var(--suave); font-size:14px; margin:0 0 14px; }
  label { display:block; font-size:13px; font-weight:600; margin:14px 0 5px; }
  .ayuda { font-weight:400; color:var(--suave); font-size:12.5px; }
  input[type=date], textarea {
    width:100%; padding:11px 12px; font-size:16px; font-family:inherit;
    border:1px solid var(--borde); border-radius:8px; background:#fff; color:var(--texto); }
  textarea { resize:vertical; }
  .horas { display:flex; flex-wrap:wrap; gap:7px; margin-top:7px; }
  .horas button { padding:9px 13px; font-size:15px; font-family:inherit; cursor:pointer;
    border:1px solid var(--borde); border-radius:8px; background:#fff; color:var(--texto); }
  .horas button.puesta { background:var(--verde); border-color:var(--verde); color:#fff; }
  /* La lista de prendas: nombre a la izquierda, contador a la derecha. Con el pulgar en
     el teléfono, los botones grandes y separados son lo que evita el error. */
  .prendas { margin-top:8px; border:1px solid var(--borde); border-radius:10px;
             overflow:hidden; }
  .prenda { display:flex; align-items:center; gap:12px; padding:10px 12px;
            border-bottom:1px solid var(--borde); }
  .prenda:last-child { border-bottom:none; }
  .prenda.puesta { background:#F7FAF5; }
  .prenda .nombre { flex:1; font-size:15.5px; }
  .prenda .precio { font-size:13px; color:var(--suave); min-width:52px; text-align:right; }
  .prenda.puesta .precio { color:var(--verde); font-weight:600; }
  /* El total, pegado al final de la lista para que se lea como su cierre y no como otra
     cosa suelta. Va tabular: los números tienen que alinearse al cambiar de cantidad. */
  .total { display:flex; justify-content:space-between; align-items:baseline;
           border-top:2px solid var(--verde); margin-top:-1px; padding:13px 12px;
           background:#F7FAF5; border-radius:0 0 10px 10px; }
  .total .etiqueta-total { font-weight:600; font-size:15px; }
  .total .cifra { font-size:22px; font-weight:600; color:var(--verde);
                  font-variant-numeric:tabular-nums; }
  .total-nota { font-size:12.5px; color:var(--suave); margin:6px 2px 0; }
  .contador { display:flex; align-items:center; gap:0; }
  .contador button { width:38px; height:38px; font-size:20px; font-family:inherit;
    line-height:1; cursor:pointer; border:1px solid var(--borde); background:#fff;
    color:var(--verde); }
  .contador button:first-child { border-radius:8px 0 0 8px; }
  .contador button:last-child { border-radius:0 8px 8px 0; }
  .contador button[disabled] { opacity:.35; cursor:default; }
  .contador .n { width:44px; text-align:center; font-size:16px; font-weight:600;
    border-top:1px solid var(--borde); border-bottom:1px solid var(--borde);
    padding:8px 0; background:#fff; }
  .prenda.puesta .n { color:var(--verde); }
  .aviso { margin-top:12px; padding:11px 13px; border-radius:9px; font-size:14px;
           background:var(--aviso-f); color:var(--aviso-t); }
  .aviso.bien { background:var(--ok-f); color:var(--ok-t); }
  .enviar { width:100%; margin-top:18px; padding:14px; font-size:16.5px; font-weight:600;
    font-family:inherit; border:none; border-radius:9px; background:var(--verde);
    color:#fff; cursor:pointer; }
  .enviar[disabled] { opacity:.5; cursor:default; }
  .mio { display:flex; justify-content:space-between; gap:12px; padding:11px 0;
         border-bottom:1px solid var(--borde); font-size:15px; }
  .mio:last-child { border-bottom:none; }
  .mio .cuando { color:var(--suave); font-size:13px; }
  .etiqueta { font-size:11.5px; font-weight:600; text-transform:uppercase;
    letter-spacing:.04em; padding:3px 9px; border-radius:20px; white-space:nowrap;
    background:var(--aviso-f); color:var(--aviso-t); align-self:flex-start; }
  .etiqueta.ok { background:var(--ok-f); color:var(--ok-t); }
  .pie { text-align:center; color:var(--suave); font-size:12.5px; margin-top:26px; }
  .centro { text-align:center; padding:40px 20px; color:var(--suave); }
</style>
</head>
<body>
<header>
  <div class="idiomas">
    <button id="b-en" onclick="ponerIdioma('en')">EN</button>
    <button id="b-es" onclick="ponerIdioma('es')">ES</button>
  </div>
  <p class="lodge">Corcovado Wilderness Lodge</p>
  <h1 id="t-titulo">Laundry</h1>
</header>
<div class="envoltorio" id="todo">
  <p class="centro" id="cargando">Loading…</p>
</div>

<script>
const CONF = "{{CONF}}";
const TOKEN = "{{TOKEN}}";
const TEXTOS = {{TEXTOS}};
let IDIOMA = "{{IDIOMA}}";
let DATOS = null;
let ELEGIDO = { fecha: "", hora: "", items: {}, nota: "" };
let ENVIANDO = false;

// La elección de idioma se recuerda en el propio teléfono: al volver a abrir el enlace
// no hay que cambiarla otra vez.
try {
  const guardado = localStorage.getItem("hk_idioma");
  if (guardado && TEXTOS[guardado]) IDIOMA = guardado;
} catch (e) {}

function T(clave) {
  const t = TEXTOS[IDIOMA] || TEXTOS.en;
  return t[clave] !== undefined ? t[clave] : (TEXTOS.en[clave] || clave);
}
function rellenar(txt, valores) {
  return String(txt).replace(/\{(\w+)\}/g, (_, k) => valores[k] !== undefined ? valores[k] : "");
}
function esc(t) {
  return String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function ponerIdioma(id) {
  if (!TEXTOS[id]) return;
  IDIOMA = id;
  try { localStorage.setItem("hk_idioma", id); } catch (e) {}
  document.documentElement.lang = id;
  // No se pierde lo ya escrito: se vuelve a dibujar con lo que hay en ELEGIDO, que es
  // justo cuando alguien cambia el idioma — después de empezar a leer.
  dibujar();
}

function marcarIdioma() {
  document.getElementById("b-en").classList.toggle("puesto", IDIOMA === "en");
  document.getElementById("b-es").classList.toggle("puesto", IDIOMA === "es");
  document.getElementById("t-titulo").textContent = T("titulo");
  document.title = T("titulo") + " · Corcovado Wilderness Lodge";
}

async function cargar() {
  try {
    const r = await fetch(`/api/housekeeping/publico/${CONF}/${TOKEN}`);
    if (!r.ok) throw new Error("enlace");
    DATOS = await r.json();
    if (!ELEGIDO.fecha) ELEGIDO.fecha = hoyDentroDeLaEstadia();
  } catch (e) {
    DATOS = "malo";
  }
  dibujar();
}

function hoyDentroDeLaEstadia() {
  const d = new Date();
  const hoy = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  if (!DATOS || !DATOS.estadia_desde) return hoy;
  if (hoy < DATOS.estadia_desde) return DATOS.estadia_desde;
  if (DATOS.estadia_hasta && hoy > DATOS.estadia_hasta) return DATOS.estadia_hasta;
  return hoy;
}

function totalElegido() {
  return Object.values(ELEGIDO.items).reduce((a, b) => a + (b || 0), 0);
}

function precioDe(codigo) {
  const p = (DATOS.prendas || []).find(x => x.codigo === codigo);
  return p && p.precio_centavos != null ? p.precio_centavos : null;
}

// Se suma en CENTAVOS enteros. Sumando decimales, doce veces 2.10 da 25.199999999999996,
// y ese número acabaría en la pantalla de un huésped.
function cuentaElegida() {
  let centavos = 0, completo = true;
  for (const [codigo, cantidad] of Object.entries(ELEGIDO.items)) {
    const precio = precioDe(codigo);
    if (precio == null) { completo = false; continue; }
    centavos += precio * cantidad;
  }
  return { centavos, completo };
}

function comoPlata(centavos) {
  const m = (DATOS && DATOS.moneda) || "$";
  return m + (centavos / 100).toLocaleString(IDIOMA === "es" ? "es-CR" : "en-US",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function cambiar(codigo, delta) {
  const tope = (DATOS.config && DATOS.config.max_por_prenda) || 99;
  const ahora = ELEGIDO.items[codigo] || 0;
  const nuevo = Math.max(0, Math.min(ahora + delta, tope));
  if (nuevo === 0) delete ELEGIDO.items[codigo]; else ELEGIDO.items[codigo] = nuevo;
  dibujar();
}

function ponerHora(h) { ELEGIDO.hora = h; dibujar(); }

function avisoMismoDia() {
  const tope = DATOS.config && DATOS.config.hora_tope_mismo_dia;
  // Sin hora tope el hotel no promete plazo, y entonces no se dice nada: inventar una
  // promesa es peor que no darla.
  if (!tope || !ELEGIDO.hora) return null;
  const bien = ELEGIDO.hora <= tope;
  return {
    bien,
    texto: bien
      ? rellenar(T("mismo_dia_si"), { hora: ELEGIDO.hora })
      : rellenar(T("mismo_dia_no"), { hora: ELEGIDO.hora, tope }),
  };
}

function dibujar() {
  marcarIdioma();
  const caja = document.getElementById("todo");

  if (DATOS === "malo") {
    caja.innerHTML = `<div class="tarjeta"><h2>${esc(T("enlace_malo_t"))}</h2>
      <p class="sub">${esc(T("enlace_malo_d"))}</p></div>`;
    return;
  }
  if (!DATOS) {
    caja.innerHTML = `<p class="centro">${esc(T("cargando"))}</p>`;
    return;
  }

  const cfg = DATOS.config || {};
  let h = "";

  h += `<div class="tarjeta">
    <h2>${esc(rellenar(T("hola"), { nombre: (DATOS.nombre || "").split(",")[0] }))}</h2>
    <p class="sub">${esc(rellenar(T("habitacion"), {
      hab: DATOS.room_no || "—", desde: DATOS.estadia_desde || "", hasta: DATOS.estadia_hasta || "",
    }))}</p>`;

  if (DATOS.mis_pedidos && DATOS.mis_pedidos.length) {
    h += `<label style="margin-top:6px;">${esc(T("ya_pedido"))}</label>`;
    DATOS.mis_pedidos.forEach((p) => {
      const est = (T("estados") || {})[p.estado] || p.estado;
      const listo = p.estado === "CONFIRMADO" || p.estado === "RECOGIDO" || p.estado === "ENTREGADO";
      let cuando = `${p.fecha}${p.hora ? " · " + p.hora : ""}`;
      if (p.mismo_dia === 1) cuando += " · " + T("vuelve_hoy");
      else if (p.mismo_dia === 0) cuando += " · " + T("vuelve_manana");
      // El total que se le COTIZÓ ese día, no uno recalculado con la lista de hoy.
      if (p.total) cuando += " · " + p.total;
      h += `<div class="mio"><div><div>${esc(p.resumen || "")}</div>
        <div class="cuando">${esc(cuando)}</div></div>
        <span class="etiqueta ${listo ? "ok" : ""}">${esc(est)}</span></div>`;
    });
  }
  h += `</div>`;

  h += `<div class="tarjeta">
    <h2>${esc(T("pide_t"))}</h2>
    <p class="sub">${esc(rellenar(T("pide_d"), { abre: cfg.abre || "", cierra: cfg.cierra || "" }))}</p>

    <label for="f">${esc(T("dia"))}</label>
    <input type="date" id="f" value="${esc(ELEGIDO.fecha)}"
           min="${esc(DATOS.estadia_desde || "")}" max="${esc(DATOS.estadia_hasta || "")}"
           onchange="ELEGIDO.fecha=this.value;dibujar();">

    <label>${esc(T("hora"))} <span class="ayuda">${esc(T("hora_ayuda"))}</span></label>
    <div class="horas">`;
  (DATOS.horas || []).forEach((hora) => {
    h += `<button type="button" class="${ELEGIDO.hora === hora ? "puesta" : ""}"
            onclick="ponerHora('${esc(hora)}')">${esc(hora)}</button>`;
  });
  h += `</div>`;

  const aviso = avisoMismoDia();
  if (aviso) {
    h += `<div class="aviso ${aviso.bien ? "bien" : ""}">${esc(aviso.texto)}</div>`;
  }

  h += `<label style="margin-top:18px;">${esc(T("prendas"))}
        <span class="ayuda">${esc(T("prendas_ayuda"))}</span></label>
        <div class="prendas">`;
  (DATOS.prendas || []).forEach((p) => {
    const n = ELEGIDO.items[p.codigo] || 0;
    // Con cantidad puesta se muestra el SUBTOTAL de esa línea, no el precio unitario:
    // es lo que el huésped quiere comprobar cuando el total no le cuadra.
    const cifra = p.precio_centavos == null
      ? T("a_consultar")
      : (n ? comoPlata(p.precio_centavos * n) : comoPlata(p.precio_centavos));
    h += `<div class="prenda ${n ? "puesta" : ""}">
      <div class="nombre">${esc(p.nombre)}</div>
      <div class="precio">${esc(cifra)}</div>
      <div class="contador">
        <button type="button" onclick="cambiar('${esc(p.codigo)}',-1)" ${n ? "" : "disabled"}
                aria-label="menos">−</button>
        <div class="n">${n}</div>
        <button type="button" onclick="cambiar('${esc(p.codigo)}',1)" aria-label="más">+</button>
      </div></div>`;
  });

  // El total solo aparece cuando ya eligió algo: un "$0.00" antes de tocar nada no le
  // dice nada a nadie.
  const cuenta = cuentaElegida();
  if (totalElegido() > 0) {
    h += `<div class="total">
      <span class="etiqueta-total">${esc(T("total"))}</span>
      <span class="cifra">${esc(comoPlata(cuenta.centavos))}</span>
    </div>`;
  }
  h += `</div>`;
  if (totalElegido() > 0) {
    h += `<p class="total-nota">${esc(T("total_ayuda"))}</p>`;
    if (!cuenta.completo) {
      h += `<p class="total-nota">${esc(T("total_parcial"))}</p>`;
    }
  }

  h += `<label for="nota" style="margin-top:18px;">${esc(T("nota"))}
          <span class="ayuda">${esc(T("nota_ayuda"))}</span></label>
        <textarea id="nota" rows="3"
          oninput="ELEGIDO.nota=this.value;">${esc(ELEGIDO.nota)}</textarea>`;

  h += `<div class="aviso" style="margin-top:16px;">${esc(T("aviso_no_es_firme"))}</div>`;
  h += `<button class="enviar" id="enviar" onclick="enviar()"
          ${(!ELEGIDO.fecha || totalElegido() === 0 || ENVIANDO) ? "disabled" : ""}>
        ${esc(ENVIANDO ? T("enviando") : T("enviar"))}</button>`;
  h += `<p id="error" class="aviso" style="display:none;"></p>`;
  h += `</div><p class="pie">${esc(T("pie"))}</p>`;

  caja.innerHTML = h;
}

async function enviar() {
  if (ENVIANDO) return;
  if (!ELEGIDO.fecha) return mostrarError(T("elige_dia"));
  if (totalElegido() === 0) return mostrarError(T("elige_prenda"));

  ENVIANDO = true;
  dibujar();
  try {
    const items = Object.entries(ELEGIDO.items)
      .map(([codigo, cantidad]) => ({ codigo, cantidad }));
    const r = await fetch(`/api/housekeeping/publico/${CONF}/${TOKEN}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fecha: ELEGIDO.fecha, hora: ELEGIDO.hora,
        nota: ELEGIDO.nota, items,
      }),
    });
    const cuerpo = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(cuerpo.detail || "No se pudo enviar");
    DATOS = cuerpo;
    ELEGIDO = { fecha: ELEGIDO.fecha, hora: "", items: {}, nota: "" };
    ENVIANDO = false;
    gracias();
  } catch (e) {
    ENVIANDO = false;
    dibujar();
    mostrarError(e.message);
  }
}

function mostrarError(texto) {
  const e = document.getElementById("error");
  if (!e) return;
  e.textContent = texto;
  e.style.display = "block";
  e.scrollIntoView({ behavior: "smooth", block: "center" });
}

function gracias() {
  const caja = document.getElementById("todo");
  caja.innerHTML = `<div class="tarjeta" style="text-align:center;">
      <h2>${esc(T("listo_t"))}</h2>
      <p class="sub">${esc(T("listo_d"))}</p>
      <button class="enviar" onclick="dibujar()">${esc(T("otro"))}</button>
    </div><p class="pie">${esc(T("pie"))}</p>`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

cargar();
</script>
</body>
</html>
"""
