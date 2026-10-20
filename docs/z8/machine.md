# Z8 board model

Machine `nikon-z8-lab`. Variant `nikon-z8-full-lab` adds the capture path fixtures.
Functional and experimental. Not a hardware specification.

## What is modeled

| Block | Behaviour |
|---|---|
| CPU | ARMv8-A, 4 cores, TCG, icount virtual clock |
| Interrupts | GICv3/GICv5 wiring, INTID registration paths, W1C semantics |
| Boot | generic loader, main payload load, service core event model |
| Storage | NAND fixture (virtual blank geometry), NOR model, SDHCI, NVMe behind DesignWare PCIe |
| Capture | RAW input, RGGB demosaic and resampling, NV16 capture stream, thumbnail path, JPEG backend, 14-bit lossless output |
| Graphics | path engine (stroke and fill), image engine, clear engine, ring submit with per-command admission and rejection accounting |
| DMA | GDMA/PDMA/statistics channels, bounded extents, unmodeled commands reported |
| Timers | multi-channel counters and periods, timer-derived events |
| Input | key-body injection channel, navigation and orientation fixtures |
| Service core | MCU peer transport, serial channels, I2C subset, GPIO fixture, PCIe link diagnostics |

## Machine properties

`-machine nikon-z8-lab,<property>=on` selects models and fixtures. Two families:

- `*-model=on` enables a functional device model (for example `graphics-path-model`).
- `*-fixture=on` supplies an explicit input (for example `bootstrap-fixtures`, `adc-input=256:512:768:1023`).

Read-only `*-state` properties dump the model state at runtime. `qemu-system-aarch64
-machine nikon-z8-lab,help` lists every property.

## Semantics

- Every modeled register has an explicit mask. Writes outside the mask are dropped, not guessed.
- Unmodeled MMIO access emits `Z8_UNKNOWN` in the log and is a fault. Never silent.
- Rejected submissions are accounted and logged (`Z8_GRAPHICS_REJECT`, `Z8_GRAPHICS_DMA_UNMODELED`,
  `Z8_1524_MVD_REJECT`, …). Rejection is the correct answer for an unsupported command word.
- RAM is demand-backed and never prefilled with image data. No readiness or image-completion
  event is invented.
- Timings are functional. This is not a cycle-accurate model.

## Scope

Board-level behaviour only: register semantics, DMA extents, event routing, admission rules.
No camera firmware, no firmware coordinates and no key-body field mapping appear in this tree.
Firmware images and inputs stay with the operator.
