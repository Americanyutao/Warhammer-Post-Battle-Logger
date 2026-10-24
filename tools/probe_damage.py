"""One bounded read-only sample of the installed game; no game changes."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from memory import WindowsAPI,ProcessMemory,load_profiles,select_profile
from native_reader import LoggerReader
from resources import atomic_json


def main():
    api=WindowsAPI();pids=api.game_pids()
    result=dict(game_pids=pids,mode='read-only single sample')
    memory=None
    try:
        if len(pids)!=1:
            result['status']='Requires exactly one running game'
        else:
            memory=ProcessMemory(api,pids[0]);module=api.game_module(pids[0])
            profile=select_profile(memory,module,load_profiles(PROJECT/'profiles'))
            reader=LoggerReader(memory,module,profile)
            frame=reader.normalized(reader.sample())
            result.update(build=profile['name'],all_anchors_verified=True,battle_available=frame is not None)
            if frame:
                result.update(sim_s=frame['sim_s'],unreadable_units=frame['unreadable_units'],
                    units=[{k:u.get(k) for k in ('id','name','side','damage','gold_damage','damage_by_source','damage_sources_consistent')} for u in frame['units']])
            result['status']='sampled' if frame else 'No active battle roster'
    except Exception as error:
        result.update(status='unavailable',error=str(error))
    finally:
        if memory:memory.close()
    atomic_json(PROJECT/'build/live-damage-check.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
