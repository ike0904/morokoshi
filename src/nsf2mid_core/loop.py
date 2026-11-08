"""
Loop / end detection (Phase 3).

Game music normally loops forever. After the loop point, every channel repeats
its event sequence with a fixed period L. For each channel's event list
(start_frame, token) we look for a lag k (in events) such that, scanning back
from the end, token[i] == token[i+k] and the time difference stays within
TOL frames of L. The scan stops at the first mismatch -> s (earliest matching
event). A lag is valid when the matched part spans (REPEATS - 1) periods, i.e. the
loop body was heard REPEATS times in a row (a section played twice and then followed
by a chorus must not be taken for the loop).
Among valid lags the one with the earliest s wins (ties: smallest L), because
the true loop repeats back to the loop point while shorter internal repeats
(A A B ...) break earlier.

Channels are combined: L = the largest per-channel period (others divide it),
each channel is re-scanned with that period and the loop start is the latest
per-channel start (the point after which *all* channels repeat).

Accumulator-tempo drivers (Dragon Quest) may shift onsets by a frame between
repetitions, hence the tolerance. v0.1.31: the period itself can be fractional (Dragon Quest IV
t13: 3234.5 frames, single repeats measure 3234-3237), so the scan follows the mean of the
repeats found so far instead of the last one, with a tolerance of 3 frames.
"""

TOL = 3                 # frames (2 until v0.1.30)
MIN_EVENTS = 8          # a channel needs this many events to take part
MIN_LOOP_FRAMES = 120   # ignore periods shorter than 2 s
LOOSE_MIN = 2           # v0.1.38: events of a non-repeating channel inside the loop that refute it
REPEATS = 3             # the loop body must be heard this many times in a row
MULT_MAX_FRAMES = 6000  # v0.1.44: longest multiple of the period tried for a non-repeating channel
LONG_LOOP_FRAMES = 3600  # v2.9.31: a loop this long (60 s) is taken after 2 rounds (Business Wars t1: 222 s)
LCM_MAX_FRAMES = 30000  # v2.9.31: longest loop made of channels that loop on their own (500 s)

from math import gcd


def _scan(t, tok, k, period=None):
    n = len(t)
    if k <= 0 or k >= n:
        return None
    last = n - 1 - k
    if tok[n - 1] != tok[last]:
        return None
    L = t[n - 1] - t[last] if period is None else period
    total, cnt = 0, 0
    i = last
    while i >= 0 and tok[i] == tok[i + k] and abs((t[i + k] - t[i]) - L) <= TOL:
        if period is None:
            total += t[i + k] - t[i]
            cnt += 1
            L = total / cnt
        i -= 1
    s = i + 1
    if s > last:
        return None
    span = t[last] - t[s]
    return s, int(round(L)), span


def repeats_for(period):
    """How many rounds of a loop must be heard: REPEATS, but 2 for loops of LONG_LOOP_FRAMES and more
    (v2.9.31: a 222 s loop needed 666 s of emulation). The rule of 3 is for short sections played
    twice before a chorus."""
    return 2 if period >= LONG_LOOP_FRAMES else REPEATS


def channel_period(events):
    """events: sorted [(frame, token)]. Returns (loop_start_frame, period) or None."""
    if len(events) < MIN_EVENTS:
        return None
    t = [e[0] for e in events]
    tok = [e[1] for e in events]
    n = len(t)
    best = None
    for k in range(1, n // 2 + 1):
        r = _scan(t, tok, k)
        if r is None:
            continue
        s, L, span = r
        if L < MIN_LOOP_FRAMES or span < (repeats_for(L) - 1) * L - TOL or (n - s) < MIN_EVENTS:
            continue
        cand = (t[s], L)
        if best is None or cand[0] < best[0] - TOL or (abs(cand[0] - best[0]) <= TOL and L < best[1]):
            best = cand
    return best


def channel_start_for_period(events, period):
    """Earliest frame from which `events` repeat with `period` until the end."""
    t = [e[0] for e in events]
    tok = [e[1] for e in events]
    n = len(t)
    # find k whose time difference at the end matches the period
    best = None
    for k in range(1, n):
        last = n - 1 - k
        if last < 0:
            break
        d = t[n - 1] - t[last]
        if d > period + TOL:
            break
        if abs(d - period) <= TOL:
            r = _scan(t, tok, k, period)
            if r and (best is None or r[0] < best):
                best = r[0]
    return None if best is None else t[best]


def repeat_share(events, start, period):
    """Share of the events from `start` on (up to one period before the end) that come again
    one period later (same token, within TOL frames). Notes that merge or split differently in
    one round leave it high; a channel that plays something else in later rounds does not."""
    by_tok = {}
    for f, tok in events:
        by_tok.setdefault(tok, []).append(f)
    end = events[-1][0] - period if events else 0
    sel = [(f, tok) for f, tok in events if start <= f <= end]
    if not sel:
        return 0.0
    hit = sum(1 for f, tok in sel if any(abs(g - f - period) <= TOL for g in by_tok[tok]))
    return hit / len(sel)


def _independent_loop(channel_events, per):
    """v2.9.31: channels that loop on their own with different lengths (Relics t2: P1 every 2688
    frames, P2 every 3072, the triangle every 384) - the whole tune comes back after the least
    common multiple (21504 frames = 358 s), which can never be heard REPEATS times. Each channel has
    been heard REPEATS times with its own period (channel_period), so the loop is the LCM from the
    latest channel start. Periods may be a frame or two off: they are taken as multiples of the
    shortest one when they are close to one. Channels without a period of their own (Relics t2:
    drum bursts every ~9076 frames, which drift by a few frames) are left as they are.
    Returns the loop dict with "independent": True, or None."""
    base = min(L for _, L in per.values())
    mult = [round(L / base) for _, L in per.values()]
    if all(abs(L - k * base) <= TOL for (_, L), k in zip(per.values(), mult)):
        lcm = 1
        for k in mult:
            lcm = lcm * k // gcd(lcm, k)
        period = lcm * base
    else:
        # periods that are not multiples of the shortest (Super Team Games t3: P1 1024, the triangle
        # 384, the drums 192 frames): the exact least common multiple (3072)
        period = 1
        for _, L in per.values():
            L = int(round(L))
            period = period * L // gcd(period, L)
    if period > LCM_MAX_FRAMES:
        return None
    start = max(s for s, _ in per.values())
    return {"start": start, "period": period, "channels": per, "independent": True}


def detect_loop(channel_events, strict=False):
    """channel_events: {name: sorted [(frame, token)]}. strict (SPC, v0.1.38): channels without
    a repeat of the common period that still play in the loop refute it.

    Returns dict(start=frame, period=frames, channels={name: (start, period)}) or None.
    """
    per = {}
    for name, ev in channel_events.items():
        r = channel_period(ev)
        if r:
            per[name] = r
    if not per:
        return None
    period = max(L for _, L in per.values())
    starts = {}
    loose = []
    for name, ev in channel_events.items():
        if len(ev) < MIN_EVENTS:
            continue
        s = channel_start_for_period(ev, period)
        if s is None:
            # a channel that does not repeat with the common period -> no reliable loop
            if name in per:
                return _independent_loop(channel_events, per)
            loose.append(name)
            continue
        if strict and s == ev[0][0]:
            # v0.1.38: a channel that repeats from its very first note was silent before it, which
            # repeats too: it enters in the second half of the loop (FF6 "The Mines of Narshe":
            # two voices from 52 s / 70 s in a loop from 17 s), it does not start the loop there
            s -= period
        starts[name] = s
    if not starts:
        return None
    # v0.1.31: a channel without a period of its own whose repeats start more than a period
    # after the others' does not repeat reliably (Dragon Quest IV t13: short triangle notes merge
    # differently in each round); it must not push the loop start back
    base = max((v for k, v in starts.items() if k in per), default=None)
    if base is not None:
        starts = {k: v for k, v in starts.items()
                  if k in per or v <= base + period or repeat_share(channel_events[k], base, period) < 0.9}
    # (not before the first note of the tune: every voice may repeat from its first note)
    first = min(ev[0][0] for ev in channel_events.values() if ev)
    start = max(first, max(starts.values()))
    # v0.1.38: a channel that still plays in the loop but does not repeat (a melody over a
    # repeating ostinato: FF6 "The Mines of Narshe", 2.18 s found after 17 s) -> not the loop yet
    busy = [name for name in loose
            if sum(1 for f, _ in channel_events[name] if f >= start) >= LOOSE_MIN
            and repeat_share(channel_events[name], start, period) < 0.9]
    if busy:
        # v0.1.44: it may repeat with a multiple of the period (Kkachi-Wa Norae Chingu t1: bass and
        # chords every 512 frames, the melody A A' A A' B B' B'' B''' every 4096 - the B phrases
        # with other echo notes each round, 0.94 alike); the smallest multiple up to
        # MULT_MAX_FRAMES is the loop. Until the tune has been heard long enough to test them all,
        # no loop yet.
        last = max(ev[-1][0] for ev in channel_events.values() if ev)
        for k in range(2, int(MULT_MAX_FRAMES // period) + 1):
            if last - start < 2 * k * period:
                return None
            if all(repeat_share(channel_events[name], start, k * period) >= 0.9 for name in busy):
                period *= k
                break
        else:
            if strict:                  # SPC only (on NES it changed 3 tunes of the test set)
                return None
    return {"start": start, "period": period, "channels": per}


def song_end(channel_events, emulated_frames, silence_frames):
    """Frame of the last event if the song stops (no events in the final
    `silence_frames` of the emulation), else None."""
    last = max((ev[-1][0] for ev in channel_events.values() if ev), default=None)
    if last is None:
        return None
    if emulated_frames - last >= silence_frames:
        return last
    return None
