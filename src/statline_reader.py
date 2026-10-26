"""External reads reproducing the verified live unit-card display getter chain."""
import math
import struct
from memory import ReadError
from statline import FIELDS

STAT_IDS=dict(armour=3,leadership=24,speed=55,melee_attack=16,melee_defence=20,
    weapon_strength=73,charge_bonus=9,spell_resistance=12,missile_resistance=13,
    fire_resistance=11,fire_weakness=15,physical_resistance=14,ward_save=10)
DIFFICULTY={'melee_attack','melee_defence','weapon_strength','charge_bonus'}


def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]


def game_round(value):
    return math.trunc(f32(value+(.5 if value>0 else -.5)))


class StatlineReader:
    def read_statline_rules(self,token):
        if not token or not self.profile.get('statline_fields'):return None
        if getattr(self,'_statline_token',None)!=token:
            self._statline_token=token;self._statline_rules=None
        if self._statline_rules is not None:return self._statline_rules
        try:
            context=self.ptr(self.g['statline_database_override'],nullable=True)
            if context:database=self.ptr(context+0x360)
            else:
                engine=self.ptr(self.g['statline_database_engine'])
                database=self.ptr(self.ptr(engine+0x78)+0x20)
            binding=self.profile['statline_fields']
            if self.read(database+binding['database_ready_offset'],1)!=b'\1':return None
            table=self.ptr(database+binding['fatigue_table_offset'])
            header=self.read(table+0xc,12);count,data=struct.unpack('<IQ',header)
            if count>1024:return None
            raw=self.read(data,count*8) if count else b'';result={}
            for offset in range(0,len(raw),8):
                row=struct.unpack_from('<Q',raw,offset)[0]
                value,state,key=struct.unpack('<fiQ',self.read(row+0x18,16))
                stat=self.uint(key+8)
                if not math.isfinite(value) or not 0<=value<=100 or not 0<=state<=5:return None
                result[(state,stat)]=value
            if self.read(table+0xc,12)!=header or (count and self.read(data,len(raw))!=raw):return None
            self._statline_rules=result
            return result
        except (ReadError,KeyError,struct.error):return None

    def statline_unit(self,address,values,block):
        binding=self.profile.get('statline_fields')
        if not binding:return None
        if values.get('cache_eligible') is not True or values.get('cache_active') is not True:return None
        result=dict.fromkeys(FIELDS)
        result.update(hp=values.get('hp_cached'),hp_max=values.get('hp_max_cached'),models=values.get('models'),models_max=values.get('models_initial'))
        try:
            current=self.ptr(address+binding['current_offset'])
            size=binding['stat_offset']+binding['stat_count']*binding['stat_stride']
            raw=self.read(current,size)
            unbreakable=self.flag(block[0x727-0x610])
            external=struct.unpack_from('<Q',raw,0x20)[0]
            external_bits=self.read(external,16) if external else bytes(16)

            def flag(index):
                word=index//64*8;mask=1<<(index%64)
                bits=lambda offset:struct.unpack_from('<Q',raw,offset+word)[0]
                return bool((bits(0x28)|struct.unpack_from('<Q',external_bits,word)[0]|((bits(0x38)|bits(0x48))&~bits(0x58)))&mask)

            def stat(index,integer=True):
                a,b,floor=struct.unpack_from('<fff',raw,binding['stat_offset']+index*binding['stat_stride'])
                if not all(math.isfinite(v) and abs(v)<1e8 for v in (a,b,floor)):return None
                return max(game_round(f32(a+b)),game_round(floor)) if integer else max(f32(a+b),floor)

            # Fatigue rows are read from the game's initialized database, so
            # live mods are respected without calling an initializer or getter.
            rules=getattr(self,'_statline_rules',None);state=values.get('fatigue_state')
            try:
                army=self.ptr(address+0x760);difficulty=self.ptr(army+0x38)
                difficulty_raw=self.read(difficulty,0x38)
                difficulty_flag=difficulty_raw[0];factor=struct.unpack_from('<f',difficulty_raw,0x34)[0]
                if difficulty_flag not in (0,1) or not math.isfinite(factor) or not 0<=factor<=100:factor=None
                elif difficulty_flag:factor=1.
            except ReadError:factor=None
            for key,index in STAT_IDS.items():
                if key=='speed':
                    try:
                        record=self.ptr(address+binding['record_offset']);land=self.ptr(record+0x500)
                        entity=self.ptr(land+0x108);flight=flag(0x20) or flag(0x21)
                        mount=self.ptr(land+0x110,nullable=True)
                        if mount:entity=self.ptr(mount+0x28)
                        else:
                            engine=self.ptr(land+0x180,nullable=True)
                            if engine:entity=self.ptr(engine+0x68);flight=False
                        base=struct.unpack('<f',self.read(entity+(0x24 if flight else 0x20),4))[0]
                        scalar=stat(index,False)
                        value=f32(f32(scalar*base)*binding['speed_display_factor']) if scalar is not None and math.isfinite(base) and 0<=base<10000 else None
                    except ReadError:value=None
                elif key=='armour':
                    a,b=stat(3),stat(26);value=a+b if a is not None and b is not None else None
                elif key=='melee_defence':
                    a,b=stat(20),stat(27);value=a+b if a is not None and b is not None else None
                elif key=='weapon_strength':
                    a,b=stat(17),stat(18);value=a+b if a is not None and b is not None else None
                elif key=='leadership' and unbreakable is True:value=100.
                else:value=stat(index)
                if key=='fire_weakness' and value is not None:value=-value
                if key=='leadership' and unbreakable is None:value=None
                if value is not None and not (key=='leadership' and unbreakable is True):
                    if rules is None or state not in range(6):value=None
                    else:
                        multiplier=rules.get((state,index))
                        immune=flag(0x50) if index==16 else flag(0x42) if index in (17,18) else False
                        if multiplier is not None and (multiplier>1 or not immune):value=f32(game_round(value)*multiplier)
                    if key in DIFFICULTY:
                        value=game_round(f32(math.trunc(value)*factor)) if value is not None and factor is not None and factor!=1 else value if factor is not None else None
                if value is not None:result[key]=max(-55 if key=='leadership' else 0,value)
            # Do not combine attributes read across a changing cache or identity.
            if self.ptr(address+binding['current_offset'])!=current or self.read(current,size)!=raw:return None
            if self.read(address+0x6f4,1)!=b'\1' or self.read(address+0x6fb,1)!=b'\1':return None
        except (ReadError,struct.error,ValueError,OverflowError):pass
        return result
