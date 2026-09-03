"""
La página que abre el huésped con su enlace para pedir una cita en el spa.

Es pública —el código del enlace es lo que la abre— y solo muestra SU reserva.

EL IDIOMA
---------
Por omisión va en INGLÉS, que es el idioma de la mayoría de los huéspedes del lodge, y
tiene un botón EN / ES siempre visible para cambiarlo en el momento.

El enlace puede traerlo puesto (`?idioma=es`), y la pantalla del Spa lo arma con el
idioma del ITINERARIO de ese huésped: si su itinerario está en español, el enlace que
recepción copia ya sale en español. Así nadie tiene que acordarse.

La elección se recuerda en el propio teléfono, para que al volver a abrirlo no haya que
cambiarlo otra vez.

OTRAS DECISIONES QUE IMPORTAN
-----------------------------
· Las respuestas médicas NO vienen precargadas. Un enlace se reenvía por WhatsApp, y no
  tiene por qué exponer las alergias de la habitación 23 a quien lo reciba. Son las
  MISMAS once preguntas del formulario que el spa ya usaba; el cruce con lo que el
  sistema sabe se hace después, del lado del spa.
· El huésped PIDE, no reserva. Se le muestran las horas libres para que no pida una que
  no existe, pero la confirma el spa. Se le dice claramente para que no se vaya creyendo
  que ya tiene la cita.
· Sin instalar nada, sin cuenta y sin escribir su habitación: el enlace ya sabe quién es.
  Ese era el error fácil del formulario anterior.

El HTML va aquí y no en un archivo aparte porque es una sola página que se sirve sola,
igual que la del código QR: un archivo más que desplegar por 300 líneas no se paga.
"""
import json

# Los dos idiomas de la página. Está armado como diccionario para que agregar otro sea
# una entrada más y no tocar el HTML — el itinerario ya maneja cinco, y el día que haga
# falta portugués aquí, se agrega aquí.
#
# El inglés va primero a propósito: es el idioma base y el que se usa si algo falta.
TEXTOS = {
    "en": {
        "titulo": "Spa",
        "cargando": "Loading…",
        "enlace_malo_t": "This link is no longer valid",
        "enlace_malo_d": "The reservation may have ended. Ask reception for a new one.",
        "hola": "Hello, {nombre}",
        "habitacion": "Room {hab} · {desde} to {hasta}",
        "ya_pedido": "What you have booked",
        "confirmada": "confirmed",
        "por_confirmar": "awaiting confirmation",
        "pide_t": "Book your treatment",
        "pide_d": "The spa is open from {abre} to {cierra}.",
        "tratamiento": "Treatment",
        "elige_uno": "Choose one…",
        "minutos": "minutes",
        "dia": "Day",
        "hora": "Time",
        "hora_ayuda": "— tap the one that suits you",
        "elige_antes": "Choose the treatment and the day first.",
        "buscando": "Looking for available times…",
        "sin_hueco": "There is no room left for {min} minutes that day.",
        "sin_hueco2": "Try another day, or talk to reception.",
        "es_solicitud": ("This is a <strong>request</strong>. The spa will confirm it; "
                         "if that time is no longer free, we will offer you another."),
        "antes_t": "Before your treatment",
        "antes_d": "For your health and safety. Only the spa team sees this.",
        "q1": "Any medical condition we should know about?",
        "q1_ph": "If there is none, write “none”",
        "q2": "Any recent surgery?",
        "q3": "Any allergies in general?",
        "q3_ph": "If there are none, write “none”",
        "q4": "Are you pregnant?",
        "q5": "Have you been diving in the last 24 hours?",
        "q5_ayuda": "— here or before arriving",
        "q6": "Terms and conditions",
        "q6_acepto": "I agree with the terms and conditions",
        "enviar": "Book the treatment",
        "enviando": "Sending…",
        "si": "Yes",
        "no": "No",
        "falta_trat": "Choose the treatment.",
        "falta_dia": "Choose the day.",
        "falta_hora": "Choose the time.",
        "falta_q": "Please answer the question about {que}.",
        "falta_terminos": "You need to accept the terms and conditions to book.",
        "sin_conexion": "No connection. Please try again in a moment.",
        "error_horas": "The times could not be loaded. Please try again.",
        "listo_t": "Done, we got it.",
        "listo_d": ("The spa will confirm your time. You can book another treatment "
                    "here if you wish."),
        "pie": "Any questions, reception will help you.",
        "q2_nombre": "recent surgery",
        "q4_nombre": "pregnancy",
        "q5_nombre": "diving in the last 24 hours",
    },
    "es": {
        "titulo": "Spa",
        "cargando": "Cargando…",
        "enlace_malo_t": "Este enlace ya no sirve",
        "enlace_malo_d": "Puede que la reserva haya terminado. Pídele uno nuevo a recepción.",
        "hola": "Hola, {nombre}",
        "habitacion": "Habitación {hab} · del {desde} al {hasta}",
        "ya_pedido": "Lo que ya tienes pedido",
        "confirmada": "confirmada",
        "por_confirmar": "por confirmar",
        "pide_t": "Pide tu tratamiento",
        "pide_d": "El spa abre de {abre} a {cierra}.",
        "tratamiento": "Tratamiento",
        "elige_uno": "Elige uno…",
        "minutos": "minutos",
        "dia": "Día",
        "hora": "Hora",
        "hora_ayuda": "— toca la que te convenga",
        "elige_antes": "Elige primero el tratamiento y el día.",
        "buscando": "Buscando horas…",
        "sin_hueco": "Ese día ya no queda espacio para {min} minutos.",
        "sin_hueco2": "Prueba otro día, o escríbenos a recepción.",
        "es_solicitud": ("Esto es una <strong>solicitud</strong>. El spa te la confirma; "
                         "si esa hora ya no estuviera libre, te proponemos otra."),
        "antes_t": "Antes de tu tratamiento",
        "antes_d": "Por tu salud y seguridad. Solo lo ve el equipo del spa.",
        "q1": "¿Alguna condición médica de la que debamos saber?",
        "q1_ph": "Si no hay ninguna, escribe «ninguna»",
        "q2": "¿Alguna cirugía reciente?",
        "q3": "¿Alguna alergia en general?",
        "q3_ph": "Si no hay ninguna, escribe «ninguna»",
        "q4": "¿Está usted embarazada?",
        "q5": "¿Has hecho buceo en las últimas 24 horas?",
        "q5_ayuda": "— aquí o antes de llegar",
        "q6": "Términos y condiciones",
        "q6_acepto": "Acepto los términos y condiciones",
        "enviar": "Pedir el tratamiento",
        "enviando": "Enviando…",
        "si": "Sí",
        "no": "No",
        "falta_trat": "Elige el tratamiento.",
        "falta_dia": "Elige el día.",
        "falta_hora": "Elige la hora.",
        "falta_q": "Falta contestar la pregunta sobre {que}.",
        "falta_terminos": "Hay que aceptar los términos y condiciones para reservar.",
        "sin_conexion": "No hay conexión. Prueba otra vez en un momento.",
        "error_horas": "No se pudieron cargar las horas. Prueba otra vez.",
        "listo_t": "Listo, lo recibimos.",
        "listo_d": ("El spa te confirma la hora. Puedes pedir otro tratamiento aquí "
                    "mismo si quieres."),
        "pie": "Cualquier duda, en recepción te ayudamos.",
        "q2_nombre": "cirugía reciente",
        "q4_nombre": "embarazo",
        "q5_nombre": "buceo en las últimas 24 horas",
    },
}

IDIOMA_POR_DEFECTO = "en"


def idioma_valido(idioma):
    """El idioma pedido si la página lo tiene, y si no el inglés.

    Se acepta 'es-CR' o 'ES' y se queda con 'es': el idioma puede venir de un enlace
    escrito a mano o del navegador del huésped, y fallar por el formato sería absurdo.
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
<title>Spa · Corcovado Wilderness Lodge</title>
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
  /* El cambio de idioma va arriba a la derecha, siempre visible: quien lo necesita lo
     necesita antes de leer nada. */
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
  input[type=text], input[type=date], select, textarea {
    width:100%; padding:11px 12px; font-size:16px; font-family:inherit;
    border:1px solid var(--borde); border-radius:8px; background:#fff; color:var(--texto); }
  textarea { resize:vertical; }
  .opciones { display:flex; gap:10px; flex-wrap:wrap; margin-top:4px; }
  .opciones label { display:inline-flex; align-items:center; gap:7px; font-weight:400;
                    margin:0; padding:9px 15px; border:1px solid var(--borde);
                    border-radius:8px; background:#fff; cursor:pointer; font-size:15px; }
  .opciones input { margin:0; }
  .horas { display:flex; flex-wrap:wrap; gap:7px; margin-top:7px; }
  .horas button { padding:9px 13px; font-size:15px; font-family:inherit; cursor:pointer;
                  border:1px solid var(--borde); border-radius:8px; background:#fff;
                  color:var(--texto); }
  .horas button.elegida { background:var(--verde); color:#fff; border-color:var(--verde); }
  button.principal { width:100%; padding:15px; font-size:17px; font-family:inherit;
    font-weight:600; color:#fff; background:var(--verde); border:0; border-radius:9px;
    cursor:pointer; margin-top:22px; }
  button.principal:disabled { opacity:.5; cursor:default; }
  .aviso { background:var(--aviso-f); color:var(--aviso-t); border-radius:9px;
           padding:12px 14px; font-size:14px; margin-top:14px; }
  .listo { background:var(--ok-f); color:var(--ok-t); border-radius:9px;
           padding:14px 16px; font-size:15px; margin-top:14px; }
  .mias { border-top:1px solid var(--borde); margin-top:16px; padding-top:12px; }
  .mias p { margin:0 0 6px; font-size:14px; }
  .etiqueta { font-size:11.5px; padding:2px 8px; border-radius:20px;
              background:var(--aviso-f); color:var(--aviso-t); }
  .etiqueta.ok { background:var(--ok-f); color:var(--ok-t); }
  footer { text-align:center; color:var(--suave); font-size:12.5px; margin-top:24px; }
</style>
</head>
<body>
<header>
  <div class="idiomas" id="idiomas"></div>
  <p class="lodge">Corcovado Wilderness Lodge</p>
  <h1>Spa</h1>
</header>
<div class="envoltorio">
  <div id="pantalla"><div class="tarjeta"><p class="sub">…</p></div></div>
  <footer id="pie"></footer>
</div>

<script>
const CONF = "{{CONF}}", TOKEN = "{{TOKEN}}";
const API = `/api/spa/publico/${CONF}/${TOKEN}`;
const TEXTOS = {{TEXTOS}};
const NOMBRES_IDIOMA = { en: "EN", es: "ES" };

// El idioma: manda el del enlace; si no, el que la persona eligió la última vez en este
// teléfono; y si tampoco, ingles. El del enlace manda porque lo puso recepción a
// propósito, con el idioma del itinerario de ese huésped.
let IDIOMA = "{{IDIOMA}}";
try {
  const guardado = localStorage.getItem("spa-idioma");
  const enElEnlace = new URLSearchParams(location.search).get("idioma");
  if (!enElEnlace && guardado && TEXTOS[guardado]) IDIOMA = guardado;
} catch (e) { /* modo privado: se queda con el del enlace */ }

let D = null, HORA = null;

function T(clave, vars) {
  let s = (TEXTOS[IDIOMA] || {})[clave];
  if (s === undefined) s = (TEXTOS.en || {})[clave] || "";
  for (const k in (vars || {})) s = s.split("{" + k + "}").join(vars[k]);
  return s;
}

function esc(t) {
  return String(t == null ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function cambiarIdioma(nuevo) {
  if (!TEXTOS[nuevo] || nuevo === IDIOMA) return;
  IDIOMA = nuevo;
  try { localStorage.setItem("spa-idioma", nuevo); } catch (e) {}
  document.documentElement.lang = nuevo;
  // Se conserva lo ya escrito: cambiar de idioma no puede costarle el formulario a
  // medio llenar. Es justo cuando alguien lo cambia — despues de empezar a leer.
  const antes = leerFormulario();
  pintarIdiomas();
  dibujar();
  escribirFormulario(antes);
}

function pintarIdiomas() {
  document.getElementById("idiomas").innerHTML = Object.keys(TEXTOS).map(k =>
    `<button type="button" class="${k === IDIOMA ? "puesto" : ""}"
       onclick="cambiarIdioma('${k}')" lang="${k}">${NOMBRES_IDIOMA[k] || k.toUpperCase()}</button>`
  ).join("");
  document.getElementById("pie").textContent = T("pie");
}

function leerFormulario() {
  const v = (id) => { const e = document.getElementById(id); return e ? e.value : ""; };
  const r = (n) => { const e = document.querySelector(`input[name="${n}"]:checked`);
                     return e ? e.value : null; };
  const c = document.getElementById("q6");
  return { serv: v("serv"), fecha: v("fecha"), hora: HORA,
           q1: v("q1"), q3: v("q3"), q2: r("q2"), q4: r("q4"), q5: r("q5"),
           q6: c ? c.checked : false };
}

function escribirFormulario(d) {
  if (!d) return;
  const p = (id, val) => { const e = document.getElementById(id); if (e && val) e.value = val; };
  p("serv", d.serv); p("fecha", d.fecha); p("q1", d.q1); p("q3", d.q3);
  for (const n of ["q2", "q4", "q5"]) {
    if (d[n] === null || d[n] === undefined) continue;
    const e = document.querySelector(`input[name="${n}"][value="${d[n]}"]`);
    if (e) e.checked = true;
  }
  const c = document.getElementById("q6");
  if (c) c.checked = !!d.q6;
  if (d.serv && d.fecha) verHoras(d.hora);
}

async function cargar() {
  pintarIdiomas();
  document.getElementById("pantalla").innerHTML =
    `<div class="tarjeta"><p class="sub">${esc(T("cargando"))}</p></div>`;
  try {
    const res = await fetch(API);
    if (!res.ok) throw new Error("enlace");
    D = await res.json();
  } catch (e) {
    document.getElementById("pantalla").innerHTML =
      `<div class="tarjeta"><h2>${esc(T("enlace_malo_t"))}</h2>
       <p class="sub">${esc(T("enlace_malo_d"))}</p></div>`;
    return;
  }
  dibujar();
}

function dibujar(mensaje) {
  const s = D.servicios || [];
  const mias = (D.mis_citas || []);
  const nombre = (D.nombre || "").split("/")[1] || D.nombre || "";
  document.getElementById("pantalla").innerHTML = `
    ${mensaje || ""}
    <div class="tarjeta">
      <h2>${esc(T("hola", { nombre: nombre }))}</h2>
      <p class="sub">${esc(T("habitacion", { hab: D.room_no || "",
        desde: D.estadia_desde, hasta: D.estadia_hasta }))}</p>
      ${mias.length ? `<div class="mias">
        <p style="font-weight:600;">${esc(T("ya_pedido"))}</p>
        ${mias.map(c => `<p>${esc(c.fecha)}${c.hora ? " · " + esc(c.hora) : ""} ·
          ${esc(c.servicio_nombre || "")}
          <span class="etiqueta ${c.estado === "CONFIRMADA" ? "ok" : ""}">${
            esc(c.estado === "CONFIRMADA" ? T("confirmada") : T("por_confirmar"))}</span></p>`).join("")}
      </div>` : ""}
    </div>

    <div class="tarjeta">
      <h2>${esc(T("pide_t"))}</h2>
      <p class="sub">${esc(T("pide_d", { abre: D.config.abre, cierra: D.config.cierra }))}</p>

      <label>${esc(T("tratamiento"))}</label>
      <select id="serv" onchange="verHoras()">
        <option value="">${esc(T("elige_uno"))}</option>
        ${s.map(x => `<option value="${esc(x.codigo)}">${esc(x.nombre)} — ${x.minutos} ${esc(T("minutos"))}</option>`).join("")}
      </select>

      <label>${esc(T("dia"))}</label>
      <input type="date" id="fecha" min="${esc(D.estadia_desde)}" max="${esc(D.estadia_hasta)}"
        value="${esc(D.estadia_desde)}" onchange="verHoras()">

      <label>${esc(T("hora"))} <span class="ayuda">${esc(T("hora_ayuda"))}</span></label>
      <div class="horas" id="horas"><span class="ayuda">${esc(T("elige_antes"))}</span></div>

      <div class="aviso">${T("es_solicitud")}</div>
    </div>

    <div class="tarjeta">
      <h2>${esc(T("antes_t"))}</h2>
      <p class="sub">${esc(T("antes_d"))}</p>

      <label>${esc(T("q1"))}</label>
      <textarea id="q1" rows="2" placeholder="${esc(T("q1_ph"))}"></textarea>

      <label>${esc(T("q2"))}</label>
      <div class="opciones">
        <label><input type="radio" name="q2" value="1"> ${esc(T("si"))}</label>
        <label><input type="radio" name="q2" value="0"> ${esc(T("no"))}</label>
      </div>

      <label>${esc(T("q3"))}</label>
      <input type="text" id="q3" placeholder="${esc(T("q3_ph"))}">

      <label>${esc(T("q4"))}</label>
      <div class="opciones">
        <label><input type="radio" name="q4" value="1"> ${esc(T("si"))}</label>
        <label><input type="radio" name="q4" value="0"> ${esc(T("no"))}</label>
      </div>

      <label>${esc(T("q5"))} <span class="ayuda">${esc(T("q5_ayuda"))}</span></label>
      <div class="opciones">
        <label><input type="radio" name="q5" value="1"> ${esc(T("si"))}</label>
        <label><input type="radio" name="q5" value="0"> ${esc(T("no"))}</label>
      </div>

      <label>${esc(T("q6"))}</label>
      <div class="opciones">
        <label><input type="checkbox" id="q6"> ${esc(T("q6_acepto"))}</label>
      </div>

      <div id="error" class="aviso" style="display:none;"></div>
      <button class="principal" id="enviar" onclick="enviar()">${esc(T("enviar"))}</button>
    </div>`;
}

async function verHoras(volverAElegir) {
  const serv = document.getElementById("serv").value;
  const fecha = document.getElementById("fecha").value;
  const caja = document.getElementById("horas");
  HORA = null;
  if (!serv || !fecha) {
    caja.innerHTML = `<span class="ayuda">${esc(T("elige_antes"))}</span>`;
    return;
  }
  caja.innerHTML = `<span class="ayuda">${esc(T("buscando"))}</span>`;
  try {
    const res = await fetch(`${API}/horas?fecha=${encodeURIComponent(fecha)}&servicio=${encodeURIComponent(serv)}`);
    if (!res.ok) throw new Error("horas");
    const d = await res.json();
    caja.innerHTML = d.horas.length
      ? d.horas.map(h => `<button type="button" onclick="elegir('${h}', this)">${h}</button>`).join("")
      : `<span class="ayuda">${esc(T("sin_hueco", { min: d.minutos }))} ${esc(T("sin_hueco2"))}</span>`;
    // Al cambiar de idioma se vuelve a marcar la hora que ya tenía elegida, si sigue libre.
    if (volverAElegir) {
      const b = [...caja.querySelectorAll("button")].find(x => x.textContent === volverAElegir);
      if (b) elegir(volverAElegir, b);
    }
  } catch (e) {
    caja.innerHTML = `<span class="ayuda">${esc(T("error_horas"))}</span>`;
  }
}

function elegir(h, boton) {
  HORA = h;
  document.querySelectorAll("#horas button").forEach(b => b.classList.remove("elegida"));
  boton.classList.add("elegida");
}

function radio(nombre) {
  const m = document.querySelector(`input[name="${nombre}"]:checked`);
  return m ? m.value : null;
}

async function enviar() {
  const error = document.getElementById("error");
  const mostrar = (t) => { error.textContent = t; error.style.display = "block";
                           error.scrollIntoView({ behavior: "smooth", block: "center" }); };
  const serv = document.getElementById("serv").value;
  const fecha = document.getElementById("fecha").value;
  if (!serv) return mostrar(T("falta_trat"));
  if (!fecha) return mostrar(T("falta_dia"));
  if (!HORA) return mostrar(T("falta_hora"));
  for (const n of ["q2", "q4", "q5"]) {
    if (radio(n) === null) return mostrar(T("falta_q", { que: T(n + "_nombre") }));
  }
  if (!document.getElementById("q6").checked) return mostrar(T("falta_terminos"));

  const boton = document.getElementById("enviar");
  boton.disabled = true;
  boton.textContent = T("enviando");
  try {
    const res = await fetch(API, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        servicio_codigo: serv, fecha, hora: HORA,
        condicion_medica: document.getElementById("q1").value.trim(),
        cirugia_reciente: radio("q2"),
        alergias: document.getElementById("q3").value.trim(),
        embarazo: radio("q4"),
        buceo_24h: radio("q5"),
        acepto_terminos: true,
      }),
    });
    const d = await res.json();
    if (!res.ok) {
      boton.disabled = false;
      boton.textContent = T("enviar");
      // 409 = alguien tomó esa hora mientras llenaba el formulario. Se vuelven a
      // cargar las horas para que la que elija exista de verdad, y se le quita la que
      // tenía marcada: si no, toca «Pedir» otra vez y le vuelve a fallar.
      if (res.status === 409) {
        HORA = null;
        await verHoras();
        document.getElementById("horas").scrollIntoView(
          { behavior: "smooth", block: "center" });
      }
      return mostrar(d.detail || T("sin_conexion"));
    }
    D = d;
    dibujar(`<div class="listo"><strong>${esc(T("listo_t"))}</strong><br>${esc(T("listo_d"))}</div>`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) {
    boton.disabled = false;
    boton.textContent = T("enviar");
    mostrar(T("sin_conexion"));
  }
}

cargar();
</script>
</body>
</html>
"""
