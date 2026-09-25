# Corrección atmosférica

ACOLITE realizará la corrección. No implementar algoritmos atmosféricos propios ni modificar defaults sin justificación.

Auditar método atmosférico, DSF, selección de bandas/espectro/modelo, percentil, intercepto, dimensiones de tiles, rango espectral, gases, datos auxiliares, presión, viento, DEM, glint y adyacencia. Los nombres exactos, defaults y compatibilidad deberán extraerse del código.

Clasificar cada setting verificado como conservar default, override de AOI, experimental o no requerido. Registrar dependencia del sensor y del formato de entrada.

La precedencia general → sensor → usuario es la hipótesis a comprobar siguiendo los loaders y las actualizaciones de settings. Conservar overrides mínimos y settings efectivos cuando el procesador permita obtenerlos.

No hay datos in situ disponibles todavía. Antes de validar científicamente la configuración se recordará al usuario incorporar observaciones, unidades, fechas y localización. Éxito de ejecución no demuestra exactitud científica.
