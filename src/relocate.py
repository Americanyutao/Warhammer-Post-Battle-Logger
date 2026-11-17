"""Adapt a verified build profile to a patched executable whose code merely moved.

Each code anchor is searched in the new executable with only its relative
call/jump/RIP displacements masked; every other byte, including the struct
offsets the logger reads, must match exactly.  Globals and data constants are
decoded through the same RIP references that pointed at them in the verified
profile.  Any missing anchor or inconsistent global rejects the build, so a
patch that changes the battle structures still reports an unsupported build.
"""
from __future__ import annotations
import copy
import hashlib
import struct

TRAILING = (0, 1, 2, 4)   # immediate bytes that may follow a RIP displacement


class RelocationError(RuntimeError):
    pass


def pe_layout(image):
    if image[:2] != b'MZ':
        raise RelocationError('The game executable has no MZ header.')
    offset = struct.unpack_from('<I', image, 0x3c)[0]
    if image[offset:offset + 4] != b'PE\0\0':
        raise RelocationError('The game executable has no PE header.')
    count, optional = struct.unpack_from('<H', image, offset + 6)[0], struct.unpack_from('<H', image, offset + 20)[0]
    sections, at = [], offset + 24 + optional
    for _ in range(count):
        vsize, rva, rsize, raw = struct.unpack_from('<IIII', image, at + 8)
        flags = struct.unpack_from('<I', image, at + 36)[0]
        sections.append(dict(rva=rva, size=min(vsize or rsize, rsize), raw=raw, code=bool(flags & 0x20000000)))
        at += 40
    return dict(stamp=struct.unpack_from('<I', image, offset + 8)[0], size=struct.unpack_from('<I', image, offset + 80)[0],
                base=struct.unpack_from('<Q', image, offset + 48)[0], sections=sections)


def _rip(data, i):
    return i >= 2 and (data[i - 1] & 0xc7) == 0x05


def masked_pattern(data, rva, size):
    """Mask rel32 fields whose target lies in the module: call/jmp/jcc and RIP-relative operands."""
    mask = bytearray(b'\xff' * len(data))
    for i in range(1, len(data) - 3):
        branch = data[i - 1] in (0xe8, 0xe9) or (i >= 2 and data[i - 2] == 0x0f and 0x80 <= data[i - 1] <= 0x8f)
        if branch or _rip(data, i):
            displacement = struct.unpack_from('<i', data, i)[0]
            if any(0 <= rva + i + 4 + extra + displacement < size for extra in TRAILING):
                mask[i:i + 4] = b'\0\0\0\0'
    return bytes(mask)


def _references(anchors, base, targets):
    """(anchor index, position, trailing) for each RIP operand that resolved to a target address."""
    found = {}
    for index, anchor in enumerate(anchors):
        data, address = bytes.fromhex(anchor['hex']), int(anchor['address'], 0)
        for i in range(2, len(data) - 3):
            if _rip(data, i):
                displacement = struct.unpack_from('<i', data, i)[0]
                for extra in TRAILING:
                    target = address + i + 4 + extra + displacement
                    if target in targets and i + 4 + extra <= len(data):
                        found.setdefault(targets[target], []).append((index, i, extra))
    return found


def _candidates(view, start_rva, data, mask, limit=64):
    segments, begin = [], None
    for i, m in enumerate(mask + b'\0'):
        if m and begin is None: begin = i
        elif not m and begin is not None: segments.append((begin, i)); begin = None
    first, last = max(segments, key=lambda s: s[1] - s[0])
    needle, found, at = data[first:last], [], view.find(data[first:last])
    while at >= 0 and len(found) <= limit:
        origin = at - first
        chunk = view[origin:origin + len(data)] if origin >= 0 else b''
        if len(chunk) == len(data) and all((a ^ b) & m == 0 for a, b, m in zip(chunk, data, mask)):
            found.append(start_rva + origin)
        at = view.find(needle, at + 1)
    return found


def adapt_profile(profile, image):
    """Return a copy of profile relocated into image (the new executable's bytes), or raise RelocationError."""
    layout, base, old_size = pe_layout(image), int(profile['image_base'], 0), profile['image_size']
    if layout['base'] != base:
        raise RelocationError('The game executable has a different preferred image base.')
    code = [(s['rva'], image[s['raw']:s['raw'] + s['size']]) for s in layout['sections'] if s['code']]

    def read(rva, size):
        for s in layout['sections']:
            if s['rva'] <= rva and rva + size <= s['rva'] + s['size']:
                return image[s['raw'] + rva - s['rva']:s['raw'] + rva - s['rva'] + size]
        return None

    anchors = profile['anchors']
    old = [int(a['address'], 0) - base for a in anchors]
    data = [bytes.fromhex(a['hex']) for a in anchors]
    is_code = [len(d) > 8 for d in data]  # 4-8 byte anchors are data constants
    located, ambiguous = {}, {}
    for index, anchor in enumerate(anchors):
        if not is_code[index]:
            continue
        mask = masked_pattern(data[index], old[index], old_size)
        if sum(1 for m in mask if m) < 8:
            raise RelocationError('Anchor ' + anchor['address'] + ' has too few fixed bytes to locate.')
        hits = [rva for start, view in code for rva in _candidates(view, start, data[index], mask)]
        if not hits:
            raise RelocationError('Game code changed at anchor ' + anchor['address'] + '.')
        (located.__setitem__(index, hits[0]) if len(hits) == 1 else ambiguous.__setitem__(index, hits))
    if not located:
        raise RelocationError('No game code anchor could be located uniquely.')
    # A repeated pattern is still proof the exact code exists; record the copy closest to where
    # the nearest uniquely located anchor moved (neighbouring functions move together).
    unique = sorted(located, key=lambda i: old[i])
    for index, hits in ambiguous.items():
        nearest = min(unique, key=lambda i: abs(old[i] - old[index]))
        shift = located[nearest] - old[nearest]
        located[index] = min(hits, key=lambda rva: abs(rva - old[index] - shift))

    def decode(index, position, extra):
        current = read(located[index], len(data[index]))
        return located[index] + position + 4 + extra + struct.unpack_from('<i', current, position)[0]

    # Data constants: follow the RIP references of uniquely located code to their new home.
    constants = {base + old[i]: i for i in range(len(anchors)) if not is_code[i]}
    for name, refs in _references(anchors, base, constants).items():
        hits = [decode(*ref) for ref in refs if ref[0] in located and ref[0] not in ambiguous]
        hits = [rva for rva in hits if read(rva, len(data[name])) == data[name]]
        if hits:
            located[name] = hits[0]
    missing = [anchors[i]['address'] for i in range(len(anchors)) if i not in located]
    if missing:
        raise RelocationError('Game data changed at anchor ' + ', '.join(missing) + '.')

    globals_ = {}
    targets = {int(value, 0): name for name, value in profile['globals'].items()}
    references = _references(anchors, base, targets)
    for name in profile['globals']:
        values = {decode(*ref) for ref in references.get(name, ())}
        if not values:
            raise RelocationError('Global ' + name + ' is not referenced by any anchor.')
        if len(values) != 1:
            raise RelocationError('Global ' + name + ' decodes inconsistently in the new build.')
        globals_[name] = hex(base + values.pop())

    adapted = copy.deepcopy(profile)
    for index, anchor in enumerate(adapted['anchors']):
        anchor['address'] = hex(base + located[index])
        anchor['hex'] = read(located[index], len(data[index])).hex()
    adapted['globals'] = globals_
    adapted.update(name='WH3 build ' + str(layout['stamp']) + ' (adapted from ' + profile['name'] + ')',
                   pe_timestamp=layout['stamp'], image_size=layout['size'],
                   source_sha256=hashlib.sha256(image).hexdigest(),
                   adapted_from=dict(name=profile['name'], pe_timestamp=profile['pe_timestamp'],
                                     source_sha256=profile['source_sha256'], repeated_anchors=len(ambiguous)),
                   live_validation='Adapted automatically: every code anchor and struct offset matched; '
                                   'globals decoded from the same RIP references.')
    return adapted
