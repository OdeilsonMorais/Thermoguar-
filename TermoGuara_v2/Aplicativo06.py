"""TermoGuará: seis temperaturas, dois controladores e registro incremental.
Instalação: python -m pip install -r requirements.txt
Execução: python Aplicativo06.py
"""
import csv
from collections import deque
from datetime import datetime
import json
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import serial
from serial.tools import list_ports
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from protocol import FIELDS, Stream, parse_data, start_command, fault_text

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('TermoGuará • duas câmaras')
        self.geometry('1180x850')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.ser = None
        self.ready = False
        self.connected_at = self.last_rx = self.last_ping = self.last_plot = 0
        self.buffer = bytearray()
        self.pending = {}
        self.command_id = 0
        self.stream = Stream()
        self.frame = None
        self.history = deque(maxlen=3600)
        self.csv_file = self.writer = None
        self.record_started = 0
        self.csv_path = None
        self.entries = []
        self.labels = []
        self.start_buttons = []
        self.status = tk.StringVar(value='Selecione a porta do Nano e conecte.')
        self.command_status = tk.StringVar(value='Nenhum comando de aquecimento enviado.')
        self.record_status = tk.StringVar(value='CSV: sem gravação')
        self.make_ui()
        self.refresh_ports()
        self.after(50, self.poll)

    def make_ui(self):
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill='x')
        self.port = ttk.Combobox(bar, width=23, state='readonly')
        self.port.pack(side='left', padx=4)
        ttk.Button(bar, text='Atualizar portas', command=self.refresh_ports).pack(side='left', padx=4)
        ttk.Button(bar, text='Conectar', command=self.connect).pack(side='left', padx=4)
        ttk.Button(bar, text='Desconectar', command=self.disconnect).pack(side='left', padx=4)
        tk.Button(bar, text='PARAR AMBAS', bg='#a82020', fg='white', command=self.stop_all).pack(side='right')
        ttk.Label(self, textvariable=self.status, wraplength=1140).pack(fill='x', padx=14, pady=4)
        ttk.Label(self, textvariable=self.command_status, wraplength=1140).pack(fill='x', padx=14)
        panels = ttk.Frame(self)
        panels.pack(fill='x', padx=10)
        for i in range(2):
            box = ttk.LabelFrame(panels, text=f'Câmara {i+1}', padding=10)
            box.pack(side='left', expand=True, fill='both', padx=4)
            label = ttk.Label(box, text='NTC A: — | NTC B: — | PT1000: —', font=('', 12))
            label.grid(row=0, column=0, columnspan=5, sticky='w', pady=5)
            self.labels.append(label)
            entries = []
            for col, (title, default) in enumerate((('Alvo °C', '40'), ('Kp', '8'), ('Ki', '0'),
                                                    ('Kd', '0'), ('Duração s', '600'))):
                ttk.Label(box, text=title).grid(row=1, column=col, padx=4)
                entry = ttk.Entry(box, width=10)
                entry.insert(0, default)
                entry.grid(row=2, column=col, padx=4, pady=4)
                entries.append(entry)
            self.entries.append(entries)
            button = ttk.Button(box, text='Iniciar câmara', command=lambda k=i: self.start(k))
            button.grid(row=3, column=0, columnspan=2, pady=8)
            self.start_buttons.append(button)
            ttk.Button(box, text='Desligar', command=lambda k=i: self.action('OFF', [k+1])).grid(row=3, column=2)
            ttk.Button(box, text='Rearmar falha', command=lambda k=i: self.action('CLR', [k+1])).grid(row=3, column=3, columnspan=2)
        record = ttk.Frame(self, padding=10)
        record.pack(fill='x')
        ttk.Button(record, text='Abrir CSV / iniciar gravação', command=self.open_csv).pack(side='left', padx=4)
        ttk.Button(record, text='Encerrar gravação', command=self.finish_csv).pack(side='left', padx=4)
        ttk.Label(record, textvariable=self.record_status).pack(side='left', padx=8)
        ttk.Label(self, text='PID usa a média dos NTC; PT1000 mede a amostra. Ganhos iniciais são apenas ponto de partida.').pack()
        fig = Figure(figsize=(10, 4), dpi=100)
        self.axes = fig.subplots(1, 2)
        self.lines = []
        for i, ax in enumerate(self.axes):
            ax.set_title(f'Câmara {i+1}')
            ax.set_xlabel('Tempo desde conexão (s)')
            ax.set_ylabel('Temperatura (°C)')
            ax.grid(alpha=.25)
            self.lines.append([ax.plot([], [], label=name, linestyle='--' if name=='Alvo' else '-')[0]
                               for name in ('NTC A', 'NTC B', 'PT1000', 'Alvo')])
            ax.legend(loc='upper left')
        fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(fig, self)
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)

    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.port['values'] = ports
        if ports and self.port.get() not in ports:
            self.port.set(ports[0])

    def connect(self):
        if self.ser:
            return
        if not self.port.get():
            messagebox.showerror('Porta', 'Selecione a porta do Arduino.')
            return
        try:
            self.ser = serial.Serial(self.port.get(), 115200, timeout=0, write_timeout=0.2)
        except (serial.SerialException, OSError) as exc:
            self.status.set(str(exc))
            return
        self.connected_at = time.monotonic()
        self.last_rx = self.last_ping = 0
        self.ready = False
        self.frame = None
        self.buffer.clear()
        self.pending.clear()
        self.stream = Stream()
        self.history.clear()
        self.status.set('Aguardando reinicialização do Nano e identificação do firmware…')

    def send(self, command, args=()):
        if not self.ser:
            raise ValueError('Porta desconectada.')
        self.command_id = self.command_id % 65535 + 1
        ident = str(self.command_id)
        line = ','.join([command, ident] + [str(a) for a in args]) + '\n'
        encoded = line.encode('ascii')
        if len(encoded) > 95:
            raise ValueError('Comando longo demais.')
        if command not in ('PING', 'HELLO'):
            self.log_event('TX ' + line.strip())
        if self.ser.write(encoded) != len(encoded):
            raise serial.SerialException('Escrita serial incompleta.')
        self.pending[ident] = (command, time.monotonic())
        return ident

    def action(self, command, args=()):
        try:
            if not self.ready:
                raise ValueError('Firmware ainda não identificado.')
            self.send(command, args)
            self.command_status.set(f'{command}: aguardando confirmação do Arduino…')
        except (ValueError, serial.SerialException, OSError) as exc:
            self.fail(str(exc))

    def start(self, i):
        try:
            if not self.ready or not self.frame or time.monotonic()-self.last_rx > 2:
                raise ValueError('Sem telemetria recente.')
            if not self.frame.get('configured'):
                raise ValueError('Confira Config.h e a montagem; HARDWARE_VERIFIED ainda é false.')
            if self.frame.get(f'fault{i+1}'):
                raise ValueError('Corrija a causa e rearme a falha antes de iniciar.')
            command, args = start_command(i+1, *(e.get().replace(',', '.') for e in self.entries[i]))
            if not self.csv_file:
                self.open_csv()
            if not self.csv_file:
                return
            self.send('PING')
            self.last_ping = time.monotonic()
            self.action(command, args)
        except (ValueError, serial.SerialException, OSError) as exc:
            messagebox.showerror('Não foi possível iniciar', str(exc))

    def stop_all(self):
        if self.ser:
            self.action('STOP')

    def open_csv(self):
        if self.csv_file:
            return
        # Diálogos modais podem suspender o heartbeat; só abra com saídas desligadas.
        if self.frame and any(self.frame.get(f'run{i}') for i in (1, 2)):
            self.status.set('Desligue as câmaras antes de abrir um arquivo.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')],
                                          initialfile=datetime.now().strftime('termoguara_%Y%m%d_%H%M%S.csv'))
        if not path:
            return
        try:
            # Exclusivo: não sobrescreve um ensaio, mesmo após confirmação do diálogo.
            self.csv_file = open(path, 'x', newline='', encoding='utf-8-sig')
            self.writer = csv.writer(self.csv_file, delimiter=';')
            self.writer.writerow(['pc_iso', 'elapsed_s'] + list(FIELDS))
            self.csv_file.flush()
            self.record_started = time.monotonic()
            self.csv_path = path
            config = Path(__file__).parent / 'firmware' / 'TermoGuara' / 'Config.h'
            metadata = {'software': 'TermoGuara 2 / protocol 1', 'port': self.port.get(),
                        'created': datetime.now().astimezone().isoformat(),
                        'requested_parameters': [[e.get() for e in entries] for entries in self.entries],
                        'local_config_reference_only': config.read_text(encoding='utf-8') if config.exists() else None,
                        'note': 'O Config.h local não comprova o firmware gravado. PWM é comando, não potência medida.'}
            Path(path + '.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
            self.record_status.set(f'Gravando: {Path(path).name}')
        except OSError as exc:
            self.finish_csv()
            messagebox.showerror('CSV', str(exc))

    def finish_csv(self):
        if self.frame and any(self.frame.get(f'run{i}') for i in (1, 2)) and self.ser:
            self.stop_all()
        if self.csv_file:
            try:
                self.csv_file.close()
            except OSError as exc:
                self.status.set(f'Erro ao fechar CSV: {exc}')
        self.csv_file = self.writer = None
        self.record_status.set('CSV encerrado' if self.csv_path else 'CSV: sem gravação')

    def receive(self, line):
        if line.startswith('DATA,'):
            frame = parse_data(line)
            if not self.ready:
                return
            self.stream.accept(frame)
            self.frame = frame
            now = time.monotonic()
            self.last_rx = now
            self.history.append((now-self.connected_at, frame))
            if self.writer:
                self.writer.writerow([datetime.now().astimezone().isoformat(),
                                      f'{now-self.record_started:.3f}'] + list(frame.values))
                self.csv_file.flush()
            for i in range(2):
                t = frame.temperatures
                self.labels[i].configure(text=(f'NTC A: {t[2*i]:.2f} | NTC B: {t[2*i+1]:.2f} | PT: {t[4+i]:.2f} °C\n'
                    f'Média: {(t[2*i]+t[2*i+1])/2:.2f} °C | Alvo: {frame.get(f"sp{i+1}_c"):.1f} °C\n'
                    f'PWM: {100*frame.get(f"pwm{i+1}")/255:.1f}% | '
                    f'{"LIGADO" if frame.get(f"run{i+1}") else "DESLIGADO"} | Restam {frame.get(f"remaining{i+1}_s")} s\n'
                    f'{fault_text(frame.get(f"fault{i+1}"))}'))
            self.status.set('Telemetria ativa • ' + ('configuração liberada' if frame.get('configured') else
                            'aquecimento bloqueado: confira Config.h e a montagem'))
            return
        p = line.split(',')
        if p == ['BOOT', 'THERMOGUARA', '1']:
            if self.ready:
                raise ValueError('Arduino reiniciou. Reconecte e confira o ensaio.')
            return
        if len(p) == 4 and p[0] == 'INFO' and p[2:] == ['THERMOGUARA', '1']:
            pending = self.pending.get(p[1])
            if pending and pending[0] == 'HELLO':
                del self.pending[p[1]]
                self.ready = True
                self.last_rx = time.monotonic()
                self.send('STOP') # conexão nunca retoma ensaio anterior
            return
        if len(p) == 3 and p[0] in ('ACK', 'ERR'):
            pending = self.pending.pop(p[1], None)
            if not pending:
                return
            if p[0] == 'ERR':
                self.command_status.set(f'Arduino recusou {pending[0]}: {p[2]}')
                self.log_event(line)
                return
            if p[2] != pending[0]:
                raise ValueError('Confirmação serial incompatível.')
            if p[2] != 'PING':
                self.command_status.set(f'Arduino confirmou {p[2]}.')
                self.log_event(line)
            return
        raise ValueError('Resposta serial desconhecida; confira o firmware e 115200 baud.')

    def log_event(self, text):
        if self.csv_file and self.csv_path:
            with open(self.csv_path + '.events.txt', 'a', encoding='utf-8') as f:
                f.write(datetime.now().astimezone().isoformat() + ' ' + text + '\n')

    def fail(self, reason):
        self.disconnect()
        self.status.set(f'PARADA: {reason} Saídas sem confirmação devem ser verificadas; timeout no Arduino: 3 s.')
        for label in self.labels:
            label.configure(text='SEM TELEMETRIA — últimos valores não são atuais')

    def disconnect(self):
        device, self.ser = self.ser, None
        self.ready = False
        if device:
            try:
                device.write(b'STOP,65535\n')
            except (serial.SerialException, OSError):
                pass
            finally:
                device.close()
        self.pending.clear()
        self.finish_csv()
        self.status.set('Desconectado. STOP enviado quando possível; desligamento não confirmado.')

    def poll(self):
        try:
            now = time.monotonic()
            if self.ser:
                if not self.ready and now-self.connected_at > 2.5 and not self.pending:
                    self.send('HELLO')
                if not self.ready and now-self.connected_at > 8:
                    raise ValueError('Identificação do firmware não recebida.')
                count = min(self.ser.in_waiting, 4096)
                if count:
                    self.buffer.extend(self.ser.read(count))
                    if len(self.buffer) > 8192:
                        raise ValueError('Buffer serial excedido.')
                    while b'\n' in self.buffer:
                        raw, _, tail = self.buffer.partition(b'\n')
                        self.buffer = bytearray(tail)
                        self.receive(raw.decode('ascii').strip())
                if self.ready:
                    if now-self.last_rx > 2:
                        raise ValueError('Telemetria interrompida.')
                    if self.frame and now-self.last_ping >= 0.8:
                        self.send('PING')
                        self.last_ping = now
                if any(now-sent > 3 for _, sent in self.pending.values()):
                    raise ValueError('Comando sem confirmação; reconecte para verificar.')
            starting = any(cmd == 'START' for cmd, _ in self.pending.values())
            for i, button in enumerate(self.start_buttons):
                active = (self.ready and self.frame and not starting and self.frame.get('configured') and
                          not self.frame.get(f'run{i+1}') and not self.frame.get(f'fault{i+1}'))
                button.configure(state='normal' if active else 'disabled')
            if now-self.last_plot > 1:
                self.draw_plot()
                self.last_plot = now
        except (ValueError, UnicodeError, serial.SerialException, OSError) as exc:
            self.fail(str(exc))
        finally:
            self.after(50, self.poll)

    def draw_plot(self):
        data = list(self.history)
        x = [item[0] for item in data]
        for i in range(2):
            keys = (f'ntc{i+1}a_c', f'ntc{i+1}b_c', f'pt{i+1}_c', f'sp{i+1}_c')
            for line, key in zip(self.lines[i], keys):
                line.set_data(x, [item[1].get(key) for item in data])
            self.axes[i].relim()
            self.axes[i].autoscale_view()
        self.canvas.draw_idle()

    def close(self):
        self.disconnect()
        # Remove callbacks de polling/desenho antes de destruir o interpretador Tk.
        for timer in self.tk.call('after', 'info'):
            self.tk.call('after', 'cancel', timer)
        self.destroy()

if __name__ == '__main__':
    App().mainloop()
