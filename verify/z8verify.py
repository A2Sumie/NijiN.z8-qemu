#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""z8verify — dynamic verification for a Z8 firmware build.

  run     drive one emulator run from a scenario file and record observations
  adopt   build a run.json from observations a driver already recorded
  judge   verdict one run against the criteria set
  report  render a run and its verdict as markdown
  selftest  per pit: a known-bad run must be reported, a clean run must not be

Usage: python3 verify/z8verify.py <command> --help
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import judge as J  # noqa: E402
import report as R  # noqa: E402


def cmd_run(args):
    """Run one firmware build and emit its problem report."""
    import scenario
    run_doc = scenario.run(args.scenario, args.out, firmware=args.firmware, qemu=args.qemu)
    verdict, text = R.write_report(run_doc, Path(args.out) / 'report.md')
    print(text)
    return 1 if verdict['verdict'] == J.PROBLEM_FOUND else 0


def cmd_adopt(args):
    obs = json.loads(Path(args.observations).read_text())
    spec = json.loads(Path(args.scenario).read_text())
    counts = spec.get('counts', {})
    if counts.get('extent') is not None:
        obs['count_extent'] = counts['extent']
    obs.setdefault('poison_armed', [p['tag'] for p in spec.get('poison', [])
                                    if p.get('role', 'poison') != 'boundary'])
    obs.setdefault('ownerless_armed', [p['tag'] for p in spec.get('poison', [])
                                       if p.get('role') == 'boundary'])
    for key in ('twin_sources', 'ring', 'guard', 'frame_tier', 'state_gate',
                'poison_touch', 'ownerless_writes', 'rejections', 'accepts_unmodeled'):
        obs.setdefault(key, {'twin_sources': {}, 'ring': None, 'guard': None,
                             'frame_tier': None, 'state_gate': []}.get(key, []))
    run_doc = dict(schema=1, kind='z8verify-run',
                   scenario=spec.get('name', Path(args.scenario).stem),
                   firmware=dict(path=str(args.firmware), sha256='adopted', bytes=0),
                   emulator=dict(path='adopted', sha256='adopted', argv=[]),
                   observations=obs, checks=obs.get('checks', []),
                   error=obs.get('error'), window_completed=obs.get('window_completed', True))
    Path(args.out).write_text(json.dumps(run_doc, indent=2) + '\n')
    print(json.dumps(J.judge(run_doc), indent=2))
    return 0


def cmd_judge(args):
    run_doc = json.loads(Path(args.run).read_text())
    verdict = J.judge(run_doc, J.load_detectors(args.criteria) if args.criteria else None)
    print(json.dumps(verdict, indent=2))
    return 1 if verdict['verdict'] == J.PROBLEM_FOUND else 0


def cmd_report(args):
    run_doc = json.loads(Path(args.run).read_text())
    out = args.out or str(Path(args.run).with_suffix('.md'))
    verdict, text = R.write_report(run_doc, out)
    print(text)
    return 1 if verdict['verdict'] == J.PROBLEM_FOUND else 0


def _clean_observations():
    """A run with every input present and every criterion passing."""
    return dict(
        count_sources={'registration': 617, 'save_immediate': 617, 'walk_counter': 617},
        count_extent=617,
        poison_armed=['slot-after-table'], poison_touch=[],
        ownerless_armed=['table-boundary'], ownerless_writes=[],
        guard=dict(valid_allowed=True, invalid_rejected=True, silent=False),
        twin_sources={'capacity': {'cap_row_a': 512, 'cap_row_b': 512}},
        ring=dict(requested_bytes=144000000, envelope_bytes=536870912, delivered_frames=5),
        state_gate=[dict(id='card-state', verdict=0, expected_verdict=0,
                         expected_clear=True, cleared=True, silent=False)],
        frame_tier=dict(frames=15, tier_cap=30),
        rejections=[dict(id='unmodeled-output', expected='unmodeled output', seen=True)],
        accepts_unmodeled=[],
        crash=dict(seen=False, kind=None),
        hits=[], reads={})


def _broken(pit):
    """The same run with exactly one pit made visible."""
    obs = _clean_observations()
    if pit == 'P1a':
        obs['count_sources']['walk_counter'] = 618
    elif pit == 'P1b':
        obs['poison_touch'] = [dict(tag='slot-after-table', addr='0x0', expected='41', found='00')]
    elif pit == 'P2':
        obs['twin_sources']['capacity']['cap_row_b'] = 514
    elif pit == 'P3-allow':
        obs['guard'] = dict(valid_allowed=True, invalid_rejected=False, silent=False)
    elif pit == 'P3-skip':
        obs['guard'] = dict(valid_allowed=False, invalid_rejected=True, silent=False)
    elif pit == 'P4':
        obs['ownerless_writes'] = [dict(tag='table-boundary', addr='0x0', expected='00', found='08')]
    elif pit == 'P5':
        obs['ring'] = dict(requested_bytes=862000000, envelope_bytes=536870912, delivered_frames=0)
    elif pit == 'P6':
        obs['state_gate'] = [dict(id='card-state', verdict=0, expected_verdict=0,
                                  expected_clear=True, cleared=False, silent=False)]
    elif pit == 'P7':
        obs['crash'] = dict(seen=True, kind='Z8_UNKNOWN')
    elif pit == 'P8':
        obs['frame_tier'] = dict(frames=31, tier_cap=30)
    return obs


def _run_doc(obs, window=True):
    return dict(schema=1, kind='z8verify-run', scenario='synthetic',
                firmware=dict(path='synthetic', sha256='0' * 64, bytes=0),
                emulator=dict(path='synthetic', sha256='0' * 64, argv=[]),
                observations=obs, checks=[], error=None, window_completed=window)


CRITERION_OF_PIT = {'P1a': 'V1', 'P1b': 'V2', 'P2': 'V5', 'P3-allow': 'V3',
                    'P3-skip': 'V3', 'P4': 'V6', 'P5': 'V7', 'P6': 'V8',
                    'P7': 'V4', 'P8': 'V9'}


def cmd_selftest(args):
    checks = []
    good = J.judge(_run_doc(_clean_observations()))
    checks.append(('clean build is CLEAN', good['verdict'] == J.CLEAN))
    for pit, crit in CRITERION_OF_PIT.items():
        verdict = J.judge(_run_doc(_broken(pit)))
        failed = [r['id'] for r in verdict['results'] if r['status'] == J.FAIL]
        checks.append((f'{pit}: known-bad is reported by {crit}',
                       verdict['verdict'] == J.PROBLEM_FOUND and failed == [crit]))
    sparse = _clean_observations()
    for key in ('count_sources', 'poison_armed', 'guard', 'twin_sources', 'ownerless_armed',
                'ring', 'state_gate', 'frame_tier', 'rejections'):
        sparse.pop(key, None)
    unverified = J.judge(_run_doc(sparse))
    checks.append(('missing inputs are not silently green', unverified['verdict'] == J.UNVERIFIED))
    incomplete = J.judge(_run_doc(_clean_observations(), window=False))
    checks.append(('incomplete window is not green', incomplete['verdict'] == J.UNVERIFIED))
    for name, ok in checks:
        print(('PASS ' if ok else 'FAIL ') + name)
    return 0 if all(ok for _, ok in checks) else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('run', help='drive one emulator run from a scenario file')
    s.add_argument('--scenario', required=True)
    s.add_argument('--out', required=True)
    s.add_argument('--firmware')
    s.add_argument('--qemu')
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser('adopt', help='build run.json from driver observations')
    s.add_argument('--observations', required=True)
    s.add_argument('--scenario', required=True)
    s.add_argument('--firmware', default='adopted')
    s.add_argument('--out', required=True)
    s.set_defaults(fn=cmd_adopt)
    s = sub.add_parser('judge', help='verdict one run')
    s.add_argument('--run', required=True)
    s.add_argument('--criteria', help='alternate detector set')
    s.set_defaults(fn=cmd_judge)
    s = sub.add_parser('report', help='render a markdown report')
    s.add_argument('--run', required=True)
    s.add_argument('--out')
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser('selftest', help='calibrate the detectors: bad build fires, clean build stays quiet')
    s.set_defaults(fn=cmd_selftest)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
