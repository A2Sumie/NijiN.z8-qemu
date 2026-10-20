# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Instruction and translation-block trace with filters.

QEMU writes `-d in_asm,exec` logs with one line per translation block and one
disassembly block per translation. This filters them: by address range, by CPU,
and by repetition, so a storm of retranslations does not bury the one line that
matters.
"""
import re
from pathlib import Path

ADDR = re.compile(r'0x([0-9a-fA-F]{4,16})')
CPU = re.compile(r'^Trace\s+(\d+):')


def qemu_trace_args(path, events=('in_asm', 'exec')):
    return ['-d', ','.join(events), '-D', str(Path(path).resolve())]


class TraceFilter:
    def __init__(self, include=(), exclude=(), cpus=None, dedupe=True, limit=200000):
        self.include = [(int(a, 16), int(b, 16)) for a, b in include]
        self.exclude = [(int(a, 16), int(b, 16)) for a, b in exclude]
        self.cpus = None if cpus is None else set(cpus)
        self.dedupe = dedupe
        self.limit = limit
        self.seen = set()
        self.kept = []

    def _wanted(self, line):
        if self.cpus is not None:
            m = CPU.match(line)
            if m and int(m.group(1)) not in self.cpus:
                return False
        hits = [int(a, 16) for a in ADDR.findall(line)]
        if self.include:
            if not any(lo <= h < hi for h in hits for lo, hi in self.include):
                return False
        if self.exclude and any(lo <= h < hi for h in hits for lo, hi in self.exclude):
            return False
        return True

    def feed(self, line):
        line = line.rstrip('\n')
        if not self._wanted(line):
            return None
        if self.dedupe:
            key = ADDR.sub('x', line.strip())
            if key in self.seen:
                return None
            self.seen.add(key)
        if len(self.kept) >= self.limit:
            return None
        self.kept.append(line)
        return line

    def filter_file(self, path):
        out = []
        with open(path, 'r', errors='replace') as f:
            for line in f:
                hit = self.feed(line)
                if hit is not None:
                    out.append(hit)
        return out
