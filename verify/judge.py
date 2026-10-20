# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Judge one recorded run against the criteria set.

Verdicts per criterion: PASS, FAIL, NOT_EXERCISED.
Verdict per build: CLEAN, PROBLEM_FOUND, UNVERIFIED.
A criterion without its inputs is NOT_EXERCISED and the build is UNVERIFIED.
"""
import json
from pathlib import Path

PASS, FAIL, NOT_EXERCISED = 'PASS', 'FAIL', 'NOT_EXERCISED'
CLEAN, PROBLEM_FOUND, UNVERIFIED = 'CLEAN', 'PROBLEM_FOUND', 'UNVERIFIED'

HERE = Path(__file__).resolve().parent


def load_criteria(path=None):
    doc = json.loads(Path(path or HERE / 'criteria.json').read_text())
    return doc['criteria']


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
        return FAIL, 'count sources disagree: ' + json.dumps(sources, sort_keys=True)
    if extent is not None and values[0] != extent:
        return FAIL, f'count {values[0]} != table extent {extent}: ' + json.dumps(sources, sort_keys=True)
    return PASS, 'count sources agree: ' + json.dumps(sources, sort_keys=True)


def _poison_touch(obs):
    armed = obs.get('poison_armed') or []
    touches = obs.get('poison_touch') or []
    if not armed and not touches:
        return NOT_EXERCISED, 'no poisoned region was armed'
    if touches:
        return FAIL, 'poisoned region touched: ' + json.dumps(touches, sort_keys=True)
    return PASS, f'{len(armed)} poisoned region(s) untouched'


def _fail_closed(obs):
    accepts = obs.get('accepts_unmodeled') or []
    if accepts:
        return FAIL, 'unmodeled accept: ' + json.dumps(accepts, sort_keys=True)
    declared = obs.get('rejections') or []
    if not declared:
        return NOT_EXERCISED, 'no reject path was declared'
    unseen = [d['id'] for d in declared if not d.get('seen')]
    if unseen:
        return NOT_EXERCISED, 'reject path declared but not exercised: ' + ', '.join(unseen)
    return PASS, f"{len(declared)} reject path(s) rejected as expected"


def _no_crash(obs):
    crash = obs.get('crash') or {}
    if crash.get('seen'):
        return FAIL, f"crash symptom observed: {crash.get('kind')}"
    return PASS, 'no crash symptom in the observed window'


RULES = {
    'count_sources_consistent': _count_sources,
    'no_poison_touch': _poison_touch,
    'fail_closed': _fail_closed,
    'no_crash': _no_crash,
}


def judge(run_doc, criteria=None):
    obs = run_doc.get('observations', {})
    results = []
    for crit in criteria or load_criteria():
        rule = RULES[crit['rule']]
        status, detail = rule(obs)
        if status == PASS and not run_doc.get('window_completed', True):
            status, detail = NOT_EXERCISED, 'run window incomplete: ' + detail
        results.append(dict(id=crit['id'], klass=crit['class'], title=crit['title'],
                            status=status, detail=detail))
    if any(r['status'] == FAIL for r in results):
        verdict = PROBLEM_FOUND
    elif any(r['status'] == NOT_EXERCISED for r in results):
        verdict = UNVERIFIED
    else:
        verdict = CLEAN
    return dict(verdict=verdict, results=results)
