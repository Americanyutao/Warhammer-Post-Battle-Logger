"""Verified native battle inspector fields on top of the standalone roster reader."""
from dataclasses import dataclass
import math
import struct
from typing import Optional
from memory import ReadError
from roster import NativeReader, UnitSample, BattleSample, ChangingBattle


@dataclass(frozen=True)
class ArmySample:
    address: int
    alliance: int
    owner: int
    current: Optional[float] = None
    reserve: Optional[float] = None
    recharge_per_second: Optional[float] = None
    maximum: Optional[float] = None
    errors: tuple = ()
    recharge_seconds_per_point: Optional[float] = None


@dataclass(frozen=True)
class InspectorUnit(UnitSample):
    xyz: Optional[tuple] = None
    healing_cap: Optional[float] = None
    field_errors: tuple = ()


@dataclass(frozen=True)
class InspectorSample(BattleSample):
    armies: tuple = ()


def nonnegative(value, name, errors):
    if math.isfinite(value) and value >= 0:
        return value
    errors.append(name + ' is unavailable')
    return None


class InspectorReader(NativeReader):
    def sample(self):
        self.armies = []
        self.seen_armies = {}
        battle = super().sample()
        self.diagnostic['inspector_field_errors'] = sum(len(a.errors) for a in self.armies) + sum(len(u.field_errors) for u in battle.units)
        return InspectorSample(**vars(battle), armies=tuple(self.armies))

    def observe_army(self, address, alliance, owner):
        if address in self.seen_armies:
            if self.seen_armies[address] != alliance:
                raise ChangingBattle('Army alliance changed during sampling.')
            return
        self.seen_armies[address] = alliance
        current = reserve = maximum = rate = interval = None
        errors = []
        try:
            raw = self.read(address + self.o['army_magic_current'], 20)
            current = nonnegative(struct.unpack_from('<f', raw, 0)[0], 'Current magic', errors)
            maximum = nonnegative(struct.unpack_from('<f', raw, 4)[0], 'Maximum magic', errors)
            offset = self.o['army_magic_recharge_rate']-self.o['army_magic_current']
            rate = nonnegative(struct.unpack_from('<f', raw, offset)[0], 'Magic recharge rate', errors)
            reserve = nonnegative(struct.unpack_from('<f', raw, 16)[0], 'Magic reserves', errors)
            # The CCO getter's reciprocal is seconds/point despite its name.
            # The 2026-10-22 capture shows 10 -> one point/10s and 6.25 -> one/6.25s.
            if rate is not None and rate > 0:
                interval = struct.unpack('<f', struct.pack('<f', 1.0 / rate))[0]
                if not math.isfinite(interval):interval = None
        except (ReadError, OverflowError) as error:
            errors.append(str(error))
        self.armies.append(ArmySample(address, alliance, owner, current, reserve, rate, maximum, tuple(errors),interval))

    def decorate_unit(self, sample, block):
        errors = []
        cap = nonnegative(struct.unpack_from('<f', block, self.o['unit_healing_cap'] - 0x610)[0], 'Healing cap', errors)
        xyz = None
        try:
            xyz = struct.unpack('<fff', self.read(sample.address + self.o['unit_position'], 12))
            if not all(math.isfinite(value) for value in xyz):
                xyz = None
                errors.append('Unit coordinates are unavailable')
        except ReadError as error:
            errors.append(str(error))
        return InspectorUnit(**vars(sample), xyz=xyz, healing_cap=cap, field_errors=tuple(errors))
