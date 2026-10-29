"""User choices survive closing a view; decoded battle/browser caches do not."""
import hashlib
import json
import math
from pathlib import Path
import uuid


class ViewerPreferences:
    def __init__(self,root,source):
        self.root=Path(root)/'preferences/report-viewer'
        digest=hashlib.sha256(Path(source).name.encode('utf-8')).hexdigest()
        self.files=dict(graphs='graphs.json',hide_explanations='hide-explanations.json',unit_values='values-'+digest+'.json')

    def load(self):
        result={}
        for name,filename in self.files.items():
            try:
                path=self.root/filename
                if path.stat().st_size>65536:continue
                value=path.read_text(encoding='utf-8');self.validate(name,value)
                result[name]=value
            except (OSError,ValueError,TypeError):continue
        return result

    def validate(self,name,value):
        if name not in self.files or not isinstance(value,str) or len(value.encode('utf-8'))>65536:raise ValueError('Invalid viewer preference.')
        data=json.loads(value)
        if name=='graphs':
            if not isinstance(data,list) or len(data)!=4 or not all(isinstance(k,str) and len(k)<100 for k in data):raise ValueError('Invalid graph choices.')
        elif name=='hide_explanations':
            if not isinstance(data,bool):raise ValueError('Invalid explanation preference.')
        elif not isinstance(data,dict) or len(data)>1024 or not all(isinstance(k,str) and len(k)<512 and type(v) in (int,float) and math.isfinite(v) and v>=0 for k,v in data.items()):
            raise ValueError('Invalid unit values.')

    def save(self,name,value):
        self.validate(name,value)
        self.root.mkdir(parents=True,exist_ok=True)
        path=self.root/self.files[name];temp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:temp.write_text(value,encoding='utf-8');temp.replace(path)
        finally:temp.unlink(missing_ok=True)
