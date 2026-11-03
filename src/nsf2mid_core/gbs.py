"""
GBS (Game Boy Sound System) file parser and player (register logging, no audio output; v0.1.27).

Same interface as nsf.NSFPlayer, so nsf2mid.convert() handles both:
  header (title / artist / total_songs / start_song / expansion / summary()), writes,
  cpu_hz, frame_cycles, dmc_samples, start(track), advance(frames), aborted, warnings,
  finish_warnings(), make_apu()

Memory map and start-up follow libgme (Gbs_Emu), which morokoshi uses for playback:
  $0000-$3FFF ROM bank 0 (the file data sits at the load address), $4000-$7FFF switchable bank
  (a write to $2000-$3FFF selects it; bank 0 is ignored when the ROM has more than one bank),
  $A000-$FFFF RAM (cart RAM, WRAM, echo, OAM, I/O, HRAM). RST n jumps to load address + n.
  PLAY is called by the timer (TAC bit 2 of the header: (256 - TMA) << shift cycles) or at
  vblank (70224 cycles, 59.73 Hz). TMA / TAC written by the tune ($FF06 / $FF07) change the rate.
"""

import struct
import zipfile

from cpu_sm83 import CPUSM83
from gb_apu import GBAPUState, GB_CPU_HZ

SENTINEL = 0xF00D           # return address of INIT / PLAY calls (libgme's idle address)
BANK = 0x4000
VBLANK_CYCLES = 70224
TIMER_SHIFT = (10, 4, 6, 8)
MAX_PLAY_HZ = 150.0         # faster PLAY rates are grouped into analysis frames of about FRAME_HZ
FRAME_HZ = 60.0             # (note / drum detection is tuned for 60 Hz frames)


def is_gbs_data(data):
    return data[:3] == b"GBS"


def gbs_zip_member(z):
    names = [n for n in z.namelist() if n.lower().endswith(".gbs")]
    return names[0] if names else None


def _cstr(b):
    b = b.split(b"\x00", 1)[0]
    for enc in ("shift_jis", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


class GBSHeader:
    expansion = 0
    expansion_names = []
    is_pal = False

    def __init__(self, data):
        if data[:3] != b"GBS":
            raise ValueError("Not a GBS file (bad magic)")
        self.version = data[3]
        self.total_songs = data[4]
        self.start_song = max(1, data[5])
        self.load_addr, self.init_addr, self.play_addr, self.stack_ptr = struct.unpack_from("<HHHH", data, 6)
        self.tma = data[0x0E]
        self.tac = data[0x0F]
        self.title = _cstr(data[0x10:0x30])
        self.artist = _cstr(data[0x30:0x50])
        self.copyright = _cstr(data[0x50:0x70])

    def play_period(self, tma=None, tac=None):
        """CPU cycles between PLAY calls (libgme Gbs_Emu::update_timer)."""
        if self.tac & 0x04:
            tma = self.tma if tma is None else tma
            tac = self.tac if tac is None else tac
            return (256 - tma) << (TIMER_SHIFT[tac & 3] - (self.tac >> 7))
        return VBLANK_CYCLES

    def summary(self):
        p = self.play_period()
        rate = GB_CPU_HZ / p
        lines = [
            f"Title     : {self.title}",
            f"Artist    : {self.artist}",
            f"Copyright : {self.copyright}",
            f"Songs     : {self.total_songs} (start {self.start_song})",
            f"Load/Init/Play/SP: ${self.load_addr:04X} / ${self.init_addr:04X} / ${self.play_addr:04X} / "
            f"${self.stack_ptr:04X}",
            f"Play rate : {'timer' if self.tac & 0x04 else 'vblank'} {rate:.2f} Hz "
            f"(TMA ${self.tma:02X} TAC ${self.tac:02X})",
            "Format    : GBS (Game Boy)",
        ]
        return "\n".join(lines)


class GBSBus:
    def __init__(self, player, rom):
        self.p = player
        self.rom = rom
        self.ram = bytearray(0x6000)          # $A000-$FFFF
        self.ram[0x4000:0x5F80] = b"\xFF" * 0x1F80   # $E000-$FF7F as libgme
        self.ram[0x5F00] = 0                  # joypad reads back as 0
        self.bank_off = BANK if len(rom) > BANK else 0
        self.n_banks = max(1, (len(rom) + BANK - 1) // BANK)

    def set_bank(self, n):
        # power-of-two mask like libgme's rom.mask_addr
        mask = 1
        while mask < self.n_banks:
            mask <<= 1
        off = (n & (mask - 1)) * BANK
        if off == 0 and len(self.rom) > BANK:
            return
        self.bank_off = off

    def read(self, addr):
        if addr < 0x4000:
            return self.rom[addr] if addr < len(self.rom) else 0
        if addr < 0x8000:
            a = self.bank_off + addr - 0x4000
            return self.rom[a] if a < len(self.rom) else 0
        if addr < 0xA000:
            return 0xFF            # VRAM: not mapped
        if 0xFF10 <= addr <= 0xFF3F:
            return self.p.apu.read(self.p.cpu.cycles, addr)
        if addr in (0xFF04, 0xFF41, 0xFF44):
            return self._lcd_timer(addr)
        return self.ram[addr - 0xA000]

    def _lcd_timer(self, addr):
        """DIV / STAT / LY from the CPU clock: some drivers wait for an LCD mode or a line
        (Wedding Peach: Jamapii Panic waits for HBlank in INIT)."""
        cyc = self.p.cpu.cycles
        if addr == 0xFF04:
            return (cyc >> 8) & 0xFF
        ly = (cyc // 456) % 154
        if addr == 0xFF44:
            return ly
        dot = cyc % 456
        mode = 1 if ly >= 144 else 2 if dot < 80 else 3 if dot < 252 else 0
        return (self.ram[addr - 0xA000] & 0x78) | 0x80 | mode

    def write(self, addr, v):
        if addr < 0x8000:
            if 0x2000 <= addr < 0x4000:
                self.set_bank(v)
            return
        if addr < 0xA000:
            return
        self.ram[addr - 0xA000] = v
        if 0xFF10 <= addr <= 0xFF3F:
            self.p.log_write(addr, v)
        elif addr in (0xFF06, 0xFF07):
            self.p.timer_written()


class GBSPlayer:
    is_gbs = True

    def __init__(self, data):
        self.header = GBSHeader(data)
        h = self.header
        self.rom = bytes(h.load_addr) + data[0x70:]
        self.writes = []
        self.dmc_samples = {}
        self.warnings = []
        self.cpu = None
        self.bus = None
        self.apu = None
        self.group = 1
        self.period = h.play_period()

    cpu_hz = GB_CPU_HZ

    @property
    def frame_cycles(self):
        return self.period * self.group

    def make_apu(self):
        return GBAPUState(self.cpu_hz)

    def log_write(self, addr, v):
        cyc = self.cpu.cycles
        self.writes.append((cyc - self.t0 if self.t0 is not None else cyc, addr, v))
        self.apu.write(cyc, addr, v)

    def timer_written(self):
        if self.t0 is None or not self.header.tac & 0x04:
            return
        p = self.header.play_period(self.bus.ram[0xFF06 - 0xA000], self.bus.ram[0xFF07 - 0xA000])
        if p != self.period and not self.rate_warned:
            self.rate_warned = True
            self.warnings.append(f"PLAY rate changed by the tune ({self.cpu_hz / self.period:.2f} -> "
                                 f"{self.cpu_hz / p:.2f} Hz); the first rate is kept")

    def _call(self, addr, max_cycles):
        cpu = self.cpu
        cpu.push(SENTINEL)
        cpu.pc = addr
        cpu.halted = False
        limit = cpu.cycles + max_cycles
        step = cpu.step
        while cpu.pc != SENTINEL:
            step()
            if cpu.halted:          # HALT / STOP: wait for the next interrupt = end of the call
                return True
            if cpu.cycles >= limit or cpu.jammed:
                return False
        return True

    def start(self, track):
        h = self.header
        self.warnings = []
        self.writes = []
        self.t0 = None
        self.frames_done = 0
        self.stuck = 0
        self.aborted = False
        self.rate_warned = False
        self.apu = GBAPUState(self.cpu_hz)
        self.bus = GBSBus(self, self.rom)
        self.cpu = CPUSM83(self.bus)
        cpu = self.cpu
        cpu.rst_base = h.load_addr
        cpu.cycles = 0
        bus = self.bus
        bus.ram[0xFF06 - 0xA000] = h.tma
        bus.ram[0xFF07 - 0xA000] = h.tac
        self.period = h.play_period()
        cpu.a = (track - 1) & 0xFF
        cpu.sp = h.stack_ptr
        if not self._call(h.init_addr, 8_000_000):
            self.warnings.append("INIT did not return within cycle limit")
        # the timer registers after INIT decide the PLAY rate (some tunes set them in INIT)
        self.period = h.play_period(bus.ram[0xFF06 - 0xA000], bus.ram[0xFF07 - 0xA000])
        rate = self.cpu_hz / self.period
        self.group = max(1, int(round(rate / FRAME_HZ))) if rate > MAX_PLAY_HZ else 1
        self.t0 = cpu.cycles
        self.writes = [(c - self.t0, a, v) for c, a, v in self.writes]

    def advance(self, frames):
        """Run `frames` more analysis frames (PLAY calls, grouped for fast timers)."""
        cpu = self.cpu
        h = self.header
        for _ in range(frames):
            if self.aborted:
                break
            for k in range(self.group):
                n = self.frames_done * self.group + k
                start = self.t0 + n * self.period
                if cpu.cycles < start:
                    cpu.cycles = start
                cpu.sp = h.stack_ptr
                cpu.jammed = False
                if not self._call(h.play_addr, max(int(self.period * 2), 2 * VBLANK_CYCLES)):
                    self.stuck += 1
                    if self.stuck >= 10 and self.stuck == n + 1:
                        self.warnings.append("PLAY never returns; emulation aborted")
                        self.aborted = True
                        break
            self.frames_done += 1
        return self.frames_done

    def finish_warnings(self):
        if self.stuck and not self.aborted:
            self.warnings.append(f"PLAY did not return within limit on {self.stuck} call(s)")
