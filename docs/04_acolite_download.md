# Descarga, extracción y límites operativos

> Estado vigente (30-09-2026): descarga/extracción nativas integradas en el wrapper, con checksums, rutas controladas, tres intentos y esperas de 60/300 s. El supervisor acota duración y disco; no convierte la descarga nativa en streaming. No descargar sin autorización, incluidos auxiliares. Véase [operación y límites](32_phase11_wrapper.md).

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

## Descarga CDSE

`download(urls, scenes=[], output=None, auth=None, auth_url=None, netrc_machine='cdse', extract_zip=True, remove_zip=True, override=False, verbosity=1)` retorna rutas locales existentes.

Autenticación nativa vía `.netrc` y otras fuentes. El método imprime el token si `verbosity>1`: mantener nivel 1 en esta llamada y evitar guardar tokens/URLs firmadas en logs. No se probaron credenciales ni se imprimieron secretos.

La descarga final usa `session.get` sin `stream=True`; iterar `iter_content` después no evita el buffering previo de requests. Además hace solicitudes para resolver redirecciones. Puede aumentar memoria/tráfico. No hay reintentos, timeouts generales ni checksum de integridad. Existencia de ZIP/SAFE provoca reutilización, incluso si quedó parcial: antes de reintentar no tomar existencia como éxito.

`remove_zip=True` borra tras extracción y existencia de carpeta, antes del QA técnico propio. Para cumplir la política vigente, usar `remove_zip=False` o adquirir comprimido con `extract_zip=False` y extraer con ACOLITE dentro del workspace temporal. El wrapper actual usa extract_zip=False y remove_zip=False al adquirir, y delega la extracción después de verificar integridad.

Fuente: [acolite/api/cdse/download.py:10](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/api/cdse/download.py#L10-L142).

## EarthExplorer

`download(entity_list, dataset_list, identifier_list, output=None, extract_tar=True, remove_tar=True, override=False, verbosity=1)`. Localiza enlaces mediante HTML de EarthExplorer y sesión; no es un cliente moderno exclusivo de download-request M2M. Sensible a cambios del portal. La descarga final también carece de streaming explícito; `remove_tar=True` elimina antes de QA propia. Fuente: [acolite/api/earthexplorer/download.py:10](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/api/earthexplorer/download.py#L10-L182).

## Extracción

`shared.extract_bundle` maneja TAR/ZIP/BZ2. Reconoce bundle y devuelve ruta identificada y ruta extraída. El argumento `targ_bundle` se reinicia internamente; no confiar en él para confinar la extracción. Usar `output` y archivos fuente dentro de un directorio por run, verificando rutas devueltas. Fuente: [acolite/shared/extract_bundle.py:9](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/shared/extract_bundle.py#L9-L89).

## Política de producto

Conservar los tres intentos totales propuestos para fallos transitorios, esperas 1/5 minutos y límite 50 GB. La auditoría demuestra que ese control pertenece a nuestro wrapper mínimo. El parche de fase 11 acota consultas y expone metadata; el supervisor limita las etapas. No se implementó streaming de descargas. Los benchmarks históricos están en fases 8/10 y no certifican un límite instantáneo de RAM o disco.


## Actualización de fase 5 — 29 de septiembre de 2026

La consulta de metadata encontró cinco SAFE L1C de 19QGV y ningún Zarr para el intervalo inicial. SAFE fue la entrada del primer ensayo. Desde el 01-10-2026 Zarr está retirado del wrapper y SAFE desde CDSE es la única entrada Sentinel-2 ([documento 06](06_acolite_zarr_input.md#retirada-del-wrapper-01-10-2026)). Ver [estrategia de adquisición y evidencia](26_phase5_input_strategy.md). En fase 5 no se descargaron escenas ni se midió rendimiento; los ensayos posteriores están en fases 6/8/10.
