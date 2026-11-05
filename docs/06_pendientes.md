# Pendientes, riesgos y trabajo futuro

Estado al 05-11-2026. Las descargas no cubiertas por las autorizaciones, el borrado de datos del usuario y los cambios de alcance se consultan antes.

## Superimagen: lo que falta

| Tema | Estado y siguiente paso |
|---|---|
| Ensayo de enero de 2026 | **Hecho** (04/05-11-2026): S2, Landsat y OLCI en las 4 zonas, sin escenas fallidas al final ([resultados](05_resultados.md#superimagen-ensayo-dic-2025--ene-2026)) |
| Calibración de glint | Con enero se mantienen 0,005 / 0,02 (S2 y Landsat) y 20° (OLCI, que en enero no descarta nada). Revisar con un mes de verano antes de procesar más meses |
| Respaldo EarthExplorer | 3 de 12 escenas Landsat lo usaron en enero sin motivo registrado; ahora queda en `via_descarga`. Revisar el motivo en el próximo lote |
| Más meses | Febrero–junio de 2026 en dos computadoras (S2 + OLCI en una, Landsat en otra), reunidos con `oceanos sync`. Presupuesto de 300 GB por computadora; un mes ocupa ~20 GB |
| Enero con `calidad.tif` de 13 bandas | Los productos de enero tienen el `calidad.tif` de 10 bandas, sin AOT ni geometría. Reprocesarlo (en curso el 05-11-2026 en otra máquina) y anotar aquí el resultado |
| Costos en la nube | Siguiente paso: estimar cómputo y almacenamiento con las cifras medidas en enero |

## Pendientes científicos

| Tema | Estado y siguiente paso |
|---|---|
| Datos in situ | Necesarios para aceptar cualquier producto: clorofila, turbidez y Kd coincidentes, con ubicación, hora, profundidad y control de calidad |
| Máscara L2W de ACOLITE | Confirmado en enero de 2026: con glint residual activo los productos acuáticos ya no quedan enmascarados como en el AOI de prueba ([resultados](05_resultados.md#superimagen-ensayo-dic-2025--ene-2026)). Revisar con un mes de verano |
| Agua muy somera y arrecifes | El fondo puede contaminar Rrs y FAI en La Parguera; evaluar con datos in situ |
| Media ponderada y variables parciales | En (b) estacional/anual, ponderar por `peso_total` es exacto salvo donde una variable faltaba en parte de las observaciones del mes ([07](07_superimagen.md#compuestos-de-calidad-de-agua)) |

## Riesgos y limitaciones técnicas

| Tema | Detalle |
|---|---|
| Respaldo EarthExplorer | Solo si M2M no entrega URL; lee el botón "Download Product" de la página y puede romperse si USGS la cambia |
| M2M en preparación | Si USGS tarda en preparar un pedido, se consulta `download-retrieve` cada 15 s hasta 20 veces; después la escena queda `FALLIDA` y se reintenta en otro `run` |
| Auxiliares | Si MERRA-2 falla, la zona queda `FALLIDA` con `AUXILIAR_POR_DEFECTO`. Coincidencia improbable: valores reales iguales a los tres defaults darían un falso positivo |
| Fuente sin checksum comparable | USGS no publica MD5/SHA del bundle: la reutilización del crudo depende del SHA-256 propio |
| WorldCover 2021 | Capa fija; cambios de costa posteriores (huracanes, rellenos) no se reflejan. El margen de 2 píxeles absorbe parte |
| Recursos | Presupuestos supervisados por muestreo, sin reservar espacio; la superimagen se comprueba antes de descargar y antes de exportar |
| Cambio de ACOLITE | Cambiar revisión o parche deja productos con linaje distinto; los compuestos no mezclan firmas pero sí escenas de distintas revisiones si se reprocesa parcialmente |
| Respaldo externo | Planificado para después: exportar la superimagen y el catálogo a un storage en la nube |

## Paralelo

Resuelto: conexión SQLite (WAL) por hilo, reservas de RAM por etapa con la RAM libre del equipo, prioridad a lo más avanzado, máximo 4 descargas CDSE, un ACOLITE por día, LUT preparadas por el primer ACOLITE ([operación](04_operacion.md#paralelo)).

Comprobado en enero de 2026: CDSE acepta 4 descargas a la vez (S2 corrió con 5–7 escenas en curso) y un corte de descarga S2 se reanudó con `Range`. En USGS no se midió cuántas descargas M2M coincidieron.

Pendiente:
- **Ganancia del paralelo.** No se midió contra una corrida de a una escena.
- **Pico de ACOLITE S2 sin historial.** El valor inicial (4,8 GB) queda corto: en enero se midieron hasta 7,85 GB. Con historial se usa el mayor pico de los últimos 20 procesos `OK` más un 10 %, así que solo afecta a un catálogo nuevo. Subir el valor inicial si un equipo nuevo se queda sin RAM.

## Trabajo futuro (no iniciado)

- **Docker y Airflow.** Flujo: catálogo → selección → adquisición → ACOLITE por zona → exportación → sargazo → compuestos → limpieza. Inventariar dependencias reales (GDAL con JP2OpenJPEG, netCDF y COG, pyproj, netCDF4) antes de contenerizar.
- **Validación científica** con datos in situ y comparación entre los métodos (a) y (b).
- **Productos propios.** Solo donde ACOLITE no cubra la necesidad.
