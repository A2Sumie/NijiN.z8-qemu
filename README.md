# NijiN.z8-qemu

QEMU 11.1.1 with a Z8 camera board model and a dynamic verification layer.

Mission: give it a firmware build, run it, get a problem report. Emulator plus
dynamic verification finds bad firmware builds: out-of-bounds walks, bad
configuration, bad loading, count drift between sources, envelope violations.

This is a research testbench. The board model is functional and experimental. It
is not a hardware specification and not a complete camera.

## Build

```sh
./configure --target-list=aarch64-softmmu
make -j$(nproc)
```

macOS 17+ SDKs obsolete the ParavirtualizedGraphics API, so add `-Dpvg=disabled`
there. First configure fetches the `dtc` and `keycodemapdb` subprojects unless
the system provides them.

Result: `build/qemu-system-aarch64` with the machines `nikon-z8-lab` and
`nikon-z8-full-lab`.

## Run

```sh
./build/qemu-system-aarch64 \
  -M nikon-z8-lab,bootstrap-fixtures=on,serial-fixture=on \
  -accel tcg,thread=single -icount shift=0,sleep=on \
  -smp 4 -m 1024M -display none -S \
  -device loader,file=<firmware.bin>,addr=0x40160000,force-raw=on,cpu-num=0
```

Machine properties select the modeled devices and input fixtures. See
[docs/z8/machine.md](docs/z8/machine.md).

## Verify

```sh
python3 verify/z8verify.py run --scenario <scenario.json> --out <run-dir>
python3 verify/z8verify.py judge --run <run-dir>/run.json
python3 verify/z8verify.py report --run <run-dir>/run.json
```

One firmware build in, one report out. The report states, per criterion, whether
the build passed, failed, or was not exercised. See [verify/README.md](verify/README.md)
and [docs/z8/verify.md](docs/z8/verify.md).

## Capability

| Area | State |
|---|---|
| CPU | ARMv8-A, 4 cores, TCG, icount |
| Boot and loading | generic loader, main payload load, secondary chain observable |
| Storage | NAND fixture, NOR model, SDHCI, NVMe behind DesignWare PCIe |
| Capture path | RAW input, demosaic and resampling, NV16 capture stream, thumbnails |
| Graphics | path engine, image engine, clear engine, ring submit with rejection accounting |
| Codec | JPEG backend, 14-bit lossless output |
| Input | key-body injection channel, navigation fixtures |
| Service core | MCU peer transport, event model, timer and counter models |
| Observation | gdbstub breakpoints and watches, QMP/HMP, qtest, trace on reject paths |
| Intervention | memory read/write, register write, call injection, call skip, poison writes |
| Verification | criteria set, judge, report |

Boundaries: release-mode input simulation is partial, coprocessor microcode has
no execution model, and the second-stage load chain has no image support. Unmodeled
access is reported as `Z8_UNKNOWN`, never silently accepted. Full list in
[docs/z8/capabilities.md](docs/z8/capabilities.md).

## Layout

```
hw/arm/nikon-z8-lab.c        board model
hw/arm/nikon-z8-*.h          capture, pixel, codec, PCIe path models
verify/                      dynamic verification layer
docs/z8/                     model, verification and capability notes
```

## License

GPL-3.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE).

---

# NijiN.z8-qemu（中文）

QEMU 11.1.1 + Z8 相机板级模型 + 动态验证层。

使命：给一个固件构建，跑起来，出问题报告。模拟器加动态验证找出问题固件：
越界走查、坏配置、坏装载、计数多源漂移、包络违规。

这是研究用试验台。板级模型是功能性、实验性的。它不是硬件规格，也不是完整相机。

## 构建

```sh
./configure --target-list=aarch64-softmmu
make -j$(nproc)
```

macOS 17+ SDK 废弃 ParavirtualizedGraphics API，加 `-Dpvg=disabled`。
首次 configure 会取 `dtc` 与 `keycodemapdb` 子项目，系统已有则不取。

产物：`build/qemu-system-aarch64`，含 `nikon-z8-lab`、`nikon-z8-full-lab` 两台机器。

## 运行

```sh
./build/qemu-system-aarch64 \
  -M nikon-z8-lab,bootstrap-fixtures=on,serial-fixture=on \
  -accel tcg,thread=single -icount shift=0,sleep=on \
  -smp 4 -m 1024M -display none -S \
  -device loader,file=<firmware.bin>,addr=0x40160000,force-raw=on,cpu-num=0
```

机器属性选择建模设备与输入 fixtures，见 [docs/z8/machine.md](docs/z8/machine.md)。

## 验证

```sh
python3 verify/z8verify.py run --scenario <scenario.json> --out <run-dir>
python3 verify/z8verify.py judge --run <run-dir>/run.json
python3 verify/z8verify.py report --run <run-dir>/run.json
```

一个固件构建进去，一份报告出来。报告逐条判据写明：通过、未通过、未验证。
见 [verify/README.md](verify/README.md)、[docs/z8/verify.md](docs/z8/verify.md)。

## 能力

见上表。边界：release 模式输入仿真半开、协处理器微码无执行模型、二级装载链无镜像支持。
未建模访问报 `Z8_UNKNOWN`，绝不静默放行。全表见 [docs/z8/capabilities.md](docs/z8/capabilities.md)。

## 许可

GPL-3.0，见 [LICENSE](LICENSE)、[NOTICE](NOTICE)。
