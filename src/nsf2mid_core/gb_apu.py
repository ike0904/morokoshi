"""
Game Boy APU state model for GBS files (v0.1.27). Like apu_state.py it models only what decides
*pitch* and *how loud* a channel sounds (no audio synthesis).

The four channels use the keys of the NES channels so the rest of nsf2mid (notes, drums, tempo,
loop, MIDI) works unchanged; MIDI ch 1-4 = the channel buttons of morokoshi:
  P1  = Square 1 (NR10-NR14, with sweep)        Freq = 131072 / (2048 - x)
  P2  = Square 2 (NR21-NR24)
  TRI = Wave     (NR30-NR34, wave RAM $FF30-)   Freq = 65536 / (2048 - x) per 32-sample table,
                                                times the number of exact repeats in the table
  NOI = Noise    (NR41-NR44). Its clock is mapped to the nearest NES noise period index so the
                 drum classification of drums.py can be reused; the 7-bit (short) mode = mode 1.
  DMC = always silent (the Game Boy has no sample channel)
A channel panned to neither side (NR51) or with its DAC off is silent.

Re-trigger for volume (soft_retrigger): Game Boy drivers change the volume of a sounding note by
writing NRx2 and re-triggering (the envelope only reloads on a trigger). A trigger at the same
semitone (noise: same NR43) while the channel sounds, with a start volume below the current
volume, continues the note (not reported as a trigger). A louder or equal re-trigger is a new
(repeated) note.
Frame sequencer: 512 Hz (length 256 Hz, sweep 128 Hz, envelope 64 Hz).
"""

import math

from apu_state import freq_to_note
from expansion import wave_cycles

GB_CPU_HZ = 4194304.0
SEQ_PERIOD = 8192           # CPU cycles per frame sequencer step (512 Hz)

# NES noise periods (NTSC CPU cycles) -> frequency of the noise shift clock
NES_NOISE_FREQ = [1789773.0 / p for p in (4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068)]

# Power-up register values written by libgme (Gbs_Emu::start_track) for $FF10-$FF3F
POWER_UP = [
    0x80, 0xBF, 0x00, 0x00, 0xBF,
    0x00, 0x3F, 0x00, 0x00, 0xBF,
    0x7F, 0xFF, 0x9F, 0x00, 0xBF,
    0x00, 0xFF, 0x00, 0x00, 0xBF,
    0x77, 0xF3, 0xF1,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0xAC, 0xDD, 0xDA, 0x48, 0x36, 0x02, 0xCF, 0x16,
    0x2C, 0x04, 0xE5, 0x2C, 0xAC, 0xDD, 0xDA, 0x48,
]
# Bits that read back as 1 (Gb_Apu::read_register)
READ_MASK = [
    0x80, 0x3F, 0x00, 0xFF, 0xBF,
    0xFF, 0x3F, 0x00, 0xFF, 0xBF,
    0x7F, 0xFF, 0x9F, 0xFF, 0xBF,
    0xFF, 0xFF, 0x00, 0x00, 0xBF,
    0x00, 0x00, 0x70,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
]


class GBEnvelope:
    def __init__(self):
        self.init_vol = 0
        self.up = False
        self.period = 0
        self.vol = 0
        self.timer = 0

    def set(self, v):
        self.init_vol = v >> 4
        self.up = bool(v & 0x08)
        self.period = v & 7

    @property
    def dac(self):
        return self.init_vol > 0 or self.up

    def trigger(self):
        self.vol = self.init_vol
        self.timer = self.period or 8

    def clock(self):
        if not self.period:
            return
        self.timer -= 1
        if self.timer <= 0:
            self.timer = self.period
            if self.up and self.vol < 15:
                self.vol += 1
            elif not self.up and self.vol > 0:
                self.vol -= 1


class GBChannel:
    def __init__(self, length_max):
        self.length_max = length_max
        self.on = False
        self.length = 0
        self.len_en = False
        self.freq = 0
        self.trig_key = None       # frequency (noise: NR43) at the last trigger

    def soft_retrigger(self, env, key):
        """True if this trigger only changes the volume of the sounding note (see module doc)."""
        soft = (self.on and env.dac and env.vol > 0 and key == self.trig_key and env.init_vol < env.vol)
        self.trig_key = key
        return soft

    def clock_length(self):
        if self.len_en and self.length > 0:
            self.length -= 1
            if self.length == 0:
                self.on = False


class GBSquare(GBChannel):
    def __init__(self, sweep):
        super().__init__(64)
        self.has_sweep = sweep
        self.duty = 0
        self.env = GBEnvelope()
        self.sw_period = self.sw_neg = self.sw_shift = 0
        self.sw_timer = 0
        self.sw_en = False
        self.shadow = 0

    def write(self, reg, v):
        """reg 0-4 (NRx0-NRx4). Returns True on trigger."""
        if reg == 0:
            self.sw_period = (v >> 4) & 7
            self.sw_neg = bool(v & 0x08)
            self.sw_shift = v & 7
        elif reg == 1:
            self.duty = v >> 6
            self.length = 64 - (v & 0x3F)
        elif reg == 2:
            self.env.set(v)
            if not self.env.dac:
                self.on = False
        elif reg == 3:
            self.freq = (self.freq & 0x700) | v
        elif reg == 4:
            self.freq = (self.freq & 0xFF) | ((v & 7) << 8)
            self.len_en = bool(v & 0x40)
            if v & 0x80:
                soft = self.soft_retrigger(self.env, round(freq_to_note(131072.0 / (2048 - self.freq))))
                self.trigger()
                return not soft
        return False

    def trigger(self):
        self.on = self.env.dac
        if self.length == 0:
            self.length = self.length_max
        self.env.trigger()
        if self.has_sweep:
            self.shadow = self.freq
            self.sw_timer = self.sw_period or 8
            self.sw_en = bool(self.sw_period or self.sw_shift)
            if self.sw_shift and self._sweep_calc() > 2047:
                self.on = False

    def _sweep_calc(self):
        d = self.shadow >> self.sw_shift
        return self.shadow - d if self.sw_neg else self.shadow + d

    def clock_sweep(self):
        if not self.has_sweep:
            return
        self.sw_timer -= 1
        if self.sw_timer > 0:
            return
        self.sw_timer = self.sw_period or 8
        if not (self.sw_en and self.sw_period):
            return
        nf = self._sweep_calc()
        if nf > 2047:
            self.on = False
        elif self.sw_shift:
            self.shadow = nf
            self.freq = nf
            if self._sweep_calc() > 2047:
                self.on = False

    def volume(self):
        return self.env.vol if self.on and self.env.dac else 0


class GBWave(GBChannel):
    VOL = (0, 15, 8, 4)          # 0 %, 100 %, 50 %, 25 % -> 0-15

    def __init__(self):
        super().__init__(256)
        self.dac = False
        self.vol_code = 0
        self.ram = [0] * 16

    def write(self, reg, v):
        if reg == 0:
            self.dac = bool(v & 0x80)
            if not self.dac:
                self.on = False
        elif reg == 1:
            self.length = 256 - v
        elif reg == 2:
            self.vol_code = (v >> 5) & 3
        elif reg == 3:
            self.freq = (self.freq & 0x700) | v
        elif reg == 4:
            self.freq = (self.freq & 0xFF) | ((v & 7) << 8)
            self.len_en = bool(v & 0x40)
            if v & 0x80:
                self.on = self.dac
                if self.length == 0:
                    self.length = 256
                return True
        return False

    def samples(self):
        out = []
        for b in self.ram:
            out += [b >> 4, b & 0xF]
        return out

    def volume(self):
        if not (self.on and self.dac):
            return 0
        s = self.samples()
        if max(s) == min(s):          # flat table: no sound
            return 0
        return self.VOL[self.vol_code]


class GBNoise(GBChannel):
    def __init__(self):
        super().__init__(64)
        self.env = GBEnvelope()
        self.shift = 0
        self.width7 = False
        self.div = 0

    def write(self, reg, v):
        if reg == 1:
            self.length = 64 - (v & 0x3F)
        elif reg == 2:
            self.env.set(v)
            if not self.env.dac:
                self.on = False
        elif reg == 3:
            self.shift = v >> 4
            self.width7 = bool(v & 0x08)
            self.div = v & 7
        elif reg == 4:
            self.len_en = bool(v & 0x40)
            if v & 0x80:
                soft = self.soft_retrigger(self.env, (self.shift, self.width7, self.div))
                self.on = self.env.dac
                if self.length == 0:
                    self.length = 64
                self.env.trigger()
                return not soft
        return False

    def clock_hz(self):
        r = self.div or 0.5
        return 524288.0 / r / (2 ** (self.shift + 1))

    def period_idx(self):
        """Nearest NES noise period index (0 = highest) of the noise clock."""
        f = self.clock_hz()
        return min(range(16), key=lambda i: abs(math.log(NES_NOISE_FREQ[i] / f)))

    def volume(self):
        if not self.on or not self.env.dac or self.shift >= 14:   # shift 14/15: no clock
            return 0
        return self.env.vol


class GBAPUState:
    """Same interface as apu_state.APUState: write(cyc, addr, v) -> triggered channel keys,
    advance(cyc), snapshot(); read(cyc, addr) for $FF10-$FF3F reads."""

    chips = ()

    def __init__(self, cpu_hz=GB_CPU_HZ):
        self.cpu_hz = cpu_hz
        self.p1 = GBSquare(True)
        self.p2 = GBSquare(False)
        self.wave = GBWave()
        self.noise = GBNoise()
        self.regs = [0] * 0x30
        self.power = True
        self.pan = 0xFF
        self.now = None
        self.seq_t = 0
        self.seq_step = 0
        for i, v in enumerate(POWER_UP):
            self.write(0, 0xFF10 + i, v)

    def _chan(self, addr):
        i = addr - 0xFF10
        if i < 5:
            return "P1", self.p1, i
        if i < 10:
            return "P2", self.p2, i - 5
        if i < 15:
            return "TRI", self.wave, i - 10
        if i < 20:
            return "NOI", self.noise, i - 15
        return None, None, None

    def advance(self, cyc):
        if self.now is None:
            self.now = cyc
            self.seq_t = cyc
            return
        while self.seq_t + SEQ_PERIOD <= cyc:
            self.seq_t += SEQ_PERIOD
            s = self.seq_step
            if s % 2 == 0:
                for ch in (self.p1, self.p2, self.wave, self.noise):
                    ch.clock_length()
            if s in (2, 6):
                self.p1.clock_sweep()
            if s == 7:
                self.p1.env.clock()
                self.p2.env.clock()
                self.noise.env.clock()
            self.seq_step = (s + 1) & 7
        self.now = cyc

    def write(self, cyc, addr, v):
        if not 0xFF10 <= addr <= 0xFF3F:
            return ()
        self.advance(cyc)
        i = addr - 0xFF10
        if addr >= 0xFF30:
            self.wave.ram[addr - 0xFF30] = v
            self.regs[i] = v
            return ()
        if addr == 0xFF26:
            on = bool(v & 0x80)
            if self.power and not on:
                for a in range(0xFF10, 0xFF26):
                    self._write_reg(a, 0)
                self.p1.on = self.p2.on = self.wave.on = self.noise.on = False
            self.power = on
            self.regs[i] = v & 0x80
            return ()
        if not self.power:
            return ()
        self.regs[i] = v
        return self._write_reg(addr, v)

    def _write_reg(self, addr, v):
        if addr == 0xFF25:
            self.pan = v
            return ()
        key, ch, reg = self._chan(addr)
        if ch is None:
            return ()
        if ch is self.noise and reg == 0:
            return ()
        return (key,) if ch.write(reg, v) else ()

    def read(self, cyc, addr):
        self.advance(cyc)
        i = addr - 0xFF10
        if addr >= 0xFF30:
            return self.wave.ram[addr - 0xFF30]
        if addr == 0xFF26:
            v = (0x80 if self.power else 0) | 0x70
            for bit, ch in enumerate((self.p1, self.p2, self.wave, self.noise)):
                if ch.on:
                    v |= 1 << bit
            return v
        return self.regs[i] | READ_MASK[i]

    def _panned(self, n):
        return bool(self.pan & (0x11 << n))

    def snapshot(self):
        out = {}
        for n, (name, ch) in enumerate((("P1", self.p1), ("P2", self.p2))):
            f = 131072.0 / (2048 - ch.freq)
            out[name] = {
                "period": ch.freq,
                "freq": f,
                "note": freq_to_note(f),
                "vol": ch.volume() if self._panned(n) else 0,
                "reg_vol": ch.env.init_vol,
                "const": ch.env.period == 0,
                "duty": ch.duty,
                "length": ch.length,
                "sweep": ch.has_sweep and ch.sw_en and ch.sw_shift > 0,
                "muted": False,
            }
        w = self.wave
        f = 65536.0 / (2048 - w.freq) * wave_cycles(w.samples())
        vol = w.volume() if self._panned(2) else 0
        out["TRI"] = {
            "period": w.freq,
            "freq": f,
            "note": freq_to_note(f),
            "vol": vol,
            "linear": w.vol_code,
            "length": w.length,
        }
        nz = self.noise
        out["NOI"] = {
            "period_idx": nz.period_idx(),
            "mode": 1 if nz.width7 else 0,
            "vol": nz.volume() if self._panned(3) else 0,
            "reg_vol": nz.env.init_vol,
            "const": nz.env.period == 0,
            "length": nz.length,
        }
        out["DMC"] = {"playing": False, "addr": 0, "len": 0, "rate": 0, "loop": False, "dac": 0, "starts": 0}
        return out
