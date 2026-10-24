"""One supported-build, read-only report-field sample. Never starts a recorder."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from memory import WindowsAPI,ProcessMemory,load_profiles,select_profile
from native_reader import LoggerReader
from resources import atomic_json


def main():
    api=WindowsAPI();pids=api.game_pids()
    result=dict(mode='one read-only sample',pids=pids);memory=None
    try:
        if len(pids)!=1:result['status']='Requires exactly one running game'
        else:
            memory=ProcessMemory(api,pids[0]);module=api.game_module(pids[0])
            profile=select_profile(memory,module,load_profiles(P/'profiles'))
            reader=LoggerReader(memory,module,profile)
            frame=reader.normalized(reader.sample())
            result.update(anchors_verified=True,battle_available=frame is not None)
            if frame:
                result.update(sim_s=frame['sim_s'],fatigue_rules=frame['fatigue_rules'],battle_result=frame['battle_result'],
                    units=[{k:u[k] for k in ('name','side','fatigue_state','fatigue_points','has_character_rank',
                        'character_level','left_battlefield','awaiting_order_after_rally_raw')} for u in frame['units']])
    except Exception as error:result['error']=str(error)
    finally:
        if memory:memory.close()
    atomic_json(P/'build/live-workspace-check.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
