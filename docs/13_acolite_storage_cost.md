# Recursos y benchmark

Entorno declarado: Intel Core i9 de 13.ª generación, 16 GB RAM físicos, WSL Ubuntu sobre Windows 11, asignación dinámica de RAM, WSL 2.6.1.0, aproximadamente 100 GB SSD libres y conexión de 100 Mbps. Presupuesto máximo de temporales: 50 GB. Estos valores no sustituyen mediciones del entorno efectivo.

Procesar una escena a la vez. No existen aún mediciones reales de duración, RAM o tamaños de producto y no se presentan estimaciones como resultados.

## Plan de medición

Instrumentar la primera escena desde adquisición para medir consulta, descarga, extracción, L1R, L2R, L2W, proyección y duración total. Obtener tiempos de etapas solo si son observables de manera fiable en logs o puntos de ejecución; indicar no disponible en otro caso.

Medir bytes transferidos cuando sea posible, tamaño adquirido, pico de RAM incluyendo subprocesos, pico de disco temporal y tamaños L1R/L2R/L2W. Registrar espacio persistente final después de limpieza, dependencias, fuente, revisión ACOLITE y configuración.

Para disco medir simultáneamente descarga, extracción, intermedios y salida todavía no validada. No sumar tamaños finales como sustituto del pico. Para RAM distinguir RSS del proceso y memoria efectiva de WSL; registrar método y frecuencia de muestreo.

Una conexión nominal de 100 Mbps equivale teóricamente a 12,5 MB/s, antes de sobrecarga y límites del proveedor. No es una predicción del tiempo real de descarga.

Evaluar NetCDF, compresión y discretización en código antes de cambiar defaults. No usar pérdida de precisión para ahorrar disco sin justificación científica. GeoTIFF solo para inspección o exportación específica.
