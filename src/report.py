"""Offline, self-contained report; no website or in-game UI dependency."""
import argparse
import json
import base64
import gzip
import re
from pathlib import Path
from logfile import load_key
from paths import resource_path
from settings import load_report_options
from report_data import read_summary
from report_compact import compact_report,expand_report,JS_DECODER


def convert(source, key, destination=None, *, report_options=None, recover_tail=False):
    summary=read_summary(source,key,recover_tail=recover_tail)
    output = Path(destination) if destination else Path(source).with_suffix('.html')
    write_report(output, summary,report_options=report_options)
    return output


def write_report(path, summary, *, report_options=None):
    from report_assets import assets_for
    options=load_report_options() if report_options is None else report_options
    summary = dict(summary, report_filename=Path(path).stem, assets=assets_for(summary.get("units", []),icons=options.get('icons',True)))
    write_summary(path,summary)


def unpack_payload(value):
    if isinstance(value,dict) and value.get('encoding') in ('gzip-base64-v1','gzip-base64-v2','gzip-base64-v3'):
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(base64.b64decode(value['payload'],validate=True))) as stream:
            raw=stream.read(256*1024*1024+1)
        if len(raw)>256*1024*1024:raise ValueError('Report data is too large.')
        decoded=json.loads(raw)
        return expand_report(decoded) if value['encoding'] in ('gzip-base64-v2','gzip-base64-v3') else decoded
    return value


def write_summary(path,summary):
    raw=json.dumps(summary,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    legacy=compact_report(summary,specialized=False)
    specialized=compact_report(summary)
    if expand_report(specialized)!=summary:raise ValueError('Specialized report reconstruction failed verification.')
    candidates=[('gzip-base64-v1',gzip.compress(raw,compresslevel=6,mtime=0))]
    for encoding,data in [('gzip-base64-v2',legacy),('gzip-base64-v3',specialized)]:
        encoded=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
        candidates.append((encoding,gzip.compress(encoded,compresslevel=6,mtime=0)))
    encoding,payload_bytes=min(candidates,key=lambda item:len(item[1]))
    envelope=dict(layout_revision=2,encoding=encoding,payload=base64.b64encode(payload_bytes).decode('ascii'))
    payload = json.dumps(envelope, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    root = resource_path('src')
    template = (root/'report_template.html').read_text(encoding='utf-8')
    template = template.replace('__CSS__', (root/'report.css').read_text(encoding='utf-8'))
    script=(root/'report_view.js').read_text(encoding='utf-8')
    bootstrap=("(async()=>{const el=document.getElementById('data');try{"
        "document.getElementById('subtitle').textContent='Loading battle report…';"
        "const packed=JSON.parse(el.textContent);const bytes=Uint8Array.from(atob(packed.payload),c=>c.charCodeAt(0));"
        "const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));"
        "const decoded=JSON.parse(await new Response(stream).text());"+JS_DECODER+"el.textContent=JSON.stringify(['gzip-base64-v2','gzip-base64-v3'].includes(packed.encoding)?expandReport(decoded):decoded);\n"+script+"\n}catch(error){console.error(error);document.getElementById('subtitle').textContent='Could not load report. Please open this file in an up-to-date browser.';}})();")
    template = template.replace('__JS__',bootstrap)
    # A crash during conversion must not leave a partial HTML listed as ready.
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    try:
        temporary.write_text(template.replace('__DATA__', payload), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def compress_existing_html(root,progress=lambda text:None):
    root=Path(root).resolve();result=dict(rebuilt=[],moved=[],skipped=[])
    destination=root/'captures/shareables'
    folders=(root/'captures',destination,root/'shareables')
    # Snapshot before moving so relocated files are not processed twice.
    paths=[path for folder in folders if not folder.is_symlink() and not folder.is_junction()
        for path in sorted(folder.glob('*.html'))]
    for path in paths:
        if path.is_symlink():continue
        try:
            if (root/'captures').is_symlink() or (root/'captures').is_junction() or destination.is_symlink() or destination.is_junction():
                raise ValueError('Linked report folders are not migrated.')
            if path.stat().st_size>384*1024*1024:raise ValueError('Report is too large.')
            text=path.read_text(encoding='utf-8')
            match=re.search(r'<script id="data" type="application/json">(.*?)</script>',text,re.S)
            if not match:continue
            value=json.loads(match[1])
            current=value.get('layout_revision')==2 and value.get('encoding') in ('gzip-base64-v1','gzip-base64-v2','gzip-base64-v3')
            if not current:
                if value.get('encoding') in ('gzip-base64-v1','gzip-base64-v2','gzip-base64-v3'):value=unpack_payload(value)
                if not isinstance(value.get('units'),list) or 'assets' not in value:continue
                progress('Compressing HTML report: '+path.name)
                write_summary(path,value)
            output=path
            if path.parent!=destination:
                destination.mkdir(parents=True,exist_ok=True)
                output=destination/path.name;number=1
                while output.exists():
                    output=destination/(path.stem+f' ({number}).html');number+=1
                path.rename(output)
                result['moved'].append(dict(source=str(path),destination=str(output)))
            if not current:result['rebuilt'].append(str(output))
        except Exception as error:result['skipped'].append(dict(path=str(path),error=str(error)))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert an encrypted battle log to an offline report.')
    parser.add_argument('file', type=Path)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(convert(args.file, load_key(args.key), args.output))
