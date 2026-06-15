#!/usr/bin/env python3
"""
音色評価プログラム ver5

【使い方】
  1. samples/original/    に元音源を置く
  2. samples/synthesized/ に合成音を置く
  3. python compare_ver5.py を起動して「評価実行」を押す

【自動処理の流れ】
  ① 前処理（自動）
      - オンセットトリム  : 先頭の無音を除去（元・合成 両方）
      - 音量正規化        : 合成音の RMS を元音源に合わせる
      - 音程確認          : F0 差が 25 cents 以内か検査
  ② 音色特徴量比較
      - AT・SC・DSV・OER の閾値評価
  ③ 修正案
      - スペクトル解析に基づく自動診断

【参考文献】
  McAdams et al. (1995) Psychol. Res. 58:177-192   — 音色知覚次元
  Siedenburg (2019) JASA 145:1078-1087             — AT 閾値 60 ms
  Wun et al. (2014) JAES 62:575-583               — SC 閾値 24%
  Horner et al. (2004) JASA 116:1800-1810          — DSV 閾値 16%
  Caclin et al. (2005) JASA 118:471-482            — OER・スペクトル不規則性
"""

import sys, os, subprocess
from pathlib import Path

# ──────────────────────────────────────────────────────
# 必要パッケージの自動インストール
# ──────────────────────────────────────────────────────
def _install(pkg):
    for extra in [[], ['--break-system-packages'], ['--user']]:
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', pkg] + extra,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            continue
    return False

def _ensure_packages():
    import importlib.util
    missing = [p for p in ['numpy', 'librosa', 'soundfile']
               if importlib.util.find_spec(p) is None]
    if not missing:
        return
    for pkg in missing:
        _install(pkg)
    os.execv(sys.executable, [sys.executable] + sys.argv)

_ensure_packages()

import numpy as np
import librosa
import soundfile as sf

try:
    import tkinter as tk
except ModuleNotFoundError:
    print("tkinter が見つかりません: brew install python-tk@3.12")
    sys.exit(1)

# ──────────────────────────────────────────────────────
# 定数
# ──────────────────────────────────────────────────────
SR_ANAL  = 22050
N_FFT    = 2048
HOP_LEN  = 512

# 前処理パラメータ
PREPROC_TOP_DB      = 35    # この dB 以下の先頭・末尾を無音とみなす
PREPROC_PRE_ROLL_MS = 30    # オンセット前に残す余白 [ms]

# 音色特徴量の閾値
THR_CENTS = 25.0
THR_AT    = 60.0
THR_SC    = 0.24
THR_DSV   = 16.0
THR_OER   = 0.20

EXTS = {'.wav', '.mp3', '.flac', '.aif', '.aiff', '.ogg'}

# フォルダ
SCRIPT_DIR     = Path(__file__).parent
SAMPLES_DIR    = SCRIPT_DIR / 'samples'
RAW_ORIG_DIR   = SAMPLES_DIR / 'original'      # 収録した元音源（入力）
RAW_SYNTH_DIR  = SAMPLES_DIR / 'synthesized'   # 収録した合成音（入力）
ORIG_DIR       = SAMPLES_DIR / 'processed' / 'original'   # 前処理済み（比較に使用）
SYNTH_DIR      = SAMPLES_DIR / 'processed' / 'synthesized'

# GUI カラー
BG      = '#f5f6fa'
BG_TBL  = '#ffffff'
C_HEAD  = ('#343a40', '#ffffff')
C_PASS  = ('#d4edda', '#155724')
C_FAIL  = ('#f8d7da', '#721c24')
C_CRIT  = ('#f8d7da', '#721c24')
C_MAJOR = ('#ffe8cc', '#8a4800')
C_MINOR = ('#fff3cd', '#856404')
C_OK_SG = ('#d4edda', '#155724')
C_WARN  = ('#fff3cd', '#856404')
C_EVEN  = ('#f8f9fa', '#333333')
C_ODD   = ('#ffffff', '#333333')

# ──────────────────────────────────────────────────────
# ファイル読み込み
# ──────────────────────────────────────────────────────
def _load_anal(path: Path) -> np.ndarray:
    y, _ = librosa.load(str(path), sr=SR_ANAL, mono=True)
    y, _ = librosa.effects.trim(y, top_db=20)
    return y

def _estimate_f0(y: np.ndarray) -> float | None:
    if len(y) < N_FFT:
        return None
    f0 = librosa.yin(y, fmin=50, fmax=2000, sr=SR_ANAL)
    valid = f0[(f0 > 50) & (f0 < 2000)]
    if len(valid) == 0:
        return None
    return float(np.median(valid))

def _hz_to_note_str(hz: float | None) -> str:
    if hz is None or hz <= 0:
        return '---'
    try:
        note = librosa.hz_to_note(hz, unicode=False)
        return f'{note} ({hz:.1f} Hz)'
    except Exception:
        return f'{hz:.1f} Hz'

def _rms_normalize(y_target: np.ndarray, y_ref: np.ndarray) -> tuple[np.ndarray, float]:
    rms_ref = float(np.sqrt(np.mean(y_ref ** 2)))
    rms_tgt = float(np.sqrt(np.mean(y_target ** 2)))
    if rms_tgt < 1e-9:
        return y_target, 1.0
    gain = rms_ref / rms_tgt
    return (y_target * gain).astype(y_target.dtype), gain

# ──────────────────────────────────────────────────────
# ファイル収集
# ──────────────────────────────────────────────────────
def _find(directory: Path, stem: str) -> Path | None:
    for ext in sorted(EXTS):
        p = directory / f'{stem}{ext}'
        if p.exists():
            return p
    return None

def collect_raw_stems() -> list[str]:
    """RAW フォルダのステム一覧"""
    seen: set[str] = set()
    for d in [RAW_ORIG_DIR, RAW_SYNTH_DIR]:
        if d.exists():
            for f in d.iterdir():
                if f.suffix.lower() in EXTS:
                    seen.add(f.stem)
    return sorted(seen)

def collect_stems() -> list[str]:
    """前処理済みフォルダのステム一覧"""
    seen: set[str] = set()
    for d in [ORIG_DIR, SYNTH_DIR]:
        if d.exists():
            for f in d.iterdir():
                if f.suffix.lower() in EXTS:
                    seen.add(f.stem)
    return sorted(seen)

# ──────────────────────────────────────────────────────
# 前処理（① オンセットトリム → ② 音量正規化 → ③ 音程確認）
# ──────────────────────────────────────────────────────
def _trim_onset(y: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    """オンセット検出・トリム。戻り値: (trimmed_y, cut_ms)"""
    _, (start_sample, end_sample) = librosa.effects.trim(y, top_db=PREPROC_TOP_DB)
    pre_roll = int(PREPROC_PRE_ROLL_MS / 1000 * sr)
    start    = max(0, start_sample - pre_roll)
    return y[start:end_sample], float(start / sr * 1000)

def run_preprocess(progress_cb=None) -> list[dict]:
    """
    RAW フォルダの全ファイルを前処理して processed/ に保存する。
    ① オンセットトリム  ② 音量正規化  ③ 音程確認
    実行のたびに processed/ を一度クリアしてから保存する。
    """
    # 前回の残存ファイルを削除してからディレクトリを再作成
    import shutil
    for d in [ORIG_DIR, SYNTH_DIR]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    stems = collect_raw_stems()
    rows  = []
    for i, stem in enumerate(stems):
        if progress_cb:
            progress_cb(f'前処理中... ({i + 1}/{len(stems)}): {stem}')

        p_orig  = _find(RAW_ORIG_DIR,  stem)
        p_synth = _find(RAW_SYNTH_DIR, stem)

        res = dict(stem=stem,
                   cut_orig_ms=None, cut_synth_ms=None,
                   gain=None,
                   f0_orig=None, f0_synth=None,
                   cents=None, pitch_ok=None,
                   error=None)
        try:
            y_o = y_s = None
            sr_o = sr_s = None

            # ① オンセットトリム（元音源）
            if p_orig:
                y_o, sr_o = librosa.load(str(p_orig), sr=None, mono=True)
                y_o, cut_o = _trim_onset(y_o, sr_o)
                res['cut_orig_ms'] = cut_o
                sf.write(str(ORIG_DIR / (stem + '.wav')), y_o, sr_o)

            # ① オンセットトリム（合成音）
            if p_synth:
                y_s, sr_s = librosa.load(str(p_synth), sr=None, mono=True)
                y_s, cut_s = _trim_onset(y_s, sr_s)
                res['cut_synth_ms'] = cut_s

                # ② 音量正規化（元音源がある場合のみ）
                if y_o is not None:
                    y_s, gain = _rms_normalize(y_s, y_o)
                    res['gain'] = gain

                sf.write(str(SYNTH_DIR / (stem + '.wav')), y_s, sr_s)

            # ③ 音程確認
            if y_o is not None and y_s is not None:
                y_o22 = librosa.resample(y_o, orig_sr=sr_o, target_sr=SR_ANAL) if sr_o != SR_ANAL else y_o
                y_s22 = librosa.resample(y_s, orig_sr=sr_s, target_sr=SR_ANAL) if sr_s != SR_ANAL else y_s
                f0_o = _estimate_f0(y_o22)
                f0_s = _estimate_f0(y_s22)
                res['f0_orig']  = f0_o
                res['f0_synth'] = f0_s
                if f0_o and f0_s and f0_o > 1e-3:
                    cents = 1200.0 * np.log2(f0_s / f0_o)
                    res['cents']    = cents
                    res['pitch_ok'] = abs(cents) <= THR_CENTS

        except Exception as e:
            res['error'] = str(e)

        rows.append(res)

    return rows

# ──────────────────────────────────────────────────────
# 音色特徴量計算（AT・SC・DSV・OER）
# ──────────────────────────────────────────────────────
def _compute_at(y: np.ndarray) -> float:
    rms = librosa.feature.rms(y=y, frame_length=N_FFT, hop_length=HOP_LEN)[0]
    if rms.max() < 1e-9:
        return 0.0
    peak_idx  = int(np.argmax(rms))
    thresh    = 0.05 * rms[peak_idx]
    onset_idx = next((i for i, v in enumerate(rms) if v >= thresh), 0)
    return float(max(peak_idx - onset_idx, 1) * HOP_LEN / SR_ANAL * 1000)

def _compute_sc(y: np.ndarray) -> float:
    n = len(y)
    seg = y[n // 4: 3 * n // 4]
    if len(seg) < N_FFT:
        seg = np.pad(seg, (0, N_FFT - len(seg)))
    return float(np.mean(
        librosa.feature.spectral_centroid(
            y=seg, sr=SR_ANAL, n_fft=N_FFT, hop_length=HOP_LEN)[0]))

def _compute_dsv(y: np.ndarray) -> float:
    stft = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP_LEN))
    pct_changes = []
    for t in range(1, stft.shape[1]):
        a, b   = stft[:, t - 1], stft[:, t]
        norm_a = np.linalg.norm(a)
        if norm_a > 1e-8:
            pct_changes.append(np.linalg.norm(b - a) / norm_a * 100.0)
    return float(np.mean(pct_changes)) if pct_changes else 0.0

def _compute_oer(y: np.ndarray) -> float | None:
    try:
        n   = len(y)
        seg = y[n // 4: 3 * n // 4]
        if len(seg) < N_FFT:
            seg = np.pad(seg, (0, N_FFT - len(seg)))
        f0_arr, voiced_flag, _ = librosa.pyin(
            seg,
            fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C7'),
            sr=SR_ANAL)
        voiced = f0_arr[voiced_flag]
        if len(voiced) == 0:
            return None
        f0    = float(np.median(voiced))
        spec  = np.abs(librosa.stft(seg, n_fft=N_FFT, hop_length=HOP_LEN))
        mag   = np.mean(spec, axis=1)
        freqs = librosa.fft_frequencies(sr=SR_ANAL, n_fft=N_FFT)
        e_odd = e_even = 0.0
        max_k = min(int((SR_ANAL / 2) / f0), 16)
        for k in range(1, max_k + 1):
            target = f0 * k
            if target >= SR_ANAL / 2:
                break
            window = f0 * 0.3
            mask   = (freqs >= target - window) & (freqs <= target + window)
            if np.any(mask):
                e = float(np.sum(mag[mask] ** 2))
                if k % 2 == 1:
                    e_odd  += e
                else:
                    e_even += e
        total = e_odd + e_even
        if total < 1e-12:
            return None
        return float(e_odd / total)
    except Exception:
        return None

def _feat_one(path: Path) -> dict | None:
    try:
        y = _load_anal(path)
        if len(y) < N_FFT:
            return None
        return {
            'at':  _compute_at(y),
            'sc':  _compute_sc(y),
            'dsv': _compute_dsv(y),
            'oer': _compute_oer(y),
        }
    except Exception:
        return None

# ──────────────────────────────────────────────────────
# スペクトル解析（③ 修正案用）
# ──────────────────────────────────────────────────────
def analyze_spectrum(paths: list) -> dict:
    sc_list, at_list, f0_list = [], [], []
    for path in paths:
        try:
            y, _ = librosa.load(str(path), sr=SR_ANAL, mono=True)
            y, _ = librosa.effects.trim(y, top_db=20)
            if len(y) < N_FFT:
                continue
            sc_list.append(float(np.mean(librosa.feature.spectral_centroid(
                y=y, sr=SR_ANAL, n_fft=N_FFT, hop_length=HOP_LEN)[0])))
            rms = librosa.feature.rms(
                y=y, frame_length=N_FFT, hop_length=HOP_LEN)[0]
            if rms.max() > 0:
                peak_idx  = int(np.argmax(rms))
                thresh    = 0.05 * rms[peak_idx]
                onset_idx = next((i for i, v in enumerate(rms) if v >= thresh), 0)
                at_list.append(float(max(peak_idx - onset_idx, 1) * HOP_LEN / SR_ANAL * 1000))
            pitches, mags = librosa.piptrack(
                y=y, sr=SR_ANAL, n_fft=N_FFT, hop_length=HOP_LEN)
            f0_vals = [pitches[mags[:, t].argmax(), t]
                       for t in range(pitches.shape[1])
                       if pitches[mags[:, t].argmax(), t] > 50]
            if f0_vals:
                f0_list.append(float(np.median(f0_vals)))
        except Exception:
            continue
    return {
        'sc': float(np.mean(sc_list)) if sc_list else None,
        'at': float(np.mean(at_list)) if at_list else None,
        'f0': float(np.mean(f0_list)) if f0_list else None,
    }

# ──────────────────────────────────────────────────────
# ② 音色特徴量比較（AT・SC・DSV・OER）
# ──────────────────────────────────────────────────────
def run_features(progress_cb=None) -> dict:
    stems = collect_stems()
    rows  = []
    for i, stem in enumerate(stems):
        if progress_cb:
            progress_cb(f'特徴量計算中... ({i + 1} / {len(stems)})')
        orig_path  = _find(ORIG_DIR,  stem)
        synth_path = _find(SYNTH_DIR, stem)

        # 前処理済みファイルをそのまま使用（正規化済み）
        fo = _feat_one(orig_path)  if orig_path  else None
        fs = _feat_one(synth_path) if synth_path else None

        at_diff = sc_ratio = dsv_diff = oer_diff = None
        if fo and fs:
            at_diff  = abs(fs['at'] - fo['at'])
            if fo['sc'] and fo['sc'] > 0:
                sc_ratio = abs(fs['sc'] - fo['sc']) / fo['sc']
            dsv_diff = abs(fs['dsv'] - fo['dsv'])
            if fo['oer'] is not None and fs['oer'] is not None:
                oer_diff = abs(fs['oer'] - fo['oer'])

        rows.append({
            'stem':       stem,
            'feat_orig':  fo,
            'feat_synth': fs,
            'at_diff':    at_diff,
            'sc_ratio':   sc_ratio,
            'dsv_diff':   dsv_diff,
            'oer_diff':   oer_diff,
        })

    def _mean_diff(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return float(np.mean(vals)) if vals else None

    n    = sum(1 for r in rows if r['feat_orig'] and r['feat_synth'])
    diff = {
        'at_diff':  _mean_diff('at_diff'),
        'sc_ratio': _mean_diff('sc_ratio'),
        'dsv_diff': _mean_diff('dsv_diff'),
        'oer_diff': _mean_diff('oer_diff'),
    }

    def _avg_feat(key, side):
        vals = [r[f'feat_{side}'][key]
                for r in rows
                if r[f'feat_{side}'] and r[f'feat_{side}'].get(key) is not None]
        return float(np.mean(vals)) if vals else None

    avg_orig  = {k: _avg_feat(k, 'orig')  for k in ('at', 'sc', 'dsv', 'oer')}
    avg_synth = {k: _avg_feat(k, 'synth') for k in ('at', 'sc', 'dsv', 'oer')}

    pass_at  = (diff['at_diff']  <= THR_AT)  if diff['at_diff']  is not None else None
    pass_sc  = (diff['sc_ratio'] <= THR_SC)  if diff['sc_ratio'] is not None else None
    pass_dsv = (diff['dsv_diff'] <= THR_DSV) if diff['dsv_diff'] is not None else None
    pass_oer = (diff['oer_diff'] <= THR_OER) if diff['oer_diff'] is not None else None

    flags = [p for p in [pass_at, pass_sc, pass_dsv, pass_oer] if p is not None]
    if not flags:
        judgment = None
    elif all(flags):
        judgment = '達成'
    elif any(flags):
        judgment = '改善中'
    else:
        judgment = '未達成'

    return {
        'rows':      rows,
        'avg_orig':  avg_orig,
        'avg_synth': avg_synth,
        'diff':      diff,
        'pass_at':   pass_at,
        'pass_sc':   pass_sc,
        'pass_dsv':  pass_dsv,
        'pass_oer':  pass_oer,
        'judgment':  judgment,
        'n_notes':   n,
    }

# ──────────────────────────────────────────────────────
# ③ 修正案生成
# ──────────────────────────────────────────────────────
def generate_suggestions(orig_spec, synth_spec, feat_result=None):
    suggestions = []

    # SC 比較
    sc_o = orig_spec.get('sc')
    sc_s = synth_spec.get('sc')
    f0_s = synth_spec.get('f0') or orig_spec.get('f0')
    if sc_o and sc_s:
        ratio = sc_s / sc_o
        if f0_s and sc_s < f0_s:
            suggestions.append({
                'level': 'critical',
                'title': 'スペクトル重心が基音より低い（病的な状態）',
                'detail': (
                    f'合成音の SC = {sc_s:.0f} Hz が推定基音 {f0_s:.0f} Hz を下回っています。\n'
                    '原因 : 低周波ノイズ・DC オフセット，または基音成分のみの状態。\n'
                    '修正 : ① DC 成分をハイパスフィルタ（カットオフ 80 Hz 程度）で除去\n'
                    '　　   ② 第2〜第8倍音を必ず加算してください。\n'
                    f'　　   目標 SC ≈ {sc_o:.0f} Hz'
                ),
                'metric': f'SC: 元={sc_o:.0f} Hz  合={sc_s:.0f} Hz  F0推定={f0_s:.0f} Hz',
            })
        elif ratio < 0.4:
            suggestions.append({
                'level': 'critical',
                'title': '高次倍音が大幅に不足（音が暗すぎる）',
                'detail': (
                    f'SC が元音源の {ratio*100:.0f}% と非常に低い値です。\n'
                    '修正 : 第4〜第8倍音の振幅を増やしてください。\n'
                    f'　　   目標 SC ≈ {sc_o:.0f} Hz'
                ),
                'metric': f'SC: 元={sc_o:.0f} Hz  合={sc_s:.0f} Hz  (比率 {ratio:.2f})',
            })
        elif ratio < 0.7:
            suggestions.append({
                'level': 'major',
                'title': '高次倍音が不足（音が暗め）',
                'detail': (
                    f'SC が元音源より {(1-ratio)*100:.0f}% 低い値です。\n'
                    '修正 : 第3〜第6倍音の振幅を少し大きくしてください。\n'
                    f'　　   目標 SC ≈ {sc_o:.0f} Hz'
                ),
                'metric': f'SC: 元={sc_o:.0f} Hz  合={sc_s:.0f} Hz  (比率 {ratio:.2f})',
            })
        elif ratio > 2.5:
            suggestions.append({
                'level': 'major',
                'title': '高次倍音が過剰（音が明るすぎる）',
                'detail': (
                    f'SC が元音源の {ratio*100:.0f}% と高すぎます。\n'
                    '修正 : 第5倍音以上の振幅を下げてください。\n'
                    f'　　   目標 SC ≈ {sc_o:.0f} Hz'
                ),
                'metric': f'SC: 元={sc_o:.0f} Hz  合={sc_s:.0f} Hz  (比率 {ratio:.2f})',
            })
        elif ratio > 1.4:
            suggestions.append({
                'level': 'minor',
                'title': '高次倍音がやや過剰（音がやや明るい）',
                'detail': (
                    '高次倍音を少し抑えると元音源に近くなります。\n'
                    f'　　   目標 SC ≈ {sc_o:.0f} Hz'
                ),
                'metric': f'SC: 元={sc_o:.0f} Hz  合={sc_s:.0f} Hz  (比率 {ratio:.2f})',
            })
        else:
            suggestions.append({
                'level': 'ok',
                'title': 'スペクトル重心は良好',
                'detail': '倍音の明るさは元音源に近い値です。',
                'metric': f'SC: 元={sc_o:.0f} Hz  合={sc_s:.0f} Hz  (比率 {ratio:.2f})',
            })

    # AT 比較
    at_o = orig_spec.get('at')
    at_s = synth_spec.get('at')
    if at_o and at_s:
        diff = at_s - at_o
        if abs(diff) <= 60:
            suggestions.append({
                'level': 'ok',
                'title': '立ち上がり時間は良好',
                'detail': '音の立ち上がりの速さは元音源に近い値です。',
                'metric': f'AT: 元={at_o:.0f} ms  合={at_s:.0f} ms  (差 {diff:+.0f} ms)',
            })
        elif diff > 60:
            suggestions.append({
                'level': 'major',
                'title': '立ち上がりが遅すぎる',
                'detail': (
                    f'合成音の立ち上がりが元音源より {diff:.0f} ms 遅れています。\n'
                    '修正 : エンベロープのアタック時間を短くしてください。\n'
                    f'　　   目標アタック ≈ {at_o:.0f} ms'
                ),
                'metric': f'AT: 元={at_o:.0f} ms  合={at_s:.0f} ms  (差 {diff:+.0f} ms)',
            })
        else:
            suggestions.append({
                'level': 'minor',
                'title': '立ち上がりがやや速い',
                'detail': (
                    f'合成音の立ち上がりが元音源より {abs(diff):.0f} ms 速いです。\n'
                    '修正 : エンベロープのアタック時間を少し長くしてください。\n'
                    f'　　   目標アタック ≈ {at_o:.0f} ms'
                ),
                'metric': f'AT: 元={at_o:.0f} ms  合={at_s:.0f} ms  (差 {diff:+.0f} ms)',
            })

    # DSV アドバイス
    if feat_result:
        avg_dsv_o = feat_result['avg_orig'].get('dsv')
        avg_dsv_s = feat_result['avg_synth'].get('dsv')
        pass_dsv  = feat_result['pass_dsv']
        n         = feat_result['n_notes']
        if avg_dsv_o is not None and avg_dsv_s is not None:
            avg_dsv_diff = abs(avg_dsv_s - avg_dsv_o)
            metric_dsv = (f'DSV: 元平均={avg_dsv_o:.1f}%  合平均={avg_dsv_s:.1f}%'
                          f'  （{n} 音符の平均差: {avg_dsv_diff:.1f}%）')
            if pass_dsv:
                suggestions.append({
                    'level': 'ok',
                    'title': 'スペクトル変動（DSV）は良好',
                    'detail': '音の時間変化の量は元音源に近い値です。',
                    'metric': metric_dsv,
                })
            elif avg_dsv_s < avg_dsv_o:
                suggestions.append({
                    'level': 'major' if avg_dsv_diff > THR_DSV * 2 else 'minor',
                    'title': 'スペクトル変動が少なすぎる（音が単調）',
                    'detail': (
                        '合成音のスペクトルが元音源より時間的変化に乏しい状態です。\n'
                        '修正 : ① 各倍音の振幅に LFO（5〜7 Hz 程度）を加えてください。\n'
                        '　　   ② 周波数に軽いビブラート（±数 Hz）を加えてください。\n'
                        '　　   ③ エンベロープに若干のランダム揺らぎを追加してください。'
                    ),
                    'metric': metric_dsv,
                })
            else:
                suggestions.append({
                    'level': 'minor',
                    'title': 'スペクトル変動が多すぎる（音が不安定）',
                    'detail': (
                        '合成音のスペクトルが元音源より時間的変化が過剰です。\n'
                        '修正 : LFO の深さ・ランダム揺らぎパラメータを小さくしてください。'
                    ),
                    'metric': metric_dsv,
                })

    # OER アドバイス
    if feat_result:
        avg_oer_o = feat_result['avg_orig'].get('oer')
        avg_oer_s = feat_result['avg_synth'].get('oer')
        pass_oer  = feat_result['pass_oer']
        n         = feat_result['n_notes']
        if avg_oer_o is None or avg_oer_s is None:
            suggestions.append({
                'level': 'minor',
                'title': '奇偶倍音比（OER）を計算できませんでした',
                'detail': (
                    'F0（基音）推定に失敗した音符が多い可能性があります。\n'
                    '音声が短すぎる場合や音程が不明確な場合に発生します。'
                ),
                'metric': '',
            })
        elif pass_oer:
            suggestions.append({
                'level': 'ok',
                'title': '奇偶倍音比（OER）は良好',
                'detail': '奇数・偶数倍音のバランスは元音源に近い値です。',
                'metric': (f'OER: 元平均={avg_oer_o:.2f}  合平均={avg_oer_s:.2f}'
                           f'  （{n} 音符の平均）'),
            })
        else:
            avg_oer_diff = abs(avg_oer_s - avg_oer_o)
            lvl = 'major' if avg_oer_diff > THR_OER * 2 else 'minor'
            metric_oer = (f'OER: 元平均={avg_oer_o:.3f}  合平均={avg_oer_s:.3f}'
                          f'  （{n} 音符の平均差: {avg_oer_diff:.3f}）')
            if avg_oer_s > avg_oer_o:
                suggestions.append({
                    'level': lvl,
                    'title': '奇数倍音が多すぎる（クラリネット寄りの音色）',
                    'detail': (
                        f'OER が元音源より高い値です（元={avg_oer_o:.2f}  合={avg_oer_s:.2f}）。\n'
                        '現状 : 奇数倍音（3f₀・5f₀・7f₀）が相対的に強すぎます。\n'
                        '修正 : 偶数倍音（2f₀・4f₀・6f₀）の振幅を増やしてください。'
                    ),
                    'metric': metric_oer,
                })
            else:
                suggestions.append({
                    'level': lvl,
                    'title': '奇数倍音が少なすぎる（偶数倍音が支配的）',
                    'detail': (
                        f'OER が元音源より低い値です（元={avg_oer_o:.2f}  合={avg_oer_s:.2f}）。\n'
                        '現状 : 偶数倍音（2f₀・4f₀・6f₀）が相対的に強すぎます。\n'
                        '修正 : 奇数倍音（3f₀・5f₀・7f₀）の振幅を増やしてください。'
                    ),
                    'metric': metric_oer,
                })

    if not suggestions:
        suggestions.append({
            'level': 'ok',
            'title': '大きな問題は検出されませんでした',
            'detail': '引き続き微調整を続けてください。',
            'metric': '',
        })
    return suggestions

# ──────────────────────────────────────────────────────
# GUI ユーティリティ
# ──────────────────────────────────────────────────────
def _cell(parent, text, bg, fg, row, col,
          bold=False, anchor='center', width=None, wraplength=None):
    kw = dict(text=text, bg=bg, fg=fg,
              font=('', 10, 'bold') if bold else ('', 10),
              relief='flat', padx=8, pady=6, anchor=anchor,
              justify='left')
    if width:
        kw['width'] = width
    if wraplength:
        kw['wraplength'] = wraplength
    tk.Label(parent, **kw).grid(row=row, column=col,
                                 sticky='nsew', padx=1, pady=1)

# ──────────────────────────────────────────────────────
# GUI メインウィンドウ
# ──────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('音色評価  ver5  — 音色特徴量比較')
        self.geometry('1020x800')
        self.minsize(800, 500)
        self.resizable(True, True)
        self.configure(bg=BG)
        self._build()

    # ─── 画面構築 ──────────────────────────────────────
    def _build(self):
        # タイトルバー
        bar = tk.Frame(self, bg='#2c3e50')
        bar.pack(fill='x', side='top')
        tk.Label(bar, text='音色評価  ver5',
                 font=('', 16, 'bold'), bg='#2c3e50', fg='white', padx=16
                 ).pack(side='left', pady=10)
        tk.Label(bar,
                 text='McAdams (1995)  ×  Siedenburg (2019)  ×  Wun (2014)  ×  Horner (2004)',
                 font=('', 10), bg='#2c3e50', fg='#adb5bd').pack(side='left', padx=8)
        self.btn_run = tk.Button(
            bar, text='▶  評価実行', font=('', 12, 'bold'),
            bg='#6f42c1', fg='white', padx=16, pady=4,
            activebackground='#59359a', bd=0, command=self.run_all)
        self.btn_run.pack(side='right', padx=16, pady=8)

        # スクロール可能エリア
        sf_frame = tk.Frame(self, bg=BG)
        sf_frame.pack(fill='both', expand=True, side='top')
        vbar = tk.Scrollbar(sf_frame, orient='vertical')
        vbar.pack(side='right', fill='y')
        self._canvas = tk.Canvas(sf_frame, bg=BG, highlightthickness=0,
                                  yscrollcommand=vbar.set)
        self._canvas.pack(side='left', fill='both', expand=True)
        vbar.config(command=self._canvas.yview)
        inner = tk.Frame(self._canvas, bg=BG)
        self._inner_id = self._canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>',
                   lambda e: self._canvas.configure(
                       scrollregion=self._canvas.bbox('all')))
        self._canvas.bind('<Configure>',
                          lambda e: self._canvas.itemconfigure(
                              self._inner_id, width=e.width))
        self._canvas.bind_all('<MouseWheel>',
                              lambda e: self._canvas.yview_scroll(
                                  int(-1 * (e.delta / 120)), 'units'))
        self._canvas.bind_all('<Button-4>',
                              lambda e: self._canvas.yview_scroll(-1, 'units'))
        self._canvas.bind_all('<Button-5>',
                              lambda e: self._canvas.yview_scroll(1, 'units'))
        p = inner

        # ステータスバー
        self.status_var = tk.StringVar(value='「評価実行」を押してください')
        tk.Label(p, textvariable=self.status_var,
                 font=('', 10), fg='#2d3436', bg=BG, pady=4,
                 justify='left', anchor='w', wraplength=980).pack(fill='x', padx=16)

        # ① 前処理結果
        tk.Label(p,
                 text='①  前処理結果  (オンセットトリム・音量正規化・音程確認)',
                 font=('', 11, 'bold'), fg='#2d3436', anchor='w', bg=BG
                 ).pack(fill='x', padx=16, pady=(8, 2))
        self.frame_preproc = tk.Frame(p, bd=1, relief='sunken', bg=BG_TBL)
        self.frame_preproc.pack(padx=16, pady=(0, 4), fill='x')
        tk.Label(self.frame_preproc, text='未実行',
                 fg='#636e72', font=('', 10), pady=12, bg=BG_TBL).pack()
        tk.Label(p,
                 text=f'※ 前処理済みファイルは samples/processed/ に保存されます。'
                      f'  音程閾値: |Δcents| ≤ {THR_CENTS:.0f} cents',
                 font=('', 8), fg='#636e72', bg=BG, wraplength=980,
                 justify='left', anchor='w').pack(fill='x', padx=16, pady=(0, 8))

        # ② 音色特徴量比較
        tk.Label(p, text='②  音色特徴量比較  (AT・SC・DSV・OER)',
                 font=('', 11, 'bold'), fg='#2d3436', anchor='w', bg=BG
                 ).pack(fill='x', padx=16, pady=(4, 2))
        self.frame_feat = tk.Frame(p, bd=1, relief='sunken', bg=BG_TBL)
        self.frame_feat.pack(padx=16, pady=(0, 8), fill='x')
        tk.Label(self.frame_feat, text='未実行',
                 fg='#636e72', font=('', 10), pady=12, bg=BG_TBL).pack()
        tk.Label(p,
                 text=f'※ 閾値: AT ≤{THR_AT:.0f} ms ／ SC ≤{THR_SC*100:.0f}% ／'
                      f' DSV ≤{THR_DSV:.0f}% ／ OER ≤{THR_OER:.2f}'
                      '  ｜  全達成→「達成」，一部→「改善中」，全不可→「未達成」',
                 font=('', 8), fg='#636e72', bg=BG, wraplength=980,
                 justify='left', anchor='w').pack(fill='x', padx=16, pady=(0, 8))

        # ③ 修正案
        tk.Label(p, text='③  合成音の修正案  (スペクトル解析に基づく自動診断)',
                 font=('', 11, 'bold'), fg='#2d3436', anchor='w', bg=BG
                 ).pack(fill='x', padx=16, pady=(4, 2))
        self.frame_suggest = tk.Frame(p, bd=1, relief='sunken', bg=BG)
        self.frame_suggest.pack(padx=16, pady=(0, 16), fill='x')
        tk.Label(self.frame_suggest, text='未実行',
                 fg='#636e72', font=('', 10), pady=12, bg=BG).pack()

    # ─── 実行 ──────────────────────────────────────────
    def run_all(self):
        self.btn_run.config(state='disabled')

        def cb(msg):
            self.status_var.set(msg)
            self.update()

        # raw ファイルの存在チェック
        if not collect_raw_stems():
            self.status_var.set(
                '⚠  samples/original/ または samples/synthesized/ にファイルがありません。')
            self.btn_run.config(state='normal')
            return

        # ① 前処理（トリム → 正規化 → 音程確認）
        preproc_rows = run_preprocess(progress_cb=cb)
        self._draw_preprocess(preproc_rows)

        # ② 音色特徴量比較
        feat_result = run_features(progress_cb=cb)
        self._draw_features(feat_result)

        # ③ 修正案
        cb('スペクトル解析中...')
        stems       = collect_stems()
        orig_paths  = [p for s in stems if (p := _find(ORIG_DIR,  s))]
        synth_paths = [p for s in stems if (p := _find(SYNTH_DIR, s))]
        orig_spec   = analyze_spectrum(orig_paths)
        synth_spec  = analyze_spectrum(synth_paths)
        suggestions = generate_suggestions(orig_spec, synth_spec,
                                           feat_result=feat_result)
        self._draw_suggestions(suggestions)

        # サマリ
        n_ok  = sum(1 for r in preproc_rows if r['pitch_ok'] is True)
        n_ng  = sum(1 for r in preproc_rows if r['pitch_ok'] is False)
        f_jdg = feat_result.get('judgment', '---') or '---'
        pitch_summary = f'音程: {n_ok} OK'
        if n_ng:
            pitch_summary += f' / {n_ng} ✗要確認'
        self.status_var.set(
            f'完了  ｜  {pitch_summary}'
            f'  ｜  特徴量: {f_jdg}'
            f'  ｜  修正案: {len(suggestions)} 件')
        self.btn_run.config(state='normal')

    # ─── ① 前処理結果テーブル描画 ───────────────────────
    def _draw_preprocess(self, rows):
        for w in self.frame_preproc.winfo_children():
            w.destroy()
        if not rows:
            tk.Label(self.frame_preproc,
                     text='ファイルが見つかりません。',
                     fg='#636e72', font=('', 10), pady=12, bg=BG_TBL).pack()
            return

        hdrs = [
            ('音符',          8),
            ('トリム(元)[ms]', 12),
            ('トリム(合)[ms]', 12),
            ('音量倍率',       10),
            ('元音程',         17),
            ('合音程',         17),
            ('差[cents]',      10),
            ('音程判定',        8),
        ]
        tbl = tk.Frame(self.frame_preproc, bg=BG_TBL)
        tbl.pack(fill='x', padx=4, pady=4)
        for c, (h, w) in enumerate(hdrs):
            tk.Label(tbl, text=h, font=('', 9, 'bold'),
                     bg='#dfe6e9', fg='#2d3436',
                     width=w, anchor='center', relief='flat', bd=0
                     ).grid(row=0, column=c, padx=1, pady=1, sticky='ew')

        for r, row in enumerate(rows, start=1):
            bg = '#fff' if r % 2 == 0 else '#f8f9fa'
            if row['error']:
                tk.Label(tbl, text=f'{row["stem"]}  エラー: {row["error"]}',
                         font=('', 9), bg='#f8d7da', fg='#721c24', anchor='w'
                         ).grid(row=r, column=0, columnspan=len(hdrs),
                                padx=1, pady=1, sticky='ew')
                continue

            cut_o  = f'-{row["cut_orig_ms"]:.0f}'  if row['cut_orig_ms']  is not None else '---'
            cut_s  = f'-{row["cut_synth_ms"]:.0f}' if row['cut_synth_ms'] is not None else '---'
            gain_s = f'{row["gain"]:.3f}×'          if row['gain']         is not None else '---'
            f0_o   = _hz_to_note_str(row['f0_orig'])
            f0_s   = _hz_to_note_str(row['f0_synth'])
            c_s    = f'{row["cents"]:+.1f}' if row['cents'] is not None else '---'

            ok = row['pitch_ok']
            if ok is True:
                mark, fg_j = '✓', '#27ae60'
            elif ok is False:
                mark, fg_j = '✗', '#e74c3c'
            else:
                mark, fg_j = '－', '#636e72'

            # 音量倍率の色（1.0 に近いほど良い）
            gain_val = row['gain']
            fg_gain  = '#636e72' if gain_val is None else (
                '#27ae60' if 0.8 <= gain_val <= 1.25 else '#e67e22')

            vals_fgs = [
                (row['stem'],  '#2d3436'),
                (cut_o,        '#636e72'),
                (cut_s,        '#636e72'),
                (gain_s,       fg_gain),
                (f0_o,         '#2980b9'),
                (f0_s,         '#2980b9'),
                (c_s,          '#2d3436'),
                (mark,         fg_j),
            ]
            for c, ((v, fg_c), (_, w)) in enumerate(zip(vals_fgs, hdrs)):
                bold = (c == 7 and ok is False)
                tk.Label(tbl, text=v,
                         font=('', 9, 'bold') if bold else ('', 9),
                         bg=bg, fg=fg_c, width=w, anchor='center'
                         ).grid(row=r, column=c, padx=1, pady=1, sticky='ew')

        for c in range(len(hdrs)):
            tbl.columnconfigure(c, weight=1)

    # ─── ② 特徴量比較テーブル描画 ──────────────────────
    def _draw_features(self, feat_result):
        for w in self.frame_feat.winfo_children():
            w.destroy()
        if not feat_result or feat_result['n_notes'] == 0:
            tk.Label(self.frame_feat, text='ファイルが見つかりません。',
                     fg='#636e72', font=('', 10), pady=12, bg=BG_TBL).pack()
            return

        n   = feat_result['n_notes']
        ao  = feat_result['avg_orig']
        as_ = feat_result['avg_synth']
        d   = feat_result['diff']

        # 平均サマリ
        tk.Label(self.frame_feat,
                 text=f'【平均】全 {n} 音符の平均値',
                 font=('', 9, 'bold'), fg='#2d3436', bg=BG_TBL, anchor='w'
                 ).pack(fill='x', padx=10, pady=(8, 2))

        tbl_avg = tk.Frame(self.frame_feat, bg=BG_TBL)
        tbl_avg.pack(fill='x', padx=10, pady=(0, 6))

        hdrs_avg = [('指標', 14), ('元音源 平均', 16), ('合成音 平均', 16),
                    ('差', 12), ('閾値', 10), ('判定', 8)]
        for col, (txt, w) in enumerate(hdrs_avg):
            _cell(tbl_avg, txt, *C_HEAD, row=0, col=col, bold=True, width=w)

        def _metric_row(r, label, v_o, v_s, diff_val, thr, pass_flag,
                        fmt_o, fmt_s, fmt_d):
            bg, fg = C_EVEN if r % 2 == 0 else C_ODD
            _cell(tbl_avg, label, bg, fg, row=r, col=0)
            _cell(tbl_avg, fmt_o.format(v_o) if v_o is not None else '---',
                  bg, fg, row=r, col=1)
            _cell(tbl_avg, fmt_s.format(v_s) if v_s is not None else '---',
                  bg, fg, row=r, col=2)
            _cell(tbl_avg, fmt_d.format(diff_val) if diff_val is not None else '---',
                  bg, fg, row=r, col=3)
            _cell(tbl_avg, thr, bg, fg, row=r, col=4)
            if pass_flag is True:
                _cell(tbl_avg, '✓ 達成',   *C_PASS, row=r, col=5, bold=True)
            elif pass_flag is False:
                _cell(tbl_avg, '✗ 未達成', *C_FAIL, row=r, col=5, bold=True)
            else:
                _cell(tbl_avg, '---', bg, fg, row=r, col=5)

        _metric_row(1, 'AT  立ち上がり時間 [ms]',
                    ao.get('at'), as_.get('at'), d.get('at_diff'),
                    f'≤ {THR_AT:.0f} ms', feat_result['pass_at'],
                    '{:.1f} ms', '{:.1f} ms', '差 {:.1f} ms')
        _metric_row(2, 'SC  スペクトル重心 [Hz]',
                    ao.get('sc'), as_.get('sc'), d.get('sc_ratio'),
                    f'≤ {THR_SC*100:.0f} %', feat_result['pass_sc'],
                    '{:.0f} Hz', '{:.0f} Hz', '差 {:.1%}')
        _metric_row(3, 'DSV スペクトル変動度 [%]',
                    ao.get('dsv'), as_.get('dsv'), d.get('dsv_diff'),
                    f'≤ {THR_DSV:.0f} %', feat_result['pass_dsv'],
                    '{:.1f} %', '{:.1f} %', '差 {:.2f} %')
        _metric_row(4, 'OER 奇数倍音比 [0-1]',
                    ao.get('oer'), as_.get('oer'), d.get('oer_diff'),
                    f'≤ {THR_OER:.2f}', feat_result['pass_oer'],
                    '{:.3f}', '{:.3f}', '差 {:.3f}')

        jdg   = feat_result['judgment']
        c_jdg = C_PASS if jdg == '達成' else C_FAIL if jdg == '未達成' else C_WARN
        _cell(tbl_avg, '総合判定', *C_HEAD, row=5, col=0, bold=True)
        for col in range(1, 5):
            _cell(tbl_avg, '', *C_HEAD, row=5, col=col)
        _cell(tbl_avg, jdg or '---', *c_jdg, row=5, col=5, bold=True)
        for col in range(6):
            tbl_avg.columnconfigure(col, weight=1)

        # 音符ごとの詳細
        tk.Frame(self.frame_feat, bg='#dee2e6', height=1
                 ).pack(fill='x', padx=10, pady=(4, 0))
        tk.Label(self.frame_feat,
                 text='【音符ごとの詳細値】',
                 font=('', 9, 'bold'), fg='#2d3436', bg=BG_TBL, anchor='w'
                 ).pack(fill='x', padx=10, pady=(4, 2))

        detail_hdrs = [
            ('音符',    8),
            ('AT元\n[ms]',   7), ('AT合\n[ms]',   7), ('AT差\n[ms]',   7),
            ('SC元\n[Hz]',   7), ('SC合\n[Hz]',   7), ('SC差\n[%]',    7),
            ('DSV元\n[%]',   7), ('DSV合\n[%]',   7), ('DSV差\n[%]',   7),
            ('OER元',        7), ('OER合',        7), ('OER差',        7),
        ]
        tbl_det = tk.Frame(self.frame_feat, bg=BG_TBL)
        tbl_det.pack(fill='x', padx=10, pady=(0, 10))

        for col, (txt, w) in enumerate(detail_hdrs):
            hbg = ('#4a6fa5' if col in (1,2,3) else
                   '#5a7a5a' if col in (4,5,6) else
                   '#7a5a7a' if col in (7,8,9) else
                   '#7a5a4a' if col in (10,11,12) else '#343a40')
            tk.Label(tbl_det, text=txt, font=('', 8, 'bold'),
                     bg=hbg, fg='white', width=w, anchor='center',
                     relief='flat', bd=0, justify='center', wraplength=70
                     ).grid(row=0, column=col, padx=1, pady=1, sticky='nsew')

        for r, row in enumerate(feat_result['rows'], start=1):
            bg = '#f8f9fa' if r % 2 != 0 else '#ffffff'
            fo = row['feat_orig']
            fs = row['feat_synth']

            def _fmt(val, fmt):
                return fmt.format(val) if val is not None else '---'

            at_o  = fo['at']  if fo else None
            at_s  = fs['at']  if fs else None
            at_d  = row['at_diff']
            at_ok = (at_d <= THR_AT) if at_d is not None else None

            sc_o  = fo['sc']  if fo else None
            sc_s  = fs['sc']  if fs else None
            sc_r  = row['sc_ratio']
            sc_ok = (sc_r <= THR_SC) if sc_r is not None else None

            dsv_o  = fo['dsv'] if fo else None
            dsv_s  = fs['dsv'] if fs else None
            dsv_d  = row['dsv_diff']
            dsv_ok = (dsv_d <= THR_DSV) if dsv_d is not None else None

            oer_o  = fo['oer'] if fo else None
            oer_s  = fs['oer'] if fs else None
            oer_d  = row['oer_diff']
            oer_ok = (oer_d <= THR_OER) if oer_d is not None else None

            def _dc(ok):
                return '#27ae60' if ok is True else '#e74c3c' if ok is False else '#636e72'

            cells = [
                (row['stem'],           bg, '#2d3436', False),
                (_fmt(at_o, '{:.1f}'),  bg, '#2d3436', False),
                (_fmt(at_s, '{:.1f}'),  bg, '#2d3436', False),
                (_fmt(at_d, '{:.1f}'),  bg, _dc(at_ok),  at_ok is False),
                (_fmt(sc_o, '{:.0f}'),  bg, '#2d3436', False),
                (_fmt(sc_s, '{:.0f}'),  bg, '#2d3436', False),
                (_fmt(sc_r, '{:.1%}'),  bg, _dc(sc_ok),  sc_ok is False),
                (_fmt(dsv_o, '{:.1f}'), bg, '#2d3436', False),
                (_fmt(dsv_s, '{:.1f}'), bg, '#2d3436', False),
                (_fmt(dsv_d, '{:.2f}'), bg, _dc(dsv_ok), dsv_ok is False),
                (_fmt(oer_o, '{:.3f}'), bg, '#2d3436', False),
                (_fmt(oer_s, '{:.3f}'), bg, '#2d3436', False),
                (_fmt(oer_d, '{:.3f}'), bg, _dc(oer_ok), oer_ok is False),
            ]
            for col, (txt, cbg, cfg, bold) in enumerate(cells):
                _, w = detail_hdrs[col]
                tk.Label(tbl_det, text=txt,
                         font=('', 8, 'bold') if bold else ('', 8),
                         bg=cbg, fg=cfg, width=w, anchor='center'
                         ).grid(row=r, column=col, padx=1, pady=1, sticky='ew')

        for col in range(len(detail_hdrs)):
            tbl_det.columnconfigure(col, weight=1)

    # ─── ③ 修正案描画 ──────────────────────────────────
    def _draw_suggestions(self, suggestions):
        for w in self.frame_suggest.winfo_children():
            w.destroy()
        if not suggestions:
            tk.Label(self.frame_suggest, text='修正案なし',
                     fg='#636e72', font=('', 10), pady=12, bg=BG).pack()
            return
        level_color = {
            'critical': C_CRIT,
            'major':    C_MAJOR,
            'minor':    C_MINOR,
            'ok':       C_OK_SG,
        }
        level_icon = {
            'critical': '🔴',
            'major':    '🟠',
            'minor':    '🟡',
            'ok':       '🟢',
        }
        for sg in suggestions:
            lvl    = sg.get('level', 'minor')
            bg, fg = level_color.get(lvl, C_MINOR)
            icon   = level_icon.get(lvl, '●')
            card   = tk.Frame(self.frame_suggest, bg=bg, pady=2, padx=4)
            card.pack(fill='x', padx=8, pady=4)
            title_f = tk.Frame(card, bg=bg)
            title_f.pack(fill='x')
            tk.Label(title_f, text=f'{icon}  {sg["title"]}',
                     font=('', 11, 'bold'), fg=fg, bg=bg,
                     anchor='w', padx=8, pady=4
                     ).pack(side='left', fill='x', expand=True)
            if sg.get('metric'):
                tk.Label(title_f, text=sg['metric'],
                         font=('', 9), fg=fg, bg=bg,
                         anchor='e', padx=12, pady=4
                         ).pack(side='right')
            if lvl != 'ok' and sg.get('detail'):
                tk.Frame(card, bg=fg, height=1).pack(fill='x', padx=8)
                tk.Label(card, text=sg['detail'],
                         font=('', 10), fg=fg, bg=bg,
                         anchor='w', justify='left',
                         padx=16, pady=6, wraplength=940
                         ).pack(fill='x')


if __name__ == '__main__':
    App().mainloop()
