"""Ordinary CLI used only by generic execution tests."""
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('source')
p.add_argument('output')
p.add_argument('--mode', default='ok')
a = p.parse_args()
out = Path(a.output)
if out.exists() or out.resolve() == Path(a.source).resolve():
    raise ValueError('Destination exists or aliases input')
value = Path(a.source).read_text()
if a.mode == 'package':
    import fixturepkg
    value = fixturepkg.VALUE
out.write_text(value)
if a.mode == 'partial':
    raise SystemExit(3)
if a.mode == 'extra':
    out.with_name('extra.txt').write_text('unexpected')
if a.mode == 'paths':
    out.write_text(json.dumps({'source': a.source, 'output': a.output}))
