import os
import json
import zipfile
import librosa
import numpy as np
from scipy.signal import find_peaks

# ==============================================================================
# Helper / Export Functions & Difficulty Calculation
# ==============================================================================

def resolve_audio_file(file_path):
    """
    If file_path is a video file and an extracted audio file (.mp3, .wav, etc.)
    already exists alongside it, return the path to the audio file instead.
    This avoids invoking audioread/ffmpeg subprocess extraction during librosa.load.
    """
    if not file_path:
        return file_path
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.m4v']:
        base = os.path.splitext(file_path)[0]
        for aext in ['.mp3', '.wav', '.ogg', '.flac', '.m4a']:
            candidate = base + aext
            if os.path.exists(candidate) and os.path.getsize(candidate) > 1024:
                return candidate
    return file_path


def format_srt_time(seconds):
    """Converts seconds into SRT time format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis -= 1000
        secs += 1
    if secs >= 60:
        secs -= 60
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        hours += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def calculate_beat_difficulty(beats, duration=None, bpm=None, close_gap_threshold=0.35, min_group_size=3):
    """
    Auto difficulty determiner based on:
    1. Count of beats
    2. Frequency of beats (average and windowed peak)
    3. Frequency of close beat groups (bursts / streams where consecutive gap <= close_gap_threshold, e.g. red square in pic 1)
    
    Returns a comprehensive dict with:
    - difficulty: str ('Easy', 'Normal', 'Hard', 'Expert', 'Master')
    - level: int (1 to 10)
    - score: float (1.0 to 12.0)
    - total_beats: int
    - duration: float
    - avg_frequency: float (beats / sec)
    - peak_frequency: float (peak beats / sec in 3s window)
    - burst_groups_count: int (number of groups of close beats)
    - burst_beats_count: int (total beats in close groups)
    - burst_frequency: float (close groups per minute)
    - max_burst_length: int (maximum consecutive close beats in a group)
    - burst_ratio: float (ratio of burst beats to total beats)
    - details_str: str
    """
    if not beats:
        return {
            'difficulty': 'None',
            'level': 0,
            'score': 0.0,
            'total_beats': 0,
            'duration': 0.0,
            'avg_frequency': 0.0,
            'peak_frequency': 0.0,
            'burst_groups_count': 0,
            'burst_beats_count': 0,
            'burst_frequency': 0.0,
            'max_burst_length': 0,
            'burst_ratio': 0.0,
            'details_str': 'No beats'
        }

    # Extract & sort timestamps
    times = []
    for b in beats:
        if isinstance(b, dict):
            t = float(b.get('time', 0.0))
        elif isinstance(b, (int, float)):
            t = float(b)
        else:
            continue
        times.append(t)
    times.sort()

    n = len(times)
    if n == 0:
        return {
            'difficulty': 'None',
            'level': 0,
            'score': 0.0,
            'total_beats': 0,
            'duration': 0.0,
            'avg_frequency': 0.0,
            'peak_frequency': 0.0,
            'burst_groups_count': 0,
            'burst_beats_count': 0,
            'burst_frequency': 0.0,
            'max_burst_length': 0,
            'burst_ratio': 0.0,
            'details_str': 'No beats'
        }

    total_dur = float(duration) if duration and duration > 0 else max(1.0, times[-1] - times[0] + 1.0)
    avg_freq = n / max(1.0, total_dur)

    # Windowed peak frequency (sliding 3s window)
    peak_freq = avg_freq
    w_size = 3.0
    j_end = 0
    for i in range(n):
        while j_end < n and times[j_end] - times[i] <= w_size:
            j_end += 1
        cnt_in_window = j_end - i
        local_freq = cnt_in_window / w_size
        if local_freq > peak_freq:
            peak_freq = local_freq

    # Detect groups of close beats (pic 1 red square example)
    burst_groups = []
    i = 0
    while i < n - 1:
        if (times[i + 1] - times[i]) <= close_gap_threshold:
            j = i + 1
            while j < n - 1 and (times[j + 1] - times[j]) <= close_gap_threshold:
                j += 1
            grp_len = j - i + 1
            if grp_len >= min_group_size:
                grp_dur = times[j] - times[i]
                burst_groups.append({
                    'start': times[i],
                    'end': times[j],
                    'count': grp_len,
                    'duration': grp_dur
                })
            i = j + 1
        else:
            i += 1

    burst_groups_count = len(burst_groups)
    burst_beats_count = sum(g['count'] for g in burst_groups)
    max_burst_length = max([g['count'] for g in burst_groups], default=0)
    bursts_per_min = burst_groups_count / max(0.1, total_dur / 60.0)
    burst_ratio = burst_beats_count / max(1, n)

    # Calculate rhythm game difficulty rating
    # 1. Base frequency component
    s_freq = avg_freq * 1.25

    # 2. Peak intensity / burst frequency component
    s_peak = max(0.0, (peak_freq - avg_freq) * 0.30)

    # 3. Close beat groups component (burst density & count)
    s_burst = (bursts_per_min * 0.28) + (burst_ratio * 2.2) + (min(max_burst_length, 25) * 0.06)

    # 4. Total note count stamina component
    s_count = min(1.5, max(0.0, (n - 150) / 450.0))

    raw_score = s_freq + s_peak + s_burst + s_count
    score = round(max(1.0, min(10.0, raw_score)), 1)
    level = int(max(1, min(10, round(score))))

    if score < 3.0:
        difficulty_name = "Easy"
    elif score < 5.0:
        difficulty_name = "Normal"
    elif score < 7.0:
        difficulty_name = "Hard"
    elif score < 9.0:
        difficulty_name = "Expert"
    else:
        difficulty_name = "Master"

    details = (
        f"Rating: {level}/10 ({difficulty_name}) | "
        f"{n} beats | Density: {avg_freq:.1f} notes/s"
    )

    return {
        'difficulty': difficulty_name,
        'level': level,
        'score': score,
        'total_beats': n,
        'duration': round(total_dur, 2),
        'avg_frequency': round(avg_freq, 2),
        'peak_frequency': round(peak_freq, 2),
        'burst_groups_count': burst_groups_count,
        'burst_beats_count': burst_beats_count,
        'burst_frequency': round(bursts_per_min, 2),
        'max_burst_length': max_burst_length,
        'burst_ratio': round(burst_ratio, 3),
        'details_str': details
    }


class BeatmapData(tuple):
    """
    Backwards-compatible tuple (beats, audio_file) that also exposes
    rich beatmap metadata: .beats, .audio_file, .settings, .zones, .title, .has_embedded_video,
    .level, .difficulty, .difficulty_stats, .levels (level chapters), and .level_mode.
    """
    def __new__(cls, beats, audio_file="", settings=None, zones=None, title="", has_embedded_video=False,
                beat_path=None, level=1, difficulty="Normal", difficulty_stats=None,
                levels=None, level_mode="ramp_within_level"):
        return super().__new__(cls, (beats, audio_file))

    def __init__(self, beats, audio_file="", settings=None, zones=None, title="", has_embedded_video=False,
                 beat_path=None, level=1, difficulty="Normal", difficulty_stats=None,
                 levels=None, level_mode="ramp_within_level"):
        self.beats = beats
        self.audio_file = audio_file
        self.settings = settings or {}
        self.zones = zones or []
        self.title = title
        self.has_embedded_video = has_embedded_video
        self.beat_path = beat_path
        self.level = level
        self.difficulty = difficulty
        self.difficulty_stats = difficulty_stats or {}
        self.levels = levels or []
        self.level_mode = level_mode


def infer_or_standardize_levels(duration, title="", level=1, levels=None, difficulty="Normal", auto_infer=False):
    """
    Standardizes level chapters. If levels list is provided and valid, normalizes it.
    If levels is None or empty, returns empty list [] unless auto_infer=True.
    """
    import re
    duration = max(1.0, float(duration))
    diff_str = str(difficulty or "Normal")
    if levels and isinstance(levels, list) and len(levels) > 0:
        cleaned = []
        for i, lv in enumerate(levels):
            if isinstance(lv, dict):
                name = str(lv.get('name', f"Level {i+1}"))
                st = max(0.0, min(duration, float(lv.get('start_time', lv.get('start', 0.0)))))
                et = max(st, min(duration, float(lv.get('end_time', lv.get('end', duration)))))
                diff = str(lv.get('difficulty', diff_str))
                cleaned.append({'name': name, 'start_time': round(st, 3), 'end_time': round(et, 3), 'difficulty': diff})
        if cleaned:
            cleaned.sort(key=lambda x: x['start_time'])
            cleaned[0]['start_time'] = 0.0
            cleaned[-1]['end_time'] = round(duration, 3)
            return cleaned

    if not auto_infer:
        return []

    # Check title / level string for character cues
    t_lower = (str(title) + " " + str(level)).lower()
    char_name = None
    if "d.va" in t_lower or "dva" in t_lower or "d-va" in t_lower:
        char_name = "D.va"
    elif "widow" in t_lower:
        char_name = "Widow"
    elif "mercy" in t_lower:
        char_name = "Mercy"
    elif "tracer" in t_lower:
        char_name = "Tracer"
    elif "allure" in t_lower:
        char_name = "Allure"
    elif "demoness" in t_lower:
        char_name = "Demoness"
    elif "wicked" in t_lower:
        char_name = "Wicked"

    # Extract level digits: prioritize title cues (e.g. 'level-1', 'no-09', 'level-5')
    lvl_num = None
    title_m = re.search(r'(?:level|lv|no)[-_ ]*0*(\d+)', str(title), re.IGNORECASE)
    if title_m:
        lvl_num = title_m.group(1)
    else:
        digits = ''.join(filter(str.isdigit, str(level)))
        lvl_num = digits if digits else "1"

    lvl_str = str(level).strip()
    if "-" in lvl_str and "level" in lvl_str.lower():
        default_name = lvl_str
    elif char_name:
        default_name = f"Level {lvl_num} - {char_name}"
    else:
        default_name = f"Level {lvl_num}"

    return [{'name': default_name, 'start_time': 0.0, 'end_time': round(duration, 3), 'difficulty': diff_str}]


def infer_zones_from_beats(beats, duration=None):
    """
    Intelligently generates musical rhythm zones from beat timestamps
    when explicit zones are not defined in the beatmap.
    Returns: list of dicts: [{'name': 'Normal Groove', 'type': 'normal', 'start_time': 0.0, 'end_time': 35.0}, ...]
    """
    if not beats:
        return []
    dur = float(duration) if duration and duration > 0 else (float(beats[-1].get('time', 60.0)) + 2.0)
    times = sorted([float(b.get('time', 0.0)) for b in beats])

    win_size = 5.0
    raw_zones = []
    t = 0.0
    while t < dur:
        t_next = min(dur, t + win_size)
        w_beats = [bt for bt in times if t <= bt < t_next]
        count = len(w_beats)
        density = count / max(0.1, (t_next - t))

        if count == 0:
            ztype = 'pause'
            zname = 'Pause / Rest'
        elif density >= 4.5:
            ztype = 'climax'
            zname = 'Climax Burst'
        elif density >= 2.6:
            ztype = 'speeding_up'
            zname = 'Speeding Up'
        elif density >= 1.0:
            ztype = 'normal'
            zname = 'Normal Groove'
        else:
            ztype = 'slowing'
            zname = 'Slowing Down'

        raw_zones.append((t, t_next, ztype, zname))
        t = t_next

    # Merge consecutive identical zones
    merged = []
    for st, et, ztype, zname in raw_zones:
        if merged and merged[-1]['type'] == ztype:
            merged[-1]['end_time'] = round(et, 2)
        else:
            merged.append({
                'name': zname,
                'type': ztype,
                'start_time': round(st, 2),
                'end_time': round(et, 2)
            })

    if merged:
        merged[0]['start_time'] = 0.0
        merged[-1]['end_time'] = round(dur, 2)
    return merged


def save_beats(file_path_base, beats, audio_file_name, settings=None, zones=None,
               embed_video=False, video_path=None, skins_dir=None,
               level=1, difficulty="Normal", difficulty_stats=None,
               levels=None, level_mode="ramp_within_level"):
    """
    Saves the beat list, settings variables, zones timings, level, difficulty,
    level chapters (levels), and level_mode into a single, clean JSON file or .beat archive.
    """
    clean_audio_name = os.path.basename(audio_file_name) if audio_file_name else ""
    
    # Calculate difficulty stats purely as metadata if not already provided
    if not difficulty_stats and beats:
        difficulty_stats = calculate_beat_difficulty(beats)

    # CRITICAL: Preserve user-chosen level and difficulty.
    # Do NOT overwrite valid choices (e.g. level=1, difficulty="Normal") with auto-calculated stats.
    if level is None:
        if levels and len(levels) > 0:
            first_lvl = levels[0]
            level = first_lvl.get('level', 1) if isinstance(first_lvl, dict) else getattr(first_lvl, 'level', 1)
        else:
            level = 1

    if difficulty is None:
        if levels and len(levels) > 0:
            first_lvl = levels[0]
            difficulty = first_lvl.get('difficulty', "Normal") if isinstance(first_lvl, dict) else getattr(first_lvl, 'difficulty', "Normal")
        else:
            difficulty = "Normal"

    if file_path_base.lower().endswith(".beat"):
        from beat_format import BeatFormat
        title = os.path.splitext(os.path.basename(file_path_base))[0]
        data = {
            "version": "2.0",
            "audio_file": clean_audio_name,
            "video_file": clean_audio_name,
            "level": level,
            "difficulty": difficulty,
            "difficulty_stats": difficulty_stats or {},
            "level_mode": level_mode,
            "levels": levels or [],
            "settings": settings or {},
            "zones": zones or [],
            "beats": beats
        }
        actual_video = video_path or (audio_file_name if audio_file_name and os.path.exists(audio_file_name) else None)
        out = BeatFormat.create(
            file_path_base,
            beatmap_source=data,
            title=title,
            video_path=actual_video,
            skins_dir=skins_dir,
            embed_video=embed_video,
        )
        print(f"Beatmap .beat archive saved successfully to:\n - {out}")
        return out

    # Normalize path to ensure .json extension
    json_path = file_path_base if file_path_base.lower().endswith(".json") else file_path_base + ".json"
    
    # Package into refined JSON format
    data = {
        "version": "2.0",
        "audio_file": clean_audio_name,
        "video_file": clean_audio_name,
        "level": level,
        "difficulty": difficulty,
        "difficulty_stats": difficulty_stats or {},
        "level_mode": level_mode,
        "levels": levels or [],
        "settings": settings or {},
        "zones": zones or [],
        "beats": beats
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        
    print(f"Beatmap JSON saved successfully to:\n - {json_path}")
    return json_path


def load_beats(file_path):
    """
    Loads beats from JSON or .beat archive.
    Returns: BeatmapData object (acts as tuple (beats, audio_file) with .settings, .zones, .title, .level, .difficulty, .levels, .level_mode)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Beatmap file not found: {file_path}")
        
    import re
    if file_path.lower().endswith('.beat') or (zipfile.is_zipfile(file_path) and not file_path.lower().endswith('.json')):
        from beat_format import BeatFormat
        with BeatFormat.open(file_path) as bf:
            data = bf.get_beatmap()
            audio_file = bf.get_video_name() or data.get("audio_file", data.get("video_file", ""))
            title = bf.get_title()
            has_embed = bf.has_embedded_video()
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        audio_file = data.get("audio_file", data.get("video_file", ""))
        title = data.get("title", os.path.splitext(os.path.basename(file_path))[0])
        has_embed = False

    beats = data.get("beats", [])
    settings = data.get("settings", {})
    zones = data.get("zones", [])
    difficulty_stats = data.get("difficulty_stats", None)
    levels = data.get("levels", [])
    level_mode = data.get("level_mode", "ramp_within_level")
    if not difficulty_stats and beats:
        difficulty_stats = calculate_beat_difficulty(beats)

    # Determine level: prioritize explicit saved level in data, then levels[0], then filename cues
    raw_level = data.get("level")
    m = re.search(r'\b(?:level|lv)[-_ ]*0*(\d+)\b', f"{title} {os.path.basename(file_path)}", re.IGNORECASE)
    if raw_level is not None:
        try:
            level = int(raw_level)
        except (ValueError, TypeError):
            level = 1
    elif levels and len(levels) > 0:
        first_lvl = levels[0]
        level = first_lvl.get('level', 1) if isinstance(first_lvl, dict) else getattr(first_lvl, 'level', 1)
    elif m:
        level = int(m.group(1))
    elif difficulty_stats and "level" in difficulty_stats:
        level = int(difficulty_stats["level"])
    else:
        level = 1

    # Determine difficulty: prioritize explicit saved difficulty in data, then levels[0]
    raw_diff = data.get("difficulty")
    if raw_diff is not None and str(raw_diff).strip() != "":
        difficulty = str(raw_diff).strip()
    elif levels and len(levels) > 0:
        first_lvl = levels[0]
        difficulty = first_lvl.get('difficulty', "Normal") if isinstance(first_lvl, dict) else getattr(first_lvl, 'difficulty', "Normal")
    elif difficulty_stats and "difficulty" in difficulty_stats:
        difficulty = difficulty_stats["difficulty"]
    else:
        difficulty = "Normal"

    if not zones and beats:
        zones = infer_zones_from_beats(beats)

    return BeatmapData(
        beats, audio_file, settings, zones,
        title=title, has_embedded_video=has_embed,
        beat_path=os.path.abspath(file_path),
        level=level, difficulty=difficulty, difficulty_stats=difficulty_stats,
        levels=levels, level_mode=level_mode
    )



# ==============================================================================
# Rhythm Smoothing & Symmetry Engine (Anti-Caterpillar & Anti-Clump)
# ==============================================================================

def smooth_rhythm_timeline(
    beats,
    period,
    phi=0.0,
    anti_caterpillar=True,
    anti_clump=True,
    min_gap=0.095,
    max_consecutive_16ths=4,
    difficulty="Normal"
):
    """
    Rhythm game post-processing pass to smooth note patterns, ensuring symmetrical,
    pleasing, and musically phrased rhythms across all tracks.
    
    1. Anti-Clump (Fixes Pic 1):
       Eliminates awkward, unsymmetrical 3-note clumps (e.g. [t, t+16th, t+8th]) inside
       steady grooves or normal difficulty by smoothing them into clean eighth-note doublets [t, t+8th],
       so rhythms stay symmetrical and matched to the measure.
       
    2. Anti-Caterpillar (Fixes Pic 2):
       Prevents unbroken 16th-note 'caterpillars' (16+ continuous notes in a row).
       Caps rapid streams to at most `max_consecutive_16ths` (default 4 notes: 1-e-&-a),
       enforcing an 8th-note breathing space between bursts so rolls appear as clean,
       rhythmically structured bursts instead of solid overlapping blobs.
       
    3. Strict Anti-Overlap Deduplication:
       Enforces minimum visual gap between notes on the same lane (>= min_gap) so
       timeline circles never overlap awkwardly into unreadable slugs.
    """
    if not beats:
        return []

    step_8th = period / 2.0
    step_16th = period / 4.0
    diff_lower = str(difficulty or "Normal").lower()
    is_easy_or_normal = diff_lower in ("easy", "normal")

    # Group beats by lane
    lanes_dict = {}
    for b in beats:
        l = b.get('lane', 4) if isinstance(b, dict) else 4
        lanes_dict.setdefault(l, []).append(b)

    all_smoothed = []

    for l, lane_beats in lanes_dict.items():
        # Sort lane beats by time
        lane_beats.sort(key=lambda x: x['time'] if isinstance(x, dict) else x)
        times = [round(float(b['time'] if isinstance(b, dict) else b), 4) for b in lane_beats]

        if len(times) <= 2:
            all_smoothed.extend(lane_beats)
            continue

        # Pass 1: Anti-Caterpillar
        # Break continuous 16th streams longer than max_consecutive_16ths into clean 4-note bursts
        # with breathing eighth-note gaps.
        if anti_caterpillar and len(times) >= 4:
            th_16th_gap = step_16th * 1.35
            smoothed_times = []
            n = len(times)
            i = 0
            while i < n:
                # Find extent of continuous rapid run
                j = i
                while j < n - 1 and (times[j + 1] - times[j]) <= th_16th_gap:
                    j += 1
                run_len = j - i + 1

                if run_len > max_consecutive_16ths:
                    # Continuous run is a caterpillar! (e.g. 8, 12, 16 notes like in Pic 2)
                    # Symmetrically phrase the run into 4-note bursts separated by breathing pauses.
                    k = 0
                    while k < run_len:
                        chunk_size = min(4, run_len - k)
                        chunk_idx = k // 4
                        if chunk_idx % 2 == 0 or not is_easy_or_normal:
                            # Keep full burst
                            for m in range(chunk_size):
                                smoothed_times.append(times[i + k + m])
                        else:
                            # Thin to clean eighth notes (keep downbeat and upbeat, drop 16th subdivisions)
                            smoothed_times.append(times[i + k])
                            if chunk_size >= 3:
                                smoothed_times.append(times[i + k + 2])
                        k += chunk_size
                else:
                    for m in range(run_len):
                        smoothed_times.append(times[i + m])
                i = j + 1
            times = smoothed_times

        # Pass 2: Anti-Clump (Fixes Pic 1)
        # Scan for isolated 3-note clumps (e.g. t, t+16th, t+8th) where surrounding notes
        # have eighth-note or quarter-note spacing.
        if anti_clump and len(times) >= 3:
            th_16th_gap = step_16th * 1.35
            th_8th_gap = step_8th * 0.82
            smoothed_times = []
            n = len(times)
            skip_idx = set()

            for idx in range(n):
                if idx in skip_idx:
                    continue

                # Check if idx starts a 3-note clump: [idx, idx+1, idx+2]
                if idx <= n - 3:
                    gap1 = times[idx + 1] - times[idx]
                    gap2 = times[idx + 2] - times[idx + 1]
                    gap_prev = times[idx] - times[idx - 1] if idx > 0 else 999.0
                    gap_next = times[idx + 3] - times[idx + 2] if idx + 3 < n else 999.0

                    # 3-note clump: gap1 and gap2 are 16th intervals, but surrounded by 8th+ notes
                    if gap1 <= th_16th_gap and gap2 <= th_16th_gap and gap_prev >= th_8th_gap and gap_next >= th_8th_gap:
                        # Isolated 3-note collision!
                        # In Normal or Easy (or non-expert), resolve into symmetrical eighth notes [idx, idx+2]
                        if is_easy_or_normal or gap1 < 0.10:
                            smoothed_times.append(times[idx])
                            smoothed_times.append(times[idx + 2])
                            skip_idx.add(idx + 1)
                            skip_idx.add(idx + 2)
                            continue

                smoothed_times.append(times[idx])
            times = smoothed_times

        # Pass 3: Strict Minimum Gap & Anti-Overlap Deduplication
        eff_gap = max(0.095, float(min_gap or 0.095))
        final_times = []
        for t_val in times:
            if not final_times or (t_val - final_times[-1]) >= (eff_gap - 1e-4):
                final_times.append(t_val)

        for t_val in final_times:
            all_smoothed.append({'time': round(t_val, 3), 'lane': l})

    all_smoothed.sort(key=lambda x: (x['time'], x['lane']))
    return all_smoothed


# ==============================================================================
# V2 Engine: Tempo, Grid Alignment & Adaptive Dynamic Beatbar Generator
# ==============================================================================

def estimate_tempo_and_grid(y, sr, hop_length=256, bpm_override=None):
    """
    Detects continuous tempo (BPM) with high-precision parabolic peak interpolation,
    downbeat phase alignment, and transient envelopes.
    """
    duration = librosa.get_duration(y=y, sr=sr)
    
    # 1. Full onset strength envelope
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    
    # 2. Multi-band spectrogram for bass (kicks) and high (rolls / percussion)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    
    idx_bass = np.where((freqs >= 20) & (freqs < 160))[0]
    idx_high = np.where(freqs >= 2500)[0]
    
    onset_bass = librosa.onset.onset_strength(S=S[idx_bass, :], sr=sr, hop_length=hop_length)
    onset_high = librosa.onset.onset_strength(S=S[idx_high, :], sr=sr, hop_length=hop_length)
    
    # 3. Tempo (BPM) Estimation
    if bpm_override is not None and bpm_override > 20.0:
        bpm = float(bpm_override)
    else:
        max_lag_sec = 2.5
        ac = librosa.autocorrelate(onset_env, max_size=int(sr / hop_length * max_lag_sec))
        lags = np.arange(len(ac))
        times = lags * (hop_length / sr)
        
        peaks, _ = find_peaks(ac, distance=max(1, int(0.18 * sr / hop_length)))
        valid_peaks = [p for p in peaks if p > 1 and p < len(ac)-1 and (75.0 <= (60.0 / times[p]) <= 165.0)]
        
        if not valid_peaks:
            valid_peaks = [p for p in peaks if p > 1 and p < len(ac)-1 and (50.0 <= (60.0 / times[p]) <= 220.0)]
            
        if valid_peaks:
            best_p = max(valid_peaks, key=lambda p: ac[p])
            alpha = float(ac[best_p - 1])
            beta = float(ac[best_p])
            gamma = float(ac[best_p + 1])
            denom = alpha - 2.0 * beta + gamma
            if abs(denom) > 1e-6:
                p_refined = best_p + 0.5 * (alpha - gamma) / denom
            else:
                p_refined = float(best_p)
                
            refined_time = p_refined * (hop_length / sr)
            if refined_time > 0:
                raw_bpm = 60.0 / refined_time
                if abs(raw_bpm - round(raw_bpm)) < 0.15:
                    bpm = float(round(raw_bpm))
                else:
                    bpm = round(raw_bpm, 2)
            else:
                bpm = 120.0
        else:
            bpm = 120.0
            
    period = 60.0 / bpm
    
    # 4. Phase (Downbeat Alignment) Sweep
    norm_bass = onset_bass / (np.max(onset_bass) + 1e-6)
    norm_env = onset_env / (np.max(onset_env) + 1e-6)
    combined_onset = 0.6 * norm_bass + 0.4 * norm_env

    best_score = -1.0
    best_phi = 0.0
    phi_step = 0.005  # 5ms resolution
    for phi_cand in np.arange(0.0, period, phi_step):
        grid_times = np.arange(phi_cand, duration, period)
        g_frames = (grid_times * sr / hop_length).astype(int)
        g_frames = g_frames[g_frames < len(combined_onset)]
        if len(g_frames) > 0:
            score = float(np.sum(combined_onset[g_frames]))
            if score > best_score:
                best_score = score
                best_phi = float(phi_cand)

    # Attack transient compensation:
    # STFT window (2048 / 22050 = ~93ms) centers peak ~46ms after transient start.
    # Acoustic drum attack rises ~60-70ms before the envelope peak.
    # Subtract 0.065s so downbeats align precisely with the attack transient and human visual hits.
    best_phi = round((best_phi - 0.065) % period, 4)
                
    # 5. Smoothed RMS Energy Curve & Combined Intensity Curve
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    win_len = int(1.5 * sr / hop_length)  # ~1.5s window
    kernel = np.ones(win_len) / max(1, win_len)
    rms_smooth = np.convolve(rms, kernel, mode='same')
    min_rms = np.min(rms_smooth)
    max_rms = np.max(rms_smooth)
    rms_norm = (rms_smooth - min_rms) / (max_rms - min_rms + 1e-6)
    
    # 6. Combined Musical Intensity (Loudness + Bass Rhythm Section + High Percussion)
    ob_dense = np.convolve(onset_bass, kernel, mode='same')
    min_ob = np.min(ob_dense)
    max_ob = np.max(ob_dense)
    ob_norm = (ob_dense - min_ob) / (max_ob - min_ob + 1e-6)
    
    oh_dense = np.convolve(onset_high, kernel, mode='same')
    min_oh = np.min(oh_dense)
    max_oh = np.max(oh_dense)
    oh_norm = (oh_dense - min_oh) / (max_oh - min_oh + 1e-6)
    
    intensity = 0.45 * rms_norm + 0.40 * ob_norm + 0.15 * oh_norm
    
    return {
        'bpm': bpm,
        'period': period,
        'phase': best_phi,
        'onset_env': onset_env,
        'onset_bass': onset_bass,
        'onset_high': onset_high,
        'rms_norm': rms_norm,
        'intensity': intensity,
        'duration': duration,
        'sr': sr,
        'hop_length': hop_length
    }


def analyze_audio_v2(
    file_path,
    target_lane=4,
    preset="musical_beatbar",
    bpm=None,
    density_scale=1.0,
    quantize_grid="auto",
    min_gap=0.095,
    insert_rolls=True,
    halve_non_intense=True,
    intro_cutoff=3.8,
    custom_curve=None,
    progress_callback=None
):
    """
    V2 Auto Beats Generation (Acoustically Aware & Musical):
    
    Key Features:
    - Onset-driven musical placement: never spams continuous blind notes.
    - Adaptive Intensity Halving: automatically halves beat rate during calm verses/breakdowns,
      accelerating into driving syncopated eighths and burst rolls only during intense drops/climaxes.
    - True acoustic frequency band isolation for Lanes 0-3:
        * Lane 0 (BASS): Sub-bass & Kicks (20-130 Hz) - preserves kick drum syncopation & rests!
        * Lane 1 (LOW-MID): Bass synths & rhythm lines (130-850 Hz)
        * Lane 2 (MID-HIGH): Snares, claps, vocal accents (850-3500 Hz)
        * Lane 3 (TREBLE): Hi-hats, percussive clicks (3500-10000 Hz)
        * Lane 4 (BEATS): Primary visual beatbar rhythm, locked to the BPM grid.
    - Multi-Track mode (All 5 Lanes): Each lane generated from its true acoustic band!
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    file_path = resolve_audio_file(file_path)
        
    if progress_callback:
        progress_callback("Loading audio file...", 10)
        
    print(f"[V2] Analyzing {file_path} (preset='{preset}', lane={target_lane})...")
    
    sr = 22050
    hop_length = 256
    y, sr = librosa.load(file_path, sr=sr)
    duration = librosa.get_duration(y=y, sr=sr)
    
    if progress_callback:
        progress_callback("Detecting BPM & musical beat grid...", 25)
        
    info = estimate_tempo_and_grid(y, sr, hop_length=hop_length, bpm_override=bpm)
    detected_bpm = info['bpm']
    period = info['period']
    phi = info['phase']
    rms_norm = info['rms_norm']
    intensity = info.get('intensity', rms_norm)
    onset_env = info['onset_env']
    onset_high = info['onset_high']
    
    step_8th = period / 2.0
    step_16th = period / 4.0
    
    print(f"[V2] Detected BPM: {detected_bpm:.2f} (Period: {period:.4f}s, Phase: {phi:.4f}s)")
    
    if progress_callback:
        progress_callback("Separating acoustic frequency bands...", 45)
        
    # STFT for acoustic band separation
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    
    # Active music boundaries
    music_frames = np.where(rms_norm > 0.08)[0]
    if len(music_frames) > 0:
        start_time = max(0.0, (music_frames[0] * hop_length / sr) - period)
        end_time = min(duration, (music_frames[-1] * hop_length / sr) + period)
    else:
        start_time = 0.0
        end_time = duration
        
    scale = max(0.2, min(3.0, density_scale))
    beats = []
    
    # Acoustic bands definition: (lane_idx, f_min, f_max, sens_multiplier, grid_step)
    lane_bands = {
        0: (20, 130, 2.2 / scale, step_8th),      # Bass / Kicks (quarter/eighth syncopation)
        1: (130, 850, 1.7 / scale, step_8th),     # Low-Mid
        2: (850, 3500, 1.6 / scale, step_8th),    # Mid-High (Snares/Claps)
        3: (3500, 10000, 1.5 / scale, step_16th)  # Treble (Hi-hats)
    }

    if progress_callback:
        progress_callback("Generating musical notes...", 75)

    # --------------------------------------------------------------------------
    # Case A: Generating specific acoustic instrument lane (Lane 0, 1, 2, or 3)
    # --------------------------------------------------------------------------
    if target_lane in (0, 1, 2, 3) and preset != "multi_lane":
        f_min, f_max, sens_mult, grid_res = lane_bands[target_lane]
        idx = np.where((freqs >= f_min) & (freqs < f_max))[0]
        onset_band = librosa.onset.onset_strength(S=S[idx, :], sr=sr, hop_length=hop_length)
        
        # Effective min gap
        eff_gap = max(0.18 if target_lane == 0 else 0.08, min_gap)
        min_dist_frames = max(1, int(eff_gap * sr / hop_length))
        
        peaks, _ = find_peaks(onset_band, height=np.mean(onset_band) * sens_mult, distance=min_dist_frames)
        band_times = peaks * hop_length / sr
        
        for bt in band_times:
            if bt < start_time or bt > end_time:
                continue
            k = round((bt - phi) / grid_res)
            t_snap = phi + k * grid_res
            if abs(bt - t_snap) < 0.055:
                beats.append({'time': round(t_snap, 3), 'lane': target_lane})
            else:
                beats.append({'time': round(bt, 3), 'lane': target_lane})

    # --------------------------------------------------------------------------
    # Case B: Multi-Track Mode (All 5 Lanes)
    # --------------------------------------------------------------------------
    elif preset == "multi_lane" or target_lane is None or target_lane == -1:
        # 1. Generate Lanes 0 - 3 from their true acoustic frequency bands
        for l_idx in range(4):
            f_min, f_max, sens_mult, grid_res = lane_bands[l_idx]
            idx = np.where((freqs >= f_min) & (freqs < f_max))[0]
            onset_band = librosa.onset.onset_strength(S=S[idx, :], sr=sr, hop_length=hop_length)
            eff_gap = max(0.18 if l_idx == 0 else 0.08, min_gap)
            min_dist_frames = max(1, int(eff_gap * sr / hop_length))
            peaks, _ = find_peaks(onset_band, height=np.mean(onset_band) * sens_mult, distance=min_dist_frames)
            band_times = peaks * hop_length / sr
            for bt in band_times:
                if bt < start_time or bt > end_time:
                    continue
                k = round((bt - phi) / grid_res)
                t_snap = phi + k * grid_res
                if abs(bt - t_snap) < 0.055:
                    beats.append({'time': round(t_snap, 3), 'lane': l_idx})
                else:
                    beats.append({'time': round(bt, 3), 'lane': l_idx})
                    
        # 2. Generate Lane 4 (BEATS) as the primary syncopated beatbar rhythm with intensity halving
        beats_lane4 = analyze_audio_v2(
            file_path, target_lane=4, preset="musical_beatbar", bpm=detected_bpm,
            density_scale=density_scale, quantize_grid=quantize_grid, min_gap=min_gap,
            insert_rolls=insert_rolls, halve_non_intense=halve_non_intense, progress_callback=None
        )
        beats.extend(beats_lane4)

    # --------------------------------------------------------------------------
    # Case C: Steady Quarters Preset
    # --------------------------------------------------------------------------
    elif preset == "steady_quarters":
        lane = int(target_lane) if 0 <= target_lane <= 4 else 4
        t = phi
        while t < end_time:
            if t >= start_time:
                frame = int(t * sr / hop_length)
                if frame >= len(rms_norm):
                    break
                energy = rms_norm[frame]
                if energy >= 0.12 / scale:
                    beats.append({'time': round(t, 3), 'lane': lane})
            t += period

    # --------------------------------------------------------------------------
    # Case D: Energetic Eighths Preset
    # --------------------------------------------------------------------------
    elif preset == "energetic_eighths":
        lane = int(target_lane) if 0 <= target_lane <= 4 else 4
        t = phi
        while t < end_time:
            if t >= start_time:
                frame = int(t * sr / hop_length)
                if frame >= len(rms_norm):
                    break
                energy = rms_norm[frame]
                if energy >= 0.12 / scale:
                    beats.append({'time': round(t, 3), 'lane': lane})
                    t_half = t + step_8th
                    f_half = int(t_half * sr / hop_length)
                    if f_half < len(onset_env) and onset_env[f_half] > np.percentile(onset_env, 45 / scale):
                        beats.append({'time': round(t_half, 3), 'lane': lane})
            t += period

    # --------------------------------------------------------------------------
    # Case E: Climax Bursts Preset
    # --------------------------------------------------------------------------
    elif preset == "climax_bursts":
        lane = int(target_lane) if 0 <= target_lane <= 4 else 4
        t = phi
        while t < end_time:
            if t >= start_time:
                frame = int(t * sr / hop_length)
                if frame >= len(rms_norm):
                    break
                energy = rms_norm[frame]
                if energy >= 0.12 / scale:
                    beats.append({'time': round(t, 3), 'lane': lane})
                    t_half = t + step_8th
                    f_half = int(t_half * sr / hop_length)
                    if f_half < len(rms_norm):
                        beats.append({'time': round(t_half, 3), 'lane': lane})
                    if insert_rolls and energy >= 0.65 / scale:
                        beats.append({'time': round(t + step_16th, 3), 'lane': lane})
                        beats.append({'time': round(t + 3 * step_16th, 3), 'lane': lane})
            t += period

    # --------------------------------------------------------------------------
    # Case F: Musical Beatbar Preset (Default / Wicked Style - Adaptive)
    # --------------------------------------------------------------------------
    else:
        lane = int(target_lane) if 0 <= target_lane <= 4 else 4
        
        # Check custom curve or dynamic percentiles
        has_custom_curve = (custom_curve is not None)
        
        # Musical phrasing thresholds:
        th_calm = 0.33
        th_intense = 0.58
        th_climax = 0.82
        
        # Audio onset thresholds for syncopation
        w_f = int(0.04 * sr / hop_length)
        onset_th_syncopation = float(np.percentile(onset_env, min(92.0, 84.0 / scale)))
        
        beats = []
        t = phi
        cutoff_val = intro_cutoff if intro_cutoff is not None else 0.0
        
        while t < end_time:
            if t < start_time or t < cutoff_val or t > (end_time - 0.5):
                t += period
                continue
                
            frame = int(t * sr / hop_length)
            if frame >= len(intensity):
                break
                
            if has_custom_curve:
                if hasattr(custom_curve, 'get_value'):
                    inte = custom_curve.get_value(t)
                elif isinstance(custom_curve, dict) and 'points' in custom_curve:
                    times_c = [p['time'] for p in custom_curve['points']]
                    vals_c = [p['value'] for p in custom_curve['points']]
                    inte = float(np.interp(t, times_c, vals_c, left=vals_c[0], right=vals_c[-1]))
                else:
                    inte = intensity[frame]
            else:
                inte = intensity[frame]
            
            k = int(round((t - phi) / period))
            beat_in_bar = k % 4          # 0, 1, 2, 3
            bar_in_phrase = (k // 4) % 4 # 0, 1, 2, 3 (3 is turnaround bar)
            
            # Level 0: Rest / Ambient (<0.05)
            if inte < 0.05:
                t += period
                continue
                
            # Level 1: Calm / Breakdown / Verse -> Halve to Half-Notes (0.5x, downbeats only) + 4-bar turnaround fill
            # Strictly zero unwanted eighth notes!
            elif inte < th_calm:
                if halve_non_intense:
                    is_turnaround = (bar_in_phrase == 3)
                    if beat_in_bar in (0, 2) or is_turnaround:
                        beats.append({'time': round(t, 3), 'lane': lane})
                else:
                    beats.append({'time': round(t, 3), 'lane': lane})
                t += period
                continue
                
            # Level 2: Buildup & Steady Grooves -> Steady Quarter Notes (1x)
            elif inte < th_intense:
                beats.append({'time': round(t, 3), 'lane': lane})
                if beat_in_bar == 3:
                    t_half = t + step_8th
                    f_half = int(t_half * sr / hop_length)
                    if f_half < len(onset_env) and onset_env[f_half] > np.percentile(onset_env, 92.0):
                        beats.append({'time': round(t_half, 3), 'lane': lane})
                t += period
                continue
                
            # Level 3: Drop / Active Chorus -> Phrased Syncopation
            elif inte < th_climax:
                beats.append({'time': round(t, 3), 'lane': lane})
                if bar_in_phrase == 3:
                    # Turnaround fill at end of phrase
                    beats.append({'time': round(t + step_8th, 3), 'lane': lane})
                elif beat_in_bar in (0, 1):
                    # Vocal / upbeat accent syncopation on beats 1 & 2
                    t_half = t + step_8th
                    f_half = int(t_half * sr / hop_length)
                    if f_half < len(onset_env):
                        local_peak = np.max(onset_env[max(0, f_half - w_f):min(len(onset_env), f_half + w_f + 1)])
                        if local_peak > onset_th_syncopation:
                            beats.append({'time': round(t_half, 3), 'lane': lane})
                t += period
                continue
                
            # Level 4: Climax Solo / Peak Drop -> Symmetrical phrased rolls (never unbroken caterpillars)
            else:
                beats.append({'time': round(t, 3), 'lane': lane})
                if insert_rolls:
                    # Symmetrical 4-note rolls on beats 0 & 2, with eighth-note breathing space on beats 1 & 3
                    if beat_in_bar in (0, 2):
                        beats.append({'time': round(t + step_16th, 3), 'lane': lane})
                        beats.append({'time': round(t + step_8th, 3), 'lane': lane})
                        beats.append({'time': round(t + 3 * step_16th, 3), 'lane': lane})
                    else:
                        beats.append({'time': round(t + step_8th, 3), 'lane': lane})
                else:
                    beats.append({'time': round(t + step_8th, 3), 'lane': lane})
                t += period
                continue

    # 4. Quantization Grid Enforcement (if specified)
    if quantize_grid in ("1/4", "1/8", "1/16"):
        grid_step = period if quantize_grid == "1/4" else (step_8th if quantize_grid == "1/8" else step_16th)
        quantized = []
        for b in beats:
            q_time = round(phi + round((b['time'] - phi) / grid_step) * grid_step, 3)
            quantized.append({'time': max(0.0, q_time), 'lane': b['lane']})
        beats = quantized

    # 5. Sorting & Rhythm Smoothing (Anti-Caterpillar & Anti-Clump)
    beats.sort(key=lambda x: (x['time'], x['lane']))
    effective_min_gap = max(0.095, float(min_gap or 0.095))
    filtered_beats = smooth_rhythm_timeline(
        beats,
        period=period,
        phi=phi,
        anti_caterpillar=True,
        anti_clump=True,
        min_gap=effective_min_gap,
        max_consecutive_16ths=4,
        difficulty="Normal"
    )
            
    if progress_callback:
        progress_callback("Finished!", 100)
        
    print(f"[V2] Generated {len(filtered_beats)} beats total.")
    return filtered_beats


# ==============================================================================
# Video Beat Parser: Direct Computer Vision Beat Extraction
# ==============================================================================

def parse_beats_from_video(
    video_path,
    roi_coords,  # tuple: (x, y, width, height)
    mode="baseline_transition",  # "baseline_transition", "projection", "color_preset", "brightness", "custom_color"
    base_color=None,  # tuple/list: (B, G, R)
    hit_color=None,   # tuple/list: (B, G, R)
    color_name="purple",  # "purple", "red", "blue", "green", "yellow", "white"
    threshold=45.0,
    min_gap=0.15,
    lead_offset=0.040,  # Lead timing compensation (seconds, default ~40ms / 2.4 frames at 60fps)
    target_lane=4,
    deduplicate=True,
    progress_callback=None
):
    """
    Directly extracts rhythm beats from a target video by analyzing pixel color / brightness
    transitions in a user-selected Region of Interest (ROI) (e.g. the visual beatbar hit marker).
    
    Parameters:
        video_path: Absolute path to the video file.
        roi_coords: (x, y, w, h) bounding box of the detection zone.
        mode: Detection mode:
            - 'baseline_transition': Euclidean distance from empty baseline color (e.g. white->red/blue).
            - 'projection': Normalized 2-point projection along (hit_color - base_color).
            - 'color_preset': Built-in channel dominance ('purple', 'red', 'blue', etc.).
            - 'brightness': Luminance / flash detection.
            - 'custom_color': Distance to a specific target color.
        base_color: (B, G, R) background color when no note is present.
        hit_color: (B, G, R) note color when hit occurs.
        threshold: Sensitivity trigger threshold.
        min_gap: Minimum time gap between successive hits (seconds).
        target_lane: Target track index (0-4).
        progress_callback: Optional callback func(frame_idx, total_frames, percent).
        
    Returns:
        List of dicts: [{'time': float, 'lane': int}] sorted by time.
    """
    import cv2
    
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Could not open video file: {video_path}")
        
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Clip ROI to valid frame boundaries
    rx, ry, rw, rh = roi_coords
    rx = max(0, min(video_w - 1, int(rx)))
    ry = max(0, min(video_h - 1, int(ry)))
    rw = max(1, min(video_w - rx, int(rw)))
    rh = max(1, min(video_h - ry, int(rh)))
    
    # Setup metric evaluator
    if mode == "projection" and base_color is not None and hit_color is not None:
        c0 = np.array(base_color, dtype=float)
        c1 = np.array(hit_color, dtype=float)
        diff_vec = c1 - c0
        norm_sq = float(np.sum(diff_vec ** 2)) or 1.0
        def eval_metric(roi):
            mean_col = np.mean(roi, axis=(0, 1))
            return float(np.dot(mean_col - c0, diff_vec) / norm_sq) * 100.0
            
    elif mode == "color_preset":
        c_name = color_name.lower()
        if c_name == "purple":
            def eval_metric(roi):
                b = float(np.mean(roi[:, :, 0]))
                g = float(np.mean(roi[:, :, 1]))
                r = float(np.mean(roi[:, :, 2]))
                return (r + b) - 2.0 * g
        elif c_name == "red":
            def eval_metric(roi):
                b = float(np.mean(roi[:, :, 0]))
                g = float(np.mean(roi[:, :, 1]))
                r = float(np.mean(roi[:, :, 2]))
                return r * 2.0 - (g + b)
        elif c_name == "blue":
            def eval_metric(roi):
                b = float(np.mean(roi[:, :, 0]))
                g = float(np.mean(roi[:, :, 1]))
                r = float(np.mean(roi[:, :, 2]))
                return b * 2.0 - (r + g)
        elif c_name == "green":
            def eval_metric(roi):
                b = float(np.mean(roi[:, :, 0]))
                g = float(np.mean(roi[:, :, 1]))
                r = float(np.mean(roi[:, :, 2]))
                return g * 2.0 - (r + b)
        elif c_name == "yellow":
            def eval_metric(roi):
                b = float(np.mean(roi[:, :, 0]))
                g = float(np.mean(roi[:, :, 1]))
                r = float(np.mean(roi[:, :, 2]))
                return (r + g) - 2.0 * b
        else: # white / flash
            def eval_metric(roi):
                return float(np.mean(roi))
                
    elif mode == "brightness":
        def eval_metric(roi):
            return float(np.mean(roi))
            
    else:  # baseline_transition: Euclidean color distance from baseline
        c0 = np.array(base_color if base_color is not None else [100.0, 100.0, 100.0], dtype=float)
        def eval_metric(roi):
            mean_col = np.mean(roi, axis=(0, 1))
            return float(np.linalg.norm(mean_col - c0))
            
    signal = []
    report_interval = max(15, total_frames // 100)
    
    try:
        for f_idx in range(total_frames):
            ret, frame = cap.read()
            if not ret:
                break
                
            roi = frame[ry:ry+rh, rx:rx+rw]
            val = eval_metric(roi)
            signal.append(val)
            
            if progress_callback and (f_idx % report_interval == 0):
                pct = int((f_idx / max(1, total_frames)) * 100)
                res = progress_callback(f_idx, total_frames, pct)
                if res is False:
                    print("[VideoParser] Processing canceled by user.")
                    return []
    finally:
        cap.release()
        
    signal = np.array(signal)
    if len(signal) == 0:
        return []
        
    # 3-frame temporal binomial smoothing to eliminate sub-pixel noise and jitter
    if len(signal) >= 3:
        smooth_kernel = np.array([0.2, 0.6, 0.2])
        smoothed_signal = np.convolve(signal, smooth_kernel, mode='same')
    else:
        smoothed_signal = signal
        
    # Peak detection with prominence constraint and min_gap
    eff_gap = max(0.12, min_gap)
    min_dist_frames = max(1, int(eff_gap * fps))
    prom = max(5.0, threshold * 0.12)
    peaks, _ = find_peaks(smoothed_signal, height=threshold, distance=min_dist_frames, prominence=prom)
    
    # Deduplication pass to eliminate adjacent hits closer than eff_gap
    times = [max(0.0, round(float(p / fps) - lead_offset, 3)) for p in peaks]
    if deduplicate:
        dedup_times = []
        for t in times:
            if not dedup_times or (t - dedup_times[-1]) >= (eff_gap - 1e-4):
                dedup_times.append(t)
        times = dedup_times
        
    detected_beats = [
        {'time': t, 'lane': int(target_lane)}
        for t in times
    ]
    detected_beats.sort(key=lambda x: x['time'])
    
    if progress_callback:
        progress_callback(total_frames, total_frames, 100)
        
    print(f"[VideoParser] Processed {len(signal)} frames. Extracted {len(detected_beats)} clean beats on Lane {target_lane} (deduplicate={deduplicate}).")
    return detected_beats


def compare_beatmaps(beats_ref, beats_cand, tolerance=0.10):
    """
    Compares a candidate beatmap against a reference beatmap (e.g. human vs generated).
    Returns a dictionary of statistics.
    """
    times_ref = np.array(sorted([b['time'] for b in beats_ref]))
    times_cand = np.array(sorted([b['time'] for b in beats_cand]))
    
    if len(times_ref) == 0 or len(times_cand) == 0:
        return {'matches': 0, 'match_pct': 0.0, 'mean_offset': 0.0, 'std_offset': 0.0}
        
    matched = 0
    offsets = []
    
    for tr in times_ref:
        closest_idx = np.argmin(np.abs(times_cand - tr))
        diff = float(times_cand[closest_idx] - tr)
        if abs(diff) <= tolerance:
            matched += 1
            offsets.append(diff)
            
    return {
        'total_ref': len(times_ref),
        'total_cand': len(times_cand),
        'matches': matched,
        'match_pct': round((matched / len(times_ref)) * 100.0, 1),
        'mean_offset': round(float(np.mean(offsets)), 4) if offsets else 0.0,
        'std_offset': round(float(np.std(offsets)), 4) if offsets else 0.0
    }


def auto_detect_zones(audio_path, duration=None, bpm=None, phase=None):
    """
    Intelligently generates initial VideoZone layout from multi-band audio intensity.
    Returns a list of VideoZone objects from zones_editor.
    """
    import librosa
    from zones_editor import VideoZone

    if not os.path.exists(audio_path):
        return []
    audio_path = resolve_audio_file(audio_path)

    sr = 22050
    hop = 256
    y, sr = librosa.load(audio_path, sr=sr)
    dur = float(duration) if duration else (len(y) / sr)

    win_len = int(1.5 * sr / hop)
    kernel = np.ones(win_len) / max(1, win_len)

    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_s = np.convolve(rms, kernel, mode='same')
    rms_norm = (rms_s - np.min(rms_s)) / (np.max(rms_s) - np.min(rms_s) + 1e-6)

    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    idx_bass = np.where((freqs >= 20) & (freqs < 160))[0]
    idx_high = np.where((freqs >= 2500) & (freqs < 10000))[0]

    ob = librosa.onset.onset_strength(S=S[idx_bass, :], sr=sr, hop_length=hop)
    oh = librosa.onset.onset_strength(S=S[idx_high, :], sr=sr, hop_length=hop)
    ob_s = np.convolve(ob, kernel, mode='same')
    oh_s = np.convolve(oh, kernel, mode='same')
    ob_norm = (ob_s - np.min(ob_s)) / (np.max(ob_s) - np.min(ob_s) + 1e-6)
    oh_norm = (oh_s - np.min(oh_s)) / (np.max(oh_s) - np.min(oh_s) + 1e-6)

    intensity = 0.45 * rms_norm + 0.40 * ob_norm + 0.15 * oh_norm

    step_sec = 2.0
    sample_times = np.arange(0, dur, step_sec)
    raw_types = []
    for st in sample_times:
        idx = int(st * sr / hop)
        val = intensity[min(idx, len(intensity) - 1)]
        if st < 3.8:
            z = 'pause'
        elif val < 0.33:
            z = 'pause'
        elif val < 0.58:
            prev_idx = max(0, int((st - 4.0) * sr / hop))
            if val > intensity[prev_idx] + 0.08:
                z = 'speeding_up'
            else:
                z = 'normal'
        elif val < 0.79:
            z = 'normal'
        else:
            z = 'climax'
        raw_types.append((st, z))

    merged = []
    cur_start = 0.0
    cur_type = raw_types[0][1]

    for st, z in raw_types[1:]:
        if z != cur_type:
            merged.append({'start': round(cur_start, 2), 'end': round(st, 2), 'type': cur_type})
            cur_start = st
            cur_type = z
    merged.append({'start': round(cur_start, 2), 'end': round(dur, 2), 'type': cur_type})

    # Filter out tiny flickers (< 3.5s)
    cleaned = []
    for m in merged:
        if not cleaned:
            cleaned.append(m)
        elif m['end'] - m['start'] < 3.5:
            cleaned[-1]['end'] = m['end']
        elif m['type'] == cleaned[-1]['type']:
            cleaned[-1]['end'] = m['end']
        else:
            cleaned.append(m)

    zones = []
    for c in cleaned:
        zones.append(VideoZone(start_time=c['start'], end_time=c['end'], zone_type=c['type']))
    return zones


def analyze_audio_v3(
    file_path,
    target_lane=4,
    preset="musical_beatbar",
    bpm=None,
    density_scale=0.85,
    quantize_grid="auto",
    min_gap=0.095,
    anti_overlap=True,
    zones=None,
    intro_cutoff=3.8,
    insert_rolls=True,
    halve_non_intense=True,
    steady_section_cleanup=True,
    timing_offset=0.0,
    level=5,
    difficulty="Normal",
    level_mode="ramp_within_level",  # 3 modes: "ramp_within_level" (easy -> hard), "rise_with_level" (rises with level), "named_levels" (custom naming & difficulty)
    custom_curve=None,
    progress_callback=None,
    levels=None,
    use_zones=True,
    use_levels=True,
    edging_style="rhythmic_tension"
):
    """
    V3 Auto Beats Generation (Acoustically Aware V2 Core + Zones, Levels & Difficulty):
    
    Key Features:
    - Built on top of V2's musical phrasing and onset-driven acoustic engine.
    - Full dynamic frequency adjustments driven by:
        1. Difficulty ('Easy', 'Normal', 'Hard', 'Expert', 'Master')
        2. Rhythm & Video Zones ('credits', 'pause', 'slowing', 'speeding_up', 'edging', 'climax', 'normal')
        3. Levels (1 to 10) with 2 Modes:
            * 'ramp_within_level': Intra-level progression where song starts easy and ramps up to hard climax.
            * 'rise_with_level': Baseline difficulty scales directly up with each higher level number.
    - Anti-overlap spacing protection to keep visual notes clean and readable.
    - Guaranteed zero beats in 'credits' zones (skippable).
    - Fully customizable via settings dialog.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    file_path = resolve_audio_file(file_path)

    if progress_callback:
        progress_callback("Loading audio for V3 analysis...", 10)

    sr = 22050
    hop_length = 256
    y, sr = librosa.load(file_path, sr=sr)
    duration = librosa.get_duration(y=y, sr=sr)

    if progress_callback:
        progress_callback("Estimating BPM & downbeat grid...", 25)

    info = estimate_tempo_and_grid(y, sr, hop_length=hop_length, bpm_override=bpm)
    detected_bpm = info['bpm']
    period = info['period']
    phi = info['phase']
    rms_norm = info['rms_norm']
    intensity = info.get('intensity', rms_norm)
    onset_env = info['onset_env']

    step_8th = period / 2.0
    step_16th = period / 4.0

    if progress_callback:
        progress_callback("Configuring difficulty, zones, and level modes...", 50)

    # Active music boundaries
    music_frames = np.where(rms_norm > 0.08)[0]
    if len(music_frames) > 0:
        start_time = max(0.0, (music_frames[0] * hop_length / sr) - period)
        end_time = min(duration, (music_frames[-1] * hop_length / sr) + period)
    else:
        start_time = 0.0
        end_time = duration

    track_span = max(1.0, end_time - start_time)
    scale = max(0.2, min(3.0, float(density_scale or 0.85)))
    lane = int(target_lane) if target_lane is not None and 0 <= target_lane <= 4 else 4

    # 1. Level normalization (1 to 10)
    level_val = max(1, min(10, int(level or 5)))

    # 2. Difficulty normalization & multipliers
    diff_str = str(difficulty or "Normal").strip()
    if diff_str.lower() in ("auto", "default", "none"):
        if level_val <= 2:
            diff_str = "Easy"
        elif level_val <= 5:
            diff_str = "Normal"
        elif level_val <= 7:
            diff_str = "Hard"
        elif level_val <= 9:
            # diff_str = "Expert"  # Commented out: expert & master spam beats too much
            diff_str = "Hard"
        else:
            # diff_str = "Master"  # Commented out: expert & master spam beats too much
            diff_str = "Hard"

    diff_mult_map = {
        "easy": 0.65,
        "normal": 1.00,
        "hard": 1.30,
        # "expert": 1.65,
        # "master": 2.05,
        "expert": 1.30,  # Fallback to Hard if present in older files
        "master": 1.30,  # Fallback to Hard if present in older files
    }
    diff_mult = diff_mult_map.get(diff_str.lower(), 1.00)

    # 3. Unwrap Zones (only if use_zones is enabled; never auto-detect zones)
    zone_list = []
    if use_zones and zones:
        if hasattr(zones, 'zones'):
            zone_list = zones.zones
        elif isinstance(zones, list):
            zone_list = zones

    def get_zone_at(t_val):
        if not zone_list:
            return None
        for z in zone_list:
            zs = z.get('start_time', z.get('start', 0.0)) if isinstance(z, dict) else getattr(z, 'start_time', 0.0)
            ze = z.get('end_time', z.get('end', 0.0)) if isinstance(z, dict) else getattr(z, 'end_time', 0.0)
            if zs <= t_val < ze:
                return z if isinstance(z, dict) else z.to_dict()
        return None

    # Check custom curve
    has_custom_curve = (custom_curve is not None)

    beats = []
    t = phi
    cutoff_val = intro_cutoff if intro_cutoff is not None else 0.0
    norm_mode = str(level_mode or "ramp_within_level").lower()

    if progress_callback:
        progress_callback("Generating V3 musical beatbar notes...", 75)

    while t < duration:
        if t < start_time or t < cutoff_val or t > (duration - 0.4):
            t += period
            continue

        frame = int(t * sr / hop_length)
        if frame >= len(intensity):
            break

        # Base acoustic intensity from V2
        if has_custom_curve:
            if hasattr(custom_curve, 'get_value'):
                raw_inte = float(custom_curve.get_value(t))
            elif isinstance(custom_curve, dict) and 'points' in custom_curve:
                times_c = [p['time'] for p in custom_curve['points']]
                vals_c = [p['value'] for p in custom_curve['points']]
                raw_inte = float(np.interp(t, times_c, vals_c, left=vals_c[0], right=vals_c[-1]))
            else:
                raw_inte = float(intensity[frame])
        else:
            raw_inte = float(intensity[frame])

        k = int(round((t - phi) / period))
        beat_in_bar = k % 4
        bar_in_phrase = (k // 4) % 4

        # Zone resolution
        zone = get_zone_at(t)
        ztype = (zone.get('type', 'normal') if zone else 'normal').lower()

        # ----------------------------------------------------------------------
        # A. CREDITS ZONE (Strictly ZERO beats, skippable)
        # ----------------------------------------------------------------------
        if ztype == 'credits':
            t += period
            continue

        # ----------------------------------------------------------------------
        # B. ZONE FREQUENCY MULTIPLIER & SPECIFIC BEHAVIOR
        # ----------------------------------------------------------------------
        zone_mult = 1.0
        zone_force_half = False
        zone_force_rolls = False

        if ztype == 'pause':
            zone_mult = 0.35
            zone_force_half = True
        elif ztype == 'slowing':
            zs = zone.get('start_time', 0.0) if isinstance(zone, dict) else getattr(zone, 'start_time', 0.0)
            ze = zone.get('end_time', duration) if isinstance(zone, dict) else getattr(zone, 'end_time', duration)
            prog = max(0.0, min(1.0, (t - zs) / max(0.1, ze - zs)))
            zone_mult = 1.0 - 0.55 * prog  # decrescendo from 1.0 to 0.45
            if prog > 0.45:
                zone_force_half = True
        elif ztype == 'speeding_up':
            zs = zone.get('start_time', 0.0) if isinstance(zone, dict) else getattr(zone, 'start_time', 0.0)
            ze = zone.get('end_time', duration) if isinstance(zone, dict) else getattr(zone, 'end_time', duration)
            prog = max(0.0, min(1.0, (t - zs) / max(0.1, ze - zs)))
            zone_mult = 0.65 + 0.75 * prog  # accelerando from 0.65 to 1.40
        elif ztype == 'edging':
            zs = zone.get('start_time', 0.0) if isinstance(zone, dict) else getattr(zone, 'start_time', 0.0)
            ze = zone.get('end_time', duration) if isinstance(zone, dict) else getattr(zone, 'end_time', duration)
            zone_prog = max(0.0, min(1.0, (t - zs) / max(0.1, ze - zs)))
            if "build" in str(edging_style).lower():
                zone_mult = 0.60 + 0.85 * (zone_prog ** 1.1)
            else:
                zone_mult = 1.05
        elif ztype == 'climax':
            zone_mult = 1.55
            zone_force_rolls = True

        # ----------------------------------------------------------------------
        # C. LEVEL FREQUENCY ADJUSTMENT (3 MODES WITH CUSTOM NAMING):
        # Mode 1: "ramp_within_level" (Each level starts from easy to hard)
        # Mode 2: "rise_with_level" (Difficulty rises with new level)
        # Mode 3: "named_levels" (Custom naming & manual difficulty per chapter)
        # Note: All modes support custom naming!
        # ----------------------------------------------------------------------
        active_ch = None
        if use_levels and levels and isinstance(levels, (list, tuple)):
            for cand in levels:
                cs = cand.get('start_time', 0.0) if isinstance(cand, dict) else getattr(cand, 'start_time', 0.0)
                ce = cand.get('end_time', duration) if isinstance(cand, dict) else getattr(cand, 'end_time', duration)
                if cs <= t <= ce:
                    active_ch = cand
                    break

        ch_lvl_val = level_val
        ch_diff_mult = diff_mult
        ch_span_start = start_time
        ch_span_end = duration

        if active_ch:
            ch_lvl_val = active_ch.get('level', level_val) if isinstance(active_ch, dict) else getattr(active_ch, 'level', level_val)
            ch_diff_name = active_ch.get('difficulty', diff_str) if isinstance(active_ch, dict) else getattr(active_ch, 'difficulty', diff_str)
            ch_diff_mult = diff_mult_map.get(str(ch_diff_name).lower(), diff_mult)
            ch_span_start = active_ch.get('start_time', start_time) if isinstance(active_ch, dict) else getattr(active_ch, 'start_time', start_time)
            ch_span_end = active_ch.get('end_time', duration) if isinstance(active_ch, dict) else getattr(active_ch, 'end_time', duration)

        ch_span = max(0.5, ch_span_end - ch_span_start)

        if not use_levels:
            level_mult = 1.00
            eff_diff_mult = diff_mult
        elif "named" in norm_mode or "just_naming" in norm_mode or "mode3" in norm_mode:
            # Mode 3: Custom naming & chapter difficulty
            level_mult = 1.00
            eff_diff_mult = ch_diff_mult
        elif "ramp" in norm_mode or "within" in norm_mode or "easy_to_hard" in norm_mode:
            # Mode 1: Progress from easy at start of level chapter to hard at chapter climax
            lvl_prog = max(0.0, min(1.0, (t - ch_span_start) / ch_span))
            ramp_curve = 0.52 + 0.96 * (lvl_prog ** 1.15)
            level_scale = 0.65 + 0.075 * ch_lvl_val
            level_mult = ramp_curve * level_scale
            eff_diff_mult = ch_diff_mult
        else:
            # Mode 2: Baseline difficulty rises directly with the Level number
            level_base = 0.45 + (ch_lvl_val - 1) * 0.165
            phrase_step = (k // 16) * 0.02
            level_mult = level_base + min(0.25, phrase_step)
            eff_diff_mult = ch_diff_mult

        # ----------------------------------------------------------------------
        # D. COMBINED EFFECTIVE INTENSITY
        # ----------------------------------------------------------------------
        eff_inte = raw_inte * scale * zone_mult * level_mult * eff_diff_mult

        # ----------------------------------------------------------------------
        # E. MUSICAL NOTE PLACEMENT (Based on V2 core logic)
        # ----------------------------------------------------------------------
        # Preset: steady_quarters
        if preset == "steady_quarters":
            if eff_inte >= 0.10:
                beats.append({'time': round(t + timing_offset, 3), 'lane': lane})

        # Preset: energetic_eighths
        elif preset == "energetic_eighths":
            if eff_inte >= 0.10:
                beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                t_half = t + step_8th
                f_half = int(t_half * sr / hop_length)
                th_onset = 50.0 if diff_str in ("Hard", "Expert", "Master") else 65.0
                if f_half < len(onset_env) and onset_env[f_half] > np.percentile(onset_env, th_onset / scale):
                    beats.append({'time': round(t_half + timing_offset, 3), 'lane': lane})

        # Preset: climax_bursts
        elif preset == "climax_bursts":
            if eff_inte >= 0.08:
                beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                t_half = t + step_8th
                beats.append({'time': round(t_half + timing_offset, 3), 'lane': lane})
                if (insert_rolls or zone_force_rolls) and eff_inte >= 0.55:
                    beats.append({'time': round(t + step_16th + timing_offset, 3), 'lane': lane})
                    beats.append({'time': round(t + 3 * step_16th + timing_offset, 3), 'lane': lane})

        # Preset: musical_beatbar (Default V2 Adaptive Engine + Enhancements)
        else:
            # ------------------------------------------------------------------
            # SPECIAL: EDGING TENSION ZONE HANDLING
            # ------------------------------------------------------------------
            if ztype == 'edging':
                zs = zone.get('start_time', 0.0) if isinstance(zone, dict) else getattr(zone, 'start_time', 0.0)
                ze = zone.get('end_time', duration) if isinstance(zone, dict) else getattr(zone, 'end_time', duration)
                zone_prog = max(0.0, min(1.0, (t - zs) / max(0.1, ze - zs)))
                is_turnaround = (bar_in_phrase == 3)
                is_expert_master = diff_str in ("Expert", "Master") or level_val >= 8

                if "build" in str(edging_style).lower():
                    # Variant 3: Building Tension (Sparse dramatic holds accelerating into rapid stutter pulses)
                    if zone_prog < 0.35:
                        # Phase 1: Sparse dramatic holds (anchored downbeat every bar, holding tension on beats 1, 2, 3)
                        if beat_in_bar == 0:
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                    elif zone_prog < 0.70:
                        # Phase 2: Steady half-notes (beats 0 and 2) + alternating stutter pulses
                        if beat_in_bar in (0, 2):
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                            if beat_in_bar == 0 and ((k // 4) % 2 == 0 or is_turnaround):
                                beats.append({'time': round(t + step_8th + timing_offset, 3), 'lane': lane})
                    else:
                        # Phase 3: Intense acceleration into rapid stutter pulses
                        if beat_in_bar in (0, 2):
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                            beats.append({'time': round(t + step_8th + timing_offset, 3), 'lane': lane})
                        elif is_turnaround and insert_rolls and beat_in_bar == 3:
                            beats.append({'time': round(t + step_16th + timing_offset, 3), 'lane': lane})
                else:
                    # Variant 1: Rhythmic Tension (Steady groove + stutter double-pulses followed by dramatic breathers)
                    is_pulse_bar = ((k // 4) % 2 == 0) or is_turnaround
                    if is_pulse_bar:
                        # Pulse Bar: Steady half-notes (beats 0 & 2) + crisp stutter pulse doublet
                        if beat_in_bar == 0:
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                            beats.append({'time': round(t + step_8th + timing_offset, 3), 'lane': lane})
                            if is_expert_master and insert_rolls:
                                beats.append({'time': round(t + step_16th + timing_offset, 3), 'lane': lane})
                        elif beat_in_bar == 2:
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                        elif is_turnaround and beat_in_bar == 3:
                            # Phrase turnaround buildup fill
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                            beats.append({'time': round(t + step_8th + timing_offset, 3), 'lane': lane})
                    else:
                        # Dramatic Pause Bar: Solid downbeat anchor, followed by dramatic tension hold
                        if beat_in_bar == 0:
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                        elif beat_in_bar == 2 and not halve_non_intense:
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})

                t += period
                continue

            # 0. Rest / Ambient Silence
            if eff_inte < 0.04:
                t += period
                continue

            # 1. Calm / Breakdown Tier (< 0.32 or forced half)
            if eff_inte < 0.32 or zone_force_half:
                if halve_non_intense:
                    if diff_str == "Easy" or level_val <= 2:
                        # Easy: downbeat only
                        if beat_in_bar == 0:
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                    else:
                        # Normal/Hard: half-notes (beats 0 and 2)
                        if beat_in_bar in (0, 2):
                            beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                    
                    # 4-bar turnaround fill
                    if bar_in_phrase == 3 and beat_in_bar == 3 and diff_str != "Easy":
                        t_half = t + step_8th
                        f_half = int(t_half * sr / hop_length)
                        if f_half < len(onset_env) and onset_env[f_half] > np.percentile(onset_env, 82.0):
                            beats.append({'time': round(t_half + timing_offset, 3), 'lane': lane})
                else:
                    if beat_in_bar in (0, 2):
                        beats.append({'time': round(t + timing_offset, 3), 'lane': lane})

            # 2. Steady Groove Tier (0.32 <= eff_inte < 0.60)
            elif eff_inte < 0.60:
                beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                # On upbeat, add syncopation if audio onset is strong and difficulty is not Easy
                if diff_str in ("Hard", "Expert", "Master") or (diff_str == "Normal" and bar_in_phrase == 3):
                    if beat_in_bar in (1, 3):
                        t_half = t + step_8th
                        f_half = int(t_half * sr / hop_length)
                        if f_half < len(onset_env) and onset_env[f_half] > np.percentile(onset_env, 78.0):
                            beats.append({'time': round(t_half + timing_offset, 3), 'lane': lane})

            # 3. Active Chorus / Drop Tier (0.60 <= eff_inte < 0.85)
            elif eff_inte < 0.85:
                beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                # Driving eighths on beats 0 and 2
                if beat_in_bar in (0, 2) or bar_in_phrase == 3:
                    t_half = t + step_8th
                    beats.append({'time': round(t_half + timing_offset, 3), 'lane': lane})
                # Add 16th flam accent for Expert/Master
                if (diff_str in ("Expert", "Master") or level_val >= 8) and insert_rolls and bar_in_phrase == 3:
                    if beat_in_bar == 3:
                        beats.append({'time': round(t + step_16th + timing_offset, 3), 'lane': lane})

            # 4. Peak Climax Tier (eff_inte >= 0.85 or zone_force_rolls)
            else:
                beats.append({'time': round(t + timing_offset, 3), 'lane': lane})
                t_half = t + step_8th
                beats.append({'time': round(t_half + timing_offset, 3), 'lane': lane})
                # Insert rapid 16th rolls symmetrically
                if (insert_rolls or zone_force_rolls) and diff_str not in ("Easy", "Normal"):
                    # Turnaround 4-note roll on beat 3 of phrase turnaround
                    if bar_in_phrase == 3 and beat_in_bar == 3:
                        beats.append({'time': round(t + step_16th + timing_offset, 3), 'lane': lane})
                        beats.append({'time': round(t + 3 * step_16th + timing_offset, 3), 'lane': lane})
                    # Commented out: rapid alternating 16th roll bursts in Expert/Master spammed beats too much
                    # elif beat_in_bar in (0, 2) and diff_str in ("Expert", "Master"):
                    #     beats.append({'time': round(t + step_16th + timing_offset, 3), 'lane': lane})
                    #     beats.append({'time': round(t + 3 * step_16th + timing_offset, 3), 'lane': lane})

        t += period

    # 4. Quantization Grid Enforcement (if specified)
    if quantize_grid in ("1/4", "1/8", "1/16"):
        grid_step = period if quantize_grid == "1/4" else (step_8th if quantize_grid == "1/8" else step_16th)
        quantized = []
        for b in beats:
            q_time = round(phi + round((b['time'] - phi) / grid_step) * grid_step, 3)
            quantized.append({'time': max(0.0, q_time), 'lane': b['lane']})
        beats = quantized

    # 4b. Explicit Credits Zone Removal (Guarantees strictly zero beats in credits)
    if zone_list:
        credits_spans = []
        for z in zone_list:
            zt = (z.get('type') if isinstance(z, dict) else getattr(z, 'zone_type', getattr(z, 'type', '')) or '').lower()
            if zt == 'credits':
                zs = z.get('start_time', z.get('start', 0.0)) if isinstance(z, dict) else getattr(z, 'start_time', 0.0)
                ze = z.get('end_time', z.get('end', 0.0)) if isinstance(z, dict) else getattr(z, 'end_time', 0.0)
                credits_spans.append((zs, ze))
        if credits_spans:
            beats = [b for b in beats if not any(s <= b['time'] <= e for s, e in credits_spans)]

    # 5. Sorting & Rhythm Smoothing (Anti-Caterpillar & Anti-Clump)
    beats.sort(key=lambda x: (x['time'], x['lane']))
    effective_min_gap = max(0.095 if anti_overlap else 0.05, float(min_gap or 0.095))
    filtered_beats = smooth_rhythm_timeline(
        beats,
        period=period,
        phi=phi,
        anti_caterpillar=anti_overlap,
        anti_clump=steady_section_cleanup or anti_overlap,
        min_gap=effective_min_gap,
        max_consecutive_16ths=4,
        difficulty=diff_str
    )

    if progress_callback:
        progress_callback("V3 Beats Generation Complete!", 100)

    print(
        f"[V3] Generated {len(filtered_beats)} beats (level={level_val}, diff='{diff_str}', "
        f"mode='{norm_mode}', anti_overlap={anti_overlap}, zones={len(zone_list)})."
    )
    return filtered_beats


def generate_beats_from_zones(media_path, zones, target_lane=4, bpm=None, intro_cutoff=3.8,
                              level=5, difficulty="Normal", level_mode="ramp_within_level",
                              levels=None, use_zones=True, use_levels=True, edging_style="rhythmic_tension"):
    """Convenience wrapper for generating V3 beats directly from a list of VideoZones."""
    return analyze_audio_v3(
        media_path,
        target_lane=target_lane,
        bpm=bpm,
        zones=zones,
        anti_overlap=True,
        intro_cutoff=intro_cutoff,
        level=level,
        difficulty=difficulty,
        level_mode=level_mode,
        levels=levels,
        use_zones=use_zones,
        use_levels=use_levels,
        edging_style=edging_style
    )

