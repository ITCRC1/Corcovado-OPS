/* Programa de servicio: lo que convierte el sistema en una app instalable.
 *
 * Dos cosas hace, y ninguna más — a propósito:
 *
 *  1. Que la app ABRA sin señal. En el lodge el internet se cae, y alguien mirando la
 *     agenda del día en el muelle no debería quedarse con la pantalla en blanco.
 *  2. Que arranque rápido, sirviendo las fuentes y las fotos desde el teléfono.
 *
 * Lo que NO hace: guardar cambios sin señal. Si no hay internet se puede consultar lo
 * último visto, pero para modificar hay que estar conectado. Encolar cambios y
 * sincronizarlos después es otro problema, y hacerlo a medias sería peor que no hacerlo.
 *
 * Sobre la estrategia, que es donde se equivocan estas cosas: el HTML y los datos van
 * SIEMPRE a la red primero, y solo se cae al teléfono si la red falla. Así un despliegue
 * nuevo se ve de inmediato — guardar el HTML sería repetir el problema de la "versión
 * vieja" que ya nos costó una tarde. Las fuentes y las imágenes sí van al revés: se
 * sirven del teléfono, porque pesan y no cambian.
 */

const VERSION = "cwl-v1";
const CACHE_ESTATICO = `${VERSION}-estatico`;   // fuentes, imágenes, iconos
const CACHE_PAGINAS = `${VERSION}-paginas`;     // el HTML y las respuestas de datos

// Lo mínimo para que la app abra sin señal la primera vez.
const BASE = ["/", "/manifest.webmanifest", "/assets/logo_blanco.png", "/assets/icono-192.png"];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(CACHE_PAGINAS)
      .then((c) => c.addAll(BASE).catch(() => {}))   // si algo falla, no se aborta la instalación
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((claves) => Promise.all(
        claves.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function esEstatico(url) {
  return url.pathname.startsWith("/assets/");
}

// No tiene sentido guardar estas: son de un momento concreto.
function noGuardar(url) {
  return url.pathname === "/api/cambios"
      || url.pathname === "/api/version"
      || url.pathname.startsWith("/api/auth/")
      || url.pathname.startsWith("/api/export/");   // descargas, van siempre a la red
}

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  if (peticion.method !== "GET") return;            // guardar cambios siempre va a la red
  const url = new URL(peticion.url);
  if (url.origin !== self.location.origin) return;  // nada de otros sitios

  // Fuentes e imágenes: del teléfono primero, y se guardan la primera vez.
  if (esEstatico(url)) {
    evento.respondWith(
      caches.match(peticion).then((guardada) => guardada || fetch(peticion).then((res) => {
        if (res.ok) caches.open(CACHE_ESTATICO).then((c) => c.put(peticion, res.clone()));
        return res;
      }))
    );
    return;
  }

  if (noGuardar(url)) return;

  // HTML y datos: la red manda; el teléfono es el respaldo cuando no hay señal.
  evento.respondWith(
    fetch(peticion)
      .then((res) => {
        if (res.ok) {
          const copia = res.clone();
          caches.open(CACHE_PAGINAS).then((c) => c.put(peticion, copia));
        }
        return res;
      })
      .catch(() => caches.match(peticion).then((guardada) => guardada || (
        // Sin señal y sin copia: si pedían una pantalla, se les da la app guardada.
        peticion.mode === "navigate" ? caches.match("/") : undefined
      )))
  );
});
