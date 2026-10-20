# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Points, probes and interventions.

Points are armed from a table and never from code: observation points,
watchpoints, one-shot points, hit throttling, probes that skip or call a
routine, and interventions that write memory, poison a slot, feed an input or
load a module. The table lives with the operator; this file carries no value.
"""
import json
import time
from pathlib import Path

ACCESS_CODE = {'break': 'sw', 'watch-r': 'r', 'watch-w': 'w', 'watch-a': 'a'}


class Point:
    """One observation point with its arming and throttling policy."""

    def __init__(self, spec):
        self.spec = dict(spec)
        self.id = spec['id']
        self.kind = spec['kind']
        self.addr = int(spec['addr'], 16)
        self.length = int(spec.get('len', 4))
        self.one_shot = bool(spec.get('one_shot', False))
        self.max_hits = int(spec.get('max_hits', 1 if self.one_shot else 8))
        self.cooldown = float(spec.get('cooldown_s', 0.0))
        self.capture = list(spec.get('capture', ['regs']))
        self.hits = 0
        self.record = []
        self.armed = False
        self._last_hit = 0.0

    def accept(self):
        """True when this hit is recorded. False when the throttle eats it."""
        now = time.monotonic()
        if self.hits >= self.max_hits:
            return False
        if self.cooldown and self.hits and now - self._last_hit < self.cooldown:
            return False
        self._last_hit = now
        self.hits += 1
        return True

    def spent(self):
        return self.hits >= self.max_hits or self.one_shot


class Intervention:
    """One write, injection or load, bound to a point or to session start."""

    def __init__(self, spec):
        self.spec = dict(spec)
        self.id = spec['id']
        self.kind = spec['kind']          # poke | poison | key-body | event | module
        self.at = spec.get('at')          # observe id, or None for session start
        self.addr = int(spec['addr'], 16) if spec.get('addr') else None
        self.bytes = bytes.fromhex(spec['bytes']) if spec.get('bytes') else None
        self.file = spec.get('file')
        self.channel = spec.get('channel')
        self.property = spec.get('machine_property')   # {"name": ..., "value": ...}
        self.done = False


class Probe:
    """A probe: skip a call and force its result, or call a routine."""

    def __init__(self, spec):
        self.spec = dict(spec)
        self.id = spec['id']
        self.kind = spec['kind']          # skipcall | invoke
        self.at = spec['at']              # observe id that triggers it
        self.fn = int(spec['fn'], 16) if spec.get('fn') else None
        self.w0 = int(spec.get('w0', '0x0'), 16)
        self.args = {k: int(v, 16) for k, v in (spec.get('args') or {}).items()}
        self.max_uses = int(spec.get('max_uses', 1))
        self.uses = 0

    def usable(self):
        return self.uses < self.max_uses


class Armory:
    """Points, interventions and probes bound to one running target."""

    def __init__(self, target, points=(), interventions=(), probes=(), on_record=None):
        self.target = target
        self.points = [Point(p) for p in points]
        self.interventions = [Intervention(i) for i in interventions]
        self.probes = [Probe(p) for p in probes]
        self.on_record = on_record or (lambda record: None)
        self.records = []
        self.events = []

    def arm(self):
        for point in self.points:
            if point.kind == 'break':
                self.target.arm(point.addr)
            else:
                self.target.watch(point.addr, point.length, ACCESS_CODE[point.kind])
            point.armed = True

    def disarm(self, point):
        if not point.armed:
            return
        if point.kind == 'break':
            self.target.disarm(point.addr)
        else:
            self.target.unwatch(point.addr, point.length, ACCESS_CODE[point.kind])
        point.armed = False

    def disarm_spent(self):
        for point in self.points:
            if point.armed and point.spent():
                self.disarm(point)

    def apply(self, what):
        """Execute one intervention. Returns the evidence it produced."""
        target = self.target
        if what.kind == 'poke':
            target.write_bytes(what.addr, what.bytes)
            return dict(wrote=what.bytes.hex(), at=hex(what.addr))
        if what.kind == 'poison':
            target.write_bytes(what.addr, what.bytes)
            after = target.read_bytes(what.addr, len(what.bytes))
            return dict(wrote=what.bytes.hex(), at=hex(what.addr),
                        readback=after.hex(), touched=after != what.bytes)
        if what.kind == 'key-body':
            # Raw body on the input channel. The field mapping is the operator's.
            target.write_bytes(what.addr, what.bytes) if what.addr else None
            return dict(body=what.bytes.hex(), channel=what.channel)
        if what.kind == 'event':
            name, value = what.property['name'], what.property['value']
            target.qmp.command('qom-set', path='/machine', property=name, value=value)
            return dict(event=name, value=value)
        if what.kind == 'module':
            return dict(loaded=what.file, at=hex(what.addr) if what.addr else None,
                        note='module feeds at launch, see Target(load=)')
        raise ValueError(f'unknown intervention kind: {what.kind}')

    def trigger(self, point):
        """A point fired: record it, apply its interventions, run its probes."""
        if not point.accept():
            self.events.append(dict(id=point.id, dropped='hit throttled'))
            return None
        state = self.target.regs()
        record = dict(id=point.id, t=round(time.monotonic(), 3), pc=hex(state.get('PC', 0)))
        if 'regs' in point.capture:
            record['regs'] = {k: hex(v) for k, v in state.items()}
        for spec in point.capture:
            if spec.startswith('mem:'):
                _, addr, size = spec.split(':')
                record.setdefault('mem', {})[addr] = \
                    self.target.read_bytes(int(addr, 16), int(size)).hex()
        for what in self.interventions:
            if what.at == point.id and not what.done:
                record.setdefault('interventions', {})[what.id] = self.apply(what)
                what.done = True
        for probe in self.probes:
            if probe.at == point.id and probe.usable():
                probe.uses += 1
                if probe.kind == 'skipcall':
                    self.target.set_reg(0, 0, probe.w0)
                    self.target.set_reg(0, 32, state['PC'] + 4)
                    record.setdefault('probes', {})[probe.id] = \
                        dict(kind='skipcall', forced_w0=hex(probe.w0))
                elif probe.kind == 'invoke':
                    self.target.set_reg(0, 0, probe.args.get('x0', 0))
                    if 'x1' in probe.args:
                        self.target.set_reg(0, 1, probe.args['x1'])
                    self.target.set_reg(0, 30, state['PC'])
                    self.target.set_reg(0, 32, probe.fn)
                    record.setdefault('probes', {})[probe.id] = \
                        dict(kind='invoke', fn=hex(probe.fn), args={k: hex(v) for k, v in probe.args.items()})
        self.records.append(record)
        self.on_record(record)
        if point.spent():
            self.disarm(point)
        return record

    def poison_readback(self):
        """Every poison slot, with whether anything touched it since."""
        out = []
        for what in self.interventions:
            if what.kind != 'poison':
                continue
            after = self.target.read_bytes(what.addr, len(what.bytes))
            out.append(dict(id=what.id, at=hex(what.addr), expected=what.bytes.hex(),
                            found=after.hex(), touched=after != what.bytes))
        return out

    def dump_t0(self, path=None, windows=()):
        """Register state per CPU plus optional memory windows at t0."""
        doc = dict(t0=time.time(), cpus=[])
        for cpu in range(self.target.cpu_count()):
            doc['cpus'].append({k: hex(v) for k, v in self.target.regs(cpu).items()})
        for window in windows:
            addr, size = int(window['addr'], 16), int(window['size'])
            doc.setdefault('windows', {})[window['addr']] = \
                self.target.read_bytes(addr, size).hex()
        if path:
            Path(path).write_text(json.dumps(doc, indent=2) + '\n')
        return doc
