# Pendientes, riesgos y trabajo futuro

Estado al 08-10-2026. Ninguna fase nueva se inicia sin orden explícita del usuario, y no se descargan escenas, LUT ni auxiliares sin autorización.

## Pendientes científicos

| Tema | Estado y siguiente paso |
|---|---|
| Productos acuáticos enmascarados | El umbral SWIR nativo enmascara casi todo el AOI ([resultados](05_resultados.md)). Investigar glint y máscara en un experimento separado y trazable, sin relajar umbrales arbitrariamente |
| Datos in situ | Necesarios para aceptar cualquier producto: observaciones coincidentes de clorofila y turbidez con ubicación, hora, profundidad y control de calidad |
| Salida solo oceánica | FAI/NDVI conservan tierra; evaluar `masking.land_water_mask` de ACOLITE (GSHHG/HydroLAKES), con atención a cayos y lagunas. Natural Earth no sirve como máscara a 10 m |

## Riesgos y limitaciones técnicas

| Tema | Detalle |
|---|---|
| RAW retenido tras `SKIPPED` | Si la salida reutilizable se reconoce **después** de descargar, el intento queda `SKIPPED`, conserva el RAW y `cleanup` lo aplaza. Corrección pendiente |
| Completitud USGS | La función nativa pide hasta 1000 resultados y no pagina. El wrapper informa `INCOMPLETE` si hay más: acotar el intervalo |
| Tamaño Landsat | `download-options` de M2M requiere el rol MACHINE (la cuenta recibe HTTP 403). El respaldo lee el HTML de EarthExplorer y puede romperse si USGS cambia la página; es solo informativo |
| Descarga en memoria | CDSE y USGS descargan sin streaming; el pico de RAM incluye el archivo completo |
| Fuente sin checksum comparable | Sin MD5/SHA del proveedor (USGS), decidir si se omite el cálculo exige descargar primero |
| Importación por nombre | `sync` no abre los NetCDF; un nombre engañoso marcaría la adquisición como disponible. Usar `--hash` si los archivos serán evidencia |
| Recursos | Presupuesto de 50 GB supervisado por muestreo, sin cuota instantánea; no se registra qué auxiliares consumió cada escena |
| Reintentos | Esperas fijas de 60 y 300 s; no se interpreta `Retry-After` |
| Respaldo externo | No hay backups automáticos del catálogo ni de `storage/runs`; definir destino y procedimiento |
| Cambio de ACOLITE | Cambiar revisión o parche invalida la reutilización de todas las salidas previas (ver [ACOLITE](02_acolite.md#instalación-y-prepare)) |

## Antes de paralelizar

- **Un escritor.** `exclusive()` bloquea `storage/.writer.lock` durante todo el comando; cada `Catalog` usa una única conexión SQLite sin WAL. Paralelizar exige separar la sesión de catálogo por tarea, o un escritor central, y definir el bloqueo por adquisición (hoy implícito).
- **Cola sin reserva.** La cola es `escenas.estado`: `pending()` la lee y el lote la actualiza al terminar cada escena, sin un estado "en proceso" ni dueño. Varios trabajadores necesitan reservar la escena en una transacción (p. ej. `estado='EN_PROCESO'` con el id del proceso).
- **Estado en `Pipeline`.** `current_run`, `metrics` y `last_query` son atributos de instancia por escena; cada trabajador necesita su propia instancia.
- **Presupuesto de disco.** `disk_bytes()` recorre `storage`, `acolite/data` y `acolite/scratch` cada 2 s por proceso y no reserva espacio: N procesos en paralelo pueden superar los 50 GB entre muestreos.
- **Progreso.** `Progress` reescribe una sola línea; varios trabajadores requieren un panel por tarea. La medición `rchar` es por proceso y ya está aislada por `stage/baseline`.
- **Directorios compartidos de ACOLITE.** `scratch` y las descargas de auxiliares/LUT son comunes a todos los procesos; la concurrencia nativa no está auditada.
- **Proveedores.** CDSE/USGS tienen límites de sesión y descarga; los reintentos usan esperas fijas (60 y 300 s) sin `Retry-After`.
- **Identidad compuesta.** `clave_resultado`/`clave_correccion` dependen de la identidad del motor; cualquier cambio del parche ACOLITE invalida la reutilización de todas las salidas previas.
- **Importados sin verificar.** Los 14 L1R/L2W actuales son procesos `IMPORTADO`: evitan descargas repetidas, pero no se reutilizan como padre para regenerar productos. Para eso hay que reprocesar la escena (o validar los archivos y marcarlos `TECNICA_OK`).

## Trabajo futuro (no iniciado)

- **Docker y Airflow (fase 12).** Flujo: catálogo → selección → adquisición → ACOLITE → validación → registro → limpieza. Cada tarea con identificador y estado; reanudar desde resultados válidos; no repetir AC por un fallo de limpieza ni multiplicar reintentos entre Airflow, wrapper y cliente nativo. Persistir solo L1R/L2W y un catálogo. Inventariar dependencias reales (GDAL con JP2OpenJPEG y netCDF, pyproj, pyresample, netCDF4) antes de contenerizar.
- **Cubo temporal (fase 13).** Alimentado por los L2W retenidos, particionado por AOI y versión de grilla, con vínculo a proceso, configuración y fuente; sin mezclar algoritmos o grillas incompatibles y sin borrar NetCDF hasta decidir una política. Es distinto de usar Zarr como entrada de ACOLITE.
- **Nuevos AOI y varios tiles.** Cada AOI necesita su propio análisis; no heredar EPSG, grilla ni algoritmos de `lapargera_v1`. Para varios tiles auditar `merge_tiles`, `merge_full_tiles`, `extend_region`, cruces UTM y proyección. Un L1R recortado no permite ampliar el AOI. Volver a descargar una escena para otro AOI es aceptable.
- **Productos propios (fase 14).** Solo donde ACOLITE no cubra la necesidad.
