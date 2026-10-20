# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""DMA accounting from the model's transfer log.

The board model logs every admitted transfer (Z8_DMA, Z8_GDMA, Z8_PDMA,
Z8_STATISTICS_DMA) and every rejection. This turns the log into a ledger:
per channel and mode, how many transfers, how many bytes, which extents, and
whether any transfer ran past the envelope a scenario declared.
"""
import json
import re
from pathlib import Path

LINE = re.compile(r'^(Z8_[A-Z0-9_]+)\s+(.*)$')
FIELD = re.compile(r'(\w+)=([^\s;]+)')
CHANNELS = ('Z8_DMA', 'Z8_GDMA', 'Z8_PDMA', 'Z8_STATISTICS_DMA')


def _int(value):
    try:
        return int(value, 16) if str(value).startswith('0x') else int(value)
    except ValueError:
        return None


def parse(text, envelope=None):
    """Account every transfer line. envelope = optional {lo, hi} guest range."""
    ledger = dict(transfers=0, bytes=0, channels={}, rejections=0, out_of_envelope=[])
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if not m:
            continue
        kind, rest = m.groups()
        fields = {k: _int(v) for k, v in FIELD.findall(rest)}
        if kind in CHANNELS:
            ch = fields.get('ch', 0) or 0
            entry = ledger['channels'].setdefault(
                f'{kind}#{ch}', dict(transfers=0, bytes=0, modes=set(), extents=[]))
            entry['transfers'] += 1
            entry['bytes'] += fields.get('bytes') or 0
            mode = re.search(r'mode=(\w+)', rest)
            if mode:
                entry['modes'].add(mode.group(1))
            dst, size = fields.get('dst'), fields.get('bytes')
            if dst is not None and size:
                entry['extents'].append([hex(dst), hex(dst + size)])
                if envelope and (dst < envelope['lo'] or dst + size > envelope['hi']):
                    ledger['out_of_envelope'].append(
                        dict(channel=f'{kind}#{ch}', dst=hex(dst), bytes=size))
            ledger['transfers'] += 1
            ledger['bytes'] += fields.get('bytes') or 0
        elif 'REJECT' in kind or 'UNMODELED' in kind:
            ledger['rejections'] += 1
    for entry in ledger['channels'].values():
        entry['modes'] = sorted(entry['modes'])
    return ledger


def summarize(ledger):
    lines = [f"transfers {ledger['transfers']}, bytes {ledger['bytes']}, "
             f"rejections {ledger['rejections']}"]
    for name in sorted(ledger['channels']):
        entry = ledger['channels'][name]
        lines.append(f"  {name}: {entry['transfers']} transfers, {entry['bytes']} bytes, "
                     f"modes {','.join(entry['modes']) or '-'}")
    if ledger['out_of_envelope']:
        lines.append(f"  OUT OF ENVELOPE: {len(ledger['out_of_envelope'])} transfer(s)")
    return '\n'.join(lines)


def write(ledger, path):
    Path(path).write_text(json.dumps(ledger, indent=2) + '\n')
