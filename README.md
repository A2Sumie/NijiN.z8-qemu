# NijiN.z8-qemu

<p align="center"><img src="assets/lockup/nijin-lockup-transparent.png" alt="NijiN" width="420"></p>

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
```

One firmware build in, one problem report out. Runtime detectors judge the build
as it runs and report the problem class with its evidence: count overrun, an
overrun landing on a live object, a guard that allows or skips everything, crash
or restart loop, twin value drift, write past a table boundary, memory envelope
violation, silent state gate, frame count past the tier cap. A detector without
its inputs reports not exercised. It never reports pass. See [verify/README.md](verify/README.md)
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
| Verification | runtime detectors, problem report |

Boundaries: release-mode input simulation is partial, coprocessor microcode has
no execution model, and the second-stage load chain has no image support. Unmodeled
access is reported as `Z8_UNKNOWN`, never silently accepted. Full list in
[docs/z8/capabilities.md](docs/z8/capabilities.md).

## QA

```sh
python3 verify/qa/z8qa.py run --observations <dir> --out qa-out --build <build>
```

The daily-use QA battery: power, shooting modes, shutter, live view, playback,
recording, menus, cards, battery, USB, error recovery. One command, one
PASS/FAIL report per item. See [verify/qa/README.md](verify/qa/README.md).

## Debug

```sh
python3 debug/z8debug.py attach --qemu build/qemu-system-aarch64 \
    --firmware <your build> --out run-01 --observe debug/local/observe.json --seconds 60
```

Breakpoints and watchpoints with one-shot and hit throttling, instruction trace
with filters, probes (skip a call, call a routine, storm limits), intervention
(memory poke, poison slots, key-body injection, event feeding, module feeding),
DMA ledger, t0 dump, screen capture. Hooks are the tables: schema and empty
templates ship with the tree, values live in `debug/local/`. See
[debug/README.md](debug/README.md) and [docs/z8/debug.md](docs/z8/debug.md).

## Layout

```
hw/arm/nikon-z8-lab.c        board model
hw/arm/nikon-z8-*.h          capture, pixel, codec, PCIe path models
verify/                      dynamic verification layer
docs/z8/                     model, verification and capability notes
```

## License

GPL-3.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Brand assets in `assets/` are CC BY-SA 4.0, see [assets/ASSETS.md](assets/ASSETS.md).

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
```

一个固件构建进去，一份问题报告出来。运行期检测器随跑随判，报出问题类别与证据：
计数越界、越界落点打在活对象上、guard 全放行或全跳过、开机崩与重启循环、孪生漂移、
越界写表、内存包络越限、静默状态门、帧数超档位。检测器缺输入记"未验证"，绝不记通过。
见 [verify/README.md](verify/README.md)、[docs/z8/verify.md](docs/z8/verify.md)。

## QA

日常常规使用面回归：开机/关机/休眠唤醒、拍照（P/A/S/M、单拍/连拍/自拍、半按全按）、
实时取景/翻转屏、回放（放大/保护/删除/幻灯片/直方图）、录像、菜单与常用设置、
换卡/双卡/卡满/格式化、电量、USB、常规报错恢复。一条命令出 PASS/FAIL 报告，
触达不到的面记 NOT_EXERCISED 并写清替代手段。见 [verify/qa/README.md](verify/qa/README.md)。

## 调试

```sh
python3 debug/z8debug.py attach --qemu build/qemu-system-aarch64 \
    --firmware <你的构建> --out run-01 --observe debug/local/observe.json --seconds 60
```

断点与观察点（一发即撤、命中泄压）、单指令 trace 与过滤、探针（skipcall/调用/风暴上限）、
干预（内存 poke、毒化槽、键体注入、事件喂入、模块喂入）、DMA 台账、t0 转储、屏幕捕获。
挂点=表：schema 与空模板随树分发，取值在 `debug/local/`。见 [debug/README.md](debug/README.md)、
[docs/z8/debug.md](docs/z8/debug.md)。

## 能力

见上表。边界：release 模式输入仿真半开、协处理器微码无执行模型、二级装载链无镜像支持。
未建模访问报 `Z8_UNKNOWN`，绝不静默放行。全表见 [docs/z8/capabilities.md](docs/z8/capabilities.md)。

## 许可

GPL-3.0，见 [LICENSE](LICENSE)、[NOTICE](NOTICE)。
`assets/` 品牌素材为 CC BY-SA 4.0，见 [assets/ASSETS.md](assets/ASSETS.md)。
