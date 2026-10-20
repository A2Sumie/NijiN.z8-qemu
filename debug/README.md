# debug — dynamic debugging

Break it, watch it, poke it. This is the debugging capability of the tree: the
channels, the points, the probes and the interventions, wired to run one build
and capture what happened.

```sh
python3 debug/z8debug.py attach --qemu build/qemu-system-aarch64 \
    --firmware <your build> --out run-01 \
    --observe debug/local/observe.json \
    --inject  debug/local/inject.json \
    --probe   debug/local/probe.json \
    --trace run-01/trace.log --trace-filter in:0x40000000-0x41000000,ex:0x40001000-0x40002000 \
    --t0 run-01/t0.json --screendump run-01/screen.ppm --dma run-01/dma.json --seconds 60
```

## Capability

| Capability | Where | Notes |
|---|---|---|
| QMP / HMP | `link.Target` | monitor commands, machine properties, screendump |
| qtest | `link.Target` | physical memory read and write, 8 bytes at a time |
| gdbstub | `link.Target` | breakpoints, watchpoints, registers, continue and stop |
| Breakpoints | `probes.Point` `kind=break` | per point policy, see throttling |
| Watchpoints | `probes.Point` `kind=watch-r/w/a` | read, write or access watch on a guest range |
| One-shot points | `one_shot: true` | fire once, then the point is removed |
| Hit throttling | `max_hits`, `cooldown_s` | the guest freezes on a hit; the throttle keeps a storm from freezing it for good |
| Memory poke | `inject` `kind=poke` | write bytes at a point or at session start |
| Poison slot | `inject` `kind=poison` | tagged write, read back at the end: touched or not |
| Key-body injection | `inject` `kind=key-body` | raw body on the input channel; the field mapping is the operator's |
| Event feeding | `inject` `kind=event` | set a machine input property at runtime (QOM) |
| Module feeding | `--module FILE@ADDR` | load an image at launch through the generic loader |
| Skip a call | `probe` `kind=skipcall` | step past the call and force its result |
| Call a routine | `probe` `kind=invoke` | set arguments, set PC, let it return |
| Probe storm limit | `max_uses` | a probe stops firing after N uses |
| Instruction trace | `--trace` | `-d in_asm,exec` into a file |
| Trace filtering | `--trace-filter`, `--cpus` | by address range and by CPU, repeated blocks collapsed |
| DMA ledger | `--dma` | every admitted transfer by channel and mode, rejections counted, envelope checked |
| t0 dump | `--t0` | registers per CPU and optional memory windows at session start |
| Screen capture | `--screendump` | PPM dump of the guest display |

## Hooks: the tables

The public tree ships the schema and empty templates. The values live with the
operator, under `debug/local/` (not distributed).

| Table | Schema | Template | Holds |
|---|---|---|---|
| Observation points | `schema/observe.schema.json` | `tables/observe.json` | points, kind, address, one-shot, throttle, capture |
| Injections | `schema/inject.schema.json` | `tables/inject.json` | poke, poison, key-body, event, module |
| Probes | `schema/probe.schema.json` | `tables/probe.json` | skipcall, invoke, storm limit |

`loader.py` checks a table against its schema and refuses it before anything is
armed. Fill `debug/local/*.json` from the templates; `z8debug attach` takes
their paths.

## Session record

`attach` writes `debug.json`: every recorded point with its registers and
memory captures, every intervention with its evidence, the poison readback, the
DMA ledger and the trace count.

```sh
python3 debug/z8debug.py selftest
```

Selftest covers the loader, the templates, one-shot and throttle policy, the
probe storm limit, the trace filters and the DMA ledger. No emulator needed.
