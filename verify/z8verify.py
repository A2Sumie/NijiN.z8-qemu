#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""z8verify — dynamic verification for a Z8 firmware build.

  run     drive one emulator run from a scenario file and record observations
  adopt   build a run.json from observations a driver already recorded
  judge   verdict one run against the criteria set
  report  render a run and its verdict as markdown
  selftest  prove the judge separates a bad build from a clean one

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
    import scenario
    run_doc = scenario.run(args.scenario, args.out, firmware=args.firmware, qemu=args.qemu)
    verdict = J.judge(run_doc)
    print(json.dumps(verdict, indent=2))
    return 1 if verdict['verdict'] == J.PROBLEM_FOUND else 0


def cmd_adopt(args):
    obs = json.loads(Path(args.observations).read_text())
    spec = json.loads(Path(args.scenario).read_text())
    counts = spec.get('counts', {})
    obs.setdefault('count_sources', {})
    if counts.get('extent') is not None:
        obs['count_extent'] = counts['extent']
    obs.setdefault('poison_armed', [p['tag'] for p in spec.get('poison', [])])
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
    verdict = J.judge(run_doc, J.load_criteria(args.criteria) if args.criteria else None)
    print(json.dumps(verdict, indent=2))
    return 1 if verdict['verdict'] == J.PROBLEM_FOUND else 0


def cmd_report(args):
    run_doc = json.loads(Path(args.run).read_text())
    out = args.out or str(Path(args.run).with_suffix('.md'))
    verdict, text = R.write_report(run_doc, out)
    print(text)
    return 1 if verdict['verdict'] == J.PROBLEM_FOUND else 0


def _synthetic(bad):
    """A run with its inputs present. bad=True carries the defects."""
    obs = dict(
        count_sources={'registration': 618 if bad else 617,
                       'save_immediate': 618 if bad else 617,
                       'table_extent': 617},
        count_extent=617,
        poison_armed=['slot-after-table'],
        poison_touch=([dict(tag='slot-after-table', addr='0x0', expected='41', found='00')]
                      if bad else []),
        rejections=[dict(id='dma-unmodeled', expected='Z8_GRAPHICS_DMA_UNMODELED',
                         seen=True)],
        accepts_unmodeled=([dict(id='graphics-submit', detail='accepted without model')]
                           if bad else []),
        crash=dict(seen=bad, kind='Z8_UNKNOWN' if bad else None),
        hits=[], reads={})
    return dict(schema=1, kind='z8verify-run', scenario='synthetic',
                firmware=dict(path='synthetic', sha256='0' * 64, bytes=0),
                emulator=dict(path='synthetic', sha256='0' * 64, argv=[]),
                observations=obs, checks=[], error=None, window_completed=True)


def cmd_selftest(args):
    bad = J.judge(_synthetic(True))
    good = J.judge(_synthetic(False))
    sparse = J.judge(_synthetic(False), J.load_criteria())
    dropped = json.loads(json.dumps(_synthetic(False)))
    dropped['observations'].pop('count_sources')
    dropped['observations'].pop('poison_armed')
    dropped['observations'].pop('rejections')
    unverified = J.judge(dropped)
    checks = [
        ('bad build is reported', bad['verdict'] == J.PROBLEM_FOUND),
        ('clean build is clean', good['verdict'] == J.CLEAN),
        ('inputs present is exercised', sparse['verdict'] == J.CLEAN),
        ('missing inputs are not silently green', unverified['verdict'] == J.UNVERIFIED),
        ('bad build fails the count criterion',
         [r['status'] for r in bad['results'] if r['id'] == 'V1'] == [J.FAIL]),
        ('bad build fails the envelope criterion',
         [r['status'] for r in bad['results'] if r['id'] == 'V2'] == [J.FAIL]),
    ]
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
    s.add_argument('--criteria')
    s.set_defaults(fn=cmd_judge)
    s = sub.add_parser('report', help='render a markdown report')
    s.add_argument('--run', required=True)
    s.add_argument('--out')
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser('selftest', help='judge positive and negative controls')
    s.set_defaults(fn=cmd_selftest)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
