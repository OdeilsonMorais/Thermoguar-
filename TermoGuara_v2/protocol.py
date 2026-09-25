"""Protocolo serial TermoGuará 1; sem dependências de GUI ou hardware."""
from dataclasses import dataclass
import math

FIELDS = ('seq', 'arduino_ms', 'ntc1a_c', 'ntc1b_c', 'ntc2a_c', 'ntc2b_c',
          'pt1_c', 'pt2_c', 'sp1_c', 'sp2_c', 'pwm1', 'pwm2', 'run1', 'run2',
          'fault1', 'fault2', 'configured', 'remaining1_s', 'remaining2_s')
FAULTS = {1: 'NTC inválido', 2: 'PT1000 inválido', 4: 'sobretemperatura',
          8: 'NTC divergentes', 16: 'comunicação perdida', 32: 'aquisição atrasada'}

def fault_text(mask):
    return ' / '.join(text for bit, text in FAULTS.items() if mask & bit) or 'OK'

def integer(text, low, high):
    if not text.isascii() or not text.isdecimal():
        raise ValueError('inteiro inválido')
    value = int(text)
    if not low <= value <= high:
        raise ValueError('inteiro fora da faixa')
    return value

@dataclass(frozen=True)
class Frame:
    values: tuple

    def get(self, key):
        return self.values[FIELDS.index(key)]

    @property
    def temperatures(self):
        return self.values[2:8]

def parse_data(line):
    parts = line.strip().split(',')
    if len(parts) != 21 or parts[:2] != ['DATA', '1']:
        raise ValueError('quadro ou versão inválidos')
    data = parts[2:]
    values = [integer(data[0], 0, 2**32-1), integer(data[1], 0, 2**32-1)]
    for i in range(2, 10):
        v = float(data[i])
        if math.isinf(v) or (math.isnan(v) and i >= 8):
            raise ValueError('valor não finito')
        if math.isfinite(v) and not -250 <= v <= 1000:
            raise ValueError('temperatura fora da faixa do protocolo')
        values.append(v)
    for i, maximum in zip(range(10, 19), (255, 255, 1, 1, 63, 63, 1, 7200, 7200)):
        values.append(integer(data[i], 0, maximum))
    for chamber in range(2):
        run, fault, pwm = values[12+chamber], values[14+chamber], values[10+chamber]
        if (not run and pwm) or (run and (fault or not values[16])):
            raise ValueError('estado inseguro/inconsistente')
        if run and any(not math.isfinite(values[i]) for i in (2+2*chamber, 3+2*chamber, 6+chamber)):
            raise ValueError('aquecimento sem sensores válidos')
    return Frame(tuple(values))

def start_command(chamber, sp, kp, ki, kd, duration):
    values = tuple(float(x) for x in (sp, kp, ki, kd, duration))
    limits = ((5, 85), (0.0001, 100), (0, 20), (0, 100), (1, 7200))
    if chamber not in (1, 2) or any(not math.isfinite(v) or not lo <= v <= hi
                                                  for v, (lo, hi) in zip(values, limits)):
        raise ValueError('Use SP 5–85 °C; Kp >0–100; Ki 0–20; Kd 0–100; duração 1–7200 s.')
    return 'START', [str(chamber)] + [f'{v:.6g}' for v in values]

class Stream:
    """Rejeita duplicatas/reordenação e detecta reinício; aceita rollover de uint32."""
    def __init__(self):
        self.previous = None

    def accept(self, frame):
        if self.previous is not None:
            for key in ('seq', 'arduino_ms'):
                delta = (frame.get(key)-self.previous.get(key)) & 0xffffffff
                if not 0 < delta < 2**31:
                    raise ValueError('reinício ou quadro fora de ordem')
        self.previous = frame
