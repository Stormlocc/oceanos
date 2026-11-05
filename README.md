# OCEANOS — superimagen costera con ACOLITE

Wrapper local para Sentinel-2, Landsat 8/9 y Sentinel-3 OLCI sobre las 4 zonas del AOI Water2Coast (Puerto Rico y Culebra). ACOLITE hace la ciencia (corrección atmosférica, glint y productos). OCEANOS se encarga de lo demás:
- búsqueda y descarga, con un catálogo SQLite;
- procesamiento por zona en la resolución nativa del sensor;
- la **superimagen**: COG por escena con calidad y linaje, sargazo diario y compuestos mensuales, estacionales y anuales;
- borrado de todo lo intermedio.

## Instalación en otra computadora con Windows

OCEANOS y ACOLITE corren en Linux: en Windows se usan dentro de **WSL2 con Ubuntu**. El entorno fijado (`environment.yml`) es para linux-64.

### Requisitos

| Recurso | Mínimo | Recomendado | Por qué |
|---|---|---|---|
| Windows | 10 22H2 u 11, 64 bits, virtualización activada en la BIOS | Windows 11 | WSL2 |
| RAM | 8 GB | 16 GB o más | Pico de ACOLITE medido en enero de 2026: hasta 7,9 GB (S2), 1,1 GB (Landsat) y 2,6 GB (OLCI) por escena |
| Disco libre | 200 GB | 250 GB | 120 GB de superimagen, 50 GB de temporales, ~10 GB de entornos y ~4 GB de LUT y auxiliares |
| Cuentas | CDSE, USGS ERS con acceso M2M, NASA Earthdata | — | Descargas de S2/OLCI, Landsat y MERRA-2 |

### 1. Instalar WSL2 con Ubuntu (PowerShell de Windows como administrador)

```powershell
wsl --install -d Ubuntu-24.04
```

Reinicia cuando lo pida. Al abrir **Ubuntu** desde el menú Inicio, crea tu usuario y contraseña de Linux.

**Opcional: más RAM para WSL.** Por defecto WSL usa la mitad de la RAM de Windows (un equipo de 32 GB queda con ~16 GB en Linux), y OCEANOS reparte las escenas según la RAM que ve WSL. Para cambiarlo:
1. Crea `C:\Users\<tu_usuario>\.wslconfig` con este contenido (ajusta los valores a tu equipo):

   ```ini
   [wsl2]
   memory=12GB
   processors=8
   ```

2. Aplica el cambio en PowerShell con `wsl --shutdown`. Esto apaga WSL entero: no lo hagas con un `run` en curso.

### 2. Paquetes, micromamba y repositorios (terminal de Ubuntu)

Todo va dentro del disco de Linux (`~`), **no en `/mnt/c`**: allí GDAL y SQLite son mucho más lentos.

```bash
sudo apt-get update && sudo apt-get install -y git curl bzip2 ca-certificates sqlitebrowser

# micromamba
mkdir -p ~/.local/bin
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C ~/.local bin/micromamba

# OCEANOS y ACOLITE en la revisión auditada (OCEANOS busca ACOLITE en ~/acolite)
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/Stormlocc/oceanos.git
git clone https://github.com/acolite/acolite.git ~/acolite
git -C ~/acolite checkout 80da0c0c681d9597fd4b7737837d6a3e61907b33

# Entorno con las versiones fijadas (tarda varios minutos)
~/.local/bin/micromamba create -y -p ~/micromamba/envs/acolite -f ~/projects/oceanos/environment.yml
```

### 3. Credenciales en `~/.netrc`

Crea el archivo con `nano ~/.netrc` y protégelo con `chmod 600 ~/.netrc`. Contenido, con tus datos:

```text
machine cdse                 login TU_CORREO_CDSE     password TU_CLAVE_CDSE
machine earthexplorer_token  login TU_USUARIO_ERS     password TU_TOKEN_M2M
machine earthexplorer        login TU_USUARIO_ERS     password TU_CLAVE_ERS
machine earthdata            login TU_USUARIO_NASA    password TU_CLAVE_NASA
```

| Máquina | Cuenta | Para qué |
|---|---|---|
| `cdse` | [Copernicus Data Space](https://dataspace.copernicus.eu) | Sentinel-2 y Sentinel-3 OLCI |
| `earthexplorer_token` | [USGS ERS](https://ers.cr.usgs.gov) | Landsat por M2M. El token de 64 caracteres se genera en el perfil ERS; la cuenta necesita el acceso de descarga M2M (*Access Request*) |
| `earthexplorer` | USGS ERS (usuario y contraseña) | Respaldo de descarga Landsat por EarthExplorer |
| `earthdata` | [NASA Earthdata](https://urs.earthdata.nasa.gov) | Auxiliares MERRA-2 que pide ACOLITE a OB.DAAC (`oceandata.sci.gsfc.nasa.gov`). Usuario y contraseña de la cuenta Earthdata, no un token. Si son incorrectos, NASA responde 401 y la escena falla con `AUXILIAR_POR_DEFECTO` |

Las credenciales nunca van al repositorio ni al catálogo.

### 4. Atajo, preparación y prueba

```bash
echo "alias oceanos='~/.local/bin/micromamba run -p ~/micromamba/envs/acolite python -m oceanos'" >> ~/.bashrc
source ~/.bashrc
cd ~/projects/oceanos

oceanos prepare        # comprueba la revisión de ACOLITE y aplica el parche de catálogo
env PYTHONPATH=.:tests ~/.local/bin/micromamba run -p ~/micromamba/envs/acolite python -m unittest discover -s tests
```

Las pruebas deben terminar en `OK` y no usan la red.

### 5. Primera ejecución

Ejecuta los comandos siempre desde `~/projects/oceanos`: `python -m oceanos` carga el paquete desde esa carpeta. El perfil y `storage/` quedan dentro del repositorio.

```bash
cd ~/projects/oceanos
oceanos run --plan --start 2026-01-01 --end 2026-02-01   # lista, tamaño de descarga y disco estimado; no descarga
oceanos run --start 2026-01-01 --end 2026-02-01          # descarga y procesa todo
```

La primera ejecución descarga además:
- las LUT de ACOLITE, desde el repositorio `acolite/acolite_luts` de GitHub: ~0,5 GB por satélite y ~3,6 GB con los siete (S2A/B/C, L8/9, S3A/B), en `~/acolite/data/LUT`. El primer ACOLITE de cada equipo corre solo mientras las baja;
- los tiles de ESA WorldCover para las máscaras de tierra.

Un `run` se puede cortar con Ctrl+C y repetir: continúa donde quedó.

**Ver los resultados desde Windows.** En el Explorador de archivos, abre `\\wsl$\Ubuntu-24.04\home\<usuario_linux>\projects\oceanos\storage\superimagen`. Los COG se abren directo en QGIS o ArcGIS Pro, y el catálogo con DB Browser for SQLite (`sqlitebrowser storage/catalog/catalog.sqlite`).

**Traer datos de otra computadora (opcional).**
- Copia `storage/` completo (catálogo y superimagen) con la misma estructura. `run` reconoce lo ya procesado y no lo vuelve a descargar.
- L1R/L2W sueltos del legado se registran con `oceanos sync`.

## Uso en Ubuntu WSL

```bash
cd ~/projects/oceanos     # en este equipo: /home/antho/projects/oceanos
alias oceanos='~/.local/bin/micromamba run -p ~/micromamba/envs/acolite python -m oceanos'

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
env PYTHONPATH=.:tests ~/.local/bin/micromamba run -p ~/micromamba/envs/acolite python -m unittest discover -s tests
```

- Las pruebas no usan la red: `tests/sin_red.py` bloquea toda conexión que no sea local.
- Requieren `~/acolite` en la revisión `80da0c0` con el [parche de catálogo](patches/acolite-catalog.patch) (`oceanos prepare`).

## Documentación

[docs/README.md](docs/README.md). La superimagen y sus decisiones están en [docs/07_superimagen.md](docs/07_superimagen.md).
