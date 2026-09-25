# Entradas soportadas y reconocimiento

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

| Entrada | Evidencia en código | Limitación |
|---|---|---|
| SAFE local L1C | `safe_test`, metadata y lector S2 | Rechaza nivel distinto de Level-1C |
| ZIP/TAR/GZ/TGZ/BZ2 | identify + extract_bundle | Extrae; no supone lectura directa comprimida |
| Zarr HTTPS terminado .zarr | inputfile_test/identify_bundle | Forma de URL estricta y metadata EOPF |
| Zarr local | Lector directo puede abrir ruta existente | identify_bundle no activa test_zarr para ruta existente |
| URI s3/http o URL firmada con sufijo distinto | No ruta automática equivalente comprobada | No prometer soporte genérico |
| Landsat bundle L1 | MTL + lector Landsat | No procesa L2 como si fuera L1 |
| ACOLITE NetCDF | generated_by y rhot/bt en identify | Un L2R reducido sin rhot puede fallar reconocimiento |

Fuentes: [acolite/acolite/inputfile_test.py:20](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/inputfile_test.py#L20-L47), [acolite/acolite/identify_bundle.py:19](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/identify_bundle.py#L19-L105), [acolite/sentinel2/l1_convert.py:90](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/l1_convert.py#L90-L99), [acolite/landsat/l1_convert.py:70](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/landsat/l1_convert.py#L70-L101).

La restricción Zarr local es del reconocimiento automático, no prueba de imposibilidad del lector. Resolver solo si realmente se necesita, sin escribir otro lector.

`acolite_run` permite que un NetCDF ya L2R omita corrección atmosférica y llegue a L2W; el archivo debe cumplir contrato de identificación y contener reflectancias/metadata requeridas. Esto favorece conservar L2R completo útil, sin garantizar reprocesamiento ilimitado.
