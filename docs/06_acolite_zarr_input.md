# Zarr remoto frente a SAFE temporal

Comparación conceptual, aún no experimental:

| Aspecto | Zarr remoto | SAFE temporal |
|---|---|---|
| Compatibilidad ACOLITE | Pendiente de proveedor y revisión | Pendiente de formato y revisión |
| Transferencia | Depende de chunks realmente leídos | Depende del producto adquirido |
| Espacio temporal | Depende de cachés y materialización | Incluye descarga y posible extracción |
| Reproducibilidad | Requiere identidad/versionado remoto | Requiere identidad/checksum del producto |
| Riesgos | Cambios de servicio, autenticación, layout | Tamaño y extracción |
| Decisión | Preferido solo si funciona correctamente | Fallback acordado |

Auditar `acolite/sentinel2/zarr` y rutas de descubrimiento relacionadas. Identificar proveedores reales, metadata, selección de ventanas, bandas y chunks, uso de fsspec/HTTP y ubicación de cachés. No afirmar reducción de tráfico o almacenamiento sin medir.

Si ambas fuentes están disponibles, comparar una misma adquisición: geometría, variables, valores válidos, diferencias científicas, tráfico, RAM, disco y tiempo. La ausencia de una fuente equivalente limita la comparación y debe declararse. No catalogar Zarr como estable para producción a partir de una única ejecución.
