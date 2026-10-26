"""External adapter. Normalized frames have no dependency on the memory reader."""
from dataclasses import dataclass
import math
import struct
from inspector_reader import InspectorReader, InspectorUnit, InspectorSample
from memory import ReadError
from result_types import TYPES, confirmed_label
from memory import valid_pointer
from statline_reader import StatlineReader


@dataclass(frozen=True)
class LoggerUnit(InspectorUnit):
    values: object = None


@dataclass(frozen=True)
class LoggerSample(InspectorSample):
    battle_phase: object = None


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


class LoggerReader(StatlineReader,InspectorReader):
    def effect_damage_scale(self, token):
        b=self.profile.get('effect_fields',{})
        offset=b.get('settings_damage_scale_offset')
        if offset is None or not token:return None
        try:
            settings=self.ptr(token[2]+self.profile['battle_clock_fields']['settings_offset'])
            value=struct.unpack('<f',self.read(settings+offset,4))[0]
            return value if finite(value) and value>=0 else None
        except (ReadError,KeyError):return None

    def battle_clock(self,token):
        b=self.profile.get('battle_clock_fields')
        if not b or not token:return None
        _,context,roster,_=token
        try:
            elapsed=struct.unpack('<f',self.read(roster+b['elapsed_offset'],4))[0]
            if not finite(elapsed) or not 0<=elapsed<=7*24*3600:return None
        except ReadError:return None
        limit=None
        try:
            override=self.read(context+b['override_flag_offset'],1)[0]
            if override==0:
                settings=self.ptr(roster+b['settings_offset'])
                value=struct.unpack('<f',self.read(settings+b['limit_offset'],4))[0]
                if finite(value) and 0<value<=7*24*3600:limit=value
            elif override==1:
                settings=self.ptr(context+b['override_pointer_offset'])
                value=self.uint(settings+b['override_limit_ms_offset'])//1000
                if 0<value<=7*24*3600:limit=value
        except ReadError:pass
        return dict(source='native_battle_ui_clock',elapsed_s=elapsed,limit_s=limit,
            remaining_s=max(0.,limit-elapsed) if limit is not None else None)

    def battle_phase(self, token):
        binding = self.profile.get('workspace_fields')
        return self.uint(token[2]+binding['phase_offset']) if token and binding else None

    def sample(self):
        token = self.roots()
        phase = self.battle_phase(token)
        self.read_statline_rules(token)
        sample = super().sample()
        if sample.token and sample.token != token:
            raise ReadError('Battle phase changed during sampling; retrying.')
        return LoggerSample(**vars(sample), battle_phase=phase if sample.token else None)

    def battle_result(self, token, phase=None):
        """Never infer victory from casualty totals or a vanished roster."""
        b = self.profile.get('workspace_fields')
        if not b: return None
        try:
            _, context, roster, _ = token
            if phase is None: phase = self.battle_phase(token)
            if phase != 8: return None
            result = self.ptr(roster+b['result_offset'])
            winner = struct.unpack('<i',self.read(result+b['result_winner_offset'],4))[0]
            local_index = self.uint(context+b['local_alliance_index_offset'])
            if local_index >= self.MAX_ALLIANCES: return None
            alliances = self.ptr(context+b['local_alliances_offset'])
            local = struct.unpack('<i',self.read(alliances+4+local_index*8,4))[0]
            if not (-1 <= winner < self.MAX_ALLIANCES and 0 <= local < self.MAX_ALLIANCES): return None
            outcome = 'Draw' if winner == -1 else 'Victory' if winner == local else 'Defeat'
            classification = self.result_type(result,local,outcome)
            if self.uint(roster+b['phase_offset']) != phase: return None
            if self.ptr(roster+b['result_offset']) != result: return None
            if struct.unpack('<i',self.read(result+b['result_winner_offset'],4))[0] != winner: return None
            return dict(outcome=outcome,**classification,
                        winner_alliance_index=winner,local_alliance_index=local,phase='Results',source='native_result',
                        result_layout='result_context_slot_8')
        except ReadError: return None

    def result_type(self, result, alliance, outcome):
        b = self.profile.get('result_type_fields')
        values = dict(result_type_code=None,result_type_record_code=None,result_type_key=None,
                      result_type_label=None,result_type_confirmed=False)
        if not b: return values
        try:
            entries = self.ptr(result+b['alliance_entries_offset'])
            address = entries+alliance*b['alliance_stride']+b['type_offset']
            raw = self.read(address,20)
            code = struct.unpack_from('<i',raw)[0]
            record = struct.unpack_from('<Q',raw,b['record_offset']-b['type_offset'])[0]
            values['result_type_code'] = code
            # The DB record stores an interned key at +10 and its parsed enum
            # at +18. Compare enums; do not interpret the interned key as a string.
            record_code = struct.unpack('<i',self.read(record+b['record_type_offset'],4))[0] if record else None
            values['result_type_record_code'] = record_code
            key = TYPES[record_code][0] if record_code in TYPES else None
            values['result_type_key'] = key
            label = confirmed_label(code,key,outcome) if record_code == code else None
            if self.ptr(result+b['alliance_entries_offset']) != entries or self.read(address,20) != raw:
                return dict(values,result_type_key=None)
            if label:
                values.update(result_type_label=label,result_type_confirmed=True)
        except (ReadError,UnicodeError): pass
        return values

    def fatigue_rules(self, sample, native_ids):
        if not self.profile.get('workspace_fields'): return None
        # Read initialized rules via the same first-entity path used by the
        # fatigue clamp. No native functions are called and no models are tracked.
        candidates=sorted(sample.units,key=lambda u:(u.alive is not True,not (u.values.get('models') or 0)))[:4]
        for unit in candidates:
            try:
                native = native_ids.get(unit.uid)
                if not native: continue
                count = self.uint(native+0x184)
                if not 0 < count <= 10000: continue
                entities = self.ptr(native+0x188)
                entity = self.ptr(entities)
                rules = self.ptr(entity+0x58)
                for offset in (0x440,8,0x430,0x20,0x187c8): rules = self.ptr(rules+offset)
                raw = self.read(rules+0x830,0x274)
                thresholds = [struct.unpack_from('<i',raw,i*0x68)[0] for i in range(7)]
                if thresholds[0] < 0 or thresholds[-1] <= 0 or thresholds[-1] > 100000000: continue
                if any(a >= b for a,b in zip(thresholds,thresholds[1:])): continue
                return dict(thresholds=thresholds,maximum=thresholds[-1],source='native_fatigue_rules')
            except ReadError: continue
        return None

    def byte_string(self, address, maximum=512):
        header=self.read(address,16)
        word=struct.unpack_from('<Q',header,8)[0]
        inline=word & 0xf000000000000000 == 0x8000000000000000
        count=(word>>56)&0xf if inline else struct.unpack_from('<I',header)[0]
        if count==0:return ''
        if count>maximum or (inline and count>14):raise ReadError('Invalid byte string length.')
        return (header[:count] if inline else self.read(word,count)).decode('utf-8')

    def unit_portrait_path(self, sample, unit_key=None, active=False):
        binding=self.profile.get('unit_identity')
        if not binding:return None
        cache=getattr(self,'_portrait_paths',None)
        if cache is None:self._portrait_paths=cache={}
        identity=(sample.uid,sample.address,sample.result,unit_key)
        if identity in cache:return cache[identity]
        try:
            setup=self.ptr(sample.address+binding['setup_offset'])
            path=self.byte_string(setup+binding['portrait_offset'])
            if path or active:
                if len(cache)<4096:cache[identity]=path or None
            return path or None
        except (ReadError,UnicodeError):return None

    def unit_record_key(self, address):
        binding=self.profile.get('unit_identity')
        if not binding:return None
        try:
            record=self.ptr(address+binding['record_offset'])
            cache=getattr(self,'_record_keys',None)
            if cache is None:self._record_keys=cache={}
            if record in cache:return cache[record]
            key=self.byte_string(record+binding['key_offset'],256)
            if not key:return None
            if not all(c.isalnum() or c in '_-.' for c in key):return None
            if len(cache)<4096:cache[record]=key
            return key
        except (ReadError,UnicodeError):return None

    def active_effects(self, address, eligible, active):
        """Read the event-maintained UI list, including passives. None != empty.

        The game's add/remove callbacks maintain this list without a selection
        gate. UI-hidden internal phases are excluded by the game itself.
        Never call native code or infer continued presence between observations.
        """
        b=self.profile.get('effect_fields')
        if not b or eligible is not True or active is not True:return None
        try:
            header=self.read(address+b['count_offset'],12)
            count,data=struct.unpack('<IQ',header)
            if count>256 or (count and not valid_pointer(data)):return None
            raw=self.read(data,count*b['stride']) if count else b''
            result=[]
            for offset in range(0,len(raw),b['stride']):
                key_address,phase,ability=struct.unpack_from('<QQQ',raw,offset)
                if not valid_pointer(phase):return None
                phase_key=self.byte_string(phase+b['phase_key_offset'],256)
                ability_key=self.byte_string(key_address,256)
                if not phase_key or not all(c.isalnum() or c in '_-.' for c in phase_key):return None
                if not ability_key or not all(c.isalnum() or c in '_-.' for c in ability_key):return None
                polarity=struct.unpack('<i',self.read(phase+b['phase_polarity_offset'],4))[0]
                # Match CcoBattleUnitEffect.Name's precedence exactly.
                name_pointer=self.ptr(ability+b['ability_name_offset'],nullable=True) if ability else 0
                if not ability:name_pointer=self.ptr(phase+b['phase_name_offset'],nullable=True)
                name=self.unicode_string(self.read(name_pointer,16)) if name_pointer else ability_key
                intensity=struct.unpack_from('<f',raw,offset+b['intensity_offset'])[0] if 'intensity_offset' in b else None
                result.append(dict(key=ability_key+':'+phase_key,name=name or ability_key,
                    polarity={0:'positive',1:'negative'}.get(polarity,'other'),
                    instance_id=f'effect-{key_address:x}',
                    intensity=intensity if finite(intensity) and intensity>=0 else None))
            # A changed array/entry is an unknown reading, never false removal.
            if header!=self.read(address+b['count_offset'],12):return None
            if count and raw!=self.read(data,len(raw)):return None
            if self.read(address+0x6f4,1)!=b'\x01' or self.read(address+0x6fb,1)!=b'\x01':return None
            return result
        except (ReadError,UnicodeError,ValueError):return None

    def decorate_unit(self, sample, block):
        decorated = super().decorate_unit(sample, block)
        values = {}
        values['unit_key'] = self.unit_record_key(sample.address)
        extra = self.profile.get('workspace_fields')
        values.update(character_level=None,has_character_rank=None,fatigue_points=None,fatigue_state_native=None,
                      left_battlefield=None,awaiting_order_after_rally_raw=None)
        if extra:
            try:
                setup = self.ptr(sample.address+extra['setup_offset'])
                rank, rank_type = struct.unpack('<II',self.read(setup+extra['character_rank_offset'],8))
                values['has_character_rank'] = rank_type < 7 and bool((0x5a >> rank_type) & 1)
                if values['has_character_rank'] and 0 < rank <= 10000: values['character_level'] = rank
            except ReadError: pass
        for key, binding in self.profile['logger_fields'].items():
            value = struct.unpack_from('<' + ('B' if binding['kind'] == '?' else binding['kind']),
                                       block, binding['offset'] - 0x610)[0]
            if binding['kind'] == '?': value = self.flag(value)
            elif not finite(value) or value < 0: value = None
            if ('fraction' in key or key == 'health_percent') and value is not None and value > 1.01:
                value = None
            values[key] = value
        # Cached combat fields are refreshed only for eligible active UI units.
        values['cache_eligible'] = self.flag(block[0x6f4 - 0x610])
        values['cache_active'] = self.flag(block[0x6fb - 0x610])
        values['active_effects'] = self.active_effects(sample.address,values['cache_eligible'],values['cache_active'])
        values['portrait_path'] = self.unit_portrait_path(sample,values['unit_key'],values['cache_active'] is True)
        values['hidden_raw'] = self.flag(block[self.o['unit_hidden'] - 0x610])
        values['damage'] = values['kills'] = values['gold_damage'] = None
        values['damage_by_source'] = None
        values['damage_sources_consistent'] = None
        values.update({key:None for key in self.profile.get('terminal_fields',{})})
        if sample.result:
            try:
                raw = self.read(sample.result + 0x20, 0xec)
                for key, offset in self.profile.get('terminal_fields',{}).items():
                    values[key] = struct.unpack_from('<I',raw,offset-0x20)[0]
                values['damage'] = struct.unpack_from('<I', raw, 0xa4)[0]
                gold = struct.unpack_from('<f', raw, 0xa8)[0]
                if finite(gold) and 0 <= gold < 2**63:
                    rounded = struct.unpack('<f', struct.pack('<f', gold + .5))[0]
                    values['gold_damage'] = int(rounded) if rounded < 2**63 else None
                values['kills'] = struct.unpack_from('<I', raw, 0xe8)[0]
                if extra: values['left_battlefield'] = self.flag(raw[extra['left_battlefield_offset']-0x20])
                accounting = self.profile.get('damage_accounting')
                if accounting:
                    counts = struct.unpack_from('<18I', raw)
                    categories, relationships = accounting['categories'], accounting['relationships']
                    # Reject a torn snapshot instead of displaying a false breakdown.
                    valid = (sum(counts[::3]) & 0xffffffff) == values['damage']
                    values['damage_sources_consistent'] = valid
                    if valid:
                        values['damage_by_source'] = {c:{r:counts[i*3+j] for j,r in enumerate(relationships)}
                                                      for i,c in enumerate(categories)}
            except ReadError:
                pass
        values['healing_budget_remaining_hp'] = None
        values['healing_budget_unlimited'] = None
        values['spawned'] = None
        native = None
        try:
            native = self.ptr(sample.address + self.o['unit_adapter'])
            values['spawned'] = self.flag(self.read(native + 0x1b8, 1)[0])
            if extra and sample.alive is True:
                state, points = struct.unpack('<II',self.read(native+extra['fatigue_offset'],8))
                if points <= 100000000: values['fatigue_points'] = points
                if state <= 5: values['fatigue_state_native'] = state
        except ReadError:
            pass
        try:
            binding = self.profile.get('healing_budget')
            if binding and native:
                stats = self.ptr(native + binding['native_stats_offset'])
                raw = self.read(stats + binding['remaining_offset'], 5)
                values['healing_budget_unlimited'] = bool(raw[4] & 1)
                if not values['healing_budget_unlimited']:
                    values['healing_budget_remaining_hp'] = struct.unpack_from('<I', raw)[0]
        except ReadError:
            pass
        values.update(primary_ammo=None, primary_ammo_start=None, secondary_ammo_start=None, primary_ammo_max=None, secondary_ammo=None,
                      secondary_ammo_max=None, leadership=None)
        report_fields = self.profile.get('report_fields')
        if native and report_fields:
            try:
                raw = self.read(native + report_fields['primary_ammo_offset'], 28)
                values['primary_ammo'], values['primary_ammo_start'], values['primary_ammo_max'] = struct.unpack_from('<III', raw)
                values['secondary_ammo'], values['secondary_ammo_start'], values['secondary_ammo_max'] = struct.unpack_from('<III', raw, 16)
            except ReadError:
                pass
        if report_fields and sample.alive is not False:
            try:
                morale = self.ptr(sample.address + report_fields['morale_adapter_offset'])
                values['leadership'] = struct.unpack('<i', self.read(morale + report_fields['leadership_offset'], 4))[0]
            except ReadError:
                pass
        try:
            details = self.ptr(sample.address + 0x1a8)
            regen = struct.unpack('<f', self.read(details + 0x200, 4))[0]
            values['regen_base_raw'] = regen if finite(regen) and regen >= 0 else None
        except ReadError:
            values['regen_base_raw'] = None
        values['healing_ceiling_fraction_raw'] = decorated.healing_cap
        values['xyz'] = decorated.xyz
        values['alive'] = sample.alive
        if values['cache_eligible'] is not True or values['cache_active'] is not True:
            for key in self.profile['logger_fields']: values[key] = None
            values['xyz'] = values['healing_ceiling_fraction_raw'] = values['regen_base_raw'] = None
        # IsAlive reports active native entity arrays, not a verified death
        # reason. Never manufacture zero HP/model readings when it becomes false.
        budget, hp = values['healing_budget_remaining_hp'], values.get('hp_cached')
        maximum = values.get('hp_max_cached')
        # This bypasses the UI's additional multi-model ceiling clamp. It is
        # a healing-budget ceiling, not a promise of resurrectable model HP.
        values['healing_budget_ceiling_hp'] = hp + budget if hp is not None and budget is not None else None
        values['healing_budget_remaining_fraction'] = budget / maximum if budget is not None and maximum else None
        values['shattered'] = values.get('morale_state') == 7 if values.get('morale_state') is not None else None
        values['grounded'] = not values['flying'] if isinstance(values.get('flying'), bool) else None
        if extra and sample.alive is True and values['cache_active'] is True and values['cache_eligible'] is True:
            values['awaiting_order_after_rally_raw'] = self.flag(block[extra['awaiting_rally_offset']-0x610])
        values['statline']=self.statline_unit(sample.address,values,block)
        return LoggerUnit(**vars(decorated), values=values)

    def normalized(self, sample):
        """Mod collectors can emit this schema directly; readers remain replaceable."""
        if sample.token is None: return None
        # Reuse the release meter's verified native alliance LOS list in both directions.
        vision, native_ids, alliances = {}, {}, {a.alliance for a in sample.armies}
        for unit in sample.units:
            try:
                native = self.ptr(unit.address + self.o['unit_adapter'])
                native_ids[unit.uid] = native
                if unit.alliance not in vision:
                    army = self.ptr(native + self.o['native_unit_army'])
                    alliance = self.ptr(army + self.o['army_alliance'])
                    seen = set(self.vector(alliance, self.o['visible_count'], self.o['visible_data'], self.MAX_UNITS))
                    vision[unit.alliance] = (alliance, seen)
                if self.ptr(unit.address + self.o['unit_adapter']) != native: native_ids.pop(unit.uid, None)
            except ReadError:
                pass
        for index, (alliance, seen) in list(vision.items()):
            try:
                if set(self.vector(alliance, self.o['visible_count'], self.o['visible_data'], self.MAX_UNITS)) != seen:
                    del vision[index]
            except ReadError:
                del vision[index]
        units = []
        for unit in sample.units:
            values = dict(unit.values)
            opponents = alliances - {unit.alliance}
            native = native_ids.get(unit.uid)
            visible = None
            if native and opponents and opponents.issubset(vision) and values['hidden_raw'] is not None:
                visible = values['hidden_raw'] is False and any(native in vision[a][1] for a in opponents)
            values['out_of_opponents_vision'] = not visible if visible is not None else None
            # UID reuse starts a separate incarnation; this identity is only battle-local.
            units.append(dict(id=f'{unit.uid}:{unit.address:x}:{unit.result:x}', uid=unit.uid,
                name=unit.name, army=str(unit.army), alliance=unit.alliance,
                controlled=unit.owner == sample.controller,
                side='Allied' if unit.alliance == sample.player_alliance else 'Enemy', **values))
        armies = [dict(id=str(a.address), alliance=a.alliance,
            side='Allied' if a.alliance == sample.player_alliance else 'Enemy',
            current=a.current, reserve=a.reserve, recharge=a.recharge_seconds_per_point,
            recharge_per_second=a.recharge_per_second, recharge_seconds_per_point=a.recharge_seconds_per_point,
            maximum=a.maximum) for a in sample.armies]
        if self.roots() != sample.token:
            raise ReadError('Battle changed while reading visibility.')
        phase = self.battle_phase(sample.token)
        if phase != sample.battle_phase: raise ReadError('Battle phase changed while normalizing; retrying.')
        result, rules = self.battle_result(sample.token,phase), self.fatigue_rules(sample,native_ids)
        clock=self.battle_clock(sample.token)
        effect_damage_scale=self.effect_damage_scale(sample.token)
        if self.roots()!=sample.token:raise ReadError('Battle changed while reading report fields and the battle clock.')
        if self.battle_phase(sample.token)!=phase:raise ReadError('Battle phase changed while reading the battle clock.')
        return dict(schema=1, kind='sample', sim_s=clock['elapsed_s'] if clock else None,
                    model_s=sample.game_ms/1000 if sample.game_ms is not None else None,battle_clock=clock,
                    units=units, armies=armies, unreadable_units=sample.errors,
                    battle_phase=phase,battle_result=result,fatigue_rules=rules,effect_damage_scale=effect_damage_scale)
