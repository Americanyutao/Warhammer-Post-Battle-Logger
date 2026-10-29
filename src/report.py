"""Offline, self-contained report; no website or in-game UI dependency."""
import argparse
import json
from pathlib import Path
from logfile import load_key
from paths import resource_path
from settings import load_report_options
from report_data import read_summary


def convert(source, key, destination=None, *, report_options=None, recover_tail=False):
    summary=read_summary(source,key,recover_tail=recover_tail)
    output = Path(destination) if destination else Path(source).with_suffix('.html')
    write_report(output, summary,report_options=report_options)
    return output


def write_report(path, summary, *, report_options=None):
    from report_assets import assets_for
    options=load_report_options() if report_options is None else report_options
    summary = dict(summary, report_filename=Path(path).stem, assets=assets_for(summary.get("units", []),icons=options.get('icons',True)))
    payload = json.dumps(summary, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    root = resource_path('src')
    template = (root/'report_template.html').read_text(encoding='utf-8')
    template = template.replace('__CSS__', (root/'report.css').read_text(encoding='utf-8'))
    template = template.replace('__JS__', (root/'report_view.js').read_text(encoding='utf-8'))
    # A crash during conversion must not leave a partial HTML listed as ready.
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    try:
        temporary.write_text(template.replace('__DATA__', payload), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert an encrypted battle log to an offline report.')
    parser.add_argument('file', type=Path)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(convert(args.file, load_key(args.key), args.output))
