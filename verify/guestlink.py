# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Drive one emulator process: QMP, qtest, gdbstub, guest memory.

Primitives only. Scenario steps live in scenario.py, criteria in judge.py.
No firmware address, no key-body field and no rig detail belongs here.
"""
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path


class QMP:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(5)
        self.sock.connect(str(path))
        self.fp = self.sock.makefile('rwb', buffering=0)
        self.events = []
        self.greeting = json.loads(self.fp.readline())
        self.command('qmp_capabilities')

    def command(self, name, **args):
        self.fp.write(json.dumps({'execute': name, 'arguments': args}).encode() + b'\n')
        while True:
            line = self.fp.readline()
            if not line:
                raise EOFError('QMP disconnected')
            item = json.loads(line)
            if 'event' in item:
                self.events.append(item)
            elif 'error' in item:
                raise RuntimeError(item['error'])
            elif 'return' in item:
                return item['return']

    def hmp(self, command, cpu=0):
        return self.command('human-monitor-command', **{'command-line': command, 'cpu-index': cpu})

    def close(self):
        self.fp.close()
        self.sock.close()


class Guest:
    """One emulator run. Use as a context manager."""

    def __init__(self, *, qemu, machine, firmware, out, load_addr=None, raw=None,
                 ram='1024M', smp=4, extra=(), gdb=True):
        if os.name == 'nt':
            raise ValueError('Windows is not supported; use macOS or Linux')
        self.qemu = Path(qemu).resolve()
        self.firmware = Path(firmware).resolve()
        if not self.qemu.is_file() or not self.firmware.is_file():
            raise ValueError('qemu binary and firmware image must exist')
        self.out = Path(out).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.temp = tempfile.TemporaryDirectory(prefix='z8verify-')
        self.runtime = Path(self.temp.name)
        self.log_path = self.out / 'stderr.log'
        argv = [str(self.qemu), '-M', machine,
                '-accel', 'tcg,thread=single', '-icount', 'shift=0,sleep=on',
                '-smp', str(smp), '-m', ram, '-display', 'none', '-serial', 'none',
                '-monitor', 'none', '-S', '-no-reboot',
                '-qmp', f'unix:{self.runtime}/qmp.sock,server=on,wait=off',
                '-qtest', f'unix:{self.runtime}/qtest.sock,server=on,wait=off',
                '-qtest-log', os.devnull]
        if gdb:
            argv += ['-gdb', f'unix:{self.runtime}/gdb.sock,server=on,wait=off']
        if raw:
            if ',' in str(raw):
                raise ValueError('raw path cannot contain a comma')
            argv += ['-object', f'memory-backend-file,id=raw,share=on,mem-path={Path(raw).resolve()},size=1M']
        if load_addr is not None:
            argv += ['-kernel', str(self.firmware)]
        else:
            argv += ['-kernel', str(self.firmware)]
        argv += list(extra)
        self.argv = argv
        self.data = dict(kind='z8verify-run', checks=[], error=None)
        self.proc = self.qmp = self.qt = self.fp = self.gdb = None
        self._log_offset = 0

    def __enter__(self):
        try:
            with self.log_path.open('wb') as log:
                self.proc = subprocess.Popen(self.argv, stdout=subprocess.DEVNULL, stderr=log)
            deadline = time.monotonic() + 20
            while not (self.runtime / 'qtest.sock').exists():
                if self.proc.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('QEMU startup failed, see stderr.log')
                time.sleep(.02)
            self.qmp = QMP(self.runtime / 'qmp.sock')
            self.qt = socket.socket(socket.AF_UNIX)
            self.qt.settimeout(5)
            self.qt.connect(str(self.runtime / 'qtest.sock'))
            self.fp = self.qt.makefile('rwb', buffering=0)
            if self.gdb:
                self.gdb = socket.socket(socket.AF_UNIX)
                self.gdb.settimeout(5)
                self.gdb.connect(str(self.runtime / 'gdb.sock'))
            return self
        except BaseException as exc:
            self.__exit__(type(exc), exc, None)
            raise

    def __exit__(self, kind, error, traceback):
        self.data['error'] = repr(error) if error else None
        if self.proc and self.proc.poll() is None:
            try:
                self.qmp.command('quit')
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.kill()
                    self.proc.wait(timeout=5)
        self.data['qemu_stopped'] = self.proc is None or self.proc.poll() is not None
        for obj in (self.fp, self.qt, self.gdb):
            if obj:
                obj.close()
        if self.qmp:
            self.qmp.close()
        self.temp.cleanup()
        return False

    # --- qtest: physical memory -------------------------------------------
    def _qt(self, command):
        self.fp.write(command.encode() + b'\n')
        while True:
            reply = self.fp.readline().decode().strip()
            if not reply.startswith('IRQ '):
                break
        if not reply.startswith('OK'):
            raise RuntimeError(f'{command}: {reply}')
        return reply.split()[1:]

    def read_bytes(self, addr, size):
        return bytes.fromhex(self._qt(f'read {addr:#x} {size:#x}')[0][2:])

    def write_bytes(self, addr, data):
        for off in range(0, len(data), 8):
            chunk = data[off:off + 8]
            word = int.from_bytes(chunk.ljust(8, b'\0'), 'little')
            self._qt(f'write {addr + off:#x} {len(chunk):#x} {word:#x}')

    def read_word(self, addr, size=4):
        return int.from_bytes(self.read_bytes(addr, size), 'little')

    # --- gdbstub: execution state -----------------------------------------
    def rsp(self, command, *, expect_ok=True, accept_stop=False):
        body = command.encode()
        self.gdb.sendall(b'$' + body + b'#' + f'{sum(body) & 255:02x}'.encode())
        while True:
            char = self.gdb.recv(1)
            while char != b'$':
                if not char:
                    raise EOFError('GDB disconnected')
                char = self.gdb.recv(1)
            reply = bytearray()
            while True:
                char = self.gdb.recv(1)
                if char == b'#':
                    break
                if not char:
                    raise EOFError('GDB disconnected in packet')
                reply += char
            checksum = b''
            while len(checksum) < 2:
                char = self.gdb.recv(2 - len(checksum))
                if not char:
                    raise EOFError('GDB disconnected at checksum')
                checksum += char
            if checksum != f'{sum(reply) & 255:02x}'.encode():
                raise RuntimeError('bad GDB checksum')
            self.gdb.sendall(b'+')
            if reply.startswith((b'T', b'S')) and not accept_stop:
                continue
            if expect_ok and reply != b'OK':
                raise RuntimeError(f'{command}: {reply!r}')
            return None if expect_ok else reply.decode('ascii')

    def regs(self, cpu=0):
        text = self.qmp.hmp('info registers', cpu)
        out = {}
        for key, value in REG.findall(text):
            out[key] = int(value, 16)
        return out

    def set_reg(self, cpu, regnum, value):
        self.rsp('Hg%x' % cpu)
        self.rsp('P%x=%s' % (regnum, int(value).to_bytes(8, 'little').hex()))

    def arm(self, pc, kind='sw'):
        self.rsp(('Z1' if kind == 'sw' else 'Z2') + f',{pc:x},4')

    def disarm(self, pc, kind='sw'):
        self.rsp(('z1' if kind == 'sw' else 'z2') + f',{pc:x},4')

    def cont(self):
        self.qmp.command('cont')

    def stop(self):
        self.qmp.command('stop')

    def running(self):
        return self.qmp.command('query-status')['running']

    def wait_pc(self, pc, timeout=300):
        """Run until one armed breakpoint on pc fires. Returns register state."""
        self.arm(pc)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self.cont()
                while self.running() and time.monotonic() < deadline:
                    time.sleep(.005)
                self.stop()
                for cpu in range(8):
                    state = self.regs(cpu)
                    if state.get('PC') == pc:
                        return state
            raise TimeoutError(f'PC {pc:#x} not reached within {timeout}s')
        finally:
            self.disarm(pc)

    def log(self):
        with self.log_path.open('r', encoding='utf-8', errors='replace') as f:
            f.seek(self._log_offset)
            text = f.read()
            self._log_offset = f.tell()
        return text

    def check(self, name, condition):
        self.data['checks'].append(dict(name=name, passed=bool(condition)))
        return bool(condition)


import re  # noqa: E402
REG = re.compile(r'\b([A-Z][A-Z0-9]{1,7})=([0-9a-fA-F]{4,16})')
