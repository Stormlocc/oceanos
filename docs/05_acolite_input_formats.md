# Formatos de entrada

El soporte exacto está pendiente de auditoría. Evaluar por separado SAFE local, SAFE comprimido, Zarr remoto, Zarr local y entradas Landsat Collection 2 Level 1.

Para cada formato documentar reconocimiento del bundle, metadata necesaria, extracción, lectura espacial parcial, acceso de red, dependencias y limitaciones. No asumir que acceso HTTP equivale a lectura remota eficiente, ni que aceptar un archivo comprimido evita extraerlo.

Para Landsat estudiar MTL, Tier, `GRID_CELL_SIZE_REFLECTIVE`, UTM y proyección del lector. No extrapolar el comportamiento de Sentinel-2.

El formato elegido debe conservar la información necesaria para la corrección atmosférica y los productos solicitados. Un producto visual o previamente corregido no se considera intercambiable sin demostrarlo.
