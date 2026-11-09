"""
Note extraction from per-frame APU snapshots (tonal channels: P1, P2, TRI).

Design (see docs/spec.md "Phase 2 ノート判定"):
  Note-on cues
    1. hi-period register write ($4003/$4007/$400B) = hardware trigger.
       If the trigger frame is silent (SMB style "trigger, vol 0, sound next frame")
       the note starts at the trigger frame provided the pitch matches.
    2. pitch moves to another semitone and stays there (>= 2 frames).
    3. silence -> sound.
  NOT note-on
    - duty change (DQ2 duty envelope), volume rises / tremolo (DQ3, Okhotsk ni Kiyu).
  Reverb tail ("echo")
    Many drivers (DQ2-4, SMB USA) keep the pitch sounding at a low volume after the
    musical note has ended. The tail start (gate-off) is the first frame g where:
      - every later volume in the note is <= vol[g], and
      - vol[g] <= peak/2, and
      - vol[g] dropped by >= 3 from the previous frame, or vol[g] <= max(2, peak/4)
      - at least 2 frames of tail remain
    By default the MIDI note ends at g; keep_tail=True keeps the full length.
"""

PITCH_SPLIT = 0.75        # semitones away from the note's pitch to count as a new note
PITCH_HOLD = 2            # frames the new pitch must persist
TRIGGER_SPAM_RATIO = 0.6  # trigger on more than this share of sounding frames -> ignore triggers


class Note:
    __slots__ = ("ch", "start", "end", "gate_end", "pitch", "vols", "duties", "pitches", "cue")

    def __init__(self, ch, start, pitch, cue):
        self.ch = ch
        self.start = start          # first frame
        self.end = None             # frame after last sounding frame
        self.gate_end = None        # frame where the reverb tail starts (== end if no tail)
        self.pitch = pitch          # MIDI note number
        self.vols = []
        self.duties = []
        self.pitches = []           # per-frame pitch (float semitones, None while silent)
        self.cue = cue              # what started the note: trig / pitch / sound

    @property
    def peak(self):
        g = int(round(self.gate_end - self.start)) if self.gate_end is not None else len(self.vols)
        return max(self.vols[:max(1, g)]) if self.vols else 0

    @property
    def has_tail(self):
        return self.gate_end is not None and self.gate_end < self.end


def _frame_info(state, written, ch):
    c = state[ch]
    trig = 3 in written[ch]
    if ch == "TRI":
        vol = 15 if c["vol"] else 0
        duty = None
    else:
        vol = c["vol"]
        duty = c["duty"]
    note = c["note"]
    if note is not None and not (0 <= note <= 127):
        note = None
    if note is None:
        vol = 0
    return vol, note, trig, duty


def find_gate_end(vols):
    """Return index (relative to note start) where the reverb tail starts, or len(vols)."""
    n = len(vols)
    if n < 3:
        return n
    peak = max(vols)
    # suffix maximum: max(vols[i:])
    suf = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suf[i] = max(vols[i], suf[i + 1])
    peak_i = vols.index(peak)
    rose = False            # volume rose again after the attack peak (tremolo / modulation)
    for g in range(1, n - 1):
        v = vols[g]
        if g > peak_i and v > vols[g - 1]:
            rose = True
        if suf[g] > v:          # volume rises again later -> not a tail
            continue
        if v * 2 > peak:
            continue
        drop = vols[g - 1] - v
        low_floor = v <= max(2, peak / 4.0)
        # After a tremolo (Okhotsk ni Kiyu: B,4,A,5,9,6,8,7 then held at 4) a sudden drop is part
        # of the modulation and the following level is the sustain, so only a low floor counts.
        if low_floor or (drop >= 3 and not rose):
            return g
    return n


SWELL_MIN_RISE = 4     # v2.9.29: times a fade-in steps up before a same-pitch retrigger is its decay
SWELL_MIN_FRAMES = 16
SWELL_TOP_SHARE = 0.25  # the fade-in reached its top only in this last share of the note


def _swell_retrigger(cur, pitch, vol):
    """A retrigger that only switches a fade-in to its decay is not a new note.

    Platoon t1 P1: C#4 v0 1 2 .. B (45 frames), then $4003 written again at C#4 v7 and decaying;
    bar 8 G4 v0 .. 8 then v7. The note's volume never fell, it climbed SWELL_MIN_RISE steps or more,
    and the retrigger comes in no louder than where the fade-in stopped (a repeated note would
    start again from the bottom, or jump up as an accent). The note must still be climbing:
    a quick attack then a held level (SD Sangoku Bushou Retsuden t2: 6 7 9 A A A A A, Monty on the
    Run t1: 0 5 5 5 ..) is a note of its own and the retrigger the next one.
    """
    if cur is None or cur.pitch != pitch or len(cur.vols) < SWELL_MIN_FRAMES:
        return False
    v = cur.vols
    steps = [b - a for a, b in zip(v, v[1:])]
    if any(s < 0 for s in steps) or sum(1 for s in steps if s > 0) < SWELL_MIN_RISE:
        return False
    last = v[-1]
    top = len(v) - v.index(last)
    return top <= SWELL_TOP_SHARE * len(v) and vol <= last and vol * 2 >= last


def _release_retrigger(cur, pitch, vol, f, infos):
    """A retrigger that only starts the release of a decayed note is not a new note (v2.9.31).

    Mr. Gold t1 P1: E5 v F F F F E E E E D D D D C C C C, then $4003 written again at E5 and held at
    v6 for 6 frames; A4 decays to 6, then v3 flat for 32 frames, then v2 flat. The note decayed
    (never rose, ended below its start), the retrigger comes in quieter than where the decay
    stopped, and it stays flat (no envelope of its own) until the next trigger, rest or other
    pitch. A soft repeated note would have an envelope of its own; a driver without envelopes
    has no decayed note before it.
    """
    if cur is None or cur.pitch != pitch or len(cur.vols) < 2:
        return False
    v = cur.vols
    if v[-1] >= v[0] or any(b > a for a, b in zip(v, v[1:])) or not 0 < vol < v[-1]:
        return False
    n = 0
    for vol2, note2, trig2, _ in infos[f + 1:]:
        if vol2 == 0 or trig2 or abs(note2 - pitch) >= PITCH_SPLIT:
            break
        if vol2 != vol:
            return False
        n += 1
    return n >= 1


REATTACK_LOW = 0.25    # v2.9.33: a note decayed to this share of its attack level or lower ...
REATTACK_HIGH = 0.75   # ... and its volume jumps back to this share of it or higher = a repeated note
REATTACK_MIN_FRAMES = 5  # ... after sounding at least this long (Castle of Dragon t3: 8 6 2 / 7 5 1 / 6 4 4 ..
                         # is one note with a stuttering attack, not three)


def _volume_reattack(cur, pitch, vol, vol_written):
    """A same-pitch note struck again by a volume write alone (no $4003/$4007 write) is a new note.

    Tiny Toon Adventures 2 t1 P2 (bar 5): D#4 v 8 7 6 6 6 5 4 3 2 1, then $4004 = 8 and the same
    decay, three times (user: three notes, not one). The note must have decayed without rising
    (a tremolo or swell rises and falls) down to REATTACK_LOW of its attack, and come back to
    REATTACK_HIGH of it or louder in one frame, after REATTACK_MIN_FRAMES or more.
    """
    if cur is None or not vol_written or cur.pitch != pitch or len(cur.vols) < REATTACK_MIN_FRAMES:
        return False
    v = cur.vols
    top = max(v[:2])
    if any(b > a for a, b in zip(v[1:], v[2:])):
        return False
    return v[-1] <= REATTACK_LOW * top and vol >= REATTACK_HIGH * top and vol - v[-1] >= 3


def extract_channel(frames, ch, keep_tail=False):
    infos = [_frame_info(f["state"], f["written"], ch) for f in frames]

    sounding = sum(1 for v, _, _, _ in infos if v > 0)
    trigs = sum(1 for v, _, t, _ in infos if t and v > 0)
    use_trig = not (sounding and trigs / sounding > TRIGGER_SPAM_RATIO)

    notes = []
    cur = None
    pending_trig = None     # (frame, note) of a trigger on a silent frame
    off_count = 0           # consecutive frames away from current pitch

    def close(at):
        nonlocal cur
        if cur is None:
            return
        cur.end = at
        g = find_gate_end(cur.vols)
        cur.gate_end = cur.end if keep_tail else cur.start + g
        notes.append(cur)
        cur = None

    for f, (vol, note, trig, duty) in enumerate(infos):
        trig = trig and use_trig
        if vol == 0:
            if trig and note is not None:
                pending_trig = (f, note)
            elif pending_trig and f - pending_trig[0] > 2:
                pending_trig = None
            close(f)
            off_count = 0
            continue

        rp = int(round(note))
        start_new = None
        if cur is None:
            start_new = "sound"
            start_frame = f
            if trig:
                start_new = "trig"
            elif pending_trig and abs(pending_trig[1] - note) < 0.5 and f - pending_trig[0] <= 2:
                start_new = "trig"
                start_frame = pending_trig[0]
        elif trig and not _swell_retrigger(cur, rp, vol) and not _release_retrigger(cur, rp, vol, f, infos):
            start_new = "trig"
            start_frame = f
        elif (not trig and ch != "TRI" and abs(note - cur.pitch) < PITCH_SPLIT
              and _volume_reattack(cur, rp, vol, 0 in frames[f]["written"].get(ch, ()))):
            start_new = "vol"
            start_frame = f
        else:
            if abs(note - cur.pitch) >= PITCH_SPLIT:
                off_count += 1
                if off_count >= PITCH_HOLD:
                    # split: the new note began off_count-1 frames ago
                    start_new = "pitch"
                    start_frame = f - off_count + 1
            else:
                off_count = 0
        pending_trig = None

        if start_new:
            if cur is not None and start_frame < f:
                # move the already-collected frames of the new pitch out of the old note
                k = f - start_frame
                moved_v = cur.vols[-k:]
                moved_d = cur.duties[-k:]
                moved_p = cur.pitches[-k:]
                del cur.vols[-k:]
                del cur.duties[-k:]
                del cur.pitches[-k:]
                close(start_frame)
                cur = Note(ch, start_frame, rp, start_new)
                cur.vols.extend(moved_v)
                cur.duties.extend(moved_d)
                cur.pitches.extend(moved_p)
            else:
                close(f)
                cur = Note(ch, start_frame, rp, start_new)
                # frames between a silent trigger and the first sounding frame
                for _ in range(f - start_frame):
                    cur.vols.append(0)
                    cur.duties.append(duty)
                    cur.pitches.append(None)
            off_count = 0
        cur.vols.append(vol)
        cur.duties.append(duty)
        cur.pitches.append(note)

    close(len(infos))
    return notes, {"trigger_cue": use_trig, "trigger_ratio": (trigs / sounding) if sounding else 0.0}


ARP_GAP = 3        # v2.9.27: frames between the notes of an arpeggio (same as nsf2mid.FAST_GAP)
ARP_MIN_FRAMES = 12  # an arpeggio lasts at least this long (Ganbare Pennant Race! P1: a 9-frame G2 E2 buzz
                     # once a beat is a drum, not a chord)


def _drum_roll(run, k):
    """A cycle retriggered once, always on the same note, and falling from it all the way is a
    pitch-drop drum played again and again, not an arpeggio (Kart Fighter TRI: F5 C#5 A#4 every
    6 frames). The run may start anywhere in the cycle."""
    trig = [j for j, n in enumerate(run) if "trig" in n.cue]
    if not trig or any((j - trig[0]) % k for j in trig) or len(trig) < len(run) // k:
        return False
    for j in range(1, len(run)):
        if (j - trig[0]) % k and run[j].pitch >= run[j - 1].pitch:
            return False
    return True


def arpeggio_end(notes, i, gap=ARP_GAP, min_notes=4):
    """End index of an arpeggio starting at notes[i] (i + 1 if there is none): notes gap frames or
    less apart, each starting where the one before ends (no silence: Mega Man 2 TRI plays its falling
    kick A#4 D#4 A3 G3 every 8 frames with a silent frame between), cycling through 2-4 pitches and
    going round at least twice for 3-4 pitches (a fast scale is not one), lasting ARP_MIN_FRAMES or more.
    Not a drum roll (_drum_roll).
    Balloon Fight t1 P2: G#4 E4 every 3 frames; M.C. Kids t2 P2: G4 B4 D5 every 2 frames."""
    best = i + 1
    for k in (2, 3, 4):
        if i + k >= len(notes) or len({notes[i + j].pitch for j in range(k)}) < k:
            continue
        e = i + 1
        while (e < len(notes) and notes[e].start - notes[e - 1].start <= gap
               and notes[e].start <= notes[e - 1].end
               and (e - i < k or notes[e].pitch == notes[e - k].pitch)):
            e += 1
        if (e - i >= max(min_notes, 2 * k) and notes[e - 1].end - notes[i].start >= ARP_MIN_FRAMES
                and not (k >= 3 and _drum_roll(notes[i:e], k))):
            best = max(best, e)
    return best


def arpeggio_notes(notes):
    """Indices of the notes that make up an arpeggio (arpeggio_end)."""
    marked = set()
    i = 0
    while i < len(notes):
        e = arpeggio_end(notes, i)
        if e - i > 1:
            marked.update(range(i, e))
        i = e
    return marked


def merge_slides(notes, keep_tail=False):
    """Merge fast pitch glides into one note.

    A glide shows up as a chain of short notes split by pitch change (e.g. the
    Mega Man 2 "triangle kick": B4 -> G4 -> D#4 -> C4 -> A#3 within 10 frames).
    A note whose length is <= SLIDE_MAX frames absorbs the following contiguous
    pitch-split note.
    v2.9.27: not the notes of an arpeggio (arpeggio_notes): its pitches come back, a glide's do not
    (M.C. Kids t2 P2: the D5 of G4 B4 D5 was absorbed into the B4).
    """
    arp = arpeggio_notes(notes)
    for idx in arp:
        notes[idx].cue += "+arp"        # not a pitch-drop drum either (drums.split_drop_drums)
    out = []
    for idx, n in enumerate(notes):
        if out and idx not in arp:
            p = out[-1]
            # a long pitch-split note after a glide is the held target note: keep it separate
            if (n.cue == "pitch" and n.start == p.end and n.end - n.start <= SLIDE_MAX
                    and (p.end - p.start <= SLIDE_MAX or "slide" in p.cue)):
                p.vols.extend(n.vols)
                p.duties.extend(n.duties)
                p.pitches.extend(n.pitches)
                p.end = n.end
                g = find_gate_end(p.vols)
                p.gate_end = p.end if keep_tail else p.start + g
                if p.cue == "pitch":
                    p.cue = "slide"
                elif p.cue != "slide":
                    p.cue = p.cue + "+slide"
                continue
        out.append(n)
    return [n for n in out if n.end - n.start >= MIN_FRAMES]


SLIDE_MAX = 3      # frames
ONSET_MERGE = 2    # tempo onsets closer than this (frames) are one event
MIN_FRAMES = 2     # notes shorter than this are dropped


def extract_notes(frames, channels=("P1", "P2", "TRI"), keep_tail=False):
    result = {}
    stats = {}
    for ch in channels:
        lst, stats[ch] = extract_channel(frames, ch, keep_tail)
        result[ch] = merge_slides(lst, keep_tail)
    return result, stats


def noise_onsets(frames):
    """Frames where the noise channel is (re)triggered and audible. Used for tempo only (Phase 2)."""
    out = []
    for f in frames:
        if "NOI" not in f["state"]:          # SPC: no noise channel of its own
            return out
        if 3 in f["written"]["NOI"] and f["state"]["NOI"]["vol"] > 0:
            out.append(f["frame"])
    return out


def tempo_onsets(notes, frames):
    """Onsets used for tempo detection.

    Pitch-split notes are excluded (glides, legato runs are less reliable), and
    onsets within ONSET_MERGE frames of each other are merged (some drivers update the
    channels on different frames).
    """
    raw = [n.start for lst in notes.values() for n in lst if not n.cue.startswith("pitch")]
    raw += noise_onsets(frames)
    raw = sorted(set(raw))
    out = []
    for o in raw:
        if out and o - out[-1] <= ONSET_MERGE:
            continue
        out.append(o)
    return out
