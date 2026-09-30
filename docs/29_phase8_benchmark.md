# Fase 8 — análisis del benchmark de una escena

> Informe histórico del ensayo. La retención y los archivos disponibles cambiaron por orden del usuario; rige la [política L1R/L2W y reinicio](33_retention_and_reset.md). Las cifras de este documento describen el ensayo previo a la limpieza.

Fecha: 29 de septiembre de 2026. **Fase 8 completada mediante análisis del ensayo existente.** El entorno local pudo procesar una escena secuencial dentro del presupuesto de recursos. Esto no cambia el dictamen de fase 7: los productos acuáticos siguen no aceptados por enmascarado total.

No se repitió la descarga, no se reprocesó la escena, no se cambiaron parámetros ni se limpiaron fuentes. La evidencia procede de las dos ejecuciones de fase 6 y de una inspección de tamaños y filtros NetCDF en esta fase.

## Tiempos observados y su alcance

| Operación | Tiempo | Interpretación |
|---|---:|---|
| Consulta Zarr | 0,92–1,25 s | Dos consultas vacías; no lectura de Zarr |
| Consulta CDSE | 19,57–29,40 s | Dos consultas de metadata |
| Descarga SAFE | 368,03 s (6 min 8 s) | Primer intento; ZIP de 789.574.421 bytes |
| Extracción | 1,13–1,28 s | SAFE completo |
| L1R completado | 38,44 s | Conversión y recorte nativos |
| L2R completado | 423,06 s (7 min 3 s) | Corrección y preparación inicial de LUT |
| L2W completado | 57,85 s | Derivación, flags y escritura |
| Procesamiento completado | 519,38 s (8 min 39 s) | Incluye L1R, L2R y L2W; no sumar otra vez sus etapas |
| Intento completado, tiempo de pared | 556,57 s (9 min 17 s) | Consultas, ZIP reutilizado, extracción, hashes y procesamiento |
| Primer intento, tiempo de pared | 395,59 s (6 min 36 s) | Incluye descarga y fallo PROJ temprano |
| Intervalo entre inicio primero y fin segundo | 1115,89 s (18 min 36 s) | Incluye intervención para corregir activación del entorno |

No hubo reproyección final. El segundo intento tiene descarga ≈0 s por reutilización del ZIP; no representa una descarga rápida ni un benchmark independiente con caché completamente preparada. No hay repetición suficiente para informar variabilidad o percentiles de rendimiento.

**L2R representa el 81,46 % del tiempo de procesamiento**, pero sus 423 s mezclan cálculo y obtención inicial de tablas. Los logs no tienen tiempos individuales suficientes para separar ambas contribuciones. No atribuir todo ese tiempo a CPU ni estimar un rendimiento con caché restando un tiempo inventado.

La relación tamaño útil del ZIP/tiempo de descarga equivale a 17,16 Mbps. Es una tasa útil aparente, no una medición del enlace ni de bytes de red: la función nativa realiza peticiones adicionales y mantiene respuestas en memoria. No se puede concluir que la conexión de 100 Mbps esté limitada a esa velocidad. No se midieron CPU acumulada, E/S de bloques, tráfico real ni consumo energético.

## Memoria y concurrencia

| Medición | Resultado |
|---|---:|
| RAM WSL disponible como total efectivo al inicio | Aproximadamente 7,6 GiB |
| Máximo RSS del proceso, Linux ru_maxrss | 4.744.155.136 bytes = 4,74 GB = 4,42 GiB |
| Pico del árbol de procesos, muestreo cada 5 s | 4.612.444.160 bytes = 4,61 GB |
| Máximo RSS del primer intento con descarga | 2.519.633.920 bytes = 2,52 GB |

La diferencia entre máximo del proceso y máximo muestreado es esperable: el muestreo puede perder picos breves. No se suman ambos valores. Tampoco incluyen toda la memoria de Windows, WSL o la caché del sistema.

**Mantener concurrencia uno.** Dos procesos con el máximo observado sumarían alrededor de 8,84 GiB de RSS, por encima de los 7,6 GiB efectivos observados, antes de otros consumos. No activar paralelismo por escena ni aumentar arbitrariamente la memoria de WSL en esta fase. Un AOI mayor requiere nueva medición; este resultado no establece una capacidad máxima universal.

## Disco y retención

| Componente retenido | Bytes | GB decimales |
|---|---:|---:|
| ZIP | 789.574.421 | 0,790 |
| SAFE extraído | 789.551.049 | 0,790 |
| L1R | 314.882.514 | 0,315 |
| L2R | 773.895.782 | 0,774 |
| L2W | 121.980.380 | 0,122 |
| LUT locales | 605.823.732 | 0,606 |
| Carpeta data completa, **incluye LUT** | 629.519.224 | 0,630 |

La carpeta output completa, incluidos settings y logs, ocupa 1.210.813.821 bytes. No sumar la fila LUT a data: está contenida en ella.

Durante el ensayo, el máximo muestreado fue 3.360.989.947 bytes y la medición final fue 3.419.458.515 bytes, equivalente al 6,84 % del techo de 50 GB. Se conserva la diferencia: **3,42 GB es ocupación final observada, no un pico continuo certificado**. El alcance comprende RAW, output, scratch y data de la copia auditada, incluyendo recursos anteriores.

L2R+L2W suman 895.876.162 bytes, unos 0,896 GB. Es el tamaño actual del par retenido, no un tamaño persistente medido después de limpieza. ZIP+SAFE representan aproximadamente 1,579 GB potencialmente recuperables; ZIP+SAFE+L1R unos 1,894 GB. Son escenarios contables, **no una autorización para borrar**. La fase 9 deberá aplicar el estado de calidad no aceptado y conservar lo necesario para diagnosticar/reprocesar.

No convertir el cociente 50/3,42 en un número de escenas seguras: cambian tamaños de origen, máscaras, LUT compartidas, compresión y etapas simultáneas. Mantener adquisición secuencial y comprobar espacio físico del host además del disco virtual WSL.

## NetCDF y representatividad

Se inspeccionaron los filtros de todas las variables bidimensionales en los tres archivos: zlib nivel 4 y shuffle activos. Las variables científicas usan Float32; l2_flags conserva tipo entero. No se encontró `least_significant_digit` en esas variables. El perfil mantiene discretización desactivada; no se introdujo compresión con pérdida.

No se compararon niveles de compresión, formatos alternativos o exportación GeoTIFF. Se conserva la configuración actual porque un único ensayo no justifica cambiarla. La mayoría de las variables acuáticas L2W contienen solo valores enmascarados y comprimen con facilidad; su tamaño y tiempo de escritura **no son representativos de una escena con abundantes píxeles válidos**.

La salida rectangular observada tiene 17.897.400 píxeles. El comportamiento de memoria y tiempo no debe extrapolarse linealmente a otra resolución o AOI: intervienen tiles DSF, geometría, LUT y memoria temporal. Tampoco hay comparación SAFE/Zarr: no hubo Zarr disponible para este intervalo.

## Decisiones y límites

- Mantener una escena por ejecución, 10 m para este perfil, NetCDF nativo comprimido y sin reproyección final.
- Conservar y reutilizar las LUT ya obtenidas, registrando sus hashes. No volver a descargarlas para simular un primer arranque.
- No implementar otro descargador, cambiar compresión, ampliar WSL ni migrar a nube basándose solo en esta muestra.
- Corregir siempre la activación del entorno mediante micromamba antes de ejecutar; la descarga y el procesamiento no necesitan repetirse para verificar esa incidencia ya resuelta.
- Registrar en futuras ejecuciones tiempos de red separados, CPU y medición de recursos con mayor resolución solo si hace falta responder a una limitación real. No añadir instrumentación compleja ahora.
- Antes de estimar costes operativos de productos útiles, resolver o evaluar el problema científico de máscara/glint y medir una escena aceptable cuando su fase esté autorizada.

Evidencia: [análisis de tiempos, inventario y filtros — evidencia consolidada](33_retention_and_reset.md#historial), [métricas de ejecución — evidencia consolidada](33_retention_and_reset.md#historial), [primer intento — evidencia consolidada](33_retention_and_reset.md#historial), [LUT y hashes — evidencia consolidada](33_retention_and_reset.md#historial), [dictamen de validación](28_phase7_validation.md).

La fase 8 queda cerrada como análisis de esta medición, con las limitaciones indicadas. La fase 9 requiere orden del usuario; no se eliminó ningún archivo.
