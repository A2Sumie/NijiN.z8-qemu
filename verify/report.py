# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Render a run and its judgement as a report."""
import json
from pathlib import Path

from judge import judge

MARK = {'PASS': 'PASS', 'FAIL': '**FAIL**', 'NOT_EXERCISED': 'not exercised'}


def render(run_doc, verdict_doc):
    fw = run_doc.get('firmware', {})
    lines = [f"# Z8 verification report — {run_doc.get('scenario', 'run')}", '',
             f"Verdict: **{verdict_doc['verdict']}**", '',
             f"Firmware: `{fw.get('path', '?')}` ({fw.get('bytes', '?')} bytes, sha256 `{fw.get('sha256', '?')[:16]}…`)",
             f"Emulator: `{run_doc.get('emulator', {}).get('path', '?')}`",
             f"Window completed: {run_doc.get('window_completed', True)}", '',
             '| # | Class | Criterion | Status | Detail |',
             '|---|---|---|---|---|']
    for r in verdict_doc['results']:
        lines.append(f"| {r['id']} | {r['klass']} | {r['title']} | {MARK[r['status']]} | {r['detail']} |")
    obs = run_doc.get('observations', {})
    lines += ['', '## Observations', '']
    for key in ('count_sources', 'poison_armed', 'poison_touch', 'rejections',
                'accepts_unmodeled', 'crash', 'hits', 'reads'):
        if key in obs and obs[key]:
            value = obs[key]
            if key in ('hits', 'reads') and isinstance(value, (dict, list)):
                value = json.dumps(value)[:400] + ('…' if len(json.dumps(value)) > 400 else '')
            lines.append(f"- **{key}**: `{json.dumps(value, ensure_ascii=False)}`")
    checks = run_doc.get('checks') or []
    if checks:
        lines += ['', '## Driver checks', '']
        for c in checks:
            lines.append(f"- {c['name']}: {'PASS' if c['passed'] else 'FAIL'}")
    if run_doc.get('error'):
        lines += ['', f"Run error: `{run_doc['error']}`"]
    return '\n'.join(lines) + '\n'


def write_report(run_doc, out_path, criteria=None):
    verdict_doc = judge(run_doc, criteria)
    text = render(run_doc, verdict_doc)
    Path(out_path).write_text(text)
    return verdict_doc, text
