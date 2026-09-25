# Catálogo y selección de escenas

## Regla acordada

Buscar Sentinel-2 para el AOI durante el 1–20 de agosto de 2026 inclusive. Procesar todas las adquisiciones válidas. No filtrar por nubosidad; registrar su valor cuando esté disponible. Mantener el filtro desactivado en el perfil, sin confundir ausencia de filtro con nubosidad máxima cero.

Nivel de producto, tile y parámetros de búsqueda definitivos pendientes de la auditoría. L1C es candidato que debe verificarse frente al flujo científico.

## Identidad

Separar adquisición física —sensor/plataforma, instante, tile y órbita cuando exista— de producto publicado —proveedor, identificador, nivel y baseline/versión— y de representación descargable —SAFE, Zarr, URI y checksum—.

Dos representaciones de la misma adquisición no son necesariamente bytes iguales. No usar únicamente el hash del archivo para agrupar adquisiciones. Conservar nombre del algoritmo junto con cada checksum; no llamarlo SHA-256 si el proveedor publica otro tipo.

## Cambios

Si cambian versión o contenido científico de entrada, registrar la nueva variante y reprocesar. Un cambio de URL temporal o fecha de consulta no justifica reprocesamiento científico por sí solo. La aparición de Zarr modifica las opciones de adquisición y queda registrada.

La política precisa ante diferencias ambiguas se definirá a partir de metadata real. No eliminar registros antiguos ni sobrescribir productos de ejecuciones previas sin conservar su provenance.

## Auditoría de API

Comprobar firma, retorno, paginación, límites, inclusividad de fechas, formatos ROI, atributos opcionales y restricciones de nivel de `ac.api.cdse.query` y `ac.api.earthexplorer.query`. Son referencias solicitadas, todavía no llamadas verificadas. Si la API no expone metadata necesaria, documentar la carencia antes de diseñar un adaptador.
