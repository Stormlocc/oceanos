# OCEANOS — pipeline costero con ACOLITE

Wrapper local para Sentinel-2 y Landsat 8/9 sobre La Parguera (Puerto Rico). ACOLITE hace la ciencia (consulta, descarga, corrección atmosférica y productos); OCEANOS administra el catálogo SQLite, la cola de descargas, los reintentos y la conservación. Persisten **L1R + L2W + SQLite**; regenerar productos desde L1R repite la corrección atmosférica. La validación científica sigue pendiente.

## Uso en Ubuntu WSL

```bash
cd /home/antho/projects/oceanos
alias oceanos='/home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m oceanos'

oceanos prepare                          # una vez: verificar ACOLITE y aplicar el parche
oceanos sync                             # opcional: registrar L1R/L2W copiados a storage/importados
oceanos search                           # ver escenas, fecha y tamaño (no descarga ni registra)
oceanos search --registrar               # dejar las nuevas en la cola
oceanos cola                             # revisar la cola
oceanos run                              # descargar y procesar la cola, con progreso y resumen
oceanos status --ultimas 5               # revisar resultados
```

- `--sensor landsat` usa el perfil Landsat; `--satelite S2B,S2C`, `--start AAAA-MM-DD` y `--end AAAA-MM-DD` (fin excluido) cambian la selección sin editar el YAML. Usa la misma selección en `search` y en `run`.
- Una sola escena: `oceanos run --escena 20260215` (nombre o fragmento único). Archivo local: `oceanos run --source escena.zip --scene NOMBRE.SAFE`. Regenerar desde L1R: `oceanos derive --l1r ARCHIVO_L1R.nc --scene NOMBRE.SAFE`.
- Ayuda con valores válidos y ejemplos: `oceanos -h` y `oceanos <comando> -h`.
- Catálogo legible en `storage/catalog/catalog.sqlite` (tablas `escenas`, `procesos`, `busquedas`, `eventos`; vistas `v_resumen`, `v_cola`, `v_descargas`, `v_fallidas`, `v_disco`). Consultas en [`sql/consultas.sql`](sql/consultas.sql); abrir con `python -m sqlite3 storage/catalog/catalog.sqlite` o DB Browser for SQLite.
- `oceanos sync storage/runs --hash` registra L1R/L2W existentes en `storage/runs` y renombra sus carpetas (`0001_S2C_2026-01-01`).

**No descargar escenas, LUT, auxiliares ni dependencias sin autorización explícita.** Los comandos anteriores son ejemplos, no una autorización. `run` y `derive` pueden descargar auxiliares aun con entrada local; el CLI no tiene modo sin red. Credenciales en `~/.netrc`.

## Pruebas

```bash
/home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m unittest discover -s tests -v
```

Requiere la instalación `/home/antho/acolite` en la revisión `80da0c0` con el [parche de catálogo](patches/acolite-catalog.patch) (`oceanos prepare`); `--acolite` permite otra ruta.

## Documentación

[docs/README.md](docs/README.md): proyecto y AOI, uso de ACOLITE, configuración, operación y catálogo, resultados de los ensayos, y pendientes.
