#!/usr/bin/env bash
# Instalación completa de OCEANOS en Ubuntu (x86_64), en una sola ejecución:
#   bash instalar_ubuntu.sh
# Equipo previsto: gri@gric-OptiPlex-AIO-7410-65W, base /home/gri/Documents/LopezA.
# Se puede repetir: cada paso salta lo que ya está hecho.
#
# Deja en BASE:
#   oceanos/                 repositorio OCEANOS (storage/ dentro)
#   acolite/                 ACOLITE en la revisión auditada 80da0c0 + parche de catálogo
#   micromamba/envs/acolite  entorno del pipeline (environment.yml del repo, versiones fijadas)
#   micromamba/envs/analisis entorno de trabajo: imágenes, NetCDF, EDA, series temporales, Jupyter
#   analisis/                carpeta de notebooks y environment.yml del entorno analisis
# y ~/acolite -> BASE/acolite (ruta por defecto de OCEANOS y de las pruebas).
set -euo pipefail

BASE=${BASE:-/home/gri/Documents/LopezA}
USUARIO_ESPERADO=gri
EQUIPO_ESPERADO=gric-OptiPlex-AIO-7410-65W
OCEANOS_GIT=https://github.com/Stormlocc/oceanos.git
ACOLITE_GIT=https://github.com/acolite/acolite.git
ACOLITE_REV=80da0c0c681d9597fd4b7737837d6a3e61907b33

MAMBA_ROOT_PREFIX=$BASE/micromamba
MM=$HOME/.local/bin/micromamba
ENV_ACOLITE=$MAMBA_ROOT_PREFIX/envs/acolite
ENV_ANALISIS=$MAMBA_ROOT_PREFIX/envs/analisis
export MAMBA_ROOT_PREFIX

paso() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
aviso() { printf '\033[1;33mAVISO: %s\033[0m\n' "$*"; }

paso "Comprobaciones"
[[ $(uname -m) == x86_64 ]] || { echo "Se requiere Linux x86_64 (environment.yml es linux-64)"; exit 1; }
[[ $(id -un) == "$USUARIO_ESPERADO" ]] || aviso "usuario $(id -un), se esperaba $USUARIO_ESPERADO"
[[ $(hostname) == "$EQUIPO_ESPERADO" ]] || aviso "equipo $(hostname), se esperaba $EQUIPO_ESPERADO"
mkdir -p "$BASE/analisis"
libre=$(df -BG --output=avail "$BASE" | tail -1 | tr -dc 0-9)
(( libre >= 80 )) || aviso "solo ${libre} GB libres en $BASE (presupuesto del perfil: 50 GB + entornos ≈ 10 GB)"
echo "CPU: $(nproc)  RAM: $(free -g | awk '/Mem:/{print $2}') GB  Disco libre: ${libre} GB"

paso "Paquetes del sistema (pide sudo)"
sudo apt-get update
sudo apt-get install -y git curl bzip2 ca-certificates sqlitebrowser

paso "micromamba"
if [[ ! -x $MM ]]; then
    mkdir -p "$HOME/.local/bin"
    curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C "$HOME/.local" bin/micromamba
fi
"$MM" --version

paso "Repositorios"
[[ -d $BASE/oceanos/.git ]] || git clone "$OCEANOS_GIT" "$BASE/oceanos"
git -C "$BASE/oceanos" pull --ff-only
[[ -d $BASE/acolite/.git ]] || git clone "$ACOLITE_GIT" "$BASE/acolite"
if [[ $(git -C "$BASE/acolite" rev-parse HEAD) != "$ACOLITE_REV" ]]; then
    git -C "$BASE/acolite" diff --quiet || { echo "ACOLITE tiene cambios locales; no se cambia de revisión"; exit 1; }
    git -C "$BASE/acolite" checkout -q "$ACOLITE_REV"
fi
if [[ -L $HOME/acolite || ! -e $HOME/acolite ]]; then
    ln -sfn "$BASE/acolite" "$HOME/acolite"
elif [[ $(realpath "$HOME/acolite") != $(realpath "$BASE/acolite") ]]; then
    aviso "~/acolite ya existe y no es un enlace: las pruebas usarán esa copia"
fi

paso "Entorno acolite (versiones fijadas del repo)"
[[ -x $ENV_ACOLITE/bin/python ]] || "$MM" create -y -p "$ENV_ACOLITE" -f "$BASE/oceanos/environment.yml"

paso "Entorno analisis (imágenes, EDA, series temporales)"
cat > "$BASE/analisis/environment.yml" <<'EOF'
name: analisis
channels:
  - conda-forge
dependencies:
  - python=3.12
  # Notebooks
  - jupyterlab
  - ipykernel
  - ipywidgets
  # Datos y tablas
  - numpy
  - pandas
  - pyarrow
  - duckdb
  - pyyaml
  - tqdm
  # NetCDF / ráster (L1R, L2W, GeoTIFF)
  - xarray
  - netcdf4
  - h5netcdf
  - dask
  - distributed
  - bottleneck
  - rioxarray
  - rasterio
  - gdal
  - pyproj
  - pyresample
  # Vectores y mapas (AOI KMZ, puntos de muestreo)
  - geopandas
  - shapely
  - fiona
  - cartopy
  - folium
  # Gráficos
  - matplotlib
  - seaborn
  - plotly
  - hvplot
  - holoviews
  - cmocean
  # Estadística, series temporales y ML
  - scipy
  - statsmodels
  - scikit-learn
  - pymannkendall
  - ruptures
  - xskillscore
EOF
if [[ -x $ENV_ANALISIS/bin/python ]]; then
    "$MM" install -y -p "$ENV_ANALISIS" -f "$BASE/analisis/environment.yml"
else
    "$MM" create -y -p "$ENV_ANALISIS" -f "$BASE/analisis/environment.yml"
fi
"$MM" run -p "$ENV_ANALISIS" python -m ipykernel install --user --name analisis --display-name "Python (analisis)"

paso "Credenciales (~/.netrc)"
touch "$HOME/.netrc"; chmod 600 "$HOME/.netrc"
pedir() {  # máquina, descripción
    grep -qE "^\s*machine\s+$1(\s|$)" "$HOME/.netrc" && { echo "$1: ya configurada"; return; }
    [[ -t 0 ]] || { aviso "$1 falta en ~/.netrc ($2)"; return; }
    read -rp "$1 — $2. Usuario (Enter para omitir): " usuario
    [[ -n $usuario ]] || { aviso "$1 omitida: añádela luego a ~/.netrc"; return; }
    read -rsp "$1 — contraseña o token: " clave; echo
    printf 'machine %s login %s password %s\n' "$1" "$usuario" "$clave" >> "$HOME/.netrc"
}
pedir cdse "Copernicus Data Space (Sentinel-2)"
pedir earthexplorer_token "USGS EarthExplorer, token M2M de 64 caracteres (Landsat)"
pedir earthdata "NASA Earthdata (auxiliares MERRA-2)"

paso "Atajos en ~/.bashrc"
inicio='# >>> oceanos >>>'
fin='# <<< oceanos <<<'
sed -i "/^$inicio\$/,/^$fin\$/d" "$HOME/.bashrc"
cat >> "$HOME/.bashrc" <<EOF
$inicio
export MAMBA_ROOT_PREFIX=$MAMBA_ROOT_PREFIX
export PATH=\$HOME/.local/bin:\$PATH
alias oceanos='$MM run -p $ENV_ACOLITE python -m oceanos'
alias oceanos-pruebas='(cd $BASE/oceanos && $MM run -p $ENV_ACOLITE python -m unittest discover -s tests -v)'
alias lab='$MM run -p $ENV_ANALISIS jupyter lab --notebook-dir=$BASE'
alias analisis='$MM run -p $ENV_ANALISIS python'
alias catalogo='sqlitebrowser $BASE/oceanos/storage/catalog/catalog.sqlite'
$fin
EOF

paso "Parche de ACOLITE y pruebas"
cd "$BASE/oceanos"
"$MM" run -p "$ENV_ACOLITE" python -m oceanos prepare
"$MM" run -p "$ENV_ACOLITE" python -m unittest discover -s tests
"$MM" run -p "$ENV_ANALISIS" python -c "import xarray, rioxarray, geopandas, statsmodels, pymannkendall; print('entorno analisis OK')"

paso "Listo"
cat <<EOF
Abre una terminal nueva (o: source ~/.bashrc) y usa:
  oceanos search                 # ver escenas (no descarga)
  oceanos search --registrar     # dejarlas en la cola
  oceanos run                    # descargar y procesar
  oceanos status --ultimas 5
  oceanos-pruebas                # pruebas del wrapper
  lab                            # JupyterLab con el kernel "Python (analisis)"
  catalogo                       # abrir el SQLite en DB Browser
Datos: $BASE/oceanos/storage (catálogo y runs con L1R/L2W).
EOF
