"""
Expansion audio chips (Phase 5): FDS, VRC6, VRC7, MMC5, N163, Sunsoft 5B.

Like apu_state, these model only what decides *pitch* and *how loud* a channel sounds; no
audio is synthesised. Every chip has the same interface:
  CHANNELS            channel keys and labels, in the order of the channel buttons of morokoshi
                      (libgme voice order). MIDI ch = 6, 7, ... in this order.
  handles(addr)       True if a CPU write to addr is a register of this chip
  write(addr, v)      apply a write; returns the channel keys to treat as (re)triggered
  read(addr)          value of a readable register (None = not handled)
  advance(cyc)        run time-based units (envelopes) up to CPU cycle cyc
  snapshot(cpu_hz)    {channel key: {"period", "freq", "note", "vol" (0-15), "duty" (timbre id)}}

NSFs using more than one expansion chip are not considered (user decision, 2026-11-02): the
chips are emulated, but their MIDI channels are simply numbered on from ch 6.
"""

import math

from apu_state import Pulse, freq_to_note


def _vol15(v, top):
    """Scale 0..top to 0..15; anything audible stays >= 1."""
    v = min(v, top)
    return max(1, int(round(v * 15 / top))) if v > 0 else 0


def wave_cycles(samples):
    """How many times a wavetable repeats exactly (1, 2, 4, ...). A table holding 2 cycles of a
    wave sounds an octave higher (e.g. FDS in Bio Miracle Bokutte Upa: 2 and 4 cycles)."""
    n = len(samples)
    k = 1
    while n % 2 == 0 and n > 1 and samples[:n // 2] == samples[n // 2:n]:
        n //= 2
        k *= 2
    return k


class Chip:
    NAME = ""
    CHANNELS = ()        # ((key, label), ...)

    def handles(self, addr):
        return False

    def read(self, addr):
        return None

    def advance(self, cyc):
        pass


# ---------------------------------------------------------------------------------------- FDS
FDS_WAVE_DIV = 65536 * 64   # f = CPU * F / (65536 * 64), 64-step wavetable


class FDS(Chip):
    """FDS wavetable channel ($4040-$408A).

    The modulation unit ($4084-$4088, vibrato / bends) is only recorded: notes use the
    centre frequency and it is not written to the MIDI (user decision)."""
    NAME = "FDS"
    CHANNELS = (("FDS", "FDS"),)

    def __init__(self):
        self.wave = [0] * 64
        self.wave_write = False   # $4089 bit 7: wavetable writable, output held
        self.master_vol = 0       # $4089 bits 0-1: 2/2, 2/3, 2/4, 2/5 (not applied)
        self.freq = 0             # 12 bit
        self.halt = False         # $4083 bit 7: wave halted
        self.env_off = False      # $4083 bit 6: envelopes halted
        self.env_speed = 0xE8     # $408A
        self.vol_direct = True    # $4080 bit 7
        self.vol_up = False
        self.vol_rate = 0
        self.gain = 0
        self.env_acc = 0
        self.mod_gain = 0
        self.mod_freq = 0
        self.mod_off = True
        self.now = None
        self.wave_ids = {}

    def handles(self, addr):
        return 0x4040 <= addr <= 0x408A

    def advance(self, cyc):
        if self.now is None:
            self.now = cyc
            return
        dt = cyc - self.now
        self.now = cyc
        if dt <= 0 or self.vol_direct or self.env_off or self.env_speed == 0 or self.wave_write:
            return
        period = 8 * (self.vol_rate + 1) * self.env_speed
        self.env_acc += dt
        ticks = int(self.env_acc // period)
        if ticks:
            self.env_acc -= ticks * period
            self.gain = min(32, self.gain + ticks) if self.vol_up else max(0, self.gain - ticks)

    def write(self, addr, v):
        if addr < 0x4080:
            if self.wave_write:
                self.wave[addr - 0x4040] = v & 0x3F
            return ()
        reg = addr - 0x4080
        if reg == 0:
            self.vol_direct = bool(v & 0x80)
            self.vol_up = bool(v & 0x40)
            self.vol_rate = v & 0x3F
            self.env_acc = 0
            if self.vol_direct:
                self.gain = v & 0x3F
        elif reg == 2:
            self.freq = (self.freq & 0xF00) | v
        elif reg == 3:
            self.freq = (self.freq & 0xFF) | ((v & 0x0F) << 8)
            self.halt = bool(v & 0x80)
            self.env_off = bool(v & 0x40)
            return ("FDS",)
        elif reg == 4:
            if v & 0x80:
                self.mod_gain = v & 0x3F
        elif reg == 6:
            self.mod_freq = (self.mod_freq & 0xF00) | v
        elif reg == 7:
            self.mod_freq = (self.mod_freq & 0xFF) | ((v & 0x0F) << 8)
            self.mod_off = bool(v & 0x80)
        elif reg == 9:
            self.wave_write = bool(v & 0x80)
            self.master_vol = v & 0x03
        elif reg == 10:
            self.env_speed = v
        return ()

    def read(self, addr):
        if 0x4040 <= addr < 0x4080:
            return self.wave[addr - 0x4040] | 0x40
        if addr == 0x4090:
            return self.gain | 0x40
        if addr == 0x4092:
            return self.mod_gain | 0x40
        return None

    def volume(self):
        if self.halt or self.wave_write or self.freq == 0 or not any(self.wave):
            return 0
        return _vol15(self.gain, 32)

    def snapshot(self, hz):
        f = hz * self.freq / FDS_WAVE_DIV * wave_cycles(self.wave)
        return {"FDS": {"period": self.freq, "freq": f, "note": freq_to_note(f) if self.freq else None,
                        "vol": self.volume(), "gain": self.gain,
                        "duty": self.wave_ids.setdefault(tuple(self.wave), len(self.wave_ids)),
                        "mod": 0 if self.mod_off else self.mod_gain}}


# --------------------------------------------------------------------------------------- VRC6
class VRC6(Chip):
    """Konami VRC6: two pulses ($9000-$9002, $A000-$A002) and a sawtooth ($B000-$B002).
    Channel order = libgme voices: Saw, Pulse 1, Pulse 2."""
    NAME = "VRC6"
    CHANNELS = (("V6SAW", "VRC6 Saw"), ("V6P1", "VRC6 Pulse 1"), ("V6P2", "VRC6 Pulse 2"))
    BASE = {0x9000: "V6P1", 0xA000: "V6P2", 0xB000: "V6SAW"}

    def __init__(self):
        self.r = {k: [0, 0, 0] for k in ("V6P1", "V6P2", "V6SAW")}
        self.ctrl = 0             # $9003: bit 0 halt, bit 1 / bit 2 = 16x / 256x frequency

    def handles(self, addr):
        return 0x9000 <= addr <= 0x9003 or 0xA000 <= addr <= 0xA002 or 0xB000 <= addr <= 0xB002

    def write(self, addr, v):
        if addr == 0x9003:
            self.ctrl = v
            return ()
        ch = self.BASE[addr & 0xF000]
        self.r[ch][addr & 3] = v
        return (ch,) if addr & 3 == 2 and v & 0x80 else ()

    def snapshot(self, hz):
        out = {}
        for ch, r in self.r.items():
            period = r[1] | ((r[2] & 0x0F) << 8)
            if self.ctrl & 4:
                period >>= 8
            elif self.ctrl & 2:
                period >>= 4
            on = bool(r[2] & 0x80) and not self.ctrl & 1
            if ch == "V6SAW":
                f = hz / (14.0 * (period + 1))
                vol = _vol15(r[0] & 0x3F, 42) if on else 0     # accumulator rate; > 42 overflows
                duty = 0
            else:
                f = hz / (16.0 * (period + 1))
                vol = (r[0] & 0x0F) if on and not r[0] & 0x80 else 0   # bit 7 = constant (DAC) mode
                duty = (r[0] >> 4) & 7
            out[ch] = {"period": period, "freq": f, "note": freq_to_note(f), "vol": vol, "duty": duty}
        return out


# --------------------------------------------------------------------------------------- VRC7
# Frequency multipliers (MULT, low nibble of patch bytes 0 / 1) of the 15 built-in VRC7 patches:
# (modulator, carrier). Patch 0 is the custom one in registers $00-$07.
VRC7_MULT = [None, (3, 1), (3, 1), (1, 1), (1, 1), (2, 1), (2, 1), (1, 1), (3, 1), (5, 1), (5, 1), (7, 1),
             (1, 3), (1, 2), (1, 3), (1, 2)]
MULT_X2 = [1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 20, 24, 24, 30, 30]   # 2 x multiplier (MULT 0 = x1/2)


def fm_pitch_factor(mod_mult, car_mult):
    """Pitch heard from a 2-operator FM voice relative to the fnum/block frequency: the partials
    are car * f +- k * mod * f, i.e. harmonics of gcd(mod, car) * f (e.g. patch 14 "synth bass",
    modulator x1 / carrier x3, sounds at x1, not x3)."""
    return math.gcd(MULT_X2[mod_mult], MULT_X2[car_mult]) / 2


class VRC7(Chip):
    """Konami VRC7: 6 FM channels (YM2413 / OPLL derivative), $9010 = register select, $9030 = data.
    Pitch: f = fnum * (3.579545 MHz / 72) * 2^block / 2^19, times fm_pitch_factor of the patch.
    Volume: 15 - attenuation while the key is on (the FM release after key off is not followed)."""
    NAME = "VRC7"
    CHANNELS = tuple((f"FM{i + 1}", f"VRC7 FM {i + 1}") for i in range(6))
    FS = 3579545.0 / 72

    def __init__(self):
        self.sel = 0
        self.reg = [0] * 0x40

    def handles(self, addr):
        return addr in (0x9010, 0x9030)

    def write(self, addr, v):
        if addr == 0x9010:
            self.sel = v & 0x3F
            return ()
        r = self.sel
        old = self.reg[r]
        self.reg[r] = v
        if 0x20 <= r <= 0x25 and v & 0x10 and not old & 0x10:   # key on
            return (f"FM{r - 0x20 + 1}",)
        return ()

    def snapshot(self, hz):
        out = {}
        for i in range(6):
            hi = self.reg[0x20 + i]
            fnum = self.reg[0x10 + i] | ((hi & 1) << 8)
            block = (hi >> 1) & 7
            inst = self.reg[0x30 + i] >> 4
            mm, cm = (self.reg[0] & 0x0F, self.reg[1] & 0x0F) if inst == 0 else VRC7_MULT[inst]
            f = fnum * self.FS * (2 ** block) / (1 << 19) * fm_pitch_factor(mm, cm)
            vol = 15 - (self.reg[0x30 + i] & 0x0F) if hi & 0x10 else 0
            out[f"FM{i + 1}"] = {"period": fnum, "freq": f, "note": freq_to_note(f) if fnum else None,
                                 "vol": vol if fnum else 0, "duty": inst}
        return out


# --------------------------------------------------------------------------------------- MMC5
class _MMC5Pulse(Pulse):
    def muted(self):          # no sweep unit, no low-period muting
        return False


class MMC5(Chip):
    """Nintendo MMC5: two 2A03-style pulses ($5000-$5007, enable $5015). Envelopes and length
    counters are clocked at 240 Hz by the chip itself. The PCM channel ($5010/$5011) is ignored."""
    NAME = "MMC5"
    CHANNELS = (("M5P1", "MMC5 Pulse 1"), ("M5P2", "MMC5 Pulse 2"))
    TICK = 7457   # CPU cycles per 240 Hz step

    def __init__(self):
        self.p = {"M5P1": _MMC5Pulse(False), "M5P2": _MMC5Pulse(False)}
        self.now = None
        self.acc = 0

    def handles(self, addr):
        return 0x5000 <= addr <= 0x5015

    def advance(self, cyc):
        if self.now is None:
            self.now = cyc
            return
        self.acc += cyc - self.now
        self.now = cyc
        while self.acc >= self.TICK:
            self.acc -= self.TICK
            for p in self.p.values():
                p.clock_quarter()
                p.clock_half()

    def write(self, addr, v):
        if addr <= 0x5007:
            ch = "M5P1" if addr < 0x5004 else "M5P2"
            self.p[ch].write(addr & 3, v)
            return (ch,) if addr & 3 == 3 else ()
        if addr == 0x5015:
            for ch, bit in (("M5P1", 1), ("M5P2", 2)):
                p = self.p[ch]
                p.enabled = bool(v & bit)
                if not p.enabled:
                    p.length = 0
        return ()

    def snapshot(self, hz):
        out = {}
        for ch, p in self.p.items():
            f = hz / (16.0 * (p.timer + 1))
            out[ch] = {"period": p.timer, "freq": f, "note": freq_to_note(f), "vol": p.volume(), "duty": p.duty}
        return out


# --------------------------------------------------------------------------------------- N163
class N163(Chip):
    """Namco 163: up to 8 wavetable channels in 128 bytes of internal RAM.
    $F800 = address port (bit 7 auto-increment), $4800 = data port. Channel i (libgme voice
    "Wave i+1") has its registers at $40 + 8i; with n channels enabled ($7F bits 4-6 = n - 1)
    only the last n (Wave 9-n .. Wave 8) play.
    Pitch: f = CPU * F / (15 * 65536 * n * L), L = wave length in 4-bit samples."""
    NAME = "N163"
    CHANNELS = tuple((f"N{i + 1}", f"N163 Wave {i + 1}") for i in range(8))

    def __init__(self):
        self.ram = [0] * 128
        self.addr = 0
        self.inc = False
        self.wave_ids = {}

    def handles(self, addr):
        return addr == 0x4800 or 0xF800 <= addr <= 0xFFFF

    def write(self, addr, v):
        if addr >= 0xF800:
            self.addr = v & 0x7F
            self.inc = bool(v & 0x80)
            return ()
        a = self.addr
        self.ram[a] = v
        if self.inc:
            self.addr = (a + 1) & 0x7F
        if a >= 0x40 and a & 7 == 4:      # frequency high / wave length
            return (f"N{(a - 0x40) // 8 + 1}",)
        return ()

    def read(self, addr):
        if addr != 0x4800:
            return None
        v = self.ram[self.addr]
        if self.inc:
            self.addr = (self.addr + 1) & 0x7F
        return v

    def snapshot(self, hz):
        out = {}
        n = ((self.ram[0x7F] >> 4) & 7) + 1
        for i in range(8):
            b = 0x40 + 8 * i
            r = self.ram
            freq = r[b] | (r[b + 2] << 8) | ((r[b + 4] & 3) << 16)
            length = 256 - (r[b + 4] & 0xFC)
            start = r[b + 6]
            vol = r[b + 7] & 0x0F
            wave = tuple((r[((start + s) & 0xFF) >> 1] >> (4 * ((start + s) & 1))) & 0x0F for s in range(length))
            f = hz * freq / (15.0 * 65536 * n * length) * wave_cycles(wave) if freq else 0.0
            active = i >= 8 - n and freq and any(wave)
            out[f"N{i + 1}"] = {"period": freq, "freq": f, "note": freq_to_note(f), "vol": vol if active else 0,
                                "duty": self.wave_ids.setdefault(wave, len(self.wave_ids))}
        return out


# ----------------------------------------------------------------------------------------- 5B
class Sunsoft5B(Chip):
    """Sunsoft 5B (YM2149F / AY-3-8910 core): 3 square channels A-C. $C000 = register select,
    $E000 = data. f = CPU / (32 * period). Noise and the hardware envelope's shape are not
    modelled (envelope mode counts as full volume)."""
    NAME = "5B"
    CHANNELS = (("5BA", "5B Tone A"), ("5BB", "5B Tone B"), ("5BC", "5B Tone C"))

    def __init__(self):
        self.sel = 0
        self.reg = [0] * 16

    def handles(self, addr):
        return 0xC000 <= addr <= 0xFFFF

    def write(self, addr, v):
        if addr < 0xE000:
            self.sel = v & 0x0F
            return ()
        r = self.sel
        self.reg[r] = v
        if r in (1, 3, 5):
            return (self.CHANNELS[r // 2][0],)
        return ()

    def snapshot(self, hz):
        out = {}
        for i, (ch, _) in enumerate(self.CHANNELS):
            period = self.reg[2 * i] | ((self.reg[2 * i + 1] & 0x0F) << 8)
            f = hz / (32.0 * max(1, period))
            tone_on = not (self.reg[7] >> i) & 1
            v = self.reg[8 + i]
            vol = (15 if v & 0x10 else v & 0x0F) if tone_on and period else 0
            out[ch] = {"period": period, "freq": f, "note": freq_to_note(f), "vol": vol, "duty": 0}
        return out


# NSF header expansion bits -> chip class, in the channel numbering order (MIDI ch 6 onwards)
CHIP_BITS = ((0x01, VRC6), (0x10, N163), (0x20, Sunsoft5B), (0x08, MMC5), (0x04, FDS), (0x02, VRC7))


def make_chips(expansion):
    """Chip instances for the NSF header's expansion byte."""
    return [cls() for bit, cls in CHIP_BITS if expansion & bit]


def channel_table(expansion):
    """[(key, MIDI channel 0-15, track name)] of the expansion channels (ch 6 = index 5 onwards)."""
    out = []
    for bit, cls in CHIP_BITS:
        if expansion & bit:
            for key, label in cls.CHANNELS:
                mch = min(15, 5 + len(out))
                out.append((key, mch, f"Ch{mch + 1} {label}"))
    return out
