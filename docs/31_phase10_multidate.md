# Fase 10 — repetición por fechas e incorporación de Landsat

Cierre técnico: 30 de septiembre de 2026. Se completaron cinco adquisiciones Sentinel-2 y tres Landsat del 1 al 20 de agosto de 2026. La aceptación científica permanece pendiente. La fase 11 no se inició.

## Ejecución y alcance

Se reutilizó Sentinel-2 del 4 de agosto, ya procesado y verificado en fases 6–9, y se ejecutaron las otras cuatro adquisiciones. La consulta actualizada confirmó las cinco fuentes sin cambios de checksum. Las consultas Zarr devolvieron cero resultados y se utilizó SAFE. Esto no valida todavía la lectura remota Zarr ni los reintentos frente a fallos transitorios.

Para Landsat se consultaron seis productos. Los tres de path/row 005/048 cubren todo el AOI; los vecinos 005/047 son espacialmente redundantes para estas fechas. No se filtró nubosidad: sigue desactivada y configurable en ambos perfiles. El bloqueo inicial de CDSE (403) se superó utilizando la descarga nativa USGS con autenticación local, sin copiar credenciales a las evidencias.

ACOLITE realizó consulta, descarga, extracción, L1R, corrección atmosférica y L2W. Los scripts de esta fase son instrumentos manuales de ensayo; el catálogo SQLite y el wrapper operativo siguen pendientes de fase 11.

## Resultados comprobados

Las ocho adquisiciones tienen L1R, L2R y L2W, productos solicitados compatibles con su sensor, coordenadas comunes y flags enteros int32. Se verificaron los ejes completos, no solo las dimensiones: EPSG:32619, 2440 × 7335 píxeles, 10 m, x 701980–775330 m e y 1997360–1972960 m. Los SHA-256 de fuentes y productos están registrados en los resúmenes de evidencia.

| Sensor y fecha | Píxeles finitos OC3 | Porcentaje del rectángulo | Procesamiento (s) |
|---|---:|---:|---:|
| S2B 2026-08-04 | 0 | 0.000000% | 519.4 |
| S2C 2026-08-09 | 0 | 0.000000% | 268.5 |
| S2A 2026-08-11 | 16713 | 0.093382% | 300.9 |
| S2B 2026-08-14 | 0 | 0.000000% | 178.4 |
| S2C 2026-08-19 | 40374 | 0.225586% | 185.9 |
| L9 2026-08-01 | 0 | 0.000000% | 191.8 |
| L8 2026-08-09 | 0 | 0.000000% | 452.4 |
| L9 2026-08-17 | 58 | 0.000324% | 155.8 |

Los porcentajes usan los 17 897 400 píxeles del rectángulo, no una máscara oceánica independiente. Tener valores finitos no demuestra validez científica. Cinco adquisiciones carecen de valores acuáticos finitos y las otras tres conservan una fracción muy pequeña. FAI/NDVI mantienen la excepción de máscara nativa; su disponibilidad no demuestra agua válida. No se relajaron umbrales para obtener resultados.

NDCI se conserva para Sentinel-2 y se excluye de Landsat por falta de soporte nativo OLI en la revisión auditada. OC4 está excluido de ambos. La banda Rrs alrededor de 613 nm de Landsat procede de contrabandas sintéticas nativas; no es una banda observada directamente.

## Incorporación Landsat y correcciones

El perfil [Landsat](../config/aoi/lapargera_v1/acolite_l89_candidate.txt) reproyecta L1R antes de la corrección atmosférica mediante ACOLITE, con nearest. L2W genera sus flags después: no se utiliza la reproyección final que omite l2_flags. La entrega a 10 m no aumenta el detalle óptico original de 30 m. DSF usa tiles de 600 × 600 a 10 m para mantener una escala física aproximada de 6 km; su validez científica sigue pendiente.

El primer ensayo Landsat produjo una grilla incorrecta porque faltaba `output_projection_metres=True`. Se corrigió y reprocesó desde L1R, sin descargar nuevamente. Se conservaron ambos intentos. El primer SIGINT fue absorbido por una rutina nativa de LUT: hubo un solapamiento breve hasta detener el proceso anterior con SIGTERM. El registro [de corrección](evidence/phase10/LC09_L1TP_005048_20260801_20260801_02_T1/grid_correction.json) distingue los logs y resultados finales. Los 191,8 s del 1 de agosto corresponden a esa reanudación, no a un ensayo completo aislado.

Landsat 8 encontró una LUT específica no descargable; ACOLITE usó su alternativa nativa y remuestreó la LUT genérica. Se completó el procesamiento. El máximo RSS individual registrado fue 6,57 GB decimales. Se mantiene concurrencia configurada uno. Los tiempos de la tabla excluyen descarga; mezclan caché fría/caliente y no constituyen una comparación de rendimiento entre sensores.

## Conservación y dictamen

El inventario final de ensayos, fuentes, productos y datos auxiliares ocupa 27,84 GB decimales, por debajo del presupuesto conjunto de 50 GB. No se borraron fuentes ni intentos; se conservan L2R para futuras derivaciones. Los hashes identifican representaciones: el SHA-256 local del TAR USGS no sustituye un checksum publicado por el proveedor ni debe compararse con el MD5 del ZIP de CDSE.

La fase queda terminada en su alcance técnico de repetición e integración de Landsat. Los perfiles permanecen candidatos: falta validar máscaras y calidad del agua, disponer de datos in situ y resolver la salida exclusivamente oceánica. Esto no equivale a aprobación científica ni a un pipeline operativo.

Evidencias: [Sentinel-2](evidence/phase10/technical_summary.json), [Landsat](evidence/phase10/landsat_technical_summary.json), [comprobaciones de cierre](evidence/phase10/closure_checks.json) y [procedencia final](evidence/phase10/final_provenance.json). La fase 11 requiere una nueva orden del usuario.
