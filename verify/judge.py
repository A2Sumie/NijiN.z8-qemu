# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Runtime detectors. Every build is judged against them as it runs.

Verdicts per criterion: PASS, FAIL, NOT_EXERCISED.
Verdict per build: CLEAN, PROBLEM_FOUND, UNVERIFIED.
A criterion without its inputs is NOT_EXERCISED and the build is UNVERIFIED.
"""
import json
from pathlib import Path

PASS, FAIL, NOT_EXERCISED = 'PASS', 'FAIL', 'NOT_EXERCISED'
CLEAN, PROBLEM_FOUND, UNVERIFIED = 'CLEAN', 'PROBLEM_FOUND', 'UNVERIFIED'

HERE = Path(__file__).resolve().parent


def load_detectors(path=None):
    doc = json.loads(Path(path or HERE / 'detectors.json').read_text())
    return doc['detectors']


load_criteria = load_detectors


def _dump(value):
    return json.dumps(value, sort_keys=True)


def _count_sources(obs):
    sources = obs.get('count_sources') or {}
    extent = obs.get('count_extent')
    if not sources:
        return NOT_EXERCISED, 'no count source was read'
    missing = [k for k, v in sources.items() if v is None]
    if missing:
        return NOT_EXERCISED, 'count source not read: ' + ', '.join(missing)
    values = sorted(set(sources.values()))
    if len(values) > 1:
        return FAIL, 'count sources disagree: ' + _dump(sources)
    if extent is not None and values[0] != extent:
        return FAIL, f'count {values[0]} != table extent {extent}: ' + _dump(sources)
    return PASS, 'count sources agree: ' + _dump(sources)


def _poison_touch(obs):
    armed = obs.get('poison_armed') or []
    touches = obs.get('poison_touch') or []
    if not armed and not touches:
        return NOT_EXERCISED, 'no poisoned region was armed'
    if touches:
        return FAIL, 'poisoned region touched: ' + _dump(touches)
    return PASS, f'{len(armed)} poisoned region(s) untouched'


def _guard_balanced(obs):
    gate = obs.get('guard') or {}
    if not gate:
        return NOT_EXERCISED, 'no guard case was exercised'
    if gate.get('silent'):
        return FAIL, 'guard acted without a verdict: ' + _dump(gate)
    allowed = gate.get('valid_allowed')
    rejected = gate.get('invalid_rejected')
    if allowed is None or rejected is None:
        return NOT_EXERCISED, 'guard needs both a valid case and an invalid case'
    if allowed and rejected:
        return PASS, 'valid case allowed, invalid case rejected'
    if not allowed and not rejected:
        return FAIL, 'guard skips everything: ' + _dump(gate)
    return FAIL, 'guard allows everything: ' + _dump(gate)


def _no_crash(obs):
    crash = obs.get('crash') or {}
    if crash.get('seen'):
        return FAIL, f"crash symptom observed: {crash.get('kind')}"
    return PASS, 'no crash symptom in the observed window'


def _twins_consistent(obs):
    twins = obs.get('twin_sources') or {}
    if not twins:
        return NOT_EXERCISED, 'no twin value pair was read'
    for name, values in twins.items():
        if any(v is None for v in values.values()):
            return NOT_EXERCISED, f'twin source not read: {name}'
        if len(set(values.values())) > 1:
            return FAIL, f'twin drift in {name}: ' + _dump(values)
    return PASS, f'{len(twins)} twin group(s) consistent: ' + _dump(twins)


def _no_ownerless_write(obs):
    armed = obs.get('ownerless_armed') or []
    writes = obs.get('ownerless_writes') or []
    if not armed and not writes:
        return NOT_EXERCISED, 'no table boundary was guarded'
    if writes:
        return FAIL, 'write past a table boundary: ' + _dump(writes)
    return PASS, f'{len(armed)} boundary slot(s) untouched'


def _ring_within_envelope(obs):
    ring = obs.get('ring') or {}
    if not ring:
        return NOT_EXERCISED, 'no ring observation'
    requested = ring.get('requested_bytes')
    envelope = ring.get('envelope_bytes')
    delivered = ring.get('delivered_frames')
    if requested is None or delivered is None:
        return NOT_EXERCISED, 'ring observation incomplete: ' + _dump(ring)
    if envelope is not None and requested > envelope:
        return FAIL, f'requested {requested} bytes past envelope {envelope}: ' + _dump(ring)
    if delivered <= 0:
        return FAIL, 'ring delivered zero frames: ' + _dump(ring)
    return PASS, f'{delivered} frame(s) delivered inside the envelope: ' + _dump(ring)


def _state_gate_explicit(obs):
    gates = obs.get('state_gate') or []
    if not gates:
        return NOT_EXERCISED, 'no state gate case was exercised'
    silent = [g for g in gates if g.get('silent')]
    if silent:
        return FAIL, 'state gate acted without a verdict: ' + _dump(silent)
    stale = [g for g in gates if g.get('expected_clear') and not g.get('cleared')]
    if stale:
        return FAIL, 'stale state survived the clear: ' + _dump(stale)
    wrong = [g for g in gates if g.get('verdict') is not None and
             g.get('expected_verdict') is not None and g['verdict'] != g['expected_verdict']]
    if wrong:
        return FAIL, 'verdict differs from the expected one: ' + _dump(wrong)
    return PASS, f'{len(gates)} state gate case(s) explicit'


def _frame_within_tier(obs):
    tier = obs.get('frame_tier') or {}
    if not tier:
        return NOT_EXERCISED, 'no frame tier observation'
    frames, cap = tier.get('frames'), tier.get('tier_cap')
    if frames is None or cap is None:
        return NOT_EXERCISED, 'frame tier observation incomplete: ' + _dump(tier)
    if frames > cap:
        return FAIL, f'frames {frames} past tier cap {cap}: ' + _dump(tier)
    return PASS, f'frames {frames} within tier cap {cap}'


RULES = {
    'count_sources_consistent': _count_sources,
    'no_poison_touch': _poison_touch,
    'guard_balanced': _guard_balanced,
    'no_crash': _no_crash,
    'twins_consistent': _twins_consistent,
    'no_ownerless_write': _no_ownerless_write,
    'ring_within_envelope': _ring_within_envelope,
    'state_gate_explicit': _state_gate_explicit,
    'frame_within_tier': _frame_within_tier,
}


def judge(run_doc, detectors=None):
    """Judge one run. A run declares which detectors it feeds; the verdict covers
    those. Detectors outside the declared scope are reported, never passed."""
    obs = run_doc.get('observations', {})
    scope = set(obs.get('detectors') or [])
    results = []
    for crit in detectors or load_detectors():
        in_scope = not scope or crit['id'] in scope
        status, detail = RULES[crit['rule']](obs)
        if status == PASS and not run_doc.get('window_completed', True):
            status, detail = NOT_EXERCISED, 'run window incomplete: ' + detail
        if not in_scope and status == NOT_EXERCISED:
            detail = 'out of scope for this run'
        results.append(dict(id=crit['id'], pit=crit.get('pit'), klass=crit['class'],
                            title=crit['title'], status=status, detail=detail,
                            in_scope=in_scope))
    scoped = [r for r in results if r['in_scope']]
    if any(r['status'] == FAIL for r in scoped):
        verdict = PROBLEM_FOUND
    elif any(r['status'] == NOT_EXERCISED for r in scoped):
        verdict = UNVERIFIED
    else:
        verdict = CLEAN
    return dict(verdict=verdict, results=results)
