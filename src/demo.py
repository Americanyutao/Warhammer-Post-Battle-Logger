"""Deterministic synthetic workload, independent of game memory."""
import argparse
import copy
import math
from pathlib import Path
import time
from aggregate import Battle
from logfile import LogWriter, load_key
from report import convert
from resources import process_resources, atomic_json


def frames(units=80, seconds=60, step=1.):
    for tick in range(int(seconds/step)+1):
        t=tick*step
        rows=[]
        for i in range(units):
            firing=i%3==0 and 5<t<seconds*.8
            damage=int(max(0,t-5)*(13+i%17))
            sources={c:dict(enemy=damage if c==('missile' if i%3==0 else 'melee') else 0,self=0,ally=0)
                     for c in ('ability','melee','missile','charge','melee_collision','other')}
            hp=max(0,8000-damage*.6)
            buffed=2<t<seconds*.8
            rows.append(dict(id=str(i), uid=i, name=('Zombies' if i%2 else 'Skeleton Spearmen')+f' {i+1}',
                army=str(i%2), alliance=i%2+1, side='Allied' if i%2==0 else 'Enemy', controlled=i%2==0,
                active_effects=([dict(key='synthetic-buff',name='Example buff',polarity='positive')] if 2<t<seconds*.8 else [])+([dict(key='synthetic-debuff',name='Example debuff',polarity='negative')] if seconds*.4<t<seconds*.9 else []),
                statline=dict(hp=int(hp),hp_max=8000,models=max(0,120-int((8000-hp)/67)),models_max=120,
                    armour=45 if buffed else 15,leadership=60,speed=50,melee_attack=95 if buffed else 75,
                    melee_defence=50,weapon_strength=410,charge_bonus=35,spell_resistance=20,
                    missile_resistance=10,fire_resistance=0,fire_weakness=20,physical_resistance=15,ward_save=5),
                damage=damage, damage_by_source=sources, damage_sources_consistent=True,
                gold_damage=int(damage*.18), kills=int(damage/55), hp_cached=int(hp),
                hp_max_cached=8000, models=max(0,120-int((8000-hp)/67)), models_initial=120,
                barrier_hp=0, barrier_max=0, primary_ammo_fraction=max(0,1-t/seconds) if i%3==0 else 0,
                secondary_ammo_fraction=0., healing_ceiling_fraction_raw=1.75-(8000-hp)/8000,
                regen_base_raw=0., spawned=i%19==0 and i>2, alive=hp>0, firing=firing,
                melee=not firing and t>10, idle=t<=5, walking=5<t<10, running=False,
                flying=False, grounded=True, routing=False, shattered=False, withdrawing=False, under_missile=t>5,
                out_of_opponents_vision=t<5, fatigue_state=min(5,int(t/30)), morale_state=0,
                xyz=[i*5+math.sin(t/20)*t,0,i*3+math.cos(t/20)*t]))
        yield dict(schema=1,kind='sample',sim_s=t,units=rows,
            armies=[dict(id=str(i),alliance=i+1,side='Allied' if i==0 else 'Enemy',
                current=max(0,30-t*.05),reserve=max(0,80-t*.2),recharge=5.,
                recharge_per_second=.2,recharge_seconds_per_point=5.,maximum=100) for i in range(2)],
            performance=dict(read_ms=0,read_calls=0,bytes_read=0))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--units',type=int,default=80)
    parser.add_argument('--seconds',type=int,default=600)
    parser.add_argument('--step',type=float,default=1.)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    key=load_key(root/'build/demo.key',create=True)
    # Unique filename; never overwrite a game capture.
    path=root/'build'/f'demo-{time.time_ns()}.wh3log'
    wall,cpu=time.perf_counter(),time.process_time()
    b=Battle(keep_history=False,max_gap=80)
    writer=LogWriter(path,key,dict(source='synthetic',maximum_interval_s=80,started_pacific='Synthetic workload · not live game data'))
    count=0
    for frame in frames(args.units,args.seconds,args.step):
        b.observe(frame);writer.write(frame);count+=1
    writer.close(dict(reason='synthetic_completed',dropped_records=0))
    elapsed=time.perf_counter()-wall
    summary=dict(source='synthetic; no game memory reads or game frame-time measurement',units=args.units,
        samples=count,simulated_seconds=args.seconds,wall_seconds=elapsed,process_cpu_seconds=time.process_time()-cpu,
        ms_per_sample=elapsed/max(1,count)*1000,encrypted_bytes=path.stat().st_size,**process_resources())
    start=time.perf_counter()
    report=convert(path,key,root/'build/demo-report.html')
    summary['report_conversion_seconds']=time.perf_counter()-start
    summary['report_bytes']=report.stat().st_size
    summary['after_report_resources']=process_resources()
    atomic_json(root/'build/benchmark.json',summary)
    print(summary)


if __name__=='__main__':main()
