#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""z8debug — dynamic debugging for the Z8 board model.

  attach    run a build with the operator's tables armed, capture the session
  selftest  prove the debug tools behave: tables, throttles, probes, filters

The tables are the hook: observation points, injections and probes. The public
tree ships empty templates and the loader; the values live in debug/local/.
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ledger as L  # noqa: E402
import loader as LO  # noqa: E402
import trace as T  # noqa: E402
from probes import Armory, Point, Probe  # noqa: E402

DEFAULT_MACHINE = 'nikon-z8-lab,bootstrap-fixtures=on,bus-window-fixture=on,serial-fixture=on,service-core-event-model=on'


def _table(args, name, kind):
    path = getattr(args, name, None)
    return LO.load(path, kind) if path else LO.template(kind)


def cmd_attach(args):
    from link import Target
    observe = _table(args, 'observe', 'observe')
    inject = _table(args, 'inject', 'inject')
    probe = _table(args, 'probe', 'probe')
    modules = []
    for item in args.module or []:
        file, addr = item.split('@')
        modules.append(dict(file=file, addr=addr))
    target = Target(qemu=args.qemu, firmware=args.firmware, machine=args.machine,
                    out=args.out, load=modules, raw=args.raw,
                    trace_log=args.trace or None)
    report = dict(qemu=str(Path(args.qemu).resolve()), machine=args.machine,
                  points=[], interventions=[], probes=[], poison=[], started=time.time())
    with target:
        armory = Armory(target, points=observe['points'], interventions=inject['injections'],
                        probes=probe['probes'],
                        on_record=lambda rec: report['points'].append(rec))
        armory.arm()
        report['t0'] = armory.dump_t0(args.t0) if args.t0 or True else None
        if args.t0:
            Path(args.t0).write_text(json.dumps(report['t0'], indent=2) + '\n')
        target.cont()
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            if not target.running():
                state = target.regs()
                for point in armory.points:
                    if point.armed and point.addr == state.get('PC'):
                        armory.trigger(point)
                        break
                armory.disarm_spent()
                target.cont()
            time.sleep(.005)
        target.stop()
        report['poison'] = armory.poison_readback()
        if args.screendump:
            report['screendump'] = target.screendump(args.screendump)
        report['log'] = target.log()
    report['dma'] = L.parse(report.pop('log'))
    if args.dma:
        L.write(report['dma'], args.dma)
    if args.trace and args.trace_filter:
        include, exclude = _split_filter(args.trace_filter)
        filt = T.TraceFilter(include=include, exclude=exclude, cpus=args.cpus)
        report['trace_kept'] = len(filt.filter_file(args.trace))
    (Path(args.out) / 'debug.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 't0'}, indent=2, default=str)[:4000])
    return 0


def _split_filter(spec):
    include, exclude = [], []
    for item in (spec or '').split(',') if spec else []:
        kind, _, rng = item.partition(':')
        lo, hi = rng.split('-')
        (include if kind == 'in' else exclude).append((lo, hi))
    return include, exclude


def cmd_selftest(args):
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    # tables and loader
    for kind in LO.KINDS:
        try:
            LO.template(kind)
            check(f'{kind} template loads', True)
        except Exception as exc:
            check(f'{kind} template loads', False)
            print('   ', exc)
    bad = {'schema': 1, 'points': [{'id': 'x', 'kind': 'nope', 'addr': '0x0'}]}
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(bad, f)
        bad_path = f.name
    try:
        LO.load(bad_path, 'observe')
        check('bad table refused', False)
    except ValueError as exc:
        check('bad table refused', 'not in' in str(exc) or 'expected' in str(exc))

    # throttle: one-shot, max hits, cooldown
    p = Point({'id': 'p', 'kind': 'break', 'addr': '0x10', 'one_shot': True})
    check('one-shot accepts once', p.accept() and not p.accept() and p.spent())
    q = Point({'id': 'q', 'kind': 'break', 'addr': '0x20', 'max_hits': 2})
    got = [q.accept() for _ in range(5)]
    check('hit throttle caps at max_hits', got == [True, True, False, False, False])
    r = Point({'id': 'r', 'kind': 'break', 'addr': '0x30', 'cooldown_s': 0.05, 'max_hits': 8})
    first = r.accept()
    time.sleep(0.001)
    cooled = r.accept()
    time.sleep(0.06)
    later = r.accept()
    check('hit throttle cools down', first and not cooled and later)

    # probe storm limit
    pr = Probe({'id': 's', 'kind': 'skipcall', 'at': 'p', 'w0': '0x0', 'max_uses': 1})
    before = pr.usable()
    pr.uses += 1
    check('probe stops after max_uses', before and not pr.usable())

    # trace filter
    lines = ['Trace 0: 0x1234 [0x40010000/0x10/0x40010000/0]',
             'Trace 1: 0x1234 [0x40010000/0x10/0x40010000/0]',
             'Trace 0: 0x5678 [0x80000000/0x10/0x80000000/0]',
             'Trace 0: 0x1234 [0x40010000/0x10/0x40010000/0]']
    filt = T.TraceFilter(include=[('0x40000000', '0x50000000')])
    kept = [filt.feed(x) for x in lines]
    check('trace keeps only included ranges',
          [k for k in kept if k] == [lines[0], lines[1]])
    cpu0 = T.TraceFilter(cpus=[0], dedupe=False)
    kept = [cpu0.feed(x) for x in lines]
    check('trace filters by cpu', [k for k in kept if k] == [lines[0], lines[2], lines[3]])

    # DMA ledger
    log = ('Z8_DMA completed ch=0 mode=fill src=0x0 dst=0xa00 bytes=0x100 width=8 rows=8 pattern=00\n'
           'Z8_GDMA completed ch=1 src=0x1 dst=0x900 bytes=0x10 mode=copy\n'
           'Z8_GRAPHICS_DMA_UNMODELED op=7\n')
    led = L.parse(log, envelope=dict(lo=0xa00, hi=0xc00))
    check('dma ledger counts transfers', led['transfers'] == 2 and led['bytes'] == 0x110)
    check('dma ledger flags envelope violation',
          len(led['out_of_envelope']) == 1 and led['out_of_envelope'][0]['dst'] == '0x900')
    check('dma ledger counts rejections', led['rejections'] == 1)

    for name, ok in checks:
        print(('PASS ' if ok else 'FAIL ') + name)
    return 0 if all(ok for _, ok in checks) else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('attach', help='run a build with the tables armed')
    s.add_argument('--qemu', required=True)
    s.add_argument('--firmware', required=True)
    s.add_argument('--machine', default=DEFAULT_MACHINE)
    s.add_argument('--out', required=True)
    s.add_argument('--raw')
    s.add_argument('--observe', help='observation point table')
    s.add_argument('--inject', help='injection table')
    s.add_argument('--probe', help='probe table')
    s.add_argument('--module', action='append', help='module feed: FILE@ADDR')
    s.add_argument('--trace', help='write a -d in_asm,exec log here')
    s.add_argument('--trace-filter', help='in:LO-HI,ex:LO-HI')
    s.add_argument('--cpus', type=int, nargs='*', help='trace: keep these cpu indexes')
    s.add_argument('--t0', help='write the t0 dump here')
    s.add_argument('--screendump', help='write a screen dump here (.ppm)')
    s.add_argument('--dma', help='write the dma ledger here')
    s.add_argument('--seconds', type=int, default=30)
    s.set_defaults(fn=cmd_attach)
    s = sub.add_parser('selftest', help='prove the debug tools behave')
    s.set_defaults(fn=cmd_selftest)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
