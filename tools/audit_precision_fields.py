"""Read-only inventory of saved scalar fields and decimal-rounding errors."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from logfile import load_key,read_log


def main():
    fields={};files=[]
    def visit(value,path):
        if isinstance(value,dict):
            for key,child in value.items():visit(child,path+'.'+key)
            return
        if isinstance(value,list):
            for child in value:visit(child,path+'[]')
            return
        stat=fields.setdefault(path,dict(types=Counter(),numeric=0,floats=0,fractional=0,changed4=0,zeroed4=0,
            minimum=None,maximum=None,smallest_nonzero=None,max_error4=0,max_relative_error4=0,examples=[]))
        stat['types'][type(value).__name__]+=1
        if type(value) not in (int,float) or not math.isfinite(value):return
        stat['numeric']+=1
        stat['minimum']=value if stat['minimum'] is None else min(value,stat['minimum'])
        stat['maximum']=value if stat['maximum'] is None else max(value,stat['maximum'])
        if value:stat['smallest_nonzero']=abs(value) if stat['smallest_nonzero'] is None else min(abs(value),stat['smallest_nonzero'])
        if type(value) is not float:return
        stat['floats']+=1
        if value!=math.trunc(value):stat['fractional']+=1
        new=round(value,4);error=abs(new-value)
        if error:
            stat['changed4']+=1
            stat['max_error4']=max(stat['max_error4'],error)
            if value:stat['max_relative_error4']=max(stat['max_relative_error4'],error/abs(value))
            if new==0:stat['zeroed4']+=1
            if len(stat['examples'])<3:stat['examples'].append([value,new])
    for folder in (P/'captures',P/'release/WH3BattleLogger/captures'):
        paths=list(folder.glob('*.wh3log'))
        if not paths:continue
        key=load_key(folder/'logger.key')
        for path in paths:
            before=hashlib.sha256(path.read_bytes()).hexdigest();count=0
            for record in read_log(path,key):
                visit(record,record['kind']);count+=1
            assert hashlib.sha256(path.read_bytes()).hexdigest()==before,'Source changed.'
            files.append(dict(file=str(path.relative_to(P)),records=count,unchanged=True))
            print(path.name,count,flush=True)
    result=dict(files=files,fields=dict(sorted(fields.items())))
    (P/'build/precision-field-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    for path,stat in sorted(fields.items()):
        if stat['numeric'] and 'deployment_baseline' not in path:
            print(path,json.dumps(stat),flush=True)


if __name__=='__main__':main()
