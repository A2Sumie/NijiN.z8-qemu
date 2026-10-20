# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Execute one scenario against one emulator run and record observations.

The scenario is data. Every address, byte string and expected value comes from
the scenario file, so the layer carries no firmware coordinate and no key-body
field. The operator writes their own scenario; templates live in scenarios/.
"""
import hashlib
import json
import time
from pathlib import Path

from guestlink import Guest

X0, LR, PC = 0, 30, 32


def _int(value):
    return int(value, 16) if isinstance(value, str) else int(value)


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


class ScenarioError(RuntimeError):
    pass


def _resolve(block, named):
    """Fill `*_from` keys in a scenario block with the named reads of the run."""
    out = {}
    for key, value in block.items():
        if key.endswith('_from'):
            out[key[:-5]] = named.get(value)
        else:
            out[key] = value
    return out


def run(scenario_path, out_dir, *, firmware=None, qemu=None, overrides=()):
    spec = json.loads(Path(scenario_path).read_text())
    if spec.get('schema') != 1:
        raise ScenarioError('unsupported scenario schema')
    for key, value in overrides.items():
        spec[key] = value
    fw = Path(firmware or spec['firmware'])
    qm = Path(qemu or spec['qemu'])
    machine = spec['machine']
    if isinstance(machine, list):
        machine = ','.join(machine)
    obs = dict(reads={}, named={}, count_sources={}, poison_touch=[], poison_armed=[],
               ownerless_writes=[], ownerless_armed=[], guard=None, twin_sources={},
               ring=None, state_gate=[], frame_tier=None,
               rejections=[], accepts_unmodeled=[], crash=dict(seen=False, kind=None),
               trace=[], hits=[])
    poison = {p['tag']: p for p in spec.get('poison', [])}
    written = {}
    guest = Guest(qemu=qm, machine=machine, firmware=fw,
                  out=out_dir, load_addr=_int(spec.get('load_addr', '0x40160000')),
                  raw=spec.get('raw'), ram=spec.get('ram', '1024M'),
                  smp=spec.get('smp', 4), extra=spec.get('extra', ()))
    with guest:
        started = time.monotonic()
        for index, step in enumerate(spec.get('steps', [])):
            do = step['do']
            if do == 'wait_pc':
                state = guest.wait_pc(_int(step['pc']), timeout=step.get('timeout', 300))
                obs['hits'].append(dict(step=index, pc=hex(_int(step['pc'])),
                                        regs={k: hex(v) for k, v in state.items()}))
            elif do == 'read_mem':
                addr, size = _int(step['addr']), _int(step.get('size', 4))
                raw = guest.read_bytes(addr, size)
                obs['reads'][step.get('as', hex(addr))] = raw.hex()
                if step.get('as'):
                    obs['named'][step['as']] = int.from_bytes(raw, 'little')
            elif do == 'write_mem':
                guest.write_bytes(_int(step['addr']), bytes.fromhex(step['bytes']))
            elif do == 'set_reg':
                guest.set_reg(step.get('cpu', 0), _int(step['reg']), _int(step['value']))
            elif do == 'poison':
                entry = poison[step['tag']]
                addr, data = _int(entry['addr']), bytes.fromhex(entry['bytes'])
                guest.write_bytes(addr, data)
                written[step['tag']] = (addr, data, entry.get('role', 'poison'))
            elif do == 'invoke':
                cpu = step.get('cpu', 0)
                state = guest.regs(cpu)
                guest.set_reg(cpu, X0, _int(step.get('x0', 0)))
                if 'x1' in step:
                    guest.set_reg(cpu, 1, _int(step['x1']))
                guest.set_reg(cpu, LR, state['PC'])
                guest.set_reg(cpu, PC, _int(step['fn']))
                guest.cont()
                deadline = time.monotonic() + step.get('timeout', 60)
                while guest.running() and time.monotonic() < deadline:
                    time.sleep(.01)
                guest.stop()
            elif do == 'skip_call':
                cpu = step.get('cpu', 0)
                state = guest.regs(cpu)
                if state['PC'] != _int(step['pc']):
                    raise ScenarioError(f"skip_call at {step['pc']}: PC is {state['PC']:#x}")
                guest.set_reg(cpu, X0, _int(step.get('w0', 0)))
                guest.set_reg(cpu, PC, state['PC'] + 4)
            elif do == 'cont':
                guest.cont()
                time.sleep(step.get('seconds', 5))
                guest.stop()
            elif do == 'snapshot':
                pass
            else:
                raise ScenarioError(f'unknown step: {do}')
            obs['trace'] += [line for line in guest.log().splitlines() if line.strip()]

        for tag, (addr, data, role) in written.items():
            after = guest.read_bytes(addr, len(data))
            entry = dict(tag=tag, addr=hex(addr), expected=data.hex(), found=after.hex())
            if after != data:
                obs['ownerless_writes' if role == 'boundary' else 'poison_touch'].append(entry)
            obs['ownerless_armed' if role == 'boundary' else 'poison_armed'].append(tag)
        obs['trace'] += [line for line in guest.log().splitlines() if line.strip()]
        obs['elapsed_sec'] = round(time.monotonic() - started, 1)

    named = obs['named']
    markers = spec.get('crash', {}).get('trace_markers', ['Z8_UNKNOWN'])
    for line in obs['trace']:
        for marker in markers:
            if marker in line:
                obs['crash'] = dict(seen=True, kind=marker)
    for item in spec.get('rejections', []):
        obs['rejections'].append(dict(
            id=item['id'], expected=item.get('trace', item['id']),
            seen=any(item.get('trace', item['id']) in line for line in obs['trace'])))
    obs['accepts_unmodeled'] = [dict(id=a['id'], detail=a.get('detail', ''))
                                for a in spec.get('accepts_unmodeled', [])]
    counts = spec.get('counts', {})
    if counts.get('extent') is not None:
        obs['count_sources'] = {src['id']: named.get(src['read'])
                                for src in counts.get('sources', [])}
        obs['count_extent'] = counts['extent']
    for pair in (spec.get('twins') or {}).get('pairs', []):
        obs['twin_sources'][pair['id']] = {r: named.get(r) for r in pair['reads']}
    if spec.get('ring'):
        obs['ring'] = _resolve(spec['ring'], named)
    if spec.get('guard'):
        obs['guard'] = _resolve(spec['guard'], named)
    if spec.get('frame_tier'):
        obs['frame_tier'] = _resolve(spec['frame_tier'], named)
    for gate in spec.get('state_gate', []):
        obs['state_gate'].append(_resolve(gate, named))
    run_doc = dict(schema=1, kind='z8verify-run', scenario=spec.get('name', Path(scenario_path).stem),
                   firmware=dict(path=str(fw), sha256=sha256(fw), bytes=fw.stat().st_size),
                   emulator=dict(path=str(qm), sha256=sha256(qm), argv=guest.argv),
                   observations=obs, checks=guest.data['checks'], error=guest.data['error'],
                   window_completed=guest.data['error'] is None)
    (Path(out_dir) / 'run.json').write_text(json.dumps(run_doc, indent=2) + '\n')
    return run_doc
