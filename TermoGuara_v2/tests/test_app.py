"""Integração GUI/serial com transporte simulado, sem acessar o Arduino."""
import csv
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from Aplicativo06 import App
from test_protocol import packet

class FakeSerial:
    def __init__(self):
        self.incoming = bytearray()
        self.sent = []
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.incoming)

    def read(self, size):
        result = bytes(self.incoming[:size])
        del self.incoming[:size]
        return result

    def write(self, value):
        self.sent.append(value)
        return len(value)

    def close(self):
        self.closed = True

class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.app.withdraw()
        self.app.update_idletasks()
        self.device = FakeSerial()
        self.app.ser = self.device
        self.app.connected_at = time.monotonic()

    def tearDown(self):
        self.app.close()

    def identify(self):
        ident = self.app.send('HELLO')
        self.app.receive(f'INFO,{ident},THERMOGUARA,1')
        self.assertTrue(self.app.ready)
        self.assertTrue(self.device.sent[-1].startswith(b'STOP,'))

    def test_handshake_and_six_display_values(self):
        self.identify()
        self.app.receive(packet())
        self.app.draw_plot()
        self.app.update_idletasks()
        self.assertIn('25.00', self.app.labels[0].cget('text'))
        self.assertEqual(len(self.app.lines[0][0].get_xdata()), 1)

    def test_csv_incremental_and_command_audit(self):
        self.identify()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'run.csv')
            with patch('Aplicativo06.filedialog.asksaveasfilename', return_value=path):
                self.app.open_csv()
            self.app.receive(packet())
            self.app.send('START', [1, 40, 8, 0, 0, 600])
            # Lê antes de fechar: comprova flush do primeiro quadro.
            with open(path, encoding='utf-8-sig', newline='') as f:
                rows = list(csv.reader(f, delimiter=';'))
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(rows[0]), len(rows[1]))
            self.assertEqual(rows[0][8:10], ['pt1_c','pt2_c'])
            self.assertIn('START', Path(path+'.events.txt').read_text())
            self.assertTrue(Path(path+'.json').exists())
            self.app.finish_csv()

    def test_stale_telemetry_disconnects_and_stops(self):
        self.identify()
        self.app.last_rx = time.monotonic()-4
        self.app.poll()
        self.assertIsNone(self.app.ser)
        self.assertTrue(self.device.closed)
        self.assertEqual(self.device.sent[-1], b'STOP,65535\n')

    def test_partial_frame_and_corruption(self):
        self.identify()
        text = packet().encode()+b'\n'
        self.device.incoming.extend(text[:20])
        self.app.poll()
        self.assertIsNone(self.app.frame)
        self.device.incoming.extend(text[20:])
        self.app.poll()
        self.assertIsNotNone(self.app.frame)
        self.device.incoming.extend(b'DATA,1,bad\n')
        self.app.poll()
        self.assertIsNone(self.app.ser)

    def test_reboot_after_handshake(self):
        self.identify()
        with self.assertRaises(ValueError):
            self.app.receive('BOOT,THERMOGUARA,1')

    def test_rejected_command_remains_visible(self):
        self.identify()
        ident = self.app.send('START', [1,40,8,0,0,600])
        self.app.receive(f'ERR,{ident},CONFIG_REQUIRED')
        self.app.receive(packet())
        self.assertIn('CONFIG_REQUIRED', self.app.command_status.get())

if __name__ == '__main__':
    unittest.main()
