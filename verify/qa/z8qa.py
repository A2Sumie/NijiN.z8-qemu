#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""z8qa — the daily-use QA battery.

One command, one report: run the set against a firmware build and read the
verdict per item. Every item is an ordinary thing a user does with the camera:
power, shooting modes, shutter, live view, playback, recording, menus, cards,
battery, USB, error recovery. Judgement is dynamic: the rule reads what the run
recorded, never what a recording says it should record. A surface the run did
not reach is NOT_EXERCISED and never PASS.

  run      judge a directory of run observations against the battery
  selftest prove the rules separate a passing item from a failing one
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PASS, FAIL, NOT_EXERCISED = 'PASS', 'FAIL', 'NOT_EXERCISED'


def load_battery(path=None):
    return json.loads(Path(path or HERE / 'battery.json').read_text())['items']


def resolve(obs, path):
    node = obs
    for part in path.split('.'):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def evaluate_check(obs, check):
    value = resolve(obs, check['obs'])
    if value is None:
        return NOT_EXERCISED, f"{check['obs']} not recorded"
    op, want = check['op'], check.get('value')
    if op == 'eq' and value != want:
        return FAIL, f"{check['obs']} = {value!r}, expected {want!r}"
    if op == 'gt' and not (isinstance(value, (int, float)) and value > want):
        return FAIL, f"{check['obs']} = {value!r}, expected > {want!r}"
    if op == 'contains' and want not in (value or []):
        return FAIL, f"{check['obs']} = {value!r} does not contain {want!r}"
    return PASS, f"{check['obs']} {op} {want!r}"


def judge_item(item, obs):
    verdict, details, reached = PASS, [], 0
    for check in item.get('expect', []):
        status, detail = evaluate_check(obs, check)
        details.append(detail)
        if status == FAIL:
            verdict = FAIL
        elif status == NOT_EXERCISED and verdict != FAIL:
            verdict = NOT_EXERCISED
        else:
            reached += 1
    if obs.get('crash', {}).get('seen') and verdict != FAIL:
        verdict, tail = FAIL, f"crash observed: {obs['crash'].get('kind')}"
        details.append(tail)
    return dict(id=item['id'], surface=item['surface'], title=item['title'],
                sequence=item.get('sequence'), expected=item.get('expected'),
                alternative=item.get('alternative'), status=verdict,
                detail='; '.join(details) or 'no expectation declared')


def judge_battery(items, observations):
    results = [judge_item(item, observations[item['id']]) if item['id'] in observations
               else dict(id=item['id'], surface=item['surface'], title=item['title'],
                         sequence=item.get('sequence'), expected=item.get('expected'),
                         alternative=item.get('alternative'), status=NOT_EXERCISED,
                         detail='no run for this item')
               for item in items]
    counts = {s: len([r for r in results if r['status'] == s])
              for s in (PASS, FAIL, NOT_EXERCISED)}
    verdict = 'FAIL' if counts[FAIL] else ('PASS WITH GAPS' if counts[NOT_EXERCISED] else 'PASS')
    return dict(verdict=verdict, counts=counts, results=results)


def render(report, build=None):
    lines = ['# Z8 daily-use QA report', '',
             f"Verdict: **{report['verdict']}**  ",
             f"PASS {report['counts'][PASS]} · FAIL {report['counts'][FAIL]} · "
             f"NOT_EXERCISED {report['counts'][NOT_EXERCISED]}",
             '']
    if build:
        lines += [f"Build: `{build}`", '']
    lines += ['| # | Surface | Operation | Expected | Verdict | Detail |',
              '|---|---|---|---|---|---|']
    for r in report['results']:
        mark = {PASS: 'PASS', FAIL: '**FAIL**', NOT_EXERCISED: 'NOT_EXERCISED'}[r['status']]
        lines.append(f"| {r['id']} | {r['surface']} | {r['title']} | {r['expected'] or '—'} "
                     f"| {mark} | {r['detail']} |")
    gaps = [r for r in report['results'] if r['status'] == NOT_EXERCISED]
    if gaps:
        lines += ['', '## Not exercised and why', '']
        for r in gaps:
            lines.append(f"- **{r['id']} {r['title']}**: {r['detail']}"
                         + (f" — {r['alternative']}" if r.get('alternative') else ''))
    return '\n'.join(lines) + '\n'


def _obs(path):
    return json.loads(Path(path).read_text())


def cmd_run(args):
    items = load_battery(args.battery)
    observations = {}
    for path in sorted(Path(args.observations).glob('*.json')):
        doc = _obs(path)
        key = doc.get('id') or path.stem.replace('obs-', '')
        observations[key] = doc
    report = judge_battery(items, observations)
    text = render(report, build=args.build)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'qa-report.md').write_text(text)
    (out / 'qa-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(text)
    return 1 if report['verdict'] == 'FAIL' else 0


def _synthetic(kind):
    if kind == 'good':
        return {'power': {'on': True}, 'liveview': {'frames': 12}, 'capture': {'frames': 3},
                'menu': {'events': 7}, 'crash': {'seen': False}}
    if kind == 'bad':
        return {'power': {'on': True}, 'liveview': {'frames': 12}, 'capture': {'frames': 0},
                'menu': {'events': 7}, 'crash': {'seen': False}}
    return {'power': {'on': True}, 'crash': {'seen': False}}


def cmd_selftest(args):
    items = [{'id': 'X1', 'surface': 's', 'title': 'frames come', 'rule': 'behavior',
              'expect': [{'obs': 'capture.frames', 'op': 'gt', 'value': 0}]},
             {'id': 'X2', 'surface': 's', 'title': 'no crash', 'rule': 'behavior',
              'expect': [{'obs': 'menu.events', 'op': 'gt', 'value': 0}]}]
    good = judge_battery(items, {'X1': _synthetic('good'), 'X2': _synthetic('good')})
    bad = judge_battery(items, {'X1': _synthetic('bad'), 'X2': _synthetic('good')})
    missing = judge_battery(items, {'X1': _synthetic('sparse')})
    checks = [('passing run is PASS', good['verdict'] == 'PASS'),
              ('failing run is FAIL', bad['verdict'] == 'FAIL' and
               [r['id'] for r in bad['results'] if r['status'] == FAIL] == ['X1']),
              ('missing input is NOT_EXERCISED', missing['counts'][NOT_EXERCISED] >= 1),
              ('missing input never passes', missing['verdict'] != 'PASS'),
              ('crash turns a run into FAIL',
               judge_battery(items, {'X1': dict(_synthetic('good'),
                                                crash={'seen': True, 'kind': 'Z8_UNKNOWN'})})['verdict'] == 'FAIL')]
    for name, ok in checks:
        print(('PASS ' if ok else 'FAIL ') + name)
    return 0 if all(ok for _, ok in checks) else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('run', help='judge a directory of run observations')
    s.add_argument('--observations', required=True, help='directory of obs-*.json')
    s.add_argument('--out', required=True)
    s.add_argument('--battery')
    s.add_argument('--build')
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser('selftest', help='prove the rules behave')
    s.set_defaults(fn=cmd_selftest)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
