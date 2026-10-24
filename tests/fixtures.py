"""Sparse memory fixture representing the independently traced native battle layout."""
import json
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
from memory import ReadError
from native_reader import LoggerReader as NativeReader

PROFILE = json.loads((PROJECT / 'profiles' / 'wh3_saved_build.json').read_text(encoding='utf-8'))


class FakeMemory:
    def __init__(self):
        self.blocks = []
        self.cursor = 0x100000
        self.calls = self.bytes_read = 0
        self.after_read = None

    def allocate(self, size):
        address = self.cursor
        self.cursor += ((size + 255) // 256 + 1) * 256
        self.blocks.append((address, bytearray(size)))
        return address

    def at(self, address, size):
        self.blocks.append((address, bytearray(size)))

    def locate(self, address, size):
        for base, data in self.blocks:
            if base <= address and address + size <= base + len(data):
                return data, address - base
        raise ReadError('Fixture has no bytes at ' + hex(address))

    def write(self, address, data):
        block, offset = self.locate(address, len(data))
        block[offset:offset + len(data)] = data

    def q(self, address, value):
        self.write(address, struct.pack('<Q', value))

    def u(self, address, value):
        self.write(address, struct.pack('<I', value))

    def read(self, address, size):
        self.calls += 1
        block, offset = self.locate(address, size)
        value = bytes(block[offset:offset + size])
        self.bytes_read += size
        if self.after_read:
            self.after_read(address, size)
        return value

    def vector(self, base, count_offset, data_offset, entries):
        array = self.allocate(max(8, len(entries) * 8))
        self.u(base + count_offset, len(entries))
        self.q(base + data_offset, array)
        for index, value in enumerate(entries):
            self.q(array + index * 8, value)
        return array

    def string(self, address, value):
        data = value.encode('utf-16-le')
        units = len(data) // 2
        if units <= 2:
            raw = bytearray(16)
            raw[:len(data)] = data
            raw[15] = 0x80 | units
            self.write(address, raw)
        else:
            buffer = self.allocate(len(data))
            self.write(buffer, data)
            self.write(address, struct.pack('<IIQ', units, units, buffer))


class BattleFixture:
    def __init__(self, own_count=2, enemy_count=1):
        self.memory = FakeMemory()
        m = self.memory
        self.module = dict(base=0x180000000, size=PROFILE['image_size'])
        self.engine = m.allocate(0x600)
        self.context = m.allocate(0x480)
        self.roster = m.allocate(0x120)
        self.script = m.allocate(0x500)
        self.my_army = m.allocate(0x180)
        self.enemy_army = m.allocate(0x180)
        # VAs from the native CCO factory and model-time getter, relocated by 0x40000000.
        m.at(0x184479e50, 16)
        m.at(0x184479ee0, 8)
        m.q(0x184479e50, self.engine)
        m.write(0x184479e58, b'\x01')
        m.q(0x184479ee0, self.script)
        m.u(self.script + 0x4a4, 10000)
        m.q(self.engine + 0x418, self.context)
        m.q(self.context + 0x448, self.roster)
        m.q(self.engine + 0x558, self.my_army)
        m.u(self.my_army + 0x88, 7)
        m.u(self.enemy_army + 0x88, 9)
        m.write(self.my_army + 0xac, struct.pack('<fffff', 30, 100, 5, 0, 60))
        m.write(self.enemy_army + 0xac, struct.pack('<fffff', 10, 100, 2.5, 0, 80))
        alliances = [m.allocate(0x110), m.allocate(0x110)]
        m.q(self.my_army + 0x148, alliances[0])
        m.q(self.enemy_army + 0x148, alliances[1])
        m.vector(self.roster, 0x104, 0x108, alliances)
        m.vector(alliances[0], 0x1c, 0x20, [self.my_army])
        m.vector(alliances[1], 0x1c, 0x20, [self.enemy_army])
        self.own = [self.unit(100 + i, self.my_army, 'Skeletons', (i + 1) * 125) for i in range(own_count)]
        self.enemy = [self.unit(200 + i, self.enemy_army, 'Zombies', 90) for i in range(enemy_count)]
        m.vector(self.my_army, 0x44, 0x48, [unit['address'] for unit in self.own])
        m.vector(self.my_army, 0x54, 0x58, [])
        m.vector(self.enemy_army, 0x44, 0x48, [unit['address'] for unit in self.enemy])
        m.vector(self.enemy_army, 0x54, 0x58, [])
        for alliance in alliances:
            m.vector(alliance, 0xf4, 0xf8, [u['adapter'] for u in self.own + self.enemy])
        self.reader = NativeReader(m, self.module, PROFILE)

    def unit(self, uid, army, name, damage, visible=True):
        m = self.memory
        address, adapter, result = m.allocate(0x800), m.allocate(0x3e00), m.allocate(0x150)
        m.write(address + 0x598, struct.pack('<fff', uid - 100, 2.5, uid * 2))
        m.write(address + 0x6cc, struct.pack('<f', 0.75))
        m.u(address + 0x614, uid)
        m.write(address + 0x6f4, bytes([int(visible)]))
        m.write(address + 0x6fe, b'\x01')
        m.write(address + 0x6fb, b'\x01')
        m.u(address + 0x6ac, 8000)
        m.u(address + 0x6b0, 7500)
        m.u(address + 0x634, 120)
        m.u(address + 0x664, 115)
        m.q(address + 0x758, adapter)
        m.q(adapter + 0x70, army)
        m.write(adapter + 0x3d90,struct.pack('<III4xIII',20,0,40,5,0,10))
        morale=m.allocate(0xc0)
        m.q(address+0x160,morale)
        m.u(morale+0x48,65)
        stats = m.allocate(0x280)
        m.q(adapter + 0x3d48, stats)
        m.u(stats + 0x264, 6000)
        details = m.allocate(0x210)
        m.q(address + 0x1a8, details)
        m.q(address + 0x760, army)
        m.q(adapter + 0x68, result)
        m.string(result + 0x68, name)
        m.string(result + 0x78, '')
        m.u(result + 0xc4, damage)
        m.u(result + 0x20 + 12, damage)  # Native enemy-melee credit.
        m.u(result + 0x108, 4)
        return dict(uid=uid, address=address, adapter=adapter, result=result)

    def sample(self):
        return self.reader.sample()
