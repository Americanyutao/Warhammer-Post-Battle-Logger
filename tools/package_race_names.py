"""Bundle English race labels from the local game localization export."""
import csv
import hashlib
import json
from pathlib import Path
import re
P=Path(__file__).resolve().parents[1]
source=P.parent/'Local-files/text/db/cultures__.loc.tsv'
names={}
with source.open(encoding='utf-8-sig',newline='') as stream:
    for row in csv.DictReader(stream,delimiter='\t',quoting=csv.QUOTE_NONE):
        match=re.match(r'cultures_name_wh[23]?_(?:main|dlc\d+)_([a-z0-9]+)_',row['key'])
        if match and row['text'] and row['text']!='placeholder':names[match[1]]=row['text']
(P/'assets/race-names.json').write_bytes(json.dumps(dict(names=names,source='text/db/cultures__.loc.tsv',sha256=hashlib.sha256(source.read_bytes()).hexdigest()),ensure_ascii=False,separators=(',',':')).encode('utf-8'))
print('Packaged',len(names),'race names.')
