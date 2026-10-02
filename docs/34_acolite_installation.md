# Instalación ACOLITE usada por OCEANOS y comando `prepare`

Fecha: 1 de octubre de 2026. Decisión del usuario: usar la instalación existente en lugar de una copia dentro del proyecto. No inicia otra fase ni procesa escenas.

## Por qué existía `.work/acolite-audit`

En la fase 2 la instalación `/home/antho/acolite` estaba en `f73cbe7` (abril de 2026) y tenía una modificación local en `config/config.txt`. La auditoría clonó upstream `80da0c0` en `.work/acolite-audit` para no alterar la instalación, y todas las fases 6–11 se ejecutaron desde esa copia con el parche de catálogo. Entre ambas revisiones cambian defaults científicos y de almacenamiento ([fase 2](23_phase2_audit_results.md)), por eso no se podía usar la instalación sin actualizarla.

## Cambio aplicado

1. `config/config.txt` de la instalación se restauró desde el repositorio. La única diferencia era una línea `version=20260421.0`; no contenía credenciales.
2. `git fetch` y checkout de `80da0c0c681d9597fd4b7737837d6a3e61907b33` (HEAD separado) en `/home/antho/acolite`.
3. `oceanos prepare` aplicó el [parche](../patches/acolite-catalog.patch) a la instalación.
4. El wrapper usa `/home/antho/acolite` por defecto (`ACOLITE` en `oceanos/config.py`; se puede cambiar con `--acolite`). Los tests también.

Al instalarla, la identidad del motor era la misma que registraron los ensayos: revisión `80da0c0`, `patch_sha256` `63ccc7fd…eec08` y `working_diff_sha256` `4052633a…a6ff`. Esa identidad cambió el 01-10-2026 (ver [huella vigente](#huella-vigente-01-10-2026)). La suite de 23 pruebas pasa.

`.work/acolite-audit` (41 MB, solo código y los cambios del parche) se eliminó el 01-10-2026 por orden del usuario, junto con su entrada gitlink del índice git del proyecto.

## Qué hace `oceanos prepare`

`prepare` (`oceanos/native.py`, función `prepare`) es idempotente y no descarga escenas:

1. Lee `git rev-parse HEAD` de la instalación. Si no es `REVISION` (`80da0c0`), se detiene: no corre ACOLITE de otra versión en silencio.
2. Con `git apply --reverse --check` comprueba si el parche ya está aplicado. Si lo está, no hace nada más.
3. Si no lo está y la instalación tiene otros cambios (`git diff --name-only`), se detiene sin tocar nada para conservarlos.
4. Si está limpia, valida el parche (`git apply --check`) y lo aplica.
5. Devuelve la identidad del motor (`identity`): revisión, SHA-256 del parche y SHA-256 del diff efectivo.

Esa identidad se calcula también en cada `search`/`run`/`derive` (`Pipeline.__init__`). Si falta el parche o la revisión es otra, la ejecución falla antes de consultar. La identidad entra en `correction_key`, de modo que un cambio en ACOLITE nunca reutiliza L1R/L2W calculados con otra versión.

El parche modifica solo la capa de consulta: `cdse/query.py` (retorno opcional de metadata con `Id`, `ContentLength` y `Checksum`, timeouts y errores HTTP) y `earthexplorer/query.py` (error USGS explícito). No toca código científico.

## Operación

```bash
oceanos prepare                       # una vez, o tras actualizar/restaurar ACOLITE
git -C /home/antho/acolite status     # debe mostrar solo los tres archivos del parche
# Volver al estado del repositorio (OCEANOS dejará de funcionar hasta otro prepare):
git -C /home/antho/acolite apply --reverse /home/antho/projects/oceanos/patches/acolite-catalog.patch
```

Para actualizar ACOLITE, seguir la sección siguiente; no hacer `git pull` directamente sobre la instalación.

## Si ACOLITE cambia de revisión

ACOLITE no se actualiza solo: es un clon git y cambia únicamente con un `git pull`/`checkout` manual. Si ocurre:

- **El wrapper se detiene.** `search`, `run`, `derive` y `prepare` comparan la revisión con `REVISION` y fallan con "Revisión ACOLITE inesperada" antes de consultar o procesar.
- **No se mezclan resultados.** La identidad del motor entra en `correction_key`; L1R/L2W de otra versión no se reutilizan y el catálogo registra ejecuciones distintas.
- **El parche puede no aplicar.** Si upstream modifica `cdse/query.py` o `earthexplorer/query.py`, `prepare` lo detecta con `git apply --check` y se detiene.
- **Riesgo científico.** Upstream puede cambiar defaults, LUT, máscaras o nombres de variables L2W. El código puede ejecutarse sin error y producir valores distintos.

### Procedimiento de actualización controlada

1. Clonar la revisión nueva en otra carpeta (por ejemplo `~/acolite-nueva`), sin tocar `~/acolite`.
2. Comprobar el parche: `git -C ~/acolite-nueva apply --check patches/acolite-catalog.patch`. Si falla, adaptarlo a las tres funciones de consulta.
3. Revisar el diff de `config/defaults.txt` y de los defaults del sensor entre ambas revisiones, contra los settings que genera `native_settings()` en `oceanos/config.py` desde `project.yaml` y `landsat.yaml`.
4. Ejecutar la suite y una consulta con `--acolite ~/acolite-nueva`, tras ajustar temporalmente `REVISION`.
5. Procesar una escena de referencia con ambas versiones y comparar las variables bidimensionales del L2W, flags y patrón de NaN, como en el [documento 33](33_retention_and_reset.md).
6. Si las diferencias son aceptables y quedan documentadas: actualizar `REVISION` en `oceanos/config.py` (única fuente de la revisión), revertir el parche en `~/acolite`, cambiar de revisión, ejecutar `oceanos prepare` y registrar la decisión en este documento.

Hoy no hay L1R/L2W conservados (reinicio del documento 33), así que el paso 5 no tiene referencia. Conservar al menos una escena procesada con la revisión vigente antes de cualquier actualización.

## Efectos a tener en cuenta

- El supervisor de disco suma `/home/antho/acolite/data` y `scratch` al presupuesto de 50 GB. Hoy `data` ocupa unos 1,8 GB (LUT ya presentes), que antes no se contaban porque las cachés de la copia se borraron en el reinicio.
- Otros proyectos que usen `/home/antho/acolite` verán la revisión `80da0c0` con el parche. El retorno por defecto de las funciones parcheadas sigue siendo compatible.

## Huella vigente (01-10-2026)

Al retirar Zarr del wrapper ([documento 06](06_acolite_zarr_input.md#retirada-del-wrapper-01-10-2026)) se quitó del parche el bloque de `stac/query_get.py` y se restauró ese archivo a upstream en `/home/antho/acolite`. `oceanos prepare` devuelve la nueva identidad:

| Campo | Anterior (fases 6–11) | Vigente |
|---|---|---|
| `revision` | `80da0c0c681d9597fd4b7737837d6a3e61907b33` | sin cambio |
| `patch_sha256` | `63ccc7fd7116c202288ac06ddcbeb6103b38735d4ffd3d48a2b28b3058eeec08` | `5cc22d82b65ba599443e1d3379e3e6ebae0f107029dc9594459a966009a8f5aa` |
| `working_diff_sha256` | `4052633a…a6ff` | `06eb7f526899a483653c74a185f5b34e1bea79e9a9b08208ce5a01c5bdbbbf57` |

El cambio no toca código científico, pero la identidad entra en `correction_key`: las ejecuciones nuevas no reutilizan L1R/L2W registrados con la huella anterior y se recalculan. El historial del catálogo conserva la huella antigua en sus ejecuciones.

