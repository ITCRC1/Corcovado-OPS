"""
La página que abre el huésped con su enlace para pedir una cita en el spa.

Es pública —el código del enlace es lo que la abre— y solo muestra SU reserva.

DECISIONES QUE IMPORTAN
-----------------------
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
igual que la del código QR: un archivo más que desplegar por 200 líneas no se paga.
"""


def html(conf_no, token):
    return _PLANTILLA.replace("{{CONF}}", conf_no).replace("{{TOKEN}}", token)


_PLANTILLA = r"""<!doctype html>
<html lang="es">
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
  header { background:var(--verde); color:#fff; padding:26px 18px 22px; text-align:center; }
  header p.lodge { font-family:"Cormorant Garamond",Georgia,serif; font-size:13px;
                   letter-spacing:.18em; text-transform:uppercase; margin:0; opacity:.85; }
  header h1 { font-family:"Cormorant Garamond",Georgia,serif; font-weight:600;
              font-size:30px; margin:6px 0 0; }
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
  <p class="lodge">Corcovado Wilderness Lodge</p>
  <h1>Spa</h1>
</header>
<div class="envoltorio">
  <div id="pantalla"><div class="tarjeta"><p class="sub">Cargando…</p></div></div>
  <footer>Cualquier duda, en recepción te ayudamos.</footer>
</div>

<script>
const CONF = "{{CONF}}", TOKEN = "{{TOKEN}}";
const API = `/api/spa/publico/${CONF}/${TOKEN}`;
let D = null, HORA = null;

function esc(t) {
  return String(t == null ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function cargar() {
  try {
    const res = await fetch(API);
    if (!res.ok) throw new Error("enlace");
    D = await res.json();
  } catch (e) {
    document.getElementById("pantalla").innerHTML =
      `<div class="tarjeta"><h2>Este enlace ya no sirve</h2>
       <p class="sub">Puede que la reserva haya terminado. Pídele uno nuevo a recepción.</p></div>`;
    return;
  }
  dibujar();
}

function dibujar(mensaje) {
  const s = D.servicios || [];
  const mias = (D.mis_citas || []);
  document.getElementById("pantalla").innerHTML = `
    ${mensaje || ""}
    <div class="tarjeta">
      <h2>Hola, ${esc((D.nombre || "").split("/")[1] || D.nombre || "")}</h2>
      <p class="sub">Habitación ${esc(D.room_no || "")} · del ${esc(D.estadia_desde)} al ${esc(D.estadia_hasta)}</p>
      ${mias.length ? `<div class="mias">
        <p style="font-weight:600;">Lo que ya tienes pedido</p>
        ${mias.map(c => `<p>${esc(c.fecha)}${c.hora ? " · " + esc(c.hora) : ""} ·
          ${esc(c.servicio_nombre || "")}
          <span class="etiqueta ${c.estado === "CONFIRMADA" ? "ok" : ""}">${
            c.estado === "CONFIRMADA" ? "confirmada" : "por confirmar"}</span></p>`).join("")}
      </div>` : ""}
    </div>

    <div class="tarjeta">
      <h2>Pide tu tratamiento</h2>
      <p class="sub">El spa abre de ${esc(D.config.abre)} a ${esc(D.config.cierra)}.</p>

      <label>Tratamiento</label>
      <select id="serv" onchange="verHoras()">
        <option value="">Elige uno…</option>
        ${s.map(x => `<option value="${esc(x.codigo)}">${esc(x.nombre)} — ${x.minutos} minutos</option>`).join("")}
      </select>

      <label>Día</label>
      <input type="date" id="fecha" min="${esc(D.estadia_desde)}" max="${esc(D.estadia_hasta)}"
        value="${esc(D.estadia_desde)}" onchange="verHoras()">

      <label>Hora <span class="ayuda">— toca la que te convenga</span></label>
      <div class="horas" id="horas"><span class="ayuda">Elige primero el tratamiento y el día.</span></div>

      <div class="aviso">
        Esto es una <strong>solicitud</strong>. El spa te la confirma; si esa hora ya no
        estuviera libre, te proponemos otra.
      </div>
    </div>

    <div class="tarjeta">
      <h2>Antes de tu tratamiento</h2>
      <p class="sub">Por tu salud y seguridad. Solo lo ve el equipo del spa.</p>

      <label>¿Alguna condición médica de la que debamos saber?</label>
      <textarea id="q1" rows="2" placeholder="Si no hay ninguna, escribe «ninguna»"></textarea>

      <label>¿Alguna cirugía reciente?</label>
      <div class="opciones">
        <label><input type="radio" name="q2" value="1"> Sí</label>
        <label><input type="radio" name="q2" value="0"> No</label>
      </div>

      <label>¿Alguna alergia en general?</label>
      <input type="text" id="q3" placeholder="Si no hay ninguna, escribe «ninguna»">

      <label>¿Está usted embarazada?</label>
      <div class="opciones">
        <label><input type="radio" name="q4" value="1"> Sí</label>
        <label><input type="radio" name="q4" value="0"> No</label>
      </div>

      <label>¿Has hecho buceo en las últimas 24 horas?
        <span class="ayuda">— aquí o antes de llegar</span></label>
      <div class="opciones">
        <label><input type="radio" name="q5" value="1"> Sí</label>
        <label><input type="radio" name="q5" value="0"> No</label>
      </div>

      <label>Términos y condiciones</label>
      <div class="opciones">
        <label><input type="checkbox" id="q6"> Acepto los términos y condiciones</label>
      </div>

      <div id="error" class="aviso" style="display:none;"></div>
      <button class="principal" id="enviar" onclick="enviar()">Pedir el tratamiento</button>
    </div>`;
  HORA = null;
}

async function verHoras() {
  const serv = document.getElementById("serv").value;
  const fecha = document.getElementById("fecha").value;
  const caja = document.getElementById("horas");
  HORA = null;
  if (!serv || !fecha) {
    caja.innerHTML = `<span class="ayuda">Elige primero el tratamiento y el día.</span>`;
    return;
  }
  caja.innerHTML = `<span class="ayuda">Buscando horas…</span>`;
  try {
    const res = await fetch(`${API}/horas?fecha=${encodeURIComponent(fecha)}&servicio=${encodeURIComponent(serv)}`);
    if (!res.ok) throw new Error("horas");
    const d = await res.json();
    caja.innerHTML = d.horas.length
      ? d.horas.map(h => `<button type="button" onclick="elegir('${h}', this)">${h}</button>`).join("")
      : `<span class="ayuda">Ese día ya no queda espacio para ${d.minutos} minutos.
         Prueba otro día, o escríbenos a recepción.</span>`;
  } catch (e) {
    caja.innerHTML = `<span class="ayuda">No se pudieron cargar las horas. Prueba otra vez.</span>`;
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
  if (!serv) return mostrar("Elige el tratamiento.");
  if (!fecha) return mostrar("Elige el día.");
  if (!HORA) return mostrar("Elige la hora.");
  for (const [n, texto] of [["q2", "cirugía reciente"], ["q4", "embarazo"],
                            ["q5", "buceo en las últimas 24 horas"]]) {
    if (radio(n) === null) return mostrar(`Falta contestar la pregunta sobre ${texto}.`);
  }
  if (!document.getElementById("q6").checked)
    return mostrar("Hay que aceptar los términos y condiciones para reservar.");

  const boton = document.getElementById("enviar");
  boton.disabled = true;
  boton.textContent = "Enviando…";
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
      boton.textContent = "Pedir el tratamiento";
      // 409 = alguien tomó esa hora mientras llenaba el formulario. Se vuelven a
      // cargar las horas para que la que elija exista de verdad, y se le quita la que
      // tenía marcada: si no, toca «Pedir» otra vez y le vuelve a fallar.
      if (res.status === 409) {
        HORA = null;
        await verHoras();
        document.getElementById("horas").scrollIntoView(
          { behavior: "smooth", block: "center" });
      }
      return mostrar(d.detail || "No se pudo enviar. Prueba otra vez.");
    }
    D = d;
    dibujar(`<div class="listo"><strong>Listo, lo recibimos.</strong><br>
      El spa te confirma la hora. Puedes pedir otro tratamiento aquí mismo si quieres.</div>`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) {
    boton.disabled = false;
    boton.textContent = "Pedir el tratamiento";
    mostrar("No hay conexión. Prueba otra vez en un momento.");
  }
}

cargar();
</script>
</body>
</html>
"""
