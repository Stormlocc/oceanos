# Fase 11 — wrapper mínimo y catálogo operativo

> Informe histórico del ensayo. La retención y los archivos disponibles cambiaron por orden del usuario; rige la [política L1R/L2W y reinicio](33_retention_and_reset.md). Las cifras de este documento describen el ensayo previo a la limpieza.

Fecha: 30 de septiembre de 2026. Estado: implementada y verificada técnicamente en WSL Ubuntu. No se inició fase 12.

## Comportamiento implementado

La interfaz `python -m oceanos` interpreta los perfiles del AOI y delega consulta, descarga, extracción, procesamiento y derivación en ACOLITE. El arranque es manual, la ejecución secuencial y la configuración conserva el intervalo 1–20 de agosto de 2026 y la nubosidad desactivada.

SQLite contiene las seis entidades del diseño de fase 3: consultas, versiones de producto, observaciones, ejecuciones, artefactos y eventos. Para mantener el MVP pequeño, varios campos del diseño detallado se agrupan en snapshots JSON en lugar de columnas independientes. Se conserva una versión de esquema, relaciones, snapshots inmutables, contador de duplicados, hashes de contenido y metadata, configuración y estados separados de validación/limpieza. El respaldo usa la API SQLite; no copia una base abierta a ciegas.

Las llamadas nativas se aíslan en procesos. El supervisor registra resultados por etapa, duración y RSS, impone tiempo máximo, revisa el presupuesto compartido y termina el grupo de procesos si debe detenerlo. El bloqueo de escritor evita concurrentes sobre el mismo catálogo. Una interrupción conserva fuentes y se reconcilia con `recover`.

La idempotencia compara SHA-256, configuración y revisión efectiva del procesador; también verifica archivos disponibles. Un checksum remoto comparable puede reutilizar un SHA local comprobado. Si no existe esa evidencia —caso habitual USGS— se descarga y verifica antes de decidir. Los cambios administrativos conservan la misma clave científica. SAFE y Zarr sin equivalencia demostrada mantienen identidades distintas.

Se busca L2R compatible antes de adquirir de nuevo cuando hay identidad comprobada. Una derivación registra el artefacto padre, crea otra ejecución y verifica productos completos, grilla, EPSG y flags. La aceptación técnica permite omitir cálculo repetido; no aprueba ciencia ni autoriza la limpieza por éxito. Esta distinción concreta la palabra “validado” del diseño de fase 3.

## Adaptación nativa delimitada

[Parche](../patches/acolite-catalog.patch): retorno opcional CDSE con metadata seleccionada, detección de HTTP/páginas inválidas y timeout de consultas CDSE/STAC; detección de error explícito USGS. El retorno por defecto CDSE sigue compatible. No se intercepta globalmente requests ni se implementa otro cliente satelital.

`prepare` comprueba el commit fijado y aplica el parche a la copia auditada. Cada ejecución registra commit, SHA del parche y hash del diff efectivo. No se alteró la instalación anterior. La paginación USGS continúa siendo una limitación nativa y su completitud se marca desconocida.

## Validación y evidencias

Las 22 pruebas automatizadas pasaron. La suite prueba duplicados, snapshots históricos, cambios de contenido, cambios administrativos, separación SAFE/Zarr, reutilización L2R sin red, fechas límite, productos no soportados, ausencia/corrupción de artefactos, exclusión mutua, interrupción, limpieza segura, limpieza fallida, reintentos/fallback y verificaciones de grilla/productos/flags. No vuelve a implementar algoritmos científicos.

Las consultas reales devolvieron cinco escenas CDSE y tres Landsat elegibles de USGS; STAC devolvió cero candidatos. Se ejecutó una derivación real desde L2R Landsat y una repetición quedó omitida. También terminó la ejecución completa desde ZIP Sentinel-2, con validación de productos y flags. Su repetición quedó omitida sin recalcular. El resumen final se documenta en [evidencia de integración — evidencia consolidada](33_retention_and_reset.md#historial).

Los ensayos científicos previos no se importan como aprobados automáticamente: permanecen como evidencia histórica. El catálogo nuevo registra sus propias operaciones. El archivo L2R externo de prueba se identifica por SHA, sin atribuirle retrospectivamente una provenance no registrada.

## Pendientes delimitados

La validación científica y los datos in situ siguen pendientes: recordar su incorporación al preparar la validación del producto acuático. No se relajan máscaras. La resolución común sigue siendo 10 m y no agrega detalle original a Landsat; NDCI solo Sentinel-2, OC4 excluido.

El presupuesto de 50 GB se controla por muestreo, no por cuota de filesystem. Zarr remoto real todavía no tiene una escena compatible de este AOI; las pruebas de fallback son simuladas. La trazabilidad incluye settings efectivos y un inventario de recursos disponibles, sin afirmar una traza exhaustiva de LUT/auxiliares realmente consumidos. La ruta de descarga usa las funciones ya ensayadas en fase 10; esta fase evita descargar escenas nuevamente para la prueba de procesamiento.

Comandos y operación: [README](../README.md). La siguiente fase, Docker/Airflow, requiere orden explícita.

Inventario compartido al cierre: 30.65 GB decimales, por debajo de 50 GB. Fuentes científicas conservadas.
