# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Render a run as a problem report: which problem class, with what evidence."""
import json
from pathlib import Path

from judge import judge, FAIL, NOT_EXERCISED, PASS, PROBLEM_FOUND

MARK = {PASS: 'PASS', FAIL: '**FAIL**', NOT_EXERCISED: 'not exercised'}
CLASS = {
    'V1': 'count overrun',
    'V2': 'overrun landing on a live object',
    'V3': 'guard bound broken (all-allow or all-skip)',
    'V4': 'crash or restart loop',
    'V5': 'twin value drift',
    'V6': 'write past a table boundary',
    'V7': 'memory envelope violation',
    'V8': 'silent state gate',
    'V9': 'frame count past the tier cap',
}


def render(run_doc, verdict_doc):
    fw = run_doc.get('firmware', {})
    problems = [r for r in verdict_doc['results'] if r['status'] == FAIL]
    lines = [f"# Z8 problem report — {run_doc.get('scenario', 'run')}", '',
             f"## Verdict: {verdict_doc['verdict']}", '',
             f"Build: `{fw.get('path', '?')}` ({fw.get('bytes', '?')} bytes, sha256 `{str(fw.get('sha256', '?'))[:16]}…`)",
             f"Emulator: `{run_doc.get('emulator', {}).get('path', '?')}`",
             f"Run window completed: {run_doc.get('window_completed', True)}", '']
    lines += ['## Problems', '']
    if problems:
        lines += ['| Class | Detector | Evidence |', '|---|---|---|']
        for r in problems:
            lines.append(f"| {CLASS.get(r['id'], r['klass'])} | {r['id']} | {r['detail']} |")
    else:
        lines.append('None. ' + ('Every detector that had its inputs stayed quiet.'
                                 if verdict_doc['verdict'] == 'CLEAN'
                                 else 'Some detectors did not get their inputs, see below.'))
    lines += ['', '## Detectors', '',
              '| # | Class | Detector | Status | Evidence |', '|---|---|---|---|---|']
    for r in verdict_doc['results']:
        mark = MARK[r['status']]
        if not r.get('in_scope', True):
            mark = 'out of scope' if r['status'] == NOT_EXERCISED else mark + ' (out of scope)'
        lines.append(f"| {r['id']} | {CLASS.get(r['id'], r['klass'])} | {r['title']} "
                     f"| {mark} | {r['detail']} |")
    obs = run_doc.get('observations', {})
    lines += ['', '## Observations', '']
    for key in ('count_sources', 'twin_sources', 'guard', 'ring', 'frame_tier', 'state_gate',
                'poison_armed', 'poison_touch', 'ownerless_armed', 'ownerless_writes',
                'rejections', 'accepts_unmodeled', 'crash', 'hits', 'reads'):
        if key in obs and obs[key]:
            value = obs[key]
            text = json.dumps(value, ensure_ascii=False)
            if len(text) > 400:
                text = text[:400] + '…'
            lines.append(f"- **{key}**: `{text}`")
    checks = run_doc.get('checks') or []
    if checks:
        lines += ['', '## Driver checks', '']
        for c in checks:
            lines.append(f"- {c['name']}: {'PASS' if c['passed'] else 'FAIL'}")
    if run_doc.get('error'):
        lines += ['', f"Run error: `{run_doc['error']}`"]
    return '\n'.join(lines) + '\n'


def write_report(run_doc, out_path, detectors=None):
    verdict_doc = judge(run_doc, detectors)
    text = render(run_doc, verdict_doc)
    Path(out_path).write_text(text)
    return verdict_doc, text
