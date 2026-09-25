import math
import unittest
from protocol import parse_data, start_command, Stream

def packet(**overrides):
    fields = ['DATA','1','0','500','25','25','25','25','25','25','40','40',
              '0','0','0','0','0','0','1','0','0']
    for key, value in overrides.items():
        fields[int(key)] = str(value)
    return ','.join(fields)

class ProtocolTests(unittest.TestCase):
    def test_six_sensors_mapping(self):
        f = parse_data(packet(**{'4': 21, '8': 28, '9': 29}))
        self.assertEqual(f.temperatures, (21,25,25,25,28,29))
        self.assertEqual(f.get('configured'), 1)

    def test_nan_is_fault_not_zero(self):
        f = parse_data(packet(**{'4': 'nan', '16': 1}))
        self.assertTrue(math.isnan(f.temperatures[0]))

    def test_bad_frames(self):
        for text in ('ACK,1,START', packet()+',1', packet().replace('DATA,1','DATA,2'),
                     packet(**{'4':'inf'}), packet(**{'10':'nan'}), packet(**{'12':256}),
                     packet(**{'14':1, '16':1}), packet(**{'12':40}),
                     packet(**{'4':'nan','14':1}), packet(**{'14':1,'18':0})):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_data(text)

    def test_start_validation(self):
        command, args = start_command(2,40,8,.1,0,600)
        self.assertEqual((command, args[0]), ('START','2'))
        for vals in ((1,'nan',8,0,0,600),(1,91,8,0,0,600),(3,40,8,0,0,600),
                     (1,40,8,0,0,0),(1,40,-1,0,0,600)):
            with self.assertRaises(ValueError):
                start_command(*vals)

    def test_reboot_and_duplicate(self):
        s = Stream()
        s.accept(parse_data(packet(**{'2':10,'3':6000})))
        with self.assertRaises(ValueError):
            s.accept(parse_data(packet(**{'2':10,'3':6000})))
        with self.assertRaises(ValueError):
            s.accept(parse_data(packet()))

    def test_rollover(self):
        s = Stream()
        s.accept(parse_data(packet(**{'2':2**32-1,'3':2**32-20})))
        s.accept(parse_data(packet(**{'2':0,'3':500})))

if __name__ == '__main__':
    unittest.main()
