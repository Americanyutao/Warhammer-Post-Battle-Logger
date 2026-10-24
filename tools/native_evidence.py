"""Targeted PE reads and development-only disassembly; no game writes or analysis."""
from pathlib import Path
import re
import struct
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.dont_write_bytecode = True


class Image:
    def __init__(self, file):
        self.file = Path(file)
        self.stream = self.file.open('rb')
        dos = self.stream.read(64)
        self.stream.seek(struct.unpack_from('<I', dos, 0x3c)[0])
        header = self.stream.read(264)
        self.base = struct.unpack_from('<Q', header, 48)[0]
        self.sections = []
        self.stream.seek(struct.unpack_from('<I', dos, 0x3c)[0] + 24 + struct.unpack_from('<H', header, 20)[0])
        for _ in range(struct.unpack_from('<H', header, 6)[0]):
            raw = self.stream.read(40)
            self.sections.append(dict(name=raw[:8].rstrip(b'\0').decode(),
                virtual_size=struct.unpack_from('<I', raw, 8)[0], rva=struct.unpack_from('<I', raw, 12)[0],
                size=struct.unpack_from('<I', raw, 16)[0], offset=struct.unpack_from('<I', raw, 20)[0],
                flags=struct.unpack_from('<I', raw, 36)[0]))

    def read(self, address, size):
        rva = address - self.base
        if rva < 0x1000:
            offset = rva
        else:
            section = next(s for s in self.sections if s['rva'] <= rva and rva + size <= s['rva'] + s['size'])
            offset = section['offset'] + rva - section['rva']
        self.stream.seek(offset)
        value = self.stream.read(size)
        if len(value) != size:
            raise ValueError('Short PE read')
        return value

    def instructions(self, address, size=128):
        sys.path.insert(0, str(ROOT / 'tools' / 'ar-python-deps'))
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
        decoder = Cs(CS_ARCH_X86, CS_MODE_64)
        decoder.detail = True
        return list(decoder.disasm(self.read(address, size), address))

    def listing(self, address, size=128):
        return '\n'.join(f'{i.address:x}: {i.bytes.hex():<30} {i.mnemonic} {i.op_str}' for i in self.instructions(address, size))

    def code_sections(self):
        for section in self.sections:
            if section['flags'] & 0x20000000:
                yield self.base + section['rva'], self.read(self.base + section['rva'], section['size'])


def pattern(image, address, size):
    sys.path.insert(0, str(ROOT / 'tools' / 'ar-python-deps'))
    from capstone import CS_GRP_CALL, CS_GRP_JUMP
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    raw = bytearray(image.read(address, size))
    mask = bytearray(b'\1' * size)
    for instruction in image.instructions(address, size):
        offset = instruction.address - address
        if any(o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP for o in instruction.operands):
            for index in range(instruction.disp_offset, instruction.disp_offset + instruction.disp_size):
                mask[offset + index] = 0
        if instruction.group(CS_GRP_CALL) or instruction.group(CS_GRP_JUMP):
            if any(o.type == X86_OP_IMM for o in instruction.operands):
                for index in range(instruction.imm_offset, instruction.imm_offset + instruction.imm_size):
                    mask[offset + index] = 0
    return re.compile(b''.join(re.escape(bytes([value])) if known else b'.' for value, known in zip(raw, mask)), re.DOTALL)


if __name__ == '__main__':
    image = Image(ROOT / 'decompile project' / 'Warhammer3.exe')
    for value in sys.argv[1:]:
        address, _, count = value.partition(':')
        print(image.listing(int(address, 16), int(count, 0) if count else 128))
