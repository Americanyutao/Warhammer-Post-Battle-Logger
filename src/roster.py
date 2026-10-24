"""Native roster and Unicode names, adapted from the verified damage-meter reader."""
from __future__ import annotations
from dataclasses import dataclass
import struct
from typing import Optional
from memory import ReadError, relocated, valid_pointer


class ChangingBattle(ReadError):
    pass


@dataclass(frozen=True)
class UnitSample:
    uid: int
    address: int
    result: int
    army: int
    alliance: int
    owner: int
    name: str
    alive: Optional[bool]
    visible: Optional[bool]


@dataclass(frozen=True)
class BattleSample:
    token: Optional[tuple] = None
    units: tuple = ()
    controller: Optional[int] = None
    player_alliance: Optional[int] = None
    game_ms: Optional[int] = None
    errors: int = 0
    detail: str = 'Waiting for a battle.'


class NativeReader:
    MAX_ALLIANCES = 16
    MAX_ARMIES = 64
    MAX_UNITS = 2048

    def __init__(self, memory, module, profile):
        self.memory, self.module, self.profile = memory, module, profile
        self.o = profile['offsets']
        self.g = {name: relocated(module, profile, value) for name, value in profile['globals'].items()}
        self.names = {}
        self.last_token = None
        self.last_game_ms = None
        self.diagnostic = {}

    def read(self, address, size):
        data = self.memory.read(address, size)
        if len(data) != size:
            raise ReadError('Short game memory read.')
        return data

    def ptr(self, address, nullable=False):
        value = struct.unpack('<Q', self.read(address, 8))[0]
        if nullable and value == 0:
            return 0
        if not valid_pointer(value):
            raise ReadError('Battle data is not currently available.')
        return value

    def uint(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def vector(self, address, count_offset, data_offset, maximum):
        # Both fields are adjacent in the native dynamic-array headers.
        start = self.read(address + count_offset, 12)
        count = struct.unpack_from('<I', start)[0]
        data = struct.unpack_from('<Q', start, data_offset - count_offset)[0]
        if count > maximum:
            raise ReadError('Battle roster exceeds the validated read limit.')
        if count == 0:
            return ()
        if not valid_pointer(data):
            raise ReadError('Battle roster has no readable pointer array.')
        values = struct.unpack('<' + 'Q' * count, self.read(data, count * 8))
        if start != self.read(address + count_offset, 12):
            raise ChangingBattle('The battle roster changed during sampling.')
        if any(not valid_pointer(value) for value in values):
            raise ChangingBattle('A battle roster entry is being replaced.')
        return values

    def unicode_string(self, header):
        # Result-unit Name is CA UniString (UTF-16), not the byte-string variant.
        # 1404d9e50 / 1404d9f50 count UTF-16 code units and copy length * 2 bytes.
        if len(header) != 16:
            raise ReadError('Invalid game string header.')
        word = struct.unpack_from('<Q', header, 8)[0]
        if word & 0xf000000000000000 == 0x8000000000000000:
            units = (word >> 56) & 0xf
            if units > 2:
                raise ReadError('Invalid inline Unicode string.')
            raw = header[:units * 2]
        else:
            units = struct.unpack_from('<I', header)[0]
            if units == 0:
                return ''
            if units > 1024 or not valid_pointer(word):
                raise ReadError('Game unit name is unavailable.')
            raw = self.read(word, units * 2)
        try:
            value = raw.decode('utf-16-le')
        except UnicodeError as error:
            raise ReadError('Game unit name encoding is unavailable.') from error
        if any(ord(char) < 32 for char in value):
            raise ReadError('Game unit name contains invalid text.')
        return value

    @staticmethod
    def flag(raw):
        return bool(raw) if raw in (0, 1) else None

    def roots(self):
        enabled = self.read(self.g['ui_enabled'], 1)[0]
        self.diagnostic['ui_enabled'] = enabled
        if not enabled:
            return None
        engine = self.ptr(self.g['ui_engine'], nullable=True)
        self.diagnostic['engine'] = hex(engine)
        if not engine:
            return None
        context = self.ptr(engine + self.o['battle_context'], nullable=True)
        local_army = self.ptr(engine + self.o['local_army'], nullable=True)
        self.diagnostic.update(context=hex(context), local_army=hex(local_army))
        if not context or not local_army:
            return None
        roster = self.ptr(context + self.o['roster'], nullable=True)
        self.diagnostic['roster'] = hex(roster)
        if not roster:
            return None
        return engine, context, roster, local_army

    def game_time(self):
        try:
            engine = self.ptr(self.g['script_engine'], nullable=True)
            return self.uint(engine + self.o['script_time_ms']) if engine else None
        except ReadError:
            return None

    def sample(self):
        self.diagnostic = {'stage': 'battle_roots', 'unreadable_units': [], 'name_failures': []}
        roots = self.roots()
        if roots is None:
            self.names.clear()
            self.last_token = None
            self.last_game_ms = None
            return BattleSample()
        engine, context, roster, local_army = roots
        token = engine, context, roster, local_army
        game_ms = self.game_time()
        rollback = game_ms is not None and self.last_game_ms is not None and game_ms < self.last_game_ms
        if token != self.last_token or rollback:
            self.names.clear()
            self.last_token = token
        self.last_game_ms = game_ms
        controller = self.uint(local_army + self.o['owner'])
        self.diagnostic.update(stage='alliance_roster', controller=controller)
        alliances = self.vector(roster, self.o['alliance_count'], self.o['alliance_data'], self.MAX_ALLIANCES)
        if not alliances:
            return BattleSample(detail='Waiting for the battle roster.')
        units, errors, seen_addresses, ids = [], 0, set(), set()
        player_alliance = None
        self.diagnostic['alliance_count'] = len(alliances)
        for alliance_index, alliance in enumerate(alliances, 1):
            self.diagnostic.update(stage='army_roster', alliance=alliance_index)
            armies = self.vector(alliance, self.o['army_count'], self.o['army_data'], self.MAX_ARMIES)
            for army in armies:
                owner = self.uint(army + self.o['owner'])
                self.observe_army(army, alliance_index, owner)
                if army == local_army or owner == controller:
                    if player_alliance is not None and player_alliance != alliance_index:
                        raise ChangingBattle('Player ownership changed during sampling.')
                    player_alliance = alliance_index
                for count_field, data_field in [('unit_count', 'unit_data'), ('reserve_count', 'reserve_data')]:
                    self.diagnostic.update(stage=count_field, army=hex(army))
                    addresses = self.vector(army, self.o[count_field], self.o[data_field], self.MAX_UNITS)
                    for unit in addresses:
                        if unit in seen_addresses:
                            continue
                        seen_addresses.add(unit)
                        if len(seen_addresses) > self.MAX_UNITS:
                            raise ReadError('The battle has too many roster entries for this prototype.')
                        try:
                            sample = self.unit(unit, army, alliance_index, owner)
                        except ReadError as error:
                            errors += 1
                            if len(self.diagnostic['unreadable_units']) < 12:
                                self.diagnostic['unreadable_units'].append({'address': hex(unit), 'error': str(error)})
                            continue
                        if sample.uid in ids:
                            raise ChangingBattle('A unit identity changed during sampling.')
                        ids.add(sample.uid)
                        units.append(sample)
        if self.roots() != roots or self.uint(local_army + self.o['owner']) != controller:
            raise ChangingBattle('The battle changed during sampling.')
        if player_alliance is None:
            raise ReadError('The player army could not be identified yet.')
        self.diagnostic.update(stage='complete', accepted_units=len(units), unreadable_count=errors)
        return BattleSample(token, tuple(units), controller, player_alliance,
                            game_ms, errors, 'Live native battle counters')

    def unit(self, address, army, alliance, owner):
        # One bounded read covers identity, cached UI state, and both backing pointers.
        start = 0x610
        block = self.read(address + start, 0x158)
        uid = struct.unpack_from('<I', block, self.o['unit_id'] - start)[0]
        adapter = struct.unpack_from('<Q', block, self.o['unit_adapter'] - start)[0]
        unit_army = struct.unpack_from('<Q', block, self.o['unit_army'] - start)[0]
        if unit_army != army:
            raise ChangingBattle('A unit is moving between armies.')
        alive = self.flag(block[self.o['unit_alive'] - start])
        visible = self.flag(block[self.o['unit_visible'] - start])
        result = 0
        name = 'Unit ' + str(uid)
        raw = b''
        try:
            if valid_pointer(adapter):
                result = self.ptr(adapter + self.o['adapter_result'], nullable=True)
            if result:
                # Name loss must not suppress verified coordinates or healing caps.
                key = uid, result
                cached = self.names.get(key)
                if cached:
                    name = cached
                else:
                    raw = self.read(result + self.o['result_name'], 32)
                    name = self.unicode_string(raw[16:32]) or self.unicode_string(raw[:16]) or name
                    if name != 'Unit ' + str(uid):
                        self.names[key] = name
        except ReadError as error:
            if len(self.diagnostic.get('name_failures', [])) < 5:
                self.diagnostic.setdefault('name_failures', []).append({'unit_id': uid, 'error': str(error), 'headers': raw.hex()})
        sample = self.decorate_unit(UnitSample(uid, address, result, army, alliance, owner, name, alive, visible), block)
        if self.uint(address + self.o['unit_id']) != uid or self.read(address + self.o['unit_adapter'], 16) != block[0x148:0x158]:
            raise ChangingBattle('A unit was replaced during sampling.')
        if result and self.ptr(adapter + self.o['adapter_result'], nullable=True) != result:
            raise ChangingBattle('A result record changed during sampling.')
        return sample

    def observe_army(self, address, alliance, owner):
        pass

    def decorate_unit(self, sample, block):
        return sample
