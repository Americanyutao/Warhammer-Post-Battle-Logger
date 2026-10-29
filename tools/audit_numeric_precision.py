"""Read-only size experiment; rounded data never leaves memory."""
import hashlib
import json
from pathlib import Path
import sys
import time

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from logfile import read_log,load_key
from log_codec import Encoder


def rounded(value,digits):
    if type(value) is float:return round(value,digits)
    if isinstance(value,dict):return {k:rounded(v,digits) for k,v in value.items()}
    if isinstance(value,list):return [rounded(v,digits) for v in value]
    return value


def measure(records,digits):
    encoder=Encoder();size=24;raw_size=0;start=time.process_time()
    for original in records:
        value=rounded(original,digits) if digits is not None and original['kind']=='sample' else original
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
        raw_size+=len(raw)
        size+=20+len(encoder.pack(raw,final=value['kind']=='footer')) # framing + GCM tag
    return dict(bytes=size,raw_json_bytes=raw_size,cpu_seconds=time.process_time()-start)


def main():
    installed=list((P/'release/WH3BattleLogger/captures').glob('*.wh3log'))
    paths=[max((P/'captures').glob('*.wh3log'),key=lambda p:p.stat().st_size),
        max(installed,key=lambda p:p.stat().st_size),max(installed,key=lambda p:p.stat().st_mtime_ns)]
    results=[]
    for path in dict.fromkeys(paths):
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        records=list(read_log(path,load_key(path.parent/'logger.key')))
        result=dict(file=str(path.relative_to(P)),records=len(records),samples=sum(r['kind']=='sample' for r in records),measurements={})
        for digits in (None,4,3,2):
            name='original' if digits is None else str(digits)
            result['measurements'][name]=measure(records,digits)
        assert result['measurements']['original']['bytes']==path.stat().st_size,'Baseline does not match production encoding.'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before,'Source changed.'
        results.append(result)
        print(json.dumps(result),flush=True)
    totals={name:dict(bytes=sum(r['measurements'][name]['bytes'] for r in results),raw_json_bytes=sum(r['measurements'][name]['raw_json_bytes'] for r in results)) for name in ('original','4','3','2')}
    baseline=totals['original']['bytes']
    for value in totals.values():value['additional_saving_percent']=100*(1-value['bytes']/baseline)
    output=P/'build/numeric-precision-audit.json'
    output.write_text(json.dumps(dict(scope='All floating-point values in sample records only; no rounding applied to saved files.',files=results,totals=totals),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(totals,indent=2))


if __name__=='__main__':main()
