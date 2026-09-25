# Catálogo, provenance y detección de cambios

## Diseño preliminar

Volumen inicial: un AOI, un sensor y veinte días; número real de escenas todavía desconocido. Predominan consultas por adquisición, versión, configuración y ejecución. Evaluar JSON para snapshots y SQLite para índice transaccional; no fijar ambos ni añadir Parquet hasta comprobar volumen y retornos reales en fase 3.

Persistir cada consulta, incluso sin resultados o fallida. Guardar metadata útil, no una copia indiscriminada de respuestas con campos volátiles o credenciales.

## Entidades mínimas

| Entidad | Campos propuestos |
|---|---|
| Consulta | Identificador, AOI/hash, proveedor, timestamp UTC, parámetros, estado, número de resultados |
| Observación de producto | Consulta, id proveedor, adquisición, sensor, nivel, colección, tile, órbita, baseline, footprint, nubosidad, checksum/tipo, fuentes disponibles |
| Ejecución | Id, producto/versionado, revisión ACOLITE, entorno, configuración, fingerprint, estado, tiempos, fuente efectiva, ejecución padre si deriva de L2R |
| Resultado | Ruta, tipo, variables, grilla, tamaño, checksum si calculado, validación, ejecución productora |
| Evento | Transición, intento, error, fallback o limpieza, timestamp y motivo |

Guardar solo atributos adicionales que ayuden a identificar, reproducir o evaluar cambios. Documentar ausencias como desconocidas; no inventar valores.

## Hashes

Separar hash de metadata seleccionada y hash de configuración científica. Canonicalizar orden, tipos, valores nulos y listas con semántica conocida. Excluir secretos, timestamps de consulta, rutas de logs y URLs temporales del fingerprint científico.

Fingerprint propuesto: identidad/versionado de entrada + hash AOI + revisión ACOLITE + settings efectivos relevantes + productos solicitados + grilla + versiones auxiliares disponibles. No asumir que los overrides por sí solos capturan defaults cambiantes.

## Comparación

Producto nuevo: registrar. Producto sin cambio relevante: vincular a nueva consulta sin repetir cálculo ya válido. Cambio de baseline/contenido: nueva versión y reprocesamiento. Cambio solo administrativo: registrar sin reprocesar. Nueva fuente Zarr: actualizar alternativas. Si no puede determinarse equivalencia científica, dejar incertidumbre explícita.

Las ejecuciones fallidas no satisfacen la condición de ya procesado. Un nuevo producto derivado no obliga a recalcular toda la cadena si existe un resultado compatible.
