"""Lossless export-only shared clocks, change columns, and derived chart samples."""
import json
import copy
import math
from report_reconstruct import prepare_report,restore_report,JS_RESTORE

JS_DECODER=JS_RESTORE+"""function expandReport(p){const memo=new Map();const own=(o,k,v)=>Object.defineProperty(o,k,{value:v,enumerable:true,writable:true,configurable:true});function value(v){if(!Array.isArray(v))return v;const id=v[0];if(memo.has(id))return structuredClone(memo.get(id));const [kind,body,rows,columns]=p.nodes[id];let out;if(kind===0){out={};for(const [k,x] of Object.entries(body))own(out,k,value(x));}else if(kind===1)out=body.map(value);else if(kind===4){let i=0;out=[];for(const [delta,count] of body)for(let n=0;n<count;n++){i+=delta;out.push(p.times[i]);}}else if(kind===3){out=value(body).map(t=>({t}));rows.forEach((path,col)=>{const runs=columns[col];let current=runs[0],next=0,change=0;for(let r=0;r<out.length;r++){if(change<runs[1].length&&r===next+runs[1][change]){next=r;current=runs[1][change+1];change+=2;}if(Array.isArray(current)&&!current.length)continue;let row=out[r];for(const k of path.slice(0,-1)){if(!Object.hasOwn(row,k))own(row,k,{});row=row[k];}own(row,path.at(-1),value(current));}});}else{let previous={};out=rows.map(patch=>{const row=structuredClone(previous);for(let i=0;i<patch.length;){const col=patch[i++];if(col<0)delete row[body[-col-1]];else own(row,body[col],value(patch[i++]));}previous=row;return row;});}memo.set(id,out);return out;}const result=value(p.root);return p.derived?restoreReport(result,value(p.derived)):result;} """


def fingerprint(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def compact_report(summary,*,specialized=True,reconstruct=True):
    if specialized and reconstruct:summary,recipes=prepare_report(summary)
    else:recipes=None
    times=set()
    def clocks(v):
        if isinstance(v,dict):
            t=v.get('t')
            if type(t) in (int,float) and math.isfinite(t):times.add(t)
            for x in v.values():clocks(x)
        elif isinstance(v,list):
            for x in v:clocks(x)
    if specialized:clocks(summary)
    times=sorted(times);time_index={t:i for i,t in enumerate(times)}
    nodes=[];known={}
    def intern(node):
        key=fingerprint(node)
        if key not in known:known[key]=len(nodes);nodes.append(node)
        return [known[key]]
    def flattened(row,path=()):
        for k,x in row.items():
            if not path and k=='t':continue
            if isinstance(x,dict) and x:yield from flattened(x,path+(k,))
            else:yield path+(k,),encode(x)
    def timeline(v):
        deltas=[];previous=0
        for row in v:
            current=time_index[row['t']];delta=current-previous;previous=current
            if deltas and deltas[-1][0]==delta:deltas[-1][1]+=1
            else:deltas.append([delta,1])
        axis=intern([4,deltas]);paths={};columns=[]
        flat=[dict(flattened(row)) for row in v]
        for row in flat:
            for path in row:paths.setdefault(path,len(paths))
        for path in paths:
            initial=flat[0].get(path,[]);previous=initial;last=0;changes=[];signature=fingerprint(initial)
            for i,row in enumerate(flat[1:],1):
                current=row.get(path,[]);key=fingerprint(current)
                if key!=signature:changes.extend([i-last,current]);last=i;previous=current;signature=key
            columns.append([initial,changes])
        return [3,axis,[list(p) for p in paths],columns]
    def encode(v):
        if isinstance(v,dict):node=[0,{k:encode(x) for k,x in v.items()}]
        elif isinstance(v,list):
            if specialized and len(v)>=3 and all(isinstance(x,dict) and type(x.get('t')) in (int,float) and math.isfinite(x['t']) for x in v):node=timeline(v)
            elif len(v)>=3 and all(isinstance(x,dict) for x in v):
                keys=list(dict.fromkeys(k for row in v for k in row));index={k:i for i,k in enumerate(keys)};previous={};rows=[]
                for row in v:
                    current={k:encode(x) for k,x in row.items()};patch=[]
                    for k in previous:
                        if k not in current:patch.append(-index[k]-1)
                    for k,x in current.items():
                        if k not in previous or fingerprint(x)!=fingerprint(previous[k]):patch.extend((index[k],x))
                    rows.append(patch);previous=current
                node=[2,keys,rows]
            else:node=[1,[encode(x) for x in v]]
        else:return v
        return intern(node)
    root=encode(summary);out=dict(root=root,nodes=nodes)
    if specialized:out['times']=times
    if recipes and (recipes['copies'] or recipes['activities']):out['derived']=encode(recipes)
    return out


def expand_report(p):
    memo={}
    def value(v):
        if not isinstance(v,list):return v
        i=v[0]
        if i in memo:return copy.deepcopy(memo[i])
        node=p['nodes'][i];kind,body=node[:2]
        if kind==0:out={k:value(x) for k,x in body.items()}
        elif kind==1:out=[value(x) for x in body]
        elif kind==4:
            index=0;out=[]
            for delta,count in body:
                for _ in range(count):index+=delta;out.append(p['times'][index])
        elif kind==3:
            out=[dict(t=t) for t in value(body)]
            for path,(initial,changes) in zip(node[2],node[3]):
                current=initial;change=0;last=0
                for r,row in enumerate(out):
                    if change<len(changes) and r==last+changes[change]:last=r;current=changes[change+1];change+=2
                    if isinstance(current,list) and not current:continue
                    for k in path[:-1]:row=row.setdefault(k,{})
                    row[path[-1]]=value(current)
        else:
            out=[];previous={}
            for patch in node[2]:
                row=copy.deepcopy(previous);j=0
                while j<len(patch):
                    col=patch[j];j+=1
                    if col<0:row.pop(body[-col-1],None)
                    else:row[body[col]]=value(patch[j]);j+=1
                out.append(row);previous=row
        memo[i]=out;return out
    result=value(p['root'])
    return restore_report(result,value(p['derived'])) if p.get('derived') else result
