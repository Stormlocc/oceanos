# APIs de catálogo y metadata realmente devuelta

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

## CDSE

Firma relevante: `query(scene=None, collection=None, product=None, start_date=None, end_date=None, roi=None, level=1, sensor=None, cloud_cover=None, tile=None, processor_version=None, ..., max_results=1000, odata_url=None, attributes=False)`.

Devuelve `(urls, scenes)` o `(urls, scenes, atts)` con `attributes=True`. `atts` conserva únicamente `Attributes`; el JSON top-level se descarta. Id puede recuperarse de la URL, nombre se conserva, pero footprint, checksum, ContentLength y demás campos top-level no están garantizados en este retorno. No afirmar que un snapshot del retorno es copia íntegra del catálogo. En fase 3 decidir enriquecimiento mínimo o ajuste estrecho del retorno nativo, evitando un cliente propio.

`collection='SENTINEL-2', level=1` selecciona S2MSI1C si no se da producto. Tile admite `19QGV` o `T19QGV`. `sensor` no se traduce en filtro de plataforma S2: no asumir que pedir S2A por ese argumento limita resultados. ROI delega en `shared.roi_wkt`, con intersección OData. `processor_version` filtra `processorVersion`. `cloud_cover=None` no añade filtro; cuando se da valor usa comparación estricta menor que.

Fecha inicial: `ContentDate/Start gt inicio`. Fecha final: añade un día y usa `lt`. Para fechas de calendario 2026-08-01/2026-08-20 incluye el día 20, pero excluye una adquisición exactamente a medianoche del inicio. Evitar añadir externamente otro día. `max_results` es tamaño de página solicitado, no límite total: sigue `@odata.nextLink` hasta terminar. No hay timeout/retry explícito ni `raise_for_status`; una respuesta HTTP errónea puede confundirse con vacío o causar excepción.

Fuente: [acolite/api/cdse/query.py:17](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/api/cdse/query.py#L17-L218); ROI: [acolite/shared/roi_wkt.py:8](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/shared/roi_wkt.py#L8-L52).

## EarthExplorer

`query(scene=None, collection=2, level=1, dataset=None, landsat_type=None, ..., start_date=None, end_date=None, roi=None, cloud_cover=None, max_results=1000, api_url=None, attributes=False)`.

Para L8/L9 usa por defecto `landsat_ot_c2_l1`. Retorna entity ids, product identifiers y datasets; con attributes añade listas de metadata completas solicitadas por escena. La respuesta de scene-search puede tener campos adicionales que no retorna. No hay argumento Tier 1, path/row ni sensor independiente: seleccionar/validar esos atributos después. No hay bucle de paginación explícito: controlar resultados incompletos antes de ampliar período.

Obtiene acceso mediante `earthexplorer_token`; la descarga tiene otra ruta de autenticación. El filtro ROI toma puntos 0 y 2 del contorno como esquinas, no calcula un envolvente robusto para cualquier polígono. Usar un rectángulo preparado con la convención requerida. Fechas no siguen la misma regla de CDSE: para Landsat no añade automáticamente un día al final. No reutilizar un único adaptador temporal sin pruebas.

Fuente: [acolite/api/earthexplorer/query.py:12](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/api/earthexplorer/query.py#L12-L211).

## STAC

`query(limit=None, start_date=None, end_date=None, nlimit=100, scene=None, sensor=None, select_features=False, base_url='https://stac.core.eopf.eodc.eu/', collection='sentinel-2-l1c')`.

Por defecto retorna features completos, id/geometry/properties/assets/links según servicio. Con `select_features=True` reduce a ids y URLs `assets.product.href` y filtra sensor por prefijo de id. Mantener features para provenance; seleccionar tile mediante properties/id después, pues no hay argumento tile. `query_get` sigue recursivamente links next.

Limitaciones reproducidas sin red: sin limit, la construcción de datetime antepone `?` a toda la URL; con bbox y end_date 2026-08-20 termina a 00:00 del día 20, salvo el caso particular inicio=fin. Para nuestro intervalo, preparar final explícito y filtrar pertenencia temporal conforme al contrato confirmado en fase 3. No confundir fin de día con fin exclusivo 21-08 sin revisar semántica del servicio.

Fuentes: [acolite/api/stac/query.py:7](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/api/stac/query.py#L7-L75), [acolite/api/stac/query_get.py:7](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/api/stac/query_get.py#L7-L41). Evidencia: `evidence/phase2/comprobaciones.json`.

## Identidades

Mantener adquisición, producto/baseline y representación como conceptos distintos. Checksum del proveedor se almacena con algoritmo; no asumir SHA-256. Los parámetros de consulta y sus timestamps pertenecen a provenance, no al fingerprint científico. Diseñar persistencia definitiva en fase 3 con estas limitaciones ya conocidas.

## Decisión de fase 3

El [diseño definitivo del catálogo](16_catalog_provenance.md) elige SQLite, snapshots inmutables de metadata seleccionada, seis tablas y extensión mínima compatible del retorno CDSE cuando se programe. Define el intervalo interno UTC semiabierto y las diferencias entre proveedores. No hubo consultas reales de adquisiciones durante esa fase.
