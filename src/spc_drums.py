"""
SPC drums (v0.1.37, phase 3): which samples are percussion, and which GM drum note each hit gets.

The S-DSP has no drum channel: drums are samples played on ordinary voices. The decision is made
per sample (SRCN) from the waveform and from how the song plays it:

- percussion sample:
  - looped with a noisy loop (no clear period) played at <= 3 pitches -> cymbal
  - one-shot without a clear pitch (period correlation < PITCH_CLEAR) played at <= 2 pitches,
    or a noisy one-shot (correlation < NOISY) at any number of pitches
  - one-shot with a clear pitch but a low, dull sound (effective spectral centroid < LOW_HZ,
    a sine-like kick / tom) played at <= 3 pitches
  - one-shot played at <= 2 pitches above HIGH_NOTE (no instrument plays there); with a clear
    pitch and a bright sound -> cowbell 56 (FF5 "Mambo de Chocobo!")
  - every note of a voice with the noise generator on (NON)
  A one-shot played at many pitches is an instrument (pizzicato, slap bass...), not a drum.
- GM note of a hit, from the sound at the rate it is played (the pitch register scales the
  centroid and the length of the sample):
  - noisy loop / long noisy one-shot -> crash cymbal 49
  - centroid < LOW_HZ at one pitch -> bass drum 36
  - centroid < MID_HZ (clear pitch): one pitch -> low tom 45 (timpani, conga...), several
    pitches -> toms 41..50 from the lowest to the highest pitch
  - centroid < HAT_HZ -> snare 38
  - brighter: short -> closed hi-hat 42, longer -> open hi-hat 46
Measured on FF4 / FF5 / FF6 / Chrono Trigger / ActRaiser / Zelda ALttP battle and field themes.

Two different sounds never share a GM note (unique_notes).

Override per sample with --drum-map "S67=38,S12=0" (0 = not a drum: keep the notes).
"""

from collections import Counter

from drums import DrumHit

PITCH_CLEAR = 0.9     # period correlation of a clearly pitched sample (spc_dsp.PERIODIC)
NOISY = 0.5           # below: noise (snare, hi-hat, cymbal)
LOW_HZ = 300.0        # effective centroid of kicks / low toms
MID_HZ = 900.0
HAT_HZ = 4500.0
HAT_CLOSED_MS = 140.0
CRASH_MS = 500.0
HIGH_NOTE = 96        # a one-shot at 1-2 pitches above C7 (ActRaiser S17 at 115): percussion
TOMS = (41, 43, 45, 47, 48, 50)


def _vel(peak):
    return max(1, min(127, int(round(peak * 127 / 15))))


def sample_kind(feat, pitches):
    """'cymbal' / 'drum' / 'low' (kick or tom by pitch count) / None (an instrument).
    pitches: the sorted MIDI notes the song plays the sample at."""
    looped, corr, cen = feat["looped"], feat["corr"], feat["cen"]
    n_pitches = len(pitches)
    if looped:
        return "cymbal" if corr < NOISY and n_pitches <= 3 else None
    if corr < NOISY or (corr < PITCH_CLEAR and n_pitches <= 2):
        return "drum"
    if cen * feat["rate"] < LOW_HZ and n_pitches <= 3:
        return "low"
    if n_pitches <= 2 and pitches and pitches[0] >= HIGH_NOTE:
        return "bell"
    return None


def hit_gm(feat, kind, rate, rank, n_pitches):
    cen = feat["cen"] * rate
    ms = feat["ms"] / rate if rate > 0 else feat["ms"]
    if kind == "bell" and cen >= MID_HZ:
        return 56
    if kind == "cymbal" or (feat["corr"] < NOISY and ms >= CRASH_MS):
        return 49
    if cen < LOW_HZ and n_pitches <= 1:
        return 36
    if cen < MID_HZ and (cen < LOW_HZ or feat["corr"] >= NOISY):
        if n_pitches <= 1:
            return 45
        return TOMS[int(round(rank * (len(TOMS) - 1) / (n_pitches - 1)))]
    if cen < HAT_HZ:
        return 38
    return 42 if ms <= HAT_CLOSED_MS else 46


def split_spc_drums(notes, frames, dsp, drum_map=None):
    """notes: {"V1".."V8": [Note]} -> (tonal notes, drum hits). Drum hits keep the voice as src."""
    drum_map = drum_map or {}
    tonal, hits = {}, []
    for ch, lst in notes.items():
        by = {}
        for n in lst:
            by.setdefault(n.duties[0] if n.duties else -1, []).append(n)
        keep = []
        for srcn, ns in by.items():
            st = [frames[min(len(frames) - 1, int(n.start))]["state"][ch] for n in ns]
            noise = [s.get("noise") for s in st]
            pitches = sorted({n.pitch for n, nz in zip(ns, noise) if not nz})
            forced = drum_map.get(("S", srcn))
            if forced == 0:
                keep += ns
                continue
            feat = dsp.sample_features(srcn)
            rates = Counter(s["period"] for s, nz in zip(st, noise) if not nz)
            feat["rate"] = rates.most_common(1)[0][0] / 4096.0 if rates else 1.0
            kind = "drum" if forced else sample_kind(feat, pitches)
            for n, s, nz in zip(ns, st, noise):
                if nz:          # noise generator: hi-hat / cymbal by length
                    d = n.gate_end - n.start
                    gm, info = (42 if d <= 8 else 46 if d <= 20 else 49), "noise"
                elif kind is None:
                    keep.append(n)
                    continue
                else:
                    rate = s["period"] / 4096.0
                    gm = forced or hit_gm(feat, kind, rate, pitches.index(n.pitch), len(pitches))
                    info = f"S{srcn} cen {feat['cen'] * rate:.0f}Hz {feat['ms'] / max(rate, 1e-3):.0f}ms"
                hits.append(DrumHit(ch, n.start, n.gate_end, gm, _vel(n.peak),
                                    (ch, "noise" if nz else srcn), info))
        if keep:
            tonal[ch] = sorted(keep, key=lambda n: n.start)
    unique_notes(hits, {k[1] for k in drum_map if k[0] == "S" and drum_map[k]})
    return tonal, sorted(hits, key=lambda d: d.start)


# other GM notes for a sound whose note another sample already uses (closest kind first)
ALTERNATIVES = {
    36: (35, 41, 43), 35: (36, 41, 43), 38: (40, 37, 39, 54), 40: (38, 37, 39, 54),
    37: (39, 40, 38), 39: (37, 40, 54), 42: (44, 54, 70, 69), 44: (42, 54, 70, 69),
    46: (53, 55, 51, 59), 49: (57, 52, 55, 51), 57: (49, 52, 55, 51), 56: (75, 76, 77, 67, 68),
    41: (43, 45, 47, 48, 50), 43: (41, 45, 47, 48, 50), 45: (47, 43, 48, 41, 50),
    47: (45, 48, 43, 50, 41), 48: (47, 50, 45, 43, 41), 50: (48, 47, 45, 43, 41),
}
PERCUSSION = range(35, 82)


def unique_notes(hits, fixed=()):
    """v0.1.37 (user request): two different sounds (samples, or the noise generator) never share
    a GM note. The sound with more hits keeps its note; the other moves to a related unused note
    (ALTERNATIVES), else the nearest unused percussion note. Samples set with --drum-map keep
    their note. The same sample may use several notes (toms, rates)."""
    groups = {}
    for h in hits:
        groups.setdefault((h.kind[1], h.gm), []).append(h)
    owner = {}
    order = sorted(groups, key=lambda g: (g[0] not in fixed, -len(groups[g])))
    for snd, gm in order:
        if snd in fixed or owner.get(gm, snd) == snd:
            owner.setdefault(gm, snd)
            continue
        free = [x for x in ALTERNATIVES.get(gm, ()) if x not in owner]
        free = free or sorted((x for x in PERCUSSION if x not in owner), key=lambda x: abs(x - gm))
        if not free:
            continue
        owner[free[0]] = snd
        for h in groups[(snd, gm)]:
            h.gm = free[0]
