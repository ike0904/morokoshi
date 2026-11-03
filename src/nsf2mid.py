"""
nsf2mid - NSF to MIDI converter (derived from morokoshi)

Phase 1: 6502 emulation + APU register log / per-frame channel state dump.
Phase 2: note extraction (P1/P2/TRI), tempo detection, quantized MIDI output.
Phase 3: drums (noise / DPCM / triangle glides -> GM percussion), loop / end detection.
Phase 4: GUI (nsf2mid_gui.py). Started when no arguments are given.
Phase 5: expansion audio (expansion.py): FDS, VRC6, VRC7, MMC5, N163, Sunsoft 5B on MIDI ch 6-.
Phase 6: GBS (Game Boy, gbs.py / cpu_sm83.py / gb_apu.py): Square 1/2, Wave, Noise on MIDI ch 1-4.
Phase 7: SPC (Super Famicom, spc.py / cpu_spc700.py / spc_dsp.py): 8 voices on MIDI ch 1-8, one track
         per sample (in progress: drums and tempo to come).

Usage:
    python nsf2mid.py                (GUI)
    python nsf2mid.py FILE.nsf|FILE.gbs|FILE.zip [-t TRACK] [-s SECONDS] [-o OUTDIR] [--info] [--dump]
                      [--keep-tail] [--no-quantize] [--unit FRAMES] [--rows-per-beat N] [--tempo auto|half|double]
                      [--loops N] [--no-loop] [--drop-drums N] [--drum-map MAP] [--triplets auto|on|off] [--mid-out FILE.mid]

バージョン履歴:
  v0.1.11 (2026-10-04) - 初版〜Phase 3: 6502 エミュレータ・APU レジスタログ・ノート抽出・テンポ/拍子検出・MIDI 出力・
                         ノイズ/DPCM/三角波ドラム・ループ/曲終端検出・シャッフル/リタルダンド対応
  v0.1.12 (2026-10-05) - Phase 4: GUI (nsf2mid_gui.py、引数なしで起動)・変換処理を convert() に分離 (中止対応)
  v0.1.13 (2026-10-08) - GUI の見た目を morokoshi に合わせる・簡易再生 (libgme)
  v0.1.17 (2026-10-18) - NSF 入りの zip を直接読み込み・3 連ノリ検出 (--triplets)・GUI 改善 (前後の曲ボタン、開くアイコン＋履歴、
                         全チェック、ショートカット)・簡易再生の 5 秒無音停止を廃止
  v0.1.18 (2026-11-01) - --mid-out: 指定パスに .mid のみ出力 (morokoshi 統合用。notes.csv / ダンプは出さない)
  v0.1.19 (2026-11-01) - --tempo auto/half/double (自動検出したテンポを区間ごとに半分/2倍)・--loops 0 でループ検出なし。
                         GUI: 「1 拍の行数」→「テンポ」(自動/半分/2倍)、「ループ検出をしない」を廃止 (ループ回数 0 で代用)
  v0.1.20 (2026-11-01) - 下降音ドラム: 三角波キックに加え矩形波 (1ch/2ch) のタムも検出。元の音程のまま MIDI ch 11/12/13
                         (1ch/2ch/3ch) に出力 (三角波は従来 ch 10 の GM 36/45)。--no-tri-drums → --no-drop-drums (旧名も可)
  v0.1.21 (2026-11-01) - 下降音ドラムの判定を「最初から下がり続ける音」に限定 (メロディのグリッサンドを除外)、
                         閾値を --drop-drums N (半音、既定 3、0 = 無効) で指定。GUI もチェックボックス → 数値
  v0.1.22 (2026-11-01) - GUI: 「クオンタイズしない」→「クオンタイズする」(既定オン)。「下降音ドラム（半音）」をドラム割当の下へ
  v0.1.23 (2026-11-02) - MIDI ch を NES のチャンネルに揃える: 下降音ドラムは ch 1/2/3 (トラックは別)、ノイズ ch 4、DPCM ch 5
                         (従来はドラム ch 10・下降音ドラム ch 11〜13)。同じ DPCM サンプルを複数のレートで鳴らす音色は
                         サンプルごとのトラックに分け、レートから音程を付ける
  v0.1.24 (2026-11-02) - 音程付き DPCM のノート番号を波形から推定した音程に (サンプルの 1 周期のビット数 × レート)。
                         周期が見つからないサンプルは一番低いレートを 48 (C3) とする
  v0.1.25 (2026-11-02) - FDS 対応: $6000〜$FFFF を RAM にしたメモリ配置 (ロード $6000〜も可)・FDS 音源のモデル
                         (周波数・音量エンベロープ・波形の周期数)・トラック Ch6 FDS (MIDI ch 6)。モジュレーションは出力しない
  v0.1.26 (2026-11-02) - 全拡張音源に対応 (expansion.py): VRC6・VRC7・MMC5・N163・Sunsoft 5B。MIDI ch は morokoshi の
                         チャンネルボタンの番号 (ch 6〜)。FDS も同じ仕組みへ移した
  v0.1.27 (2026-11-03) - GBS (ゲームボーイ) 対応: SM83 CPU・GB APU モデル・GBS プレイヤー (メモリ配置・起動は libgme に合わせる)。
                         Square 1/2・Wave・Noise を MIDI ch 1〜4 に。音量変更のための再トリガーは同じ音の続きとする。
                         GUI: .gbs / GBS 入りの zip と GBS の m3u (0 始まり)
  v0.1.28 (2026-11-03) - 3 連系のグリッド: 拍の頭になる行を選ぶ (シャッフルの長い音が拍の頭)、16 分の位置の発音は 16 分に置く。
                         短い曲 (8 オンセット〜) もシャッフル判定。グリッド単位がほぼ整数なら整数に
  v0.1.29 (2026-11-03) - ループ開始を小節頭に (曲頭に 1〜3 拍の小節)。グリッドに合う区間でも少しずつ遅くなる音の並びは
                         リタルダンドとして追う。途切れずに続く区間は小節線へ飛ばさない
  v0.1.30 (2026-11-03) - ループが 4/4 の小節で割り切れない曲は、ループ内の変拍子 (6/8・5/8・7/8・2/4 など) を
                         リズムの繰り返しとフィルインから求めて拍子を入れる (meter.py)。リタルダンド判定の基準をグリッドの行に
  v0.1.31 (2026-11-03) - 周期が小数のループを検出 (許容差 3 フレーム・周期の平均)。1/60 秒の丸めの揺れだけの区間はテンポを追わない。
                         変拍子に 9/8 を追加
  v0.1.32 (2026-11-03) - 変拍子をフレーズ単位で判定: 2 回続けて鳴るフレーズ (オクターブ違いも可) を探し、その中だけを小節に分ける
  v0.1.33 (2026-11-03) - ループのない曲は長い音・ベースの重さで小節頭を決める (前打ちの小節)。3 連系の 8 分音符を旋律の間隔で決める
  v0.1.34 (2026-11-03) - ループのない曲の前打ちは、30 秒以上の曲で、出だしが前打ちの形 (最初の長い音が候補の拍) のときだけ
  v0.1.35 (2026-11-03) - 1 小節ごとに音型が繰り返す区間は、その周期を 1 小節としてテンポ・区間の始まりと終わり・次の区間への切り替え位置を決める
  v0.1.36 (2026-11-03) - SPC (スーパーファミコン) 対応の第 1・2 段階: SPC700・DSP の模型・サンプルの音高推定・エンベロープ。
                         8 ボイス = MIDI ch 1〜8、サンプルが変わったら同じ ch の別トラック (CLI のみ。ドラム・テンポは今後)
  v0.1.37 (2026-11-03) - SPC 第 3 段階: 打楽器のサンプルを判定して GM ドラムのノートに (ボイスの ch の「ChN Drums」トラック。
                         spc_drums.py)。--drum-map に SPC のサンプル指定 (S67=38、0 = ドラムにしない)。
                         低い音域を探せないサンプルで音高推定が落ちる不具合を修正
"""

APP_VERSION = "v0.1.37"

import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nsf import open_player, nsf_base_name  # noqa: E402
from apu_state import APUState, note_name  # noqa: E402
from notes import extract_notes, tempo_onsets  # noqa: E402
from tempo import detect_tempo_map, TickMap  # noqa: E402
from midi import Track, write_smf  # noqa: E402
from spc_drums import split_spc_drums  # noqa: E402
from drums import (noise_hits, dmc_hits, split_drop_drums, detect_triangle_split, parse_drum_map,  # noqa: E402
                   summarize, GM_NAMES, DROP_DRUM_CHANNELS, DROP_DRUM_MIN)
from loop import detect_loop, REPEATS as LOOP_REPEATS  # noqa: E402
from expansion import channel_table  # noqa: E402
from meter import odd_bars, SNARES as SNARE_NOTES  # noqa: E402

PPQ = 480
MIDI_CH = {"P1": 0, "P2": 1, "TRI": 2}
# Expansion channels use MIDI ch 6- in the order of morokoshi's channel buttons (libgme voices):
# expansion.channel_table() adds them to MIDI_CH / TRACK_NAMES (v0.1.25-)
TONAL = ("P1", "P2", "TRI")
# GM programs (0-based) for the tonal tracks; None = no program change (default).
# Notation software (Sibelius) picks instruments from the program number (e.g. 38 Synth Bass is
# notated an octave up) and re-sorts tracks by instrument family, so no program is written unless
# requested with --programs.
MIDI_PROG = {"P1": None, "P2": None, "TRI": None}
CHUNK_SEC = 60.0      # emulate in chunks; stop when a loop or the end of the song is found
SILENCE_SEC = 4.0     # this much silence after the last note = song ended
CONFIRM_SEC = 20.0    # at least this much repeat after the first loop (short loops)

REG_NAMES = {
    0x4000: "P1_CTRL", 0x4001: "P1_SWEEP", 0x4002: "P1_LO", 0x4003: "P1_HI",
    0x4004: "P2_CTRL", 0x4005: "P2_SWEEP", 0x4006: "P2_LO", 0x4007: "P2_HI",
    0x4008: "TRI_LIN", 0x4009: "TRI_UNUSED", 0x400A: "TRI_LO", 0x400B: "TRI_HI",
    0x400C: "NOI_CTRL", 0x400D: "NOI_UNUSED", 0x400E: "NOI_PERIOD", 0x400F: "NOI_LEN",
    0x4010: "DMC_CTRL", 0x4011: "DMC_DAC", 0x4012: "DMC_ADDR", 0x4013: "DMC_LEN",
    0x4014: "OAM_DMA", 0x4015: "APU_STATUS", 0x4016: "JOY1", 0x4017: "FRAME_CNT",
    0x4080: "FDS_VOL_ENV", 0x4082: "FDS_FREQ_LO", 0x4083: "FDS_FREQ_HI", 0x4084: "FDS_MOD_ENV",
    0x4085: "FDS_MOD_CNT", 0x4086: "FDS_MOD_LO", 0x4087: "FDS_MOD_HI", 0x4088: "FDS_MOD_TABLE",
    0x4089: "FDS_WAVE_VOL", 0x408A: "FDS_ENV_SPEED",
}
REG_NAMES.update({a: f"FDS_WAVE_{a - 0x4040:02d}" for a in range(0x4040, 0x4080)})
REG_NAMES.update({0x9000: "VRC6_P1_CTRL", 0x9001: "VRC6_P1_LO", 0x9002: "VRC6_P1_HI", 0x9003: "VRC6_FREQ_CTRL",
                  0xA000: "VRC6_P2_CTRL", 0xA001: "VRC6_P2_LO", 0xA002: "VRC6_P2_HI",
                  0xB000: "VRC6_SAW_RATE", 0xB001: "VRC6_SAW_LO", 0xB002: "VRC6_SAW_HI",
                  0x9010: "VRC7_SELECT", 0x9030: "VRC7_DATA", 0x4800: "N163_DATA", 0xF800: "N163_ADDR",
                  0xC000: "5B_SELECT", 0xE000: "5B_DATA", 0x5015: "MMC5_STATUS"})
REG_NAMES.update({0x5000 + i: f"MMC5_P{i // 4 + 1}_{('CTRL', 'SWEEP', 'LO', 'HI')[i % 4]}" for i in range(8)})


def expansion_channels(expansion):
    """[(key, MIDI channel, track name)] of the NSF's expansion channels; registers them in
    MIDI_CH / TRACK_NAMES."""
    table = channel_table(expansion)
    for key, mch, name in table:
        MIDI_CH[key] = mch
        TRACK_NAMES[key] = name
    return table

CH_RANGES = (("P1", 0x4000), ("P2", 0x4004), ("TRI", 0x4008), ("NOI", 0x400C), ("DMC", 0x4010))


def ch_of(addr):
    for name, base in CH_RANGES:
        if base <= addr < base + 4:
            return name, addr - base
    return None, None


def build_frames(writes, n_frames, frame_cycles, cpu_hz, expansion=0, apu=None, cache=None):
    """Replay writes through the APU model; return per-frame snapshots.

    Each entry: dict(frame, time, state, written={ch: set(reg)}, status_writes)
    expansion: the NSF header's expansion byte; its channels get their own state / written keys,
    and a write that (re)triggers one of them is recorded as reg 3 (like $4003 on the 2A03)
    apu: the APU model to replay through (GBS: gb_apu.GBAPUState, whose trigger writes NRx4
    mark the channel's reg 3 the same way)
    cache: a dict kept between calls (SPC, v0.1.36): the frames built so far are reused and only
    the new ones are added (convert() analyses again after every emulation chunk)
    """
    if cache and cache.get("frames") is not None and len(cache["frames"]) <= n_frames:
        apu, frames, wi = cache["apu"], cache["frames"], cache["wi"]
    else:
        apu = apu or APUState(cpu_hz, expansion=expansion)
        frames = []
        wi = 0
    exp_keys = [k for c in apu.chips for k, _ in c.CHANNELS]
    nw = len(writes)
    for f in range(len(frames), n_frames):
        end = (f + 1) * frame_cycles
        if hasattr(apu, "keys"):              # SPC: the 8 voices (v0.1.36)
            written = {k: set() for k in apu.keys}
        else:
            written = {"P1": set(), "P2": set(), "TRI": set(), "NOI": set(), "DMC": set()}
        for k in exp_keys:
            written[k] = set()
        status = []
        kon = {}
        while wi < nw and writes[wi][0] < end:
            cyc, addr, val = writes[wi]
            for k in apu.write(cyc, addr, val) or ():
                written[k].add(3)
                kon.setdefault(k, cyc)
            ch, reg = ch_of(addr)
            if ch in written:
                written[ch].add(reg)
            elif addr == 0x4015:
                status.append(val)
            wi += 1
        apu.advance(end)
        frames.append({
            "frame": f,
            "time": f * frame_cycles / cpu_hz,
            "state": apu.snapshot(),
            "written": written,
            "status": status,
            "kon": kon,          # first (re)trigger of each channel in the frame, CPU cycle
        })
    if cache is not None:
        cache.update(apu=apu, frames=frames, wi=wi)
    return frames


def cents_of(note):
    if note is None:
        return 0
    return int(round((note - round(note)) * 100))


def write_writes_csv(path, writes, frame_cycles, cpu_hz):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame", "cycle_in_frame", "time_s", "addr", "value", "value_bin", "reg"])
        for cyc, addr, val in writes:
            fr = int(cyc // frame_cycles) if cyc >= 0 else -1
            cin = cyc - fr * frame_cycles if fr >= 0 else cyc
            w.writerow([fr, int(cin), f"{max(cyc, 0) / cpu_hz:.5f}", f"${addr:04X}", f"${val:02X}",
                        f"{val:08b}", REG_NAMES.get(addr, "?")])


def write_frames_csv(path, frames):
    cols = ["frame", "time_s"]
    for ch in ("P1", "P2"):
        cols += [f"{ch}_note", f"{ch}_cents", f"{ch}_period", f"{ch}_vol", f"{ch}_duty",
                 f"{ch}_envvol", f"{ch}_const", f"{ch}_len", f"{ch}_sweep", f"{ch}_written"]
    cols += ["TRI_note", "TRI_cents", "TRI_period", "TRI_on", "TRI_linear", "TRI_len", "TRI_written"]
    cols += ["NOI_period", "NOI_mode", "NOI_vol", "NOI_envvol", "NOI_const", "NOI_len", "NOI_written"]
    cols += ["DMC_playing", "DMC_addr", "DMC_len", "DMC_rate", "DMC_loop", "DMC_starts", "DMC_written",
             "STATUS_writes"]
    base = {"P1", "P2", "TRI", "NOI", "DMC"}
    exp = [k for k in frames[0]["state"] if k not in base] if frames else []
    for k in exp:
        cols += [f"{k}_note", f"{k}_cents", f"{k}_freq", f"{k}_period", f"{k}_vol", f"{k}_timbre", f"{k}_trig"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for fr in frames:
            s = fr["state"]
            wr = fr["written"]
            row = [fr["frame"], f"{fr['time']:.4f}"]
            for ch in ("P1", "P2"):
                c = s[ch]
                row += [note_name(c["note"]), cents_of(c["note"]), c["period"], c["vol"], c["duty"],
                        c["reg_vol"], int(c["const"]), c["length"], int(c["sweep"]),
                        "".join(str(r) for r in sorted(wr[ch]))]
            t = s["TRI"]
            row += [note_name(t["note"]), cents_of(t["note"]), t["period"], int(t["vol"] > 0),
                    t["linear"], t["length"], "".join(str(r) for r in sorted(wr["TRI"]))]
            n = s["NOI"]
            row += [f"{n['period_idx']:X}", n["mode"], n["vol"], n["reg_vol"], int(n["const"]),
                    n["length"], "".join(str(r) for r in sorted(wr["NOI"]))]
            d = s["DMC"]
            row += [int(d["playing"]), f"${d['addr']:04X}", d["len"], d["rate"], int(d["loop"]),
                    d["starts"], "".join(str(r) for r in sorted(wr["DMC"])),
                    " ".join(f"${v:02X}" for v in fr["status"])]
            for k in exp:
                c = s[k]
                row += [note_name(c["note"]), cents_of(c["note"]), f"{c['freq']:.1f}", c["period"], c["vol"],
                        c["duty"], int(3 in wr[k])]
            w.writerow(row)


def _tone_cell(c, written, prev):
    """Tracker cell for a pulse channel.

    Markers: '*' = $4003/$4007 written (phase reset + envelope restart),
             'd' = duty changed, 'p' = period changed without hi-reg write,
             '~' = pitch more than 20 cents off the tempered note.
    """
    if c["vol"] == 0:
        if 3 in written:
            # triggered but silent this frame (software envelope starting at 0)
            return f"{note_name(c['note'])} v0 D{c['duty']} *  "
        return f"{'...':<14}"
    mark = ""
    mark += "*" if 3 in written else " "
    mark += "d" if prev is not None and prev["duty"] != c["duty"] else " "
    mark += "p" if prev is not None and prev["period"] != c["period"] and 3 not in written else " "
    off = "~" if abs(cents_of(c["note"])) > 20 else " "
    return f"{note_name(c['note'])}{off}v{c['vol']:X} D{c['duty']} {mark}"


def write_tracker_txt(path, frames, header, track, frame_rate):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# nsf2mid {APP_VERSION} tracker view\n")
        f.write(f"# {header.title} / {header.artist} / track {track} / {frame_rate:.3f} frames/s\n")
        f.write("# Pulse cell: NOTE[~] vVOL Dduty [*][d][p]\n")
        f.write("#   * = hi-period reg written (phase reset/env restart), d = duty change,\n")
        f.write("#   p = period change w/o hi-reg write, ~ = >20 cents off pitch\n")
        f.write("# TRI cell: NOTE[~] [*]   NOI cell: Pperiod Mmode vVOL [*]   DMC: sample addr when (re)started\n\n")
        f.write(f"{'frame':>6} {'time':>8} | {'P1':<14} | {'P2':<14} | {'TRI':<8} | {'NOI':<10} | DMC\n")
        prev = None
        for fr in frames:
            s = fr["state"]
            wr = fr["written"]
            p1 = _tone_cell(s["P1"], wr["P1"], prev and prev["P1"])
            p2 = _tone_cell(s["P2"], wr["P2"], prev and prev["P2"])
            t = s["TRI"]
            if t["vol"]:
                off = "~" if abs(cents_of(t["note"])) > 20 else " "
                tri = f"{note_name(t['note'])}{off} {'*' if 3 in wr['TRI'] else ' '}  "
            else:
                tri = f"{'...':<8}"
            n = s["NOI"]
            if n["vol"]:
                noi = f"P{n['period_idx']:X} M{n['mode']} v{n['vol']:X} {'*' if 3 in wr['NOI'] else ' '}"
            else:
                noi = f"{'...':<10}"
            d = s["DMC"]
            dmc = ""
            if prev is not None and d["starts"] != prev["DMC"]["starts"]:
                dmc = f"${d['addr']:04X}"
            elif d["playing"]:
                dmc = " |"
            fds = ""
            for k in s:      # expansion cells: NOTE[~] vVOL Ttimbre [*]
                if k in ("P1", "P2", "TRI", "NOI", "DMC"):
                    continue
                c = s[k]
                if c["vol"]:
                    off = "~" if abs(cents_of(c["note"])) > 20 else " "
                    fds += f" | {note_name(c['note'])}{off}v{c['vol']:X} T{c['duty']:<2}{'*' if 3 in wr[k] else ' '}"
                else:
                    fds += f" | {'...':<14}"
            f.write(f"{fr['frame']:>6} {fr['time']:>8.3f} | {p1} | {p2} | {tri} | {noi} | {dmc:<6}{fds}\n")
            prev = s


def vol_to_velocity(v):
    return max(1, min(127, int(round(v * 127 / 15))))


# Track names avoid real instrument names: notation software (Sibelius) picks instruments from the
# track name, and "Triangle" became the percussion triangle (moved into the percussion section).
TRACK_NAMES = {"P1": "Ch1 Pulse", "P2": "Ch2 Pulse", "TRI": "Ch3 Wave"}
DRUM_TRACKS = (("NOI", "Ch4 Noise drums"), ("DMC", "Ch5 DPCM drums"), ("P1", "Ch1 Pulse drums"),
               ("P2", "Ch2 Pulse drums"), ("TRI", "Ch3 Wave drums"))
# v0.1.23: every track uses the MIDI channel of its NES channel (drums on their own tracks).
# Noise / DPCM keep GM drum note numbers; pitch-drop drums and pitched DPCM samples their pitch.
# (v0.1.22 and before: noise / DPCM on ch 10, pitch-drop drums on ch 11-13)
DRUM_CH = {"P1": 0, "P2": 1, "TRI": 2, "NOI": 3, "DMC": 4}


def build_midi(notes, drums, tmap, title, track_no, end_frame, loop, transpose, programs):
    t0 = Track(f"{title} #{track_no}" if title else f"track {track_no}")
    for tick, bpm in tmap.tempo_events():
        t0.tempo(tick, bpm)
    for tick, (num, den) in tmap.meter_events():
        t0.time_signature(tick, num, den.bit_length() - 1, 36 if (num % 3 == 0 and den == 8) else 24)
    if loop:
        t0.meta(tmap(loop["start"]), 0x06, b"loopStart")
        t0.meta(tmap(loop["start"] + loop["period"]), 0x06, b"loopEnd")
    tracks = [t0]
    min_len = int(tmap.min_ticks) if tmap.quantize else max(1, int(tmap.min_ticks / 4))
    end_tick = tmap(end_frame)

    def span(start, stop):
        st = tmap(start)
        en = min(tmap(stop), end_tick)
        if en <= st:
            en = st + min_len
        return st, en

    for ch in notes:
        groups = [(TRACK_NAMES[ch], notes[ch])]
        if ch.startswith("V"):
            # SPC (v0.1.36): one track per sample (instrument) on the voice's MIDI channel
            srcns = sorted({note_sample(n) for n in notes[ch] if n.start < end_frame})
            groups = [(f"{TRACK_NAMES[ch]} S{s}", [n for n in notes[ch] if note_sample(n) == s])
                      for s in srcns]
        for gi, (name, lst) in enumerate(groups):
            tr = Track(name)
            mch = MIDI_CH[ch]
            if programs.get(ch) is not None:
                tr.program(0, mch, programs[ch])
            if loop and gi == 0 and ch in ("P1", "V1"):
                tr.control(tmap(loop["start"]), mch, 111, 0)   # RPG Maker style loop marker
            for n in lst:
                if n.start >= end_frame:
                    continue
                st, en = span(n.start, n.gate_end)
                vel = 100 if ch == "TRI" else vol_to_velocity(n.peak)
                tr.note(st, en, mch, max(0, min(127, n.pitch + transpose.get(ch, 0))), vel)
            tracks.append(tr)
    for src, name, hits in drum_track_groups(drums, end_frame):
        tr = Track(name)
        for d in hits:
            st, en = span(d.start, d.end)
            num = d.gm if d.pitch is None else d.pitch + transpose.get(src, 0)
            tr.note(st, en, DRUM_CH[src], max(0, min(127, num)), d.vel)
        tracks.append(tr)
    return tracks


def odd_loop_meters(tmap, loop, notes, drums, end_frame, loops):
    """v0.1.30: a loop that is not a whole number of 4/4 bars gets its odd bars (meter.odd_bars)."""
    part = tmap.parts[0]
    if tmap.downbeat_tick is None or part.meter != (4, 4):
        return
    start = tmap.downbeat_tick
    span = tmap(loop["start"] + loop["period"]) - tmap(loop["start"])
    if len(tmap.parts) > 1 and tmap.parts[1].origin_tick < start + span * loops:
        return
    events = [(tmap(n.start), ch, n.pitch, False) for ch, lst in notes.items() for n in lst if n.start < end_frame]
    events += [(tmap(d.start), "DRUM_" + d.src, str(d.gm if d.pitch is None else d.pitch),
                d.pitch is None and d.gm in SNARE_NOTES) for d in drums if d.start < end_frame]
    bars = odd_bars(events, start, start + span)
    if not bars:
        return
    rep = [(t + k * span, m) for k in range(loops) for t, m in bars]
    tmap.set_odd_meters(rep, start + span * loops, part.meter)
    print("  Odd bars in the loop: " + ", ".join(f"{m[0]}/{m[1]} at beat {t / PPQ:g}" for t, m in bars))


def drum_track_groups(drums, end_frame):
    """[(src, track name, hits)] of the non-empty drum tracks. A DPCM sample played at several
    rates (pitched sample) gets its own track "Ch5 DPCM $ADDR" after the DPCM drums.
    SPC (v0.1.37): one track "ChN Drums" per voice."""
    out = []
    voices = sorted({d.src for d in drums if d.src.startswith("V")}, key=lambda k: int(k[1:]))
    for src in voices:
        out.append((src, f"{TRACK_NAMES[src]} Drums", [d for d in drums if d.src == src and d.start < end_frame]))
    for src, name in DRUM_TRACKS:
        hits = [d for d in drums if d.src == src and d.start < end_frame]
        if src != "DMC":
            out.append((src, name, hits))
            continue
        out.append((src, name, [d for d in hits if d.pitch is None]))
        samples = sorted({d.kind[1:3] for d in hits if d.pitch is not None})
        addrs = [a for a, _ in samples]
        for addr, length in samples:
            label = f"Ch5 DPCM ${addr:04X}" + (f" len {length}" if addrs.count(addr) > 1 else "")
            out.append((src, label, [d for d in hits if d.pitch is not None and d.kind[1:3] == (addr, length)]))
    return [g for g in out if g[2]]


def write_notes_csv(path, notes, drums, tmap, transpose):
    rows = []
    for ch, lst in notes.items():
        for n in lst:
            rows.append((n.start, ch, n))
    for d in drums:
        rows.append((d.start, "DRUM_" + d.src, d))
    rows.sort(key=lambda r: (r[0], r[1]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ch", "start_frame", "gate_end_frame", "end_frame", "gate_frames", "tail_frames",
                    "note", "midi", "peak_vol", "cue", "start_tick", "end_tick", "vols"])
        for _, ch, n in rows:
            if ch.startswith("DRUM_"):
                if n.pitch is not None:  # pitch-drop drum / pitched DPCM sample
                    p = n.pitch + transpose.get(n.src, 0)
                    name, num = note_name(p), p
                else:
                    name, num = GM_NAMES.get(n.gm, str(n.gm)), n.gm
                w.writerow([ch, n.start, n.end, n.end, n.end - n.start, 0,
                            name, num, n.vel, n.info,
                            tmap(n.start) if tmap else "", tmap(n.end) if tmap else "", ""])
                continue
            out_pitch = n.pitch + transpose.get(ch, 0)
            w.writerow([ch, n.start, n.gate_end, n.end, n.gate_end - n.start, n.end - n.gate_end,
                        note_name(out_pitch), out_pitch, n.peak, n.cue,
                        tmap(n.start) if tmap else "", tmap(n.gate_end) if tmap else "",
                        " ".join(f"{v:X}" for v in n.vols[:48])])


def analyze(player, n_frames, args, drum_map):
    """Replay the register log and extract notes / drums / loop.

    detect: the notes seen by tempo / meter / loop detection. They use the fixed triangle-kick rule
    (detect_triangle_split) and keep the pulse notes, so detection does not depend on --drop-drums."""
    expansion = player.header.expansion
    cache = getattr(player, "frames_cache", None)
    frames = build_frames(player.writes, n_frames, player.frame_cycles, player.cpu_hz, expansion,
                          None if cache and cache.get("frames") else player.make_apu(), cache)
    if getattr(player, "is_spc", False):
        return analyze_spc(frames, args, player.frame_cycles, cache["apu"], drum_map)
    notes, stats = extract_notes(frames, TONAL + tuple(k for k, _, _ in expansion_channels(expansion)),
                                 keep_tail=args.keep_tail)
    base = noise_hits(frames, drum_map) + dmc_hits(frames, player.dmc_samples, player.cpu_hz, drum_map)
    detect = dict(notes)
    detect["TRI"], detect_tri = detect_triangle_split(notes["TRI"])
    drop_drums = []
    for ch in DROP_DRUM_CHANNELS:
        notes[ch], hits = split_drop_drums(notes[ch], ch, 0 if args.no_drop_drums else args.drop_drums)
        drop_drums += hits
    drums = sorted(base + drop_drums, key=lambda d: d.start)
    events = {ch: [(n.start, n.pitch) for n in lst] for ch, lst in detect.items()}
    events["DRUM"] = [(d.start, (d.src, d.kind)) for d in sorted(base + detect_tri, key=lambda d: d.start)]
    loop = None if args.no_loop else detect_loop(events)
    return frames, notes, stats, drums, events, loop, detect


def analyze_spc(frames, args, frame_cycles, dsp, drum_map):
    """SPC (v0.1.36): the 8 voices are the channels (MIDI ch 1-8). v0.1.37: percussion samples
    become GM drum notes on the track "ChN Drums" of their voice (spc_drums). Tempo / loop
    detection see every note (drums included), as before."""
    keys = tuple(f"V{i + 1}" for i in range(8))
    for i, k in enumerate(keys):
        MIDI_CH[k] = i
        DRUM_CH[k] = i
        TRACK_NAMES[k] = f"Ch{i + 1}"
    notes, stats = extract_notes(frames, keys, keep_tail=args.keep_tail)
    notes = {k: v for k, v in notes.items() if v}
    # the exact key-on time inside the frame (fractional frames): the driver runs on its own
    # timer (FF4: 222 Hz), so whole 1/60 s frames put notes up to a frame off the beat grid
    for k, lst in notes.items():
        for n in lst:
            f = frames[n.start] if n.start < len(frames) else None
            if f and k in f["kon"]:
                n.start = f["kon"][k] / frame_cycles
    detect = dict(notes)
    events = {ch: [(n.start, n.pitch) for n in lst] for ch, lst in detect.items()}
    loop = None if args.no_loop else detect_loop(events)
    tonal, drums = split_spc_drums(notes, frames, dsp, drum_map)
    tonal = {k: tonal.get(k, []) for k in notes}
    return frames, tonal, stats, drums, events, loop, detect


def note_sample(n):
    """Sample number (SRCN) a SPC note starts with (stored as its duty)."""
    return n.duties[0] if n.duties else -1


class Cancelled(Exception):
    """Raised when the GUI asks to stop a conversion."""


def build_parser():
    ap = argparse.ArgumentParser(description=f"nsf2mid {APP_VERSION} - NSF / GBS to MIDI converter")
    ap.add_argument("nsf", help="input .nsf / .gbs file, or a zip containing one (zophar.net style)")
    ap.add_argument("-t", "--track", type=int, default=0, help="track number (1-based, default: start song)")
    ap.add_argument("-s", "--seconds", type=float, default=600.0,
                    help="maximum length to emulate in seconds (stops early when a loop or the end is found)")
    ap.add_argument("-o", "--outdir", default=None, help="output folder (default: <nsf folder>/nsf2mid_out)")
    ap.add_argument("--mid-out", default=None,
                    help="write only the .mid to this path (no notes.csv / dumps; overrides -o)")
    ap.add_argument("--info", action="store_true", help="print header info only")
    ap.add_argument("--dump", action="store_true", help="also write register/frame/tracker dumps (Phase 1)")
    ap.add_argument("--keep-tail", action="store_true", help="keep reverb tails in note length")
    ap.add_argument("--no-quantize", action="store_true", help="do not snap notes to the detected grid")
    ap.add_argument("--unit", type=float, default=None, help="override grid unit (frames per row)")
    ap.add_argument("--rows-per-beat", type=int, default=None, help="override rows per beat (e.g. 4 = 16th rows)")
    ap.add_argument("--tempo", choices=("auto", "half", "double"), default="auto",
                    help="auto = detected tempo (default), half / double = halve / double the detected tempo")
    ap.add_argument("--loops", type=int, default=1,
                    help="how many times to write the loop body (default 1, 0 = no loop detection)")
    ap.add_argument("--no-loop", action="store_true", help="disable loop detection (emulate --seconds fully)")
    ap.add_argument("--time-sig", default="",
                    help='time signature per tempo segment, e.g. "6/8,4/4" ("-" = auto)')
    ap.add_argument("--tri-octave", type=int, default=0,
                    help="octave shift for triangle notes in the MIDI (default 0 = APU pitch)")
    ap.add_argument("--programs", default="",
                    help='GM programs (0-based) for P1,P2,TRI, e.g. "80,80,38"; "-" = no program change '
                         '(default: none)')
    ap.add_argument("--triplets", choices=("auto", "on", "off"), default="auto",
                    help="prefer triplet feel: auto = detect (default), on = always, off = never (binary)")
    ap.add_argument("--drop-drums", type=float, default=DROP_DRUM_MIN, metavar="SEMITONES",
                    help="pitch-drop drums (triangle kicks, pulse toms): short notes gliding down by at least "
                         f"this many semitones go to their own tracks (default {DROP_DRUM_MIN}, 0 = off)")
    ap.add_argument("--no-drop-drums", "--no-tri-drums", dest="no_drop_drums", action="store_true",
                    help="same as --drop-drums 0")
    ap.add_argument("--drum-map", default="",
                    help='override drum notes, e.g. "3:0=42,12:0=36,DMC:E000:129:15=38,S67=38" '
                         "(noise: periodIdx:mode, DPCM: DMC:addrHex:len:rate, SPC: S + sample number, "
                         "=0 keeps an SPC sample as notes)")
    return ap


def convert(args, should_stop=None):
    """Convert one track as described by the parsed arguments.

    Progress is printed to stdout. should_stop() is polled between emulation chunks;
    returning True raises Cancelled. Returns (exit code, list of output files).
    """
    if args.loops <= 0:  # --loops 0 = no loop detection (same as --no-loop)
        args.no_loop = True
    drum_map = parse_drum_map(args.drum_map)
    transpose = {"TRI": 12 * args.tri_octave}
    programs = dict(MIDI_PROG)
    if args.programs:
        for ch, v in zip(("P1", "P2", "TRI"), args.programs.split(",")):
            v = v.strip()
            programs[ch] = None if v == "-" else int(v)

    player = open_player(args.nsf)
    h = player.header
    print(f"nsf2mid {APP_VERSION}")
    print(h.summary())
    if args.info:
        return 0, []

    track = args.track or h.start_song
    if not 1 <= track <= h.total_songs:
        print(f"Error: track {track} out of range 1..{h.total_songs}")
        return 1, []

    t0 = time.time()
    player.start(track)       # GBS: the PLAY rate is known after INIT
    frame_rate = player.cpu_hz / player.frame_cycles
    max_frames = int(args.seconds * frame_rate)
    chunk = int(CHUNK_SEC * frame_rate)
    print(f"\nEmulating track {track} (max {args.seconds:.0f} s @ {frame_rate:.3f} Hz)")
    n_frames = 0
    end_reason = "max length"
    prev_loop = None
    while n_frames < max_frames:
        if should_stop and should_stop():
            raise Cancelled()
        n_frames = player.advance(min(chunk, max_frames - n_frames))
        if args.no_loop or player.aborted:
            if player.aborted:
                end_reason = "emulation aborted"
            if player.aborted:
                break
            continue
        frames, notes, stats, drums, events, loop, detect = analyze(player, n_frames, args, drum_map)
        # accept a loop only when it is stable over two chunks and heard LOOP_REPEATS times in a row
        if (loop and prev_loop and abs(loop["start"] - prev_loop["start"]) <= 2
                and abs(loop["period"] - prev_loop["period"]) <= 2
                and n_frames - loop["start"] >= max(LOOP_REPEATS * loop["period"],
                                                    loop["period"] + CONFIRM_SEC * frame_rate)):
            end_reason = "loop found"
            break
        prev_loop = loop
        last_end = max([n.end for lst in notes.values() for n in lst] + [d.end for d in drums], default=0)
        if last_end and n_frames - last_end >= SILENCE_SEC * frame_rate:
            end_reason = "song ended"
            break
    player.finish_warnings()
    frames, notes, stats, drums, events, loop, detect = analyze(player, n_frames, args, drum_map)
    print(f"  {n_frames} frames ({n_frames / frame_rate:.1f} s) in {time.time() - t0:.2f} s, "
          f"{len(player.writes)} register writes; stopped: {end_reason}")
    for w in player.warnings:
        print(f"  Warning: {w}")

    # ---- song range
    last_end = max([n.end for lst in notes.values() for n in lst] + [d.end for d in drums], default=n_frames)
    if loop and end_reason == "loop found":
        end_frame = loop["start"] + loop["period"] * max(1, args.loops)
        print(f"\nLoop: starts at {loop['start'] / frame_rate:.2f} s, length {loop['period'] / frame_rate:.2f} s "
              f"({loop['period']} frames); writing intro + {max(1, args.loops)} loop(s)")
    else:
        loop = None
        end_frame = last_end if end_reason == "song ended" else n_frames
        print(f"\nLoop: none ({end_reason}); song length {end_frame / frame_rate:.2f} s")

    outdir = args.outdir or os.path.join(os.path.dirname(os.path.abspath(args.nsf)), "nsf2mid_out")
    if not getattr(args, "mid_out", None):
        os.makedirs(outdir, exist_ok=True)
    base = nsf_base_name(args.nsf)
    if len(base) > 40:
        base = base[:40].rstrip()
    stem = os.path.join(outdir, f"{base}_t{track:02d}")
    outputs = []
    mid_out = getattr(args, "mid_out", None)

    if args.dump and not mid_out:
        write_writes_csv(stem + "_writes.csv", player.writes, player.frame_cycles, player.cpu_hz)
        write_frames_csv(stem + "_frames.csv", frames)
        write_tracker_txt(stem + "_tracker.txt", frames, h, track, frame_rate)
        outputs += [stem + "_writes.csv", stem + "_frames.csv", stem + "_tracker.txt"]

    print("\nNotes:")
    for ch in notes:
        lst = [n for n in notes[ch] if n.start < end_frame]
        tails = sum(1 for n in lst if n.has_tail)
        st = stats[ch]
        cue = "on" if st["trigger_cue"] else "IGNORED (driver re-triggers almost every frame)"
        print(f"  {ch:3}: {len(lst):4} notes, {tails:4} reverb tails cut, "
              f"trigger ratio {st['trigger_ratio']:.2f} -> trigger cue {cue}")
    in_range = [d for d in drums if d.start < end_frame]
    if in_range:
        print("Drums (source, kind, hits -> GM note):")
        for src, kind, cnt, gm, info, pitch in summarize(in_range):
            if src in DROP_DRUM_CHANNELS:
                print(f"  {src:3} {'pitch-drop drum':28} {cnt:4} -> MIDI ch {DRUM_CH[src] + 1}, original pitch "
                      f"(e.g. {info})")
            elif pitch is not None:
                print(f"  {src:3} {str(kind):28} {cnt:4} -> MIDI ch {DRUM_CH[src] + 1}, pitched sample "
                      f"{note_name(pitch)} ({info})")
            else:
                print(f"  {src:3} {str(kind):28} {cnt:4} -> {gm:3} {GM_NAMES.get(gm, ''):16} "
                      f"MIDI ch {DRUM_CH[src] + 1} ({info})")
    full = detect

    onsets = [o for o in tempo_onsets(full, frames) if o < end_frame]
    onsets += [d.start for d in in_range if d.src == "DMC"]
    chan_notes = {ch: {n.start: n.pitch for n in full[ch] if n.start < end_frame and not n.cue.startswith("pitch")}
                  for ch in notes}
    tempo = detect_tempo_map(onsets, frame_rate, args.rows_per_beat, args.unit, chan_notes, args.triplets,
                             args.tempo)
    tmap = None
    if tempo is None:
        print("\nTempo: not enough notes to detect")
    else:
        g = tempo["global"]
        print(f"\nTempo: grid unit {g['unit']:g} frames (fit {g['score'] * 100:.1f}%), "
              f"{'shuffle (long-short on a straight grid)' if tempo.get('shuffle') else 'triplet feel (3 notes per beat)' if tempo.get('triplet') else 'ternary (triplet/shuffle)' if tempo['ternary'] else 'binary'}")
        if tempo.get("tempo_kept"):
            print(f"  Tempo double: {tempo['tempo_kept']} segment(s) kept as detected "
                  "(odd rows per beat cannot be halved)")
        meters = [tuple(int(x) for x in m.split("/")) if m.strip() not in ("", "-") else None
                  for m in args.time_sig.split(",")] if args.time_sig else None
        tmap = TickMap(tempo, PPQ, not args.no_quantize, frame_rate, onsets,
                       {ch: [n for n in lst if n.start < end_frame] for ch, lst in full.items()}, meters,
                       downbeat=loop["start"] if loop else None)
        for sg in tempo["segments"]:
            print(f"  from {sg.start / frame_rate:7.2f} s: {sg.bpm:7.2f} BPM  "
                  f"(unit {sg.unit:.4g} frames x {sg.rows} rows/beat, fit {sg.score * 100:.1f}%)  "
                  f"{sg.meter[0]}/{sg.meter[1]}" + ("  [tempo tracked]" if sg.tracked else ""))
            if sg.score < 0.8 and not sg.tracked:
                print("    Warning: poor grid fit (rubato or unsupported rhythm?)")
        if loop:
            odd_loop_meters(tmap, loop, notes, drums, end_frame, max(1, args.loops))
        mid_path = mid_out or stem + ".mid"
        write_smf(mid_path, build_midi(notes, drums, tmap, h.title, track, end_frame, loop, transpose, programs), PPQ)
        outputs.insert(0, mid_path)

    if not mid_out:
        write_notes_csv(stem + "_notes.csv", notes, drums, tmap, transpose)
        outputs.append(stem + "_notes.csv")
    print("\nOutput:")
    for o in outputs:
        print(f"  {o}")
    return 0, outputs


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        # no arguments: start the GUI (Phase 4)
        from nsf2mid_gui import main as gui_main
        return gui_main()
    return convert(build_parser().parse_args(argv))[0]


if __name__ == "__main__":
    sys.exit(main())
