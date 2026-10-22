"""
ae_beatbar_replicator.py - Python Replication of After Effects Beatbar Scripts

Replicates the algorithms from:
  1. FH_beatbar_gen_v0.5.jsx (by Quantoz & PsychoSplash)
     - Rising-edge audio amplitude threshold detection
     - Refractory / cooldown period (minRestTime)
     - 1-frame psychoacoustic visual perception lead compensation (-1 / fps)
     - Discrete beat extraction
  2. AutoBeatKey_v0.4_SliderProperty.jsx (by Quantoz)
     - 3-Pass continuous animation curve / keyframe generation
     - Dynamic time & value scaling for closely-spaced beats (prevents jarring plunges)
     - Smooth Bezier / cubic spline interpolation
"""

import os
import sys
import json
import argparse
import numpy as np
import librosa
import scipy.signal


# ==============================================================================
# 1. After Effects "Convert Audio to Keyframes" Emulation
# ==============================================================================

def convert_audio_to_amplitude(
    audio_path_or_y,
    sr=22050,
    fps=60.0,
    filter_mode="raw",  # "raw", "kick", "bass_boost", or "percussion"
    normalize_peak=None  # If float (e.g. 50.0 or 100.0), scales peak to this value
):
    """
    Simulates Adobe After Effects' native 'Convert Audio to Keyframes' command.
    
    In After Effects, this computes the RMS amplitude envelope sampled at each
    composition frame (e.g. 60 fps).
    
    Args:
        audio_path_or_y: File path to audio or numpy audio waveform array.
        sr: Audio sample rate (default: 22050 Hz).
        fps: Target composition framerate (default: 60.0 fps).
        filter_mode: Pre-processing filter before amplitude calculation:
            - 'raw': Full mix (closest to standard AE behavior).
            - 'kick': 35-180 Hz bandpass (isolates kicks/downbeats).
            - 'bass_boost': Low shelf / bass emphasis.
            - 'percussion': Highpass > 1500 Hz (snare / hi-hat).
        normalize_peak: Optional peak normalization target value.
        
    Returns:
        times: 1D numpy array of frame timestamps in seconds.
        amplitude: 1D numpy array of envelope values (AE slider-like scale ~ 0-40).
    """
    if isinstance(audio_path_or_y, str):
        if not os.path.exists(audio_path_or_y):
            raise FileNotFoundError(f"Audio file not found: {audio_path_or_y}")
        y, sr = librosa.load(audio_path_or_y, sr=sr)
    else:
        y = np.asarray(audio_path_or_y, dtype=np.float32)

    # Optional frequency pre-filtering (mimics editors isolating kick drum / EQ)
    if filter_mode == "kick":
        sos = scipy.signal.butter(4, [35, 180], btype='bandpass', fs=sr, output='sos')
        y_proc = scipy.signal.sosfilt(sos, y)
    elif filter_mode == "percussion":
        sos = scipy.signal.butter(4, 1500, btype='highpass', fs=sr, output='sos')
        y_proc = scipy.signal.sosfilt(sos, y)
    else:
        y_proc = y

    hop_length = max(1, int(sr / fps))
    frame_length = max(1, hop_length * 2)

    # Compute RMS envelope centered at each frame
    rms = librosa.feature.rms(y=y_proc, frame_length=frame_length, hop_length=hop_length, center=True)[0]
    
    # AE amplitude scale typically maps nominal 0 dBFS sine wave to ~30-50 on the slider
    amplitude = rms * 100.0

    if normalize_peak is not None and np.max(amplitude) > 0:
        amplitude = (amplitude / np.max(amplitude)) * normalize_peak

    times = np.arange(len(amplitude)) / float(fps)
    return times, amplitude


# ==============================================================================
# 2. Replication: FH_beatbar_gen_v0.5.jsx (Discrete Layer Spawner)
# ==============================================================================

def fh_beatbar_detect(
    amplitude,
    fps=60.0,
    threshold=5.0,
    min_rest_time=0.15,
    beat_time_offset=0.0,
    use_one_frame_shift=True,
    target_framerate=60.0,
    target_lane=4
):
    """
    Faithful Python replication of FH_beatbar_gen_v0.5.jsx.
    
    Algorithm:
      1. Detects rising edge threshold crossings:
         `amplitude[i] > threshold` AND `amplitude[i - 1] <= threshold`
      2. Computes beat time with visual latency compensation:
         `time = (i / fps) - (1 / target_framerate if use_one_frame_shift else 0) - beat_time_offset`
      3. Skips `round(min_rest_time * fps)` frames to enforce cooldown.
      
    Args:
        amplitude: 1D array of audio amplitude values per frame.
        fps: Sampling framerate of the amplitude array.
        threshold: Amplitude trigger threshold (default: 5.0).
        min_rest_time: Cooldown in seconds after a detected beat (default: 0.15s).
        beat_time_offset: Hit moment offset inside the animation layer (default: 0.0s).
        use_one_frame_shift: Shift 1 frame earlier for audio-visual sync compensation.
        target_framerate: Target video framerate for the 1-frame shift (default: 60.0).
        target_lane: Track lane (default: 4 for main beatbar).
        
    Returns:
        List of dicts: [{'time': float, 'lane': int}] sorted by time.
    """
    keys_to_skip = int(round(min_rest_time * fps))
    one_frame_shift = (1.0 / target_framerate) if use_one_frame_shift else 0.0
    
    beats = []
    num_frames = len(amplitude)
    i = 1  # Start at index 1 to compare with i - 1 (equivalent to JS 1-indexed i=2)

    while i < num_frames:
        if amplitude[i] > threshold and amplitude[i - 1] <= threshold:
            t_event = (i / float(fps)) - beat_time_offset - one_frame_shift
            if t_event >= 0.0:
                beats.append({
                    'time': round(float(t_event), 3),
                    'lane': int(target_lane)
                })
            # Skip frames to prevent double detection, +1 for loop step
            i += keys_to_skip + 1
        else:
            i += 1

    return beats


# ==============================================================================
# 3. Replication: AutoBeatKey_v0.4_SliderProperty.jsx (Keyframe Curve Generator)
# ==============================================================================

def autobeatkey_generate_keyframes(
    beat_times,
    val_at_beat=100.0,
    val_regular=0.0,
    animation_length=0.66,
    animation_midpoint=25.0
):
    """
    Faithful Python replication of AutoBeatKey_v0.4_SliderProperty.jsx 3-Pass algorithm.
    
    Produces keyframes that describe the continuous pulsating motion of the beatbar:
      - Pass 1: Peak beat keys (val_at_beat).
      - Pass 2: Attack keys before each peak. If the time difference from the
                previous peak is less than `animation_length`, it dynamically scales
                both the drop amount and the attack time to prevent sudden drops.
      - Pass 3: Decay keys after peaks (when distance to next peak permits).
      
    Args:
        beat_times: List of beat timestamps in seconds.
        val_at_beat: Peak slider value at beat impact (default: 100.0).
        val_regular: Resting/idle slider value between beats (default: 0.0).
        animation_length: Total pulse duration in seconds (rise + fall).
        animation_midpoint: % of animation_length for the rise phase (e.g. 25%).
        
    Returns:
        List of keyframe dicts:
        [{'time': float, 'value': float, 'type': 'attack'|'peak'|'decay'}]
    """
    if animation_length <= 0:
        animation_length = 0.01

    key_t_before = animation_length * (animation_midpoint / 100.0)
    key_t_after = animation_length - key_t_before

    # Pass 1: Base peak keys
    peaks = [{'time': float(t), 'value': float(val_at_beat), 'type': 'peak'} for t in sorted(beat_times)]
    if not peaks:
        return []

    # Pass 2: Attack keys inserted before each peak
    keys_with_attack = []
    for i, peak in enumerate(peaks):
        this_time = peak['time']
        if i == 0:
            peak_t_diff = animation_length + 1.0
        else:
            peak_t_diff = this_time - peaks[i - 1]['time']

        if peak_t_diff > animation_length:
            att_time = this_time - key_t_before
            att_val = val_regular
        else:
            # Dynamic scaling for tight spacing
            scale = peak_t_diff / animation_length
            if val_at_beat > val_regular:
                dyn_regular = val_at_beat - abs(val_at_beat - val_regular) * scale
            else:
                dyn_regular = val_at_beat + abs(val_at_beat - val_regular) * scale
            dyn_key_time = peak_t_diff * (animation_midpoint / 100.0)
            att_time = this_time - dyn_key_time
            att_val = dyn_regular

        keys_with_attack.append({'time': round(att_time, 4), 'value': round(att_val, 2), 'type': 'attack'})
        keys_with_attack.append(peak)

    # Pass 3: Decay keys inserted after peaks
    final_keys = []
    num_peaks = len(peaks)
    for i in range(num_peaks):
        attack_key = keys_with_attack[2 * i]
        peak_key = keys_with_attack[2 * i + 1]
        final_keys.append(attack_key)
        final_keys.append(peak_key)

        this_time = peak_key['time']
        if i == num_peaks - 1:
            peak_t_diff = animation_length + 1.0
        else:
            peak_t_diff = peaks[i + 1]['time'] - this_time

        if peak_t_diff > animation_length:
            dec_time = this_time + key_t_after
            dec_val = val_regular
            final_keys.append({'time': round(dec_time, 4), 'value': round(dec_val, 2), 'type': 'decay'})

    # Ensure chronological order and remove negative time keys
    final_keys = [k for k in final_keys if k['time'] >= 0.0]
    final_keys.sort(key=lambda k: k['time'])
    return final_keys


def evaluate_autobeat_curve(keyframes, sample_times, val_regular=0.0):
    """
    Evaluates the continuous smooth animation curve across an array of sample timestamps.
    Applies smooth cubic ease (matching After Effects' Bezier easing) between keyframes.
    
    Args:
        keyframes: Output from `autobeatkey_generate_keyframes()`.
        sample_times: 1D numpy array of timestamps.
        val_regular: Idle baseline value when outside keyframe regions.
        
    Returns:
        1D numpy array of animated slider values.
    """
    if not keyframes:
        return np.full_like(sample_times, val_regular)

    kf_times = np.array([k['time'] for k in keyframes])
    kf_vals = np.array([k['value'] for k in keyframes])

    # Piecewise Hermite / cubic easing for smooth pulse interpolation
    values = np.full(len(sample_times), float(val_regular), dtype=float)

    for idx, t in enumerate(sample_times):
        if t <= kf_times[0]:
            values[idx] = kf_vals[0] if abs(t - kf_times[0]) < 0.001 else val_regular
        elif t >= kf_times[-1]:
            values[idx] = kf_vals[-1] if abs(t - kf_times[-1]) < 0.001 else val_regular
        else:
            # Find interval
            i = np.searchsorted(kf_times, t) - 1
            t0, t1 = kf_times[i], kf_times[i + 1]
            v0, v1 = kf_vals[i], kf_vals[i + 1]

            if abs(t1 - t0) < 1e-6:
                values[idx] = v0
            else:
                # Normalized progress [0, 1]
                u = (t - t0) / (t1 - t0)
                # Smoothstep / cubic S-curve: 3*u^2 - 2*u^3
                smooth_u = u * u * (3.0 - 2.0 * u)
                values[idx] = v0 + (v1 - v0) * smooth_u

    return values


# ==============================================================================
# 4. High-Level All-in-One Generator
# ==============================================================================

def analyze_audio_ae_method(
    audio_path,
    threshold=10.0,
    min_rest_time=0.15,
    filter_mode="kick",
    fps=60.0,
    use_one_frame_shift=True,
    target_lane=4,
    generate_curve=False,
    animation_length=0.66,
    animation_midpoint=25.0
):
    """
    All-in-one generator implementing the After Effects script workflow:
      1. Converts audio to amplitude envelope (with optional kick/percussion filter).
      2. Runs FH_beatbar rising-edge threshold detection.
      3. Optionally generates continuous AutoBeatKey keyframe curves.
    
    Returns:
        dict containing:
          - 'beats': List of [{'time': t, 'lane': lane}]
          - 'amplitude': Array of amplitude envelope
          - 'amplitude_times': Array of time points for amplitude
          - 'keyframes': (Optional) List of animation keyframes
    """
    times, amp = convert_audio_to_amplitude(
        audio_path,
        fps=fps,
        filter_mode=filter_mode
    )

    beats = fh_beatbar_detect(
        amp,
        fps=fps,
        threshold=threshold,
        min_rest_time=min_rest_time,
        use_one_frame_shift=use_one_frame_shift,
        target_framerate=fps,
        target_lane=target_lane
    )

    result = {
        'beats': beats,
        'amplitude': amp,
        'amplitude_times': times,
        'threshold': threshold,
        'min_rest_time': min_rest_time,
        'filter_mode': filter_mode
    }

    if generate_curve and beats:
        beat_times = [b['time'] for b in beats]
        keyframes = autobeatkey_generate_keyframes(
            beat_times,
            val_at_beat=100.0,
            val_regular=0.0,
            animation_length=animation_length,
            animation_midpoint=animation_midpoint
        )
        result['keyframes'] = keyframes

    return result


# ==============================================================================
# CLI Testing & Demonstration
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replication of After Effects Beatbar JSX Scripts in Python")
    parser.add_argument("audio_path", nargs="?", default="1/wicked-r34-level-1.mp3", help="Path to audio file")
    parser.add_argument("--threshold", type=float, default=12.0, help="Volume threshold trigger (default: 12.0)")
    parser.add_argument("--min-rest", type=float, default=0.18, help="Cooldown time in seconds (default: 0.18s)")
    parser.add_argument("--filter", choices=["raw", "kick", "percussion"], default="kick", help="Audio filtering")
    parser.add_argument("--fps", type=float, default=60.0, help="Composition framerate (default: 60)")
    parser.add_argument("--output", "-o", default=None, help="Save beats JSON to file")
    parser.add_argument("--compare", "-c", default="1/wicked-r34-level-1.json", help="Compare with reference beatmap")

    args = parser.parse_args()

    if not os.path.exists(args.audio_path):
        print(f"Error: File not found: {args.audio_path}")
        sys.exit(1)

    print("=" * 70)
    print(" [AE BEATBAR REPLICATOR] Running After Effects Algorithm Replication")
    print("=" * 70)
    print(f" Audio File:       {args.audio_path}")
    print(f" Trigger Threshold:{args.threshold}")
    print(f" Refractory Rest:  {args.min_rest}s")
    print(f" Pre-filter:       {args.filter}")
    print(f" Target Framerate: {args.fps} fps")
    print("-" * 70)

    res = analyze_audio_ae_method(
        args.audio_path,
        threshold=args.threshold,
        min_rest_time=args.min_rest,
        filter_mode=args.filter,
        fps=args.fps,
        generate_curve=True
    )

    beats = res['beats']
    keyframes = res.get('keyframes', [])

    print(f"\n[+] Extracted {len(beats)} beats using FH_beatbar algorithm.")
    if beats:
        print(f"    First 5 beats: {[b['time'] for b in beats[:5]]}")
        print(f"    Last 5 beats:  {[b['time'] for b in beats[-5:]]}")

    print(f"\n[+] Generated {len(keyframes)} AutoBeatKey animation keyframes.")
    if keyframes:
        print("    Sample keyframes around first beat:")
        for k in keyframes[:6]:
            print(f"      * {k['type']:<7} at t={k['time']:6.3f}s -> value={k['value']:5.1f}")

    if args.output:
        out_data = {
            "version": "2.0",
            "audio_file": os.path.basename(args.audio_path),
            "settings": {
                "engine": "after_effects_replica",
                "threshold": args.threshold,
                "min_rest_time": args.min_rest,
                "filter_mode": args.filter
            },
            "beats": beats
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)
        print(f"\n[+] Saved beats to: {args.output}")

    if args.compare and os.path.exists(args.compare):
        print("\n" + "=" * 70)
        print(f" [COMPARISON] Comparing against reference: {args.compare}")
        print("=" * 70)
        with open(args.compare, "r", encoding="utf-8") as f:
            ref_data = json.load(f)
        ref_beats = [b['time'] for b in ref_data.get('beats', []) if b.get('lane', 4) == 4]
        cand_beats = [b['time'] for b in beats]

        tolerance = 0.08  # 80ms window
        matched = 0
        offsets = []
        for rb in ref_beats:
            diffs = [abs(cb - rb) for cb in cand_beats]
            if diffs and min(diffs) <= tolerance:
                matched += 1
                offsets.append(cand_beats[diffs.index(min(diffs))] - rb)

        pct = (matched / max(1, len(ref_beats))) * 100.0
        avg_offset = (sum(offsets) / len(offsets) * 1000.0) if offsets else 0.0
        print(f" Reference Beats:  {len(ref_beats)}")
        print(f" Generated Beats:  {len(cand_beats)}")
        print(f" Matched (+/- 80ms): {matched} / {len(ref_beats)} ({pct:.1f}%)")
        print(f" Average Offset:   {avg_offset:+5.1f} ms")
        print("=" * 70)
