"""
S-DSP model for SPC files (v0.1.36, phase 1): what decides the pitch and the loudness of each of
the 8 voices, rebuilt from the logged DSP writes. No audio is synthesised except the BRR
decoding of the samples, which is needed to know the pitch of each sample.

Pitch of a voice = pitch of its sample at the original rate x P / 0x1000 (P = 14-bit pitch
register, 0x1000 = 32 kHz). The pitch of a sample comes from its waveform (sample_pitch): the
period of the looped part (or of the start of a one-shot sample) by autocorrelation, as for the
DPCM samples of the NES (drums.dpcm_period).
"""

import math

from apu_state import freq_to_note

DSP_RATE = 32000.0
PERIODIC = 0.9          # autocorrelation of a clearly periodic sample: its period is the pitch
HPS_OCTAVE_SLACK = 1.0  # log-spectrum score an octave lower may lose and still be the fundamental


def brr_decode(ram, start, max_blocks=4096):
    """Decode a BRR sample from `start`. Returns (samples, loop_flag, end_index)."""
    out = []
    p1 = p2 = 0
    addr = start
    loop = False
    for _ in range(max_blocks):
        if addr + 9 > len(ram):
            break
        hdr = ram[addr]
        shift, filt = hdr >> 4, (hdr >> 2) & 3
        loop = bool(hdr & 2)
        for i in range(16):
            byte = ram[addr + 1 + i // 2]
            n = (byte >> 4) if i % 2 == 0 else (byte & 0xF)
            if n >= 8:
                n -= 16
            s = (n << shift) >> 1 if shift <= 12 else (-2048 if n < 0 else 0)
            if filt == 1:
                s += p1 + ((-p1) >> 4)
            elif filt == 2:
                s += (p1 << 1) + ((-p1 * 3) >> 5) - p2 + (p2 >> 4)
            elif filt == 3:
                s += (p1 << 1) + ((-p1 * 13) >> 6) - p2 + ((p2 * 3) >> 4)
            s = max(-32768, min(32767, s))
            out.append(s)
            p2, p1 = p1, s
        addr += 9
        if hdr & 1:
            break
    return out, loop, addr


def sample_table(ram, dir_page):
    """{srcn: (start, loop_start)} for the 256 directory entries."""
    base = dir_page << 8
    tab = {}
    for n in range(256):
        a = (base + 4 * n) & 0xFFFF
        if a + 3 >= len(ram):
            break
        tab[n] = (ram[a] | (ram[a + 1] << 8), ram[a + 2] | (ram[a + 3] << 8))
    return tab


def _autocorr_period(x, circular, min_lag=4, max_lag=2048):
    """Period (samples, fractional) with the best normalised autocorrelation, preferring the
    shortest lag within 90 % of the best (avoids octave-down errors). Returns (period, corr)."""
    n = len(x)
    if n < 2 * min_lag:
        return None, 0.0
    mean = sum(x) / n
    x = [v - mean for v in x]
    e = sum(v * v for v in x)
    if e <= 0:
        return None, 0.0
    max_lag = min(max_lag, n - 1 if circular else n // 2)
    corr = [0.0] * (max_lag + 2)
    for lag in range(min_lag, max_lag + 1):
        if circular:
            s = sum(x[i] * x[(i + lag) % n] for i in range(n))
            corr[lag] = s / e
        else:
            m = n - lag
            a = x[:m]
            b = x[lag:]
            ea = sum(v * v for v in a)
            eb = sum(v * v for v in b)
            corr[lag] = sum(p * q for p, q in zip(a, b)) / math.sqrt(ea * eb) if ea > 0 and eb > 0 else 0.0
    best = max(corr[min_lag:max_lag + 1])
    if best <= 0:
        return None, 0.0
    for lag in range(min_lag + 1, max_lag):
        c = corr[lag]
        if c >= 0.9 * best and c >= corr[lag - 1] and c >= corr[lag + 1]:
            # parabolic interpolation of the peak
            a, b, d = corr[lag - 1], c, corr[lag + 1]
            den = a - 2 * b + d
            off = 0.5 * (a - d) / den if den else 0.0
            return lag + off, c
    return None, best


def _hps_pitch(x, n_harm=5):
    """Fundamental by summing the log spectrum at its first harmonics (harmonic product).
    Samples whose period is ambiguous in time (FF5 "A Presentiment" sample 39: strong 4th and
    5th harmonics, autocorrelation found the 5th harmonic = 4 semitones off) are right here,
    up to the octave. Returns (Hz, score) or (None, 0)."""
    import numpy as np
    x = np.asarray(x, float)
    if len(x) < 32 or not x.any():
        return None, 0.0
    x = x - x.mean()
    n = 1 << 15
    y = np.tile(x, int(np.ceil(n / len(x))))[:n] * np.hanning(n)
    lm = np.log(np.abs(np.fft.rfft(y)) + 1e-9)
    lo, hi = int(25 * n / DSP_RATE), int(2000 * n / DSP_RATE)
    m = len(lm)

    def score(b):
        sc = 0.0
        for h in range(1, n_harm + 1):
            c = h * b
            if c + 3 >= m:
                break
            sc += lm[c - 2:c + 3].max()
        return sc
    best, bb = None, 0
    for b in range(lo, hi):
        sc = score(b)
        if best is None or sc > best:
            best, bb = sc, b
    # an octave lower fitting about as well is the fundamental (its even harmonics are the
    # ones found): FF5 sample 39 -> 234 Hz rather than 468
    # (no octave below the search range: the best stays)
    half = max(((score(b), b) for b in range(max(lo, bb // 2 - 2), bb // 2 + 3)), default=(None, 0))
    if half[0] is not None and half[0] >= best - HPS_OCTAVE_SLACK:
        best, bb = half
    return bb * DSP_RATE / n, best


def sample_pitch(ram, start, loop_start):
    """(frequency at P = 0x1000 in Hz or None, correlation, looped) of one sample."""
    s, looped, _ = brr_decode(ram, start)
    if not s:
        return None, 0.0, looped
    if looped and start <= loop_start:
        li = (loop_start - start) // 9 * 16
        body = s[li:] if 0 <= li < len(s) else []
        if len(body) >= 16:
            per, c = _autocorr_period(body[:4096], circular=True)
            if per and c >= PERIODIC:
                return DSP_RATE / per, c, True
            f, sc = _hps_pitch(body)        # ambiguous period: by the harmonics (loop tiled)
            if f:
                return f, c, True
    seg = s[min(len(s) // 8, 512):][:8192]
    per, c = _autocorr_period(seg[:4096], circular=False)
    if per and c >= PERIODIC:
        return DSP_RATE / per, c, looped
    f, sc = _hps_pitch(seg)
    return f, c, looped


# envelope rates: DSP samples between two envelope steps (rate 0 = never)
RATE = [0, 2048, 1536, 1280, 1024, 768, 640, 512, 384, 320, 256, 192, 160, 128, 96, 80, 64, 48,
        40, 32, 24, 20, 16, 12, 10, 8, 6, 5, 4, 3, 2, 1]
ENV_MAX = 0x7FF


class Voice:
    """One voice: registers, key state and the envelope (ADSR / GAIN, 0..0x7FF).
    The envelope decides when a note is really silent (drivers that never key off, one-shot
    sounds that fade), not only KON / KOFF."""
    __slots__ = ("vol_l", "vol_r", "pitch", "srcn", "adsr1", "adsr2", "gain",
                 "on", "kon_count", "env", "mode", "frac", "sample_left")

    def __init__(self):
        self.vol_l = self.vol_r = 0
        self.pitch = 0
        self.srcn = 0
        self.adsr1 = self.adsr2 = self.gain = 0
        self.on = False
        self.kon_count = 0
        self.env = 0
        self.mode = "release"      # attack / decay / sustain / release / gain
        self.frac = 0.0            # DSP samples left over towards the next envelope step
        self.sample_left = None    # one-shot sample: source samples until it ends (None = loops)

    def key_on(self):
        self.on = True
        self.kon_count += 1
        self.env = 0
        self.frac = 0.0
        self.mode = "attack" if self.adsr1 & 0x80 else "gain"

    def key_off(self):
        self.mode = "release"

    def run(self, samples):
        """Advance the envelope by `samples` DSP samples (32 kHz)."""
        if self.sample_left is not None and self.on:
            self.sample_left -= samples * self.pitch / 4096.0
            if self.sample_left <= 0:
                self.env = 0
                self.on = False
                return
        if self.mode == "gain" and not self.gain & 0x80:
            self.env = (self.gain & 0x7F) << 4          # direct gain
            return
        if self.mode == "release":                      # -8 every sample
            self.env = max(0, self.env - 8 * int(samples))
            if self.env == 0:
                self.on = False
            return
        if self.mode == "attack":
            r = (self.adsr1 & 0xF) * 2 + 1
        elif self.mode == "decay":
            r = ((self.adsr1 >> 4) & 7) * 2 + 16
        elif self.mode == "sustain":
            r = self.adsr2 & 0x1F
        else:
            r = self.gain & 0x1F
        period = RATE[r]
        if period == 0:
            return
        self.frac += samples
        steps = int(self.frac // period)
        self.frac -= steps * period
        env = self.env
        for _ in range(steps):
            if self.mode == "attack":
                env += 1024 if (self.adsr1 & 0xF) == 0xF else 32
                if env >= ENV_MAX:
                    env = ENV_MAX
                    self.mode = "decay"
                    break
            elif self.mode == "decay":
                env -= ((env - 1) >> 8) + 1
                if (env >> 8) <= (self.adsr2 >> 5):
                    self.mode = "sustain"
                    break
            elif self.mode == "sustain":
                env -= ((env - 1) >> 8) + 1
            else:                                      # GAIN modes
                m = (self.gain >> 5) & 3
                if m == 0:
                    env -= 32
                elif m == 1:
                    env -= ((env - 1) >> 8) + 1
                elif m == 2:
                    env += 32
                else:
                    env += 32 if env < 0x600 else 8
            env = max(0, min(ENV_MAX, env))
            if env == 0 and self.mode in ("sustain", "gain"):
                break
        self.env = env


class DSPState:
    """Replays DSP writes; snapshot() -> {"V1".."V8": {...}} per analysis frame.
    Same interface as apu_state.APUState for nsf2mid.build_frames: write(cyc, reg, v) returns the
    keys of the voices keyed on (KON = the note start), advance(cyc), snapshot()."""

    chips = ()
    keys = tuple(f"V{i + 1}" for i in range(8))

    def __init__(self, ram, dsp_init, cpu_hz=1024000.0):
        self.ram = ram
        self.cpu_hz = cpu_hz
        self.voices = [Voice() for _ in range(8)]
        self.regs = bytearray(dsp_init)
        self.pitch_cache = {}
        self.len_cache = {}
        self.now = None
        for i, vc in enumerate(self.voices):
            for r in range(8):
                self._voice_reg(vc, r, dsp_init[i * 16 + r])

    def advance(self, cyc):
        if self.now is None:
            self.now = cyc
            return
        if cyc <= self.now:
            return
        samples = (cyc - self.now) * 32000.0 / self.cpu_hz
        for vc in self.voices:
            vc.run(samples)
        self.now = cyc

    @staticmethod
    def _voice_reg(vc, r, v):
        if r == 0:
            vc.vol_l = v - 256 if v > 127 else v
        elif r == 1:
            vc.vol_r = v - 256 if v > 127 else v
        elif r == 2:
            vc.pitch = (vc.pitch & 0x3F00) | v
        elif r == 3:
            vc.pitch = (vc.pitch & 0xFF) | ((v & 0x3F) << 8)
        elif r == 4:
            vc.srcn = v
        elif r == 5:
            vc.adsr1 = v
        elif r == 6:
            vc.adsr2 = v
        elif r == 7:
            vc.gain = v

    def write(self, cyc, reg, v):
        self.advance(cyc)
        self.regs[reg] = v
        vi, r = reg >> 4, reg & 0xF
        if r <= 7:
            self._voice_reg(self.voices[vi], r, v)
            return ()
        if reg == 0x4C:            # KON
            out = []
            for i in range(8):
                if v >> i & 1:
                    vc = self.voices[i]
                    vc.key_on()
                    vc.sample_left = self.sample_length(vc.srcn)
                    out.append(f"V{i + 1}")
            return out
        if reg == 0x5C:            # KOFF
            for i in range(8):
                if v >> i & 1:
                    self.voices[i].key_off()
        return ()

    def sample_length(self, srcn):
        """Length of a one-shot sample in source samples (None = it loops)."""
        if srcn not in self.len_cache:
            start, _ = sample_table(self.ram, self.regs[0x5D]).get(srcn, (0, 0))
            s, looped, _ = brr_decode(self.ram, start)
            self.len_cache[srcn] = None if looped else float(len(s))
        return self.len_cache[srcn]

    def srcn_pitch(self, srcn):
        if srcn not in self.pitch_cache:
            tab = sample_table(self.ram, self.regs[0x5D])
            start, loop = tab.get(srcn, (0, 0))
            self.pitch_cache[srcn] = sample_pitch(self.ram, start, loop)
        return self.pitch_cache[srcn]

    def sample_features(self, srcn):
        """For the drum decision (spc_drums): looped, period correlation, spectral centroid (Hz)
        of the first 4096 samples and length (ms), both at the original rate (P = 0x1000)."""
        import numpy as np
        start, _ = sample_table(self.ram, self.regs[0x5D]).get(srcn, (0, 0))
        s, looped, _ = brr_decode(self.ram, start)
        x = np.asarray(s[:4096], float)
        cen = 0.0
        if len(x) >= 32:
            x = x - x.mean()
            sp = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
            if sp.sum() > 0:
                cen = float((sp * np.fft.rfftfreq(len(x), 1 / DSP_RATE)).sum() / sp.sum())
        return {"looped": looped, "corr": self.srcn_pitch(srcn)[1], "cen": cen,
                "ms": len(s) * 1000.0 / DSP_RATE}

    def snapshot(self):
        out = {}
        for i, vc in enumerate(self.voices):
            base, corr, looped = self.srcn_pitch(vc.srcn)
            f = base * vc.pitch / 4096.0 if base and vc.pitch else None
            loud = max(abs(vc.vol_l), abs(vc.vol_r)) * vc.env / ENV_MAX     # 0..128
            vol = 0 if not loud else max(1, min(15, int(round(loud * 15 / 96))))
            out[f"V{i + 1}"] = {
                "period": vc.pitch,
                "freq": f or 0.0,
                "note": freq_to_note(f) if f else None,
                "vol": vol if vc.env > 0 else 0,
                "duty": vc.srcn,
                "srcn": vc.srcn,
                "kon": vc.kon_count,
                "noise": bool(self.regs[0x3D] >> i & 1),
            }
        return out
