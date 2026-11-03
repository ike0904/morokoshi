"""
SPC (Super Famicom / SNES sound) file reader and player (register logging, no audio; v0.1.36, phase 1).

An SPC file is a snapshot of the sound unit: 64 KB of RAM, the 128 DSP registers and the SPC700
registers. Playback resumes the SPC700 from that state; the sound driver keeps running and
writes the DSP through $F2 (address) / $F3 (data). Every DSP write is logged with its CPU cycle
(1.024 MHz), like the APU writes of an NSF.

I/O ($F0-$FF): $F1 control (timer enable, port clear, IPL ROM), $F2/$F3 DSP, $F4-$F7 ports
(the values stored in the file are what the main CPU last wrote), $FA-$FC timer targets,
$FD-$FF timer counters (4 bits, cleared on read). Timers 0 / 1 tick at 8 kHz, timer 2 at 64 kHz.

Speed: the driver spends most of its time polling a timer counter. When the same instruction
reads a counter as 0 again within a few cycles, the CPU clock jumps to the next tick of that
timer (idle skip).
"""

import zipfile

from cpu_spc700 import CPUSPC700

CPU_HZ = 1024000.0
TIMER_PERIOD = (128, 128, 16)

IPL_ROM = bytes([
    0xCD, 0xEF, 0xBD, 0xE8, 0x00, 0xC6, 0x1D, 0xD0, 0xFC, 0x8F, 0xAA, 0xF4, 0x8F, 0xBB, 0xF5, 0x78,
    0xCC, 0xF4, 0xD0, 0xFB, 0x2F, 0x19, 0xEB, 0xF4, 0xD0, 0xFC, 0x7E, 0xF4, 0xD0, 0x0B, 0xE4, 0xF5,
    0xCB, 0xF4, 0xD7, 0x00, 0xFC, 0xD0, 0xF3, 0xAB, 0x01, 0x10, 0xEF, 0x7E, 0xF4, 0x10, 0xEB, 0xBA,
    0xF6, 0xDA, 0x00, 0xBA, 0xF4, 0xC4, 0xF4, 0xDD, 0x5D, 0xD0, 0xDB, 0x1F, 0x00, 0x00, 0xC0, 0xFF,
])


def _cstr(b):
    b = b.split(b"\x00", 1)[0]
    for enc in ("shift_jis", "latin-1"):
        try:
            return b.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return ""


def is_spc_data(data):
    return data[:27] == b"SNES-SPC700 Sound File Data"


class SPCHeader:
    expansion = 0
    expansion_names = []
    is_pal = False
    total_songs = 1
    start_song = 1

    def __init__(self, data):
        if not is_spc_data(data):
            raise ValueError("Not an SPC file (bad magic)")
        self.pc = data[0x25] | (data[0x26] << 8)
        self.a, self.x, self.y, self.psw, self.sp = data[0x27], data[0x28], data[0x29], data[0x2A], data[0x2B]
        self.title = _cstr(data[0x2E:0x4E])
        self.game = _cstr(data[0x4E:0x6E])
        self.artist = _cstr(data[0xB1:0xD1]) if data[0x23] == 0x1A else ""
        self.copyright = self.game
        try:
            self.length_sec = int(_cstr(data[0xA9:0xAC]) or 0)
        except ValueError:
            self.length_sec = 0

    def summary(self):
        return "\n".join([
            f"Title     : {self.title}",
            f"Game      : {self.game}",
            f"Artist    : {self.artist}",
            f"Length    : {self.length_sec} s (ID666)",
            "Format    : SPC (Super Famicom)",
        ])


class Timer:
    def __init__(self, period):
        self.period = period
        self.enabled = False
        self.target = 256
        self.stage = 0          # internal divider (counts timer clocks up to the target)
        self.counter = 0        # 4-bit output counter
        self.last = 0           # CPU cycle up to which the timer has run

    def run(self, now):
        if not self.enabled:
            self.last = now
            return
        ticks = (now - self.last) // self.period
        if ticks <= 0:
            return
        self.last += ticks * self.period
        total = self.stage + ticks
        self.counter = (self.counter + total // self.target) & 0xF
        self.stage = total % self.target

    def next_count(self, now):
        """CPU cycle at which the counter next increases."""
        self.run(now)
        return self.last + (self.target - self.stage) * self.period


class SPCBus:
    def __init__(self, player, ram, dsp, control):
        self.p = player
        self.ram = bytearray(ram)
        self.dsp = bytearray(dsp)
        self.dsp_addr = self.ram[0xF2]
        self.timers = [Timer(TIMER_PERIOD[i]) for i in range(3)]
        for i, t in enumerate(self.timers):
            t.target = self.ram[0xFA + i] or 256
            t.enabled = bool(control & (1 << i))
            t.counter = self.ram[0xFD + i] & 0xF
        self.control = control
        self.ports = list(self.ram[0xF4:0xF8])
        self.idle = {}             # read pc -> cycle of the last zero read of a counter

    def read(self, addr):
        if 0xF0 <= addr <= 0xFF:
            return self._io_read(addr)
        if addr >= 0xFFC0 and self.control & 0x80:
            return IPL_ROM[addr - 0xFFC0]
        return self.ram[addr]

    def _io_read(self, addr):
        cpu = self.p.cpu
        if addr == 0xF3:
            return self.p.dsp_read(self.dsp_addr & 0x7F)
        if addr == 0xF2:
            return self.dsp_addr
        if 0xF4 <= addr <= 0xF7:
            return self.ports[addr - 0xF4]
        if addr >= 0xFD:
            t = self.timers[addr - 0xFD]
            t.run(cpu.cycles)
            v = t.counter
            t.counter = 0
            if v == 0 and t.enabled:
                # idle skip: the same instruction polling an empty counter again
                pc = cpu.pc
                prev = self.idle.get(pc)
                if prev is not None and cpu.cycles - prev < 64:
                    cpu.cycles = max(cpu.cycles, t.next_count(cpu.cycles))
                self.idle[pc] = cpu.cycles
            return v
        return self.ram[addr]

    def write(self, addr, v):
        if 0xF0 <= addr <= 0xFF:
            self._io_write(addr, v)
        self.ram[addr] = v

    def _io_write(self, addr, v):
        cpu = self.p.cpu
        if addr == 0xF1:
            for i, t in enumerate(self.timers):
                t.run(cpu.cycles)
                on = bool(v & (1 << i))
                if on and not t.enabled:
                    t.stage = 0
                    t.counter = 0
                    t.last = cpu.cycles
                t.enabled = on
            if v & 0x10:
                self.ports[0] = self.ports[1] = 0
            if v & 0x20:
                self.ports[2] = self.ports[3] = 0
            self.control = v
        elif addr == 0xF2:
            self.dsp_addr = v
        elif addr == 0xF3:
            if self.dsp_addr < 0x80:
                self.p.dsp_write(self.dsp_addr, v)
        elif 0xFA <= addr <= 0xFC:
            t = self.timers[addr - 0xFA]
            t.run(cpu.cycles)
            t.target = v or 256


class SPCPlayer:
    """Same interface as nsf.NSFPlayer for the parts nsf2mid uses (header, writes, cpu_hz,
    start(), advance(frames)); frames are fixed slices of FRAME_HZ."""
    is_spc = True
    FRAME_HZ = 60.0

    def __init__(self, data):
        self.data = data
        self.header = SPCHeader(data)
        self.ram = data[0x100:0x10100]
        self.dsp_init = data[0x10100:0x10180]
        self.writes = []
        self.dmc_samples = {}
        self.warnings = []
        self.cpu_hz = CPU_HZ

    @property
    def frame_cycles(self):
        return CPU_HZ / self.FRAME_HZ

    def dsp_write(self, reg, v):
        self.dsp[reg] = v
        if reg == 0x7C:          # ENDX: any write clears it
            self.dsp[reg] = 0
        self.writes.append((self.cpu.cycles, reg, v))

    def dsp_read(self, reg):
        return self.dsp[reg]

    def start(self, track=1):
        h = self.header
        self.writes = []
        self.warnings = []
        self.frames_done = 0
        self.aborted = False
        self.dsp = bytearray(self.dsp_init)
        self.bus = SPCBus(self, self.ram, self.dsp_init, self.ram[0xF1])
        self.cpu = CPUSPC700(self.bus)
        c = self.cpu
        c.pc, c.a, c.x, c.y, c.psw, c.sp = h.pc, h.a, h.x, h.y, h.psw, h.sp
        # the state at the start: every voice register as stored (the first frame sees them)
        for reg in range(0x80):
            if reg not in (0x4C, 0x5C, 0x7C):
                self.writes.append((0, reg, self.dsp_init[reg]))

    def advance(self, frames):
        cpu = self.cpu
        step = cpu.step
        for _ in range(frames):
            if self.aborted:
                break
            end = (self.frames_done + 1) * self.frame_cycles
            while cpu.cycles < end:
                step()
                if cpu.halted:
                    self.warnings.append("SPC700 stopped (SLEEP / STOP)")
                    self.aborted = True
                    break
            self.frames_done += 1
        return self.frames_done

    def finish_warnings(self):
        pass


def read_spc_bytes(path, member=None):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist() if n.lower().endswith(".spc"))
            if not names:
                raise ValueError("no .spc file in the zip")
            return z.read(member or names[0])
    with open(path, "rb") as f:
        return f.read()
