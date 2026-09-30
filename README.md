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

La consulta no descarga escenas. Para avanzar paso a paso, ejecutar una versión concreta devuelta por `search`:

```bash
oceanos run --version ID_DE_VERSION
# O utilizar una fuente local:
oceanos run --source /ruta/escena.zip --scene NOMBRE_SENTINEL2.SAFE
# Regenerar desde L1R, sin descargar; vuelve a ejecutar AC:
oceanos --products 'Rrs_*,chl_oc3,fai,ndvi' derive --l1r /ruta/escena_L1R.nc --scene NOMBRE_SENTINEL2.SAFE
```

`run` sin versión ejecuta todo el intervalo. `--force` crea un intento nuevo. `recover` registra interrupciones; `cleanup ID` evalúa limpieza. Las opciones globales (`--profile`, `--products`, `--start`, `--end`) van antes del subcomando.

Perfil inicial: 1–20 de agosto de 2026; `--end 2026-08-21` es exclusivo. Nubosidad desactivada y configurable en YAML. Landsat acepta límites diarios UTC. OC4 excluido; NDCI solo Sentinel-2. Conservar L1R no crea bandas inexistentes ni permite ampliar un AOI ya recortado.

## Registro y archivos

- `storage/catalog/catalog.sqlite`: única trazabilidad operativa, con hashes, configuración, resumen científico y errores/métricas breves.
- `storage/runs/<id>/`: únicamente L1R y L2W al completar correctamente. L1R ya registrado se referencia como padre, sin copiarlo de nuevo.
- `storage/temporary/`: RAW, extracción y transporte efímero entre procesos.

No se guardan logs de éxito, JSON por etapa, manifiestos por ejecución ni backups por cada comando. Los intermediarios se retiran después de comprobar L1R/L2W; no se interpreta esto como aprobación científica. Fuentes externas, AOI y credenciales nunca se borran automáticamente.

Tres intentos remotos, esperas de 60 y 300 segundos y fallback SAFE informado. USGS puede tener completitud desconocida; Zarr real continúa pendiente de una escena compatible. Se supervisa el presupuesto compartido de 50 GB cada dos segundos, sin prometer una cuota de disco instantánea. Credenciales en `~/.netrc`; no incorporarlas al repositorio.

## Pruebas

```bash
/home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m unittest discover -s tests -v
```

El entorno existente incluye GDAL/PROJ. El parche de catálogo se aplica únicamente a la copia auditada `.work/acolite-audit`; `/home/antho/acolite` permanece intacta.

[Plan y documentación](docs/README.md) · [Conservación y reinicio de pruebas](docs/33_retention_and_reset.md). Docker/Airflow siguen pendientes de una nueva orden.
