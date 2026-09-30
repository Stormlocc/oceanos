# Airflow y Docker futuros

No implementar antes de estabilizar el procesamiento manual, repetir fechas e incorporar Landsat. La automatización no debe cambiar decisiones científicas.

Flujo conceptual: descubrir catálogo → comparar versiones → seleccionar → adquirir → ACOLITE → validar → persistir resultados → limpiar → futura ingestión Zarr.

Cada operación tendrá identificador, estado y resultado observable. Reanudar a partir de resultados válidos; no repetir una corrección completa por un fallo de limpieza. Evitar reintentos multiplicados entre Airflow, wrapper y cliente nativo.

Concurrencia inicial uno para procesamiento ACOLITE. Ajustar solamente con benchmark. Ejecución manual por rango de fechas prioritario; no se requiere tiempo casi real.

Inventariar dependencias Python, GDAL/JP2/OpenJPEG, NetCDF, pyproj, pyresample, Zarr, fsspec y aiohttp según imports reales. Comparar entorno WSL con contenedor ACOLITE solo después de estabilizar la base. Docker CLI instalado no demuestra daemon disponible ni entorno científico configurado.

Colab se considerará tras la implementación base, contemplando almacenamiento efímero, persistencia externa y credenciales de sesión. Nube futura sin proveedor seleccionado.

## Resultados de auditoría de fase 2

Dependencias verificadas contra [environment.yml:1](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/environment.yml#L1); módulos remotos requieren Zarr/fsspec/aiohttp y GDAL Zarr. ACOLITE usa settings globales mutables; aislar proceso por ejecución antes de concurrencia entre AOI. Reintentos, límites, provenance y QA propios siguen siendo pequeños controles externos. Docker y Airflow no se implementaron ni se probaron en esta fase.

## Política vigente de conservación

En la futura fase de orquestación, persistir solo L1R/L2W y SQLite. La tarea de regeneración parte de L1R, repite AC y retira L2R tras QA técnico. Airflow no deberá crear otra copia del catálogo ni logs científicos redundantes. Ver [decisión transversal](33_retention_and_reset.md).
