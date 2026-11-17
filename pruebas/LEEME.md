# Pruebas

Cómo correrlas:

```
python pruebas/correr_todo.py           # todas
python pruebas/correr_todo.py carga     # solo las que lleven 'carga' en el nombre
python pruebas/probar_carga_opera.py    # una sola suite, directa
```

Devuelve `0` si todo pasa y `1` si algo falla, así que sirve tal cual para un
verificador automático.

**No hacen falta credenciales y no salen a internet.** `correr_todo.py` borra las
variables `OPERA_*` antes de arrancar cada suite justamente para eso: una prueba que
dependiera de qué huéspedes hay hoy en el hotel no sirve de prueba, y una que llamara a
Opera de verdad no se podría correr desde cualquier sitio.

Cada suite corre en **su propio proceso y su propia base**. No es manía: `init_db.DB_PATH`
se fija al importar el módulo, y las suites se contaminan entre ellas —una deja una
reserva cancelada, otra renombra un restaurante—. Corriéndolas en fila sobre la misma
carpeta salen fallos que no existen.

## Qué fija `probar_pantallas.py`

Que el menú de la interfaz y los permisos del servidor sigan alineados. La interfaz
resuelve cada pantalla por **posición**: el índice del botón elige su permiso, su filtro,
su cargador y si se refresca sola. Son cinco listas más la del servidor, y desalinearlas
no da error — abre la pantalla equivocada, o esconde un botón a quien sí tiene permiso.
Ya pasó al agregar el Spa: se desplegó bien y no le aparecía a nadie.

## Qué fija `probar_housekeeping.py`

Las tres reglas de la lavandería que el formulario de Google no podía tener: que se le
diga al huésped si su ropa vuelve el mismo día, que el enlace sepa quién es y muera con la
reserva, y que lo recogido quede escrito aunque el catálogo cambie después. Las tres
fallan en silencio: nadie ve un error, simplemente alguien se queda sin su ropa.

Y la cuenta, que falla igual de callada: los centavos enteros, el impuesto sacado una vez
sobre el subtotal y no prenda por prenda, y el medio centavo que **sube** —el `round()` de
Python redondea al par y se llevaría un centavo por pedido sin que nadie sepa de dónde
salió—. También que el precio lo ponga el catálogo y nunca el formulario: la página del
huésped es pública.

## Qué fija `probar_carga_opera.py`

La regla por la que entran a la base las actualizaciones de Opera. Está escrita porque
este fallo ya llegó a la operación el 2026-09-07: el hotel vio las reservas del día como
canceladas y la hoja del restaurante con una sola habitación.

| Comprobación | Qué protege |
|---|---|
| Un lote parcial no cancela lo que la fuente sigue viendo | **el fallo que ocurrió.** Opera carga solo lo que cambió; el universo son todas las que vio |
| Una descarga incompleta no cancela nada | «no vino en el lote» solo significa «cancelada» si la lista vino completa |
| La válvula frena una cancelación masiva | red de seguridad: si desaparecieron más de las reportadas, no se toca nada y se avisa |
| Una cancelación de verdad sí se refleja | que protegerse no acabe en «no cancelar nunca»: una cancelada sigue ocupando mesa y bote |
| La que la fuente deja de reportar se cancela | el camino del PDF, que sí trae la hoja completa |
| Una reserva que revive recupera su estado y retira el aviso | una cancelación falsa no debe dejar avisos colgados |
| Se recarga la cancelada que Opera reporta viva | sin esto una cancelación falsa se queda puesta para siempre |
| El núcleo de Opera no borra el trabajo de recepción | el otro fallo silencioso: perder tours, régimen, notas y punto de embarque |
| La hoja del restaurante solo cuenta las vivas | de punta a punta, la pantalla donde se vio el problema |

## Qué fija `probar_jornada.py`

Que la hora de un tour se lea igual en las dos puntas y que la línea del día del
Dashboard no pierda ninguna salida. Está escrita porque pasó: se agregó al catálogo una
cabalgata de la tarde con la hora escrita **«2:00 pm»** —el campo es texto libre— y todo
lo que lo lee partía por los dos puntos, así que la salida se leyó como las 2 de la
madrugada. La línea recortaba al borde lo que caía fuera de la jornada y la caja quedó
**debajo del pajareo de las 6**; de paso el detector de choques, que no entendía la hora,
marcó un conflicto con el PNC que no existía. Ninguna de las dos cosas da error: la
salida sale en la tabla de abajo y no sale en la línea.

La suite fija las dos mitades: la hora se normaliza **al guardarla** (`backend/horas.py`,
el catálogo y el arranque, que además arregla lo ya guardado) y la línea del día
**estira** la ventana en vez de recortar, reparte las cajas por el hueco que ocupan en
pantalla y enseña aparte las salidas sin hora.

## Las dos comprobaciones de navegador

Hay cosas de la pantalla que no se pueden comprobar leyendo el archivo: dónde cayó una
caja, si una tapa a otra. Para eso hay dos páginas que se abren en un navegador y leen
las funciones del `frontend/index.html` de al lado —no una copia—:

| Archivo | Qué mide |
|---|---|
| `pruebas/jornada.html` | que la línea del día dibuje TODAS las salidas, cada una en su hora y sin pisarse |
| `pruebas/etiquetas_movil.html` | que en el teléfono cada dato lleve la etiqueta que le toca, contando el `rowspan` |

Se abren con la carpeta levantada (`python -m http.server`, el navegador bloquea el
archivo local) y cada una dice su cuenta: *17/17*, *18/18*.

## Si añades una suite

Se llama `probar_*.py`, importa `comun` y termina con:

```python
if __name__ == "__main__":
    sys.exit(comun.correr("nombre de la suite", PRUEBAS))
```

`correr_todo.py` la encuentra sola.

**Comprueba que la prueba nueva falla de verdad.** Una prueba que pasa contra el código
bueno no demuestra nada por sí sola: rompe a propósito lo que dice proteger, mira que
falle, y restaura. Las de aquí se comprobaron así — reintroduciendo el fallo viejo del
lote-como-universo, que produce 3 fallos con el nombre de las habitaciones canceladas de
más.
