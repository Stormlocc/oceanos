"""Reparto dinámico de CPU y RAM entre escenas en paralelo (70 % del equipo por defecto).

Cada escena recorre su cadena completa (descarga → extracción → ACOLITE → L1R/L2W) en su
propio hilo; cada etapa pesada corre en un proceso aislado (oceanos.worker). Antes de lanzar
ese proceso se reserva su pico de RAM esperado: solo arranca si cabe en la fracción de RAM
asignada junto con lo ya reservado. Los hilos BLAS/OpenMP de cada proceso se limitan para que
la suma no supere la fracción de CPU.
"""
import contextlib
import os
import threading

SHARE = 0.7
GB = 1e9
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


def hardware():
    """CPU utilizables por este proceso y RAM total en bytes (en WSL, la de la VM)."""
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1
    try:
        with open('/proc/meminfo') as stream:
            memory = next(int(line.split()[1])*1024 for line in stream if line.startswith('MemTotal:'))
    except (OSError, StopIteration, ValueError):
        memory = os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
    return cpus, memory


def peaks(catalog, family):
    """Pico de RAM esperado por etapa: el mayor medido en el catálogo (+10 %) o el valor por defecto."""
    result = {}
    for stage, default in PEAKS[family].items():
        measured = catalog.stage_peak(stage, family)
        result[stage] = measured*1.1 if measured else default
    return result


def plan(catalog, config, free_disk, workers=None, share=SHARE, cpus=None, memory=None):
    """Recursos de un lote según el equipo, el historial del catálogo y el disco libre del presupuesto.

    Sin `workers` se calcula: tantas descargas como quepan en la RAM asignada más una escena
    lista para ACOLITE, sin superar la fracción de CPU ni el disco libre (3,5 GB por escena).
    """
    detected = hardware()
    resources = Resources(peaks(catalog, config['family']), cpus or detected[0], memory or detected[1], share)
    if workers is None:
        by_memory = int(resources.memory_budget//resources.peaks['acquire'])+1
        workers = min(resources.cpu_budget, by_memory, int(free_disk//SCENE_DISK))
    resources.workers = max(1, workers)
    return resources


class Resources:
    """Reservas de RAM por etapa compartidas por los hilos de un lote."""
    def __init__(self, peaks, cpus, memory, share=SHARE, workers=1):
        self.peaks, self.cpus, self.memory, self.share = peaks, cpus, memory, share
        self.cpu_budget = max(1, int(cpus*share))
        self.memory_budget = memory*share
        self.workers = workers
        self.used, self.active, self.alone = 0.0, 0, False
        # Hasta que un ACOLITE termine bien, nada corre a la vez que él: la primera ejecución
        # prepara LUT en acolite/data, un directorio compartido sin auditoría de concurrencia.
        self.warm = False
        self.waiting = {}
        self.condition = threading.Condition()
        self.stop = threading.Event()

    def threads(self):
        """Hilos BLAS/OpenMP por proceso aislado: la fracción de CPU repartida entre las escenas."""
        return max(1, self.cpu_budget//self.workers)

    def environment(self):
        """Entorno del proceso aislado con los hilos numéricos limitados."""
        return {**os.environ, **{name: str(self.threads()) for name in THREADS}}

    def admit(self, stage):
        """Reserva la RAM de la etapa si cabe ahora (con `condition` tomada) y devuelve si entró.

        Una etapa sola siempre entra aunque su pico supere la fracción asignada; si no, un
        equipo pequeño nunca podría procesar una escena.
        """
        need = self.peaks.get(stage, 0)
        exclusive = stage == 'process' and not self.warm
        rank = PRIORITY.get(stage, len(PRIORITY))
        ahead = any(count for other, count in self.waiting.items() if PRIORITY.get(other, len(PRIORITY)) < rank)
        if self.alone or ahead or (self.active and (exclusive or self.used+need > self.memory_budget)):
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
        return (f'Paralelo: {self.workers} escena(s) a la vez · equipo {self.cpus} CPU y {size(self.memory)} RAM, '
                f'se usa el {self.share*100:.0f} %: {self.cpu_budget} CPU y {size(self.memory_budget)} · '
                f'{self.threads()} hilos por proceso · pico RAM '
                + ', '.join(f'{name} {size(self.peaks[stage])}' for stage, name in NAMES.items()))
