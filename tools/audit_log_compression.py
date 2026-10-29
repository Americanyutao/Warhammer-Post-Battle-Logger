"""Read-only, lossless size/CPU experiments; never changes the product format."""
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import zlib

P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P/'src'),str(P/'build/compression-audit-deps')]
import zstandard as zstd
from logfile import read_log,load_key


def encode(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')).hexdigest()


def difference(old,new):
    if type(old) is not type(new):return ['r',new]
    if isinstance(new,dict):
        changes={}
        for key,value in new.items():
            change=difference(old[key],value) if key in old else ['r',value]
            if change is not None:changes[key]=change
        removed=[key for key in old if key not in new]
        return ['d',removed,changes] if removed or changes else None
    if isinstance(new,list):
        if len(old)!=len(new):return ['r',new]
        changes=[]
        for i,(a,b) in enumerate(zip(old,new)):
            change=difference(a,b)
            if change is not None:changes.append([i,change])
        if not changes:return None
        if len(changes)*2>=len(new) and not any(isinstance(v,(dict,list)) for v in new):return ['r',new]
        return ['l',changes]
    same=struct.pack('>d',old)==struct.pack('>d',new) if isinstance(new,float) else old==new
    return None if same else ['r',new]


def apply(old,change):
    if change==0:return old
    if change[0]=='r':return change[1]
    if change[0]=='d':
        out=dict(old)
        for key in change[1]:del out[key]
        for key,value in change[2].items():out[key]=apply(out.get(key),value)
        return out
    out=list(old)
    for index,value in change[1]:out[index]=apply(out[index],value)
    return out


def load(path,key):
    raws=[];digests=[];serialized=0.;read_cpu=0.;samples=0;unit_counts=[];unchanged=compared=0
    fields=Counter();equal_fields=Counter();previous={};first=last=None;revision=None;complete=False
    iterator=iter(read_log(path,key,recover_tail=True))
    while True:
        before=time.process_time()
        try:record=next(iterator)
        except StopIteration:break
        read_cpu+=time.process_time()-before
        before=time.process_time();raws.append(encode(record));serialized+=time.process_time()-before
        digests.append(digest(record))
        if record['kind']=='header':revision=record.get('metadata',{}).get('collector_revision')
        if record['kind']=='footer':complete=True
        if record['kind']!='sample':continue
        samples+=1;unit_counts.append(len(record.get('units',[])))
        t=record.get('sim_s')
        if t is not None:first=t if first is None else first;last=t
        current={}
        for unit in record.get('units',[]):
            uid=unit['id'];current[uid]=unit
            old=previous.get(uid)
            if old is None:continue
            for name,value in unit.items():
                if name not in old:continue
                fields[name]+=1;compared+=1
                if difference(old[name],value) is None:equal_fields[name]+=1;unchanged+=1
        previous=current
    facts=dict(samples=samples,records=len(raws),max_units=max(unit_counts,default=0),
        first_s=first,last_s=last,collector_revision=revision,complete=complete,
        raw_json_bytes=sum(map(len,raws)),json_encode_cpu_s=serialized,current_read_cpu_s=read_cpu,
        unchanged_unit_field_fraction=unchanged/compared if compared else None,
        fields=[dict(name=name,unchanged=equal_fields[name],observations=count,fraction=equal_fields[name]/count)
            for name,count in fields.most_common()])
    return raws,digests,facts


def benchmark(raws,mode):
    start=time.process_time();packets=[]
    if mode in ('zlib1','zlib6'):
        level=int(mode[-1]);packets=[zlib.compress(raw,level) for raw in raws]
    elif mode=='zlib1_stream':
        compressor=zlib.compressobj(1)
        for i,raw in enumerate(raws):
            packets.append(compressor.compress(raw)+compressor.flush(zlib.Z_FINISH if i==len(raws)-1 else zlib.Z_SYNC_FLUSH))
    elif mode=='zstd1_independent':
        compressor=zstd.ZstdCompressor(level=1)
        packets=[compressor.compress(raw) for raw in raws]
    else:
        level=1 if mode=='zstd1_stream' else 3
        compressor=None
        for i,raw in enumerate(raws):
            if compressor is None:compressor=zstd.ZstdCompressor(level=level).compressobj()
            boundary=i==len(raws)-1 or (mode=='zstd3_reset30' and (i+1)%30==0)
            packets.append(compressor.compress(raw)+compressor.flush(zstd.COMPRESSOBJ_FLUSH_FINISH if boundary else zstd.COMPRESSOBJ_FLUSH_BLOCK))
            if boundary:compressor=None
    encode_cpu=time.process_time()-start
    decoder=None;decode_cpu=0.
    for index,(raw,packet) in enumerate(zip(raws,packets)):
        before=time.process_time()
        if mode in ('zlib1','zlib6'):restored=zlib.decompress(packet)
        elif mode=='zlib1_stream':
            if decoder is None:decoder=zlib.decompressobj()
            restored=decoder.decompress(packet)
        elif mode=='zstd1_independent':restored=zstd.ZstdDecompressor().decompress(packet)
        else:
            if decoder is None:decoder=zstd.ZstdDecompressor().decompressobj()
            restored=decoder.decompress(packet)
            if decoder.eof:decoder=None
        json.loads(restored)
        decode_cpu+=time.process_time()-before
        assert restored==raw,(mode,index)
    return dict(bytes=24+sum(len(packet)+20 for packet in packets),
        compression_cpu_s=encode_cpu,decode_and_json_cpu_s=decode_cpu,verified_records=len(raws))


def delta_benchmark(raws,digests):
    previous=None;packets=[];encode_cpu=0.;delta_bytes=0
    for raw in raws:
        current=json.loads(raw)
        before=time.process_time()
        change=['r',current] if previous is None else difference(previous,current)
        packed=encode(0 if change is None else change)
        packets.append(zlib.compress(packed,1));delta_bytes+=len(packed)
        encode_cpu+=time.process_time()-before
        previous=current
    state=None;decode_cpu=0.
    for index,packet in enumerate(packets):
        before=time.process_time()
        state=apply(state,json.loads(zlib.decompress(packet)))
        # Match read_log's fresh-object contract: callers may mutate a yielded record.
        restored=copy.deepcopy(state)
        decode_cpu+=time.process_time()-before
        assert digest(restored)==digests[index],('delta',index)
    return dict(bytes=24+sum(len(packet)+20 for packet in packets),
        writer_cpu_s=encode_cpu,decode_and_materialize_cpu_s=decode_cpu,
        delta_json_bytes=delta_bytes,verified_records=len(raws))


def main():
    roots=[P/'captures',P/'release/WH3BattleLogger/captures']
    inventory=[]
    for root in roots:
        for path in root.glob('*.wh3log'):
            inventory.append(dict(path=path.relative_to(P).as_posix(),bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),modified_ns=path.stat().st_mtime_ns))
    largest=sorted(inventory,key=lambda item:item['bytes'],reverse=True)[:3]
    installed=[item for item in inventory if item['path'].startswith('release/')]
    latest=sorted(installed,key=lambda item:item['modified_ns'],reverse=True)[:2]
    selected={item['path'] for item in largest+latest}
    results=[]
    for item in inventory:
        if item['path'] not in selected:continue
        path=P/item['path'];key=load_key(path.parent/'logger.key')
        raws,digests,facts=load(path,key)
        codecs={name:benchmark(raws,name) for name in
            ('zlib1','zlib6','zlib1_stream','zstd1_independent','zstd1_stream','zstd3_stream','zstd3_reset30')}
        for values in codecs.values():
            values['writer_cpu_s']=values['compression_cpu_s']+facts['json_encode_cpu_s']
        codecs['delta_zlib1']=delta_benchmark(raws,digests)
        assert codecs['zlib1']['bytes']==item['bytes'],('baseline mismatch',item['path'])
        row=dict(**item,**facts,codecs=codecs)
        results.append(row)
        print(json.dumps(dict(file=path.name,mb=round(item['bytes']/1e6,3),samples=facts['samples'],units=facts['max_units'],
            sizes_mb={name:round(values['bytes']/1e6,3) for name,values in codecs.items()})),flush=True)
    for item in inventory:
        assert hashlib.sha256((P/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
    evidence=dict(python=sys.version,zstandard=zstd.__version__,inventory=inventory,results=results,
        all_original_hashes_unchanged=True,notes=[
            'Sizes include the existing 24-byte file header and 20-byte authenticated framing per record; no production format was written.',
            'CPU excludes collection, AES/disk I/O and verification. Full-JSON writers include measured common JSON serialization; readers include JSON parsing.',
            'Delta decoding includes deep copies to preserve fresh record ownership. No sample/field/precision is discarded.',
            'Streams flush every record, allowing each complete authenticated packet prefix to decompress immediately.',
            'Reset30 uses independent zstd frames every30 records, rather than one dictionary for the whole battle.'])
    output=P/'build/log-compression-audit.json'
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print('Read-only audit complete:',output,flush=True)


if __name__=='__main__':main()
