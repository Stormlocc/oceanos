# Fase 5 — estrategia de adquisición

Fecha: 29 de septiembre de 2026. **Fase completada como selección de entrada y consulta de metadata.** OC4 queda excluido por decisión del usuario; fase 4 cerrada como configuración candidata. No se descargaron escenas, no se ejecutó corrección atmosférica ni se implementó el pipeline.

## Resultado de disponibilidad

Se ejecutaron las funciones nativas `api.stac.query` y `api.cdse.query` de la revisión auditada `80da0c0c681d9597fd4b7737837d6a3e61907b33` en aislamiento, con timeout HTTP de 30 segundos y captura de las respuestas públicas para esta comprobación. Esa instrumentación temporal no modifica ACOLITE ni constituye el cliente futuro.

- EOPF STAC: consulta por bounding box del AOI, Sentinel-2 L1C y 1–21 agosto UTC; HTTP 200, FeatureCollection vacía. No hay entrada Zarr localizada para este intervalo y AOI en ese catálogo al consultar. Esto no demuestra ausencia en todos los proveedores ni incompatibilidad del lector.
- El `base_url` default de la función termina en `/` y produce `//collections`: el servidor respondió 404. Pasar explícitamente `https://stac.core.eopf.eodc.eu`, sin barra final, resolvió la URL usando la misma función. No reintentar un error determinista de URL como si fuera una interrupción de red.
- CDSE OData: nivel L1C, tile 19QGV, fechas 1–20 agosto y `cloud_cover=None`; HTTP 200, cinco productos online, sin siguiente página. Sus footprints cubren el bounding box del AOI. Son candidatos del catálogo, aún no escenas validadas científicamente.

| Adquisición UTC | Plataforma | Tamaño publicado (bytes) | Nubosidad publicada (%) |
|---|---|---:|---:|
| 2026-08-04T15:07:19.024000Z | S2B | 789574421 | 2.35590791006 |
| 2026-08-09T15:07:21.025000Z | S2C | 771317634 | 17.527426916301 |
| 2026-08-11T15:07:41.024000Z | S2A | 790195963 | 13.869330227836 |
| 2026-08-14T15:07:19.024000Z | S2B | 810576889 | 1.916390456568 |
| 2026-08-19T15:07:21.025000Z | S2C | 780896915 | 46.643046970647 |

Tamaño publicado conjunto: **3,942,561,822 bytes**, aproximadamente 3.94 GB decimales. No incluye extracción, NetCDF, auxiliares ni logs. A 100 Mbps son aproximadamente 5.3 minutos de transferencia ideal; no es un benchmark. Se descargará una escena a la vez. La nubosidad se registra, sin excluir adquisiciones ni ordenar por ella.

Para el primer ensayo se propone la adquisición más antigua, **S2B_MSIL1C_20260804T150719_N0512_R082_T19QGV_20260804T182348.SAFE**, por criterio cronológico reproducible. La fase 6 procesa una sola escena; el resto corresponde a la ejecución repetida posterior. Antes de descargar se vuelve a consultar disponibilidad/versión, porque estos resultados son una instantánea.

## Flujo seleccionado

1. Consultar primero el catálogo propio para detectar resultados reutilizables o cambios; si un L2R contiene reflectancias, TOA y datos de flags suficientes, derivar productos sin volver a adquirir RAW. No existe todavía la base SQLite implementada.
2. Consultar Zarr mediante la API STAC nativa, con base URL explícita, bbox y extremo final del día 21. Aplicar intervalo local exclusivo y validar identificación de adquisición/tile/nivel.
3. Si aparece un Zarr candidato, comprobar metadatos y estructura compatibles con el lector auditado antes de usarlo. No deducir compatibilidad solo de una extensión `.zarr`. Comprobar geometría y procedencia; no comparar checksum SAFE contra checksum Zarr como si fueran el mismo archivo.
4. Ante fallo transitorio de acceso Zarr: tres intentos totales, esperas de 60 y 300 segundos; registrar causa y avisar. Respetar Retry-After cuando el servicio lo indique. Tras agotar intentos, pasar automáticamente a SAFE e informar. Una consulta exitosa sin resultados o un formato incompatible permite fallback inmediato: repetir no crearía datos ausentes. En esta fase no hubo fallo transitorio y no se simuló esta política con esperas.
5. Para SAFE, usar catálogo, descarga y extracción nativos CDSE; una escena por directorio temporal. `remove_zip=False`, `remove_tar=False` y borrados de procesamiento desactivados durante el ensayo. No borrar tras L1R ni antes de validar L2R/L2W y registrar procedencia.
6. Verificar checksum disponible contra el archivo descargado y calcular SHA-256 propio. El catálogo observado proporciona MD5 y BLAKE3, no SHA-256: conservar algoritmo y valor originales, sin renombrarlos. Un nuevo baseline/contenido genera versión e historial; cambios administrativos por sí solos no obligan a recalcular.

La ruta inicial prevista es **SAFE temporal**, por ausencia de resultados Zarr en la consulta actual. La preferencia del perfil sigue siendo Zarr; no se ha medido su ahorro ni validado equivalencia radiométrica SAFE/Zarr.

## Recursos, acceso y trazabilidad

El techo de temporales es conjunto: 50.000.000.000 bytes. Antes de adquirir, considerar archivo, extracción, intermedios, auxiliares y salidas en construcción, además del espacio libre real. El tamaño publicado del archivo no permite asegurar cuánto ocupará el ensayo. Registrar el máximo de disco y memoria desde fase 6; no descargar las cinco escenas juntas. Si el presupuesto no alcanza, informar y detener esa adquisición, conservando catálogo/logs; no eliminar resultados persistentes para hacer espacio.

La descarga nativa auditada mantiene el contenido de respuesta en memoria; con archivos publicados de aproximadamente 0,77–0,81 GB se selecciona como candidata para el ensayo secuencial, sin prometer un pico total de RAM. No se implementa ahora un descargador alternativo. Observar consumo real antes de decidir si hace falta una extensión mínima de streaming.

Las consultas realizadas son públicas. No se leyeron credenciales ni se verificó autenticación de descarga. La presencia de `.netrc` no prueba autorización CDSE. En fase 6 deberá comprobarse acceso mediante la ruta nativa, sin imprimir secretos. Preparar la revisión fijada y sus rutas antes de ejecutar: la instalación habitual sigue en otra revisión.

La función CDSE nativa devuelve URLs/nombres/Attributes, pero descarta campos superiores como checksum, tamaño y footprint. La evidencia de esta fase conserva la respuesta HTTP original mediante instrumentación temporal. Para automatizar la procedencia se mantiene la extensión mínima y compatible definida en fase 3; no está implementada. Los JSON de evidencia son comprobaciones de investigación, no sustituyen al catálogo operativo SQLite.

## Evidencia y comprobaciones

- [Consulta STAC con default y error 404](evidence/phase5/stac_query.json).
- [Consulta STAC con URL normalizada](evidence/phase5/stac_query_normalized.json) y [respuesta vacía comprobada](evidence/phase5/stac_empty_response.json).
- [Respuesta CDSE completa y argumentos](evidence/phase5/cdse_query.json).
- [Resumen de candidatos](evidence/phase5/candidates.json), [comprobaciones](evidence/phase5/checks.json) y [hashes de entrega](evidence/phase5/manifest.json).

Se comprobaron coherencia YAML/TXT sin OC4, política sin nubosidad, respuesta STAC vacía válida, cinco identidades CDSE únicas dentro del intervalo y cobertura del AOI según footprints. No se probaron descarga, reintentos de transferencia, valores científicos, máscaras ni rendimiento. No se añade una suite que replique los catálogos: los tests operativos del wrapper corresponden a su implementación.

## Siguiente fase

La fase 6 requiere orden del usuario: preparar la revisión elegida, adquirir una escena y ejecutar el ensayo instrumentado. No comenzar todavía procesamiento masivo, limpieza ni Docker. Recordar la falta de datos in situ antes de la fase de validación científica.
