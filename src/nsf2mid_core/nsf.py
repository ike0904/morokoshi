"""
NSF file parser and player (register-logging, no audio output).

The player runs INIT once and then calls PLAY at the rate given in the header,
recording every APU register write together with its CPU-cycle timestamp.
"""

import os
import struct
import zipfile

from cpu6502 import CPU6502
from apu_state import APUState

NTSC_CPU_HZ = 1789773.0
PAL_CPU_HZ = 1662607.0

EXPANSION_NAMES = [
    (0x01, "VRC6"),
    (0x02, "VRC7"),
    (0x04, "FDS"),
    (0x08, "MMC5"),
    (0x10, "N163"),
    (0x20, "5B"),
]

# Sentinel address used as the return address for INIT / PLAY calls.
# Placed in the unmapped $5xxx area (not used by 2A03-only NSFs).
SENTINEL = 0x5FF0


def is_nsf_zip(path):
    return path.lower().endswith(".zip") and zipfile.is_zipfile(path)


def _zip_nsf_member(z):
    names = [n for n in z.namelist() if n.lower().endswith(".nsf")]
    if not names:   # v0.1.27: zips of GBS files (zophar.net style) too
        names = [n for n in z.namelist() if n.lower().endswith(".gbs")]
    if not names:
        raise ValueError("no .nsf / .gbs file in the zip")
    return names[0]


def read_nsf_bytes(path):
    """Return the NSF (or GBS) data of a file or of a zip holding one (zophar.net style)."""
    if is_nsf_zip(path):
        with zipfile.ZipFile(path) as z:
            return z.read(_zip_nsf_member(z))
    with open(path, "rb") as f:
        return f.read()


def zip_contents(path):
    """For a zip: (inner .nsf name, {.m3u name: bytes}). For a plain .nsf: (None, {})."""
    if not is_nsf_zip(path):
        return None, {}
    with zipfile.ZipFile(path) as z:
        m3u = {n: z.read(n) for n in z.namelist() if n.lower().endswith(".m3u")}
        return _zip_nsf_member(z), m3u


def nsf_base_name(path):
    """Base name for output files: "Foo (EMU).zophar.zip" -> "Foo (EMU)", "bar.nsf" -> "bar"."""
    base = os.path.basename(path)
    if base.lower().endswith(".zip"):
        base = base[:-4]
        if base.lower().endswith(".zophar"):
            base = base[:-7]
        return base
    return os.path.splitext(base)[0]


class NSFHeader:
    def __init__(self, data):
        if data[:5] != b"NESM\x1a":
            raise ValueError("Not an NSF file (bad magic)")
        self.version = data[5]
        self.total_songs = data[6]
        self.start_song = data[7]
        self.load_addr, self.init_addr, self.play_addr = struct.unpack_from("<HHH", data, 8)
        self.title = _cstr(data[0x0E:0x2E])
        self.artist = _cstr(data[0x2E:0x4E])
        self.copyright = _cstr(data[0x4E:0x6E])
        self.speed_ntsc = struct.unpack_from("<H", data, 0x6E)[0]
        self.banks = list(data[0x70:0x78])
        self.speed_pal = struct.unpack_from("<H", data, 0x78)[0]
        self.pal_flags = data[0x7A]
        self.expansion = data[0x7B]
        # v2.9.27 (user): several expansion chips = a header error of the rip (a cartridge has one
        # chip; Platoon, Power Blade ... list VRC6+VRC7(+FDS) and write none of them): no expansion
        self.expansion_ignored = self.expansion if bin(self.expansion & 0x3F).count("1") >= 2 else 0
        if self.expansion_ignored:
            self.expansion = 0
        self.bankswitched = any(self.banks)

    @property
    def is_pal(self):
        # bit0: PAL, bit1: dual. Dual-compatible tunes are played as NTSC.
        return (self.pal_flags & 0x03) == 0x01

    @property
    def expansion_names(self):
        return [n for bit, n in EXPANSION_NAMES if self.expansion & bit]

    def summary(self):
        lines = [
            f"Title     : {self.title}",
            f"Artist    : {self.artist}",
            f"Copyright : {self.copyright}",
            f"Songs     : {self.total_songs} (start {self.start_song})",
            f"Load/Init/Play: ${self.load_addr:04X} / ${self.init_addr:04X} / ${self.play_addr:04X}",
            f"Speed     : NTSC {self.speed_ntsc} us, PAL {self.speed_pal} us, "
            f"region {'PAL' if self.is_pal else 'NTSC'}",
            f"Bankswitch: {'yes ' + ' '.join(f'{b:02X}' for b in self.banks) if self.bankswitched else 'no'}",
            f"Expansion : {', '.join(self.expansion_names) or 'none'}",
        ]
        return "\n".join(lines)


def _cstr(b):
    b = b.split(b"\x00", 1)[0]
    for enc in ("shift_jis", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


class NSFBus:
    """Memory map for an NSF tune (2A03, plus the FDS layout when the FDS bit is set).

    FDS tunes (v0.1.25): $6000-$FFFF is writable RAM (the FDS loads its program from disk into
    RAM), the tune may load below $8000, and bank writes ($5FF6-$5FFF, $5FF6/$5FF7 = $6000/$7000)
    copy a 4KB bank of the file into that RAM.
    Expansion sound registers (exp_handles(addr) True) go to on_apu_write like the 2A03 ones;
    on_exp_read answers readable ones (FDS $4040-$4092, N163 $4800). MMC5 also gets its
    ExRAM ($5C00-$5FF5) and the 8x8 multiplier ($5205/$5206).
    """

    def __init__(self, header, rom_data, on_apu_write, on_status_read=None, on_exp_read=None,
                 exp_handles=None):
        self.h = header
        self.ram = bytearray(0x800)
        self.sram = bytearray(0x2000)       # $6000-$7FFF
        self.on_apu_write = on_apu_write
        self.on_status_read = on_status_read
        self.on_exp_read = on_exp_read
        self.exp_handles = exp_handles or (lambda addr: False)
        self.cpu = None
        self.fds = bool(header.expansion & 0x04)
        self.mmc5 = bool(header.expansion & 0x08)
        self.exram = bytearray(0x400)       # MMC5 $5C00-$5FFF
        self.mul = [0xFF, 0xFF]             # MMC5 multiplier operands
        if self.fds:
            self._init_fds(header, rom_data)
            return

        if header.bankswitched:
            pad = header.load_addr & 0x0FFF
            img = bytes(pad) + rom_data
        else:
            pad = header.load_addr - 0x8000
            if pad < 0:
                raise ValueError(f"Load address ${header.load_addr:04X} below $8000 is not supported")
            img = bytes(pad) + rom_data
        n_banks = max(1, (len(img) + 0xFFF) // 0x1000)
        img = img + bytes(n_banks * 0x1000 - len(img))
        self.image = img
        self.n_banks = n_banks
        # 8 slots of 4KB for $8000-$FFFF; each holds the bank's start offset
        self.slot = [0] * 8
        if header.bankswitched:
            for i, b in enumerate(header.banks):
                self._set_bank(i, b)
        else:
            for i in range(8):
                self.slot[i] = i * 0x1000 if i < n_banks else None

    def _set_bank(self, slot, bank):
        self.slot[slot] = (bank % self.n_banks) * 0x1000

    def _init_fds(self, header, rom_data):
        self.mem = bytearray(0xA000)        # $6000-$FFFF, all RAM
        if header.bankswitched:
            img = bytes(header.load_addr & 0x0FFF) + rom_data
            self.n_banks = max(1, (len(img) + 0xFFF) // 0x1000)
            self.image = img + bytes(self.n_banks * 0x1000 - len(img))
            # $6000/$7000 start with the $E000/$F000 bank values ($76/$77), as the NSF spec says
            for slot, b in enumerate([header.banks[6], header.banks[7]] + list(header.banks)):
                self._fds_bank(slot, b)
        else:
            off = header.load_addr - 0x6000
            if off < 0:
                raise ValueError(f"Load address ${header.load_addr:04X} below $6000 is not supported")
            data = rom_data[:0xA000 - off]
            self.mem[off:off + len(data)] = data

    def _fds_bank(self, slot, bank):
        """Copy 4KB bank `bank` of the file to $6000 + slot * $1000 (slot 0-9)."""
        base = (bank % self.n_banks) * 0x1000
        self.mem[slot * 0x1000:(slot + 1) * 0x1000] = self.image[base:base + 0x1000]

    def read(self, addr):
        if addr < 0x2000:
            return self.ram[addr & 0x7FF]
        if self.fds and addr >= 0x6000:
            return self.mem[addr - 0x6000]
        if (0x4040 <= addr <= 0x4097 or addr == 0x4800) and self.on_exp_read:
            v = self.on_exp_read(addr)
            if v is not None:
                return v
        if self.mmc5 and 0x5205 <= addr <= 0x5206:
            prod = self.mul[0] * self.mul[1]
            return prod & 0xFF if addr == 0x5205 else prod >> 8
        if self.mmc5 and 0x5C00 <= addr <= 0x5FF5:
            return self.exram[addr - 0x5C00]
        if addr >= 0x8000:
            base = self.slot[(addr - 0x8000) >> 12]
            if base is None:
                return 0
            return self.image[base + (addr & 0x0FFF)]
        if addr >= 0x6000:
            return self.sram[addr - 0x6000]
        if addr == 0x4015 and self.on_status_read:
            return self.on_status_read()
        if addr == SENTINEL:
            return 0x4C  # JMP to self, never actually executed (player stops at sentinel)
        return 0

    def write(self, addr, val):
        if addr < 0x2000:
            self.ram[addr & 0x7FF] = val
        elif self.exp_handles(addr):
            self.on_apu_write(addr, val)
        elif self.fds and addr >= 0x6000:
            self.mem[addr - 0x6000] = val
        elif self.mmc5 and 0x5205 <= addr <= 0x5206:
            self.mul[addr - 0x5205] = val
        elif self.mmc5 and 0x5C00 <= addr <= 0x5FF5:
            self.exram[addr - 0x5C00] = val
        elif self.fds and 0x5FF6 <= addr <= 0x5FFF:
            if self.h.bankswitched:
                self._fds_bank(addr - 0x5FF6, val)
        elif 0x4000 <= addr <= 0x4017:
            self.on_apu_write(addr, val)
        elif 0x5FF8 <= addr <= 0x5FFF:
            if self.h.bankswitched:
                self._set_bank(addr - 0x5FF8, val)
        elif 0x6000 <= addr < 0x8000:
            self.sram[addr - 0x6000] = val


def open_player(path):
    """NSFPlayer, or gbs.GBSPlayer for GBS data (v0.1.27), or spc.SPCPlayer for an SPC file /
    a zip of SPC files (v0.1.36)."""
    from spc import is_spc_path, SPCPlayer
    if is_spc_path(path):
        return SPCPlayer(None, path)
    data = read_nsf_bytes(path)
    if data[:3] == b"GBS":
        from gbs import GBSPlayer
        return GBSPlayer(data)
    return NSFPlayer(path, data)


def read_header(data):
    """NSFHeader, gbs.GBSHeader or spc.SPCHeader of the file data."""
    from spc import is_spc_data, SPCHeader
    if is_spc_data(data):
        return SPCHeader(data)
    if data[:3] == b"GBS":
        from gbs import GBSHeader
        return GBSHeader(data)
    return NSFHeader(data)


class NSFPlayer:
    is_gbs = False

    def __init__(self, path, data=None):
        data = read_nsf_bytes(path) if data is None else data
        self.header = NSFHeader(data)
        self.rom = data[0x80:]
        self.writes = []          # (cpu_cycle, addr, value)
        self.bus = None
        self.cpu = None
        self.warnings = []

    @property
    def cpu_hz(self):
        return PAL_CPU_HZ if self.header.is_pal else NTSC_CPU_HZ

    @property
    def frame_cycles(self):
        speed = self.header.speed_pal if self.header.is_pal else self.header.speed_ntsc
        if speed == 0:
            speed = 20000 if self.header.is_pal else 16639
        return speed * self.cpu_hz / 1_000_000.0

    def _log_write(self, addr, val):
        cyc = self.cpu.cycles
        self.writes.append((cyc - self.t0 if self.t0 is not None else cyc, addr, val))
        dmc = self.apu.dmc
        before = dmc.start_count
        self.apu.write(cyc, addr, val)
        if dmc.start_count != before:
            self._capture_dmc(dmc.sample_addr, dmc.sample_len)

    def _capture_dmc(self, addr, length):
        """Keep the bytes of each DPCM sample (for drum classification)."""
        key = (addr, length)
        if key in self.dmc_samples:
            return
        rd = self.bus.read
        self.dmc_samples[key] = bytes(rd(0x8000 | ((addr + i) & 0x7FFF)) for i in range(length))

    def make_apu(self):
        return APUState(self.cpu_hz, expansion=self.header.expansion)

    @property
    def fds(self):
        return bool(self.header.expansion & 0x04)

    def _exp_read(self, addr):
        v = self.apu.read_expansion(self.cpu.cycles, addr)
        if addr == 0x4800 and v is not None:
            # N163 data reads advance the auto-increment address: log the new address so that
            # the replay (build_frames) stays in step
            n163 = next(c for c in self.apu.chips if c.NAME == "N163")
            cyc = self.cpu.cycles
            self.writes.append((cyc - self.t0 if self.t0 is not None else cyc, 0xF800,
                                n163.addr | (0x80 if n163.inc else 0)))
        return v

    def _status_read(self):
        # Drivers that read $4015 (length counter status) need a live APU model
        return self.apu.read_status(self.cpu.cycles)

    def _call(self, addr, max_cycles):
        cpu = self.cpu
        ret = SENTINEL - 1
        cpu.push(ret >> 8)
        cpu.push(ret & 0xFF)
        cpu.pc = addr
        limit = cpu.cycles + max_cycles
        step = cpu.step
        while cpu.pc != SENTINEL:
            step()
            if cpu.cycles >= limit or cpu.jammed:
                return False
        return True

    def start(self, track):
        """Load the tune and run INIT for `track` (1-based)."""
        h = self.header
        self.warnings = []
        if h.expansion_ignored:
            names = [n for bit, n in EXPANSION_NAMES if h.expansion_ignored & bit]
            self.warnings.append(f"The header lists several expansion chips ({', '.join(names)}): "
                                 "treated as no expansion (a cartridge has one chip)")
        self.writes = []
        self.dmc_samples = {}
        self.t0 = None
        self.frames_done = 0
        self.stuck = 0
        self.aborted = False
        self.apu = APUState(self.cpu_hz, expansion=h.expansion)
        chips = self.apu.chips
        self.bus = NSFBus(h, self.rom, self._log_write, self._status_read, self._exp_read,
                          (lambda a: any(c.handles(a) for c in chips)) if chips else None)
        self.cpu = CPU6502(self.bus)
        cpu = self.cpu

        # Power-up APU state as recommended by the NSF spec
        cpu.cycles = 0
        for a in range(0x4000, 0x4014):
            self.bus.write(a, 0x00)
        self.bus.write(0x4015, 0x00)
        self.bus.write(0x4015, 0x0F)
        self.bus.write(0x4017, 0x40)
        if self.fds:
            # FDS sound on, as the FDS BIOS leaves it: master envelope speed $E8, volume gain 0
            self.bus.write(0x4089, 0x00)
            self.bus.write(0x408A, 0xE8)
            self.bus.write(0x4080, 0x80)

        # INIT
        cpu.a = (track - 1) & 0xFF
        cpu.x = 1 if h.is_pal else 0
        cpu.y = 0
        cpu.s = 0xFD
        cpu.p = 0x24
        if not self._call(h.init_addr, 3_000_000):
            self.warnings.append("INIT did not return within cycle limit")
        # Frame 0 starts when INIT returns; INIT writes get negative cycle values
        self.t0 = cpu.cycles
        self.writes = [(c - self.t0, a, v) for c, a, v in self.writes]

    def advance(self, frames):
        """Call PLAY `frames` more times. Returns the total number of frames emulated."""
        cpu = self.cpu
        fc = self.frame_cycles
        play = self.header.play_addr
        for _ in range(frames):
            if self.aborted:
                break
            f = self.frames_done
            start = self.t0 + int(round(f * fc))
            if cpu.cycles < start:
                cpu.cycles = start
            cpu.s = 0xFD
            if not self._call(play, int(fc * 2)):
                self.stuck += 1
                cpu.s = 0xFD
                cpu.jammed = False
                if self.stuck >= 10 and self.stuck == f + 1:
                    self.warnings.append("PLAY never returns; emulation aborted")
                    self.aborted = True
            self.frames_done += 1
        return self.frames_done

    def finish_warnings(self):
        if self.stuck and not self.aborted:
            self.warnings.append(f"PLAY did not return within limit on {self.stuck} frame(s)")

    def run(self, track, frames):
        """Run `track` (1-based) for `frames` play calls; returns the register writes
        as (cpu_cycle relative to frame 0, addr, value). INIT writes have cycle < 0."""
        self.start(track)
        self.advance(frames)
        self.finish_warnings()
        return self.writes
