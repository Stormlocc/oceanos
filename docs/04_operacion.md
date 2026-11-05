# Operación del wrapper `oceanos`

`python -m oceanos` interpreta el perfil `water2coast_v1` y delega en ACOLITE la corrección atmosférica y los productos. OCEANOS se encarga de búsqueda, descarga, catálogo, superimagen y limpieza.

- Hay un solo escritor del catálogo a la vez.
- Cada comando tiene ayuda con valores válidos y ejemplos: `oceanos <comando> -h`.
- Alias y ejemplos rápidos en el [README](../README.md). Qué se guarda y por qué: [superimagen](07_superimagen.md).

## Comandos

| Comando | Red | Función |
|---|---|---|
| `prepare` | No | Verifica la revisión de ACOLITE y aplica el parche |
| `run [--plan]` | Sí | **Todo en uno**, por sensor: máscaras → búsqueda y registro → descarga → ACOLITE por zona → COG → sargazo diario → compuestos. `--plan` se detiene tras la búsqueda y muestra qué se bajaría, el tamaño y el disco estimado |
| `run --escena X` / `run --source ARCHIVO --scene NOMBRE` | Sí | Una escena del catálogo o un archivo local. `--force` reprocesa zonas ya terminadas |
| `search [--registrar [ESCENA…]] [--json]` | Metadatos | Consultar sin descargar; `--registrar` deja escenas en la cola |
| `mascara` | WorldCover | Crear las máscaras de tierra que falten |
| `sargazo`, `componer` | No | Recalcular sargazo diario o compuestos desde `superimagen/escenas` |
| `superimagen` | No | Productos por zona y sensor, compuestos y disco frente al presupuesto |
| `status [N] [--estado E] [--ultimas N] [--legado]` | No | Procesos, o el detalle del proceso N |
| `reporte [--resultado R] [--sensor S] [--csv ARCHIVO] [--legado]` | No | Resultado por escena y por zona, con motivo e intentos |
| `cola [--quitar ESCENA…]` | No | Ver o retirar escenas de la cola |
| `sync [CARPETA] [--hash]` | No | Registrar como **legado** L1R/L2W copiados a mano |
| `recover` | No | Marcar interrupciones y limpiar lo parcial; se ejecuta solo al iniciar `run` y `search` |

**Selección.** Las opciones de selección valen antes o después del comando:

| Opción | Efecto |
|---|---|
| `--sensor` | Un sensor. Por defecto se procesan todos los del perfil, en orden S2 → Landsat → OLCI |
| `--satelite` | Restringe los satélites; acepta minúsculas y `LC08/LC09` |
| `--zona` | Restringe las zonas |
| `--start/--end` | `AAAA-MM-DD[THH:MM:SSZ]`, con el fin excluido |

**Validación y errores.**
- El CLI valida fechas, productos, sensores, satélites, zonas y estados antes de abrir el catálogo.
- Los errores locales se muestran con su mensaje y salen con código 2.
- Los errores remotos muestran solo el tipo de excepción, para no exponer respuestas ni credenciales.

**Escenas y procesos.** Las escenas se nombran por su producto; en los comandos basta un fragmento único, como `20251216`. Los procesos se numeran 1, 2, 3…

## Flujo de `run`

1. **Recuperación y motor.** `recover` y comprobación de la identidad de ACOLITE.
2. **Por cada sensor seleccionado:**
   1. **Máscaras de tierra.** Se crean las que falten para cada zona; WorldCover se descarga una sola vez.
   2. **Búsqueda.** Se busca el periodo completo y se registran las escenas `NUEVA` y `FALLIDA`. Se omiten, con su motivo, las que repiten una adquisición ya en cola o ya terminada en todas sus zonas.
   3. **Estimación.** Se muestra la lista que se descargaría y el total: escenas, GB de L1, productos de zona y su tamaño estimado, uso actual de la superimagen frente a los 120 GB. Si se pasaría del presupuesto, aparece un AVISO. Con `--plan` el comando termina aquí.
   4. **Escenas en paralelo** (ver [ejecución de una escena](#ejecución-de-una-escena)).
   5. **Sargazo diario** de los días del periodo.
   6. **Compuestos** de los meses completos, con sus estaciones y años.
3. **Resumen final.** Escenas por estado, tiempos, descarga y disco.

`run` se puede cortar y repetir: no vuelve a descargar adquisiciones con todas sus zonas terminadas ni recalcula compuestos cuya firma no cambió. Para el ensayo de enero de 2026:

```bash
oceanos run --plan --start 2026-01-01 --end 2026-02-01
oceanos run --start 2026-01-01 --end 2026-02-01
```

## Estados

**Escena (cola)**

| Estado | Significado | Lo toma `run` |
|---|---|---|
| `NUEVA` | Vista en una búsqueda, sin compromiso | `run` la registra si toca una zona |
| `PENDIENTE` | En la cola | Sí, si cumple la selección vigente |
| `FALLIDA` | Falló el último proceso | Sí; el próximo `run` reintenta solo las zonas pendientes y reutiliza el crudo si su SHA-256 coincide |
| `PROCESADA` | Todas sus zonas tienen resultado terminal | No |
| `DISPONIBLE` | Su adquisición ya estaba terminada en sus zonas (otra versión del proveedor) | No |

**Adquisición.** Se decide por adquisición (`satélite:día:lugar`) y zona del AOI, sin red. Si el proveedor publica varias versiones del mismo producto (reproceso con otro baseline), entra solo la más reciente.

**Zona** (`productos_escena.estado`). Los tres estados son terminales y no se reintentan sin `--force`:

| Estado | Significado |
|---|---|
| `OK` | Exportada a la superimagen |
| `NUBOSA` | Más del 50 % de nubes sobre la zona |
| `SIN_DATOS` | La escena no cubre la zona |

**Proceso.** Puede quedar `OK`, `FALLIDO` o `INTERRUMPIDO`. Motivos propios de la superimagen:

| Motivo | Qué pasó |
|---|---|
| `AUXILIAR_POR_DEFECTO` | ACOLITE no consiguió MERRA-2 |
| `SIN_MASCARA` | Falta la máscara de tierra de la zona |
| `PRESUPUESTO_SUPERIMAGEN` | No cabe otro producto en los 120 GB |
| `ValueError` | Falta un producto o la grilla no coincide (el mensaje queda en el evento) |

## Ejecución de una escena

1. **Comprobación.** Se verifica que la escena cumpla el perfil y se registran las zonas que toca. Si no queda ninguna pendiente, queda `DISPONIBLE` sin crear proceso.
2. **Presupuesto.** Si no cabe otro producto, no se descarga.
3. **Proceso.** Se crea `EN_CURSO` con su temporal `storage/temporary/<N>`.
4. **Adquisición.**
   - **Crudo.** Si un proceso fallido anterior conservó el crudo y su SHA-256 coincide, se reutiliza (evento `REUTILIZA_DESCARGA`).
   - **Vía de descarga.** Si no, se descarga en streaming:
     - Sentinel-2 y OLCI: `native.cdse_download`.
     - Landsat: `native.usgs_download`, por M2M con `download-options` → `download-request` → URL, y EarthExplorer como respaldo.
   - **Redirecciones.** Solo se siguen hacia `dataspace.copernicus.eu` o `usgs.gov`.
   - **Reanudación.** Un intento cortado se reanuda con `Range` + `If-Range`.
   - **Reintentos.** Hasta 3 intentos, con esperas de 10 y 30 s. Si la cuota se supera (429), se espera al menos 30 s, o lo que pida `Retry-After` si no pasa de 60 s; si pide más, se deja de intentar.
   - **Verificación.** Se comprueban el tamaño y los checksums del proveedor, y se guarda el SHA-256 propio.
5. **Extracción** en el temporal, rechazando rutas fuera de la carpeta y enlaces.
6. **Por cada zona pendiente:**
   1. Nubes sobre la zona.
   2. ACOLITE en un proceso aislado, con límite de tiempo y control de disco.
   3. Validación: EPSG y ejes, cada producto pedido y todas las `Rrs_*`.
   4. Auxiliares reales.
   5. Exportación a COG, verificación y linaje.
   6. Borrado de L1R, L2R y L2W de la zona.

   Si falla una zona, el proceso queda `FALLIDO`. Las zonas ya terminadas quedan registradas, y el crudo se conserva para el próximo intento (`limpieza APLAZADA`).
7. **Cierre.** El proceso queda `OK` / `TECNICA_OK` con el resultado de cada zona y se borran el crudo y la extracción (`limpieza HECHA`).

## Progreso y tiempos

**Progreso en pantalla**
- Durante `run`, una línea por escena muestra la etapa, el porcentaje, los MB, la velocidad y el tiempo restante.
- En paralelo es una línea compacta con todas las escenas.
- Sin terminal interactiva se imprime una línea cada 30 s.

**Cómo se mide el avance**
- Las descargas escriben un `.part`, y su tamaño es el avance.
- La extracción y ACOLITE se comparan con la mediana histórica de esa etapa.

**Registro por proceso:** `descarga_min`, `descarga_mb`, `intentos` y las métricas de RAM por etapa.

## Paralelo

`run` con dos o más escenas las reparte entre varios hilos. Cada escena recorre su cadena completa con su propia conexión SQLite (WAL). Al iniciar se imprime el reparto calculado para el equipo:

```
Paralelo: 8 escena(s) a la vez · equipo 20 CPU, 29.4 GB RAM (28.0 GB libre) · se usan 18 CPU y 25.0 GB (se dejan 2 CPU y 2.9 GB al sistema) · 2 hilos por proceso · descargas a la vez 4 · pico RAM descarga 0.4 GB, extracción 1.2 GB, ACOLITE 4.8 GB
```

### Memoria

- **Presupuesto.** Es la RAM libre al iniciar (`MemAvailable`, o el `memory.max` de cgroup si es más estricto) menos una reserva para el sistema: el 10 % de la RAM del equipo, mínimo 1,5 GB.
- **Reserva por etapa.** Antes de lanzar cada proceso aislado se reserva su pico de RAM esperado. El pico es el mayor `rss_bytes` de esa etapa en los últimos 20 procesos `OK` del sensor, más un 10 %.
- **Valores sin historial:**

  | Etapa | RAM |
  |---|---|
  | Búsqueda | 1,0 GB |
  | Descarga | 0,4 GB |
  | Extracción | 1,2 GB |
  | Nubes | 0,8 GB |
  | ACOLITE, Sentinel-2 | 4,8 GB |
  | ACOLITE, Landsat | 6,6 GB |
  | ACOLITE, OLCI | 6,6 GB |
  | Exportación | 1,5 GB |

- **Medido en enero de 2026** (catálogo de la laptop): ACOLITE S2 hasta 7,85 GB, Landsat 1,1 GB y OLCI 2,6 GB; exportación S2 hasta 3,1 GB. Un catálogo nuevo arranca con los valores sin historial, que en S2 se quedan cortos hasta que haya procesos `OK`.
- **Espera.** Si no cabe, espera y la barra dice el motivo.
- **Etapa sola.** Una etapa sola siempre arranca, para no bloquear equipos pequeños.

### Orden de las etapas

- **Prioridad.** Va primero lo más avanzado (exportación, ACOLITE, extracción) y después la descarga, para liberar RAM y disco antes de traer más.
- **Escenas a la vez.** Las descargas que permiten el proveedor y la RAM, más los ACOLITE que caben, sin superar los núcleos ni el disco libre. Se calculan 3,5 GB de temporales por escena.
- **`--trabajadores N`.** Fija el número de escenas a la vez.

### CPU

- **Núcleos.** Se usan los núcleos utilizables menos ~10 %.
- **Hilos.** Cada proceso aislado recibe `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS` = núcleos ÷ escenas a la vez.
- **Ajuste manual.** `OCEANOS_CPUS=N` y `OCEANOS_RAM_GB=X` fijan los núcleos y la RAM del lote.

### Descargas

- **CDSE (S2 y OLCI).** Como máximo 4 a la vez: es la cuota de una cuenta gratuita ([cuotas CDSE](https://documentation.dataspace.copernicus.eu/Quotas.html)).
- **USGS.** También 4, como tope prudente.
- **Ajuste.** `OCEANOS_DESCARGAS=N` lo cambia.

### Recursos compartidos de ACOLITE

- **Auxiliares.** Dos ACOLITE del mismo día no corren a la vez, porque pedirían el mismo auxiliar.
- **LUT.** Si faltan las LUT de alguna plataforma del lote, el primer ACOLITE corre solo: espera a que terminen las etapas en curso (también las descargas) y nada más arranca hasta que acabe. ACOLITE baja entonces las LUT de ese satélite (~0,5 GB). En un equipo nuevo esto puede tardar decenas de minutos con poca CPU en uso; después el lote sigue en paralelo.
- **`scratch`.** Cada etapa usa su propio `scratch`.

### Interrupción

**Ctrl+C** corta los procesos aislados y los procesos quedan `INTERRUMPIDO`. `recover` los limpia al iniciar el siguiente comando.

## Retención y limpieza

- **Qué persiste:** la superimagen (`storage/superimagen`), el catálogo y el legado. Crudo, extracción, L1R, L2R y L2W se borran después de exportar y verificar.
- **Proceso fallido:** conserva su temporal (`APLAZADA`) para reutilizar el crudo. Cuando un intento posterior lo reutiliza, se limpia.
- **Seguridad:** toda ruta se resuelve dentro de `storage/temporary/<N>` y nunca se siguen enlaces. Un fallo de borrado deja `limpieza FALLIDA` sin convertir en fallido un proceso exitoso.
- **Lo que nunca se borra:** el legado y lo importado (`NO_APLICA`), las fuentes externas, el AOI y las credenciales. Los flags de borrado nativo de ACOLITE están desactivados.
- **Presupuestos:** 50 GB de temporales, que cuentan `storage/temporary`, `acolite/data` y `acolite/scratch`, con al menos 2 GB libres en el disco. La superimagen tiene 120 GB aparte ([disco](07_superimagen.md#disco)).

## Legado `lapargera_v1`

- **Migración del catálogo.** Al abrir un catálogo v4, OCEANOS hace una copia de respaldo y lo migra a la versión actual (v6).
  - Los procesos anteriores quedan con `legado=1`.
  - Sus escenas vuelven a `NUEVA`.
- **Archivos.** Los L1R/L2W siguen en `storage/runs` y nunca se borran.
- **Fuera del trabajo nuevo.** El legado no entra a la cola, ni a la regla de "ya tenemos esta adquisición", ni a la superimagen.
- **Consulta.** Se ve con `status --legado`, `reporte --legado` o la vista `v_legado`.

`sync` registra como legado los L1R/L2W copiados a mano a una carpeta de `storage`. La carpeta por defecto es `importados`; no se pueden usar `catalog`, `temporary`, `superimagen` ni `auxiliares`.
- **Qué lee:** solo el nombre de salida de ACOLITE (`<sensor>_<AAAA_MM_DD_HH_MM_SS>_<tile|pathrow>_<región>_<L1R|L2W>.nc`), sin abrir los NetCDF.
- **`--hash`:** calcula el SHA-256.
- **Idempotencia:** `sync` se puede repetir sin duplicar registros.
- **Estado de la escena:** no lo cambia.

## Reporte

`oceanos reporte` no usa la red. Muestra cada escena trabajada con:
- su resultado (`OK`, `FALLIDA`, `PENDIENTE`, `DISPONIBLE`);
- el resultado de cada zona (`ponce_guayanilla:OK la_parguera_guanica:NUBOSA`);
- los intentos de descarga;
- el motivo del último fallo, en palabras.

Opciones:
- `--resultado FALLIDA`: solo las fallidas.
- `--sensor`: solo un sensor.
- `--csv`: guarda la misma tabla en un archivo.

`oceanos superimagen` resume los productos por zona y sensor, los compuestos y el disco.

## Catálogo SQLite (esquema v6)

`storage/catalog/catalog.sqlite` es el único registro operativo.
- **Formato:** fechas `AAAA-MM-DD HH:MM:SS` UTC; tamaños en MB, salvo `bytes`.
- **Comentarios:** cada columna lleva su comentario en la base y los visores lo muestran.
- **Migración:** un catálogo v4 o v5 se respalda (`catalog_v<n>_respaldo_<fecha>.sqlite`) y se migra en el sitio.
  - v4: los procesos del AOI anterior quedan como legado.
  - v5 → v6 (noviembre de 2026): se agrega `productos_escena.correccion`, que queda vacía en los productos ya exportados. Se registra un evento `MIGRACION`.

| Tabla | Una fila por | Columnas principales |
|---|---|---|
| `escenas` | Producto del proveedor | sensor, satélite, `fecha_utc`, tile, proveedor, `tamano_mb`, nubosidad, estado (cola), `adquisicion`, `fuente` (JSON), `zonas` (JSON) |
| `procesos` | Descarga y procesamiento, o importación | escena, aoi, tipo, estado, tiempos, intentos, error, validación, limpieza, `detalle` (JSON: métricas, zonas, entorno), `legado` |
| `busquedas` | Intento de búsqueda | proveedor, sensor, satélites, desde, hasta, estado, devueltas, cumplen, completitud, tamaños, descartadas, `aoi` |
| `eventos` | Hecho relevante | fecha, proceso, escena, tipo, mensaje |
| `productos_escena` | Escena × zona × AOI | estado, carpeta, bytes, variables, nubes, cobertura, glint y linaje completo ([07](07_superimagen.md#etapa-escenas)) |
| `mascaras` | Zona × sensor × resolución | ruta, capa, sha256, `tierra_pct` |
| `compuestos` | Sargazo diario, compuesto mensual, estacional o anual | tipo, método, zona, sensor, periodo, carpeta, firma, bytes, `n_escenas`, detalle |
| `compuesto_escenas` | Escena que entró a un compuesto | compuesto, producto |

**Vistas:**

| Vista | Contenido |
|---|---|
| `v_resumen` | Resumen general |
| `v_cola` | Escenas en la cola |
| `v_descargas` | Descargas realizadas |
| `v_fallidas` | Escenas fallidas |
| `v_superimagen` | Escenas y GB por zona, sensor y estado |
| `v_compuestos` | Compuestos generados |
| `v_legado` | Procesos del legado |
| `v_disco` | L1R/L2W del legado |

Hay más consultas en [`sql/consultas.sql`](../sql/consultas.sql).

## Pruebas

```bash
env PYTHONPATH=.:tests /home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m unittest discover -s tests
```

Son 103 pruebas, sin red: `tests/sin_red.py` bloquea toda conexión no local. Usan dobles de ACOLITE y servidores locales.

- **`test_wrapper.py`** cubre:
  - catálogo, migraciones v4 y v5 → v6, y legado;
  - cola por adquisición y zonas, y reutilización del crudo;
  - limpieza y presupuestos;
  - validación;
  - descargas CDSE y USGS (M2M y respaldo EarthExplorer), reanudación con `Range` y reintentos;
  - paralelo y recursos;
  - CLI (`run --plan`, selección, reporte con CSV) y `sync` como legado.
- **`test_superimagen.py`** cubre, sobre una grilla pequeña:
  - exportación a COG con `calidad.tif` (incluidos `aot_550`, `vza` y `raa`, y la lectura del formato anterior de 10 bandas) y linaje con `correccion`;
  - nubes por zona y máscara de tierra;
  - sargazo diario;
  - compuestos (a) y (b) con sus pesos, estaciones y años, y completitud del mes;
  - flujo completo de una zona.

Las pruebas no validan los algoritmos científicos de ACOLITE.
