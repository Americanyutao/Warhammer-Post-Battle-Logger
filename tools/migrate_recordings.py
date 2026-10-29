"""Migrate verified closed recordings in explicitly selected app directories."""
import argparse
import json
from pathlib import Path
import sys
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from log_migration import optimize_captures

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True,action='append')
    parser.add_argument('--delete-html',action='store_true')
    parser.add_argument('--release-storage',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result={str(root):optimize_captures(root,delete_html=args.delete_html,precision=args.release_storage,progress=lambda message:print(message,flush=True)) for root in args.data_dir}
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
