# OCEANOS — superimagen costera con ACOLITE

Wrapper local para Sentinel-2, Landsat 8/9 y Sentinel-3 OLCI sobre las 4 zonas del AOI Water2Coast (Puerto Rico y Culebra). ACOLITE hace la ciencia (corrección atmosférica, glint y productos). OCEANOS se encarga de lo demás:
- búsqueda y descarga, con un catálogo SQLite;
- procesamiento por zona en la resolución nativa del sensor;
- la **superimagen**: COG por escena con calidad y linaje, sargazo diario y compuestos mensuales, estacionales y anuales;
- borrado de todo lo intermedio.

## Uso en Ubuntu WSL

```bash
cd /home/antho/projects/oceanos
alias oceanos='/home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m oceanos'

oceanos prepare                                        # una vez: verificar ACOLITE y aplicar el parche
oceanos run --plan --start 2026-01-01 --end 2026-02-01 # qué se descargaría y cuánto disco ocuparía
oceanos run --start 2026-01-01 --end 2026-02-01        # todo: buscar, descargar, ACOLITE, escenas, sargazo, compuestos
oceanos superimagen                                    # productos por zona y sensor, y disco frente a 120 GB
oceanos reporte                                        # resultado por escena y zona, con motivo (--csv archivo.csv)
```

**Comandos frecuentes**
- `run` es único, reanudable e idempotente. Repetirlo no vuelve a descargar ni recalcular lo ya hecho; solo procesa lo que falta.
- `oceanos sargazo` y `oceanos componer` recalculan sin descargar. `oceanos mascara` crea las máscaras de tierra; `run` también las crea si faltan.

**Selección**
- `--sensor`, `--satelite`, `--zona`, `--start` y `--end` (fin excluido) cambian la selección sin editar el YAML.
- Por defecto se procesan todos los sensores del perfil, en orden S2 → Landsat → OLCI.
- Una sola escena: `oceanos run --escena 20251216`.
- Archivo local: `oceanos run --source escena.zip --scene NOMBRE.SAFE`.

**Legado**
- `lapargera_v1` se conserva aparte: `oceanos status --legado` y `oceanos reporte --legado`.

**Paralelo**
- `run` reparte las escenas según la CPU y RAM libres; con `--trabajadores 1` va de a una. Detalle en [operación](docs/04_operacion.md#paralelo).

**Catálogo**
- Está en `storage/catalog/catalog.sqlite`. Las consultas útiles están en [`sql/consultas.sql`](sql/consultas.sql).
- Ayuda: `oceanos -h` y `oceanos <comando> -h`.

**Autorizaciones y credenciales**
- Las descargas de escenas, auxiliares, LUT y WorldCover necesitan autorización del usuario. `run --plan` muestra la lista y el tamaño antes de bajar.
- Las credenciales van en `~/.netrc` (CDSE, USGS/EarthExplorer, NASA Earthdata para MERRA-2).

## Pruebas

```bash
env PYTHONPATH=.:tests /home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m unittest discover -s tests
```

- Las pruebas no usan la red: `tests/sin_red.py` bloquea toda conexión que no sea local.
- Requieren `/home/antho/acolite` en la revisión `80da0c0` con el [parche de catálogo](patches/acolite-catalog.patch) (`oceanos prepare`).

## Documentación

[docs/README.md](docs/README.md). La superimagen y sus decisiones están en [docs/07_superimagen.md](docs/07_superimagen.md).
