"""Reparto dinámico de CPU y RAM entre escenas en paralelo según el equipo donde se ejecuta.

Cada escena recorre su cadena completa (descarga → extracción → ACOLITE → L1R/L2W) en su
propio hilo; cada etapa pesada corre en un proceso aislado (oceanos.worker). El presupuesto sale
de lo que el equipo tiene al iniciar: núcleos utilizables (afinidad y cuota de cgroup) y RAM
disponible (MemAvailable y límite memory.max de cgroup; en WSL, la de la VM), menos una reserva
para el sistema. Antes de lanzar cada proceso se reserva su pico de RAM esperado: solo arranca si
cabe en el presupuesto junto con lo ya reservado y, además, en la RAM libre de ese momento. Los
hilos BLAS/OpenMP de cada proceso se limitan para que la suma no supere los núcleos asignados.
"""
import contextlib
import os
import threading
from pathlib import Path

GB = 1e9
# Reserva de RAM para el sistema y otras aplicaciones: 10 % del equipo, mínimo 1,5 GB.
RESERVE_FRACTION, RESERVE_MINIMUM = 0.1, 1.5*GB
# Variables de entorno para fijar a mano los núcleos y la RAM (GB) del lote.
CPUS_VARIABLE, RAM_VARIABLE = 'OCEANOS_CPUS', 'OCEANOS_RAM_GB'
CGROUP = Path('/sys/fs/cgroup')
# Picos RSS por etapa sin historial: catálogo v3, 14 escenas Sentinel-2 (descarga ≈2,5 GB porque
# ACOLITE acumula el ZIP en memoria; ACOLITE ≈4,7 GB) y máximo de los ensayos Landsat (6,57 GB).
PEAKS = {'sentinel2': {'query': 1.0*GB, 'acquire': 2.6*GB, 'extract': 1.2*GB, 'process': 4.8*GB},
         'landsat': {'query': 1.0*GB, 'acquire': 2.6*GB, 'extract': 1.2*GB, 'process': 6.6*GB}}
# Disco por escena en curso: RAW, extraído, salidas y auxiliares (3,42 GB medidos).
SCENE_DISK = 3.5*GB
# Prioridad al admitir: lo más avanzado primero, para liberar RAM y disco antes de descargar más.
PRIORITY = {'process': 0, 'extract': 1, 'acquire': 2, 'query': 3}
THREADS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')
NAMES = {'acquire': 'descarga', 'extract': 'extracción', 'process': 'ACOLITE'}


def first_line(path):
    """Primera línea de un archivo del sistema, o None si no existe o no se puede leer."""
    try:
        return Path(path).read_text().splitlines()[0].strip()
    except (OSError, IndexError):
        return None


def cgroup_limits(root=CGROUP, membership='/proc/self/cgroup'):
    """Núcleos permitidos por cpu.max y RAM libre bajo el memory.max más estricto (cgroup v2).

    Recorre el cgroup del proceso hasta la raíz; devuelve None en lo que no tenga límite.
    """
    try:
        own = next(line[3:] for line in Path(membership).read_text().splitlines() if line.startswith('0::'))
    except (OSError, StopIteration):
        return None, None
    folder = root/own.strip().lstrip('/')
    cpus = free = None
    for level in (folder, *folder.parents):
        quota = (first_line(level/'cpu.max') or 'max').split()
        if quota[0] != 'max':
            allowed = max(1, int(quota[0])//int(quota[1] if len(quota) > 1 else 100000))
            cpus = allowed if cpus is None else min(cpus, allowed)
        limit = first_line(level/'memory.max')
        if limit and limit != 'max':
            left = max(0, int(limit)-int(first_line(level/'memory.current') or 0))
            free = left if free is None else min(free, left)
        if level == root:
            break
    return cpus, free


def meminfo(path='/proc/meminfo'):
    """RAM total y disponible en bytes según /proc/meminfo (en WSL, la de la VM)."""
    values = {}
    try:
        with open(path) as stream:
            for line in stream:
                key, value = line.split(':', 1)
                values[key] = int(value.split()[0])*1024
    except (OSError, ValueError):
        pass
    total = values.get('MemTotal') or os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
    return total, values.get('MemAvailable', total)


def available():
    """RAM libre ahora para procesos nuevos: la menor entre el sistema y el límite de cgroup."""
    free, limited = meminfo()[1], cgroup_limits()[1]
    return free if limited is None else min(free, limited)


def hardware():
    """Núcleos utilizables, RAM total y RAM disponible ahora, respetando afinidad y cgroup."""
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1
    quota, limited = cgroup_limits()
    total, free = meminfo()
    return min(cpus, quota or cpus), total, free if limited is None else min(free, limited)


def reserve(memory):
    """RAM que se deja al sistema: 10 % del equipo, mínimo 1,5 GB."""
    return max(RESERVE_MINIMUM, memory*RESERVE_FRACTION)


def spare_cpus(cpus):
    """Núcleos que se dejan al sistema y al proceso principal: ninguno con 1-2, ~10 % (≥ 1) con más."""
    return 0 if cpus <= 2 else max(1, round(cpus/10))


def overrides(environ=os.environ):
    """Núcleos y RAM (bytes) fijados con OCEANOS_CPUS / OCEANOS_RAM_GB; None si no se indicaron."""
    def number(name, kind):
        value = environ.get(name, '').strip()
        if not value:
            return None
        try:
            parsed = kind(value)
        except ValueError:
            parsed = 0
        if parsed <= 0:
            raise ValueError(f'{name}={value!r} inválido: use un número mayor que 0')
        return parsed
    ram = number(RAM_VARIABLE, float)
    return number(CPUS_VARIABLE, int), ram*GB if ram else None


def peaks(catalog, family):
    """Pico de RAM esperado por etapa: el mayor medido en el catálogo (+10 %) o el valor por defecto."""
    result = {}
    for stage, default in PEAKS[family].items():
        measured = catalog.stage_peak(stage, family)
        result[stage] = measured*1.1 if measured else default
    return result


def plan(catalog, config, free_disk, workers=None, cpus=None, memory=None, free=None, live=available):
    """Recursos de un lote según el equipo, el historial del catálogo y el disco libre del presupuesto.

    `cpus`, `memory` (total) y `free` (disponible) sustituyen a lo detectado; OCEANOS_CPUS y
    OCEANOS_RAM_GB fijan directamente núcleos y RAM del lote. Sin `workers` se calcula: tantas
    descargas como quepan en la RAM asignada más una escena lista para ACOLITE, sin superar los
    núcleos asignados ni el disco libre (3,5 GB por escena).
    """
    detected = hardware()
    cpus, memory = cpus or detected[0], memory or detected[1]
    free = detected[2] if free is None else free
    fixed_cpus, fixed_ram = overrides()
    resources = Resources(peaks(catalog, config['family']), cpus, memory, free, live=live,
                          cpu_budget=fixed_cpus, memory_budget=fixed_ram)
    if workers is None:
        by_memory = int(resources.memory_budget//resources.peaks['acquire'])+1
        workers = min(resources.cpu_budget, by_memory, int(free_disk//SCENE_DISK))
    resources.workers = max(1, workers)
    return resources


class Resources:
    """Reservas de RAM por etapa compartidas por los hilos de un lote.

    Por defecto usa los núcleos menos `spare_cpus` y la RAM disponible menos `reserve`;
    `cpu_budget`/`memory_budget` los fijan a mano. `live()` devuelve la RAM libre del momento
    (None la ignora) para no arrancar una etapa más si otras aplicaciones ocuparon la memoria.
    """
    def __init__(self, peaks, cpus, memory, free=None, workers=1, live=None, cpu_budget=None, memory_budget=None):
        self.peaks, self.cpus, self.memory = peaks, cpus, memory
        self.available = memory if free is None else free
        self.spare = reserve(memory)
        self.cpu_budget = cpu_budget or max(1, cpus-spare_cpus(cpus))
        self.memory_budget = memory_budget or max(0.0, self.available-self.spare)
        self.manual = bool(cpu_budget or memory_budget)
        self.live = live
        self.workers = workers
        self.used, self.active, self.alone = 0.0, 0, False
        # Hasta que un ACOLITE termine bien, nada corre a la vez que él: la primera ejecución
        # prepara LUT en acolite/data, un directorio compartido sin auditoría de concurrencia.
        self.warm = False
        self.waiting = {}
        self.condition = threading.Condition()
        self.stop = threading.Event()

    def threads(self):
        """Hilos BLAS/OpenMP por proceso aislado: los núcleos asignados repartidos entre las escenas."""
        return max(1, self.cpu_budget//self.workers)

    def environment(self):
        """Entorno del proceso aislado con los hilos numéricos limitados."""
        return {**os.environ, **{name: str(self.threads()) for name in THREADS}}

    def fits_now(self, need):
        """La etapa cabe en la RAM libre de este momento, dejando la reserva del sistema."""
        if self.live is None:
            return True
        free = self.live()
        return free is None or need <= free-self.spare

    def admit(self, stage):
        """Reserva la RAM de la etapa si cabe ahora (con `condition` tomada) y devuelve si entró.

        Una etapa sola siempre entra aunque su pico supere la RAM asignada; si no, un equipo
        pequeño nunca podría procesar una escena.
        """
        need = self.peaks.get(stage, 0)
        exclusive = stage == 'process' and not self.warm
        rank = PRIORITY.get(stage, len(PRIORITY))
        ahead = any(count for other, count in self.waiting.items() if PRIORITY.get(other, len(PRIORITY)) < rank)
        if self.alone or ahead:
            return False
        if self.active and (exclusive or self.used+need > self.memory_budget or not self.fits_now(need)):
            return False
        self.used += need
        self.active += 1
        self.alone = exclusive
        return True

    def free(self, stage):
        """Libera la reserva de la etapa (con `condition` tomada) y despierta a los que esperan."""
        self.used -= self.peaks.get(stage, 0)
        self.active -= 1
        self.alone = False
        self.condition.notify_all()

    @contextlib.contextmanager
    def reserve(self, stage, waiting=None):
        """Espera a que la etapa quepa, la mantiene reservada mientras dura y luego la libera.

        `waiting()` se llama cada segundo de espera (barra de progreso). Si se pidió detener el
        lote, la espera termina con KeyboardInterrupt.
        """
        with self.condition:
            self.waiting[stage] = self.waiting.get(stage, 0)+1
            try:
                while not self.admit(stage):
                    if self.stop.is_set():
                        raise KeyboardInterrupt
                    if waiting:
                        waiting()
                    self.condition.wait(1)
            finally:
                self.waiting[stage] -= 1
        try:
            yield
        finally:
            with self.condition:
                self.free(stage)

    def describe(self):
        """Resumen legible del reparto para imprimir al iniciar el lote."""
        size = lambda value: f'{value/GB:.1f} GB'
        origin = ('fijado con ' + '/'.join((CPUS_VARIABLE, RAM_VARIABLE)) if self.manual else
                  f'se dejan {self.cpus-self.cpu_budget} CPU y {size(self.spare)} al sistema')
        return (f'Paralelo: {self.workers} escena(s) a la vez · equipo {self.cpus} CPU, '
                f'{size(self.memory)} RAM ({size(self.available)} libre) · se usan {self.cpu_budget} CPU y '
                f'{size(self.memory_budget)} ({origin}) · {self.threads()} hilos por proceso · pico RAM '
                + ', '.join(f'{name} {size(self.peaks[stage])}' for stage, name in NAMES.items()))
