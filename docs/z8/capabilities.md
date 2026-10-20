# Capabilities and boundaries

What the model does, and what it does not. State is per 2026-10.

## Capabilities

| Area | State |
|---|---|
| CPU and boot | ARMv8-A 4 cores, TCG, icount; main payload load; secondary chain observable |
| Memory | DRAM banks, service core RAM, demand-backed, no prefilled image data |
| Storage | NAND fixture, NOR model, SDHCI, NVMe behind DesignWare PCIe |
| Capture path | RAW input, demosaic and resampling, NV16 capture stream, thumbnails |
| Codec | JPEG backend, 14-bit lossless output |
| Graphics | path, image, clear engines; ring submit with admission, rejection accounting, completion tracking |
| DMA | GDMA, PDMA, statistics channels with bounded extents |
| Input | key-body injection channel, navigation, orientation, GPIO fixtures |
| Service core | MCU peer transport, serial, I2C subset, event model, timer and counter models |
| PCIe | DBI and unrolled ATU adapter, link diagnostics, INTx model |
| Observation | gdbstub points and watches, QMP/HMP, qtest, reject-path trace |
| Intervention | memory and register write, call injection, call skip, poison writes |
| Verification | criteria set, judge, report |

## Boundaries

| Boundary | State |
|---|---|
| Release-mode input simulation | partial |
| Coprocessor microcode | no execution model |
| Second-stage load chain | no image support |
| Physical sensor and optics | not modeled; inputs are synthetic and explicit |
| Physical codec timing | functional only |
| Cycle accuracy | not claimed; icount with a functional clock |

Unmodeled access is reported as `Z8_UNKNOWN`. It is never silently accepted.
Unsupported command words are rejected and accounted (`Z8_GRAPHICS_DMA_UNMODELED`
and friends). Silence is not a pass.

## Not in this tree

Camera firmware, firmware coordinates, key-body field mapping, camera data,
user settings samples. The operator supplies firmware and inputs locally.
