# -*- coding: utf-8 -*-
"""Morokoshi Time v1.4.17 (PyQt6) by ikeさん"""
APP_VERSION = "v1.5.3"
import sys, os, time, hashlib, json, tempfile, subprocess, copy
import threading, base64, io
from fractions import Fraction

import numpy as np
import soundfile as sf
import sounddevice as sd
# scipy / librosa / Pillow は使用しない（軽量化のためnumpy実装に置き換え済み）

# 高速タイムストレッチ/ピッチシフト（Signalsmith Stretch）。無ければlibrosaにフォールバック
try:
    import python_stretch as _ps
    _HAS_PS = True
except Exception:
    _HAS_PS = False

def _fast_stretch(mono, sr, spd, semi):
    """python-stretchで高速変換。
    mono: 1次元float32, spd: 速度倍率(1.0=等速), semi: 半音"""
    if _HAS_PS:
        try:
            audio = mono[np.newaxis, :].astype(np.float32)  # (1, N)
            st = _ps.Signalsmith.Stretch()
            st.preset(1, sr)
            if semi != 0:
                st.setTransposeSemitones(float(semi))
            st.timeFactor = spd if spd != 0 else 1.0
            out = st.process(audio)
            return np.ascontiguousarray(out[0]).astype(np.float32)
        except Exception:
            pass
    # python-stretchが使えない場合は元の音声をそのまま返す
    return mono.astype(np.float32)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QLineEdit, QFrame, QSizePolicy,
    QFileDialog, QStackedWidget
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize, pyqtSlot, QPointF
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QPixmap, QImage, QFont,
    QPainterPath, QIcon, QCursor
)

# ── テーマ（フラットグレー）
BG      = "#2B2B2B"   # 背景
BG2     = "#3C3F41"   # パネル背景
BG3     = "#4C5052"   # 入力欄背景
FG      = "#BBBBBB"   # 通常テキスト
FG2     = "#888888"   # 薄テキスト
ACC     = "#4A90D9"   # アクセント（波形再生済み）
ACC2    = "#1A3A5A"   # 波形未再生
SEL     = "#214283"   # 選択
BORDER  = "#555555"   # ボーダー
RED_HL  = "#CC3333"   # ハイライト赤

MARKER_A = 10  # A-point key in engine.markers (AB repeat / Ear mode)
MARKER_B = 11  # B-point key in engine.markers (AB repeat / Ear mode)


# ── キャッシュ
CACHE = os.path.join(os.path.expanduser("~"), ".morokoshi_cache")
os.makedirs(CACHE, exist_ok=True)
CACHE_DAYS = 30

# スペクトラムアナライザー: 1/3オクターブ系の固定15バンド中心周波数(Hz)
SPECTRUM_BANDS_HZ = [25,40,63,100,160,250,400,630,1000,1600,2500,4000,6300,10000,16000]
# 主要周波数として下にラベルを出すバンドのインデックス（全バンド表示）
SPECTRUM_LABEL_IDX = list(range(len(SPECTRUM_BANDS_HZ)))

def _spectrum_band_edges(centers):
    """隣接バンド中心の対数中点を境界として、各バンドの[低,高)を返す(len(centers)+1個)"""
    mids=[(centers[i]*centers[i+1])**0.5 for i in range(len(centers)-1)]
    lo = centers[0]**2/mids[0]
    hi = centers[-1]**2/mids[-1]
    return [lo]+mids+[hi]

SPECTRUM_BAND_EDGES = _spectrum_band_edges(SPECTRUM_BANDS_HZ)

def _spectrum_bar_geometry(w, n):
    """スペアナのバー幅・間隔・各バー中心x座標を計算(SpectrumWidgetとラベル行で共有)"""
    gap=max(1, round(w*0.012))
    bw=max(1.0, (w-gap*(n+1))/n)
    centers=[gap+i*(bw+gap)+bw/2.0 for i in range(n)]
    return gap, bw, centers

# フィルター(HPF/LPF): 15バンド(SPECTRUM_BANDS_HZと共通)の境界をカットオフ周波数として使う。
# 各段は4次バターワース(=-24dB/Oct)。両端を選べばバンドパス、片端なら片方のみ。
FILTER_BANDS_HZ = SPECTRUM_BANDS_HZ
FILTER_DB_FLOOR = -36.0  # カーブ描画時の下限(これより下はクリップ表示)

def _build_filter_sos(lo_idx, hi_idx, sr):
    """選択中の帯域[lo_idx, hi_idx]からHPF/LPFのsosを組み立てる。
    各段は4次バターワース(=-24dB/Oct)。
    両端とも全域(0〜最後)ならフィルター無し(None)。
    戻り値: sos配列、またはフィルター無しの場合はNone"""
    n=len(FILTER_BANDS_HZ)
    lo_idx=max(0,min(n-1,int(lo_idx))); hi_idx=max(0,min(n-1,int(hi_idx)))
    if lo_idx>hi_idx: lo_idx,hi_idx=hi_idx,lo_idx
    nyq=sr*0.5
    sections=[]
    if lo_idx>0:
        fc=min(FILTER_BANDS_HZ[lo_idx], nyq*0.99)
        sections.append(_butter_sos(fc, "highpass", sr))
    if hi_idx<n-1:
        fc=min(FILTER_BANDS_HZ[hi_idx], nyq*0.99)
        sections.append(_butter_sos(fc, "lowpass", sr))
    if not sections:
        return None
    return np.vstack(sections)

# ── scipy.signal 代替実装（numpy のみ）──────────────────────────────────────
# butter / sosfilt / sosfreqz を numpy で再現
# 4次バターワース専用（N=4固定で十分なため）

def _butter_sos(fc, btype, fs):
    """4次バターワースフィルターのSOSを設計する。
    fc: カットオフ周波数(Hz), btype: 'lowpass'|'highpass', fs: サンプルレート(Hz)
    戻り値: sos (shape: (2, 6))  各行=[b0,b1,b2,1,a1,a2]"""
    N = 4
    # アナログプロトタイプ極（4次バターワース）
    # p_k = exp(j*π*(2k+N-1)/(2N)), k=0..N-1  → 左半平面
    k = np.arange(N)
    poles_a = np.exp(1j * np.pi * (2*k + N - 1) / (2*N))
    # 共役ペアを2次セクションへ（k=0&3, k=1&2）
    pairs = [(poles_a[0], poles_a[3]), (poles_a[1], poles_a[2])]

    # プリワープ
    wd = 2.0 * np.pi * fc / fs          # デジタル角周波数
    wa = 2.0 * fs * np.tan(wd / 2.0)   # アナログ等価周波数

    sos = np.zeros((2, 6))
    for i, (p1, p2) in enumerate(pairs):
        # アナログLP原型の2次セクション: H(s) = wa^2 / (s^2 - (p1+p2)*wa*s + p1*p2*wa^2)
        a1_a = -(p1 + p2).real          # -2*cos(θ) (虚部は打ち消し合う)
        a0_a = (p1 * p2).real           # ≒ 1.0

        if btype == 'lowpass':
            # バイリニア変換 LP: s → wa*(z-1)/(z+1)*... の結果
            b0_a, b1_a, b2_a = wa**2, 0.0, 0.0
            A0 = wa**2 + a1_a * wa + a0_a * wa**2 / wa**2
            # 直接 bilinear を展開
            k2 = wa / (2.0 * fs)
            # H_d(z): bilinear s = 2fs*(z-1)/(z+1) 代入
            # 分子: wa^2 → 分母展開
            d0 = (2*fs)**2 + a1_a * wa * (2*fs) + wa**2
            d1 = 2*(wa**2 - (2*fs)**2)
            d2 = (2*fs)**2 - a1_a * wa * (2*fs) + wa**2
            n0 = wa**2; n1 = 2*wa**2; n2 = wa**2
        else:  # highpass: LP → HP変換: s → wa/s してからbilinear
            d0 = (2*fs)**2 + a1_a * wa * (2*fs) + wa**2
            d1 = 2*(wa**2 - (2*fs)**2)
            d2 = (2*fs)**2 - a1_a * wa * (2*fs) + wa**2
            n0 = (2*fs)**2; n1 = -2*(2*fs)**2; n2 = (2*fs)**2

        # 正規化 (a0=1)
        sos[i] = [n0/d0, n1/d0, n2/d0, 1.0, d1/d0, d2/d0]
    return sos


def _sosfilt(sos, x, axis=0, zi=None):
    """SOSフィルターを適用する（直接II転置形）。
    sos: (n_sec, 6), x: ndarray, axis: フィルター軸
    zi: (n_sec, 2, ...) 初期状態。戻り値: (y, zf)"""
    x = np.asarray(x, dtype=np.float64)
    n_sec = sos.shape[0]
    # 軸を先頭に移動
    x = np.moveaxis(x, axis, 0)
    shape_rest = x.shape[1:]
    n = x.shape[0]

    if zi is None:
        zi = np.zeros((n_sec, 2) + shape_rest, dtype=np.float64)
    else:
        zi = np.array(zi, dtype=np.float64)

    y = x.copy()
    zf = np.zeros_like(zi)

    for s in range(n_sec):
        b0, b1, b2, _, a1, a2 = sos[s]
        z0 = zi[s, 0]
        z1 = zi[s, 1]
        out = np.empty_like(y)
        for n_i in range(n):
            xn = y[n_i]
            yn = b0 * xn + z0
            z0 = b1 * xn - a1 * yn + z1
            z1 = b2 * xn - a2 * yn
            out[n_i] = yn
        y = out
        zf[s, 0] = z0
        zf[s, 1] = z1

    y = np.moveaxis(y, 0, axis)
    return y, zf


def _sosfreqz(sos, worN, fs):
    """SOS フィルターの周波数応答を計算する。
    worN: 周波数配列(Hz), fs: サンプルレート(Hz)
    戻り値: (w, H)  w=worN, H=複素応答"""
    w = np.asarray(worN, dtype=np.float64)
    z = np.exp(1j * 2.0 * np.pi * w / fs)
    H = np.ones(len(z), dtype=complex)
    for sec in sos:
        b0, b1, b2, _, a1, a2 = sec
        zinv = 1.0 / z
        num = b0 + b1 * zinv + b2 * zinv**2
        den = 1.0 + a1 * zinv + a2 * zinv**2
        H *= num / den
    return w, H


def _estimate_bpm(mono, sr):
    """numpy自己相関法によるBPM推定。
    mono: 1次元float32配列, sr: サンプルレート
    戻り値: BPM(float) または None"""
    # オンセット強度エンベロープを作成（短時間エネルギー差分）
    hop = int(sr * 0.01)          # 10ms hop
    frame_len = int(sr * 0.04)    # 40ms frame
    n_frames = (len(mono) - frame_len) // hop
    if n_frames < 20:
        return None
    energy = np.array([
        np.sum(mono[i*hop:i*hop+frame_len]**2)
        for i in range(n_frames)
    ], dtype=np.float64)
    # 差分でオンセット強度に
    onset = np.maximum(np.diff(energy, prepend=energy[0]), 0)
    onset -= onset.mean()

    # 自己相関でBPMを探索（40〜240 BPM）
    fps = sr / hop                # フレームレート
    lag_min = int(fps * 60.0 / 240.0)
    lag_max = int(fps * 60.0 / 40.0)
    lag_max = min(lag_max, len(onset) - 1)
    if lag_min >= lag_max:
        return None

    # 正規化自己相関
    norm = np.dot(onset, onset)
    if norm == 0:
        return None
    corr = np.array([
        np.dot(onset[:len(onset)-lag], onset[lag:]) / norm
        for lag in range(lag_min, lag_max+1)
    ])
    best_lag = np.argmax(corr) + lag_min
    bpm = fps * 60.0 / best_lag
    return round(float(bpm), 3) if 20 < bpm < 300 else None


def load_global_settings():
    """楽曲に依存しないグローバル設定（zoom倍率・音量）を読み込む"""
    p = os.path.join(CACHE, "settings.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return {"zoom": float(d.get("zoom", 1.0)),
                "volume": int(d.get("volume", 100))}
    except Exception:
        return {"zoom": 1.0, "volume": 100}

def save_global_settings(zoom, volume):
    p = os.path.join(CACHE, "settings.json")
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"zoom": zoom, "volume": volume}, f)
    except Exception:
        pass

def _fhash(path):
    st = os.stat(path)
    return hashlib.md5(f"{os.path.abspath(path)}|{st.st_mtime}|{st.st_size}".encode()).hexdigest()

def _conv_hash(fh, spd, semi):
    return hashlib.md5(f"{fh}|spd={spd}|semi={semi}".encode()).hexdigest()

def _cache_valid(p):
    return os.path.exists(p) and (time.time()-os.path.getmtime(p) < CACHE_DAYS*86400)

def get_wav_cache(path):
    h = _fhash(path)
    w = os.path.join(CACHE, h+".wav")
    return (w, h) if _cache_valid(w) else (None, h)

def set_wav_cache(path, tmp, fh):
    import shutil
    dst = os.path.join(CACHE, fh+".wav")
    shutil.copy2(tmp, dst); return dst

def get_conv_cache(fh, spd, semi):
    p = os.path.join(CACHE, _conv_hash(fh,spd,semi)+".wav")
    return p if _cache_valid(p) else None

def set_conv_cache(fh, spd, semi, data, sr):
    p = os.path.join(CACHE, _conv_hash(fh,spd,semi)+".wav")
    sf.write(p, data, sr); return p

def save_session(fh, state):
    p = os.path.join(CACHE, fh+"_session.json")
    try:
        with open(p,'w',encoding='utf-8') as f: json.dump(state, f, ensure_ascii=False)
    except: pass

def load_session(fh):
    p = os.path.join(CACHE, fh+"_session.json")
    if not os.path.exists(p): return None
    try:
        with open(p,encoding='utf-8') as f: return json.load(f)
    except: return None

def purge_old_cache():
    now = time.time()
    try:
        for f in os.listdir(CACHE):
            fp = os.path.join(CACHE, f)
            if now-os.path.getmtime(fp) > CACHE_DAYS*86400: os.remove(fp)
    except: pass

# ── アイコン
_ICON_CACHE = {}
_ICON_B64 = {
    "help": "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",
    "zoom": "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",
    "ear": "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",
    "ab_repeat": "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",
    "ff": "iVBORw0KGgoAAAANSUhEUgAAAJYAAACWCAYAAAA8AXHiAAAOeklEQVR4nO2da6wkRRXHfzNzdxfxLWrU+EoMYlQ0fACC4gswxig+EEQjica4GhJEBCOKxkhc0EhE9IMIoqJo5CU+o/JIEDE+AxoNajCIUWNYjQZBze59zPjh9N86Xbdn793d6eq+d84vmcxMT81Mddepc06dOlUNMCQIZkwIVdAKIVhBK4RgBa0QghW0QghWEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARBEARzwaDw/y0Ao+r1CNiSHRtQ3xBugf5sELdAul7+ujW9HjHnlBIsXeiF7PiweoyoC9Eoe+6aXPB9p9A54D4TW0pVsG+U1FhNF1wNMqAuTIPq0ZeGGdKsjRaAbdS1mf8ODcfngtIn7c3aC4GvA18FXoIJ0aChXN/YBrwD+CZwJvDY6vjW6tmbcy+Qc0Xpk5Y2OhgYAxP3fA5wUId1W4sRJijbqdf7x8CRrpz3w3xnmStKnXSugV6ONYwaR49rgUNJfkvuzHeFrtOBwIXACrBEvf4vwwRpRNJe0B8/sSilBUv/90pSg6xQ1wBj4HjM5FA9D9Z4tM2oejwMuLiq51L1vNvV+xPAI6vv9KFDdEZJNT0kjQpfQV2oVqqHhGsZeCdwAGsLVYlzkJA8GLiU1CnG1DXvGPgi8NSqvEa7QUvkjf8a6oLVpLkmmGP/7Oz7uSbYk2aYZcMOgIdigpWb8JWGYyeR/DIanjctfTtBCdYAMzNgJvMG4GhSIDUPSI7da+8sD6rfXG611oYf/UnjXgW8C3i4q6ev/wJzPGqcFevRWHq/DCxSd47HwFlYIy1UDx/jyh1kHxebVcPtSWN5n8uf0xi4FRuQ+DjYXDr0bbBewfL+1jKrG+kmkv+SIx8u12glBGvZPf+XeifRZydStxL+9abSWl2awqYLKSfYT/MMqDfgMcA1wMms9p3GWCPmvz2ZWa2n42cNHuCO++meq7EByaOqcmNXBsoNRDYV+QU7kekay2stP1ocu9crwA7gMe735SjnDvuszM5aplD1Xmo4vpw9P6uq6xaSn1VylNsqJTXWWtkAUL/weYBUzq+c+wnwXuAS4DCSo+4d9pLDfGlLmeNx9rk01Air+y+xkMuYTSBIOX0aFUoomhpFmkDaSA00xKLdtwMnAA+qym9x39Nvt43PalDHENJiQ5IgDYCvAVcAj2j4vQ0tbCVn331IYELSJmp8b678azWCH6YPG8peg2mwg0iao0mg9scs5uYtpylXS/+5JftMIZCTsVjdC6hr46Zz9HhB7q0QlqyY/ut17NnH2tuH/JrrMP8FmhtEgjptdLYWD8HM777W2/tfi9R9xrdVv+9jW96cbxj/q0+mcH+RCX0V8AtMEzyQ1DBe2+UmKTe9bddTmjTPNfsUcBnwdFKw1wd3pcm8sPWyDbuoVJs9TgIzBK4EzsWG9jIv0lRq2Cbt1SaL7rVmFryQDzGH/kvAUVUZ7wao84xJQlmyU6ybXkr7fuLP6Qzgz8Cx1NOe9ewnkUsgTSP/qMm/3IbNjf4Q+DDJsfcdYkwSzF6axs0oWNJOYgTcCLwFazT5OGrMktfAD5bkRynEIgFZIpm/9wAXAc8g+XSaylpg9bn2jtKpMwCvZ7bOu+JfY/e7i1mZSzH/BfY9xrU/zrv/jgTIf6a6L5JyvPQ4FksyhPImfK8pXbEmAZ61UCtACtazx1hDLWIpxb8Gnkfq6V0EieXveRM4cZ8rQ2Opeqxgc6TbsXCKhK23aTheHbeNn/ODFOiclWDlcTB/0bdS929uBk7HtI93nAesHkXiPoMkADqfvfHPfJwrD4Xk77e4hz67CNO6B1fHFVSedg0PyP63GL2T9BaRUGvUeCGWX39IdnzZlRe58HTpMJ8A/BZbM7CVZEZ9Z9KIcRer89eKME+CNSJNC8lcvhj4MpbCo1GXGmgtH6z0hLHSb9QBrsMyJR7tykwwYVtyx+S7FWWeBAvqQiBTfBiWznIB8ETq000qN+03SiKB9+7LecBO4EUk7aURZhvZHetm3gTLx46g3lBvBy4HDsccffVyaYiu8dkdfgQJlrp9KpZdq+DpxH2veEiiDxesFOPs2R9XD38+8BPgrdjQXinQfvoHutNafuJeQdaV6vjHgG8Az6QuVKWnrID5Eqwh9SG6z97UJLDiTJdgo6/HY/7KnvytkkImTaX6KH0IrN5HAb/CpoU08gznvWV8L/bmTa8XSH7KBAvgfgWLeZXI51oP+QKRPGde9bwWOA3LT/OOfDHUi0tItI//+Pel8P89LWUm96cOB27BApNe6Pw5QDnB25MimFD3rS7ABiUyjfl3W43cz5PGWg8+jgXJjFwMnE0SLmUpNAlqVyiUsuzeHwN8G8uy9Z1GAjimvsfEzPCz/EGanPazBEpd+SDwLeBJdGRe1kBCJUHZitX7CZhwXURavKFzovrOhl/j6NXvG5i+0qXrh5x5TWL7yePvAj9wde/TOfjVTAqmqu5LwEvXaJ+Z0QcV3ickSJB6t0yMOA5z6Aek7IS+4JeR5WlBC8BzsPlD7eLTNGc5s4oEhqZz1DDyVUZZGR96UPJgX7I4fT38wELn8k8sHWc3KTis854pIVh1FHDcTQqM+hHfENvo43pSYzWtvO6KISnNxkfqdS5Xk0aI/txmXv8QrIRfryhT4dcxTrBJ31OBO0ihmk4CkHtAuVwy4QvA54CnAH+nvi4A6tp5ZnSxIZjiQFK/pebi8v/xAdNp5dTzh8Ap2ALTMeanKAJeasX1tLifN2Urrqzq9CEsReje7HtjV3bmzJPG8pFpvfcNJRPhR3pD4PvYOsUrsV1kNJGthis5VFf9fazKL7Lwjvpfsb3FPsBqoWqdedrCUFoyj57rs3yqZ4Ktkvk48I/qmNYEqswizfu7t4HqL02pJfvSqNJAI+D32PrK3xSoVyPzJFiQera0jJbi+wi6Gmw7lgTog6EKQEqwtrrjbV/Lxey/8yX2CnTuwCbR/1J9ps5QNCwyb4LlhciHDpZICy+uB94N/I7UGBpVSdPtoi5MJcxhvmpawrRCyho9BRv55fn6JbbKrDFvgiVzl6ebqNE+D7wfuMeVV8P48n5xhsq1jddK0rzKF7sbeC22tYA35X5hSGislsnzsXTseGyJ1RL1EIMPNMr8qKGk9VoJMjag//ba9nzgk1iKcp6toqmd4sybYMk518UfYqukd2Ab0Coavcxqp1jaThvu+rzy0pO427BzOAmbYN7F6viUQiGd4H2OjU7TdMaEerzGm7UBZvZOwiaV9RuKXek7+WocBSC9aZmlmcnrrPnIRZJwX43t73At9VkCnUNnmkpsJo2lht9NipznGkomZCe2F9VNwH/oR+fK5yqF3isX7H3Yoo97SIqhUyFqYjMJlrTGNnfMT1uANdwt2AYhd7ky6xk5tS18EnxvVv02RmNss7rvAfdjgiYt1js2U+Q9N+syDYvu/XYsJ+kPrmxfshNUf5kyDRaG2H5Zh2DbYf67Kp9nsfaKzaSxPD4utRXTRsdhDjqs9sf6IFhQd8Blvs/BJpH/VpVRGEEadkx/Osf/2UwaC+rxHTXM+cDjMBMIqx3tXjUIqU1uxbYu+ijmE/q4lE/V6WRB6lpsNo2VD7nfhOVP7SI5wd6fklaD7pd4yb+aYPsynAX8iRSQXWR18mHXdZ7KZhIs7/jehq1mvp10I3Dvt6i392lRhOp0BvBZbLQKVt/FrKxGt1oY0TtKC5bPXvRZAdNyjfLv+of8DCXbjar352GrmHdWxxTQFPtq+vw+Wvl1m1Z3v3/VIDueB1V3YlsU/ZR6Cs80/6l3IQbPRtJYahw/zeKj32NMS12Jmb7SfoeExZunph37NFjwGRaXAx8hhUD8d3rnP62HLp33fRkmy2nVsFwNeRXwNOALpFSY0uc2woKz0+5F6J1sv2fV6VgY5C7qac7+ecMNsvqgsfZmVKNA4RLmO42xUdNF2HC8SVhzLdImftSm1363Y3UGpTYfge2JKnOnLYi0QYl+a8PRVU/YW23lTZ+mbO7EYlPnkBYJyM+SRsjTkdtGI8580zOFP/T5Dmz/059jZtvHrrTKBvrR8feJLiq+NxoqLzfBevtnsAUCd5J6u/dh9CxBK6W1fKzJC4uECmwfhR+R5ijzRR3+nJfdZxvK19pItlv+1RnYEqw7SY5w3iiaXyu95s9PyWiRg3ykK7AbAdyATctoVJzfHD3/PQnnhqLPqja/mLdhZu9mkjbyDjwkIfPDcwlY2/iQiZ/nGwNnYtmp97E6eu5X3Hh0g6ZeTtmsRUnB8vNb+Z4BEpB8lz2V+Q7wZuBfJIGbFjHPBXKWQuVDHh4fl/JaZoBNel/vvrve1cc+8LmhhArKmkKFAWS+NPrxG2v4MIEu/KuxZLz7WH2LtQFlQwtjbPDgNzjzHcCvhrkM22ryRvptGVqhixP2+eR6PS0P/bnAz0gCpZGf7/WlzcQCNsXiFy1IoHTsbEyw7qWcKe4VJTWWTIhUvKLj+ahuDHwaeDI2esp3nMtzrkpukJ8vVoDUQRawJWNvxBa53l+oTr2l5Khp5J6PoH4bW5nI07A7o0LzWrouE9sWsLpfQMor1+NWbL9PsDhbXve5o3RDqXEOxGJREqo/YrcgkWOfr4DZUz1LaF4/2Dia+i5651K/9Qik8+hlhmfbTBvltIFvfDm8W4EjMSG6A1sg4FcfL7vX3jHO61wiAKr/lOk+FLtFyt3YXglLrkzThPnc0bVp8atQmuqSr1jxd7kSJTSW/mMLq0eu+S1581vxbvjNY4MgCIIgCIIgCIIgCIIgCIIgCIIgCIIgCIIgCIIgCIIgCDpkLleSBO2xme6lE/SIjbSNUbCBCMEKWiEEK2iN8LGCmRMaK2iFEKygFUKwglYIwQpaIQQraIUQrKAVQrCCIAiCIAiCIAiCIGiByG4IZk7EsYJW+B+wPHC4vGliKAAAAABJRU5ErkJggg==",
    "open": "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",
    "play_pause": "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",
    "redo": "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",
    "reset": "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",
    "rew": "iVBORw0KGgoAAAANSUhEUgAAAJYAAACWCAYAAAA8AXHiAAANSElEQVR4nO2dX6xl1xzHP/v8ufdOZzppp1MxRYYMUTpEOjNqVE2EVuqhPNBE0RCNpEiRSnjw50VEkCiCUH9S8UDQ9An1p7Qz6k9CPHipSAgivPHCzNx7z/awzs/6rbXXPvffWWvvOef3SU7Ovvuee+5v7/Xdv/Vbv/Xba1cYxnypAAZdW2EsJiYsIwsmLCMLJiwjCyYsIwsDplG8YcwT81hGFkxYRhZMWEYWTFhGFkxYRhZMWEYWTFiGYfQeyYlW5rGMLJiwjCyYsIwsmLCMLJiwjCyYsIwsmLCMrFhNljEvKiyPZeTChGVkQYRVd2qFsXCYxzKyYMIysmDCMrJgwjIM45LB8lhGHkxYRhZMWEYWTFhGFkxYRhZMWEYWTFhGNpa5Fmuotgf4C03e9bmp6PZcDRP7BtP9bfZ2SucGFGKEuqEy+nkMrEafr3CNNlaf7eu50hdEhTuWMV6M4y6M6uvJyk3q6o4FJz+v0L2wtMfSdowSvxc6ERQsZ4xV4bs96UZqXANJXdoLgPuBLwJHgYvFrWyySdheIpoJ3vZDwOuBLwG3qs92ckEsi8caEMZRgj7+/cCbcI1V4xrzJ8A1dO+xRjgxaRvk4hgC1wLfxNtdA2+Yfs6EVQA53gGui5PtI8B9uAbRrwlwmu6FJZ5WujwdP50AHsfbKxfGOeBAQftm71hQYk8l3eBB4OX4BtnAi0qu/BfTvbDADyhWp68DwN14ey/gxVUDvwT2FbRt9o4FR4/wVoA34sU0wYlpg7A7PEV/hCXB+tXAp3A2XgTWp9vreIGdBS4vaFuw3fXJmhdxHkqG3vFoSRrnGcCDuAYQIYmYtMhq4IWZbRe7wB/DCs72uH1WgZOEdsbdt7wem36+xCBt4T1WHNyCE9Jw+j4Abgb+THiVdy0s8DEf+OPQCdB9wJ00PawJKzPxFa5/XsU1zAcIr/RN9XOXwhIB6aeF6GN5FvAVQuGIwC5iwipCPFUDcB3wAK4x5KUbqGthaXt1PDfEjUr/Riimtpc+BhPWnJHkoRzbaeCfuJMu3Z94q4l674uwhMuAN5MWjwhMbDdhZaTCiUpO5CHgPXiBrEfvcWN1KayV6OcnAU8QpkHiQP08oci0sCbAozhhlWjjhRaWDMUHwNMJE54bhIHuOs0G6YPHqnCDi7N4jxSLSnupOHg3YWViFXgl4cmOGyIWUR+6whFwBfBBwosh9qxxoG7CmiOSOohHT4eBdzG7YWYFvZs0G6gGbtiBbZLSaKuNantG5HOBr+GTm3t9beJiLH2ecrIQCVItKNk+DvyMZrc2K8+TQ1iz0EG0jFzXgFcBf8F7I9317eTiMGHtAl2UB66RRriR0x2EsZMIJBXw5hKWDr51kZ1Gx4AVriTnvuh/rdMcuZqwMqFzOjLLD3AV8GFCIUkWXWfTU6PAeQsrVR48UtvSfcu+E8DD7NyzmrDmQKVe0nDiCW4k3XXEDVSyK9SZfom1IBTdGvBu9d3b6ep2IzoTVgtV9ALXQPuB22kKIh7VycndboyyV2G1BesjtU93fXqk2jYls91uvHfCGrV+rH8MgCuBT+MqIzfxnkwOakJ4gOIpNknHPPOknr7LOdXd8xh4Ea6hBW1zXJsu4tDfe0mVkffV2NQVdgPwLbyopFZdTrzs03mcyfR3uUUVs4E/hoPAXYSikrlKcDbruUq5OOT4JvS3nWZSsitMDbdjG/T2Cs4DvI35Bra76Qrj2q5UnZfeXwHPBD5XwPa+dYWU7AqHuIMVI2pCrzOiecVeC9yLu8Ghb8ix6OMa445lDLwU+B7u4tig7LnunJIHK3GOvEtXIErfwMdLNa4c+Bz9KAkW5GKQLnaAO54RPtWxD3gr8Bn8hXJJdmV7oaSw5ORXeFGBa6whvvu5GrgHV5C3qT7TtbhqnPe5oPZNCC+SY8Af8V5XLqSlE1bJA9ZXuZS3gO8CR8BzgM/jRCWN1ja3VpoKlxaIiwhFQLcD38d73on6fB/sL07pg9bJTslEV8Br8TknmZaJS126Dt414u0PAx9VduvgeZL4rqUI3pM7ChgwVO9HgA8RFuHtduI1p7Diu4CG0/1no892IaLeCav0SEWP/GpcHfrHgVumv5dAuFZ/U9OPriTuyl8DfIfQK8kFs6G25Vj6cAwLiXgoWYNAVyT04ZUqmJN9MqVT4bq+L6i/6cK7bsf71sBPaZY8LxySNtgPvJ3+NcgmXkgXCOuhTk2P4SnAN6b72+b3+vDqXFglu8Ial4n+KnDTdN864UIXXVNP3/WqLmLbSeBX+BHfWH3eurmw2y+abljDld7eRDiHF+e1ukIELlc8+KK71wHfxotKZgzA59qMjjhNM445T77uYLfdYU2zMFDHW30Z9fWtKwy8dkmPdSH6fzXNEWDXiEfS00ySS9N19trDmsdKUFJYvwN+hBdS3KV0jZ671FWg4KorHlKfk/3ruO5Tuk7DUfTpXzWuluqT8s+n+4Kgr0P0XKYuEBwBv8et7flZvKjE4y7lJHOfkHm/y4BXMHu6Q8deqZLjEvGJfkm64XLg/bTfntVmZ+m4rPN0Q8krTeKXddyCsU/FTTjroE88l6y5vkF/hvJj4D/Ax4DbgD9M9+tzGNsq3WsfPHIpireXrqyUf34AeCfhaEwmb8UTlE6kprzLyam9soCbVId+F5co1XcIravti4SJ12XwWJ04AvmnsiD/AOcJbgR+g28QnfnusiuU7ZOkCw4P41azkc/LCDJeWqj0q2thdeK1dJZdLzR7CH9rlJyY/1JeVG3CisMGfbfzzTQrI/TPy+axOgtf9FSSvmdwBb/ayqy1rHI2SKp05iRhNyh2D/Dx4HHgEcJFPUoLqmthxfeBFmNWoAu+4W4Ffo2PU/ogLLE5vm9RC22MvzDiWNGElfGf6rUX4m4RwqK0YzhxlW6QNmFpAaVYwRcD3kLYrS5LuuH/wiqdINXzbRLkaqRAbgD8CTgDvCX6jjrxnRCuJ4rapz+/HdqEU0fvMZIaqYAf4m6nf1B95yw7dmrjVvZNEtslPMk8jiMbcvBys8UqbgL7F3jhSAI1tZJMHNfsJEabFbxvx24dL4JbDecdyg69IK18/7y6ykniOx8hXDuiVIlyX3KPQPqOHKmLGpF+iNKmep9VK7+ThUF2Kyw5BghrzNZwZcyzxDCPIN+EtQVxcBwXI94J/Bt/AmOPtJdR5F6FFR+HXBgV7hEr9ysbUw+DMmFlQE/+6n3aC4xwXeNx/EmUUeNFmie2pLDihdXEZn2Sr8KvkbrJfLPyJqwZiFGpm1TjhdeuAD5CeNVrQYnn2onQ5uWxpPvWI0ld6vwS3Hqp8v3zSKmYsLaBNEy8L37WzH5cOUtN+OCiOtq3k1X99hK8C2226wcuHcWtRGPBeyH0yCp+dIleclHfQPp84Ad4YYi3kix4KY+lF1AbtGxrT7ZCOAm/cMLqpcJ2yDW4hW7jE912d7P+XZxf22tX2IZ4Wz0VNMI93PyJFnu12OMuM3UR6O0fU27tiCq1vQjCkiLCV9NshFhQIqCUkHIKSyNzj8JR4OszbJjQ/nCBeNlxE9Yc0d3Ns3G3msUlLPGzdOJYrKSwwKckdHXtHcqG1F1MbXcLmbAyIjHOELcQ7vsIr2iJP9pimpzC0uc4Lh3SsZk8C0jHhdr7ph4nF9d/mbDmiM526+N5GW46aFaArLub3DGWkEqn6EHKEdxd42KHVKrGA5S2h3iasOaMznfJiOgYbtnJ8zTXhN8gnHvMKaxUI0t3GNsObsXlewi7bR1n6S7chJWZeFi9Nn2Xh2KmPJbO2ucSVmpWYavPr+KEcQb4K6F4pITbhJWZuCuJE5YSIN8G/AMvqAuUSTfE3kijLwaxVeefBri5xk/QfMC4nmHonbCWAZ31vg63VHY8wtJ3BumUxPWFba0SL3B3Nd2l7NX2S9wlg5MJ7ja7Umu4Lq2woFktcS++O9HJ0niUdaKsmUBTWNqDPQ94nGYXGF8cj9F8nEpOe1PbS4Fe5XiMa6wzNPNbekJ7QtlnQgspj7WCF8oxXNc4K2XyaPT3ue1NbS88OtYY4u9tBHgabk2J2HuJ0LrwWNAUlo69RriByd14QckzGuU4HqabZYyWSlgx0r1I3LWGKyKMc0N/x9V/dYkO7OMnuYK74fcczSD+ATp8XuEyERcT6nopqfa8HvcgAPFW76VcnLIVqae4ClcCXyYM5k/RTHPkIhDWMilLTvBk+i4i0w9YkqD9IG5Jy38BPy9n4pbEXkFixvXpvhVct/1k4Le43JcwIS8VTtSyvXTEuS75eZz4jAT5fThRqZq0uKBwRf0uLorMTdJjabUtK1s1QN/PT9f2Bx7LVqIzsrBUD2fcgr57pK3olf3msYwsmLCMLJiwjCyYsIwsmLAMw7hkGJjHMrJgwjKyYMIysmDCMrJgwjKyYMIysmDCMrJgwjLmRXA3kAnLyIIJy8iCCcvIggnLyIIJy8iCCcvIggnLMAzDMAzDMAzDMAzDMIylpQ8LihmLRQWWeTcyYcIysmDCMrJgwjKyYMIysmDCMrJgwjKy8D9cY/C2t60KowAAAABJRU5ErkJggg==",
    "tempo_search": "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",
    "undo": "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",
}

def _get_icon(name, size=32, color=None):
    key = (name, size, color)
    if key in _ICON_CACHE: return _ICON_CACHE[key]
    r,g,b = (0xBB,0xBB,0xBB) if color is None else (int(color[1:3],16),int(color[3:5],16),int(color[5:7],16))

    def _tint_qimage(qimg):
        """QImage(ARGB32)のRGB全チャンネルをr,g,bで置換（アルファ保持）。numpy使用。"""
        qimg = qimg.convertToFormat(QImage.Format.Format_ARGB32)
        ptr = qimg.bits()
        ptr.setsize(qimg.height() * qimg.width() * 4)
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((qimg.height(), qimg.width(), 4)).copy()
        # ARGB32 little-endian: [B, G, R, A] の順で格納
        arr[:,:,0] = b; arr[:,:,1] = g; arr[:,:,2] = r
        raw = arr.tobytes()
        tinted = QImage(raw, qimg.width(), qimg.height(), QImage.Format.Format_ARGB32)
        return QIcon(QPixmap.fromImage(tinted.copy()))

    # 埋め込みBase64を優先
    if name in _ICON_B64:
        data = base64.b64decode(_ICON_B64[name])
        qimg = QImage.fromData(bytes(data))
        qimg = qimg.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        ico = _tint_qimage(qimg)
        _ICON_CACHE[key] = ico
        return ico

    # 埋め込みに無ければローカルPNGから読み込み
    _dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(_dir, f"{name}.png")
    if os.path.exists(png_path):
        qimg = QImage(png_path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        ico = _tint_qimage(qimg)
        _ICON_CACHE[key] = ico
        return ico
    return QIcon()

def _load_icons(): pass


# ════════════════════════════════════════
# ConvCache
# ════════════════════════════════════════
class ConvCache:
    def __init__(self, maxsize=8):
        self._d={}; self._order=[]; self._max=maxsize
    def get(self, key): return self._d.get(key)
    def put(self, key, val):
        if key in self._d: self._order.remove(key)
        elif len(self._order) >= self._max: old=self._order.pop(0); del self._d[old]
        self._d[key]=val; self._order.append(key)

# ════════════════════════════════════════
# NSF (NES Sound Format) 対応 — libgme ctypes バインディング
# ════════════════════════════════════════
import ctypes as _ct

NSF_SR              = 44100
NSF_FRAME_SAMPLES   = 735                      # NES 1フレーム ≈ 44100/60
NSF_MIN_DURATION    = 10.0                     # 最低10秒保証(sec)
NSF_DEFAULT_DUR_SEC = 60.0                     # デフォルトデコード時間（1分）
NSF_SILENCE_DUR_SEC = 5.0                      # 自然終了判定：最後N秒が無音
NSF_EXT_STEP_SEC    = 60.0                     # 手動延長ステップ（1分）
NSF_MAX_DUR_SEC     = 900.0                    # 最大15分
NSF_SILENCE_THRESH  = 32.0 / 32768.0           # 未使用チャンネル判定閾値(float32)

class _GmeInfo(_ct.Structure):
    _fields_ = [
        ("length",       _ct.c_int), ("intro_length", _ct.c_int),
        ("loop_length",  _ct.c_int), ("play_length",  _ct.c_int),
        ("i4",  _ct.c_int), ("i5",  _ct.c_int), ("i6",  _ct.c_int),
        ("i7",  _ct.c_int), ("i8",  _ct.c_int), ("i9",  _ct.c_int),
        ("i10", _ct.c_int), ("i11", _ct.c_int), ("i12", _ct.c_int),
        ("i13", _ct.c_int), ("i14", _ct.c_int),
        ("system",    _ct.c_char_p), ("game",      _ct.c_char_p),
        ("song",      _ct.c_char_p), ("author",    _ct.c_char_p),
        ("copyright", _ct.c_char_p), ("comment",   _ct.c_char_p),
        ("dumper",    _ct.c_char_p),
        ("s7",  _ct.c_char_p), ("s8",  _ct.c_char_p), ("s9",  _ct.c_char_p),
        ("s10", _ct.c_char_p), ("s11", _ct.c_char_p), ("s12", _ct.c_char_p),
        ("s13", _ct.c_char_p), ("s14", _ct.c_char_p),
    ]

_gme_lib_cache = None

def _gme_load():
    """libgme.dll をロードしてAPIを設定する。失敗したら None を返す。"""
    global _gme_lib_cache
    if _gme_lib_cache is not None:
        return _gme_lib_cache
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    # DLL検索候補ディレクトリ（exe隣の dll/ を優先し、dist/ も含める）
    dll_dirs = [os.path.join(base, "dll"), base, os.path.join(base, "dist")]
    for d in dll_dirs:
        try: os.add_dll_directory(d)
        except Exception: pass
    dll_paths = [os.path.join(d, "libgme.dll") for d in dll_dirs] + ["libgme.dll"]
    for path in dll_paths:
        try:
            lib = _ct.CDLL(path)
            lib.gme_open_data.restype  = _ct.c_char_p
            lib.gme_open_data.argtypes = [_ct.c_void_p, _ct.c_long, _ct.POINTER(_ct.c_void_p), _ct.c_int]
            lib.gme_delete.restype     = None
            lib.gme_delete.argtypes    = [_ct.c_void_p]
            lib.gme_track_count.restype  = _ct.c_int
            lib.gme_track_count.argtypes = [_ct.c_void_p]
            lib.gme_start_track.restype  = _ct.c_char_p
            lib.gme_start_track.argtypes = [_ct.c_void_p, _ct.c_int]
            lib.gme_play.restype   = _ct.c_char_p
            lib.gme_play.argtypes  = [_ct.c_void_p, _ct.c_int, _ct.c_void_p]
            lib.gme_track_ended.restype  = _ct.c_int
            lib.gme_track_ended.argtypes = [_ct.c_void_p]
            lib.gme_voice_count.restype  = _ct.c_int
            lib.gme_voice_count.argtypes = [_ct.c_void_p]
            lib.gme_voice_name.restype   = _ct.c_char_p
            lib.gme_voice_name.argtypes  = [_ct.c_void_p, _ct.c_int]
            lib.gme_mute_voice.restype   = None
            lib.gme_mute_voice.argtypes  = [_ct.c_void_p, _ct.c_int, _ct.c_int]
            lib.gme_track_info.restype   = _ct.c_char_p
            lib.gme_track_info.argtypes  = [_ct.c_void_p, _ct.POINTER(_ct.c_void_p), _ct.c_int]
            lib.gme_free_info.restype    = None
            lib.gme_free_info.argtypes   = [_ct.c_void_p]
            lib.gme_set_fade.restype     = None
            lib.gme_set_fade.argtypes    = [_ct.c_void_p, _ct.c_int]
            _gme_lib_cache = lib
            return lib
        except Exception as ex:
            pass
    return None


# ─── ffmpeg auto-download ─────────────────────────────────────────────────────

_FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-lgpl.zip"
)
_FFMPEG_EXE_IN_ZIP = "ffmpeg-master-latest-win64-lgpl/bin/ffmpeg.exe"

def _get_app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _find_ffmpeg():
    base = _get_app_dir()
    candidates = [
        os.path.join(base, "ffmpeg.exe"),
        os.path.join(base, "dist", "ffmpeg.exe"),
        "ffmpeg",
    ]
    for p in candidates:
        try:
            r = subprocess.run(
                [p, "-version"],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if r.returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    return None

def _download_ffmpeg(scb=None) -> str:
    import urllib.request, zipfile, io
    dest_dir = _get_app_dir()
    dest_path = os.path.join(dest_dir, "ffmpeg.exe")
    if scb: scb("Downloading ffmpeg... (~40MB, first time only)")
    _log(f"ffmpeg download: {_FFMPEG_URL}")
    try:
        with urllib.request.urlopen(_FFMPEG_URL, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            buf = io.BytesIO()
            while True:
                chunk = resp.read(65536)
                if not chunk: break
                buf.write(chunk)
                downloaded += len(chunk)
                if scb and total:
                    scb(f"Downloading ffmpeg... {downloaded * 100 // total}%")
    except Exception as e:
        raise RuntimeError(f"ffmpeg download failed: {e}")
    if scb: scb("Extracting ffmpeg...")
    _log(f"ffmpeg extract: {len(buf.getvalue())} bytes")
    try:
        buf.seek(0)
        tmp_dir = os.path.join(dest_dir, "_ffmpeg_tmp")
        with zipfile.ZipFile(buf) as zf:
            zf.extract(_FFMPEG_EXE_IN_ZIP, path=tmp_dir)
        import shutil
        shutil.move(os.path.join(tmp_dir, _FFMPEG_EXE_IN_ZIP), dest_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        raise RuntimeError(f"ffmpeg extraction failed: {e}")
    _log(f"ffmpeg installed: {dest_path}")
    if scb: scb("ffmpeg installed")
    return dest_path

def _ensure_ffmpeg(scb=None) -> str:
    path = _find_ffmpeg()
    if path:
        return path
    return _download_ffmpeg(scb=scb)

# ─────────────────────────────────────────────────────────────────────────────


def _nsf_fmt(path):
    """NSFヘッダーを確認してフォーマット ('NESM'/'NSFe'/None) を返す"""
    try:
        with open(path, 'rb') as f:
            h = f.read(5)
        if h[:4] == b'NESM': return 'NESM'
        if h[:4] == b'NSFe': return 'NSFe'
    except Exception:
        pass
    return None


_NSF_EXP_BITS = [
    (0x01, "VRC6"), (0x02, "VRC7"), (0x04, "FDS"),
    (0x08, "MMC5"), (0x10, "N163"), (0x20, "5B"),
]

def _nsf_exp_byte(raw, fmt):
    """NSFヘッダーから拡張音源バイトを返す"""
    if fmt == 'NSFe':
        pos = 4
        while pos + 8 <= len(raw):
            csz  = int.from_bytes(raw[pos:pos+4], 'little')
            ctyp = raw[pos+4:pos+8]
            if ctyp == b'INFO' and csz >= 13:
                return raw[pos + 8 + 12]
            pos += 8 + csz
        return 0
    return raw[0x7B] if len(raw) > 0x7B else 0

def _nsf_chip_names(raw, fmt):
    """拡張音源チップ名のリストを返す（無拡張なら空リスト）"""
    b = _nsf_exp_byte(raw, fmt)
    return [name for bit, name in _NSF_EXP_BITS if b & bit]


def _nsf_pad_banks(nsf_raw: bytes) -> bytes:
    """NSFデータの末尾bankが不完全な場合、4KB境界までゼロパッドして補完する。
    FDS NSFでbank値がファイルサイズを超える場合に有効。libgmeに渡す前に呼ぶ。"""
    if len(nsf_raw) < 0x80:
        return nsf_raw
    banks = [nsf_raw[0x70 + i] for i in range(8)]
    max_bank = max(banks)
    min_required = 0x80 + (max_bank + 1) * 4096
    if len(nsf_raw) >= min_required:
        return nsf_raw
    pad_size = min_required - len(nsf_raw)
    _log(f"NSF bank pad: max_bank={max_bank} file={len(nsf_raw)} need={min_required} pad={pad_size}bytes")
    return nsf_raw + bytes(pad_size)


def _nsf_fix_low_load(nsf_raw: bytes) -> bytes:
    """Convert NSF with LOAD < 0x8000 to libgme-compatible form via 6502 trampoline.
    Splits code into RAM part (LOAD..0x7FFF) and ROM part (0x8000..), places a
    trampoline at INIT that copies RAM part at runtime then JMPs to original INIT."""
    if len(nsf_raw) < 0x80:
        return nsf_raw
    load = nsf_raw[8] | (nsf_raw[9] << 8)
    init = nsf_raw[10] | (nsf_raw[11] << 8)
    if load >= 0x8000:
        return nsf_raw
    code = nsf_raw[0x80:]
    ram_size = 0x8000 - load
    ram_part = code[:ram_size]
    rom_part = code[ram_size:]
    trampoline_offset = (len(rom_part) + 63) & ~63
    TRAMPOLINE_ADDR = 0x8000 + trampoline_offset
    RAM_PART_ADDR   = TRAMPOLINE_ADDR + 64
    src_lo = RAM_PART_ADDR & 0xFF;  src_hi = (RAM_PART_ADDR >> 8) & 0xFF
    dst_lo = load & 0xFF;           dst_hi = (load >> 8) & 0xFF
    n_pages = (ram_size + 255) // 256
    # Trampoline: 41 bytes (pad to 64)
    # offset 0:  STA $04       -- save A (track number from libgme) FIRST
    # offset 2:  setup $00/$01 = src pointer, $02/$03 = dst pointer
    # offset 20: LDY #0        [loop]
    # offset 22: LDA ($00),Y  [inner]
    # offset 27: BNE inner → 22 (rel=-7=0xF9)
    # offset 34: BNE loop  → 20 (rel=-16=0xF0)
    # offset 36: LDA $04       -- restore A (track number) before JMP
    # offset 38: JMP original_init
    trampoline_code = bytes([
        0x85, 0x04,                              # STA $04  (save track number)
        0xA9, src_lo, 0x85, 0x00,               # LDA/STA $00
        0xA9, src_hi, 0x85, 0x01,               # LDA/STA $01
        0xA9, dst_lo, 0x85, 0x02,               # LDA/STA $02
        0xA9, dst_hi, 0x85, 0x03,               # LDA/STA $03
        0xA2, n_pages,                           # LDX #n_pages
        0xA0, 0x00,                              # LDY #0         [loop @20]
        0xB1, 0x00,                              # LDA ($00),Y   [inner @22]
        0x91, 0x02,                              # STA ($02),Y
        0xC8,                                    # INY
        0xD0, 0xF9,                             # BNE inner  (→22, rel=-7)
        0xE6, 0x01,                              # INC $01
        0xE6, 0x03,                              # INC $03
        0xCA,                                    # DEX
        0xD0, 0xF0,                             # BNE loop   (→20, rel=-16)
        0xA5, 0x04,                              # LDA $04  (restore track number)
        0x4C, init & 0xFF, (init >> 8) & 0xFF,  # JMP original_init
    ])
    trampoline = trampoline_code + bytes(64 - len(trampoline_code))
    header = bytearray(nsf_raw[:0x80])
    header[8]  = 0x00;                    header[9]  = 0x80
    header[10] = TRAMPOLINE_ADDR & 0xFF;  header[11] = (TRAMPOLINE_ADDR >> 8) & 0xFF
    pad = bytes(trampoline_offset - len(rom_part))
    new_data = rom_part + pad + trampoline + ram_part
    _log(f"NSF low-load fix: LOAD=0x{load:04X} INIT=0x{init:04X} "
         f"ram={ram_size}B rom={len(rom_part)}B trampoline=0x{TRAMPOLINE_ADDR:04X}")
    return bytes(header) + new_data


def _nsf_detect_ch_used(gme_lib, nsf_raw, track_idx, ch_count, detect_sec=3.0, scb=None):
    """各chが音を出すかどうかを判定する（mute-after方式）。
    mute-afterでINITが正常実行されるため、FDSなどタイミング依存ゲームでも正しく検出できる。
    先頭SKIP_FRAMESフレームはINIT汚染のため判定対象外。
    戻り値: list[bool]"""
    ch_used = []
    CHUNK = NSF_FRAME_SAMPLES
    SKIP_FRAMES = 3  # INIT汚染フレームをスキップ
    target_s = int(detect_sec * NSF_SR)
    for ch in range(ch_count):
        if scb: scb(f"NSF: detecting ch {ch+1}/{ch_count}...")
        _buf = _ct.create_string_buffer(nsf_raw, len(nsf_raw))
        emu = _ct.c_void_p()
        err = gme_lib.gme_open_data(_buf, len(nsf_raw), _ct.byref(emu), NSF_SR)
        if err is not None:
            ch_used.append(False); continue
        err2 = gme_lib.gme_start_track(emu, track_idx)
        if err2 is not None:
            gme_lib.gme_delete(emu); ch_used.append(False); continue
        # mute-after: start_track後にミュート設定
        for i in range(ch_count):
            gme_lib.gme_mute_voice(emu, i, 0 if i == ch else 1)
        buf16 = (_ct.c_int16 * (CHUNK * 2))()
        # 先頭SKIP_FRAMESはINIT汚染のため読み飛ばす
        for _ in range(SKIP_FRAMES):
            if gme_lib.gme_play(emu, CHUNK * 2, buf16) is not None: break
        samples = []; rendered = 0
        while rendered < target_s:
            if gme_lib.gme_play(emu, CHUNK * 2, buf16) is not None: break
            mono = np.frombuffer(bytes(buf16), dtype=np.int16)[::2].copy()
            need = target_s - rendered
            if len(mono) > need: mono = mono[:need]
            samples.append(mono); rendered += len(mono)
        gme_lib.gme_delete(emu)
        if samples:
            arr_f = np.concatenate(samples).astype(np.float32) / 32768.0
            # SKIP_FRAMES後もINIT汚染残留がある場合があるため、追加でLEAK_S分をスキップして判定
            # これによりINITでトリガーされたDPCMサンプル等を「未使用」として正しく検出できる
            _DET_LEAK = 60 * CHUNK  # 1000ms: wait for INIT-triggered length counters to expire
            if len(arr_f) > _DET_LEAK:
                used = float(np.max(np.abs(arr_f[_DET_LEAK:]))) > NSF_SILENCE_THRESH
            else:
                used = float(np.max(np.abs(arr_f))) > NSF_SILENCE_THRESH
        else:
            used = False
        _log(f"NSF ch{ch}: used={used}")
        ch_used.append(used)
    return ch_used


def _nsf_render(gme_lib, nsf_raw, track_idx, ch_mask, ch_count, dur_sec=None, scb=None):
    """指定チャンネルマスクでNSFを1パスレンダリングする（mute-after方式）。
    mute-afterによりINITは全ch正常実行→タイミング正確。
    1パスなのでINIT汚染は1×（N倍増幅しない）→実用上は聴こえないレベル。
    戻り値: (float32 mono array, natural_end: bool, actual_dur_sec: float)"""
    if dur_sec is None:
        dur_sec = NSF_DEFAULT_DUR_SEC
    CHUNK = NSF_FRAME_SAMPLES
    target_s = int(dur_sec * NSF_SR)
    min_s = int(NSF_MIN_DURATION * NSF_SR)
    _buf = _ct.create_string_buffer(nsf_raw, len(nsf_raw))
    emu = _ct.c_void_p()
    err = gme_lib.gme_open_data(_buf, len(nsf_raw), _ct.byref(emu), NSF_SR)
    if err is not None:
        return np.zeros(max(target_s, min_s), dtype=np.float32), True, dur_sec
    err2 = gme_lib.gme_start_track(emu, track_idx)
    if err2 is not None:
        gme_lib.gme_delete(emu)
        return np.zeros(max(target_s, min_s), dtype=np.float32), True, dur_sec
    # mute-after: INIT後にマスク設定（タイミング正確化）
    for i in range(ch_count):
        gme_lib.gme_mute_voice(emu, i, 0 if (ch_mask >> i) & 1 else 1)
    buf16 = (_ct.c_int16 * (CHUNK * 2))()
    samples = []; rendered = 0
    while rendered < target_s:
        if gme_lib.gme_play(emu, CHUNK * 2, buf16) is not None: break
        mono = np.frombuffer(bytes(buf16), dtype=np.int16)[::2].copy()
        need = target_s - rendered
        if len(mono) > need: mono = mono[:need]
        samples.append(mono); rendered += len(mono)
    gme_lib.gme_delete(emu)
    target_len = max(rendered, min_s)
    if rendered < target_len:
        samples.append(np.zeros(target_len - rendered, dtype=np.int16))
    arr = (np.concatenate(samples)[:target_len] if samples
           else np.zeros(target_len, dtype=np.int16))
    arr_f = arr.astype(np.float32) / 32768.0
    sil_s = int(NSF_SILENCE_DUR_SEC * NSF_SR)
    sil_start = len(arr_f) - sil_s
    natural_end = (sil_start >= 0 and sil_s > 0 and
                   bool(np.max(np.abs(arr_f[sil_start:])) < NSF_SILENCE_THRESH))
    if natural_end:
        nz = np.where(np.abs(arr_f) > NSF_SILENCE_THRESH)[0]
        music_end = (min(len(arr_f), nz[-1] + int(0.5 * NSF_SR)) if len(nz) > 0
                     else min_s)
        arr_f = arr_f[:max(min_s, music_end)]
    # INIT汚染クリーンアップ：楽音開始以前をゼロ化
    # mute-afterでも最大5フレーム分（≈83ms）はINIT汚染が残る可能性がある。
    # _LEAK_S以降に「無音→楽音」のパターンがあれば、_LEAK_S以前をすべてゼロ化。
    # _LEAK_S時点で楽音あり（nz[0]==0）の場合はゼロ化しない（頭切れ防止）。
    _LEAK_S = 5 * CHUNK   # ≈83ms: cover INIT noise tail
    if len(arr_f) > _LEAK_S:
        _nz = np.where(np.abs(arr_f[_LEAK_S:]) > NSF_SILENCE_THRESH)[0]
        if len(_nz) > 0 and _nz[0] > 0:
            # _LEAK_S以降に無音→楽音のパターン：楽音開始点までゼロ化
            _ms = _LEAK_S + int(_nz[0])
            arr_f[:_ms] = 0.0
            _fe = min(_ms + 256, len(arr_f))
            if _fe > _ms:
                arr_f[_ms:_fe] *= np.linspace(0.0, 1.0, _fe - _ms, dtype=np.float32)
        elif len(_nz) == 0:
            # _LEAK_S以降に楽音なし＝INIT汚染ノイズのみ → INIT区間もゼロ化
            arr_f[:_LEAK_S] = 0.0
        _log(f"NSF noise cleanup: LEAK_S={_LEAK_S} nz0={_nz[0] if len(_nz)>0 else 'none(zeroed)'}")

    actual_dur_sec = len(arr_f) / NSF_SR
    _log(f"NSF render: mask={ch_mask:#b} ch_count={ch_count} dur={actual_dur_sec:.1f}s natural_end={natural_end}")
    return arr_f, natural_end, actual_dur_sec


# ════════════════════════════════════════
# SPC (Super Famicom / SNES Sound Format) 対応 — libgme ctypes バインディング
# ════════════════════════════════════════
SPC_SR              = 44100
SPC_CH_COUNT        = 8
SPC_DEFAULT_DUR_SEC = 120.0
SPC_MIN_DURATION    = 5.0
SPC_SILENCE_DUR_SEC = 5.0
SPC_MAX_DUR_SEC     = 600.0
SPC_SILENCE_THRESH  = 32.0 / 32768.0

def _spc_get_meta(gme_lib, spc_raw):
    """libgmeでSPCのメタデータ(タイトル・長さ)を取得する"""
    _buf = _ct.create_string_buffer(spc_raw, len(spc_raw))
    emu = _ct.c_void_p()
    err = gme_lib.gme_open_data(_buf, len(spc_raw), _ct.byref(emu), SPC_SR)
    meta = {'game': '', 'song': '', 'author': '', 'dur_sec': SPC_DEFAULT_DUR_SEC, 'play_len_ms': 0}
    if err is not None:
        return meta
    try:
        info_p = _ct.c_void_p()
        if gme_lib.gme_track_info(emu, _ct.byref(info_p), 0) is None:
            try:
                info = _ct.cast(info_p, _ct.POINTER(_GmeInfo)).contents
                meta['game']   = (info.game   or b'').decode(errors='replace').strip()
                meta['song']   = (info.song   or b'').decode(errors='replace').strip()
                meta['author'] = (info.author or b'').decode(errors='replace').strip()
                pl = info.play_length
                if pl is not None and int(pl) > 0:
                    meta['play_len_ms'] = int(pl)
                    meta['dur_sec'] = min(int(pl) / 1000.0, SPC_MAX_DUR_SEC)
            finally:
                gme_lib.gme_free_info(info_p)
    finally:
        gme_lib.gme_delete(emu)
    return meta

def _spc_detect_ch_used(gme_lib, spc_raw, detect_sec=3.0, scb=None):
    """SPCの各チャンネルが音を出すか検出する"""
    CHUNK = 735
    ch_used = []
    for ch in range(SPC_CH_COUNT):
        if scb: scb(f"SPC: detecting ch {ch+1}/{SPC_CH_COUNT}...")
        _buf = _ct.create_string_buffer(spc_raw, len(spc_raw))
        emu = _ct.c_void_p()
        err = gme_lib.gme_open_data(_buf, len(spc_raw), _ct.byref(emu), SPC_SR)
        if err is not None:
            ch_used.append(False); continue
        err2 = gme_lib.gme_start_track(emu, 0)
        if err2 is not None:
            gme_lib.gme_delete(emu); ch_used.append(False); continue
        for i in range(SPC_CH_COUNT):
            gme_lib.gme_mute_voice(emu, i, 0 if i == ch else 1)
        target_s = int(detect_sec * SPC_SR)
        buf16 = (_ct.c_int16 * (CHUNK * 2))()
        samples = []; rendered = 0
        while rendered < target_s:
            if gme_lib.gme_play(emu, CHUNK * 2, buf16) is not None: break
            mono = np.frombuffer(bytes(buf16), dtype=np.int16)[::2].copy()
            samples.append(mono); rendered += len(mono)
        gme_lib.gme_delete(emu)
        if samples:
            arr_f = np.concatenate(samples).astype(np.float32) / 32768.0
            used = float(np.max(np.abs(arr_f))) > SPC_SILENCE_THRESH
        else:
            used = False
        ch_used.append(used)
        _log(f"SPC ch{ch}: used={used}")
    return ch_used

def _spc_render(gme_lib, spc_raw, ch_mask, dur_sec=None, scb=None, trim_silence=True, play_len_ms=0):
    """指定チャンネルマスクでSPCを1パスレンダリングする。
    play_len_ms>0 の場合 gme_set_fade でループを有効化し、fade後まで収録する。
    trim_silence=False の場合は無音トリムをスキップし固定長を維持する。
    戻り値: (float32 mono array, natural_end: bool, actual_dur_sec: float)"""
    if dur_sec is None:
        dur_sec = SPC_DEFAULT_DUR_SEC
    CHUNK = 735
    min_s = int(SPC_MIN_DURATION * SPC_SR)
    _buf = _ct.create_string_buffer(spc_raw, len(spc_raw))
    emu = _ct.c_void_p()
    err = gme_lib.gme_open_data(_buf, len(spc_raw), _ct.byref(emu), SPC_SR)
    if play_len_ms > 0:
        target_s = int((play_len_ms / 1000.0 + 8.0) * SPC_SR)
    else:
        target_s = int(dur_sec * SPC_SR)
    if err is not None:
        return np.zeros(max(target_s, min_s), dtype=np.float32), True, dur_sec
    err2 = gme_lib.gme_start_track(emu, 0)
    if err2 is not None:
        gme_lib.gme_delete(emu)
        return np.zeros(max(target_s, min_s), dtype=np.float32), True, dur_sec
    if play_len_ms > 0:
        gme_lib.gme_set_fade(emu, play_len_ms)
    for i in range(SPC_CH_COUNT):
        gme_lib.gme_mute_voice(emu, i, 0 if (ch_mask >> i) & 1 else 1)
    buf16 = (_ct.c_int16 * (CHUNK * 2))()
    samples = []; rendered = 0
    while rendered < target_s:
        if gme_lib.gme_play(emu, CHUNK * 2, buf16) is not None: break
        mono = np.frombuffer(bytes(buf16), dtype=np.int16)[::2].copy()
        need = target_s - rendered
        if len(mono) > need: mono = mono[:need]
        samples.append(mono); rendered += len(mono)
    gme_lib.gme_delete(emu)
    target_len = max(rendered, min_s)
    if rendered < target_len:
        samples.append(np.zeros(target_len - rendered, dtype=np.int16))
    arr = (np.concatenate(samples)[:target_len] if samples
           else np.zeros(target_len, dtype=np.int16))
    arr_f = arr.astype(np.float32) / 32768.0
    if trim_silence:
        sil_s = int(SPC_SILENCE_DUR_SEC * SPC_SR)
        sil_start = len(arr_f) - sil_s
        natural_end = (sil_start >= 0 and sil_s > 0 and
                       bool(np.max(np.abs(arr_f[sil_start:])) < SPC_SILENCE_THRESH))
        if natural_end:
            nz = np.where(np.abs(arr_f) > SPC_SILENCE_THRESH)[0]
            music_end = (min(len(arr_f), nz[-1] + int(0.5 * SPC_SR)) if len(nz) > 0 else min_s)
            arr_f = arr_f[:max(min_s, music_end)]
    else:
        natural_end = False
    actual_dur_sec = len(arr_f) / SPC_SR
    _log(f"SPC render: mask={ch_mask:#b} dur={actual_dur_sec:.1f}s natural_end={natural_end}")
    return arr_f, natural_end, actual_dur_sec


class SpcState:
    """SPCファイル（またはZIP内SPC）の状態とデコード済みデータを保持する"""
    def __init__(self):
        self.is_zip      = False      # True if loaded from ZIP
        self.path        = ""         # 元のファイルパス (.spc or .zip)
        self.spc_names   = []         # 表示名リスト（zipの場合はファイル名）
        self.track_metas = []         # [{game,song,author,dur_sec}] per track
        self.track_count = 1
        self.cur_track   = 0
        self.ch_count    = SPC_CH_COUNT
        self.ch_names    = [str(i+1) for i in range(SPC_CH_COUNT)]
        self.ch_active   = [True] * SPC_CH_COUNT
        self.sr          = SPC_SR
        self._spc_raws   = {}         # {track_idx: bytes}
        # track_data: {track_idx: {
        #   'wav':         float32 mono array,
        #   'ch_used':     list[bool],
        #   'ch_mask':     int,
        #   'decoded_sec': float,
        # }}
        self.track_data  = {}


class NsfState:
    """NSFファイルの状態とデコード済みデータを保持する"""
    def __init__(self):
        self.path          = ""
        self.fmt           = ""       # "NESM" or "NSFe"
        self.game          = ""       # ゲームタイトル（ファイル全体）
        self.author        = ""
        self.track_count   = 0
        self.track_titles  = []       # NSFe: 曲ごとのタイトル list[str]
        self.cur_track     = 0
        self.ch_count      = 0
        self.ch_names      = []       # チャンネル名 list[str]
        self.ch_active        = []    # チャンネルON/OFF list[bool]
        self.expansion_chips  = []    # 拡張音源チップ名 list[str] 例: ["FDS"]
        self.sr            = NSF_SR
        self._nsf_raw      = None     # NSFファイルの生バイト（延長デコード用）
        # track_data: {track_idx: {
        #   'wav':         float32 mono array,  # ch_maskで1パスレンダリングしたPCM
        #   'ch_used':     list[bool],           # 各chが音を出すか（グレーアウト判定）
        #   'ch_mask':     int,                  # wavを生成したチャンネルビットマスク
        #   'decoded_sec': float,                # wavの長さ（秒）
        #   'view_sec':    float,                # 現在の表示/再生範囲（秒）
        #   'natural_end': bool,                 # 自然終了したか
        # }}
        self.track_data    = {}


# ════════════════════════════════════════
# AudioEngine
# ════════════════════════════════════════
import time as _time
def _log(msg):
    """操作ログをコンソールとファイルに出力"""
    ts = _time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if APP_VERSION.endswith('.0'):  # リリースビルドはファイルログ不要
        return
    try:
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "morokoshi.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


class AudioEngine:
    def __init__(self):
        self.data=None; self.sr=44100; self._file_hash=None
        self._proc=None; self._proc_spd=1.0; self._proc_semi=0
        self.position=0; self.playing=False; self.paused=False
        self._feeder_eof=False
        self._nsf=None   # NsfState or None
        self._spc=None   # SpcState or None
        self.volume=1.0; self.speed=1.0; self.semitones=0; self.fine_semi=0.0
        self.ab_active=False; self.ear_active=False; self.markers={}
        self._stream=None; self._lock=threading.Lock()
        self._stop=threading.Event(); self._tmp=tempfile.mkdtemp()
        self.on_tick=None; self._gen=0; self._mem=ConvCache()
        # リアルタイム再生用
        self._out_buf=np.zeros((0,2),dtype=np.float32)  # 出力待ちリングバッファ
        self._src_pos=0          # 原曲サンプル位置（次に変換すべき先頭）
        self._played_orig=0      # 実際に出力した分の原曲サンプル数（現在位置の真実）
        self._rt_lock=threading.Lock()
        self._rt_gen=0           # speed/key変更時に先読みを破棄するための世代
        # スペクトラムアナライザー用: 直近にスピーカーへ出力した音声(モノラル)のスナップショット
        self._vis_latest=np.zeros(2048,dtype=np.float32)
        # フィルター(HPF/LPF)用: 通過域のバンド範囲とフィルタ状態
        self.filter_lo_idx=0
        self.filter_hi_idx=len(FILTER_BANDS_HZ)-1
        self._filter_zi=None
        self._filter_sos_cache_key=None
        self._filter_sos_cache=None

    def _key(self,spd,semi): return (round(spd,2),semi)

    def load(self, path, scb=None):
        lower = path.lower()
        if lower.endswith('.nsf'):
            self._spc = None
            return self._load_nsf(path, scb)
        if lower.endswith('.spc'):
            self._nsf = None
            return self._load_spc(path, scb)
        if lower.endswith('.zip'):
            self._nsf = None
            return self._load_spc_zip(path, scb)
        self._nsf = None
        self._spc = None
        wav, fh = get_wav_cache(path)
        if not wav:
            if scb: scb("Converting...")
            wtmp = os.path.join(self._tmp,"src.wav")
            ffmpeg_path = _ensure_ffmpeg(scb=scb)
            cmd = [ffmpeg_path,"-y","-i",path,"-ar","44100","-ac","2","-sample_fmt","s16",wtmp]
            try:
                _cf = subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0
                r = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=_cf)
                if r.returncode != 0: raise RuntimeError(r.stderr.decode(errors="replace")[-400:])
            except FileNotFoundError:
                raise RuntimeError("ffmpeg not found (try re-opening the file)")
            wav = set_wav_cache(path, wtmp, fh)
        if scb: scb("Loading...")
        data, sr = sf.read(wav, dtype="float32", always_2d=True)
        with self._lock:
            self.data=data; self.sr=sr; self._file_hash=fh
            self._proc=data; self._proc_spd=1.0; self._proc_semi=0
            self.speed=1.0; self.semitones=0; self.fine_semi=0.0
            self.position=0; self._src_pos=0; self.markers={}; self.ab_active=False; self.ear_active=False
            self._out_buf=np.zeros((0,2),dtype=np.float32)
            self._mem=ConvCache()
            self.filter_lo_idx=0; self.filter_hi_idx=len(FILTER_BANDS_HZ)-1
            self._filter_zi=None; self._filter_sos_cache_key=None; self._filter_sos_cache=None
        threading.Thread(target=purge_old_cache, daemon=True).start()
        if scb: scb("Done")
        return len(data)/sr

    # ── NSF専用メソッド ───────────────────────────────────────────
    def _load_nsf(self, path, scb=None):
        """NSFファイルをlibgmeで読み込む"""
        gme = _gme_load()
        if gme is None:
            raise RuntimeError("libgme.dll not found")
        if scb: scb("Loading NSF...")
        with open(path, 'rb') as _f:
            _nsf_raw = _f.read()
        _nsf_raw = _nsf_pad_banks(_nsf_raw)     # pad incomplete trailing bank
        _nsf_raw = _nsf_fix_low_load(_nsf_raw)  # fix LOAD < 0x8000 via trampoline
        # メタデータ取得用の一時emu
        _nsf_buf = _ct.create_string_buffer(_nsf_raw, len(_nsf_raw))
        emu = _ct.c_void_p()
        err = gme.gme_open_data(_nsf_buf, len(_nsf_raw), _ct.byref(emu), NSF_SR)
        if err is not None:
            raise RuntimeError(f"NSF load error: {err.decode(errors='replace')}")
        try:
            track_count = gme.gme_track_count(emu)
            ch_count    = gme.gme_voice_count(emu)
            ch_names    = [gme.gme_voice_name(emu, i).decode(errors='replace')
                           for i in range(ch_count)]
            fmt = _nsf_fmt(path) or 'NESM'
            game_title = ""; author = ""; track_titles = []
            for ti in range(track_count):
                info_p = _ct.c_void_p()
                if gme.gme_track_info(emu, _ct.byref(info_p), ti) is None:
                    try:
                        info = _ct.cast(info_p, _ct.POINTER(_GmeInfo)).contents
                        if ti == 0:
                            game_title = (info.game   or b"").decode(errors='replace').strip()
                            author     = (info.author or b"").decode(errors='replace').strip()
                        track_titles.append((info.song or b"").decode(errors='replace').strip())
                    finally:
                        gme.gme_free_info(info_p)
                else:
                    track_titles.append("")
        finally:
            gme.gme_delete(emu)

        nsf = NsfState()
        nsf.path = path; nsf.fmt = fmt; nsf.game = game_title
        nsf.author = author; nsf.track_count = track_count
        nsf.track_titles = track_titles; nsf.ch_count = ch_count
        nsf.ch_names = ch_names; nsf.cur_track = 0
        nsf.ch_active = [True] * ch_count
        nsf._nsf_raw = _nsf_raw
        nsf.expansion_chips = _nsf_chip_names(_nsf_raw, fmt)

        # トラック0をデコード（ch判定→1パスレンダリング）
        if scb: scb("NSF: ch detection...")
        ch_used = _nsf_detect_ch_used(gme, _nsf_raw, 0, ch_count, scb=scb)
        ch_mask = sum((1 << i) for i in range(ch_count) if ch_used[i])
        if ch_mask == 0:
            _log("NSF ch_mask=0: fallback to all-ch render to verify")
            _all_mask = (1 << ch_count) - 1
            _test_wav, _, _ = _nsf_render(gme, _nsf_raw, 0, _all_mask, ch_count, dur_sec=3.0)
            if float(np.max(np.abs(_test_wav))) > NSF_SILENCE_THRESH:
                ch_used = [True] * ch_count; ch_mask = _all_mask
                _log(f"NSF fallback: ch_mask={ch_mask:#b} (all used)")
            else:
                _log("NSF fallback: truly silent, ch_mask remains 0")
        if scb: scb("NSF: rendering track 1...")
        wav, natural_end, actual_dur = _nsf_render(gme, _nsf_raw, 0, ch_mask, ch_count,
                                                   NSF_DEFAULT_DUR_SEC, scb)
        nsf.track_data[0] = {
            'wav': wav, 'ch_used': ch_used, 'ch_mask': ch_mask,
            'decoded_sec': actual_dur, 'view_sec': actual_dur,
            'natural_end': natural_end,
        }
        nsf.ch_active = list(ch_used)

        with self._lock:
            self._nsf = nsf
        dur = self._nsf_mix_apply()
        fh = _fhash(path)
        with self._lock:
            self._file_hash = fh
            self.speed = 1.0; self.semitones = 0; self.fine_semi = 0.0
            self.position = 0; self._src_pos = 0
            self.markers = {}; self.ab_active = False; self.ear_active = False
            self._mem = ConvCache()
            self.filter_lo_idx = 0; self.filter_hi_idx = len(FILTER_BANDS_HZ) - 1
            self._filter_zi = None; self._filter_sos_cache_key = None; self._filter_sos_cache = None
        threading.Thread(target=purge_old_cache, daemon=True).start()
        if scb: scb("Done")
        return dur

    def _nsf_mix_apply(self, cur_sec=None):
        """現在のwavをengine.dataに設定する。戻り値: 長さ(sec)"""
        nsf = self._nsf
        if nsf is None or nsf.cur_track not in nsf.track_data:
            return 0.0
        td = nsf.track_data[nsf.cur_track]
        wav = td.get('wav')
        if wav is None or len(wav) == 0:
            return 0.0
        raw_len = len(wav)
        view_s = int(td.get('view_sec', raw_len / nsf.sr) * nsf.sr)
        view_s = max(1, min(view_s, raw_len))
        mixed = np.clip(wav[:view_s], -1.0, 1.0).astype(np.float32)
        stereo = np.stack([mixed, mixed], axis=1).astype(np.float32)
        dur = len(stereo) / nsf.sr
        with self._lock:
            self.data = stereo; self.sr = nsf.sr
            self._proc = stereo; self._proc_spd = 1.0; self._proc_semi = 0
            if cur_sec is not None:
                self.position = max(0, min(int(cur_sec * nsf.sr), len(stereo) - 1))
                self._out_buf = np.zeros((0, 2), dtype=np.float32)
            else:
                self.position = max(0, min(self.position, len(stereo) - 1))
        return dur

    def _nsf_toggle_channel(self, ch_idx, solo=False, reset=False):
        """NSFチャンネルのON/OFFを切り替える。戻り値: 新しいch_mask（再レンダリング用）"""
        nsf = self._nsf
        if nsf is None or ch_idx >= nsf.ch_count: return 0
        td = nsf.track_data.get(nsf.cur_track)
        if td is None: return 0
        ch_used = td['ch_used']
        if reset:
            for i in range(nsf.ch_count): nsf.ch_active[i] = ch_used[i]
        elif solo:
            only_this = (ch_used[ch_idx] and nsf.ch_active[ch_idx] and
                         all(not nsf.ch_active[i]
                             for i in range(nsf.ch_count) if ch_used[i] and i != ch_idx))
            if only_this:
                for i in range(nsf.ch_count): nsf.ch_active[i] = ch_used[i]
            else:
                for i in range(nsf.ch_count): nsf.ch_active[i] = (i == ch_idx and ch_used[i])
        else:
            if ch_used[ch_idx]: nsf.ch_active[ch_idx] = not nsf.ch_active[ch_idx]
        self._mem = ConvCache()
        return sum((1 << i) for i in range(nsf.ch_count)
                   if i < len(nsf.ch_active) and nsf.ch_active[i] and
                   i < len(ch_used) and ch_used[i])

    def _nsf_apply_new_wav(self, wav, ch_mask):
        """ch切替レンダリング完了後、wavをホットスワップする（再生位置保持）"""
        nsf = self._nsf
        if nsf is None or nsf.cur_track not in nsf.track_data: return
        td = nsf.track_data[nsf.cur_track]
        td['wav'] = wav; td['ch_mask'] = ch_mask
        td['decoded_sec'] = len(wav) / nsf.sr
        raw_len = len(wav)
        view_s = int(td.get('view_sec', raw_len / nsf.sr) * nsf.sr)
        view_s = max(1, min(view_s, raw_len))
        mixed = np.clip(wav[:view_s], -1.0, 1.0).astype(np.float32)
        stereo = np.stack([mixed, mixed], axis=1).astype(np.float32)
        cur_sec = self.current_sec()
        new_pos = max(0, min(int(cur_sec * nsf.sr), len(stereo) - 1))
        with self._lock:
            self.data = stereo; self.sr = nsf.sr
            self._proc = stereo; self._proc_spd = 1.0; self._proc_semi = 0
            self.position = new_pos
        with self._rt_lock:
            self._rt_gen += 1
            self._src_pos = new_pos
            self._played_orig = new_pos
            _fo_len = min(len(self._out_buf), 2048)
            if _fo_len > 0:
                _fo = np.linspace(1.0, 0.0, _fo_len, dtype=np.float32)[:, np.newaxis]
                self._out_buf[:_fo_len] *= _fo
                self._out_buf = self._out_buf[:_fo_len].copy()
            else:
                self._out_buf = np.zeros((0, 2), dtype=np.float32)
            self._feeder_eof = False

    def nsf_set_track(self, track_idx, scb=None):
        """NSFトラックを切り替える。必要に応じてデコードする。戻り値: 長さ(sec)"""
        nsf = self._nsf
        if nsf is None or track_idx < 0 or track_idx >= nsf.track_count: return 0.0

        # 切替前のトラック状態をセッションとして保存
        old_track = nsf.cur_track
        if old_track in nsf.track_data:
            _pend_old = getattr(nsf, '_pending_track_sessions', {})
            if old_track in _pend_old:
                # File-load pre-set session takes priority over stale live state
                nsf.track_data[old_track]['session'] = _pend_old.pop(old_track)
            else:
                nsf.track_data[old_track]['session'] = {
                    'position':  self.current_sec(),
                    'markers':   dict(self.markers),
                    'ch_active': list(nsf.ch_active),
                    'ab_active': self.ab_active,
                    'ear_active': self.ear_active,
                }

        nsf.cur_track = track_idx
        if track_idx not in nsf.track_data:
            if nsf._nsf_raw is None: return 0.0
            gme = _gme_load()
            if gme is None: return 0.0
            if scb: scb(f"NSF: ch detection track {track_idx+1}...")
            ch_used = _nsf_detect_ch_used(gme, nsf._nsf_raw, track_idx, nsf.ch_count, scb=scb)
            ch_mask = sum((1 << i) for i in range(nsf.ch_count) if i < len(ch_used) and ch_used[i])
            if ch_mask == 0:
                _log("NSF ch_mask=0: fallback to all-ch render to verify")
                _all_mask = (1 << nsf.ch_count) - 1
                _test_wav, _, _ = _nsf_render(gme, nsf._nsf_raw, track_idx, _all_mask, nsf.ch_count, dur_sec=3.0)
                if float(np.max(np.abs(_test_wav))) > NSF_SILENCE_THRESH:
                    ch_used = [True] * nsf.ch_count; ch_mask = _all_mask
                    _log(f"NSF fallback: ch_mask={ch_mask:#b} (all used)")
                else:
                    _log("NSF fallback: truly silent, ch_mask remains 0")
            if scb: scb(f"NSF: rendering track {track_idx+1}...")
            wav, natural_end, actual_dur = _nsf_render(gme, nsf._nsf_raw, track_idx, ch_mask,
                                                       nsf.ch_count, NSF_DEFAULT_DUR_SEC, scb)
            nsf.track_data[track_idx] = {
                'wav': wav, 'ch_used': ch_used, 'ch_mask': ch_mask,
                'decoded_sec': actual_dur, 'view_sec': actual_dur,
                'natural_end': natural_end,
            }
            # Inject pending session from file load (ch_active, position, markers, etc.)
            _pend = getattr(nsf, '_pending_track_sessions', {})
            if track_idx in _pend:
                nsf.track_data[track_idx]['session'] = _pend.pop(track_idx)

        td = nsf.track_data[track_idx]
        session = td.get('session')
        if session:
            nsf.ch_active  = list(session.get('ch_active', td['ch_used']))
            # Keys are stringified in JSON; convert back to int so all marker checks work
            self.markers   = {int(k): float(v) for k, v in session.get('markers', {}).items()}
            self.ab_active = bool(session.get('ab_active', False))
            self.ear_active = bool(session.get('ear_active', False))
            restore_pos    = float(session.get('position', 0.0))
        else:
            nsf.ch_active  = list(td['ch_used'])
            self.markers   = {}
            self.ab_active = False
            self.ear_active = False
            restore_pos    = 0.0

        # セッション復元時: wavのch_maskとch_activeが異なれば再レンダリング
        target_ch_mask = sum((1 << i) for i in range(nsf.ch_count)
                             if i < len(nsf.ch_active) and nsf.ch_active[i] and
                             i < len(td['ch_used']) and td['ch_used'][i])
        if target_ch_mask != td.get('ch_mask', -1) and nsf._nsf_raw is not None:
            gme2 = _gme_load()
            if gme2 is not None:
                if scb: scb(f"NSF: re-rendering with session channels...")
                new_wav, new_nat, new_dur = _nsf_render(gme2, nsf._nsf_raw, track_idx,
                                                        target_ch_mask, nsf.ch_count,
                                                        td.get('decoded_sec', NSF_DEFAULT_DUR_SEC), scb)
                td['wav'] = new_wav; td['ch_mask'] = target_ch_mask
                td['decoded_sec'] = new_dur; td['view_sec'] = new_dur
                td['natural_end'] = new_nat

        self.stop()
        self._mem = ConvCache()
        dur = self._nsf_mix_apply(cur_sec=restore_pos)
        with self._rt_lock:
            data_len = len(self.data) if self.data is not None else 0
            restore_s = max(0, min(int(restore_pos * nsf.sr), data_len - 1))
            self._src_pos    = restore_s
            self._played_orig = restore_s
        return dur

    def nsf_extend_track(self, track_idx, new_view_sec, scb=None):
        """NSFトラックの再生時間を変更する。戻り値: (dur, natural_end)"""
        nsf = self._nsf
        if nsf is None or track_idx not in nsf.track_data: return 0.0, True
        td = nsf.track_data[track_idx]
        decoded_sec = td.get('decoded_sec', 0.0)
        natural_end = td.get('natural_end', True)
        min_dur = NSF_MIN_DURATION if natural_end else 60.0
        new_view_sec = max(min_dur, min(new_view_sec, NSF_MAX_DUR_SEC))

        if new_view_sec <= decoded_sec:
            # 短縮/既存範囲内: view_secを更新するだけ
            td['view_sec'] = new_view_sec
            dur = self._nsf_mix_apply()
            with self._rt_lock:
                new_len = len(self.data) if self.data is not None else 1
                # Keep only the valid pre-buffered portion (up to new end)
                spd = self.speed if self.speed > 0 else 1.0
                buf_keep = max(0, int((new_len - self._played_orig) / spd))
                if len(self._out_buf) > buf_keep:
                    self._out_buf = self._out_buf[:buf_keep]
                # Allow feeder to hit EOF naturally at new_len
                self._src_pos = min(self._src_pos, new_len)
                self._rt_gen += 1   # discard in-flight stale chunk, wake EOF wait loop
                self._feeder_eof = False
            return dur, natural_end

        # 延長が必要
        if natural_end:
            return self._nsf_mix_apply(), True

        if nsf._nsf_raw is None: return self._nsf_mix_apply(), False
        gme = _gme_load()
        if gme is None: return self._nsf_mix_apply(), False

        ch_mask = td.get('ch_mask', (1 << nsf.ch_count) - 1)
        if scb: scb(f"NSF: rendering {decoded_sec:.0f}s→{new_view_sec:.0f}s...")
        new_wav, new_natural_end, new_actual_dur = _nsf_render(
            gme, nsf._nsf_raw, track_idx, ch_mask, nsf.ch_count, new_view_sec, scb)

        td['wav']         = new_wav
        td['decoded_sec'] = new_actual_dur
        td['view_sec']    = new_view_sec
        td['natural_end'] = new_natural_end
        self._mem = ConvCache()
        dur = self._nsf_mix_apply()
        return dur, new_natural_end

    # ── SPC専用メソッド ───────────────────────────────────────────
    def _load_spc(self, path, scb=None):
        """単体SPCファイルをlibgmeで読み込む"""
        gme = _gme_load()
        if gme is None:
            raise RuntimeError("libgme.dll not found")
        if scb: scb("Loading SPC...")
        with open(path, 'rb') as _f:
            spc_raw = _f.read()
        meta = _spc_get_meta(gme, spc_raw)
        if scb: scb("SPC: detecting channels...")
        ch_used = _spc_detect_ch_used(gme, spc_raw, scb=scb)
        ch_mask = sum((1 << i) for i in range(SPC_CH_COUNT) if ch_used[i])
        if ch_mask == 0:
            ch_used = [True] * SPC_CH_COUNT
            ch_mask = (1 << SPC_CH_COUNT) - 1
        if scb: scb("SPC: rendering...")
        wav, natural_end, actual_dur = _spc_render(
            gme, spc_raw, ch_mask, meta['dur_sec'], scb, play_len_ms=meta.get('play_len_ms', 0))
        spc = SpcState()
        spc.path = path
        spc.is_zip = False
        spc.spc_names = [os.path.basename(path)]
        spc.track_metas = [meta]
        spc.track_count = 1
        spc.cur_track = 0
        spc.ch_active = list(ch_used)
        spc._spc_raws = {0: spc_raw}
        spc.track_data[0] = {
            'wav': wav, 'ch_used': ch_used, 'ch_mask': ch_mask, 'decoded_sec': actual_dur,
        }
        with self._lock:
            self._spc = spc
        dur = self._spc_mix_apply()
        fh = _fhash(path)
        with self._lock:
            self._file_hash = fh
            self.speed = 1.0; self.semitones = 0; self.fine_semi = 0.0
            self.position = 0; self._src_pos = 0
            self.markers = {}; self.ab_active = False; self.ear_active = False
            self._mem = ConvCache()
            self.filter_lo_idx = 0; self.filter_hi_idx = len(FILTER_BANDS_HZ) - 1
            self._filter_zi = None; self._filter_sos_cache_key = None; self._filter_sos_cache = None
        threading.Thread(target=purge_old_cache, daemon=True).start()
        if scb: scb("Done")
        return dur

    def _load_spc_zip(self, path, scb=None):
        """ZIPファイル内のSPCを読み込む（ASCII順で並べてtrackとして管理）"""
        import zipfile
        if not zipfile.is_zipfile(path):
            raise RuntimeError("Not a valid ZIP file")
        gme = _gme_load()
        if gme is None:
            raise RuntimeError("libgme.dll not found")
        if scb: scb("Loading ZIP...")
        with zipfile.ZipFile(path, 'r') as zf:
            all_names = sorted([n for n in zf.namelist() if n.lower().endswith('.spc')])
            if not all_names:
                raise RuntimeError("No SPC files found in ZIP")
            spc_raws_list = []
            for n in all_names:
                spc_raws_list.append(zf.read(n))
        track_count = len(all_names)
        display_names = [os.path.basename(n) for n in all_names]
        # メタデータ取得（全trackのヘッダーを読む）
        if scb: scb("SPC: reading metadata...")
        track_metas = []
        for i, raw in enumerate(spc_raws_list):
            m = _spc_get_meta(gme, raw)
            track_metas.append(m)
        # track 0 をデコード
        if scb: scb("SPC: detecting channels (track 1)...")
        ch_used = _spc_detect_ch_used(gme, spc_raws_list[0], scb=scb)
        ch_mask = sum((1 << i) for i in range(SPC_CH_COUNT) if ch_used[i])
        if ch_mask == 0:
            ch_used = [True] * SPC_CH_COUNT
            ch_mask = (1 << SPC_CH_COUNT) - 1
        if scb: scb("SPC: rendering track 1...")
        wav, natural_end, actual_dur = _spc_render(
            gme, spc_raws_list[0], ch_mask, track_metas[0]['dur_sec'], scb,
            play_len_ms=track_metas[0].get('play_len_ms', 0))
        spc = SpcState()
        spc.path = path
        spc.is_zip = True
        spc.spc_names = display_names
        spc.track_metas = track_metas
        spc.track_count = track_count
        spc.cur_track = 0
        spc.ch_active = list(ch_used)
        spc._spc_raws = {i: raw for i, raw in enumerate(spc_raws_list)}
        spc.track_data[0] = {
            'wav': wav, 'ch_used': ch_used, 'ch_mask': ch_mask, 'decoded_sec': actual_dur,
        }
        with self._lock:
            self._spc = spc
        dur = self._spc_mix_apply()
        fh = _fhash(path)
        with self._lock:
            self._file_hash = fh
            self.speed = 1.0; self.semitones = 0; self.fine_semi = 0.0
            self.position = 0; self._src_pos = 0
            self.markers = {}; self.ab_active = False; self.ear_active = False
            self._mem = ConvCache()
            self.filter_lo_idx = 0; self.filter_hi_idx = len(FILTER_BANDS_HZ) - 1
            self._filter_zi = None; self._filter_sos_cache_key = None; self._filter_sos_cache = None
        threading.Thread(target=purge_old_cache, daemon=True).start()
        if scb: scb("Done")
        return dur

    def _spc_mix_apply(self, cur_sec=None):
        """現在のSPC wavをengine.dataに設定する。戻り値: 長さ(sec)"""
        spc = self._spc
        if spc is None or spc.cur_track not in spc.track_data:
            return 0.0
        td = spc.track_data[spc.cur_track]
        wav = td.get('wav')
        if wav is None or len(wav) == 0:
            return 0.0
        mixed = np.clip(wav, -1.0, 1.0).astype(np.float32)
        stereo = np.stack([mixed, mixed], axis=1).astype(np.float32)
        dur = len(stereo) / spc.sr
        with self._lock:
            self.data = stereo; self.sr = spc.sr
            self._proc = stereo; self._proc_spd = 1.0; self._proc_semi = 0
            if cur_sec is not None:
                self.position = max(0, min(int(cur_sec * spc.sr), len(stereo) - 1))
            else:
                self.position = 0
            self._out_buf = np.zeros((0, 2), dtype=np.float32)
        return dur

    def _spc_toggle_channel(self, ch_idx, solo=False, reset=False):
        """SPCチャンネルのON/OFFを切り替える。戻り値: 新しいch_mask"""
        spc = self._spc
        if spc is None or ch_idx >= spc.ch_count: return 0
        td = spc.track_data.get(spc.cur_track)
        if td is None: return 0
        ch_used = td['ch_used']
        if reset:
            for i in range(spc.ch_count): spc.ch_active[i] = ch_used[i]
        elif solo:
            only_this = (ch_used[ch_idx] and spc.ch_active[ch_idx] and
                         all(not spc.ch_active[i]
                             for i in range(spc.ch_count) if ch_used[i] and i != ch_idx))
            if only_this:
                for i in range(spc.ch_count): spc.ch_active[i] = ch_used[i]
            else:
                for i in range(spc.ch_count): spc.ch_active[i] = (i == ch_idx and ch_used[i])
        else:
            if ch_used[ch_idx]: spc.ch_active[ch_idx] = not spc.ch_active[ch_idx]
        self._mem = ConvCache()
        return sum((1 << i) for i in range(spc.ch_count)
                   if i < len(spc.ch_active) and spc.ch_active[i] and
                   i < len(ch_used) and ch_used[i])

    def _spc_apply_new_wav(self, wav, ch_mask):
        """SPC ch切替レンダリング完了後、wavをホットスワップする（再生位置保持）"""
        spc = self._spc
        if spc is None or spc.cur_track not in spc.track_data: return
        td = spc.track_data[spc.cur_track]
        td['wav'] = wav; td['ch_mask'] = ch_mask
        mixed = np.clip(wav, -1.0, 1.0).astype(np.float32)
        stereo = np.stack([mixed, mixed], axis=1).astype(np.float32)
        cur_sec = self.current_sec()
        new_pos = max(0, min(int(cur_sec * spc.sr), len(stereo) - 1))
        with self._lock:
            self.data = stereo; self.sr = spc.sr
            self._proc = stereo; self._proc_spd = 1.0; self._proc_semi = 0
            self.position = new_pos
        with self._rt_lock:
            self._rt_gen += 1
            self._src_pos = new_pos
            self._played_orig = new_pos
            _fo_len = min(len(self._out_buf), 2048)
            if _fo_len > 0:
                _fo = np.linspace(1.0, 0.0, _fo_len, dtype=np.float32)[:, np.newaxis]
                self._out_buf[:_fo_len] *= _fo
                self._out_buf = self._out_buf[:_fo_len].copy()
            else:
                self._out_buf = np.zeros((0, 2), dtype=np.float32)
            self._feeder_eof = False

    def spc_set_track(self, track_idx, scb=None):
        """SPCトラック(ZIP内)を切り替える。戻り値: 長さ(sec)"""
        spc = self._spc
        if spc is None or track_idx < 0 or track_idx >= spc.track_count: return 0.0

        # 切替前のトラック状態をセッションとして保存
        old_track = spc.cur_track
        if old_track in spc.track_data:
            spc.track_data[old_track]['session'] = {
                'position':   self.current_sec(),
                'markers':    dict(self.markers),
                'ch_active':  list(spc.ch_active),
                'ab_active':  self.ab_active,
                'ear_active': self.ear_active,
            }

        spc.cur_track = track_idx
        if track_idx not in spc.track_data:
            spc_raw = spc._spc_raws.get(track_idx)
            if spc_raw is None: return 0.0
            gme = _gme_load()
            if gme is None: return 0.0
            if scb: scb(f"SPC: detecting channels (track {track_idx+1})...")
            ch_used = _spc_detect_ch_used(gme, spc_raw, scb=scb)
            ch_mask = sum((1 << i) for i in range(SPC_CH_COUNT) if ch_used[i])
            if ch_mask == 0:
                ch_used = [True] * SPC_CH_COUNT
                ch_mask = (1 << SPC_CH_COUNT) - 1
            if scb: scb(f"SPC: rendering track {track_idx+1}...")
            meta_t = spc.track_metas[track_idx] if track_idx < len(spc.track_metas) else {}
            dur_sec = meta_t.get('dur_sec', SPC_DEFAULT_DUR_SEC)
            wav, natural_end, actual_dur = _spc_render(
                gme, spc_raw, ch_mask, dur_sec, scb, play_len_ms=meta_t.get('play_len_ms', 0))
            spc.track_data[track_idx] = {
                'wav': wav, 'ch_used': ch_used, 'ch_mask': ch_mask, 'decoded_sec': actual_dur,
            }

        td = spc.track_data[track_idx]
        session = td.get('session')
        if session:
            spc.ch_active   = list(session.get('ch_active', td['ch_used']))
            self.markers    = {int(k): float(v) for k, v in session.get('markers', {}).items()}
            self.ab_active  = bool(session.get('ab_active', False))
            self.ear_active = bool(session.get('ear_active', False))
            restore_pos     = float(session.get('position', 0.0))
        else:
            spc.ch_active   = list(td['ch_used'])
            self.markers    = {}
            self.ab_active  = False
            self.ear_active = False
            restore_pos     = 0.0

        # セッション復元時: ch_maskとch_activeが異なれば再レンダリング
        target_ch_mask = sum((1 << i) for i in range(SPC_CH_COUNT)
                             if i < len(spc.ch_active) and spc.ch_active[i] and
                             i < len(td['ch_used']) and td['ch_used'][i])
        if target_ch_mask != td.get('ch_mask', -1):
            spc_raw2 = spc._spc_raws.get(track_idx)
            gme2 = _gme_load()
            if spc_raw2 and gme2:
                if scb: scb(f"SPC: re-rendering with session channels...")
                meta_t2 = spc.track_metas[track_idx] if track_idx < len(spc.track_metas) else {}
                new_wav, _, new_dur = _spc_render(
                    gme2, spc_raw2, target_ch_mask,
                    meta_t2.get('dur_sec', SPC_DEFAULT_DUR_SEC), scb,
                    play_len_ms=meta_t2.get('play_len_ms', 0))
                td['wav'] = new_wav; td['ch_mask'] = target_ch_mask
                td['decoded_sec'] = new_dur

        self.stop()
        self._mem = ConvCache()
        dur = self._spc_mix_apply(cur_sec=restore_pos)
        with self._rt_lock:
            data_len = len(self.data) if self.data is not None else 0
            restore_s = max(0, min(int(restore_pos * spc.sr), data_len - 1))
            self._src_pos     = restore_s
            self._played_orig = restore_s
        return dur

    def _request_conv(self, spd, semi, scb, fast=False, resume=True):
        if self.data is None: return
        self._gen+=1; gen=self._gen
        cur_sec = self.current_sec()
        if spd==1.0 and semi==0:
            self._apply_proc(self.data,1.0,0,cur_sec,resume=resume)
            if scb: scb(f"Speed×{spd:.1f} Key{semi:+d}"); return
        k = self._key(spd,semi)
        cached = self._mem.get(k)
        if cached is not None:
            self._apply_proc(cached,spd,semi,cur_sec,resume=resume); return
        if self._file_hash:
            dc = get_conv_cache(self._file_hash, spd, semi)
            if dc:
                def load_dc():
                    try:
                        d,_ = sf.read(dc, dtype="float32", always_2d=True)
                        if self._gen!=gen: return
                        self._mem.put(k,d)
                        self._apply_proc(d,spd,semi,cur_sec,resume=resume)
                        if scb: scb(f"Speed×{spd:.1f} Key{semi:+d}")
                    except: threading.Thread(target=self._do_conv,args=(spd,semi,cur_sec,gen,scb,fast,resume),daemon=True).start()
                threading.Thread(target=load_dc,daemon=True).start(); return
        threading.Thread(target=self._do_conv,args=(spd,semi,cur_sec,gen,scb,fast,resume),daemon=True).start()

    def _do_conv(self, spd, semi, cur_sec, gen, scb, fast, resume=True):
        k = self._key(spd,semi)
        try:
            if scb: scb("Converting...")
            mono = self.data.mean(axis=1).astype(np.float32)
            if spd!=1.0 or semi!=0:
                mono = _fast_stretch(mono, self.sr, spd, semi)
            proc = np.stack([mono,mono],axis=1).astype(np.float32)
            if self._gen!=gen: return
            self._mem.put(k,proc)
            if self._file_hash:
                threading.Thread(target=set_conv_cache,args=(self._file_hash,spd,semi,proc,self.sr),daemon=True).start()
            self._apply_proc(proc,spd,semi,cur_sec,resume=resume)
            if scb: scb(f"Speed×{spd:.1f} Key{semi:+d}")
        except Exception as e:
            if scb: scb(f"Convert error: {e}")

    def _apply_proc(self, proc, spd, semi, cur_sec, resume=True):
        new_pos = max(0, min(int(cur_sec*spd*self.sr), len(proc)-1))
        was = self.playing
        self.stop()
        with self._lock:
            self._proc=proc; self._proc_spd=spd; self._proc_semi=semi; self.position=new_pos
        if was and resume: self.play()

    def set_speed(self, v, scb=None):
        self.speed = round(max(0.5,min(2.0, round(v/0.1)*0.1)),1)
        self._rt_reset_from_current()
        if scb: scb(f"Speed×{self.speed:.1f} Key{self.semitones:+d}")

    def set_semitones(self, v, scb=None):
        self.semitones = max(-24,min(24,int(v)))
        self._rt_reset_from_current()
        if scb: scb(f"Speed×{self.speed:.1f} Key{self.semitones:+d}")

    def set_fine_semi(self, v, scb=None):
        self.fine_semi = round(max(-1.0,min(1.0, float(v))),2)
        self._rt_reset_from_current()
        if scb: scb(f"Speed×{self.speed:.1f} Key{self.semitones:+d} Fine{self.fine_semi:+.2f}")

    def _rt_reset_from_current(self):
        """speed/key変更時: 現在位置から先読みを作り直す"""
        if self.data is None: return
        with self._rt_lock:
            self._rt_gen += 1
            self._src_pos=max(0, min(int(self._played_orig), len(self.data)-1))
            self._out_buf=np.zeros((0,2),dtype=np.float32)
            self._feeder_eof=False  # 改めて読み直すので、EOF確定状態は解除する

    def rt_marker_changed(self):
        """ループ中にA/Bマーカーが変わった時: 先読みを現在位置から作り直す"""
        if self.data is None: return
        if not self.playing: return
        if not (self.ab_active or self.ear_active): return
        with self._rt_lock:
            self._rt_gen += 1
            self._src_pos=max(0, min(int(self._played_orig), len(self.data)-1))
            self._out_buf=np.zeros((0,2),dtype=np.float32)
            self._feeder_eof=False

    def _make_chunk(self, src_pos, out_frames, spd, semi):
        """原曲のsrc_posから、出力out_framesに必要な分を変換して返す。
        戻り値: (出力データ(out_frames,2), 消費した原曲サンプル数)
        ※ フィルター(HPF/LPF)はここでは適用しない（先読みバッファに入る前段）。
        　 cb()内で出力直前にかけることで、操作への反応を速くする。"""
        # 標準時は変換せず原曲そのまま（EOF付近ではゼロパディングせず実データ分だけ返す）
        if abs(spd-1.0)<1e-6 and abs(semi)<1e-9:
            end=min(src_pos+out_frames, len(self.data))
            consumed=end-src_pos
            if consumed<=0:
                return np.zeros((0,2),dtype=np.float32), 0
            return self.data[src_pos:end].copy(), consumed
        # 変換あり: 出力out_framesに必要な原曲サンプル数 ≒ out_frames*spd
        need=int(out_frames*spd)+1
        end=min(src_pos+need, len(self.data))
        src=self.data[src_pos:end]
        if len(src)==0:
            return np.zeros((0,2),dtype=np.float32), 0
        mono=src.mean(axis=1).astype(np.float32)
        conv=_fast_stretch(mono, self.sr, spd, semi)
        m=min(out_frames, len(conv))
        out=np.zeros((m,2),dtype=np.float32)
        out[:,0]=conv[:m]; out[:,1]=conv[:m]
        return out, (end-src_pos)

    def _filter_process(self, stereo_chunk):
        """選択中の帯域に応じたHPF/LPF(各-24dB/Oct)を適用する。
        全域選択(フィルター無し)の時は何もせず素通し（負荷・誤差を避ける）"""
        if stereo_chunk.shape[0]==0:
            return stereo_chunk
        lo=self.filter_lo_idx; hi=self.filter_hi_idx
        key=(lo,hi)
        if key!=self._filter_sos_cache_key:
            sr=self.sr if self.sr else 44100
            self._filter_sos_cache=_build_filter_sos(lo,hi,sr)
            self._filter_sos_cache_key=key
        sos=self._filter_sos_cache
        if sos is None:
            return stereo_chunk
        nch=stereo_chunk.shape[1] if stereo_chunk.ndim>1 else 1
        if (self._filter_zi is None) or (self._filter_zi.shape[0]!=sos.shape[0]) or (self._filter_zi.shape[2]!=nch):
            self._filter_zi=np.zeros((sos.shape[0],2,nch),dtype=np.float64)
        filtered,self._filter_zi=_sosfilt(sos, stereo_chunk.astype(np.float64), axis=0, zi=self._filter_zi)
        return filtered.astype(np.float32)

    def set_filter_range(self, lo_idx, hi_idx):
        n=len(FILTER_BANDS_HZ)
        lo_idx=max(0,min(n-1,int(lo_idx))); hi_idx=max(0,min(n-1,int(hi_idx)))
        if lo_idx>hi_idx: lo_idx,hi_idx=hi_idx,lo_idx
        self.filter_lo_idx=lo_idx; self.filter_hi_idx=hi_idx

    def reset_filter(self):
        self.filter_lo_idx=0; self.filter_hi_idx=len(FILTER_BANDS_HZ)-1
        self._filter_zi=None
        self._filter_sos_cache_key=None; self._filter_sos_cache=None

    def play(self, seek_sec=None):
        _log(f"Engine.play: seek_sec={seek_sec} src_pos={self._src_pos} playing={self.playing}")
        self.stop()
        if self.data is None: return
        if seek_sec is not None:
            self._src_pos = int(seek_sec*self.sr)
        self._src_pos = max(0, min(self._src_pos, len(self.data)-1))
        self._played_orig = self._src_pos  # 現在位置の基点（原曲サンプル）
        with self._rt_lock:
            self._rt_gen += 1   # 旧フィーダーが生き残っていても書き込みを無効化
            self._play_gen = getattr(self, '_play_gen', 0) + 1  # play()専用gen（seekでは変化しない）
            self._out_buf=np.zeros((0,2),dtype=np.float32)
        self.playing=True; self.paused=False; self._stop.clear()
        self._feeder_eof=False  # 先読みが原曲末尾まで読み終えたかどうか

        def cb(outdata, frames, t, st):
            if not self.playing or self.paused:
                outdata[:]=0
                self._vis_latest=np.zeros(frames,dtype=np.float32)
                return
            spd=self.speed if self.speed>0 else 1.0
            with self._rt_lock:
                if len(self._out_buf)>=frames:
                    seg=self._out_buf[:frames]
                    self._out_buf=self._out_buf[frames:]
                    seg=self._filter_process(seg)
                    outdata[:]=seg*self.volume
                    self._played_orig += int(frames*spd)
                else:
                    n=len(self._out_buf)
                    seg=self._filter_process(self._out_buf)
                    outdata[:n]=seg*self.volume
                    outdata[n:]=0
                    self._out_buf=np.zeros((0,2),dtype=np.float32)
                    self._played_orig += int(n*spd)
                    if self._feeder_eof:
                        # 先読みが原曲末尾まで読み終え、バッファも使い切った→ここで初めて再生終了
                        self.playing=False
            # スペクトラムアナライザー用に、実際に出力した音声(モノラル)を保存
            self._vis_latest=outdata[:,0].copy()
            if (self.ab_active or self.ear_active):
                aA=self.markers.get(MARKER_A); aB=self.markers.get(MARKER_B)
                if aA is not None and aB is not None:
                    lo,hi=sorted([aA,aB])
                    if self._played_orig >= int(hi*self.sr) or self._played_orig < int(lo*self.sr):
                        self._played_orig = int(lo*self.sr)

        # 先読みスレッド: out_bufに先のチャンクを供給
        def feeder():
            my_play_gen = self._play_gen  # play()専用gen（seekでは変化しないのでseekでfeederが終了しない）
            CHUNK=int(self.sr*10.0)  # 10秒の出力チャンク（継ぎ目を減らす）
            while not self._stop.is_set() and self.playing:
                # 新しいplay()が呼ばれた場合は旧feederを即終了（seekでは終了しない）
                if self._play_gen != my_play_gen:
                    break
                if self.paused:
                    time.sleep(0.02); continue
                try:
                    with self._rt_lock:
                        buffered=len(self._out_buf)
                    # 15秒分まで先読み
                    if buffered < int(self.sr*15.0):
                        spd=self.speed if self.speed>0 else 1.0
                        semi=self.semitones + self.fine_semi  # Key(半音)+Fine(微調整,小数)を合算
                        chunk_frames=CHUNK
                        with self._rt_lock:
                            gen=self._rt_gen
                            # AB/Earループ判定（原曲秒）
                            if (self.ab_active or self.ear_active):
                                aA=self.markers.get(MARKER_A); aB=self.markers.get(MARKER_B)
                                if aA is not None and aB is not None:
                                    lo,hi=sorted([aA,aB])
                                    hi_s=int(hi*self.sr); lo_s=int(lo*self.sr)
                                    if self._src_pos >= hi_s or self._src_pos < lo_s:
                                        self._src_pos=lo_s
                                    remain=hi_s - self._src_pos
                                    if remain>0:
                                        chunk_frames=min(CHUNK, int(remain/spd)+1)
                            start_pos=self._src_pos
                        out,consumed=self._make_chunk(start_pos, chunk_frames, spd, semi)
                        if consumed<=0:
                            # 原曲末尾に達した。EOFフラグをセットしてseek待機ループへ
                            with self._rt_lock:
                                if gen==self._rt_gen:
                                    self._feeder_eof=True
                            # EOF後: seekによりrt_genが変わるまで待機（10ms間隔）
                            # seekされたらEOFフラグをリセットして外側ループで再スタート
                            while (not self._stop.is_set() and
                                   self.playing and
                                   self._play_gen==my_play_gen):
                                time.sleep(0.01)
                                with self._rt_lock:
                                    if self._rt_gen!=gen:
                                        self._feeder_eof=False  # seek検出→EOFリセット
                                        break
                            continue  # 外側ループへ（seek時はbreak→continue、stop/play時はwhile条件で自然終了）
                        with self._rt_lock:
                            if gen==self._rt_gen:
                                self._out_buf=np.concatenate([self._out_buf, out], axis=0)
                                self._src_pos = start_pos + consumed
                            # gen不一致（seek済み）の場合はこのチャンクを捨てて次のループへ
                            # （feederは終了しない: seekはplay_genを変えないため）
                    else:
                        time.sleep(0.01)
                except Exception as ex:
                    # 先読み中の予期しない例外でスレッドが落ちて無音になるのを防ぐ。
                    # ログに残して少し待ってから次のループへ（再生自体は止めない）
                    _log(f"feeder error: {ex}")
                    time.sleep(0.05)

        self._stream = sd.OutputStream(samplerate=self.sr,channels=2,dtype="float32",blocksize=2048,callback=cb)
        self._stream.start()
        threading.Thread(target=feeder,daemon=True).start()
        def mon():
            while not self._stop.is_set():
                if self.on_tick: self.on_tick(self.current_sec(), self.total_sec())
                time.sleep(0.05)
        threading.Thread(target=mon,daemon=True).start()

    def pause_toggle(self):
        self.paused=not self.paused
        _log(f"Engine.pause_toggle: paused={self.paused}")
    def stop(self):
        _log(f"Engine.stop: playing={self.playing} position={self.position}")
        self._stop.set(); self.playing=False
        self._feeder_eof=False
        self._vis_latest=np.zeros(2048,dtype=np.float32)
        self._filter_zi=None
        if self._stream:
            try: self._stream.stop(); self._stream.close()
            except: pass
            self._stream=None

    def seek(self, sec):
        if self.data is None:
            _log(f"Engine.seek: data is None, skip (sec={sec})")
            return
        p=int(max(0.0,min(sec,self.total_sec()))*self.sr)
        p=min(p, max(0, len(self.data)-1))  # 末尾境界外アクセス防止（EOF直後のflash対策）
        _log(f"Engine.seek: sec={sec:.3f} -> src_pos={p}")
        with self._rt_lock:
            self._rt_gen += 1   # 旧先読みを無効化（シーク直後の再生バグ対策）
            self._src_pos=p
            self._played_orig=p
            self._out_buf=np.zeros((0,2),dtype=np.float32)  # シーク前の古いバッファを破棄
            self._feeder_eof=False  # lock内でリセット（callbackとのrace防止）

    def current_sec(self):
        if self.data is None: return 0.0
        # 実際に出力した原曲サンプル数 = 現在聞こえている位置（x1.0基準の秒）
        return max(0.0, self._played_orig/self.sr)

    def total_sec(self):
        return len(self.data)/self.sr if self.data is not None else 0.0

    def set_marker(self, n):
        self.markers[n]=self.current_sec()

    def goto_marker(self, n):
        if n in self.markers: self.seek(self.markers[n])

    def estimate_tempo(self, center_sec=None, window=10.0):
        if self.data is None: return None
        if center_sec is None: center_sec=self.current_sec()
        lo=max(0.0,center_sec-window/2); hi=min(self.total_sec(),center_sec+window/2)
        seg=self.data[int(lo*self.sr):int(hi*self.sr)].mean(axis=1)
        if len(seg)<self.sr: return None
        try:
            return _estimate_bpm(seg, self.sr)
        except: return None

    def get_waveform(self, width=700):
        if self.data is None: return None
        mono=self.data.mean(axis=1); n=len(mono)
        chunk=max(1,n//width)
        peaks=np.array([np.abs(mono[i*chunk:min((i+1)*chunk,n)]).max() for i in range(width)],dtype=np.float32)
        mx=peaks.max()
        if mx>0: peaks/=mx
        return peaks

    def get_spectrum(self):
        """直近に出力した音声(self._vis_latest)をFFT解析し、SPECTRUM_BANDS_HZ各帯域の
        レベル(0.0〜1.0)を返す。スペクトラムアナライザー表示用。"""
        bands=SPECTRUM_BANDS_HZ; edges=SPECTRUM_BAND_EDGES
        num_bands=len(bands)
        buf=self._vis_latest
        n=len(buf) if buf is not None else 0
        if n<64:
            return np.zeros(num_bands, dtype=np.float32)
        sr=self.sr if self.sr else 44100
        win=np.hanning(n).astype(np.float32)
        n_fft=max(8192, 1<<int(np.ceil(np.log2(n))))  # ゼロパディングで帯域分解能を補間
        mag=np.abs(np.fft.rfft(buf*win, n=n_fft))
        freqs=np.fft.rfftfreq(n_fft, d=1.0/sr)
        norm=2.0/n  # FFTマグニチュード → 振幅(0〜1相当)へのおおよその正規化
        nyq=sr/2.0
        levels=np.zeros(num_bands, dtype=np.float32)
        for i in range(num_bands):
            lo=edges[i]; hi=min(edges[i+1], nyq)
            if hi<=lo: continue
            idx=np.where((freqs>=lo)&(freqs<hi))[0]
            if len(idx)==0:
                j=int(np.argmin(np.abs(freqs-(lo*hi)**0.5)))
                amp=mag[j]*norm
            else:
                amp=mag[idx].max()*norm
            db=20.0*np.log10(amp+1e-6)
            lvl=(db+54.0)/48.0  # -54dB(無音側)〜-6dB(大音量側)を 0.0〜1.0 にマッピング
            levels[i]=max(0.0, min(1.0, lvl))
        return levels


# 波形ウィジェット
# ════════════════════════════════════════
class WaveformWidget(QWidget):
    seeked = pyqtSignal(float)
    view_changed = pyqtSignal()  # ズーム/スクロール時に発火
    ab_drag = pyqtSignal(float)  # AB範囲ドラッグ時、移動量(全体比率)を発火
    double_clicked = pyqtSignal(float)  # ダブルクリック位置(全体比率)を発火
    marker_reset_requested = pyqtSignal(int)  # マーカーの真上をダブルクリック→そのマーカー番号(MARKER_A or MARKER_B)
    seek_revert = pyqtSignal(float)  # ダブルクリック確定時、1回目クリックによるシークを取り消すための復元先比率
    position_drag = pyqtSignal(float)  # 現在位置線ドラッグ中、ライブの比率を発火（確定シークはseekedで行う）
    marker_drag = pyqtSignal(int, float)  # A/Bマーカー線ドラッグ中、(マーカー番号, ライブの比率)を発火
    def __init__(self, parent=None):
        super().__init__(parent)
        self.waveform=None; self.position=0.0
        self._ab_a=None; self._ab_b=None
        self._marker_hit_tol_px=8  # ダブルクリックでマーカーとみなす許容範囲(px)。外部からself.S()込みで上書きされる
        self.setFixedHeight(42); self._dragging=False
        self._drag_mode=None; self._press_x=0; self._press_view=None
        self._press_on_ab=False; self._press_r=0.0
        self._pre_click_pos=0.0       # クリック列開始時点の再生位置比率（ダブルクリック確定時の復元用）
        self._last_press_time=0.0     # シングル/ダブルクリック列の判定用
        self._suppress_next_release_seek=False  # ダブルクリック確定後、2回目releaseのシークを抑制するフラグ
        self._view_lo=0.0; self._view_hi=1.0  # 表示範囲（全体に対する比率）
        self._total=0.0
        self._last_manual=0.0  # 最後に手動でズーム/スクロールした時刻
        self._is_playing=False  # 再生中フラグ（拡大方針の切替用）
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def set_total(self, total): self._total=total

    def reset_view(self):
        self._view_lo=0.0; self._view_hi=1.0; self.update(); self.view_changed.emit()

    def align_view_for_play(self):
        # 再生開始時: 現在位置が表示範囲の80%より右なら、80%地点に合わせてから再生
        span=self._vspan()
        if span >= 1.0: return
        trig = self._view_lo + span*0.8
        _log(f"align_view_for_play: pos={self.position:.4f} view=[{self._view_lo:.4f},{self._view_hi:.4f}] trig={trig:.4f}")
        if self.position > trig:
            lo = self.position - span*0.8
            if lo < 0: lo = 0
            hi = lo + span
            if hi > 1: hi = 1; lo = 1-span
            self._view_lo=lo; self._view_hi=hi
            self._last_manual=0.0  # 追従抑制を解除（すぐ追従できるよう）
            _log(f"align_view_for_play -> view=[{lo:.4f},{hi:.4f}]")
            self.update(); self.view_changed.emit()

    def _vspan(self):
        return max(1e-6, self._view_hi-self._view_lo)

    def set_waveform(self, peaks): self.waveform=peaks; self.update()
    def set_position(self, ratio, follow=False):
        self.position=max(0.0,min(1.0,ratio))
        self._is_playing=follow
        span=self._vspan()
        # 再生中(follow=True)かつズーム中、かつ手動操作から3秒以上経過した時のみ追従
        if follow and span < 1.0 and (time.time()-self._last_manual) > 3.0:
            # 再生位置が表示範囲の80%地点を超えたら、80%地点に保つようスクロール
            trig = self._view_lo + span*0.8
            if self.position > trig:
                lo = self.position - span*0.8
                if lo < 0: lo = 0
                hi = lo + span
                if hi > 1: hi = 1; lo = 1-span
                self._view_lo=lo; self._view_hi=hi
                self.view_changed.emit()
            elif self.position < self._view_lo:
                # 巻き戻し等で左に出た場合は左端に合わせる
                lo = self.position
                hi = lo + span
                if hi > 1: hi = 1; lo = 1-span
                self._view_lo=lo; self._view_hi=hi
                self.view_changed.emit()
        self.update()
    def set_ab(self, a, b, total):
        self._ab_a = a/total if (a is not None and total>0) else None
        self._ab_b = b/total if (b is not None and total>0) else None
        self.update()

    def _r2x(self, r, w):
        return (r - self._view_lo) / self._vspan() * w
    def _x2r(self, x, w):
        return self._view_lo + (x / max(1,w)) * self._vspan()

    def paintEvent(self, e):
        p = QPainter(self)
        w=self.width(); h=self.height()
        p.fillRect(0,0,w,h, QColor(BG2))
        wf=self.waveform
        if wf is None: p.end(); return
        n=len(wf); cy=h/2
        lo=self._view_lo; span=self._vspan()
        px=self._r2x(self.position, w)
        i0=max(0, int(lo*n)-1); i1=min(n, int(self._view_hi*n)+2)
        idxs_all=list(range(i0,i1))
        if idxs_all:
            path_pre=QPainterPath()
            x0=(idxs_all[0]/n - lo)/span*w
            path_pre.moveTo(x0,cy)
            for i in idxs_all:
                x=(i/n - lo)/span*w
                path_pre.lineTo(x, cy-wf[i]*(cy-4))
            for i in reversed(idxs_all):
                x=(i/n - lo)/span*w
                path_pre.lineTo(x, cy+wf[i]*(cy-4))
            path_pre.closeSubpath(); p.fillPath(path_pre, QColor(ACC2))
        if px>0:
            # 再生済み領域: 全波形を明るい色で描き、px までをクリップ表示（滑らかに追従）
            p.save()
            p.setClipRect(0,0,int(px)+1,h)
            path_pl=QPainterPath()
            x0=(idxs_all[0]/n - lo)/span*w
            path_pl.moveTo(x0,cy)
            for i in idxs_all:
                x=(i/n - lo)/span*w
                path_pl.lineTo(x, cy-wf[i]*(cy-4))
            for i in reversed(idxs_all):
                x=(i/n - lo)/span*w
                path_pl.lineTo(x, cy+wf[i]*(cy-4))
            path_pl.closeSubpath(); p.fillPath(path_pl, QColor(ACC))
            p.restore()
        if self._ab_a is not None and self._ab_b is not None:
            xa=int(self._r2x(min(self._ab_a,self._ab_b), w))
            xb=int(self._r2x(max(self._ab_a,self._ab_b), w))
            p.fillRect(xa,0,xb-xa,h, QColor(255,255,0,30))
            p.setPen(QPen(QColor(255,200,0,180),1))
            p.drawLine(xa,0,xa,h); p.drawLine(xb,0,xb,h)
        elif self._ab_a is not None or self._ab_b is not None:
            xx=int(self._r2x(self._ab_a if self._ab_a is not None else self._ab_b, w))
            p.setPen(QPen(QColor(255,200,0,180),1))
            p.drawLine(xx,0,xx,h)
        if 0<=px<=w:
            p.setPen(QPen(QColor(FG),1))
            p.drawLine(int(px),0,int(px),h)
        p.end()

    def _seek(self, e):
        r=self._x2r(e.position().x(), self.width())
        self.seeked.emit(max(0.0,min(1.0,r)))

    def mousePressEvent(self,e):
        hide_tt()
        focused = QApplication.focusWidget()
        if focused is not None: focused.clearFocus()
        w=self.window()
        if w: w.setFocus()
        if e.button()==Qt.MouseButton.LeftButton:
            self._dragging=True
            self._press_x=e.position().x()
            self._press_view=(self._view_lo, self._view_hi)
            self._drag_mode=None  # まだクリックかドラッグか不明
            # ダブルクリック確定後に残ったフラグが次のクリック列に持ち込まれないよう、念のためここでクリア
            self._suppress_next_release_seek=False
            # ダブルクリック列の1回目のpressでだけ、確定前の再生位置を記録しておく
            # （2回目のpressはdoubleClickInterval内に来るので、その時は上書きしない）
            now=time.time()
            if (now-self._last_press_time) > (QApplication.doubleClickInterval()/1000.0):
                self._pre_click_pos=self.position
            self._last_press_time=now
            # 押した位置がA〜B間（黄色部分）かを判定
            self._press_on_ab=False
            if self._ab_a is not None and self._ab_b is not None:
                r=self._x2r(self._press_x, max(1,self.width()))
                lo=min(self._ab_a,self._ab_b); hi=max(self._ab_a,self._ab_b)
                if lo<=r<=hi:
                    self._press_on_ab=True
            self._press_r=self._x2r(self._press_x, max(1,self.width()))
            # 現在位置線・A線・B線のいずれかの直上を掴んでいるか判定（帯ドラッグより優先）
            w=max(1,self.width())
            cands=[("pos", abs(self._r2x(self.position,w)-self._press_x))]
            if self._ab_a is not None:
                cands.append(("a", abs(self._r2x(self._ab_a,w)-self._press_x)))
            if self._ab_b is not None:
                cands.append(("b", abs(self._r2x(self._ab_b,w)-self._press_x)))
            in_tol=[c for c in cands if c[1]<=self._marker_hit_tol_px]
            self._grab_target = min(in_tol, key=lambda c:c[1])[0] if in_tol else None

    def mouseMoveEvent(self,e):
        if not self._dragging: return
        dx=e.position().x()-self._press_x
        if self._drag_mode is None and abs(dx)>5:
            # 優先順位: 現在位置線・マーカー線の直上 > AB黄色帯 > 通常ドラッグ
            if self._grab_target=="pos":
                self._drag_mode="pos_move"
            elif self._grab_target=="a":
                self._drag_mode="marker_a_move"
            elif self._grab_target=="b":
                self._drag_mode="marker_b_move"
            else:
                self._drag_mode="ab_move" if self._press_on_ab else "drag"
        if self._drag_mode=="ab_move":
            # 現在のマウス比率とpress時比率の差分だけABを移動
            cur_r=self._x2r(e.position().x(), max(1,self.width()))
            delta=cur_r-self._press_r
            self._press_r=cur_r  # 差分方式（累積）
            self.ab_drag.emit(delta)
        elif self._drag_mode=="pos_move":
            r=max(0.0,min(1.0,self._x2r(e.position().x(), max(1,self.width()))))
            self.position=r  # 見た目はすぐ追従させる
            self.update()
            self.position_drag.emit(r)
        elif self._drag_mode=="marker_a_move":
            r=max(0.0,min(1.0,self._x2r(e.position().x(), max(1,self.width()))))
            self.marker_drag.emit(MARKER_A, r)
        elif self._drag_mode=="marker_b_move":
            r=max(0.0,min(1.0,self._x2r(e.position().x(), max(1,self.width()))))
            self.marker_drag.emit(MARKER_B, r)
        # 通常ドラッグ(scroll)は廃止

    def mouseReleaseEvent(self,e):
        if self._dragging and self._drag_mode is None:
            if self._suppress_next_release_seek:
                # ダブルクリック確定済み：2回目クリックのreleaseによる再シークを抑制
                self._suppress_next_release_seek=False
            else:
                # 動いていない → クリック＝シーク
                self._seek(e)
        elif self._drag_mode=="pos_move":
            # ドラッグ確定: 最終位置へ実際にシークする
            r=max(0.0,min(1.0,self._x2r(e.position().x(), max(1,self.width()))))
            self.seeked.emit(r)
        self._dragging=False; self._drag_mode=None

    def mouseDoubleClickEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            # ダブルクリック確定: 1回目クリックによるシークを取り消し、2回目releaseのシークも抑制する
            # （ダブルクリックは「マーカー操作」であり、「再生位置の移動」ではない、という仕様）
            self._suppress_next_release_seek=True
            self.seek_revert.emit(self._pre_click_pos)
            w=max(1,self.width())
            x=e.position().x()
            # マーカー(A/B)の真上(許容範囲px以内)なら、マーカー設置よりリセットを優先する。
            # 両方が範囲内に入っていれば、より近い側だけをリセット対象にする。
            cands=[]
            if self._ab_a is not None:
                cands.append((MARKER_A, abs(self._r2x(self._ab_a, w)-x)))
            if self._ab_b is not None:
                cands.append((MARKER_B, abs(self._r2x(self._ab_b, w)-x)))
            in_tol=[c for c in cands if c[1]<=self._marker_hit_tol_px]
            if in_tol:
                target=min(in_tol, key=lambda c:c[1])[0]
                self.marker_reset_requested.emit(target)
                return
            r=self._x2r(x, w)
            self.double_clicked.emit(max(0.0,min(1.0,r)))

    def wheelEvent(self,e):
        w=max(1,self.width())
        delta=e.angleDelta().y()
        if delta==0: return
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Shift+ホイール → 横スクロール
            span=self._vspan()
            step=span*0.15*(1 if delta<0 else -1)
            lo=self._view_lo+step; hi=self._view_hi+step
            if lo<0: hi-=lo; lo=0
            if hi>1: lo-=(hi-1); hi=1
            self._view_lo=max(0.0,lo); self._view_hi=min(1.0,hi)
        else:
            # ホイール → カーソル位置中心にズーム
            cursor_r=self._x2r(e.position().x(), w)
            span=self._vspan()
            factor=0.85 if delta>0 else (1/0.85)  # 上で拡大
            new_span=max(0.005, min(1.0, span*factor))
            # カーソル位置の比率を保つ
            frac=(cursor_r-self._view_lo)/span
            lo=cursor_r-frac*new_span
            hi=lo+new_span
            if lo<0: lo=0; hi=new_span
            if hi>1: hi=1; lo=1-new_span
            self._view_lo=max(0.0,lo); self._view_hi=min(1.0,hi)
            # 再生中のみ: 再生位置が表示範囲外に出たら含むようスライド補正
            if self._is_playing:
                pos=self.position
                sp=self._view_hi-self._view_lo
                if pos < self._view_lo:
                    self._view_lo=max(0.0, pos); self._view_hi=self._view_lo+sp
                elif pos > self._view_hi:
                    self._view_hi=min(1.0, pos); self._view_lo=self._view_hi-sp
        self._last_manual=time.time()
        self.update(); self.view_changed.emit()

# ════════════════════════════════════════
# NSF専用パネル (スペアナエリアの代替)
# ════════════════════════════════════════
_NSF_CH_LABELS_JIS = ["1","2","3","4","5","6","7","8","9","0","-","^","¥"]  # ¥
_NSF_CH_LABELS_US  = ["1","2","3","4","5","6","7","8","9","0","-","=","\\"]

def _nsf_ch_labels():
    """JIS/USキーボードを自動判別してチャンネルラベルリストを返す"""
    try:
        import ctypes as _ct2
        hkl = _ct2.windll.user32.GetKeyboardLayout(0)
        if (hkl & 0xFFFF) == 0x0411:  # 0x0411 = 日本語(JIS)
            return _NSF_CH_LABELS_JIS
    except Exception:
        pass
    return _NSF_CH_LABELS_US

class NsfChButton(QPushButton):
    """チャンネルON/OFFトグルボタン"""
    right_clicked = pyqtSignal()
    def __init__(self, label, scale=1.0, parent=None):
        super().__init__(parent)
        self.setText(label); self._scale=scale
        self._on=True; self._used=True
        sz=max(16, int(round(20*scale)))
        self.setFixedSize(sz, sz)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _attach_tt(self, f"Channel ON/OFF [{label}]\nRight-click: Solo")
        # Suppress tooltip when channel is grayed-out (not used)
        _orig_enter = self.enterEvent
        _orig_leave = self.leaveEvent
        def _cond_enter(e, ww=self):
            if ww._used: _orig_enter(e)
        def _cond_leave(e, ww=self):
            if ww._used: _orig_leave(e)
        self.enterEvent = _cond_enter
        self.leaveEvent = _cond_leave
        self._refresh_style()
    def set_state(self, on, used):
        self._on=on; self._used=used
        self.setEnabled(True)   # 常に有効（グレーアウトはスタイルのみ）
        self._refresh_style()
    def _refresh_style(self):
        fs=max(6, int(round(10*self._scale)))
        if not self._used:
            st=(f"QPushButton{{color:{FG2}; background:{BG}; border:1px solid {BORDER};"
                f"border-radius:2px; font-size:{fs}px; padding:0;}}")
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif self._on:
            st=(f"QPushButton{{color:#FFD700; background:{BG3}; border:1px solid #FFD700;"
                f"border-radius:2px; font-size:{fs}px; padding:0;}}"
                f"QPushButton:hover{{border:1px solid #FFFF00;}}"
                f"QPushButton:pressed{{background:{BG2};}}")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            st=(f"QPushButton{{color:{FG2}; background:{BG2}; border:1px solid {BORDER};"
                f"border-radius:2px; font-size:{fs}px; padding:0;}}"
                f"QPushButton:hover{{border:1px solid {FG2};}}"
                f"QPushButton:pressed{{color:#FFD700;}}")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(st)
    def mousePressEvent(self, e):
        if not self._used:
            return
        if e.button()==Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        else:
            super().mousePressEvent(e)


class _NsfMarquee(QWidget):
    """長いテキストを横スクロール表示するラベル"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text=""; self._offset=0; self._delay=0
        self._timer=QTimer(self); self._timer.timeout.connect(self._tick)
    def setText(self, t):
        self._text=t; self._offset=0; self._delay=0
        self._timer.stop(); self.update()
        fm=self.fontMetrics()
        if fm.horizontalAdvance(t)>self.width():
            self._timer.start(50)
    def _tick(self):
        if self._delay<20: self._delay+=1; return
        fm=self.fontMetrics(); tw=fm.horizontalAdvance(self._text)
        if tw<=self.width(): self._timer.stop(); self._offset=0
        else:
            gap=fm.horizontalAdvance("     ")
            self._offset+=2
            if self._offset>=tw+gap: self._offset=0
        self.update()
    def paintEvent(self, e):
        p=QPainter(self); p.fillRect(0,0,self.width(),self.height(),QColor(BG))
        if not self._text: p.end(); return
        p.setPen(QColor(FG)); p.setClipRect(0,0,self.width(),self.height())
        fm=p.fontMetrics()
        y=(self.height()+fm.ascent()-fm.descent())//2
        tw=fm.horizontalAdvance(self._text)
        p.drawText(-self._offset, y, self._text)
        if tw>self.width():
            gap=fm.horizontalAdvance("     ")
            p.drawText(-self._offset+tw+gap, y, self._text)
        p.end()
    def resizeEvent(self, e):
        super().resizeEvent(e)
        fm=self.fontMetrics()
        if fm.horizontalAdvance(self._text)>self.width():
            if not self._timer.isActive(): self._timer.start(50)
        else:
            self._timer.stop(); self._offset=0


class NsfPanel(QWidget):
    """NSFモード専用表示パネル（スペアナエリアの代わりに配置）"""
    track_changed    = pyqtSignal(int)        # 0-based track index
    channel_toggled  = pyqtSignal(int, bool, bool)  # ch_idx, solo, reset

    def __init__(self, scale=1.0, parent=None):
        super().__init__(parent)
        self._scale=scale; self._total=1; self._cur=0; self._ch_btns=[]
        self._drag_y0=0; self._drag_base=0; self._dragging=False
        self._wheel_timer=QTimer(self); self._wheel_timer.setSingleShot(True)
        self._wheel_timer.timeout.connect(self._emit_track_changed)
        self._build()

    def S(self, px): return int(round(px*self._scale))

    def _build(self):
        lo=QVBoxLayout(self); lo.setContentsMargins(self.S(4),self.S(2),self.S(4),self.S(1)); lo.setSpacing(self.S(1))
        # 上行: 曲番号 / 総数 + タイトル
        r1=QWidget(); r1.setFixedHeight(self.S(24))
        r1lo=QHBoxLayout(r1); r1lo.setContentsMargins(0,0,0,0); r1lo.setSpacing(self.S(2))
        _nav_style = (
            f"QPushButton{{color:{FG};background:{BG3};border:1px solid {BORDER};"
            f"border-radius:3px;font-size:{self.S(12)}px;padding:0;}}"
            f"QPushButton:hover{{background:{BG2};border:1px solid {FG2};}}"
            f"QPushButton:pressed{{color:#FFD700;border:1px solid #FFD700;}}"
            f"QPushButton:disabled{{color:{FG2};background:{BG3};border:1px solid {BORDER};}}"
        )
        self._track_prev_btn = QPushButton("<")
        self._track_prev_btn.setFixedSize(self.S(11), self.S(22))
        self._track_prev_btn.setStyleSheet(_nav_style)
        self._track_prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _attach_tt(self._track_prev_btn, "Previous track\nKey: [,] or Shift+← / Shift+[,]: ×10")
        self._track_prev_btn.clicked.connect(self._on_prev_track)
        r1lo.addWidget(self._track_prev_btn)
        self._track_edit=QLineEdit("001")
        self._track_edit.setFixedWidth(self.S(36)); self._track_edit.setFixedHeight(self.S(22))
        self._track_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_edit.setReadOnly(True)
        self._track_edit.setCursor(Qt.CursorShape.SizeVerCursor)
        _attach_tt(self._track_edit, "Track number\nDrag up/down or Wheel to change\n2-Click: Edit")
        self._track_edit.setStyleSheet(
            f"QLineEdit{{color:{FG};background:{BG3};border:1px solid {BORDER};padding:0 2px;}}"
            f"QLineEdit:hover{{border:1px solid {FG2};}}"
            f"QLineEdit:focus{{border:1px solid {ACC};}}")
        self._track_edit.returnPressed.connect(self._commit_track)
        self._track_edit.editingFinished.connect(self._commit_track)
        self._track_edit.mouseDoubleClickEvent=lambda e: self._start_edit()
        self._track_edit.wheelEvent=self._track_wheel
        self._track_edit.mousePressEvent=self._track_press
        self._track_edit.leaveEvent=self._track_leave
        self._track_edit.mouseMoveEvent=self._track_move
        self._track_edit.mouseReleaseEvent=self._track_release
        r1lo.addWidget(self._track_edit)
        self._track_next_btn = QPushButton(">")
        self._track_next_btn.setFixedSize(self.S(11), self.S(22))
        self._track_next_btn.setStyleSheet(_nav_style)
        self._track_next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _attach_tt(self._track_next_btn, "Next track\nKey: [.] or Shift+→ / Shift+[.]: ×10")
        self._track_next_btn.clicked.connect(self._on_next_track)
        r1lo.addWidget(self._track_next_btn)
        self._total_lbl=QLabel("/001"); self._total_lbl.setFixedWidth(self.S(46))
        self._total_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._total_lbl.setStyleSheet(f"color:{FG2};background:{BG};")
        _attach_tt(self._total_lbl, "Total tracks")
        r1lo.addWidget(self._total_lbl)
        _sp=QLabel(" "); _sp.setFixedWidth(self.S(4)); _sp.setStyleSheet(f"background:{BG};"); r1lo.addWidget(_sp)
        self._title=_NsfMarquee(); self._title.setStyleSheet(f"background:{BG};")
        _attach_tt(self._title, "NSF title")
        r1lo.addWidget(self._title, 1); lo.addWidget(r1)
        # 下行: チャンネルボタン
        self._ch_row=QWidget(); self._ch_row.setFixedHeight(self.S(24))
        self._ch_row_lo=QHBoxLayout(self._ch_row)
        self._ch_row_lo.setContentsMargins(0,0,0,0); self._ch_row_lo.setSpacing(self.S(2))
        self._ch_row_lo.addStretch(); lo.addWidget(self._ch_row)
        self.setStyleSheet(f"background:{BG};")

    def _start_edit(self):
        self._track_edit.setCursor(Qt.CursorShape.IBeamCursor)
        self._track_edit.setReadOnly(False); self._track_edit.selectAll()

    def _commit_track(self):
        self._track_edit.setReadOnly(True)
        self._track_edit.setCursor(Qt.CursorShape.SizeVerCursor)
        try:
            v=max(1, min(self._total, int(self._track_edit.text())))
            if v-1!=self._cur: self.track_changed.emit(v-1)
        except ValueError: pass
        self._track_edit.setText(f"{self._cur+1:03d}")

    # ── 楽曲番号ドラッグ ───────────────────────
    def _track_press(self, e):
        if not self._track_edit.isReadOnly():
            from PyQt6.QtWidgets import QLineEdit as _QLE
            _QLE.mousePressEvent(self._track_edit, e); return
        if e.button()==Qt.MouseButton.LeftButton:
            self._drag_y0=e.position().y(); self._drag_base=self._cur; self._dragging=False

    def _track_move(self, e):
        if not self._track_edit.isReadOnly(): return
        if not (e.buttons() & Qt.MouseButton.LeftButton): return
        dy = self._drag_y0 - e.position().y()  # 上=正=インクリメント
        if abs(dy) < 4: return
        self._dragging = True
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        steps = int(dy / 10) * (10 if shift else 1)
        v = max(0, min(self._total - 1, self._drag_base + steps))
        if v != self._cur:
            self._cur = v
            self._track_edit.setText(f"{v+1:03d}")
            self._wheel_timer.start(300)

    def _track_release(self, e):
        if not self._track_edit.isReadOnly():
            from PyQt6.QtWidgets import QLineEdit as _QLE
            _QLE.mouseReleaseEvent(self._track_edit, e); return
        # ドラッグ完了後はメインウィンドウにフォーカスを戻す
        top = self.window()
        if top: top.setFocus()

    def _track_leave(self, e):
        # マウスがウィジェット外に出たらメインウィンドウにフォーカスを戻す
        if self._track_edit.isReadOnly():
            top = self.window()
            if top: top.setFocus()

    def _track_wheel(self, e):
        if not self._track_edit.isReadOnly(): return
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        step = 10 if shift else 1
        delta = e.angleDelta().y()
        v = self._cur + (step if delta > 0 else -step)
        v = max(0, min(self._total - 1, v))
        if v != self._cur:
            self._cur = v
            self._track_edit.setText(f"{v+1:03d}")
            self._wheel_timer.start(300)

    def _emit_track_changed(self):
        self.track_changed.emit(self._cur)

    def _on_prev_track(self):
        step = 10 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        v = max(0, self._cur - step)
        if v != self._cur:
            self._cur = v
            self._track_edit.setText(f"{v+1:03d}")
            self._update_nav_btns()
            self.track_changed.emit(self._cur)

    def _on_next_track(self):
        step = 10 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        v = min(self._total - 1, self._cur + step)
        if v != self._cur:
            self._cur = v
            self._track_edit.setText(f"{v+1:03d}")
            self._update_nav_btns()
            self.track_changed.emit(self._cur)

    def _update_nav_btns(self):
        self._track_prev_btn.setEnabled(self._cur > 0)
        self._track_next_btn.setEnabled(self._cur < self._total - 1)

    def set_info(self, total, cur_0, title):
        self._total=max(1,total); self._cur=cur_0
        self._total_lbl.setText(f"/{self._total:03d}")
        self._track_edit.setText(f"{self._cur+1:03d}")
        self._title.setText(title)
        self._update_nav_btns()

    def set_channels(self, count, names, active, used, expansion_chips=None):
        for b in self._ch_btns:
            self._ch_row_lo.removeWidget(b); b.deleteLater()
        self._ch_btns.clear()
        # stretchを一旦除去して再追加
        while self._ch_row_lo.count():
            item=self._ch_row_lo.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for i in range(count):
            if i==5:  # 基本5chと拡張音源の間に隙間
                sp=QWidget(); sp.setFixedWidth(self.S(6)); sp.setStyleSheet(f"background:{BG};")
                self._ch_row_lo.addWidget(sp)
            _lbls=_nsf_ch_labels()
            lbl=_lbls[i] if i<len(_lbls) else str(i+1)
            btn=NsfChButton(lbl, scale=self._scale, parent=self._ch_row)
            btn.set_state(active[i], used[i])
            btn.clicked.connect(lambda _=False, idx=i: self._on_click(idx))
            btn.right_clicked.connect(lambda idx=i: self.channel_toggled.emit(idx, False, True))
            self._ch_btns.append(btn); self._ch_row_lo.addWidget(btn)
        if expansion_chips:
            fs = max(6, int(round(9 * self._scale)))
            chip_lbl = QLabel(" ".join(expansion_chips))
            chip_lbl.setStyleSheet(
                f"color:{FG2};background:{BG};font-size:{fs}px;padding:0 3px;")
            self._ch_row_lo.addWidget(chip_lbl)
        self._ch_row_lo.addStretch()

    def _on_click(self, idx):
        shift=bool(QApplication.keyboardModifiers()&Qt.KeyboardModifier.ShiftModifier)
        # クリック→ソロ操作、Shift+クリック→個別ON/OFFトグル
        self.channel_toggled.emit(idx, not shift, False)

    def update_channel_states(self, active, used):
        for i, btn in enumerate(self._ch_btns):
            if i<len(active): btn.set_state(active[i], used[i])

    def update_track_num(self, cur_0):
        self._cur=cur_0
        self._track_edit.setText(f"{cur_0+1:03d}")
        self._update_nav_btns()

    def set_loading(self, loading: bool):
        """楽曲読み込み中はナビゲーションUIを無効化してグレーアウト"""
        self._track_prev_btn.setEnabled(not loading and self._cur > 0)
        self._track_next_btn.setEnabled(not loading and self._cur < self._total - 1)
        self._track_edit.setEnabled(not loading)
        for btn in self._ch_btns:
            btn.setEnabled(not loading)


# ════════════════════════════════════════
# SPCパネル（SPC / ZIP-SPC モード専用表示パネル）
# ════════════════════════════════════════
class SpcPanel(QWidget):
    """SPCモード専用表示パネル（スペアナエリアの代わりに配置）"""
    track_changed   = pyqtSignal(int)           # 0-based track index
    channel_toggled = pyqtSignal(int, bool, bool)  # ch_idx, solo, reset

    def __init__(self, scale=1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._ch_btns = []
        self._is_zip = False
        self._total = 1; self._cur = 0
        self._drag_y0 = 0; self._drag_base = 0; self._dragging = False
        self._spc_titles = []
        self._track_tt_text = "Track number\nDrag up/down or Wheel to change\n2-Click: Edit"
        self._wheel_timer = QTimer(self)
        self._wheel_timer.setSingleShot(True)
        self._wheel_timer.timeout.connect(self._emit_track_changed)
        self._build()

    def S(self, px): return int(round(px * self._scale))

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(self.S(4), self.S(2), self.S(4), self.S(1))
        lo.setSpacing(self.S(1))
        # Row 1: track navigation (zip mode のみ表示) + title
        r1 = QWidget(); r1.setFixedHeight(self.S(24))
        r1lo = QHBoxLayout(r1)
        r1lo.setContentsMargins(0, 0, 0, 0); r1lo.setSpacing(self.S(2))
        _nav_style = (
            f"QPushButton{{color:{FG};background:{BG3};border:1px solid {BORDER};"
            f"border-radius:3px;font-size:{self.S(12)}px;padding:0;}}"
            f"QPushButton:hover{{background:{BG2};border:1px solid {FG2};}}"
            f"QPushButton:pressed{{color:#FFD700;border:1px solid #FFD700;}}"
            f"QPushButton:disabled{{color:{FG2};background:{BG3};border:1px solid {BORDER};}}"
        )
        self._track_prev_btn = QPushButton("<")
        self._track_prev_btn.setFixedSize(self.S(11), self.S(22))
        self._track_prev_btn.setStyleSheet(_nav_style)
        self._track_prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _attach_tt(self._track_prev_btn, "Previous track\nKey: [,] or Shift+←")
        self._track_prev_btn.clicked.connect(self._on_prev_track)
        r1lo.addWidget(self._track_prev_btn)
        self._track_edit = QLineEdit("001")
        self._track_edit.setFixedWidth(self.S(36)); self._track_edit.setFixedHeight(self.S(22))
        self._track_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_edit.setReadOnly(True)
        self._track_edit.setCursor(Qt.CursorShape.SizeVerCursor)
        self._track_edit.setStyleSheet(
            f"QLineEdit{{color:{FG};background:{BG3};border:1px solid {BORDER};padding:0 2px;}}"
            f"QLineEdit:hover{{border:1px solid {FG2};}}"
            f"QLineEdit:focus{{border:1px solid {ACC};}}")
        self._track_edit.returnPressed.connect(self._commit_track)
        self._track_edit.editingFinished.connect(self._commit_track)
        self._track_edit.mouseDoubleClickEvent = lambda e: self._start_edit()
        self._track_edit.wheelEvent = self._track_wheel
        self._track_edit.mousePressEvent = self._track_press
        self._track_edit.leaveEvent = self._track_leave
        self._track_edit.enterEvent = lambda e, s=self: show_tt(s._track_tt_text, s._track_edit)
        self._track_edit.mouseMoveEvent = self._track_move
        self._track_edit.mouseReleaseEvent = self._track_release
        r1lo.addWidget(self._track_edit)
        self._track_next_btn = QPushButton(">")
        self._track_next_btn.setFixedSize(self.S(11), self.S(22))
        self._track_next_btn.setStyleSheet(_nav_style)
        self._track_next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _attach_tt(self._track_next_btn, "Next track\nKey: [.] or Shift+→")
        self._track_next_btn.clicked.connect(self._on_next_track)
        r1lo.addWidget(self._track_next_btn)
        self._total_lbl = QLabel("/001")
        self._total_lbl.setFixedWidth(self.S(46))
        self._total_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._total_lbl.setStyleSheet(f"color:{FG2};background:{BG};")
        _attach_tt(self._total_lbl, "Total tracks")
        r1lo.addWidget(self._total_lbl)
        # ナビ部品はまとめて管理（zip mode のみ可視）
        self._nav_widgets = [
            self._track_prev_btn, self._track_edit,
            self._track_next_btn, self._total_lbl,
        ]
        for w in self._nav_widgets:
            w.setVisible(False)
        _sp = QLabel(" "); _sp.setFixedWidth(self.S(4)); _sp.setStyleSheet(f"background:{BG};")
        r1lo.addWidget(_sp)
        self._title = _NsfMarquee(); self._title.setStyleSheet(f"background:{BG};")
        _attach_tt(self._title, "SPC title")
        r1lo.addWidget(self._title, 1)
        lo.addWidget(r1)
        # Row 2: channel buttons (常に8ch固定)
        self._ch_row = QWidget(); self._ch_row.setFixedHeight(self.S(24))
        self._ch_row_lo = QHBoxLayout(self._ch_row)
        self._ch_row_lo.setContentsMargins(0, 0, 0, 0); self._ch_row_lo.setSpacing(self.S(2))
        self._ch_row_lo.addStretch()
        lo.addWidget(self._ch_row)
        self.setStyleSheet(f"background:{BG};")

    def set_zip_mode(self, is_zip):
        self._is_zip = is_zip
        for w in self._nav_widgets:
            w.setVisible(is_zip)

    # ── トラックナビゲーション ──────────────────────
    def _start_edit(self):
        self._track_edit.setCursor(Qt.CursorShape.IBeamCursor)
        self._track_edit.setReadOnly(False); self._track_edit.selectAll()

    def _commit_track(self):
        self._track_edit.setReadOnly(True)
        self._track_edit.setCursor(Qt.CursorShape.SizeVerCursor)
        try:
            v = max(1, min(self._total, int(self._track_edit.text())))
            if v - 1 != self._cur: self.track_changed.emit(v - 1)
        except ValueError: pass
        self._track_edit.setText(f"{self._cur+1:03d}")

    def _track_press(self, e):
        if not self._track_edit.isReadOnly():
            from PyQt6.QtWidgets import QLineEdit as _QLE
            _QLE.mousePressEvent(self._track_edit, e); return
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_y0 = e.position().y(); self._drag_base = self._cur; self._dragging = False

    def _track_move(self, e):
        if not self._track_edit.isReadOnly(): return
        if not (e.buttons() & Qt.MouseButton.LeftButton): return
        dy = self._drag_y0 - e.position().y()
        if abs(dy) < 4: return
        self._dragging = True
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        steps = int(dy / 10) * (10 if shift else 1)
        v = max(0, min(self._total - 1, self._drag_base + steps))
        if v != self._cur:
            self._cur = v
            self._track_edit.setText(f"{v+1:03d}")
            self._update_track_tooltip()
            show_tt(self._track_tt_text, self._track_edit)
            self._wheel_timer.start(300)

    def _track_release(self, e):
        if not self._track_edit.isReadOnly():
            from PyQt6.QtWidgets import QLineEdit as _QLE
            _QLE.mouseReleaseEvent(self._track_edit, e); return
        top = self.window()
        if top: top.setFocus()

    def _track_leave(self, e):
        hide_tt()
        if self._track_edit.isReadOnly():
            top = self.window()
            if top: top.setFocus()

    def _track_wheel(self, e):
        if not self._track_edit.isReadOnly(): return
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        step = 10 if shift else 1
        delta = e.angleDelta().y()
        v = self._cur + (step if delta > 0 else -step)
        v = max(0, min(self._total - 1, v))
        if v != self._cur:
            self._cur = v
            self._track_edit.setText(f"{v+1:03d}")
            self._update_track_tooltip()
            show_tt(self._track_tt_text, self._track_edit)
            self._wheel_timer.start(300)

    def _emit_track_changed(self):
        self.track_changed.emit(self._cur)

    def _on_prev_track(self):
        step = 10 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        v = max(0, self._cur - step)
        if v != self._cur:
            self._cur = v
            self._track_edit.setText(f"{v+1:03d}")
            self._update_nav_btns()
            self.track_changed.emit(self._cur)

    def _on_next_track(self):
        step = 10 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        v = min(self._total - 1, self._cur + step)
        if v != self._cur:
            self._cur = v
            self._track_edit.setText(f"{v+1:03d}")
            self._update_nav_btns()
            self.track_changed.emit(self._cur)

    def _update_nav_btns(self):
        self._track_prev_btn.setEnabled(self._cur > 0)
        self._track_next_btn.setEnabled(self._cur < self._total - 1)

    def set_info(self, total, cur_0, title):
        self._total = max(1, total); self._cur = cur_0
        self._total_lbl.setText(f"/{self._total:03d}")
        self._track_edit.setText(f"{self._cur+1:03d}")
        self._title.setText(title)
        self._update_nav_btns()
        self._update_track_tooltip()

    def set_channels(self, active, used):
        while self._ch_row_lo.count():
            item = self._ch_row_lo.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._ch_btns.clear()
        for i in range(SPC_CH_COUNT):
            btn = NsfChButton(str(i+1), scale=self._scale, parent=self._ch_row)
            btn.set_state(active[i] if i < len(active) else True,
                          used[i]   if i < len(used)   else True)
            btn.clicked.connect(lambda _=False, idx=i: self._on_click(idx))
            btn.right_clicked.connect(lambda idx=i: self.channel_toggled.emit(idx, False, True))
            self._ch_btns.append(btn)
            self._ch_row_lo.addWidget(btn)
        self._ch_row_lo.addStretch()

    def _on_click(self, idx):
        shift = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.channel_toggled.emit(idx, not shift, False)

    def update_channel_states(self, active, used):
        for i, btn in enumerate(self._ch_btns):
            if i < len(active): btn.set_state(active[i], used[i] if i < len(used) else True)

    def update_track_num(self, cur_0):
        self._cur = cur_0
        self._track_edit.setText(f"{cur_0+1:03d}")
        self._update_nav_btns()
        self._update_track_tooltip()

    def set_loading(self, loading):
        self._track_prev_btn.setEnabled(not loading and self._cur > 0)
        self._track_next_btn.setEnabled(not loading and self._cur < self._total - 1)
        self._track_edit.setEnabled(not loading)
        for btn in self._ch_btns:
            btn.setEnabled(not loading)

    def set_track_titles(self, titles):
        self._spc_titles = list(titles)
        self._update_track_tooltip()

    def _update_track_tooltip(self):
        if not self._spc_titles:
            self._track_tt_text = "Track number\nDrag up/down or Wheel to change\n2-Click: Edit"
            return
        lines = []
        for i in range(max(0, self._cur - 4), min(self._total, self._cur + 5)):
            marker = "→  " if i == self._cur else "   "
            name = self._spc_titles[i] if i < len(self._spc_titles) else ""
            lines.append(f"{marker}{i+1:03d}: {name}")
        self._track_tt_text = "\n".join(lines)


# ════════════════════════════════════════
# スペクトラムアナライザー（簡易グラフィックイコライザー風表示）
# ════════════════════════════════════════
class SpectrumWidget(QWidget):
    NUM_BANDS = len(SPECTRUM_BANDS_HZ)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._levels=np.zeros(self.NUM_BANDS, dtype=np.float32)
        self._peak  =np.zeros(self.NUM_BANDS, dtype=np.float32)
        self.setFixedHeight(42)
        self._overlay=None  # FilterOverlayWidget（重ねて表示する子ウィジェット）への参照

    def resizeEvent(self, e):
        if self._overlay is not None:
            self._overlay.setGeometry(0,0,self.width(),self.height())
        super().resizeEvent(e)

    def set_levels(self, new_levels):
        new_levels=np.asarray(new_levels, dtype=np.float32)
        if len(new_levels)!=len(self._levels):
            self._levels=new_levels.copy(); self._peak=new_levels.copy()
        else:
            up=new_levels>self._levels
            # 上昇は即追従、下降はゆっくり減衰（VUメーター風の見た目にする）
            self._levels=np.where(up, new_levels, self._levels*0.72+new_levels*0.28)
            # ピークホールド：少しずつ落ちる横線（信号が無ければ0まで落ちて消える）
            self._peak=np.maximum(new_levels, self._peak-0.025)
        self.update()

    def paintEvent(self, e):
        p=QPainter(self)
        w=self.width(); h=self.height()
        p.fillRect(0,0,w,h, QColor(BG2))
        n=len(self._levels)
        if n==0: p.end(); return
        _,bw,centers=_spectrum_bar_geometry(w, n)
        bottom=h-1; top_margin=2
        usable=h-top_margin*2
        for i in range(n):
            x=centers[i]-bw/2.0
            lvl=float(self._levels[i])
            if lvl>0.003:  # 信号が無い(0)バンドにはバーを描画しない
                bh=max(1.0, lvl*usable)
                y=bottom-bh
                p.fillRect(int(round(x)), int(round(y)), int(round(bw))+1, int(round(bh))+1, QColor(ACC))
            pk=float(self._peak[i])
            if pk>0.003:  # 信号が無い(0)バンドにはピーク線を出さない
                py=bottom-pk*usable
                p.setPen(QPen(QColor(ACC),1))
                p.drawLine(int(round(x)), int(py), int(round(x+bw)), int(py))
        p.end()

# ════════════════════════════════════════
# スペクトラムアナライザー: 主要周波数ラベル行
# ════════════════════════════════════════
class SpectrumLabelsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._n=len(SPECTRUM_BANDS_HZ)
        self._font_px=9
        self.setFixedHeight(13)

    def set_font_px(self, px):
        self._font_px=px; self.update()

    @staticmethod
    def _fmt_hz(hz):
        if hz>=1000:
            v=hz/1000.0
            return (f"{v:g}".rstrip("0").rstrip(".") if v!=int(v) else f"{int(v)}")+"K"
        return f"{int(hz)}"

    def paintEvent(self, e):
        p=QPainter(self)
        w=self.width(); h=self.height()
        p.fillRect(0,0,w,h, QColor(BG))
        n=self._n
        if n==0: p.end(); return
        _,bw,centers=_spectrum_bar_geometry(w, n)
        f=self.font(); f.setPixelSize(max(6,int(self._font_px)))
        p.setFont(f)
        p.setPen(QColor(FG2))
        col_w=max(14, int(bw)+2)
        for i in SPECTRUM_LABEL_IDX:
            if i<0 or i>=n: continue
            cx=centers[i]
            p.drawText(int(cx-col_w/2), 0, col_w, h,
                       Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter,
                       self._fmt_hz(SPECTRUM_BANDS_HZ[i]))
        p.end()

# ════════════════════════════════════════
# フィルター(HPF/LPF) オーバーレイ（スペアナの上に重ねて表示。
# グライコ表示領域(スペアナと同じ範囲)にマウスオーバーした時だけ表示する）
# ════════════════════════════════════════
class FilterOverlayWidget(QWidget):
    GENERAL_TIP = ("Spectrum Analyzer\n"
                   "Filter (HPF/LPF, -24dB/Oct)\n"
                   "Drag:Select pass band\n"
                   "R-Click:Reset (no filter)")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._n=len(FILTER_BANDS_HZ)
        self._lo=0; self._hi=self._n-1   # 現在のフィルター範囲（全域=フィルター無し）
        self._dragging=False
        self._drag_start_idx=None
        self._hovering=False  # マウスがこのエリア上にあるか
        self.on_range_changed=None  # callback(lo_idx, hi_idx)
        self.setMouseTracking(True)
        self.hide()

    # ── 外部連携 ──────────────────────────────
    def set_range(self, lo, hi):
        n=self._n
        lo=max(0,min(n-1,int(lo))); hi=max(0,min(n-1,int(hi)))
        if lo>hi: lo,hi=hi,lo
        self._lo=lo; self._hi=hi
        self._update_visibility()
        self.update()

    def _update_visibility(self):
        """フィルターON(通過域が全域でない)時は、ホバーの有無に関わらず常に表示する。
        フィルターOFF時は、ホバー時のみ表示する（従来通り）。"""
        if self.is_active() or self._hovering:
            self.show(); self.raise_()
        else:
            self.hide()

    def range(self):
        return (self._lo, self._hi)

    def is_active(self):
        return not (self._lo==0 and self._hi==self._n-1)

    def _x_in_range(self, x, centers, bw):
        """x座標が、現在の通過域(黄色塗りつぶし部分)の範囲内にあるか判定する"""
        x0=centers[self._lo]-bw/2.0; x1=centers[self._hi]+bw/2.0
        return x0<=x<=x1

    # ── ジオメトリ ────────────────────────────
    def _geom(self):
        w=self.width(); h=self.height()
        _,bw,centers=_spectrum_bar_geometry(w, self._n)
        return w,h,bw,centers

    def _band_at_x(self, x, centers):
        best=0; bd=1e18
        for i,cx in enumerate(centers):
            d=abs(cx-x)
            if d<bd: bd=d; best=i
        return best

    @staticmethod
    def _fmt_hz(hz):
        if hz>=1000:
            v=hz/1000.0
            s=(f"{v:g}".rstrip("0").rstrip(".") if v!=int(v) else f"{int(v)}")
            return s+"KHz"
        return f"{int(hz)}Hz"

    def _range_desc(self, lo, hi):
        n=self._n
        if lo==0 and hi==n-1:
            return "No filter"
        if lo==0:
            return f"Low-pass {self._fmt_hz(FILTER_BANDS_HZ[hi])}"
        if hi==n-1:
            return f"High-pass {self._fmt_hz(FILTER_BANDS_HZ[lo])}"
        return f"Band-pass {self._fmt_hz(FILTER_BANDS_HZ[lo])} - {self._fmt_hz(FILTER_BANDS_HZ[hi])}"

    def _apply(self):
        self._update_visibility()
        if self.on_range_changed:
            self.on_range_changed(self._lo, self._hi)

    def _show_default_tip(self):
        show_tt(self.GENERAL_TIP, self)

    def _show_range_tip(self):
        show_tt(f"Spectrum Analyzer\n{self._range_desc(self._lo, self._hi)}", self)

    # ── 周波数応答カーブ（おおむねの音量曲線） ──────
    def _curve_points(self, w, h):
        lo,hi=self._lo,self._hi
        if lo==0 and hi==self._n-1:
            return None  # フィルター無し → 描画しない
        sr=44100.0  # 表示用カーブは見た目の近似なので固定sr(代表値)で評価する
        sos=_build_filter_sos(lo,hi,sr)
        if sos is None:
            return None
        _,bw,centers=_spectrum_bar_geometry(w, self._n)
        f_lo=SPECTRUM_BAND_EDGES[0]; f_hi=SPECTRUM_BAND_EDGES[-1]
        freqs=np.geomspace(f_lo, f_hi, 96)
        try:
            _,resp=_sosfreqz(sos, worN=freqs, fs=sr)
        except Exception:
            return None
        db=20.0*np.log10(np.maximum(np.abs(resp), 1e-6))
        db=np.clip(db, FILTER_DB_FLOOR, 0.0)
        log_centers=np.log(FILTER_BANDS_HZ)
        xs=np.interp(np.log(freqs), log_centers, centers)
        margin=3.0
        usable=max(1.0, h-margin*2)
        frac=db/FILTER_DB_FLOOR  # db=0→0, db=FLOOR→1
        ys=margin+frac*usable
        return list(zip(xs.tolist(), ys.tolist()))

    # ── 描画 ──────────────────────────────────
    def paintEvent(self, e):
        p=QPainter(self)
        w,h,bw,centers=self._geom()
        if self._n==0: p.end(); return
        lo,hi=self._lo,self._hi
        if self.is_active():
            x0=centers[lo]-bw/2.0; x1=centers[hi]+bw/2.0
            p.fillRect(int(x0),0,max(1,int(x1-x0)),h, QColor(255,255,0,28))
            pen=QPen(QColor(255,255,0,150)); pen.setWidth(1); pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(int(x0),0,int(x0),h)
            p.drawLine(int(x1),0,int(x1),h)
        pts=self._curve_points(w,h)
        if pts:
            pen=QPen(QColor(255,215,0)); pen.setWidth(1)
            p.setPen(pen)
            path=QPainterPath()
            path.moveTo(pts[0][0], pts[0][1])
            for px,py in pts[1:]:
                path.lineTo(px,py)
            p.drawPath(path)
        p.end()

    # ── マウス ────────────────────────────────
    def enterEvent(self, e):
        self._hovering=True
        self._update_visibility()

    def mouseMoveEvent(self, e):
        if not self._hovering:
            self._hovering=True  # オーバーレイが常時表示中で、spectrum側のenterEventを経由しなかった場合の保険
        w,h,bw,centers=self._geom()
        x=e.position().x()
        if self._dragging:
            idx=self._band_at_x(x, centers)
            lo=min(self._drag_start_idx, idx); hi=max(self._drag_start_idx, idx)
            if (lo,hi)!=(self._lo,self._hi):
                self._lo=lo; self._hi=hi
                self._apply()
                self.update()
            self._show_range_tip()
            return
        if self.is_active() and self._x_in_range(x, centers, bw):
            self._show_range_tip()
        else:
            self._show_default_tip()

    def mousePressEvent(self, e):
        hide_tt()
        w,h,bw,centers=self._geom()
        x=e.position().x()
        if e.button()==Qt.MouseButton.RightButton:
            self.set_range(0, self._n-1)
            self._apply()
            show_tt("Filter reset (no filter)", self)
            return
        if e.button()!=Qt.MouseButton.LeftButton:
            return
        idx=self._band_at_x(x, centers)
        self._drag_start_idx=idx
        self._dragging=True
        self._lo=idx; self._hi=idx
        self._apply()
        self.update()
        self._show_range_tip()

    def mouseReleaseEvent(self, e):
        if e.button()==Qt.MouseButton.RightButton:
            return
        self._dragging=False
        w,h,bw,centers=self._geom()
        pos=e.position()
        if not (0<=pos.x()<=self.width() and 0<=pos.y()<=self.height()):
            self._hovering=False
            hide_tt(); self._update_visibility()
        else:
            if self.is_active() and self._x_in_range(pos.x(), centers, bw):
                self._show_range_tip()
            else:
                self._show_default_tip()

    def leaveEvent(self, e):
        if not self._dragging:
            self._hovering=False
            hide_tt()
            self._update_visibility()

# ════════════════════════════════════════
# 時間表示ラベル（桁ハイライト対応）
# ════════════════════════════════════════
class TimeLabel(QLabel):
    edit_committed = pyqtSignal(float)  # 直接入力確定時に秒数を発火
    edit_invalid = pyqtSignal()         # 不正入力時に発火
    def __init__(self, text="--:--.-", parent=None):
        super().__init__(text, parent)
        self._hi=-1
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)
        self._normal_style=(f"QLabel{{color:{FG}; border:1px solid {BORDER}; "
                            f"background:{BG3}; padding:1px 4px;}}"
                            f"QLabel:hover{{border:1px solid {FG2};}}")
        self.setStyleSheet(self._normal_style)
        self._editor=None

    def set_highlight(self, ci): self._hi=ci; self.update()
    def clear_highlight(self): self._hi=-1; self.setStyleSheet(self._normal_style); self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        # 赤いフォーカス（桁ハイライト）は廃止

    @staticmethod
    def parse_time(s):
        """ 'MM:SS.m' / 'SS.m' / 秒数 を秒(float)に変換。失敗時None """
        s=s.strip()
        if not s or s.startswith("--"): return None
        try:
            if ":" in s:
                mm,rest=s.split(":",1)
                return int(mm)*60 + float(rest)
            return float(s)
        except: return None

    @staticmethod
    def format_time(sec):
        sec=max(0.0,sec)
        m=int(sec)//60; s=int(sec)%60
        d=int(round((sec-int(sec))*10))
        if d>=10: s+=1; d-=10
        if s>=60: m+=1; s-=60
        return f"{m:02d}:{s:02d}.{d:1d}"

    def begin_edit(self):
        """ダブルクリックで編集用QLineEditを表示"""
        # シングルタップのSet遅延タイマーが動いていればキャンセル
        if getattr(self, "_tap_timer", None):
            self._tap_timer.stop()
        if self._editor is not None: return
        from PyQt6.QtWidgets import QLineEdit
        ed=QLineEdit(self)
        cur=self.text()
        ed.setText("" if cur.startswith("--") else cur)
        ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ed.setStyleSheet(f"color:{FG}; background:{BG3}; border:1px solid #FFD700; padding:0;")
        ed.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        ed.setGeometry(0,0,self.width(),self.height())
        ed.setFocus(); ed.selectAll()
        self._editor=ed
        def commit():
            if self._editor is None: return
            txt=self._editor.text()
            self._editor.deleteLater(); self._editor=None
            sec=TimeLabel.parse_time(txt)
            if sec is not None and sec>=0:
                self.edit_committed.emit(float(sec))
            elif txt.strip()!="":
                self.edit_invalid.emit()
        def cancel():
            if self._editor is None: return
            self._editor.deleteLater(); self._editor=None
        def on_wheel(ev):
            # 編集中(ダブルクリック後)のホイールで値を増減。不正な値の時は何もせずエラー表示
            sec=TimeLabel.parse_time(ed.text())
            if sec is None:
                self.edit_invalid.emit(); ev.ignore(); return
            shift=bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            step=1.0 if shift else 0.1
            delta=step if ev.angleDelta().y()>0 else -step
            new_sec=max(0.0, round((sec+delta)/0.1)*0.1)
            ed.setText(TimeLabel.format_time(new_sec))
            ev.accept()
        ed.wheelEvent=on_wheel
        ed.returnPressed.connect(commit)
        ed.editingFinished.connect(commit)
        ed.show()

    def mouseDoubleClickEvent(self, e):
        self.begin_edit()

# ════════════════════════════════════════
# ドラッグラベル（速度・キー・音量）
# ════════════════════════════════════════
class DragLabel(QLabel):
    value_changed = pyqtSignal(float)
    value_edited_invalid = pyqtSignal()
    def __init__(self, text, step=0.25, lo=0.25, hi=4.0, default=0.0, big_step=None, parent=None):
        super().__init__(text, parent)
        self.step=step; self.lo=lo; self.hi=hi
        self.big_step=big_step if big_step is not None else step
        self.default_value=default
        self._val=0.0; self._y0=0; self._base=0.0; self._editor=None
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setStyleSheet(f"QLabel{{color:{FG}; background:{BG3}; border:1px solid {BORDER}; padding:2px 8px;}}"
                           f"QLabel:hover{{border:1px solid {FG2};}}")
        self.setFixedHeight(22)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    def set_value(self, v): self._val=v
    def mousePressEvent(self,e):
        hide_tt()
        if e.button()==Qt.MouseButton.RightButton:
            # 右クリック → デフォルト値に戻す
            self._val=self.default_value
            self.value_changed.emit(self._val)
            return
        if e.button()==Qt.MouseButton.LeftButton:
            self._y0=e.position().y(); self._base=self._val
    def mouseMoveEvent(self,e):
        if not (e.buttons() & Qt.MouseButton.LeftButton): return
        dy=self._y0-e.position().y()
        if abs(dy)<4: return
        steps=int(dy//12)
        shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        st = self.big_step if shift else self.step
        new_v=max(self.lo,min(self.hi, round((self._base+steps*st)/st)*st))
        if new_v!=self._val: self._val=new_v; self.value_changed.emit(new_v)
    def mouseReleaseEvent(self,e): pass
    def mouseDoubleClickEvent(self,e):
        from PyQt6.QtWidgets import QLineEdit
        if getattr(self,"_editor",None) is not None: return
        ed=QLineEdit(self)
        ed.setText(self.text().replace("×","").replace("x","").replace("+","").replace("±",""))
        ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ed.setStyleSheet(f"color:{FG}; background:{BG3}; border:1px solid #FFD700; padding:0;")
        ed.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        ed.setGeometry(0,0,self.width(),self.height())
        ed.setFocus(); ed.selectAll()
        self._editor=ed
        def commit():
            if self._editor is None: return
            txt=self._editor.text().strip()
            self._editor.deleteLater(); self._editor=None
            try:
                v=float(txt)
            except:
                self.value_edited_invalid.emit(); return
            v=max(self.lo,min(self.hi, round(v/self.step)*self.step))
            self._val=v; self.value_changed.emit(v)
        def on_wheel(ev):
            # 編集中(ダブルクリック後)のホイールで値を増減。不正な値の時は何もせずエラー表示
            txt=ed.text().strip()
            try:
                v=float(txt)
            except:
                self.value_edited_invalid.emit(); ev.ignore(); return
            shift=bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            st=self.big_step if shift else self.step
            delta=st if ev.angleDelta().y()>0 else -st
            new_v=max(self.lo, min(self.hi, round((v+delta)/self.step)*self.step))
            if float(self.step).is_integer():
                ed.setText(str(int(round(new_v))))
            else:
                ed.setText(f"{new_v:.1f}")
            ev.accept()
        ed.wheelEvent=on_wheel
        ed.returnPressed.connect(commit)
        ed.editingFinished.connect(commit)
        ed.show()

# ════════════════════════════════════════
# カスタムツールチップ
# ════════════════════════════════════════
_TT = None
def show_tt(text, widget=None):
    global _TT
    if _TT is None:
        _TT=QLabel()
        _TT.setWindowFlags(Qt.WindowType.ToolTip|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        _TT.setStyleSheet("background:#FFFFCC; color:#000; border:1px solid #888; padding:3px 6px; font-size:12px;")
        _TT.setMargin(2)
    _TT.setText(text); _TT.adjustSize()
    if widget is not None:
        # 対象ウィジェットの真下に表示（対象に被らない）
        try:
            gp=widget.mapToGlobal(widget.rect().bottomLeft())
            _TT.move(gp.x(), gp.y()+4); _TT.show(); return
        except Exception:
            pass
    pos=QCursor.pos()
    _TT.move(pos.x()+14, pos.y()+20); _TT.show()
def hide_tt():
    global _TT
    if _TT: _TT.hide()

def _attach_tt(w, text):
    """NsfPanelなどMainWindow外で使えるツールチップアタッチ（モジュール関数版）"""
    prev_enter = w.enterEvent
    prev_leave = w.leaveEvent
    def enter(e, t=text, ww=w):
        show_tt(t, ww)
        try: prev_enter(e)
        except: pass
    def leave(e):
        hide_tt()
        try: prev_leave(e)
        except: pass
    w.enterEvent = enter
    w.leaveEvent = leave

class TipButton(QPushButton):
    def __init__(self, tip="", parent=None):
        super().__init__(parent); self._tip=tip
    def enterEvent(self,e):
        if self._tip: show_tt(self._tip, self)
        super().enterEvent(e)
    def mousePressEvent(self,e):
        hide_tt(); super().mousePressEvent(e)
    def leaveEvent(self,e):
        hide_tt(); super().leaveEvent(e)


# ════════════════════════════════════════
# メインウィンドウ
# ════════════════════════════════════════
class MarkerRow(QWidget):
    """高さ固定・背景色確実描画のマーカー行ウィジェット"""
    def __init__(self, bg, parent=None, height=26):
        super().__init__(parent)
        self._bg = QColor(bg)
        self.setFixedHeight(height)
    def paintEvent(self, e):
        from PyQt6.QtGui import QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)

class DividerRow(QWidget):
    """カテゴリの区切りを示す、薄いグレーの横線を中央に描く固定高さのスペーサー。
    上下の余白はQt自身のレイアウト(ストレッチ)で揃えるため、paintEventでの
    手計算による上下の非対称が起きない。"""
    def __init__(self, color, height=9, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        lo=QVBoxLayout(self); lo.setContentsMargins(0,0,0,0); lo.setSpacing(0)
        lo.addStretch(1)
        line=QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{color}; border:none;")
        lo.addWidget(line)
        lo.addStretch(1)

class MainWindow(QMainWindow):
    _tick_sig   = pyqtSignal(float, float)
    _status_sig = pyqtSignal(str)
    _load_done_sig = pyqtSignal(float, object, object)
    _tempo_busy_sig = pyqtSignal(bool)
    _nsf_track_done_sig = pyqtSignal(float, object)        # dur, waveform
    _nsf_extend_done_sig = pyqtSignal(float, bool, object) # dur, natural_end, waveform
    _nsf_ch_render_done_sig = pyqtSignal(object, int, int) # wav, ch_mask, track_idx
    _spc_track_done_sig = pyqtSignal(float, object)        # dur, waveform
    _spc_ch_render_done_sig = pyqtSignal(object, int, int) # wav, ch_mask, track_idx

    def __init__(self):
        super().__init__()
        self.engine = AudioEngine()
        self.engine.on_tick = lambda pos,tot: self._tick_sig.emit(pos,tot)
        self._total=0.0
        self._tempo=120.0; self._beat=4; self._bar=2.0
        self._kp_enter_time=0.0  # テンキーEnter押下時刻（直後の4/6をSetにする）
        # グローバル設定（zoom倍率・音量）を読み込み
        _gs=load_global_settings()
        self._scale = 2.0 if _gs["zoom"]>=2.0 else 1.0
        self._init_volume = max(0, min(200, _gs["volume"]))

        # 耳コピモードの点滅アニメーション用
        self._ear_blink_timer=QTimer(self)
        self._ear_blink_timer.timeout.connect(self._ear_blink_tick)
        self._ear_blink_on=False  # False=通常色, True=青

        self._nsf_loading = False        # NSFトラックデコード中フラグ
        self._nsf_ch_rendering = False   # ch切替レンダリング中フラグ
        self._nsf_wf_views = {}          # {track_idx: (view_lo, view_hi)} 波形ズーム保存
        self._nsf_pending_session = None # session to apply after initial track switch on load
        # NSF 総再生時間ラベル（点滅・ドラッグ延長）
        self._nsf_dur_editable = False   # True = 赤点滅・ドラッグ可
        self._nsf_dur_blink_phase = 0.0
        self._nsf_dur_blink_dir = 1
        self._nsf_dur_blink_timer = QTimer(self)
        self._nsf_dur_blink_timer.timeout.connect(self._nsf_dur_blink_tick)
        self._nsf_dur_drag_y = None
        self._nsf_dur_drag_base = None
        self._nsf_extend_done_sig.connect(self._on_nsf_extend_done)
        # SPC 関連
        self._spc_loading = False
        self._spc_ch_rendering = False
        self._spc_wf_views = {}
        self._spc_track_done_sig.connect(self._on_spc_track_done)
        self._spc_ch_render_done_sig.connect(self._on_spc_ch_render_done)
        self._tick_sig.connect(self._on_tick)
        self._status_sig.connect(lambda m: self._msg.setText(m))
        self._tempo_busy_sig.connect(self._set_tempo_inputs_enabled)
        self._load_done_sig.connect(self._on_load_done)
        self._nsf_track_done_sig.connect(self._on_nsf_track_done)
        self._nsf_ch_render_done_sig.connect(self._on_nsf_ch_render_done)

        self.setWindowTitle(f"Morokoshi Time {APP_VERSION}  by Ike-san")
        self.setFixedSize(self.S(375), self.S(313))
        self.setAcceptDrops(True)
        self._build_ui()
        self.setFocus()

        # スペクトラムアナライザー更新タイマー（約25fps）
        self._spec_timer=QTimer(self)
        self._spec_timer.timeout.connect(self._update_spectrum)
        self._spec_timer.start(40)

    def S(self, px):
        """px値をzoom倍率でスケール（整数を返す）"""
        return int(round(px * self._scale))

    # ── DnD
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self,e):
        urls=e.mimeData().urls()
        if urls:
            p=urls[0].toLocalFile()
            if os.path.exists(p): self._load(p)

    # ── UI構築
    def _build_ui(self):
        central=QWidget(); self.setCentralWidget(central)
        root=QVBoxLayout(central); root.setContentsMargins(self.S(8),self.S(8),self.S(8),self.S(0)); root.setSpacing(self.S(2))

        # Folder/File行は削除（ファイル名はウィンドウタイトルに表示）

        # ── メインエリア
        # 青グループ(マーカー) | 赤グループ(Speed/Key/Rew/FF) | アイコン列(Tempo Detection)
        main_area=QWidget(); main_area.setStyleSheet(f"background:{BG};")
        main_lo=QHBoxLayout(main_area); main_lo.setContentsMargins(0,0,0,0); main_lo.setSpacing(self.S(6))

        # ── 共通サイズ定義
        LBL_W = self.S(54)
        VAL_W = self.S(64)
        self.VAL_W = VAL_W

        # ── Rew/FF表示・Tempo/Beat/Bar入力欄（A,B,Speed,Keyの右側に配置するため先に作成）
        self._rewff_lbl=QLineEdit("4.0s")
        self._rewff_lbl.setFixedWidth(VAL_W); self._rewff_lbl.setFixedHeight(self.S(22))
        self._rewff_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rewff_lbl.setReadOnly(True)
        self._rewff_lbl._normal_style=f"QLineEdit{{color:{FG}; background:{BG3}; border:1px solid {BORDER}; padding:1px 4px;}}QLineEdit:hover{{border:1px solid {FG2};}}"
        self._rewff_lbl.setStyleSheet(self._rewff_lbl._normal_style)
        self._rewff_lbl.setCursor(Qt.CursorShape.SizeVerCursor)
        self._rewff_lbl._y0=0; self._rewff_lbl._base=4.0
        self._rewff_lbl._moved=False; self._rewff_lbl._editor=None
        self._rewff_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._rewff_lbl.mousePressEvent      = lambda e: self._rewff_press(e)
        self._rewff_lbl.mouseMoveEvent       = lambda e: self._rewff_move(e)
        self._rewff_lbl.mouseReleaseEvent    = lambda e: None
        self._rewff_lbl.mouseDoubleClickEvent= lambda e: self._rewff_dblclick(e)
        self._rewff_lbl.wheelEvent           = lambda e: self._rewff_wheel(e)
        self._attach_tip(self._rewff_lbl, "Rew/FF step\n2-Click:Edit(sec)\nDrag:+/-0.1s\nShift+Drag:+/-1.0s\nR-Click:Reset Tempo/Beat/Bar\n→Tempo is recalculated")

        # A<->B 差分表示（編集不可、Rew/FFと同様の表示）
        self._abdiff_lbl=QLineEdit("--:--.-")
        self._abdiff_lbl.setFixedWidth(VAL_W); self._abdiff_lbl.setFixedHeight(self.S(22))
        self._abdiff_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._abdiff_lbl.setReadOnly(True)
        self._abdiff_lbl._normal_style=f"QLineEdit{{color:{FG}; background:{BG3}; border:1px solid {BORDER}; padding:1px 4px;}}QLineEdit:hover{{border:1px solid {FG2};}}"
        self._abdiff_lbl.setStyleSheet(self._abdiff_lbl._normal_style)
        self._abdiff_lbl.setCursor(Qt.CursorShape.SizeVerCursor)
        self._abdiff_lbl._y0=0; self._abdiff_lbl._base=None
        self._abdiff_lbl._moved=False; self._abdiff_lbl._editor=None
        self._abdiff_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._abdiff_lbl.mousePressEvent      = lambda e: self._abdiff_press(e)
        self._abdiff_lbl.mouseMoveEvent       = lambda e: self._abdiff_move(e)
        self._abdiff_lbl.mouseReleaseEvent    = lambda e: None
        self._abdiff_lbl.mouseDoubleClickEvent= lambda e: self._abdiff_dblclick(e)
        self._abdiff_lbl.wheelEvent           = lambda e: self._abdiff_wheel(e)
        self._attach_tip(self._abdiff_lbl, "A<->B duration\n2-Click:Edit(sec)\nDrag:+/-0.1s\nShift+Drag:+/-1.0s\nR-Click:Reset A & B\nB marker moves, A stays fixed")

        for attr, default, dstep, dmin, dmax, tipname, tipshift in [
            ("_tempo_edit","120.0", 0.1, 30.0, 300.0, "Tempo", "Shift+Drag:+/-1.0"),
            ("_beat_edit", "4",     1.0, 1.0,  16.0,  "Beat",  None),
            ("_bar_edit",  "2.0",   0.1, 0.1,  100.0, "Bar",   "Shift+Drag:+/-1.0"),
        ]:
            edit=QLineEdit(default); edit.setFixedWidth(VAL_W); edit.setFixedHeight(self.S(22))
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.setStyleSheet(f"QLineEdit{{color:{FG}; background:{BG3}; border:1px solid {BORDER}; padding:1px 4px;}}"
                               f"QLineEdit:hover{{border:1px solid {FG2};}}")
            edit.returnPressed.connect(lambda ed=None: (self._update_rewff(), self.setFocus()))
            edit.editingFinished.connect(lambda ed=edit: (self._update_rewff(), ed.setReadOnly(True), ed.setStyleSheet(f"QLineEdit{{color:{FG}; background:{BG3}; border:1px solid {BORDER}; padding:1px 4px;}}QLineEdit:hover{{border:1px solid {FG2};}}")))
            edit.setCursor(Qt.CursorShape.SizeVerCursor)
            edit._dstep=dstep; edit._dint=(dstep>=1.0); edit._dmin=dmin; edit._dmax=dmax
            edit._default=default
            edit._y0=0; edit._base=0.0; edit._moved=False
            edit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)  # 右クリックメニュー無効
            edit.setReadOnly(True)  # 通常は編集不可。2-Clickで編集開始
            if tipname=="Beat":
                _tt=f"{tipname}\n2-Click:Edit\nDrag:+/-1\nR-Click:Reset"
            else:
                _tt=f"{tipname}\n2-Click:Edit\nDrag:+/-0.1\n{tipshift}\nR-Click:Reset"
            self._attach_tip(edit, _tt)
            edit.mousePressEvent   = lambda e,ed=edit: self._edit_press(e,ed)
            edit.mouseMoveEvent    = lambda e,ed=edit: self._edit_move(e,ed)
            edit.mouseReleaseEvent = lambda e,ed=edit: self._edit_release(e,ed)
            edit.mouseDoubleClickEvent = lambda e,ed=edit: self._edit_dblclick(e,ed)
            edit.wheelEvent        = lambda e,ed=edit: self._edit_wheel(e,ed)
            setattr(self, attr, edit)

        def mk_row(label_text, widget):
            _mg=self.S(2)
            outer=MarkerRow(BG, height=self.S(22)+2*_mg)
            outer_lo=QVBoxLayout(outer); outer_lo.setContentsMargins(0,_mg,0,_mg); outer_lo.setSpacing(0)
            row=QWidget(); row.setFixedHeight(self.S(22)); row.setStyleSheet(f"background:{BG};")
            rlo=QHBoxLayout(row); rlo.setContentsMargins(self.S(2),0,self.S(2),0); rlo.setSpacing(self.S(4))
            lbl=QLabel(label_text)  # strip()しない："  A   "等の先頭スペース(インデント)を保持するため
            lbl.setStyleSheet(f"color:{FG2};")
            # ラベル領域を固定幅(46px)にして全行の値ボックス位置を揃える
            lbl_wrap=QWidget(); lbl_wrap.setFixedWidth(self.S(46)); lbl_wrap.setStyleSheet("background:transparent;")
            lw_lo=QHBoxLayout(lbl_wrap); lw_lo.setContentsMargins(0,0,0,0); lw_lo.setSpacing(0)
            lw_lo.addWidget(lbl); lw_lo.addStretch()
            rlo.addWidget(lbl_wrap); rlo.addWidget(widget)
            rlo.addStretch()
            outer_lo.addWidget(row)
            return outer
        self._mk_row_fn = mk_row  # _add_marker_rowからも同じ行構築ルーチンを使うため保持


        # ── 青グループ：マーカー列 (stretch=1)
        # 左列(A<->B,A,B,Key,Fine)と中央列(Rew/FF,Tempo,Beat,Bar,Speed)は完全に独立した
        # 縦スタックとして配置する（「Aの右にTempoを置く」のではなく、それぞれ上から順に
        # 並べた結果、行の高さが同じなのでたまたま横に揃って見える、という構造）。
        # 枠線の代わりに、カテゴリの境目にだけ余白+薄いグレーの横線を入れて区切りを示す。
        left_col=QWidget(); left_col.setStyleSheet(f"background:{BG};")
        outer_lo=QVBoxLayout(left_col); outer_lo.setContentsMargins(0,0,0,0); outer_lo.setSpacing(0)
        cols_lo=QHBoxLayout(); cols_lo.setContentsMargins(0,0,0,0); cols_lo.setSpacing(self.S(6))

        # 左列: A<->B, A, B, ―区切り―, Key, Fine
        left_stack=QWidget(); left_stack.setStyleSheet(f"background:{BG};")
        left_vlo=QVBoxLayout(left_stack); left_vlo.setContentsMargins(0,0,0,0); left_vlo.setSpacing(0)

        self._mk_rows={}
        left_vlo.addWidget(mk_row("A<->B ", self._abdiff_lbl))
        # A/Bマーカー行は、専用の入れ子コンテナを介さず、他の行(Tempo/Beat/Bar等)と
        # 完全に同じ階層(left_vloの直接の子)に配置する。これにより、入れ子構造の違いに
        # よる余白のズレが構造上発生しなくなる。_rebuild_markers()は、A<->B行の直後の
        # インデックスへ直接 insertWidget する。
        self._mk_vlo = left_vlo
        self._mk_insert_at = 1  # A<->B行(index 0)の直後
        self._rebuild_markers()
        left_vlo.addWidget(DividerRow(BORDER, self.S(5)))

        self._key_lbl=DragLabel("±0", step=1, lo=-24, hi=24, default=0.0, big_step=12)
        self._key_lbl.set_value(0); self._key_lbl.setFixedWidth(VAL_W); self._key_lbl.setFixedHeight(self.S(22))
        self._key_lbl.value_changed.connect(self._on_key)
        self._key_lbl.value_edited_invalid.connect(lambda: self._st("Invalid number"))
        self._attach_tip(self._key_lbl, "Key\n2-Click:Edit\nDrag:+/-1\nShift+Drag:+/-12\nR-Click:Reset")
        left_vlo.addWidget(mk_row("Key   ", self._key_lbl))

        self._fine_lbl=DragLabel("±0.00", step=0.01, lo=-1.0, hi=1.0, default=0.0, big_step=0.1)
        self._fine_lbl.set_value(0.0); self._fine_lbl.setFixedWidth(VAL_W); self._fine_lbl.setFixedHeight(self.S(22))
        self._fine_lbl.value_changed.connect(self._on_fine)
        self._fine_lbl.value_edited_invalid.connect(lambda: self._st("Invalid number"))
        self._attach_tip(self._fine_lbl, "Fine\n2-Click:Edit\nDrag:+/-0.01\nShift+Drag:+/-0.1\nR-Click:Reset")
        left_vlo.addWidget(mk_row("Fine  ", self._fine_lbl))
        cols_lo.addWidget(left_stack)

        # 中央列: Rew/FF, Tempo, Beat, Bar, ―区切り―, Speed
        mid_stack=QWidget(); mid_stack.setStyleSheet(f"background:{BG};")
        mid_vlo=QVBoxLayout(mid_stack); mid_vlo.setContentsMargins(0,0,0,0); mid_vlo.setSpacing(0)
        mid_vlo.addWidget(mk_row("Rew/FF", self._rewff_lbl))
        mid_vlo.addWidget(mk_row("Tempo ", self._tempo_edit))
        mid_vlo.addWidget(mk_row("Beat  ", self._beat_edit))
        mid_vlo.addWidget(mk_row("Bar   ", self._bar_edit))
        mid_vlo.addWidget(DividerRow(BORDER, self.S(5)))

        self._spd_lbl=DragLabel("x1.0", step=0.1, lo=0.5, hi=2.0, default=1.0, big_step=0.5)
        self._spd_lbl.set_value(1.0); self._spd_lbl.setFixedWidth(VAL_W); self._spd_lbl.setFixedHeight(self.S(22))
        self._spd_lbl.value_changed.connect(self._on_spd)
        self._spd_lbl.value_edited_invalid.connect(lambda: self._st("Invalid number"))
        self._attach_tip(self._spd_lbl, "Speed\n2-Click:Edit\nDrag:+/-0.1\nShift+Drag:+/-0.5\nR-Click:Reset")
        mid_vlo.addWidget(mk_row("Speed ", self._spd_lbl))
        cols_lo.addWidget(mid_stack)

        outer_lo.addLayout(cols_lo)
        outer_lo.addStretch()  # 残りを下に伸ばす
        main_lo.addWidget(left_col, 0)

        # ── アイコン群（A/B/Speed/Key行とは別グループ、3行構成）
        icon_col=QWidget(); icon_col.setStyleSheet(f"background:{BG};")
        icon_lo=QVBoxLayout(icon_col); icon_lo.setContentsMargins(0,self.S(4),0,0); icon_lo.setSpacing(0)

        # 4列構成（各列32px）で配置
        #   [blank], Help,  Zoom
        #   Open,   Tempo, Reset
        #   [blank], Ear
        #   Rew,    AB,    FF
        # ※ None=空（透明）スロット。A/B押しボタンはテンキー(4/6)との整合性のためEarの左右に配置。
        icon_grid = [
            [None,
             ("help","Help [H]","_help_btn",self._show_help),
             ("zoom","Zoom [Z]","_zoom_btn",self._toggle_zoom)],
            [("open","Open [O]","_open_btn",self._open),
             ("tempo_search","Tempo Detection [T]","_tempo_btn",self._tempo_detect),
             ("reset","Reset All [R / Shift: Clear Cache]","_reset_btn",
              lambda: self._do_cache_clear() if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else self._do_reset())],
            [self._wrap_small_btn(self._btn_marker_a),
             ("ear","Ear Mode [↑]","_ear_btn",self._ear_mode),
             self._wrap_small_btn(self._btn_marker_b)],
            [("rew","Rew [←]","_rew_btn",self._rew),
             ("ab_repeat","AB Repeat [↓]","_ab_btn",self._ab_toggle),
             ("ff","FF [→]","_ff_btn",self._ff)],
        ]
        for _row in icon_grid:
            _rw=QWidget(); _rw.setStyleSheet(f"background:{BG};")
            _rlo=QHBoxLayout(_rw); _rlo.setContentsMargins(0,0,0,0); _rlo.setSpacing(self.S(4))
            for _cell in _row:
                if _cell is None:
                    # 透明な空スロット（位置合わせ用）
                    _sp=QWidget(); _sp.setFixedSize(self.S(32),self.S(32))
                    _sp.setStyleSheet("background:transparent;")
                    _rlo.addWidget(_sp)
                elif isinstance(_cell, QWidget):
                    # 既存ウィジェットをそのまま配置（A/Bボタンなど）
                    _rlo.addWidget(_cell)
                else:
                    _name,_tip,_attr,_slot=_cell
                    # AB Repeatはトグル式なのでフラッシュ除外
                    _b=self._mk_icon_btn(_name,_tip,_slot, flash=(_name not in ("ab_repeat","ear")))
                    _rlo.addWidget(_b)
                    if _attr: setattr(self,_attr,_b)
            _rlo.addStretch()
            icon_lo.addWidget(_rw)

        icon_lo.addStretch()
        main_lo.addWidget(icon_col, 0, Qt.AlignmentFlag.AlignTop)

        # Rew/FF 右クリック → Tempo/Beat/Bar リセット
        from PyQt6.QtWidgets import QPushButton as _QPB
        def _make_rew_ff_press(btn_self):
            def _press(e):
                hide_tt()
                if e.button()==Qt.MouseButton.RightButton:
                    self._reset_tempo_beat_bar()
                else:
                    _QPB.mousePressEvent(btn_self, e)
            return _press
        self._rew_btn.mousePressEvent = _make_rew_ff_press(self._rew_btn)
        self._ff_btn.mousePressEvent  = _make_rew_ff_press(self._ff_btn)

        root.addWidget(main_area, 0, Qt.AlignmentFlag.AlignTop)

        # ── スペアナ/NSFパネル切り替えエリア（QStackedWidget）
        self._mode_stack=QStackedWidget(); self._mode_stack.setFixedHeight(self.S(55))
        self._mode_stack.setStyleSheet(f"background:{BG};")

        # ページ0: スペクトラムアナライザー + ラベル行
        spec_area=QWidget(); spec_area.setStyleSheet(f"background:{BG};")
        spec_lo=QVBoxLayout(spec_area); spec_lo.setContentsMargins(0,0,0,0); spec_lo.setSpacing(0)
        self._spectrum=SpectrumWidget()
        self._spectrum.setFixedHeight(self.S(42))
        spec_lo.addWidget(self._spectrum)
        self._spectrum_labels=SpectrumLabelsWidget()
        self._spectrum_labels.set_font_px(self.S(8))
        self._spectrum_labels.setFixedHeight(self.S(13))
        spec_lo.addWidget(self._spectrum_labels)
        self._mode_stack.addWidget(spec_area)   # index 0

        # ページ1: NSFパネル
        self._nsf_panel=NsfPanel(scale=self._scale)
        self._nsf_panel.track_changed.connect(self._nsf_set_track)
        self._nsf_panel.channel_toggled.connect(self._nsf_on_ch_toggle)
        self._mode_stack.addWidget(self._nsf_panel)  # index 1

        # ページ2: SPCパネル
        self._spc_panel = SpcPanel(scale=self._scale)
        self._spc_panel.track_changed.connect(self._spc_set_track)
        self._spc_panel.channel_toggled.connect(self._spc_on_ch_toggle)
        self._mode_stack.addWidget(self._spc_panel)  # index 2

        root.addWidget(self._mode_stack)

        # ── フィルター(HPF/LPF) オーバーレイ（スペアナの上に重ねて表示。
        #    フィルターON時は常時表示、OFF時はグライコ表示領域(スペアナと同じ範囲)に
        #    マウスオーバーした時だけ表示する）
        self._filter_overlay=FilterOverlayWidget(self._spectrum)
        self._filter_overlay.setGeometry(0,0,self._spectrum.width(),self._spectrum.height())
        self._spectrum._overlay=self._filter_overlay
        self._filter_overlay.on_range_changed=lambda lo,hi: self.engine.set_filter_range(lo,hi)
        self._filter_overlay.set_range(self.engine.filter_lo_idx, self.engine.filter_hi_idx)
        def _spectrum_enter(e, fo=self._filter_overlay):
            fo._hovering=True; fo._update_visibility()
        self._spectrum.enterEvent=_spectrum_enter

        # ── 波形エリア
        wf_area=QWidget(); wf_area.setFixedHeight(self.S(42)+self.S(12)+self.S(36)); wf_area.setStyleSheet(f"background:{BG};")
        wf_lo=QVBoxLayout(wf_area); wf_lo.setContentsMargins(0,0,0,0); wf_lo.setSpacing(0)
        self._waveform=WaveformWidget(); self._waveform.seeked.connect(self._on_wf_seek)
        self._waveform.seek_revert.connect(self._on_wf_seek)  # ダブルクリック確定時、1回目クリックのシークを取り消す
        self._waveform.setFixedHeight(self.S(42))
        self._waveform._marker_hit_tol_px=self.S(8)  # マーカー直上ダブルクリック判定の許容範囲
        self._waveform.marker_reset_requested.connect(self._reset_marker)
        self._attach_tip(self._waveform, "Waveform\nClick:Seek\nDrag position line:Move playhead\nDrag A/B line:Move that marker\nDouble-click:Set marker\nDouble-click on A/B:Reset it\nWheel:Zoom\nShift+Wheel:Scroll\nDrag A-B:Move both")
        wf_lo.addWidget(self._waveform)
        from PyQt6.QtWidgets import QScrollBar
        self._wf_scroll=QScrollBar(Qt.Orientation.Horizontal)
        self._wf_scroll.setFixedHeight(self.S(12))
        self._wf_scroll.setRange(0,0); self._wf_scroll.setPageStep(1000)
        self._wf_scroll.setStyleSheet(
            f"QScrollBar:horizontal{{height:{self.S(12)}px;background:{BG2};border:none;}}"
            f"QScrollBar::handle:horizontal{{background:{BG3};border-radius:4px;min-width:{self.S(20)}px;}}"
            f"QScrollBar::handle:horizontal:hover{{background:{FG2};}}"
            f"QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0px;}}")
        self._wf_scroll.valueChanged.connect(self._on_wf_scroll)
        self._attach_tip(self._wf_scroll, "Drag:Scroll")
        self._waveform.view_changed.connect(self._sync_wf_scroll)
        self._waveform.ab_drag.connect(self._on_ab_drag)
        self._waveform.double_clicked.connect(self._on_wf_double_click)
        self._waveform.position_drag.connect(self._on_wf_position_drag)
        self._waveform.marker_drag.connect(self._on_wf_marker_drag)
        wf_lo.addWidget(self._wf_scroll)

        # 時間行
        time_row=QWidget(); time_row.setFixedHeight(self.S(32)); time_row.setStyleSheet(f"background:{BG};")
        time_lo=QHBoxLayout(time_row); time_lo.setContentsMargins(0,0,0,0); time_lo.setSpacing(self.S(4))
        self._pos_lbl=TimeLabel("00:00.0"); self._pos_lbl.setFixedSize(self.S(64),self.S(22))
        self._pos_lbl.setCursor(Qt.CursorShape.SizeVerCursor)
        self._pos_lbl._y0=0; self._pos_lbl._base=0.0; self._pos_lbl._step=1.0; self._pos_lbl._ci=0
        self._pos_lbl.mousePressEvent   = self._pos_press
        self._pos_lbl.mouseMoveEvent    = self._pos_move
        self._pos_lbl.mouseReleaseEvent = self._pos_release
        self._pos_lbl.edit_committed.connect(self._set_current_time)
        self._pos_lbl.edit_invalid.connect(lambda: self._st("Invalid time"))
        self._pos_lbl.leaveEvent        = self._pos_leave
        self._attach_tip(self._pos_lbl, "Current Time\n2-Click:Edit\nDrag:+/-0.1s\nShift+Drag:+/-1.0s\nR-Click:Reset")
        self._dur_lbl=QLabel("00:00.0"); self._dur_lbl.setFixedSize(self.S(64),self.S(22))
        self._dur_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dur_lbl.setStyleSheet(f"color:{FG2};")
        self._dur_lbl.mousePressEvent   = self._dur_lbl_press
        self._dur_lbl.mouseMoveEvent    = self._dur_lbl_move
        self._dur_lbl.mouseReleaseEvent = self._dur_lbl_release
        self._dur_lbl.wheelEvent        = self._dur_lbl_wheel
        self._dur_lbl.enterEvent        = self._dur_lbl_enter
        self._dur_lbl.leaveEvent        = self._dur_lbl_leave
        self._attach_tip(self._dur_lbl, "Total time\n(NSF: Drag up/Wheel↑ to extend\nDrag down/Wheel↓ to shorten)")
        self._vol_slider=QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0,200); self._vol_slider.setValue(100)
        self._vol_slider.setFixedWidth(self.S(80))
        self._vol_slider.setStyleSheet(
            f"QSlider::groove:horizontal{{height:{self.S(4)}px;background:{BG3};}}"
            f"QSlider::handle:horizontal{{width:{self.S(12)}px;height:{self.S(12)}px;margin:-{self.S(4)}px 0;background:{FG};border-radius:{self.S(6)}px;}}")
        self._vol_slider.valueChanged.connect(lambda v: (setattr(self.engine,'volume',v/100.0), self._vol_pct.setText(f"{v}%"), self._on_volume_changed(v)))
        self._vol_pct=QLabel("100%"); self._vol_pct.setStyleSheet(f"color:{FG2};"); self._vol_pct.setFixedWidth(self.S(40))
        self._vol_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # 右クリックで100%に戻す
        def _vol_reset(e):
            if e.button()==Qt.MouseButton.RightButton:
                self._vol_slider.setValue(100)
        def _vol_slider_press(e):
            if e.button()==Qt.MouseButton.RightButton:
                self._vol_slider.setValue(100); return
            QSlider.mousePressEvent(self._vol_slider, e)
        self._vol_slider.mousePressEvent = _vol_slider_press
        self._vol_pct.mousePressEvent = _vol_reset
        self._attach_tip(self._vol_slider, "Volume\nDrag:change\nR-Click:100%")
        self._attach_tip(self._vol_pct, "Volume\nR-Click:100%")
        def _mk_lbl_wrap(lbl, w):
            pad=self.S(4); ctr=QWidget(); ctr.setFixedWidth(w); ctr.setStyleSheet(f"background:{BG};")
            lo2=QVBoxLayout(ctr); lo2.setContentsMargins(0,pad,0,0); lo2.setSpacing(0)
            lo2.addWidget(lbl); lo2.addStretch()
            return ctr
        time_lo.addWidget(_mk_lbl_wrap(self._pos_lbl, self.S(64)))
        time_lo.addStretch()
        self._play_btn=self._mk_icon_btn("play_pause","Play/Pause [Space] / Shift: Reset",
            lambda: self._seek_to_start() if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else self._pp(),
            flash=False)
        time_lo.addWidget(self._play_btn, 0, Qt.AlignmentFlag.AlignTop)
        time_lo.addStretch()
        time_lo.addWidget(_mk_lbl_wrap(self._dur_lbl, self.S(64)))
        wf_lo.addWidget(time_row)
        root.addWidget(wf_area)


        # ── メッセージバー（右端に音量バー）
        msg_row=QWidget(); msg_row.setFixedHeight(self.S(19)); msg_row.setStyleSheet(f"background:{BG};")
        # 左端をSpeed/Key行と同じ2px、右端も同じ2px余白に
        msg_lo=QHBoxLayout(msg_row); msg_lo.setContentsMargins(self.S(2),0,self.S(8),0); msg_lo.setSpacing(self.S(4))
        self._msg=QLabel("Drop a file or click Open to load")
        self._msg.setStyleSheet(f"color:{FG2}; background:{BG}; padding:1px 0px; font-size:{self.S(11)}px;")
        self._msg.setMaximumWidth(self.S(230))  # 音量バーに被らないよう制限
        msg_lo.addWidget(self._msg)
        msg_lo.addStretch()
        msg_lo.addWidget(self._vol_slider)
        msg_lo.addWidget(self._vol_pct)
        # Show ffmpeg path on hover (only before any file is loaded)
        def _msg_enter(e, ww=self):
            if ww.engine._file_hash is None:
                import shutil as _sh
                _base = _get_app_dir()
                _candidates = [
                    os.path.join(_base, "ffmpeg.exe"),
                    os.path.join(_base, "dist", "ffmpeg.exe"),
                ]
                _found = next((p for p in _candidates if os.path.exists(p)), None)
                if _found is None:
                    _found = _sh.which("ffmpeg")
                    _label = f"ffmpeg (PATH): {_found}" if _found else "ffmpeg: not found (will auto-download on first file open)"
                else:
                    _label = f"ffmpeg: {_found}"
                show_tt(_label, ww._msg)
        def _msg_leave(e):
            hide_tt()
        self._msg.enterEvent = _msg_enter
        self._msg.leaveEvent = _msg_leave
        root.addWidget(msg_row)

        # 音量の初期値を反映
        try:
            self._vol_slider.setValue(self._init_volume)
        except Exception:
            pass

    def _apply_scale(self, root_w):
        """構築済みUIツリーを再帰走査し、固定サイズ・フォント・余白をscale倍にする"""
        from PyQt6.QtWidgets import QLayout
        s=self._scale
        def scale_widget(w):
            # フォント
            f=w.font()
            ps=f.pointSizeF()
            if ps>0:
                f.setPointSizeF(ps*s); w.setFont(f)
            # 固定サイズ（min/maxが同じ＝固定とみなす）
            mn=w.minimumSize(); mx=w.maximumSize()
            fw = (mn.width()==mx.width() and mn.width()>0)
            fh = (mn.height()==mx.height() and mn.height()>0)
            if fw and fh:
                w.setFixedSize(int(mn.width()*s), int(mn.height()*s))
            else:
                if fw: w.setFixedWidth(int(mn.width()*s))
                if fh: w.setFixedHeight(int(mn.height()*s))
            # maximumWidthのみ設定されている場合
            if not fw and mx.width()<16777215:
                w.setMaximumWidth(int(mx.width()*s))
            if not fh and mx.height()<16777215:
                w.setMaximumHeight(int(mx.height()*s))
            # レイアウトのマージン・スペーシング
            lay=w.layout()
            if lay is not None:
                scale_layout(lay)
            # ボタンのアイコンサイズ
            try:
                from PyQt6.QtWidgets import QAbstractButton
                if isinstance(w, QAbstractButton):
                    isz=w.iconSize()
                    if isz.width()>0:
                        nm=getattr(w,"_icon_name",None)
                        ns=int(isz.width()*s)
                        w.setIconSize(QSize(ns,ns))
                        if nm: w.setIcon(_get_icon(nm, ns, FG))
            except Exception:
                pass
        def scale_layout(lay):
            m=lay.contentsMargins()
            lay.setContentsMargins(int(m.left()*s),int(m.top()*s),int(m.right()*s),int(m.bottom()*s))
            try: lay.setSpacing(int(lay.spacing()*s))
            except Exception: pass
            for i in range(lay.count()):
                it=lay.itemAt(i)
                cw=it.widget()
                if cw is not None:
                    scale_widget(cw)
                else:
                    sub=it.layout()
                    if sub is not None: scale_layout(sub)
                    sp=it.spacerItem()
                    if sp is not None:
                        sz=sp.sizeHint()
                        sp.changeSize(int(sz.width()*s), int(sz.height()*s))
        scale_widget(root_w)

    # ──────────────────────────────────────
    # マーカー行
    # ──────────────────────────────────────
    def _rebuild_markers(self):
        for n in list(self._mk_rows):
            row,tl=self._mk_rows.pop(n); self._mk_vlo.removeWidget(row); row.deleteLater()
        for i,(n,label) in enumerate([(10,"  A   "),(11,"  B   ")]):
            self._add_marker_row(n, label, self._mk_insert_at+i)

    def _attach_tip(self, w, text):
        """任意のウィジェットにホバーで独自ツールチップを表示（既存enter/leaveを保持してチェーン）"""
        prev_enter = w.enterEvent
        prev_leave = w.leaveEvent
        def enter(e, t=text, ww=w):
            show_tt(t, ww)
            try: prev_enter(e)
            except: pass
        def leave(e):
            hide_tt()
            try: prev_leave(e)
            except: pass
        w.enterEvent = enter
        w.leaveEvent = leave

    def _wrap_small_btn(self, btn):
        """サイズの異なる小さいボタン(A/Bなど)を、アイコン1個分(32x32)の透明な枠の中央に
        配置する。アイコン列の他の行と列幅・配置が揃うようにするため。"""
        wrap=QWidget(); wrap.setFixedSize(self.S(32),self.S(32)); wrap.setStyleSheet("background:transparent;")
        wlo=QHBoxLayout(wrap); wlo.setContentsMargins(0,0,0,0); wlo.setSpacing(0)
        wlo.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        return wrap

    def _mk_icon_btn(self, name, tip, slot=None, flash=True):
        ICO_SM=self.S(32); ICO_IMG=self.S(28)
        b=TipButton(tip=tip)
        b.setIcon(_get_icon(name,ICO_IMG,FG))
        b.setIconSize(QSize(ICO_IMG,ICO_IMG))
        b.setFixedSize(ICO_SM,ICO_SM)
        b.setStyleSheet(
            "QPushButton{background:transparent; border:none; border-radius:4px;}"
            f"QPushButton:hover{{background:{BG2};}}")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b._icon_name=name
        if flash:
            # 押下中は黄色、離したら通常色に戻す
            b.pressed.connect(lambda nm=name, bb=b: bb.setIcon(_get_icon(nm,ICO_IMG,"#FFD700")))
            b.released.connect(lambda nm=name, bb=b: bb.setIcon(_get_icon(nm,ICO_IMG,FG)))
            if slot:
                # モーダルダイアログ等でreleasedが取りこぼされても確実に戻す
                def _wrapped(checked=False, _slot=slot, nm=name, bb=b):
                    try: _slot()
                    finally: bb.setIcon(_get_icon(nm,ICO_IMG,FG))
                b.clicked.connect(_wrapped)
        else:
            if slot: b.clicked.connect(slot)
        return b

    def _add_marker_row(self, n, label, insert_idx):
        # 番号表示・押しボタン（A/Bの押しボタンはEarアイコンの左右に配置するため、
        # ここでは行には追加しない。ボタン自体はアイコン列用に別途生成して保持する）
        _lab=label.strip()
        if _lab in ("A","B"):
            btn=TipButton(tip=f"Go to marker {_lab} [{_lab}]")
            btn.setText(_lab)
            btn.setFixedSize(self.S(22), self.S(22))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton{{color:{FG}; background:{BG3}; border:1px solid {BORDER}; border-radius:3px; font-size:{self.S(12)}px; padding:0;}}"
                f"QPushButton:hover{{background:{BG2}; border:1px solid {FG2};}}"
                f"QPushButton:pressed{{color:#FFD700; border:1px solid #FFD700;}}")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _=False, nn=n: self._goto_marker(nn))
            setattr(self, f"_btn_marker_{_lab.lower()}", btn)
        # 時間
        tl=TimeLabel(self._fmt(self.engine.markers.get(n)))
        tl.setFixedWidth(self.VAL_W); tl._n=n; tl._base=0.0; tl._step=1.0; tl._ci=0; tl._moved=False; tl._y0=0
        tl.setFixedHeight(self.S(22))
        tl.setCursor(Qt.CursorShape.SizeVerCursor)
        tl.mousePressEvent   = lambda e,t=tl: self._mk_press(e,t)
        tl.mouseMoveEvent    = lambda e,t=tl: self._mk_move(e,t)
        tl.mouseReleaseEvent = lambda e,t=tl: self._mk_release(e,t)
        def _mk_leave(e, t=tl): t.clear_highlight(); t.setText(self._fmt(self.engine.markers.get(t._n)))
        tl.leaveEvent = _mk_leave
        # ダブルクリックで直接入力 → マーカー時間に反映
        tl.edit_committed.connect(lambda sec, nn=n: self._set_marker_time(nn, sec))
        tl.edit_invalid.connect(lambda: self._st("Invalid time"))
        _lab2 = "A" if n==MARKER_A else "B"
        self._attach_tip(tl, f"Marker {_lab2}\n1-Click:Set [Shift+{_lab2}]\n2-Click:Edit\nDrag:+/-0.1s\nShift+Drag:+/-1.0s\nR-Click:Clear")
        # 行の外枠・ラベル配置は、他の行(Tempo/Beat/Bar等)と完全に同じ共通ルーチンで作る。
        # これにより、行の高さ・マージンの食い違いによるズレが構造上発生しない。
        outer = self._mk_row_fn(label, tl)
        self._mk_vlo.insertWidget(insert_idx, outer)
        self._mk_rows[n]=(outer,tl)

    def _refresh_marker(self, n):
        if n in self._mk_rows:
            _,tl=self._mk_rows[n]
            tl.clear_highlight()
            tl.setText(self._fmt(self.engine.markers.get(n)))

    # ──────────────────────────────────────
    # マーカー時間ドラッグ
    # ──────────────────────────────────────
    def _mk_press(self, e, tl):
        hide_tt()
        # 右クリック → マーカーをリセット（A/Bは両方一括リセット）
        if e.button()==Qt.MouseButton.RightButton:
            if tl._n in (10, 11):
                self._reset_marker(MARKER_A)
                self._reset_marker(MARKER_B)
            else:
                self._reset_marker(tl._n)
            return
        tl._moved=False
        sec=self.engine.markers.get(tl._n)
        if sec is None:
            tl._base=None  # 未設定 → ドラッグ調整不可（シングルタップでSetのみ）
            return
        tl._y0=e.position().y(); tl._base=sec; tl._step=0.1; tl._ci=0
        # Ear Mode連動用: press時点の相手マーカー値を保存
        other = MARKER_B if tl._n==MARKER_A else MARKER_A
        tl._base_other = self.engine.markers.get(other)

    def _set_marker_time(self, n, sec):
        """直接入力でマーカー時間を設定。A=Bはエラー、A>Bは入れ替え"""
        if self.engine.data is None: return
        if sec < 0 or (self._total>0 and sec > self._total):
            self._st("Time out of range")
            self._refresh_marker(n)
            return
        other = MARKER_B if n==MARKER_A else MARKER_A
        ov = self.engine.markers.get(other)
        # Ear Mode中: 差分を保ったまま相手も移動（範囲外ならエラーで元に戻す）
        if self.engine.ear_active and ov is not None:
            diff = ov - self.engine.markers.get(n, sec)
            no = sec + diff
            if no < 0 or (self._total>0 and no > self._total):
                self._st("Time out of range")
                self._refresh_marker(n)
                return
            self.engine.markers[n]=sec
            self.engine.markers[other]=no
            self._refresh_marker(MARKER_A); self._refresh_marker(MARKER_B)
            self._update_wf_ab()
            self._st("Markers updated")
            return
        if ov is not None:
            if abs(sec-ov) < 1e-9:
                self._st("A and B cannot be equal")
                self._refresh_marker(n)
                return
            # A>B（またはB<A）になる場合は入れ替え
            self.engine.markers[n]=sec
            a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
            if a is not None and b is not None and a>b:
                self.engine.markers[MARKER_A], self.engine.markers[MARKER_B] = b, a
            self._refresh_marker(MARKER_A); self._refresh_marker(MARKER_B)
            self._update_wf_ab()
            self._st("Markers updated")
            return
        self.engine.markers[n]=sec
        self._refresh_marker(n)
        if n in (MARKER_A, MARKER_B): self._update_wf_ab()
        self._st(f"Marker {'A' if n==MARKER_A else 'B' if n==MARKER_B else n} = {self._fmt(sec)}")

    def _set_current_time(self, sec):
        """直接入力で現在時刻（再生位置）を設定（楽曲時間を超えたらエラー、元の値のまま）"""
        if self.engine.data is None: return
        if sec < 0 or (self._total>0 and sec > self._total):
            self._st("Time out of range")
            self._pos_lbl.setText(self._fmt(self.engine.current_sec()))  # 元に戻す
            return
        self.engine.seek(sec)
        self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(sec))
        if self._total>0: self._waveform.set_position(sec/self._total)

    def _reset_marker(self, n):
        if n in self.engine.markers:
            del self.engine.markers[n]
        if n in (MARKER_A, MARKER_B):
            # AB Repeat / Ear Mode ON中にA/Bを消去したらOFFにする
            if self.engine.ab_active:
                self.engine.ab_active=False
                self._ab_btn.setIcon(_get_icon("ab_repeat",self.S(28),FG))
                self._st("AB Repeat OFF")
            if self.engine.ear_active:
                self.engine.ear_active=False
                self._ear_btn.setIcon(_get_icon("ear",self.S(28),FG))
                self._stop_ear_blink()
                self._st("Ear Mode OFF")
            self._update_wf_ab()
        self._refresh_marker(n)
        self._st(f"Marker {'A' if n==MARKER_A else 'B' if n==MARKER_B else n} reset")

    def _mk_move(self, e, tl):
        if self.engine.markers.get(tl._n) is None: return
        if not (e.buttons() & Qt.MouseButton.LeftButton): return
        try:
            dy=tl._y0-e.position().y()
            if abs(dy)<3: return
            tl._moved=True
            steps=int(dy/12.0)
            shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            step = 1.0 if shift else tl._step
            new_sec=max(0.0, tl._base+steps*step)
            n=tl._n
            looping_now = self.engine.playing and (self.engine.ab_active or self.engine.ear_active)
            # Ear Mode中: 差分を保ったまま両マーカーを連動
            if self.engine.ear_active and MARKER_A in self.engine.markers and MARKER_B in self.engine.markers:
                other = MARKER_B if n==MARKER_A else MARKER_A
                cur_n=self.engine.markers[n]; other_v=self.engine.markers[other]
                delta=new_sec-cur_n
                if looping_now:
                    lo=min(cur_n,other_v); hi=max(cur_n,other_v)
                    cur_pos=self.engine.current_sec()
                    new_lo=lo+delta; new_hi=hi+delta
                    if new_lo > cur_pos:
                        delta = cur_pos-lo
                    elif new_hi < cur_pos:
                        delta = cur_pos-hi
                final_n=cur_n+delta; final_other=other_v+delta
                if final_n < 0 or final_other < 0 or (self._total>0 and (final_n>self._total or final_other>self._total)):
                    return  # どちらかが範囲外なら動かさない
                self.engine.markers[n]=final_n
                self.engine.markers[other]=final_other
                self._refresh_marker(other)
                self._update_wf_ab()
                tl.setText(self._fmt(final_n))
                return
            # 通常時: 相手マーカーを追い越さない（A は B-0.1s まで、B は A+0.1s から）
            other = MARKER_B if n==MARKER_A else MARKER_A
            ov = self.engine.markers.get(other)
            if ov is not None:
                if n==MARKER_A:
                    new_sec=min(new_sec, ov-0.1)
                else:
                    new_sec=max(new_sec, ov+0.1)
                new_sec=max(0.0, new_sec)
            # ループ中(AB/Ear ON)の再生時は、再生位置を追い越さないよう制限する
            if looping_now:
                cur_pos=self.engine.current_sec()
                if n==MARKER_A:
                    new_sec=min(new_sec, cur_pos)
                else:
                    new_sec=max(new_sec, cur_pos)
            self.engine.markers[n]=new_sec
            if n in (MARKER_A, MARKER_B): self._update_wf_ab()
            tl.setText(self._fmt(new_sec))
        except Exception as ex: print("mk_move err:", ex)

    def _mk_release(self, e, tl):
        if e.button()==Qt.MouseButton.RightButton:
            return
        tl.clear_highlight()
        tl.setText(self._fmt(self.engine.markers.get(tl._n)))
        if not tl._moved:
            # シングルタップ → 200ms遅延でSet（その間にダブルクリックが来たらキャンセル）
            n=tl._n
            if getattr(tl,"_tap_timer",None):
                tl._tap_timer.stop()
            tl._tap_timer=QTimer(self); tl._tap_timer.setSingleShot(True)
            tl._tap_timer.timeout.connect(lambda nn=n: self._tap_set_marker(nn))
            tl._tap_timer.start(200)
        else:
            # ドラッグ確定 → A>Bなら入れ替え
            self._normalize_ab()
            self._update_wf_ab()

    def _tap_set_marker(self, n):
        # マーカーをSetし、時間テキストボックスを一瞬黄色にする
        self._rec_marker(n)
        if n in self._mk_rows:
            _, tl = self._mk_rows[n]
            flash_style=(f"color:#FFD700; border:1px solid #FFD700; "
                         f"background:{BG3}; padding:1px 4px;")
            tl.setStyleSheet(flash_style)
            QTimer.singleShot(150, lambda t=tl: t.setStyleSheet(t._normal_style))

    def _mk_update_hl(self, x, tl):
        try:
            fm=tl.fontMetrics(); cw=max(1,fm.horizontalAdvance("0"))
            text=self._fmt(tl._base if tl._base else 0.0)
            tw=fm.horizontalAdvance(text); xoff=(tl.width()-tw)//2
            ci=max(0,min(int((x-xoff)/cw),len(text)-1))
            while ci<len(text) and text[ci] in(':','.','-'): ci+=1
            ci=min(ci,len(text)-1)
            step_map={0:600.0,1:60.0,3:10.0,4:1.0,6:0.1}
            tl._step=step_map.get(ci,1.0); tl._ci=ci
            tl.set_highlight(ci)
        except: pass

    # ──────────────────────────────────────
    # 現在時間ドラッグ
    # ──────────────────────────────────────
    def _pos_press(self, e):
        hide_tt()
        # 右クリック → デフォルト(先頭0:00.0)に戻す
        if e.button()==Qt.MouseButton.RightButton:
            if self.engine.data is not None:
                self.engine.seek(0.0)
                self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(0.0))
                self._waveform.set_position(0)
            return
        self._pos_lbl._y0=e.position().y()
        self._pos_lbl._base=self.engine.current_sec()
        self._pos_lbl._step=0.1

    def _pos_move(self, e):
        if not (e.buttons() & Qt.MouseButton.LeftButton): return
        dy=self._pos_lbl._y0-e.position().y()
        if abs(dy)<3: return
        steps=int(dy/12.0)
        shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        step = 1.0 if shift else self._pos_lbl._step
        new_sec=max(0.0,min(self._pos_lbl._base+steps*step,self._total))
        self.engine.seek(new_sec)
        self._pos_lbl.setText(self._fmt(new_sec))
        self._waveform.set_position(new_sec/self._total if self._total else 0)

    def _pos_release(self, e): pass

    # ── Tempo/Bar/Beat 入力欄の上下ドラッグ
    def _edit_press(self, e, ed):
        hide_tt()
        from PyQt6.QtWidgets import QLineEdit
        if e.button()==Qt.MouseButton.RightButton:
            # 右クリック → デフォルト値に戻す
            ed.setText(getattr(ed,"_default",ed.text()))
            self._update_rewff()
            return
        try: ed._base=float(ed.text())
        except: ed._base=0.0
        ed._y0=e.position().y(); ed._moved=False
        QLineEdit.mousePressEvent(ed, e)

    def _edit_dblclick(self, e, ed):
        # 2-Click → 編集可能にして全選択。枠を黄色くハイライト
        ed.setReadOnly(False)
        ed.setStyleSheet(f"color:{FG}; background:{BG3}; border:1px solid #FFD700; padding:1px 4px;")
        ed.setFocus(); ed.selectAll()

    def _edit_move(self, e, ed):
        # 左ボタンを押している時のみドラッグ調整（ホバーでは何もしない）
        if not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        dy=ed._y0-e.position().y()
        if abs(dy)<3: return
        ed._moved=True
        steps=int(dy/12.0)
        shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        dstep = 1.0 if (shift and not ed._dint) else ed._dstep
        val=ed._base+steps*dstep
        lo=getattr(ed,"_dmin",0.0); hi=getattr(ed,"_dmax",9999.0)
        val=max(lo, min(hi, val))
        if ed._dint:
            ed.setText(str(int(round(val))))
        else:
            ed.setText(f"{val:.1f}")
        self._update_rewff()

    def _edit_wheel(self, e, ed):
        # 2-Clickで編集モードに入っている間だけホイールで増減を許可（通常表示中は無効）
        if ed.isReadOnly():
            e.ignore(); return
        txt=ed.text().strip()
        try:
            v=float(txt)
        except Exception:
            self._st("Invalid number"); e.ignore(); return
        shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        dstep = 1.0 if (shift and not ed._dint) else ed._dstep
        delta = dstep if e.angleDelta().y()>0 else -dstep
        lo=getattr(ed,"_dmin",0.0); hi=getattr(ed,"_dmax",9999.0)
        val=max(lo, min(hi, v+delta))
        if ed._dint:
            ed.setText(str(int(round(val))))
        else:
            ed.setText(f"{val:.1f}")
        self._update_rewff()
        e.accept()

    def _edit_release(self, e, ed):
        from PyQt6.QtWidgets import QLineEdit
        QLineEdit.mouseReleaseEvent(ed, e)

    def _pos_leave(self, e):
        self._pos_lbl.clear_highlight()

    def _pos_update_hl(self, x):
        try:
            lbl=self._pos_lbl; fm=lbl.fontMetrics(); cw=max(1,fm.horizontalAdvance("0"))
            text=self._fmt(self.engine.current_sec()); tw=fm.horizontalAdvance(text)
            xoff=(lbl.width()-tw)//2
            ci=max(0,min(int((x-xoff)/cw),len(text)-1))
            while ci<len(text) and text[ci] in(':','.','-'): ci+=1
            ci=min(ci,len(text)-1)
            step_map={0:600.0,1:60.0,3:10.0,4:1.0,6:0.1}
            lbl._step=step_map.get(ci,1.0); lbl._ci=ci
            lbl.set_highlight(ci)
        except: pass

    # ──────────────────────────────────────
    # Rew/FF
    # ──────────────────────────────────────
    def _rewff_sec(self):
        try:
            t=float(self._tempo_edit.text())
            b=int(self._beat_edit.text())
            bar=float(self._bar_edit.text())
            if t>0 and b>0: return 60.0/t*b*bar
        except: pass
        return 4.0

    def _update_rewff(self):
        # 入力値を検証。不正なら直前の有効値に戻してエラー表示。
        err=False
        # Tempo
        try:
            t=float(self._tempo_edit.text()); t=max(30.0,min(300.0,t))
            self._tempo=t
        except:
            err=True
        self._tempo_edit.setText(f"{self._tempo:.1f}")
        # Beat
        try:
            b=int(round(float(self._beat_edit.text()))); b=max(1,min(16,b))
            self._beat=b
        except:
            err=True
        self._beat_edit.setText(str(self._beat))
        # Bar
        try:
            bar=float(self._bar_edit.text()); bar=max(0.1,min(100.0,bar))
            self._bar=bar
        except:
            err=True
        self._bar_edit.setText(f"{self._bar:.1f}")
        sec=self._rewff_sec()
        self._rewff_lbl.setText(f"{sec:.1f}s")
        if err:
            self._st("Invalid number")

    def _reset_tempo_beat_bar(self):
        """Tempo/Beat/Bar をデフォルト値にリセット"""
        self._tempo=120.0; self._beat=4; self._bar=2.0
        self._tempo_edit.setText("120.0"); self._beat_edit.setText("4"); self._bar_edit.setText("2.0")
        self._update_rewff()
        self._st("Tempo/Beat/Bar Reset")

    def _rew(self):
        _log(f"_rew: current={self.engine.current_sec():.3f} rewff_sec={self._rewff_sec():.3f}")
        if self.engine.ear_active:
            self._ear_shift(-self._rewff_sec()); return
        new_sec = max(0.0, self.engine.current_sec() - self._rewff_sec())
        self.engine.seek(new_sec)
        self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(new_sec))
        if self._total > 0: self._waveform.set_position(new_sec / self._total)
    def _ff(self):
        _log(f"_ff: current={self.engine.current_sec():.3f} rewff_sec={self._rewff_sec():.3f}")
        if self.engine.ear_active:
            self._ear_shift(self._rewff_sec()); return
        new_sec = min(self._total, self.engine.current_sec() + self._rewff_sec())
        self.engine.seek(new_sec)
        self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(new_sec))
        if self._total > 0: self._waveform.set_position(new_sec / self._total)

    def _ear_shift(self, delta):
        """耳コピモード時のRew/FF: A/Bマーカーをdeltaだけずらす"""
        if self.engine.data is None: return
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None or b is None: return
        na=a+delta; nb=b+delta
        lo_lim=0.0; hi_lim=self._total if self._total>0 else max(na,nb)
        if na<lo_lim or nb<lo_lim or na>hi_lim or nb>hi_lim:
            self._st("Marker out of range"); return
        self.engine.markers[MARKER_A]=na; self.engine.markers[MARKER_B]=nb
        self._refresh_marker(MARKER_A); self._refresh_marker(MARKER_B)
        self._update_wf_ab()
        if self.engine.playing:
            lo=min(na,nb); hi=max(na,nb)
            cur=self.engine.current_sec()
            if not (lo<=cur<=hi):
                self.engine.seek(lo)

    # ──────────────────────────────────────
    # 再生
    # ──────────────────────────────────────
    def _pp(self):
        _log(f"_pp: data_is_None={self.engine.data is None} playing={self.engine.playing} paused={self.engine.paused}")
        if self.engine.data is None: return
        if self.engine.playing:
            self.engine.pause_toggle()
            self._upd_play(not self.engine.paused)
            # 一時停止から再開する時も、80%より右ならビューを合わせる
            if not self.engine.paused:
                if self._total>0:
                    self._waveform.position=max(0.0,min(1.0, self.engine.current_sec()/self._total))
                self._waveform.align_view_for_play()
        else:
            # AB Repeat有効時: ループ外なら小さい方のマーカーへ移動してから再生
            if (self.engine.ab_active or self.engine.ear_active) and MARKER_A in self.engine.markers and MARKER_B in self.engine.markers:
                lo=min(self.engine.markers[MARKER_A],self.engine.markers[MARKER_B])
                hi=max(self.engine.markers[MARKER_A],self.engine.markers[MARKER_B])
                cur=self.engine.current_sec()
                if not (lo<=cur<=hi):
                    self.engine.seek(lo)
                    self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(lo))
                    if self._total>0: self._waveform.set_position(lo/self._total)
            # 再生開始前に現在位置を波形へ同期してからビュー調整
            if self._total>0:
                self._waveform.position=max(0.0,min(1.0, self.engine.current_sec()/self._total))
            self._waveform.align_view_for_play()  # 80%より右なら先にスクロール位置を合わせる
            self.engine.play(); self._upd_play(True)

    def _upd_play(self, active):
        color = "#FFD700" if active else FG
        self._play_btn.setIcon(_get_icon("play_pause",self.S(28),color))

    def _ab_toggle(self):
        _log(f"_ab_toggle: ab_active={self.engine.ab_active} markers_AB={self.engine.markers.get(MARKER_A)},{self.engine.markers.get(MARKER_B)}")
        if self.engine.ab_active:
            self.engine.ab_active=False
            self._ab_btn.setIcon(_get_icon("ab_repeat",self.S(28),FG))
            if self.engine.playing: self.engine._rt_reset_from_current()
            self._update_wf_ab(); self._st("AB Repeat OFF")
        else:
            # 排他: Ear ModeがONならOFFにする
            if self.engine.ear_active:
                self.engine.ear_active=False
                self._ear_btn.setIcon(_get_icon("ear",self.S(28),FG))
                self._stop_ear_blink()
            # マーカー記入漏れを補完してからON
            if self.engine.data is not None:
                self._fill_ab_markers()
            self.engine.ab_active=True
            self._ab_btn.setIcon(_get_icon("ab_repeat",self.S(28),"#FFD700"))
            self._update_wf_ab(); self._st("AB Repeat ON")

    def _fill_ab_markers(self):
        """AB Repeat ON時、A/Bの記入漏れをRew/FF表示時間を使って補完"""
        rewff=self._rewff_sec()
        has_a = MARKER_A in self.engine.markers
        has_b = MARKER_B in self.engine.markers
        total = self._total if self._total>0 else None
        def clamp(v):
            v=max(0.0, v)
            if total is not None: v=min(v, total)
            return v
        if not has_a and not has_b:
            # 両方ブランク → A=現在時間, B=現在時間+Rew/FF
            cur=self.engine.current_sec()
            self.engine.markers[MARKER_A]=clamp(cur)
            self.engine.markers[MARKER_B]=clamp(cur+rewff)
            self._refresh_marker(MARKER_A); self._refresh_marker(MARKER_B)
        elif not has_a and has_b:
            # Aのみブランク → A = B - Rew/FF
            self.engine.markers[MARKER_A]=clamp(self.engine.markers[MARKER_B]-rewff)
            self._refresh_marker(MARKER_A)
        elif has_a and not has_b:
            # Bのみブランク → B = A + Rew/FF
            self.engine.markers[MARKER_B]=clamp(self.engine.markers[MARKER_A]+rewff)
            self._refresh_marker(MARKER_B)

    def _update_wf_ab(self):
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        self._waveform.set_ab(a,b,self._total)
        self.engine.rt_marker_changed()
        self._update_abdiff()

    def _update_abdiff(self):
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is not None and b is not None:
            self._abdiff_lbl.setText(self._fmt(abs(a-b)))
        else:
            self._abdiff_lbl.setText("--:--.-")

    # ── A<->B インタラクティブ操作 ──────────────────────────────────────
    def _abdiff_press(self, e):
        hide_tt()
        if e.button()==Qt.MouseButton.RightButton:
            # A/B 両方を一度にリセット
            self._reset_marker(MARKER_A); self._reset_marker(MARKER_B)
            return
        if self.engine.data is None:
            self._abdiff_lbl._base=None; return
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None or b is None:
            self._fill_ab_markers()
            self._update_wf_ab()
            a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None or b is None:
            self._abdiff_lbl._base=None; return
        self._abdiff_lbl._y0=e.position().y()
        self._abdiff_lbl._base=abs(b-a)
        self._abdiff_lbl._moved=False

    def _abdiff_move(self, e):
        if not (e.buttons() & Qt.MouseButton.LeftButton): return
        base=self._abdiff_lbl._base
        if base is None: return
        dy=self._abdiff_lbl._y0-e.position().y()
        if abs(dy)<3: return
        self._abdiff_lbl._moved=True
        steps=int(dy/12.0)
        shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        dstep=1.0 if shift else 0.1
        new_dur=max(0.1, round((base+steps*dstep)*10)/10)
        self._apply_abdiff_duration(new_dur, revert_on_error=False)

    def _abdiff_wheel(self, e):
        if self.engine.data is None: e.ignore(); return
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None or b is None:
            self._fill_ab_markers(); self._update_wf_ab()
            a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None or b is None: e.ignore(); return
        dur=abs(b-a)
        shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        dstep=1.0 if shift else 0.1
        delta=dstep if e.angleDelta().y()>0 else -dstep
        new_dur=max(0.1, round((dur+delta)*10)/10)
        self._apply_abdiff_duration(new_dur)
        e.accept()

    def _abdiff_dblclick(self, e):
        if getattr(self._abdiff_lbl,"_editor",None) is not None: return
        if self.engine.data is None: return
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None or b is None:
            self._fill_ab_markers(); self._update_wf_ab()
            a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        dur = abs(b-a) if (a is not None and b is not None) else 0.0
        from PyQt6.QtWidgets import QLineEdit
        ed=QLineEdit(self._abdiff_lbl)
        ed.setText(f"{dur:.1f}")
        ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ed.setStyleSheet(f"color:{FG}; background:{BG3}; border:1px solid #FFD700; padding:0;")
        ed.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        ed.setGeometry(0,0,self._abdiff_lbl.width(),self._abdiff_lbl.height())
        ed.setFocus(); ed.selectAll()
        self._abdiff_lbl._editor=ed
        def commit():
            if self._abdiff_lbl._editor is None: return
            txt=ed.text().strip()
            ed.deleteLater(); self._abdiff_lbl._editor=None
            self._abdiff_lbl.setStyleSheet(self._abdiff_lbl._normal_style)
            try: new_dur=float(txt)
            except: self._st("Invalid number"); self._update_abdiff(); return
            if new_dur<=0: self._st("Duration must be positive"); self._update_abdiff(); return
            self._apply_abdiff_duration(new_dur)
        ed.returnPressed.connect(commit)
        ed.editingFinished.connect(commit)
        ed.show()

    def _apply_abdiff_duration(self, new_dur, revert_on_error=True):
        """A<->B 差分を new_dur 秒に変更。A固定・B移動。"""
        if self.engine.data is None: return
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None or b is None:
            self._fill_ab_markers()
            a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None:
            self._st("Set A marker first")
            if revert_on_error: self._update_abdiff()
            return
        new_b=a+new_dur
        if new_b<=a+1e-9:
            self._st("B must be after A")
            if revert_on_error: self._update_abdiff()
            return
        if self._total>0 and new_b>self._total:
            self._st("B out of range")
            if revert_on_error: self._update_abdiff()
            return
        self.engine.markers[MARKER_B]=new_b
        self._refresh_marker(MARKER_B)
        self._update_wf_ab()

    # ── Rew/FF インタラクティブ操作 ──────────────────────────────────────
    def _rewff_press(self, e):
        hide_tt()
        if e.button()==Qt.MouseButton.RightButton:
            # Tempo/Beat/Bar を一度にリセット
            self._reset_tempo_beat_bar(); return
        self._rewff_lbl._base=self._rewff_sec()
        self._rewff_lbl._y0=e.position().y()
        self._rewff_lbl._moved=False

    def _rewff_move(self, e):
        if not (e.buttons() & Qt.MouseButton.LeftButton): return
        dy=self._rewff_lbl._y0-e.position().y()
        if abs(dy)<3: return
        self._rewff_lbl._moved=True
        steps=int(dy/12.0)
        shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        dstep=1.0 if shift else 0.1
        new_sec=max(0.01, round((self._rewff_lbl._base+steps*dstep)*10)/10)
        self._apply_rewff_sec(new_sec, revert_on_error=False)

    def _rewff_wheel(self, e):
        cur_sec=self._rewff_sec()
        shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        dstep=1.0 if shift else 0.1
        delta=dstep if e.angleDelta().y()>0 else -dstep
        new_sec=max(0.01, round((cur_sec+delta)*10)/10)
        self._apply_rewff_sec(new_sec)
        e.accept()

    def _rewff_dblclick(self, e):
        if getattr(self._rewff_lbl,"_editor",None) is not None: return
        from PyQt6.QtWidgets import QLineEdit
        ed=QLineEdit(self._rewff_lbl)
        ed.setText(f"{self._rewff_sec():.1f}")
        ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ed.setStyleSheet(f"color:{FG}; background:{BG3}; border:1px solid #FFD700; padding:0;")
        ed.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        ed.setGeometry(0,0,self._rewff_lbl.width(),self._rewff_lbl.height())
        ed.setFocus(); ed.selectAll()
        self._rewff_lbl._editor=ed
        def commit():
            if self._rewff_lbl._editor is None: return
            txt=ed.text().strip()
            ed.deleteLater(); self._rewff_lbl._editor=None
            try: new_sec=float(txt)
            except: self._st("Invalid number"); return
            if new_sec<=0: self._st("Value must be positive"); return
            self._apply_rewff_sec(new_sec)
        ed.returnPressed.connect(commit)
        ed.editingFinished.connect(commit)
        ed.show()

    def _apply_rewff_sec(self, new_sec, revert_on_error=True):
        """Rew/FFをnew_sec秒にするためTempoを逆算して更新。"""
        if new_sec<=0:
            self._st("Invalid value"); return
        try:
            b=int(self._beat_edit.text())
            bar=float(self._bar_edit.text())
        except:
            self._st("Invalid Beat/Bar"); return
        if b<=0 or bar<=0:
            self._st("Invalid Beat/Bar"); return
        new_tempo=60.0*b*bar/new_sec
        if new_tempo<30.0 or new_tempo>300.0:
            self._st(f"Tempo out of range (30-300): {new_tempo:.1f}")
            if revert_on_error:
                sec=self._rewff_sec()
                self._rewff_lbl.setText(f"{sec:.1f}s")
            return
        new_tempo=round(new_tempo*10)/10
        self._tempo=new_tempo
        self._tempo_edit.setText(f"{new_tempo:.1f}")
        self._update_rewff()

    # ──────────────────────────────────────
    # Speed / Key
    # ──────────────────────────────────────
    def _on_spd(self, v):
        self.engine.set_speed(v, self._st)
        self._spd_lbl.set_value(self.engine.speed)
        self._spd_lbl.setText(f"×{self.engine.speed:.1f}")

    def _key_text(self, v):
        """Keyの表示文字列。0のときは「±0」、それ以外は符号付き整数。"""
        v=int(round(v))
        return "±0" if v==0 else f"{v:+d}"

    def _fine_text(self, v):
        """Fineの表示文字列。0のときは「±0.00」、それ以外は符号付き小数。"""
        return "±0.00" if abs(v)<1e-9 else f"{v:+.2f}"

    def _on_key(self, v):
        self.engine.set_semitones(int(round(v)), self._st)
        self._key_lbl.set_value(self.engine.semitones)
        self._key_lbl.setText(self._key_text(self.engine.semitones))

    def _on_fine(self, v):
        self.engine.set_fine_semi(v, self._st)
        self._fine_lbl.set_value(self.engine.fine_semi)
        self._fine_lbl.setText(self._fine_text(self.engine.fine_semi))

    # ──────────────────────────────────────
    # Tempo Detection
    # ──────────────────────────────────────
    def _set_tempo_inputs_enabled(self, enabled):
        """Rew/FF〜Bar の入力欄をまとめて有効/無効（テンポ検出中はグレーアウト）"""
        widgets=[self._rewff_lbl, self._tempo_edit, self._beat_edit, self._bar_edit]
        for w in widgets:
            w.setEnabled(enabled)
            if enabled:
                if w is self._rewff_lbl:
                    w.setStyleSheet(w._normal_style)
                else:
                    w.setStyleSheet(f"color:{FG}; background:{BG3}; border:1px solid {BORDER}; padding:1px 4px;")
            else:
                w.setStyleSheet(f"color:{FG2}; background:{BG}; border:1px solid {BORDER}; padding:1px 4px;")

    def _tempo_detect(self):
        if self.engine.data is None: self._st("Load a file first"); return
        # 再生中なら「停止ボタンを押した」扱い: 停止して現在位置を確定・固定
        if self.engine.playing:
            cur=self.engine.current_sec()
            self.engine.stop(); self._upd_play(False)
            self.engine.seek(cur)  # _src_pos と _played_orig を現在位置で一致させ固定
            self._pos_lbl.setText(self._fmt(cur))
        self._st("Detecting tempo...")
        self._set_tempo_inputs_enabled(False)  # 検出中はグレーアウト
        ctr=self.engine.current_sec()
        def worker():
            t=self.engine.estimate_tempo(ctr)
            if t:
                # テンポ(BPM)のみ反映。Beat(拍子)は検出しない／Barも変更しない。
                self._tempo_edit.setText(f"{t:.1f}")
                self._tempo=t
                # Beatが万一0以下なら4に補正（拍子は検出しないので通常は変化なし）
                try:
                    if int(self._beat_edit.text())<=0:
                        self._beat_edit.setText("4")
                except:
                    self._beat_edit.setText("4")
                self._update_rewff()
                self._st(f"Tempo detected: {t:.1f} BPM")
            else:
                self._st("Tempo detection failed")
            self._tempo_busy_sig.emit(True)  # グレーアウト解除（メインスレッドで実行）
        threading.Thread(target=worker,daemon=True).start()

    # ──────────────────────────────────────
    # Reset
    # ──────────────────────────────────────
    def _get_state(self):
        state = {
            "markers":   dict(self.engine.markers),
            "speed":     self.engine.speed,
            "semitones": self.engine.semitones,
            "fine_semi": self.engine.fine_semi,
            "tempo":     self._tempo,
            "beat":      self._beat,
            "bar":       self._bar,
            "position":  self.engine.current_sec(),
            "view_lo":   self._waveform._view_lo,
            "view_hi":   self._waveform._view_hi,
            "ab_active": self.engine.ab_active,
            "ear_active":self.engine.ear_active,
            "filter_lo": self.engine.filter_lo_idx,
            "filter_hi": self.engine.filter_hi_idx,
        }
        if self.engine._nsf is not None:
            nsf = self.engine._nsf
            state["nsf_track"] = nsf.cur_track
            state["nsf_ch_active"] = list(nsf.ch_active)
            # Save per-track sessions for all decoded tracks
            nsf_tracks = {}
            for tidx, td in nsf.track_data.items():
                if tidx == nsf.cur_track:
                    nsf_tracks[str(tidx)] = {
                        'position':  self.engine.current_sec(),
                        'markers':   dict(self.engine.markers),
                        'ch_active': list(nsf.ch_active),
                        'ab_active': self.engine.ab_active,
                        'ear_active': self.engine.ear_active,
                    }
                elif 'session' in td:
                    nsf_tracks[str(tidx)] = dict(td['session'])
            if nsf_tracks:
                state["nsf_tracks"] = nsf_tracks
        if self.engine._spc is not None:
            spc = self.engine._spc
            state["spc_track"] = spc.cur_track
            state["spc_ch_active"] = list(spc.ch_active)
        return state

    def _apply_state(self, state):
        if not state: return
        # マーカーのキーはJSONで文字列化されるため整数に戻す
        raw=state.get("markers", {})
        self.engine.markers = {int(k): float(v) for k,v in raw.items()}
        # 音量は再現しない（除く）。古いセッションでキーが無くてもデフォルト値を使う
        self._tempo=state.get("tempo",120.0); self._beat=state.get("beat",4); self._bar=state.get("bar",2.0)
        self._tempo_edit.setText(f"{self._tempo:.1f}")
        self._beat_edit.setText(str(self._beat))
        self._bar_edit.setText(f"{self._bar:.1f}")
        self._update_rewff()
        _spd=state.get("speed",1.0); _semi=state.get("semitones",0); _fine=state.get("fine_semi",0.0)
        if self.engine.speed!=_spd:
            self.engine.set_speed(_spd, self._st)
        if self.engine.semitones!=_semi:
            self.engine.set_semitones(_semi, self._st)
        if self.engine.fine_semi!=_fine:
            self.engine.set_fine_semi(_fine, self._st)
        self._spd_lbl.set_value(self.engine.speed)
        self._spd_lbl.setText(f"×{self.engine.speed:.1f}")
        self._key_lbl.set_value(self.engine.semitones)
        self._key_lbl.setText(self._key_text(self.engine.semitones))
        self._fine_lbl.set_value(self.engine.fine_semi)
        self._fine_lbl.setText(self._fine_text(self.engine.fine_semi))
        self._rebuild_markers()
        self._update_wf_ab()
        # フィルター(HPF/LPF)の状態を復元（保存が無い古いセッションはフィルター無し扱い）
        flo=state.get("filter_lo", None); fhi=state.get("filter_hi", None)
        try:
            if flo is not None and fhi is not None:
                self.engine.set_filter_range(flo, fhi)
            else:
                self.engine.reset_filter()
        except Exception as ex:
            _log(f"_apply_state filter err: {ex}")
            self.engine.reset_filter()
        self._filter_overlay.set_range(self.engine.filter_lo_idx, self.engine.filter_hi_idx)
        # 現在時刻（再生位置）を再現
        pos=state.get("position", 0.0)
        try:
            self.engine.seek(pos)
            self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(pos))
            if self._total>0: self._waveform.set_position(pos/self._total)
        except Exception as ex:
            _log(f"_apply_state position err: {ex}")
        # 波形の拡大表示範囲を復元
        vlo=state.get("view_lo",0.0); vhi=state.get("view_hi",1.0)
        if 0.0<=vlo<vhi<=1.0:
            self._waveform._view_lo=vlo; self._waveform._view_hi=vhi
            self._waveform.update(); self._sync_wf_scroll()
        # AB Repeat / Ear Mode の状態を復元
        if state.get("ab_active", False) and MARKER_A in self.engine.markers and MARKER_B in self.engine.markers:
            self.engine.ab_active=True
            self._ab_btn.setIcon(_get_icon("ab_repeat",self.S(28),"#FFD700"))
        elif state.get("ear_active", False) and MARKER_A in self.engine.markers and MARKER_B in self.engine.markers:
            self.engine.ear_active=True
            self._ear_btn.setIcon(_get_icon("ear",self.S(28),"#FFD700"))
            self._start_ear_blink()

    def _seek_to_start(self):
        """再生位置を先頭（00:00.0）にリセット（再生中でも停止してリセット）"""
        if self.engine.data is None: return
        if self.engine.playing or self.engine.paused:
            self.engine.stop()
            self._upd_play(False)
        self.engine.seek(0.0)
        self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(0.0))
        self._waveform.set_position(0)
        self._st("Reset to start [Shift+Space]")

    def _do_reset(self):
        if self.engine.data is None: return
        self.engine.stop()  # 再生中にリセットされた場合もフィーダーを確実に停止する
        # NSFモード: 全トラックの保存済みセッションをクリア（位置情報が残らないように）
        _nsf_r = self.engine._nsf
        if _nsf_r is not None:
            for _td in _nsf_r.track_data.values():
                _td.pop('session', None)
        self.engine.speed=1.0; self.engine.semitones=0; self.engine.fine_semi=0.0
        self.engine.markers={}; self.engine.ab_active=False; self.engine.ear_active=False
        self._tempo=120.0; self._beat=4; self._bar=2.0
        self._spd_lbl.set_value(1.0); self._spd_lbl.setText("×1.0")
        self._key_lbl.set_value(0);   self._key_lbl.setText("±0")
        self._fine_lbl.set_value(0.0); self._fine_lbl.setText("±0.00")
        self._tempo_edit.setText("120.0"); self._beat_edit.setText("4"); self._bar_edit.setText("2.0")
        self._update_rewff()
        self.engine.reset_filter()
        self._filter_overlay.set_range(self.engine.filter_lo_idx, self.engine.filter_hi_idx)
        self.engine.seek(0.0)
        self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(0.0))
        self._waveform.set_position(0); self._update_wf_ab()
        self._waveform.reset_view()
        self._rebuild_markers(); self._upd_play(False)
        self._ab_btn.setIcon(_get_icon("ab_repeat",self.S(28),FG))
        self._ear_btn.setIcon(_get_icon("ear",self.S(28),FG))
        self._stop_ear_blink()
        self._st("Reset [R]")

    def _do_cache_clear(self):
        """キャッシュクリア＆アプリ再起動（Shift+R / Shift+Reset All / テンキーENTER+9）"""
        from PyQt6.QtWidgets import QMessageBox
        ret = QMessageBox.question(self, "Clear Cache",
            "This will discard the current track, delete the cache folder, and restart the app.\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        _log("キャッシュクリア: 開始")
        self.engine.stop()
        import shutil
        try:
            shutil.rmtree(CACHE)
            _log(f"キャッシュクリア: {CACHE} 削除完了")
        except Exception as ex:
            _log(f"キャッシュクリア: 削除エラー {ex}")
        try:
            os.makedirs(CACHE, exist_ok=True)
        except Exception as ex:
            _log(f"キャッシュクリア: 再作成エラー {ex}")
        _log("キャッシュクリア: アプリ再起動")
        self.engine._file_hash = ""  # closeEventでのセッション保存を抑制
        subprocess.Popen([sys.executable] + sys.argv)
        QApplication.instance().quit()

    # ──────────────────────────────────────
    # マーカー操作
    # ──────────────────────────────────────
    def _goto_marker(self, n):
        if n in self.engine.markers:
            self.engine.goto_marker(n)
            # 再生状態は変えず、表示位置だけ更新する（停止中でも見た目が追従するように）
            pos=self.engine.current_sec()
            self._pos_lbl.setText(self._fmt(pos))
            if self._total>0:
                self._waveform.set_position(pos/self._total)

    def _ear_mode(self):
        """耳コピモード。基本的にAB Repeatと同じ挙動。ABとは排他。"""
        _log(f"_ear_mode: ear_active={self.engine.ear_active} markers_AB={self.engine.markers.get(MARKER_A)},{self.engine.markers.get(MARKER_B)}")
        if self.engine.ear_active:
            self.engine.ear_active=False
            self._ear_btn.setIcon(_get_icon("ear",self.S(28),FG))
            self._stop_ear_blink()
            # ループ解除: 溜まったループ済み先読みを破棄し現在位置から作り直す
            if self.engine.playing: self.engine._rt_reset_from_current()
            self._update_wf_ab(); self._st("Ear Mode OFF")
        else:
            # 排他: AB RepeatがONならOFFにする
            if self.engine.ab_active:
                self.engine.ab_active=False
                self._ab_btn.setIcon(_get_icon("ab_repeat",self.S(28),FG))
            # マーカー記入漏れを補完してからON
            if self.engine.data is not None:
                self._fill_ab_markers()
            self.engine.ear_active=True
            self._ear_btn.setIcon(_get_icon("ear",self.S(28),"#FFD700"))
            self._start_ear_blink()
            self._update_wf_ab(); self._st("Ear Mode ON")

    def _start_ear_blink(self):
        self._ear_blink_phase=0.0
        self._ear_blink_dir=1
        self._ear_blink_timer.start(50)

    def _stop_ear_blink(self):
        self._ear_blink_timer.stop()
        self._apply_ear_blink_color(0.0)
        for n in (10,11):
            if n in self._mk_rows:
                _, tl = self._mk_rows[n]
                tl.setStyleSheet(tl._normal_style)
        if getattr(self,"_abdiff_lbl",None) is not None:
            self._abdiff_lbl.setStyleSheet(self._abdiff_lbl._normal_style)

    def _ear_blink_tick(self):
        self._ear_blink_phase += self._ear_blink_dir * (50.0/1000.0)
        if self._ear_blink_phase >= 1.0:
            self._ear_blink_phase = 1.0; self._ear_blink_dir = -1
        elif self._ear_blink_phase <= 0.0:
            self._ear_blink_phase = 0.0; self._ear_blink_dir = 1
        self._apply_ear_blink_color(self._ear_blink_phase)

    def _lerp_color(self, c1, c2, t):
        r=int(c1[0]+(c2[0]-c1[0])*t)
        g=int(c1[1]+(c2[1]-c1[1])*t)
        b=int(c1[2]+(c2[2]-c1[2])*t)
        return f"#{r:02X}{g:02X}{b:02X}"

    def _apply_ear_blink_color(self, t):
        normal=(0xBB,0xBB,0xBB); blue=(0x4A,0x90,0xE2)
        col=self._lerp_color(normal, blue, t)
        for attr in ("_rew_btn","_ff_btn"):
            b=getattr(self, attr, None)
            if b is not None:
                nm=getattr(b,"_icon_name",None)
                if nm: b.setIcon(_get_icon(nm,self.S(28),col))
        for n in (10,11):
            if n in self._mk_rows:
                _, tl = self._mk_rows[n]
                tl.setStyleSheet(f"color:{col}; border:1px solid {BORDER}; "
                                 f"background:{BG3}; padding:1px 4px;")
        # A<->B 差分表示も点滅（透明背景・枠なし）
        if getattr(self,"_abdiff_lbl",None) is not None:
            self._abdiff_lbl.setStyleSheet(f"QLineEdit{{color:{col}; background:{BG3}; border:1px solid {BORDER}; padding:1px 4px;}}")

    def _normalize_ab(self):
        """A>BになっていたらAとBを入れ替えて常にA<Bにする"""
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is not None and b is not None and a>b:
            self.engine.markers[MARKER_A], self.engine.markers[MARKER_B] = b, a
            self._refresh_marker(MARKER_A); self._refresh_marker(MARKER_B)

    def _rec_marker(self, n):
        if self.engine.data is None: return
        other = MARKER_B if n==MARKER_A else MARKER_A
        ov = self.engine.markers.get(other)
        cur = self.engine.current_sec()
        # もう一方と同じ時間ならNG（直前の状態を維持）
        if ov is not None and abs(cur-ov) < 0.05:
            self._st("A and B cannot be equal")
            return
        self.engine.set_marker(n)
        self._refresh_marker(n)
        self._normalize_ab()
        if n in (MARKER_A, MARKER_B): self._update_wf_ab()

    # ──────────────────────────────────────
    # Help / Zoom
    # ──────────────────────────────────────
    def _show_help(self):
        # py(exe)と同じフォルダの morokoshi_readme.pdf をWindows既定アプリで開く
        import os
        try:
            base=os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base=os.getcwd()
        pdf=os.path.join(base, "morokoshi_readme.pdf")
        if not os.path.exists(pdf):
            self._st("morokoshi_readme.pdf not found")
            return
        try:
            os.startfile(pdf)  # Windows既定アプリで開く
            self._st("Opening manual...")
        except Exception as ex:
            _log(f"_show_help err: {ex}")
            self._st("Could not open manual")

    def _on_volume_changed(self, v):
        # 音量はグローバル設定として保持（楽曲非依存）
        self._init_volume=v
        save_global_settings(self._scale, v)

    def _toggle_zoom(self):
        # 画面拡大トグル（1.0 ⇔ 2.0）。UIを作り直して全体をスケール
        self._scale = 1.0 if self._scale>=2.0 else 2.0
        # グローバル設定を保存（音量も現在値で）
        try: vol=self._vol_slider.value()
        except Exception: vol=self._init_volume
        save_global_settings(self._scale, vol)
        self._init_volume=vol
        # フォントサイズを含むスタイルシートを更新
        app=QApplication.instance()
        if app is not None: app.setStyleSheet(app_stylesheet(self._scale))
        self._rebuild_window()

    def _rebuild_window(self):
        # 現在の表示状態を保持しつつウィンドウUIを再構築
        _prev_st = self._msg.text() if hasattr(self, "_msg") else ""
        wf = self._waveform.waveform if hasattr(self,"_waveform") else None
        vlo = self._waveform._view_lo if hasattr(self,"_waveform") else 0.0
        vhi = self._waveform._view_hi if hasattr(self,"_waveform") else 1.0
        pos = self.engine.current_sec()
        # 旧UIを破棄して作り直し
        old=self.centralWidget()
        self.setFixedSize(self.S(375), self.S(313))
        self._build_ui()
        if old is not None:
            old.deleteLater()
        # 状態を復元
        self._dur_lbl.setText(self._fmt(self._total))
        self._pos_lbl.setText(self._fmt(pos))
        self._tempo_edit.setText(f"{self._tempo:.1f}")
        self._beat_edit.setText(str(self._beat))
        self._bar_edit.setText(f"{self._bar:.1f}")
        self._spd_lbl.set_value(self.engine.speed)
        self._spd_lbl.setText(f"×{self.engine.speed:.1f}")
        self._key_lbl.set_value(self.engine.semitones)
        self._key_lbl.setText(self._key_text(self.engine.semitones))
        self._fine_lbl.set_value(self.engine.fine_semi)
        self._fine_lbl.setText(self._fine_text(self.engine.fine_semi))
        self._update_rewff()
        self._rebuild_markers()
        if wf is not None:
            self._waveform.set_waveform(wf)
            self._waveform.set_total(self._total)
            self._waveform._view_lo=vlo; self._waveform._view_hi=vhi
            if self._total>0: self._waveform.set_position(pos/self._total)
        self._update_wf_ab()
        self._sync_wf_scroll()
        # AB/Earアイコンの状態を反映
        if self.engine.ab_active:
            self._ab_btn.setIcon(_get_icon("ab_repeat",self.S(28),"#FFD700"))
        if self.engine.ear_active:
            self._ear_btn.setIcon(_get_icon("ear",self.S(28),"#FFD700"))
            self._start_ear_blink()
        # NSF/SPCモード復元
        is_nsf = self.engine._nsf is not None
        is_spc = self.engine._spc is not None
        if is_nsf:
            self._mode_stack.setCurrentIndex(1)
        elif is_spc:
            self._mode_stack.setCurrentIndex(2)
        else:
            self._mode_stack.setCurrentIndex(0)
        if is_nsf:
            self._spec_timer.stop(); self._nsf_update_panel()
        elif is_spc:
            self._spec_timer.stop(); self._spc_update_panel()
        else:
            self._spec_timer.start(40)
        self._upd_play(self.engine.playing and not self.engine.paused)
        if _prev_st:
            self._msg.setText(_prev_st)
        self.setFocus()

    # ──────────────────────────────────────
    # ファイル
    # ──────────────────────────────────────
    def _open(self):
        import os
        # 前回開いたファイルのフォルダ → 無ければ %USERPROFILE%\Music
        start_dir = self._load_last_folder()
        if not start_dir or not os.path.isdir(start_dir):
            profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
            start_dir = os.path.join(profile, "Music")
        if not os.path.isdir(start_dir):
            start_dir = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        path,_=QFileDialog.getOpenFileName(self,"Open Media File",start_dir,
            "Media (*.mp3 *.mp4 *.wav *.flac *.aac *.ogg *.m4a *.wma *.opus *.webm *.avi *.mkv *.mov *.nsf *.spc *.zip);;NSF (*.nsf);;SPC (*.spc *.zip);;All (*.*)")
        if path:
            folder = os.path.dirname(os.path.abspath(path))
            self._last_folder = folder
            self._save_last_folder(folder)
            self._load(path)

    def _last_folder_path(self):
        import os
        return os.path.join(CACHE, "last_folder.txt")

    def _save_last_folder(self, folder):
        try:
            with open(self._last_folder_path(), "w", encoding="utf-8") as f:
                f.write(folder)
        except Exception as ex:
            _log(f"_save_last_folder err: {ex}")

    def _load_last_folder(self):
        import os
        try:
            p=self._last_folder_path()
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return f.read().strip()
        except Exception as ex:
            _log(f"_load_last_folder err: {ex}")
        return getattr(self, "_last_folder", "")

    def _load(self, path):
        _log(f"_load: path={path}")
        prev=self.engine._file_hash
        if prev: save_session(prev, self._get_state())
        fname = os.path.basename(path)
        self.setWindowTitle(f"Morokoshi Time - {fname}")
        self.engine.stop()
        threading.Thread(target=self._load_th, args=(path,), daemon=True).start()

    def _load_th(self, path):
        _log(f"_load_th: start path={path}")
        try:
            tot=self.engine.load(path, self._st)
            _log(f"_load_th: loaded tot={tot} data_is_None={self.engine.data is None} _proc_is_None={self.engine._proc is None}")
            wf=self.engine.get_waveform(700)
            session=load_session(self.engine._file_hash)
            self._load_done_sig.emit(tot, wf, session)
        except Exception as ex:
            self._status_sig.emit(f"Load failed: {ex}")

    @pyqtSlot(float, object, object)
    def _on_load_done(self, tot, wf, session):
        self._total=tot
        self._waveform.set_waveform(wf); self._waveform.set_position(0)
        self._waveform.set_total(tot); self._waveform.reset_view()
        self._sync_wf_scroll()
        self._dur_lbl.setText(self._fmt(tot))
        self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(0.0))
        # NSF / SPC モード切り替え
        is_nsf = self.engine._nsf is not None
        is_spc = self.engine._spc is not None
        if is_nsf:
            self._mode_stack.setCurrentIndex(1)
        elif is_spc:
            self._mode_stack.setCurrentIndex(2)
        else:
            self._mode_stack.setCurrentIndex(0)
        if is_nsf:
            self._spec_timer.stop()
            self._nsf_update_panel()
            nsf = self.engine._nsf
            td = nsf.track_data.get(nsf.cur_track, {})
            self._nsf_set_dur_editable(not td.get('natural_end', True))
        elif is_spc:
            self._spec_timer.stop()
            self._spc_update_panel()
            self._nsf_set_dur_editable(False)
        else:
            self._spec_timer.start(40)
            self._nsf_set_dur_editable(False)
        if session: self._apply_state(session)
        else: self._do_reset()
        # Restore per-track NSF sessions for all decoded tracks
        if is_nsf and session:
            saved_track = session.get("nsf_track", 0)
            nsf = self.engine._nsf
            # Load all per-track sessions from nsf_tracks; fall back to legacy single-track fields
            raw_tracks = session.get('nsf_tracks', {})
            if not raw_tracks and session.get('nsf_ch_active') is not None:
                # Legacy: build single entry for saved_track from top-level session fields
                raw_tracks = {
                    str(saved_track): {
                        'position':  float(session.get('position', 0.0)),
                        'markers':   {int(k): float(v) for k, v in session.get('markers', {}).items()},
                        'ch_active': session.get('nsf_ch_active'),
                        'ab_active': bool(session.get('ab_active', False)),
                        'ear_active': bool(session.get('ear_active', False)),
                    }
                }
            # Populate _pending_track_sessions for all saved tracks
            nsf._pending_track_sessions = {int(k): v for k, v in raw_tracks.items()}
            if isinstance(saved_track, int) and 0 < saved_track < nsf.track_count:
                self._nsf_pending_session = session  # for speed/key/tempo/filter via _apply_state
                self._nsf_set_track(saved_track)
            else:
                # Staying on track 0: apply its session (ch_active) directly
                ts0 = nsf._pending_track_sessions.pop(0, None)
                if ts0 and 'ch_active' in ts0:
                    ch_ac = ts0.get('ch_active') or []
                    td0 = nsf.track_data.get(0)
                    if td0 and ch_ac and len(ch_ac) == nsf.ch_count:
                        nsf.ch_active = [bool(x) for x in ch_ac]
                        nsf.track_data[0]['session'] = ts0
                        new_mask = sum((1 << i) for i in range(nsf.ch_count)
                                       if i < len(nsf.ch_active) and nsf.ch_active[i]
                                       and i < len(td0['ch_used']) and td0['ch_used'][i])
                        if new_mask != td0.get('ch_mask', -1) and nsf._nsf_raw is not None:
                            self._nsf_start_ch_render(new_mask, 0, nsf._nsf_raw,
                                                       nsf.ch_count, td0.get('decoded_sec', 0))
                self._nsf_update_panel()
        # SPC セッション復元
        if is_spc and session:
            spc = self.engine._spc
            saved_track = session.get("spc_track", 0)
            ch_ac = session.get("spc_ch_active")
            if ch_ac and len(ch_ac) == spc.ch_count:
                spc.ch_active = [bool(x) for x in ch_ac]
                td0 = spc.track_data.get(0)
                if td0:
                    new_mask = sum((1 << i) for i in range(spc.ch_count)
                                   if i < len(spc.ch_active) and spc.ch_active[i]
                                   and i < len(td0['ch_used']) and td0['ch_used'][i])
                    if new_mask != td0.get('ch_mask', -1):
                        self._spc_start_ch_render(new_mask, 0, td0.get('decoded_sec', SPC_DEFAULT_DUR_SEC))
            if spc.is_zip and isinstance(saved_track, int) and 0 < saved_track < spc.track_count:
                self._spc_set_track(saved_track)
            else:
                self._spc_update_panel()

    # ──────────────────────────────────────
    # SPC 専用メソッド
    # ──────────────────────────────────────
    def _spc_update_panel(self):
        """SPCパネルの表示を現在の状態に合わせて更新する"""
        spc = self.engine._spc
        if spc is None: return
        td = spc.track_data.get(spc.cur_track)
        if td is None: return
        self._spc_panel.set_zip_mode(spc.is_zip)
        meta = spc.track_metas[spc.cur_track] if spc.cur_track < len(spc.track_metas) else {}
        parts = [p for p in [meta.get('game',''), meta.get('song','')] if p]
        if not parts and spc.spc_names:
            parts = [spc.spc_names[spc.cur_track] if spc.cur_track < len(spc.spc_names) else ""]
        title = " / ".join(parts)
        self._spc_panel.set_info(spc.track_count, spc.cur_track, title)
        self._spc_panel.set_channels(spc.ch_active, td['ch_used'])
        if spc.is_zip:
            tt_names = []
            for i, m in enumerate(spc.track_metas):
                name = m.get('song','') or (spc.spc_names[i] if i < len(spc.spc_names) else "")
                tt_names.append(name)
            self._spc_panel.set_track_titles(tt_names)

    def _spc_set_track(self, track_idx_0based):
        """SPCトラックを切り替える（ZIPモード用・バックグラウンド）"""
        if self._spc_loading: return
        spc = self.engine._spc
        if spc is None or not spc.is_zip: return
        self._spc_wf_views[spc.cur_track] = (
            self._waveform._view_lo, self._waveform._view_hi)
        self._spc_loading = True
        self._spc_panel.update_track_num(track_idx_0based)
        self._spc_panel.set_loading(True)
        self._st(f"SPC: Loading track {track_idx_0based+1}...")
        def do_set():
            try:
                dur = self.engine.spc_set_track(track_idx_0based, self._st)
                wf = self.engine.get_waveform(700)
                self._spc_track_done_sig.emit(dur, wf)
            except Exception as ex:
                self._spc_loading = False
                self._status_sig.emit(f"SPC track change failed: {ex}")
        threading.Thread(target=do_set, daemon=True).start()

    @pyqtSlot(float, object)
    def _on_spc_track_done(self, dur, wf):
        """SPCトラック切替完了後のUI更新"""
        self._spc_loading = False
        self._spc_panel.set_loading(False)
        self._total = dur
        self._waveform.set_waveform(wf)
        self._waveform.set_total(dur)
        spc = self.engine._spc
        saved_zoom = self._spc_wf_views.get(spc.cur_track) if spc else None
        if saved_zoom and 0.0 <= saved_zoom[0] < saved_zoom[1] <= 1.0:
            self._waveform._view_lo, self._waveform._view_hi = saved_zoom
            self._waveform.update()
        else:
            self._waveform.reset_view()
        pos = self.engine.current_sec()
        self._waveform.set_position(pos / dur if dur > 0 else 0)
        self._sync_wf_scroll()
        self._dur_lbl.setText(self._fmt(dur))
        self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(pos))
        self._rebuild_markers(); self._update_wf_ab()
        if self.engine.ab_active:
            self._ab_btn.setIcon(_get_icon("ab_repeat", self.S(28), "#FFD700"))
        else:
            self._ab_btn.setIcon(_get_icon("ab_repeat", self.S(28), FG))
        if self.engine.ear_active:
            self._ear_btn.setIcon(_get_icon("ear", self.S(28), "#FFD700"))
            self._start_ear_blink()
        else:
            self._ear_btn.setIcon(_get_icon("ear", self.S(28), FG))
            self._stop_ear_blink()
        self._spc_update_panel()
        self._st(f"SPC: Track {spc.cur_track+1 if spc else 1}")

    def _spc_on_ch_toggle(self, ch_idx, solo, reset):
        """SPCチャンネルON/OFFボタン押下"""
        if self._spc_loading or self._spc_ch_rendering: return
        new_ch_mask = self.engine._spc_toggle_channel(ch_idx, solo=solo, reset=reset)
        spc = self.engine._spc
        if spc is None: return
        td = spc.track_data.get(spc.cur_track)
        if td is None: return
        self._spc_panel.update_channel_states(spc.ch_active, td['ch_used'])
        if new_ch_mask == td.get('ch_mask'):
            wf = self.engine.get_waveform(700)
            self._waveform.set_waveform(wf); return
        self._spc_start_ch_render(new_ch_mask, spc.cur_track, td.get('decoded_sec', SPC_DEFAULT_DUR_SEC))

    def _spc_start_ch_render(self, ch_mask, track_idx, decoded_sec):
        """SPC ch切替バックグラウンドレンダリングを開始する"""
        self._spc_ch_rendering = True
        spc = self.engine._spc
        spc_raw = spc._spc_raws.get(track_idx) if spc else None
        if spc_raw is None:
            self._spc_ch_rendering = False; return
        def do_render():
            try:
                gme = _gme_load()
                if gme is None:
                    self._spc_ch_rendering = False; return
                wav, _, _ = _spc_render(gme, spc_raw, ch_mask, decoded_sec, trim_silence=False)
                self._spc_ch_render_done_sig.emit(wav, ch_mask, track_idx)
            except Exception as ex:
                self._spc_ch_rendering = False
                self._status_sig.emit(f"SPC ch render failed: {ex}")
        threading.Thread(target=do_render, daemon=True).start()

    @pyqtSlot(object, int, int)
    def _on_spc_ch_render_done(self, wav, ch_mask, track_idx):
        """SPC ch切替レンダリング完了後のUI更新"""
        self._spc_ch_rendering = False
        spc = self.engine._spc
        if spc is None or spc.cur_track != track_idx: return
        self.engine._spc_apply_new_wav(wav, ch_mask)
        wf = self.engine.get_waveform(700)
        self._waveform.set_waveform(wf)

    # ──────────────────────────────────────
    # NSF 専用メソッド
    # ──────────────────────────────────────
    def _nsf_update_panel(self):
        """NSFパネルの表示を現在の状態に合わせて更新する"""
        nsf=self.engine._nsf
        if nsf is None: return
        td=nsf.track_data.get(nsf.cur_track)
        if td is None: return
        if nsf.fmt=='NSFe' and nsf.track_titles:
            title=nsf.track_titles[nsf.cur_track] if nsf.cur_track<len(nsf.track_titles) else ""
        else:
            parts=[p for p in [nsf.game, nsf.author] if p]
            title=" / ".join(parts)
        self._nsf_panel.set_info(nsf.track_count, nsf.cur_track, title)
        self._nsf_panel.set_channels(nsf.ch_count, nsf.ch_names, nsf.ch_active, td['ch_used'],
                                     expansion_chips=nsf.expansion_chips or None)

    def _nsf_set_track(self, track_idx_0based):
        """NSFトラックを切り替える（バックグラウンドスレッド）"""
        if self._nsf_loading: return
        nsf=self.engine._nsf
        if nsf is None: return
        # 切替前のトラックのズーム状態を保存
        self._nsf_wf_views[nsf.cur_track] = (
            self._waveform._view_lo, self._waveform._view_hi)
        self._nsf_loading = True
        # 即時パネル番号更新（読み込み完了前でもUIに反映）
        self._nsf_panel.update_track_num(track_idx_0based)
        self._nsf_panel.set_loading(True)
        self._st(f"NSF: Loading track {track_idx_0based+1}...")
        def do_set():
            try:
                dur=self.engine.nsf_set_track(track_idx_0based, self._st)
                wf=self.engine.get_waveform(700)
                self._nsf_track_done_sig.emit(dur, wf)
            except Exception as ex:
                self._nsf_loading = False
                self._nsf_pending_session = None
                self._status_sig.emit(f"NSF track change failed: {ex}")
        threading.Thread(target=do_set, daemon=True).start()

    @pyqtSlot(float, object)
    def _on_nsf_track_done(self, dur, wf):
        """NSFトラック切替完了後のUI更新"""
        self._nsf_loading = False
        self._nsf_panel.set_loading(False)
        self._total=dur
        self._waveform.set_waveform(wf)
        self._waveform.set_total(dur)
        # 保存済みズームがあれば復元、なければリセット
        nsf_for_zoom = self.engine._nsf
        saved_zoom = self._nsf_wf_views.get(nsf_for_zoom.cur_track) if nsf_for_zoom else None
        if saved_zoom and 0.0 <= saved_zoom[0] < saved_zoom[1] <= 1.0:
            self._waveform._view_lo, self._waveform._view_hi = saved_zoom
            self._waveform.update()
        else:
            self._waveform.reset_view()
        self._sync_wf_scroll()
        self._dur_lbl.setText(self._fmt(dur))
        # セッション保存があれば位置を復元、なければ先頭へ
        pos = self.engine.current_sec()
        self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(pos))
        self._waveform.set_position(pos / dur if dur > 0 else 0)
        self._rebuild_markers()
        self._update_wf_ab()
        # AB/Ear ボタン状態を復元
        if self.engine.ab_active:
            self._ab_btn.setIcon(_get_icon("ab_repeat", self.S(28), "#FFD700"))
        else:
            self._ab_btn.setIcon(_get_icon("ab_repeat", self.S(28), FG))
        if self.engine.ear_active:
            self._ear_btn.setIcon(_get_icon("ear", self.S(28), "#FFD700"))
            self._start_ear_blink()
        else:
            self._ear_btn.setIcon(_get_icon("ear", self.S(28), FG))
            self._stop_ear_blink()
        self._upd_play(False)
        self._nsf_update_panel()
        nsf=self.engine._nsf
        if nsf:
            td = nsf.track_data.get(nsf.cur_track, {})
            self._nsf_set_dur_editable(not td.get('natural_end', True))
        fname=os.path.basename(nsf.path) if nsf else ""
        trk=nsf.cur_track+1 if nsf else 0
        tot=nsf.track_count if nsf else 0
        self._st(f"NSF: {trk}/{tot}  {fname}")
        # Apply session saved at file load (position, markers, etc. for restored track)
        pending = self._nsf_pending_session
        if pending is not None:
            self._nsf_pending_session = None
            self._apply_state(pending)

    # ──────────────────────────────────────
    # NSF 総再生時間 編集モード
    # ──────────────────────────────────────
    def _nsf_set_dur_editable(self, editable):
        """NSF 総再生時間ラベルの編集可/不可を切り替える"""
        self._nsf_dur_editable = editable
        if editable:
            self._nsf_dur_blink_phase = 0.0
            self._nsf_dur_blink_dir = 1
            self._nsf_dur_blink_timer.start(50)
        else:
            self._nsf_dur_blink_timer.stop()
            self._dur_lbl.setStyleSheet(f"color:{FG2};")

    def _nsf_dur_blink_tick(self):
        self._nsf_dur_blink_phase += self._nsf_dur_blink_dir * (50.0 / 1000.0)
        if self._nsf_dur_blink_phase >= 1.0:
            self._nsf_dur_blink_phase = 1.0; self._nsf_dur_blink_dir = -1
        elif self._nsf_dur_blink_phase <= 0.0:
            self._nsf_dur_blink_phase = 0.0; self._nsf_dur_blink_dir = 1
        t = self._nsf_dur_blink_phase
        # Ear modeの青点滅と同じ明度感: #BBBBBB（薄グレー）→ #CC4444（中赤）
        r = int(0xBB + (0xCC - 0xBB) * t)
        g = int(0xBB + (0x44 - 0xBB) * t)
        b = int(0xBB + (0x44 - 0xBB) * t)
        self._dur_lbl.setStyleSheet(f"color:#{r:02X}{g:02X}{b:02X};")

    def _dur_lbl_enter(self, e):
        if self._nsf_dur_editable:
            self._dur_lbl.setCursor(Qt.CursorShape.SizeVerCursor)

    def _dur_lbl_leave(self, e):
        self._dur_lbl.unsetCursor()

    def _dur_lbl_press(self, e):
        if not self._nsf_dur_editable: return
        if e.button() == Qt.MouseButton.LeftButton:
            self._nsf_dur_drag_y    = e.position().y()
            nsf = self.engine._nsf
            if nsf:
                td = nsf.track_data.get(nsf.cur_track, {})
                self._nsf_dur_drag_base = td.get('view_sec', NSF_DEFAULT_DUR_SEC)

    def _dur_lbl_move(self, e):
        if not self._nsf_dur_editable: return
        if not (e.buttons() & Qt.MouseButton.LeftButton): return
        if self._nsf_dur_drag_y is None or self._nsf_dur_drag_base is None: return
        dy = self._nsf_dur_drag_y - e.position().y()
        steps = int(dy // 20)
        if steps == 0: return
        nsf = self.engine._nsf
        if nsf is None: return
        td = nsf.track_data.get(nsf.cur_track, {})
        decoded = td.get('decoded_sec', NSF_DEFAULT_DUR_SEC)
        new_sec = self._nsf_dur_drag_base + steps * NSF_EXT_STEP_SEC
        new_sec = max(NSF_MIN_DURATION, min(NSF_MAX_DUR_SEC, new_sec))
        # ラベルをプレビュー更新（実際の延長はリリース時）
        self._dur_lbl.setText(self._fmt(new_sec))

    def _dur_lbl_release(self, e):
        if not self._nsf_dur_editable: return
        if e.button() != Qt.MouseButton.LeftButton: return
        if self._nsf_dur_drag_y is None or self._nsf_dur_drag_base is None: return
        dy = self._nsf_dur_drag_y - e.position().y()
        steps = int(dy // 20)
        self._nsf_dur_drag_y = None; self._nsf_dur_drag_base = None
        if steps == 0:
            # 元の値に戻す
            nsf = self.engine._nsf
            if nsf:
                td = nsf.track_data.get(nsf.cur_track, {})
                self._dur_lbl.setText(self._fmt(td.get('view_sec', NSF_DEFAULT_DUR_SEC)))
            return
        nsf = self.engine._nsf
        if nsf is None or self._nsf_loading: return
        td = nsf.track_data.get(nsf.cur_track, {})
        base = td.get('view_sec', NSF_DEFAULT_DUR_SEC)
        new_sec = base + steps * NSF_EXT_STEP_SEC
        new_sec = max(NSF_MIN_DURATION, min(NSF_MAX_DUR_SEC, new_sec))
        self._nsf_start_extend(nsf.cur_track, new_sec)

    def _dur_lbl_wheel(self, e):
        if not self._nsf_dur_editable: return
        nsf = self.engine._nsf
        if nsf is None or self._nsf_loading: return
        delta = e.angleDelta().y()
        if delta == 0: return
        step = NSF_EXT_STEP_SEC if delta > 0 else -NSF_EXT_STEP_SEC
        td = nsf.track_data.get(nsf.cur_track, {})
        cur = td.get('view_sec', NSF_DEFAULT_DUR_SEC)
        new_sec = max(NSF_MIN_DURATION, min(NSF_MAX_DUR_SEC, cur + step))
        if new_sec == cur: return
        self._nsf_start_extend(nsf.cur_track, new_sec)

    def _nsf_start_extend(self, track_idx, new_sec):
        """NSFトラックの再生時間を変更する（バックグラウンド）"""
        if self._nsf_loading: return
        # Prevent shortening below current playback position
        cur_sec = self.engine.current_sec()
        if new_sec < cur_sec:
            self._st("Cannot shorten below current position")
            return
        self._nsf_loading = True
        def do_extend():
            try:
                dur, natural_end = self.engine.nsf_extend_track(track_idx, new_sec, self._st)
                wf = self.engine.get_waveform(700)
                self._nsf_extend_done_sig.emit(dur, natural_end, wf)
            except Exception as ex:
                self._nsf_loading = False
                self._status_sig.emit(f"NSF duration change failed: {ex}")
        threading.Thread(target=do_extend, daemon=True).start()

    @pyqtSlot(float, bool, object)
    def _on_nsf_extend_done(self, dur, natural_end, wf):
        """NSF延長完了後のUI更新"""
        self._nsf_loading = False
        self._total = dur
        self._waveform.set_waveform(wf)
        self._waveform.set_total(dur)
        # 延長後はズームを保持（reset_view()しない）
        self._waveform.update(); self._sync_wf_scroll()
        self._dur_lbl.setText(self._fmt(dur))
        if natural_end:
            self._nsf_set_dur_editable(False)
        nsf = self.engine._nsf
        if nsf:
            td = nsf.track_data.get(nsf.cur_track)
            if td:
                self._nsf_panel.update_channel_states(nsf.ch_active, td['ch_used'])
        # 短縮した場合、現在位置・マーカーが範囲外になることがある → リセット
        cur_sec = self.engine.current_sec()
        if cur_sec > dur:
            self.engine.seek(0.0)
            self._pos_lbl.clear_highlight(); self._pos_lbl.setText(self._fmt(0.0))
            self._waveform.set_position(0)
        clipped = False
        for n in list(self.engine.markers.keys()):
            if self.engine.markers[n] > dur:
                del self.engine.markers[n]; clipped = True
        if clipped:
            self._rebuild_markers(); self._update_wf_ab()
            if self.engine.ab_active and (MARKER_A not in self.engine.markers or MARKER_B not in self.engine.markers):
                self.engine.ab_active = False
                self._ab_btn.setIcon(_get_icon("ab_repeat", self.S(28), FG))
            if self.engine.ear_active and (MARKER_A not in self.engine.markers or MARKER_B not in self.engine.markers):
                self.engine.ear_active = False
                self._ear_btn.setIcon(_get_icon("ear", self.S(28), FG)); self._stop_ear_blink()
        self._st(f"NSF: duration set to {self._fmt(dur)}")

    def _nsf_on_ch_toggle(self, ch_idx, solo, reset):
        """チャンネルON/OFFボタン押下"""
        if self._nsf_loading or self._nsf_ch_rendering: return
        new_ch_mask = self.engine._nsf_toggle_channel(ch_idx, solo=solo, reset=reset)
        nsf = self.engine._nsf
        if nsf is None: return
        td = nsf.track_data.get(nsf.cur_track)
        if td is None: return
        self._nsf_panel.update_channel_states(nsf.ch_active, td['ch_used'])
        if new_ch_mask == td.get('ch_mask'):
            wf = self.engine.get_waveform(700)
            self._waveform.set_waveform(wf); return
        self._nsf_start_ch_render(new_ch_mask, nsf.cur_track, nsf._nsf_raw,
                                  nsf.ch_count, td.get('decoded_sec', NSF_DEFAULT_DUR_SEC))

    def _nsf_toggle_ch_by_key(self, ch_idx):
        """キーボードショートカットによるチャンネルソロ"""
        if self._nsf_loading or self._nsf_ch_rendering: return
        nsf = self.engine._nsf
        if nsf is None or ch_idx >= nsf.ch_count: return
        new_ch_mask = self.engine._nsf_toggle_channel(ch_idx, solo=True)
        td = nsf.track_data.get(nsf.cur_track)
        if td is None: return
        self._nsf_panel.update_channel_states(nsf.ch_active, td['ch_used'])
        if new_ch_mask == td.get('ch_mask'):
            wf = self.engine.get_waveform(700)
            self._waveform.set_waveform(wf); return
        self._nsf_start_ch_render(new_ch_mask, nsf.cur_track, nsf._nsf_raw,
                                  nsf.ch_count, td.get('decoded_sec', NSF_DEFAULT_DUR_SEC))

    def _nsf_start_ch_render(self, ch_mask, track_idx, nsf_raw, ch_count, decoded_sec):
        """ch切替のバックグラウンドレンダリングを開始する"""
        self._nsf_ch_rendering = True
        def do_render():
            try:
                gme = _gme_load()
                if gme is None:
                    self._nsf_ch_rendering = False; return
                wav, _, _ = _nsf_render(gme, nsf_raw, track_idx, ch_mask, ch_count, decoded_sec)
                self._nsf_ch_render_done_sig.emit(wav, ch_mask, track_idx)
            except Exception as ex:
                self._nsf_ch_rendering = False
                self._status_sig.emit(f"NSF ch render failed: {ex}")
        threading.Thread(target=do_render, daemon=True).start()

    @pyqtSlot(object, int, int)
    def _on_nsf_ch_render_done(self, wav, ch_mask, track_idx):
        """ch切替レンダリング完了後のUI更新"""
        self._nsf_ch_rendering = False
        nsf = self.engine._nsf
        if nsf is None or nsf.cur_track != track_idx: return
        self.engine._nsf_apply_new_wav(wav, ch_mask)
        wf = self.engine.get_waveform(700)
        self._waveform.set_waveform(wf)

    # ──────────────────────────────────────
    # tick
    # ──────────────────────────────────────
    def _update_spectrum(self):
        sp=getattr(self,"_spectrum",None)
        if sp is None: return
        try:
            levels=self.engine.get_spectrum()
        except Exception:
            return
        sp.set_levels(levels)

    def _on_tick(self, pos, total):
        if total==0: return
        if not self.engine.playing:
            # エンジン停止直後の残留シグナルによる位置上書きを防ぐ
            self._upd_play(False); return
        self._pos_lbl.setText(self._fmt(pos))
        _following = not self.engine.paused
        self._waveform.set_position(pos/total, follow=_following)

    def _on_wf_seek(self, ratio):
        if self._total>0:
            pos=ratio*self._total
            self.engine.seek(pos)
            self._pos_lbl.setText(self._fmt(pos))
            self._waveform.set_position(ratio)

    def _on_wf_position_drag(self, ratio):
        # 現在位置線をドラッグ中: 時間表示だけライブ更新（実際のシークはリリース時にseekedで行う）
        if self._total>0:
            pos=ratio*self._total
            self._pos_lbl.clear_highlight()
            self._pos_lbl.setText(self._fmt(pos))

    def _on_wf_marker_drag(self, n, ratio):
        # A/Bマーカー線を波形上でドラッグ中: そのマーカーを移動する。
        # Ear Mode中はA-B間の差分を保ったまま両方を連動して動かす。
        # 通常時は相手マーカーを追い越さない（最小0.1s間隔を保つ）。
        # ループ中(AB/Ear ON)の再生時は、帯ドラッグと同様に再生位置を追い越さないよう制限する。
        if self._total<=0: return
        new_sec=max(0.0, min(self._total, ratio*self._total))
        other = MARKER_B if n==MARKER_A else MARKER_A
        looping_now = self.engine.playing and (self.engine.ab_active or self.engine.ear_active)
        if self.engine.ear_active and MARKER_A in self.engine.markers and MARKER_B in self.engine.markers:
            cur_n=self.engine.markers[n]; other_v=self.engine.markers[other]
            delta=new_sec-cur_n  # ドラッグで生じる移動量（A,B同時に同じだけ動かす）
            if looping_now:
                lo=min(cur_n,other_v); hi=max(cur_n,other_v)
                cur_pos=self.engine.current_sec()
                new_lo=lo+delta; new_hi=hi+delta
                if new_lo > cur_pos:
                    delta = cur_pos-lo
                elif new_hi < cur_pos:
                    delta = cur_pos-hi
            final_n=cur_n+delta; final_other=other_v+delta
            if final_n < 0 or final_other < 0 or final_n > self._total or final_other > self._total:
                return  # どちらかが範囲外になる場合は動かさない
            self.engine.markers[n]=final_n
            self.engine.markers[other]=final_other
            self._refresh_marker(other)
        else:
            ov = self.engine.markers.get(other)
            if ov is not None:
                if n==MARKER_A:
                    new_sec=min(new_sec, ov-0.1)
                else:
                    new_sec=max(new_sec, ov+0.1)
                new_sec=max(0.0, min(self._total, new_sec))
            if looping_now:
                cur_pos=self.engine.current_sec()
                if n==MARKER_A:
                    new_sec=min(new_sec, cur_pos)
                else:
                    new_sec=max(new_sec, cur_pos)
            self.engine.markers[n]=new_sec
        self._refresh_marker(n)
        self._update_wf_ab()

    def _on_ab_drag(self, delta_ratio):
        # 波形の黄色部分(A〜B)ドラッグ → A,Bマーカーを同時移動。現在時間は変えない
        if self._total<=0: return
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None or b is None: return
        ds=delta_ratio*self._total  # 移動量(秒)
        lo=min(a,b); hi=max(a,b)
        # 楽曲範囲(0〜total)で頭打ち
        if lo+ds < 0:        ds = -lo
        if hi+ds > self._total: ds = self._total-hi
        # ループ中(AB/Ear ON)の再生時のみ、再生位置を追い越さないよう制限
        # （両方OFFの通常再生・停止中は自由に追い越せる）
        if self.engine.playing and (self.engine.ab_active or self.engine.ear_active):
            cur=self.engine.current_sec()
            new_lo=lo+ds; new_hi=hi+ds
            if new_lo > cur:      # 範囲が再生位置を追い越して右へ
                ds = cur-lo
            elif new_hi < cur:    # 範囲が再生位置を追い越して左へ
                ds = cur-hi
        if abs(ds) < 1e-9: return
        self.engine.markers[MARKER_A]=a+ds
        self.engine.markers[MARKER_B]=b+ds
        self._refresh_marker(MARKER_A); self._refresh_marker(MARKER_B)
        self._update_wf_ab()

    def _on_wf_double_click(self, ratio):
        # 波形ダブルクリックでマーカーをセット
        if self._total<=0: return
        t=ratio*self._total
        a=self.engine.markers.get(MARKER_A); b=self.engine.markers.get(MARKER_B)
        if a is None and b is None:
            target=10  # 両方未入力 → A
        elif a is None:
            target=10  # A未入力 → A
        elif b is None:
            target=11  # B未入力 → B
        else:
            # 両方入力済み → クリック位置に近い方のマーカーを置き換え
            target = 10 if abs(t-a) <= abs(t-b) else 11
        self.engine.markers[target]=t
        self._refresh_marker(target)
        self._normalize_ab()  # A>Bなら入れ替え
        self._update_wf_ab()
        self._st(f"Marker {'A' if target==10 else 'B'} set")

    def _on_wf_scroll(self, value):
        # スクロールバー操作 → 波形の表示範囲を移動
        wf=self._waveform
        span=wf._vspan()
        if span>=1.0: return
        lo=(value/1000.0)
        lo=max(0.0, min(1.0-span, lo))
        wf._view_lo=lo; wf._view_hi=lo+span
        wf._last_manual=time.time()  # 手動操作として追従を一時抑制
        _log(f"WF scrollbar: value={value} span={span:.4f} view=[{lo:.4f},{lo+span:.4f}] playing={self.engine.playing}")
        wf.update()

    def _sync_wf_scroll(self):
        # 波形の表示範囲 → スクロールバーに反映
        wf=self._waveform
        span=wf._vspan()
        sb=self._wf_scroll
        sb.blockSignals(True)
        if span>=1.0:
            sb.setRange(0,0)
        else:
            sb.setRange(0, int(1000*(1.0-span)))
            sb.setPageStep(int(1000*span))
            sb.setValue(int(wf._view_lo*1000))
        sb.blockSignals(False)

    # ──────────────────────────────────────
    # キーボード
    # ──────────────────────────────────────
    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if event.type()!=QEvent.Type.KeyPress: return False
        focused=QApplication.focusWidget()
        if isinstance(focused, QLineEdit): return False
        return self._handle_key(event)

    def _key_btn(self, vk, key, shift=False, keypad=False):
        """キーコードに対応するボタンを返す（フラッシュ用、トグル式は除外）"""
        K=Qt.Key
        if shift:
            # Shift+A/B（Set）は時間ボックスを光らせるのでボタンは光らせない
            if vk==65: return None
            if vk==66: return None
            if vk==82: return getattr(self,"_reset_btn",None)  # Shift+R → キャッシュクリア
            return None
        # テンキー裏ショートカット（トグル式のEar/ABは除外）
        if keypad:
            if key==K.Key_7: return getattr(self,"_open_btn",None)
            if key==K.Key_8: return getattr(self,"_tempo_btn",None)
            if key==K.Key_9: return getattr(self,"_reset_btn",None)
            if key==K.Key_1: return getattr(self,"_rew_btn",None)
            if key==K.Key_3: return getattr(self,"_ff_btn",None)
            if key==K.Key_4: return getattr(self,"_btn_marker_a",None)
            if key==K.Key_6: return getattr(self,"_btn_marker_b",None)
            if key==K.Key_Slash: return getattr(self,"_help_btn",None)
            if key==K.Key_Asterisk: return getattr(self,"_zoom_btn",None)
            # 5(Ear)/2(AB)/0(Play)はトグル式なので除外
            return None
        m={
            79:getattr(self,"_open_btn",None),
            84:getattr(self,"_tempo_btn",None),
            82:getattr(self,"_reset_btn",None),
            72:getattr(self,"_help_btn",None),
            90:getattr(self,"_zoom_btn",None),
            65:getattr(self,"_btn_marker_a",None),
            66:getattr(self,"_btn_marker_b",None),
        }
        if vk in m: return m[vk]
        if key==K.Key_Left:  return getattr(self,"_rew_btn",None)
        if key==K.Key_Right: return getattr(self,"_ff_btn",None)
        # ↑(Ear)はトグル式なのでフラッシュ除外
        return None

    def _flash_on(self, btn):
        if btn is None: return
        inner=getattr(btn,"_inner_btn",None)
        if inner is not None:  # →A/→Bボタン（ラッパー）
            inner.setDown(True); return
        if isinstance(btn, QPushButton) and btn.icon().isNull():
            # A/Bボタン（テキスト）→ :pressed スタイルを適用
            btn.setDown(True)
        else:
            # アイコンボタン → 黄色アイコンに
            nm=getattr(btn,"_icon_name",None)
            if nm: btn.setIcon(_get_icon(nm,self.S(28),"#FFD700"))

    def _flash_off(self, btn):
        if btn is None: return
        inner=getattr(btn,"_inner_btn",None)
        if inner is not None:
            inner.setDown(False); return
        if isinstance(btn, QPushButton) and btn.icon().isNull():
            btn.setDown(False)
        else:
            nm=getattr(btn,"_icon_name",None)
            if nm: btn.setIcon(_get_icon(nm,self.S(28),FG))

    def _handle_key(self, e):
        key=e.key(); K=Qt.Key
        shift=bool(e.modifiers()&Qt.KeyboardModifier.ShiftModifier)
        ctrl =bool(e.modifiers()&Qt.KeyboardModifier.ControlModifier)
        vk=e.nativeVirtualKey()

        # キー押下中フラッシュ（自動リピートでなければ）
        if not e.isAutoRepeat():
            _kp=bool(e.modifiers() & Qt.KeyboardModifier.KeypadModifier)
            _b=self._key_btn(vk, key, shift, keypad=_kp)
            if _b is not None: self._flash_on(_b)

        # Shift+A/B → マーカーをSet（現在時間を記録）
        if shift:
            # NSFモード: Shift+チャンネルキー → そのchのみON/OFF逆転（他ch影響なし）
            _nsf_sh = self.engine._nsf
            if _nsf_sh is not None and not bool(e.modifiers() & Qt.KeyboardModifier.KeypadModifier):
                # Shift changes e.key() for digit/symbol keys; use nativeVirtualKey for digits/OEM
                _SH_VK = {49:0, 50:1, 51:2, 52:3, 53:4, 54:5, 55:6, 56:7, 57:8, 48:9, 189:10}
                _SH_KEY = {
                    K.Key_AsciiCircum:11, K.Key_AsciiTilde:11, K.Key_Equal:11,
                    K.Key_Backslash:12, K.Key_Bar:12,
                }
                _nsf_sh_ch = _SH_VK.get(vk, _SH_KEY.get(key))
                if _nsf_sh_ch is not None:
                    if _nsf_sh_ch < _nsf_sh.ch_count:
                        self._nsf_on_ch_toggle(_nsf_sh_ch, solo=False, reset=False)
                    return True
            # SPCモード: Shift+1～8 → そのchのみON/OFF逆転
            _spc_sh = self.engine._spc
            if _spc_sh is not None and not bool(e.modifiers() & Qt.KeyboardModifier.KeypadModifier):
                _SPC_VK = {49:0, 50:1, 51:2, 52:3, 53:4, 54:5, 55:6, 56:7}
                _spc_sh_ch = _SPC_VK.get(vk)
                if _spc_sh_ch is not None:
                    self._spc_on_ch_toggle(_spc_sh_ch, solo=False, reset=False)
                    return True
            if vk==65: self._tap_set_marker(10); return True  # Shift+A → A をSet
            if vk==66: self._tap_set_marker(11); return True  # Shift+B → B をSet
            if key==K.Key_4: self._tap_set_marker(10); return True  # Shift+テンキー4 → A をSet
            if key==K.Key_6: self._tap_set_marker(11); return True  # Shift+テンキー6 → B をSet
            if vk==82:  # Shift+R → キャッシュクリア（キャンセル時もアイコンを戻す）
                try: self._do_cache_clear()
                finally:
                    _b=getattr(self,"_reset_btn",None)
                    if _b is not None: self._flash_off(_b)
                return True
            if key==K.Key_Space: self._seek_to_start(); return True  # Shift+Space → 先頭リセット
            # NSFモード: Shift+←/→ で曲切り替え, Shift+[,][.] で10曲ずつ
            nsf_s=self.engine._nsf
            if nsf_s is not None:
                if key==K.Key_Left:
                    if nsf_s.cur_track>0: self._nsf_set_track(nsf_s.cur_track-1)
                    return True
                if key==K.Key_Right:
                    if nsf_s.cur_track<nsf_s.track_count-1: self._nsf_set_track(nsf_s.cur_track+1)
                    return True
                if key in (K.Key_Comma, K.Key_Less):
                    _t=max(0, nsf_s.cur_track-10)
                    if _t!=nsf_s.cur_track: self._nsf_set_track(_t)
                    return True
                if key in (K.Key_Period, K.Key_Greater):
                    _t=min(nsf_s.track_count-1, nsf_s.cur_track+10)
                    if _t!=nsf_s.cur_track: self._nsf_set_track(_t)
                    return True
            # SPC(ZIP)モード: Shift+←/→ で曲切り替え, Shift+[,][.] で10曲ずつ
            spc_s = self.engine._spc
            if spc_s is not None and spc_s.is_zip:
                if key==K.Key_Left:
                    if spc_s.cur_track > 0: self._spc_set_track(spc_s.cur_track - 1)
                    return True
                if key==K.Key_Right:
                    if spc_s.cur_track < spc_s.track_count - 1: self._spc_set_track(spc_s.cur_track + 1)
                    return True
                if key in (K.Key_Comma, K.Key_Less):
                    _t = max(0, spc_s.cur_track - 10)
                    if _t != spc_s.cur_track: self._spc_set_track(_t)
                    return True
                if key in (K.Key_Period, K.Key_Greater):
                    _t = min(spc_s.track_count - 1, spc_s.cur_track + 10)
                    if _t != spc_s.cur_track: self._spc_set_track(_t)
                    return True
            return False

        # NSFモード: メインキーボード最上段(1～\)でチャンネルソロ/全ON
        _nsf_now=self.engine._nsf
        if _nsf_now is not None and not bool(e.modifiers()&Qt.KeyboardModifier.KeypadModifier):
            _NSF_KEY_MAP={
                K.Key_1:0, K.Key_2:1, K.Key_3:2, K.Key_4:3, K.Key_5:4,
                K.Key_6:5, K.Key_7:6, K.Key_8:7, K.Key_9:8, K.Key_0:9,
                K.Key_Minus:10, K.Key_AsciiCircum:11, K.Key_Equal:11, K.Key_Backslash:12,
            }
            if key in _NSF_KEY_MAP:
                ch=_NSF_KEY_MAP[key]
                if ch<_nsf_now.ch_count:
                    self._nsf_toggle_ch_by_key(ch)
                return True
        # SPCモード: 1-8 キーでチャンネルソロ
        _spc_now = self.engine._spc
        if _spc_now is not None and not bool(e.modifiers()&Qt.KeyboardModifier.KeypadModifier):
            _SPC_KEY_MAP = {
                K.Key_1:0, K.Key_2:1, K.Key_3:2, K.Key_4:3,
                K.Key_5:4, K.Key_6:5, K.Key_7:6, K.Key_8:7,
            }
            if key in _SPC_KEY_MAP:
                ch = _SPC_KEY_MAP[key]
                self._spc_on_ch_toggle(ch, solo=True, reset=False)
                return True

        # NSFモード: [,] → 前の曲, [.] → 次の曲
        _nsf_nav=self.engine._nsf
        if _nsf_nav is not None:
            if key==K.Key_Comma:
                if _nsf_nav.cur_track>0: self._nsf_set_track(_nsf_nav.cur_track-1)
                return True
            if key==K.Key_Period:
                if _nsf_nav.cur_track<_nsf_nav.track_count-1: self._nsf_set_track(_nsf_nav.cur_track+1)
                return True
        # SPCモード(ZIP): [,] → 前の曲, [.] → 次の曲
        _spc_nav = self.engine._spc
        if _spc_nav is not None and _spc_nav.is_zip:
            if key==K.Key_Comma:
                if _spc_nav.cur_track > 0: self._spc_set_track(_spc_nav.cur_track - 1)
                return True
            if key==K.Key_Period:
                if _spc_nav.cur_track < _spc_nav.track_count - 1: self._spc_set_track(_spc_nav.cur_track + 1)
                return True
        # 修飾なし
        if key==K.Key_Space: self._pp(); return True
        if key==K.Key_Left:  self._rew(); return True
        if key==K.Key_Right: self._ff();  return True
        if key==K.Key_Up:    self._ear_mode(); return True  # ↑ Ear Mode
        if key==K.Key_Down:  self._ab_toggle(); return True  # ↓
        if vk==79:  # O（モーダルダイアログ後に確実に色を戻す）
            try: self._open()
            finally:
                _b=getattr(self,"_open_btn",None)
                if _b is not None: self._flash_off(_b)
            return True
        if vk==84: self._tempo_detect(); return True  # T
        if vk==82: self._do_reset(); return True  # R
        if vk==72:  # H → Help（PDF表示、外部アプリ起動でフラッシュ解除）
            try: self._show_help()
            finally:
                _b=getattr(self,"_help_btn",None)
                if _b is not None: self._flash_off(_b)
            return True
        if vk==90: self._toggle_zoom(); return True  # Z → Zoom
        if vk==65: self._goto_marker(10); return True  # A → A へ移動(Go To)
        if vk==66: self._goto_marker(11); return True  # B → B へ移動(Go To)
        # テンキー裏ショートカット（アイコン配置と同じ並び）
        kp = bool(e.modifiers() & Qt.KeyboardModifier.KeypadModifier)
        # テンキーEnter → 直後の4/6をSetにするためのフラグ（時刻記録）
        if kp and key in (K.Key_Enter, K.Key_Return):
            self._kp_enter_time=time.time()
            return True
        if kp or key in (K.Key_0,K.Key_1,K.Key_2,K.Key_3,K.Key_4,K.Key_5,K.Key_6,K.Key_7,K.Key_8,K.Key_9,K.Key_Slash,K.Key_Asterisk):
            # テンキー / → Help, テンキー * → Zoom
            if key==K.Key_Slash:
                try: self._show_help()
                finally:
                    _b=getattr(self,"_help_btn",None)
                    if _b is not None: self._flash_off(_b)
                return True
            if key==K.Key_Asterisk: self._toggle_zoom(); return True
            # Enter直後(1.5秒以内)の4/6はSet動作
            enter_recent = (time.time()-self._kp_enter_time) < 1.5
            if key==K.Key_4:
                if enter_recent:
                    self._kp_enter_time=0.0; self._tap_set_marker(10)
                else:
                    self._goto_marker(10)
                return True
            if key==K.Key_6:
                if enter_recent:
                    self._kp_enter_time=0.0; self._tap_set_marker(11)
                else:
                    self._goto_marker(11)
                return True
            if key==K.Key_7:
                try: self._open()
                finally:
                    _b=getattr(self,"_open_btn",None)
                    if _b is not None: self._flash_off(_b)
                return True
            if key==K.Key_8: self._tempo_detect(); return True
            if key==K.Key_9:
                if enter_recent:
                    self._kp_enter_time=0.0
                    try: self._do_cache_clear()
                    finally:
                        _b=getattr(self,"_reset_btn",None)
                        if _b is not None: self._flash_off(_b)
                else:
                    self._do_reset()
                return True
            if key==K.Key_5: self._ear_mode(); return True
            if key==K.Key_1:
                if enter_recent and self.engine._nsf is not None:
                    self._kp_enter_time=0.0
                    _n=self.engine._nsf
                    if _n.cur_track>0: self._nsf_set_track(_n.cur_track-1)
                elif enter_recent and self.engine._spc is not None and self.engine._spc.is_zip:
                    self._kp_enter_time=0.0
                    _s=self.engine._spc
                    if _s.cur_track>0: self._spc_set_track(_s.cur_track-1)
                else:
                    self._rew()
                return True
            if key==K.Key_2: self._ab_toggle(); return True
            if key==K.Key_3:
                if enter_recent and self.engine._nsf is not None:
                    self._kp_enter_time=0.0
                    _n=self.engine._nsf
                    if _n.cur_track<_n.track_count-1: self._nsf_set_track(_n.cur_track+1)
                elif enter_recent and self.engine._spc is not None and self.engine._spc.is_zip:
                    self._kp_enter_time=0.0
                    _s=self.engine._spc
                    if _s.cur_track<_s.track_count-1: self._spc_set_track(_s.cur_track+1)
                else:
                    self._ff()
                return True
            if key==K.Key_0:
                if enter_recent:
                    self._kp_enter_time=0.0; self._seek_to_start()
                else:
                    self._pp()
                return True
        return False

    def keyReleaseEvent(self, e):
        vk=e.nativeVirtualKey()
        if not e.isAutoRepeat():
            # Shiftを先に離す場合に備え、両方のボタンを通常色に戻す
            for _sh in (False, True):
                _b=self._key_btn(vk, e.key(), _sh)
                if _b is not None: self._flash_off(_b)
            # テンキーのフラッシュも解除
            _b=self._key_btn(vk, e.key(), False, keypad=True)
            if _b is not None: self._flash_off(_b)

    # ──────────────────────────────────────
    # ユーティリティ
    # ──────────────────────────────────────
    def _fmt(self, sec):
        if sec is None: return "--:--.-"
        m=int(sec)//60; s=int(sec)%60
        d=int(round((sec-int(sec))*10))
        if d>=10: s+=1; d-=10
        if s>=60: m+=1; s-=60
        return f"{m:02d}:{s:02d}.{d:1d}"

    def _st(self, msg): self._status_sig.emit(msg)

    def mousePressEvent(self, e):
        """何もない場所クリックでQLineEditのフォーカスを解除"""
        focused = QApplication.focusWidget()
        if isinstance(focused, QLineEdit):
            focused.clearFocus()
            self.setFocus()
        super().mousePressEvent(e)

    def closeEvent(self, e):
        fh=self.engine._file_hash
        if fh: save_session(fh,self._get_state())
        self.engine.stop(); e.accept()

# ════════════════════════════════════════
# エントリーポイント
# ════════════════════════════════════════
def app_stylesheet(scale=1.0):
    fs=int(round(13*scale))
    return (
        f"* {{font-family:Consolas,'MS Gothic','Courier New',monospace; font-size:{fs}px; color:{FG}; background:{BG};}}"
        f"QMainWindow {{background:{BG};}}"
        f"QWidget {{background:{BG};}}"
        f"QLineEdit {{background:{BG3}; border:1px solid {BORDER}; padding:2px 4px;}}"
        f"QPushButton {{background:transparent; border:none;}}"
        f"QScrollBar {{background:{BG2};}}"
        f"QToolTip {{background:#FFFFCC; color:#000; border:1px solid #888; padding:3px 6px;}}"
    )

def main():
    print(f"Morokoshi Time {APP_VERSION}", flush=True)
    _log(f"=== Morokoshi Time {APP_VERSION} starting ===")
    app=QApplication(sys.argv)
    app.setStyle("Fusion")
    _gs=load_global_settings()
    _sc=2.0 if _gs["zoom"]>=2.0 else 1.0
    app.setStyleSheet(app_stylesheet(_sc))
    _load_icons()

    # ウィンドウ・タスクバーアイコン設定
    def _find_app_icon():
        if getattr(sys, 'frozen', False):
            return QIcon(sys.executable)  # EXEに埋め込まれたアイコンを使用
        base = os.path.dirname(os.path.abspath(__file__))
        for p in [os.path.join(base,"morokoshi.ico"),
                  os.path.join(base,"..","icon","morokoshi.ico"),
                  os.path.join(base,"icon","morokoshi.ico")]:
            if os.path.exists(p): return QIcon(p)
        return QIcon()
    _app_icon = _find_app_icon()
    if not _app_icon.isNull():
        app.setWindowIcon(_app_icon)

    win=MainWindow()
    app.installEventFilter(win)
    win.show()

    if len(sys.argv)>1 and os.path.exists(sys.argv[1]):
        QTimer.singleShot(500, lambda: win._load(sys.argv[1]))

    # Windowsコンソールモードを保存して終了後に復元
    _con_mode = None
    try:
        import ctypes as _ctc
        _h = _ctc.windll.kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        _m = _ctc.c_ulong(0)
        if _ctc.windll.kernel32.GetConsoleMode(_h, _ctc.byref(_m)):
            _con_mode = (_h, _m.value)
    except Exception:
        pass
    ret = app.exec()
    # PortAudio (sounddevice) の cleanup が数十秒 hang することがある。
    # sys.exit() は atexit ハンドラ経由で Pa_Terminate() を呼ぶためその影響を受ける。
    # os._exit() はプロセスを即時終了し、hang を回避する。
    # （closeEvent で save_session・engine.stop は完了済みなので安全）
    try:
        if _con_mode:
            _ctc.windll.kernel32.SetConsoleMode(_con_mode[0], _con_mode[1])
    except Exception:
        pass
    try:
        print()
    except Exception:
        pass
    os._exit(0)

if __name__=="__main__":
    main()