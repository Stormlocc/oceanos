# OCEANOS — pipeline costero con ACOLITE

Wrapper secuencial en WSL para Sentinel-2 y Landsat 8/9. ACOLITE realiza la ciencia; OCEANOS administra catálogo, reintentos y conservación. La validación científica de La Parguera sigue pendiente.

**Persistencia:** L1R + L2W + SQLite. Para nuevos productos: L1R → corrección atmosférica → L2R temporal → L2W. L2R se elimina después del QA técnico y registro. Se ahorra disco a cambio de repetir AC; reproducibilidad requiere configuración y recursos auxiliares compatibles.

## Comandos en Ubuntu WSL

```bash
cd /home/antho/projects/oceanos
alias oceanos='/home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m oceanos'
oceanos prepare
oceanos search
oceanos --profile config/aoi/lapargera_v1/landsat.yaml search
oceanos status
```

`status` lee solo SQLite, sin ACOLITE ni red. Muestra cada ejecución con escena, estados, error y ruta/disponibilidad del L2W:

```bash
oceanos status                      # todas, en orden cronológico
oceanos status --ultimas 5          # las 5 más recientes
oceanos status --estado FAILED      # STARTED, SUCCEEDED, SKIPPED, FAILED o INTERRUPTED
oceanos status 38d623c4             # detalle de una (id o prefijo único): claves, métricas, artefactos y eventos
```

La consulta no descarga escenas. Para avanzar paso a paso, ejecutar una versión concreta devuelta por `search`:

```bash
oceanos run --version ID_DE_VERSION
# O utilizar una fuente local:
oceanos run --source /ruta/escena.zip --scene NOMBRE_SENTINEL2.SAFE
# Regenerar desde L1R, sin descargar; vuelve a ejecutar AC:
oceanos --products 'Rrs_*,chl_oc3,fai,ndvi' derive --l1r /ruta/escena_L1R.nc --scene NOMBRE_SENTINEL2.SAFE
```

`run` sin versión ejecuta todo el intervalo. `--force` crea un intento nuevo. `recover` registra interrupciones y borra lo parcial de toda ejecución `INTERRUPTED` (temporal y carpeta `runs/ID` si no registró artefactos); se ejecuta automáticamente al iniciar `search`, `run` y `derive`, y un fallo de borrado queda en `limpieza=FAILED` sin detener el arranque. Un nuevo `run` vuelve a descargar desde cero. `cleanup ID` evalúa la limpieza de una ejecución concreta. Las opciones globales (`--profile`, `--products`, `--start`, `--end`) van antes del subcomando.

Perfiles actuales: Sentinel-2 del 1 al 14 de agosto de 2026 (`--end 2026-08-15`, exclusivo); Landsat del 1 al 20 (`--end 2026-08-21`, exclusivo). Los ensayos históricos usaron el intervalo 1–20 para ambos sensores. Nubosidad desactivada y configurable en YAML. Landsat acepta límites diarios UTC. OC4 excluido; NDCI solo Sentinel-2. Conservar L1R no crea bandas inexistentes ni permite ampliar un AOI ya recortado.

**Operación por autorización:** no descargar escenas, LUT, auxiliares ni dependencias sin autorización explícita del usuario. Los comandos anteriores son ejemplos, no una autorización de ejecución. `run` y `derive`, incluso con entrada local, pueden descargar recursos auxiliares de ACOLITE; `search` consulta metadata remota sin descargar escenas. El CLI actual no impone esta autorización ni tiene un modo sin red.

## Registro y archivos

- `storage/catalog/catalog.sqlite`: única trazabilidad operativa, con hashes, configuración, resumen científico y errores/métricas breves.
- `storage/runs/<id>/`: únicamente L1R y L2W al completar correctamente. L1R ya registrado se referencia como padre, sin copiarlo de nuevo.
- `storage/temporary/`: RAW, extracción y transporte efímero entre procesos.

No se guardan logs de éxito, JSON por etapa, manifiestos por ejecución ni backups por cada comando. Los intermediarios se retiran después de comprobar L1R/L2W; no se interpreta esto como aprobación científica. Fuentes externas, AOI y credenciales nunca se borran automáticamente.

Tres intentos remotos con esperas de 60 y 300 segundos. Sentinel-2 se adquiere como SAFE desde CDSE y Landsat como TAR desde USGS. Zarr EOPF no se usa: su catálogo STAC no cubre el AOI ([documento 06](docs/06_acolite_zarr_input.md#retirada-del-wrapper-01-10-2026)). USGS puede tener completitud desconocida. Se supervisa el presupuesto compartido de 50 GB cada dos segundos, sin prometer una cuota de disco instantánea. Credenciales en `~/.netrc`; no incorporarlas al repositorio.

Limitación conocida: cuando se reconoce una salida reutilizable después de descargar, el intento queda `SKIPPED` y conserva el RAW; `cleanup` actualmente aplaza ese caso. La corrección está pendiente. El reinicio autorizado anterior retiró las escenas de prueba y mantuvo el historial; ver [estado y conservación](docs/33_retention_and_reset.md).

## Pruebas

```bash
/home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m unittest discover -s tests -v
```

El entorno existente incluye GDAL/PROJ. OCEANOS usa la instalación `/home/antho/acolite` (opción `--acolite` para otra ruta), fijada en la revisión `80da0c0` con el [parche de catálogo](patches/acolite-catalog.patch) aplicado por `prepare`. Ver [instalación ACOLITE y `prepare`](docs/34_acolite_installation.md).

[Plan y documentación](docs/README.md) · [Conservación y reinicio de pruebas](docs/33_retention_and_reset.md). Docker/Airflow siguen pendientes de una nueva orden.
