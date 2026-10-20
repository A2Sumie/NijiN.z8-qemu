# Runtime verification

Run one firmware build. Get a problem report.

```sh
python3 verify/z8verify.py run    --scenario <scenario.json> --out <run-dir>
python3 verify/z8verify.py judge  --run <run-dir>/run.json
python3 verify/z8verify.py report --run <run-dir>/run.json
```

`run` drives the emulator and hands the observations to the detectors. The
report is a problem report: which problem class, with what evidence. One build
in, one problem report out.

## Detectors

| Criterion | Class | Catches |
|---|---|---|
| V1 | multi-source consistency | a count raised in one place while the backing table keeps its own extent: the walk runs one entry too far |
| V2 | envelope assertion | an overrun that lands on a poisoned or live object instead of padding |
| V3 | stub behaviour | fail-open and fail-closed: a reject path that silently accepts, or a declared path never exercised |
| V4 | crash symptom | diagnostic dumps and restart loops in the observed window |

Status per detector: `PASS`, `FAIL`, `NOT_EXERCISED`. A detector without its
inputs is `NOT_EXERCISED`, never `PASS`. Verdict per build: `CLEAN`,
`PROBLEM_FOUND`, `UNVERIFIED`. A run declares which detectors it feeds; the
verdict covers those and the report says so for the rest.

## Observation and intervention

Through the emulator's own channels: gdbstub breakpoints and watches, QMP and HMP,
qtest memory access, trace on the reject paths.

| Step | Action |
|---|---|
| `wait_pc` | run until a point is reached, record the register state |
| `read_mem` / `write_mem` | read or write guest physical memory |
| `poison` | write a tagged pattern into a region that must stay untouched |
| `invoke` | call a guest function at a point and record the result |
| `skip_call` | step past a call and force its result, for gate control |
| `set_reg` | set a guest register |
| `cont` | let the guest run for a window |
| `snapshot` | take the recorded state |

## Calibration

A scenario is JSON. It carries every address, byte string and expected value, so
the layer itself holds no firmware coordinate. Cases: `verify/calibration/`,
one per problem class, each with a known-bad build and a clean one. Real cases
with real coordinates belong in `verify/local/`, which is not distributed.

Rules that keep a comparison valid:

- Two runs that differ in one variable need an innocent control. A crash in both
  condemns the scenario, not the variable.
- Arm observation points after boot, never during it.
- A control run under the default layout is not evidence of safety. Layout
  poisoning turns a silent one-entry overrun into an observable one.

## Feeding observations from another driver

Any driver that can record observations can be judged:

```sh
python3 verify/z8verify.py adopt --observations <obs.json> --scenario <scenario.json> --out run.json
```

`obs.json` shape: `count_sources`, `poison_armed`, `poison_touch`, `rejections`,
`accepts_unmodeled`, `crash`, `hits`, `reads`. The scenario supplies `count_extent`
and the poison declarations.

## Detector calibration

```sh
python3 verify/z8verify.py selftest
```

Proves the judge separates a bad build from a clean one, and that missing inputs
never read as clean.
