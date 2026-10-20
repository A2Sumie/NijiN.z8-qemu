# verify — runtime detectors

Run one firmware build. Get a problem report.

```sh
python3 verify/z8verify.py run --scenario calibration/<case>.json --out run-01
```

Detectors live on the observation layer. They judge every run as it happens and
report the problem class with its evidence. The report lists the problems first,
then each detector with its status and evidence.

| Detector | Class | Fires on |
|---|---|---|
| V1 | count overrun | a count that no longer matches the table it walks |
| V2 | live-object landing | an overrun that lands on a poisoned or live slot |
| V3 | guard bound | a guard that allows everything or skips everything |
| V4 | crash / loop | diagnostic dumps and restart loops |
| V5 | twin drift | one value carried by several sources, raised in one |
| V6 | boundary write | a write past a table nobody owns |
| V7 | memory envelope | a request past the envelope, a ring that delivers zero frames |
| V8 | silent state gate | sticky state, dual configuration, a gate that says nothing |
| V9 | frame tier | a frame count past the tier cap |

Status per detector: `PASS`, `FAIL`, `not exercised`. A detector without its
inputs is `not exercised`, never `PASS`. Verdict per build: `CLEAN`,
`PROBLEM_FOUND`, `UNVERIFIED`. A run declares which detectors it feeds; the
verdict covers those and says so for the rest.

Files:

| File | Role |
|---|---|
| `z8verify.py` | CLI: run, adopt, judge, report, selftest |
| `guestlink.py` | one emulator process: QMP, qtest, gdbstub, guest memory |
| `scenario.py` | drives the run, records `run.json` |
| `detectors.json` | the detector set |
| `judge.py` | detector evaluation |
| `report.py` | problem report |
| `calibration/` | cases that prove a detector fires on a known-bad build and stays quiet on a clean one |
| `local/` | your own cases. Not distributed. |

Calibration is how the detectors are proven, not the product:

```sh
python3 verify/z8verify.py selftest
```

Method notes: [../docs/z8/verify.md](../docs/z8/verify.md).
Model notes: [../docs/z8/machine.md](../docs/z8/machine.md).
