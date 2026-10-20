# verify — dynamic verification layer

Run one firmware build. Get a problem report.

```sh
python3 verify/z8verify.py run    --scenario scenarios/overrun-count-pair.json --out run-01
python3 verify/z8verify.py judge  --run run-01/run.json
python3 verify/z8verify.py report --run run-01/run.json
```

Files:

| File | Role |
|---|---|
| `z8verify.py` | CLI: run, adopt, judge, report, selftest |
| `guestlink.py` | one emulator process: QMP, qtest, gdbstub, guest memory |
| `scenario.py` | scenario executor, records `run.json` |
| `criteria.json` | the criteria set (V1–V4) |
| `judge.py` | PASS / FAIL / NOT_EXERCISED per criterion, CLEAN / PROBLEM_FOUND / UNVERIFIED per build |
| `report.py` | markdown report |
| `scenarios/` | scenario templates with placeholder coordinates |
| `local/` | your own scenarios. Not distributed. |

A scenario carries every address and byte string it uses. The layer carries none.
Copy a template into `local/`, fill in the values your build needs, run it.

`selftest` proves the judge separates a bad build from a clean one without
starting the emulator:

```sh
python3 verify/z8verify.py selftest
```

Method notes: [../docs/z8/verify.md](../docs/z8/verify.md).
Model notes: [../docs/z8/machine.md](../docs/z8/machine.md).
