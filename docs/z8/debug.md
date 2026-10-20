# Dynamic debugging

The debugging layer is `debug/`. Channels, points, probes and interventions in
one place, wired to run a build and capture what happened.

| Group | Capability |
|---|---|
| Channels | QMP, HMP, qtest, gdbstub |
| Points | breakpoints, watchpoints (read, write, access), one-shot fire-and-remove, hit throttling and cooldown |
| Trace | `-d in_asm,exec` log, filtered by address range and CPU, repeated blocks collapsed |
| Probes | skip a call and force its result, call a routine, probe storm limit |
| Intervention | memory poke, poison slot with readback, key-body injection, event feeding, module feeding |
| Accounting | DMA ledger by channel and mode, rejections, envelope check |
| Capture | t0 register and memory dump, guest screen dump |

## Hooks

Tables are the hook. The tree ships schema and empty templates:

- `debug/schema/observe.schema.json` and `debug/tables/observe.json` — observation points.
- `debug/schema/inject.schema.json` and `debug/tables/inject.json` — injections.
- `debug/schema/probe.schema.json` and `debug/tables/probe.json` — probes.

The loader checks a table against its schema and refuses it before anything is
armed. The operator fills `debug/local/` (not distributed): addresses, key-body
field mappings, address tables. The format is the schema.

## Discipline

- A point that hits often freezes the guest. Set `one_shot` or `max_hits`.
- Arm observation points after boot, never during it.
- A probe that fires in a loop is a probe storm. Set `max_uses`.
- Coordinates stay local. The tree carries none.

Usage: [../../debug/README.md](../../debug/README.md).
