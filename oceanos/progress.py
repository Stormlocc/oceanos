"""Barra de progreso en terminal para `run`, sin dependencias externas."""
import shutil
import sys
import threading
import time


def size(value):
    """Bytes en unidades decimales legibles (como el presupuesto del perfil)."""
    if value is None:
        return '—'
    for unit in ('B', 'KB', 'MB', 'GB'):
        if abs(value) < 1000 or unit == 'GB':
            return f'{value:.0f} {unit}' if unit in ('B', 'KB') else f'{value:.1f} {unit}'
        value /= 1000


def duration(seconds):
    """Segundos como 1h02m03s, 4m05s o 12s."""
    if seconds is None:
        return '—'
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours}h{minutes:02d}m{seconds:02d}s' if hours else (f'{minutes}m{seconds:02d}s' if minutes else f'{seconds}s')


def bar(fraction, width=24):
    """Barra de bloques para una fracción entre 0 y 1."""
    filled = int(round(max(0.0, min(1.0, fraction))*width))
    return '█'*filled + '░'*(width-filled)


class Progress:
    """Muestra una línea que se reescribe por etapa; sin terminal, una línea cada `every` segundos.

    Con varias escenas en paralelo cada hilo ocupa un espacio: en terminal la línea las junta en
    forma compacta y sin terminal se imprime una línea por escena. Los mensajes llevan [i/n].
    """
    def __init__(self, stream=None, interactive=None, every=30):
        self.stream = stream or sys.stdout
        self.interactive = self.stream.isatty() if interactive is None else interactive
        self.every, self.last, self.active = every, 0.0, False
        self.batch_started = time.monotonic()
        self.lock = threading.RLock()
        # Hilo -> {'tag': '[i/n]', 'prefix': '[i/n] etiqueta', 'text': estado de la etapa}.
        self.slots = {}

    @property
    def compact(self):
        """Hay más de una escena en curso."""
        return len(self.slots) > 1

    def scene(self, index, total, label):
        """Anuncia la escena en curso: [i/n] etiqueta, con tiempo transcurrido del lote."""
        with self.lock:
            self.clear()
            self.slots[threading.get_ident()] = {'tag': f'[{index}/{total}]', 'prefix': f'[{index}/{total}] {label}',
                                                 'text': ''}
            elapsed = duration(time.monotonic()-self.batch_started)
            self.stream.write(f'── Escena {index} de {total}: {label}  (lote: {elapsed})\n')
            self.stream.flush()

    def release(self):
        """Retira la escena del hilo actual al terminarla."""
        with self.lock:
            self.slots.pop(threading.get_ident(), None)
            self.clear()

    def message(self, text):
        """Imprime un mensaje sin pisar la línea de estado; en paralelo, con la etiqueta [i/n]."""
        with self.lock:
            self.clear()
            slot = self.slots.get(threading.get_ident())
            self.stream.write((f"{slot['tag']} " if slot and self.compact else '')+text+'\n')
            self.stream.flush()

    def update(self, text):
        """Reescribe la línea de estado de la etapa actual."""
        with self.lock:
            slot = self.slots.setdefault(threading.get_ident(), {'tag': '', 'prefix': '', 'text': ''})
            slot['text'] = text
            if self.interactive:
                line = ' │ '.join(f"{s['tag']} {s['text']}" for s in self.slots.values() if s['text']) \
                    if self.compact else f"{slot['prefix']}  {text}"
                width = shutil.get_terminal_size((100, 20)).columns - 1
                self.stream.write('\r'+line[:width].ljust(width))
                self.active = True
            elif time.monotonic()-self.last >= self.every:
                self.stream.write(''.join(f"{s['prefix']}  {s['text']}\n" for s in self.slots.values() if s['text']))
                self.last = time.monotonic()
            self.stream.flush()

    def clear(self):
        """Cierra la línea reescribible para que otro mensaje no la pise."""
        with self.lock:
            if self.active:
                self.stream.write('\n')
                self.stream.flush()
                self.active = False

    def download(self, done, total, rate, elapsed):
        """Estado de la descarga: porcentaje, bytes, velocidad y tiempo restante estimado."""
        if total:
            fraction = min(done/total, 1.0)
            remaining = (total-done)/rate if rate and done < total else None
            if self.compact:
                self.update(f'descarga {fraction*100:.0f}% {size(rate)}/s quedan {duration(remaining)}')
                return
            self.update(f'descarga {bar(fraction)} {fraction*100:5.1f}%  {size(min(done, total))}/{size(total)}'
                        f'  {size(rate)}/s  quedan {duration(remaining)}')
        else:
            self.update(f'descarga {size(done)}  {size(rate)}/s  {duration(elapsed)}')

    def stage(self, name, elapsed, expected=None):
        """Estado de una etapa sin bytes medibles: tiempo transcurrido frente al habitual."""
        if expected:
            fraction = min(elapsed/expected, 0.99)
            if self.compact:
                self.update(f'{name} ~{fraction*100:.0f}%')
                return
            self.update(f'{name} {bar(fraction)} ~{fraction*100:3.0f}%  {duration(elapsed)} (habitual {duration(expected)})')
        else:
            self.update(f'{name}  {duration(elapsed)}')
