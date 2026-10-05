#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from bin.project_runtime import add_config_argument, data_path, load_project
from bin.project_runtime import resource_path

import numpy as np


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pitch_to_hz(pitch: str) -> float:
    from music21.pitch import Pitch

    if pitch.strip().upper() in {"R", "REST"}:
        return 0.0
    # The planner emits music21's B-4 flat spelling; accept it as well as Bb4.
    return float(Pitch(pitch.strip()).frequency)


def _validate_event_timing(events: list[dict], meter: str) -> None:
    """Reject timing the existing concatenating backend cannot represent."""
    try:
        numerator, denominator = (int(part) for part in meter.split("/"))
    except (TypeError, ValueError) as exc:
        raise ValueError("A simple constant meter such as 3/4 is required") from exc
    if numerator <= 0 or denominator <= 0:
        raise ValueError("Meter components must be positive")
    measure_beats = numerator * 4.0 / denominator
    cursor = 0.0
    for event in events:
        if event.get("is_slur") or not str(event.get("lyric", "")).strip():
            raise ValueError("Nishiren adapter does not yet support slurs or blank-lyric events")
        if _pitch_to_hz(str(event["pitch"])) <= 0:
            raise ValueError("Nishiren adapter does not yet support rests")
        measure = int(event["measure"])
        beat = float(event["start_beat"])
        start = (measure - 1) * measure_beats + beat - 1
        duration = float(event["duration_beats"])
        if (measure < 1 or not 1 <= beat < measure_beats + 1
                or not math.isfinite(start) or not math.isfinite(duration) or duration <= 0):
            raise ValueError("Invalid event measure, beat or duration")
        if not math.isclose(start, cursor, abs_tol=1e-6):
            raise ValueError("Nishiren adapter requires contiguous events starting at measure 1 beat 1")
        cursor += duration


def _load_nishiren_phoneme_map(nishiren_root: Path) -> dict[str, int]:
    # The voicebank's authoritative phoneme-id mapping is the json file referenced
    # by dsconfig.yaml (not the training-time dsdict.yaml ordering).
    obj = _load_json(nishiren_root / "dsmain" / "phonemes.json")
    if not isinstance(obj, dict):
        raise ValueError(f"Unexpected dsmain/phonemes.json shape: {type(obj)}")
    return {str(k): int(v) for k, v in obj.items()}


def _load_nishiren_language_map(nishiren_root: Path) -> dict[str, int]:
    obj = _load_json(nishiren_root / "dsmain" / "languages.json")
    if isinstance(obj, dict) and all(isinstance(v, int) for v in obj.values()):
        return obj
    raise ValueError(f"Could not understand Nishiren languages.json: {obj}")


def _load_nishiren_embedding(path: Path, hidden: int) -> np.ndarray:
    try:
        arr = np.load(path, allow_pickle=False).astype(np.float32).reshape(-1)
        if arr.size == hidden:
            return arr
    except Exception:
        pass

    try:
        arr = np.loadtxt(path, dtype=np.float32).reshape(-1)
        if arr.size == hidden:
            return arr
    except Exception:
        pass

    arr = np.fromfile(path, dtype=np.float32).reshape(-1)
    if arr.size == hidden:
        return arr
    raise ValueError(f"Could not load speaker embedding from {path}; expected {hidden} floats, got {arr.size}.")


def _normalize_nishiren_phonemes(phonemes: list[str], language_prefix: str) -> list[str]:
    out: list[str] = []
    for ph in phonemes:
        ph = str(ph).strip()
        if not ph:
            continue
        # Accept already-prefixed Nishiren tokens like "en/aa".
        if "/" in ph:
            out.append(ph)
            continue
        # Accept ARPABET-like tokens like "HH" or "AH0".
        while ph and ph[-1].isdigit():
            ph = ph[:-1]
        out.append(f"{language_prefix}/{ph.lower()}")
    return out


def _word_to_phones(word: str, lex: dict[str, list[str]]) -> list[str]:
    normalized = "".join(c.lower() for c in word if c.isalpha() or c in {"'", "-"}).strip("-'")
    phones = lex.get(normalized)
    if not isinstance(phones, list) or not phones or not all(isinstance(p, str) and p.strip() for p in phones):
        raise ValueError(f"No pronunciation for {word!r}; supply event phonemes or a pronunciation_lexicon entry")
    return phones


def _preflight_models(root: Path, style: str) -> None:
    required = [
        "dsdur/linguistic.onnx", "dsdur/dur.onnx", "dsdur/phonemes.json", "dsdur/languages.json",
        "dsmain/acoustic.onnx", "dsmain/phonemes.json", "dsmain/languages.json", f"dsmain/{style}.emb",
    ]
    for group, model in (("dspitch", "pitch"), ("dsvariance", "variance")):
        # Optional model groups may be absent, but partial installations fail.
        folder = root / group
        if folder.exists():
            required += [f"{group}/linguistic.onnx", f"{group}/{model}.onnx",
                         f"{group}/phonemes.json", f"{group}/languages.json"]
    missing = [str(root / name) for name in required if not (root / name).is_file()]
    if not list((root / "dsvocoder").glob("*.onnx")):
        missing.append(str(root / "dsvocoder/*.onnx"))
    if missing:
        raise ValueError("Missing Nishiren resources: " + ", ".join(missing))


def _run_nishiren_onnx(
    *,
    nishiren_root: Path,
    language: str,
    style: str,
    events: list[dict],
    tempo_bpm: float,
    sr: int,
    out_wav: Path,
    log_path: Path | None,
    debug_out: Path | None,
    vel: float,
    gender: float,
    steps: int,
    lexicon: dict[str, list[str]],
) -> dict:
    os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")
    import onnxruntime as ort  # type: ignore[import-not-found]
    import soundfile as sf  # type: ignore[import-not-found]

    HOP = 512
    HIDDEN = 384

    # Use duration model (dsdur) to get realistic phoneme timing.
    dsdur_root = nishiren_root / "dsdur"
    if not (dsdur_root / "linguistic.onnx").exists() or not (dsdur_root / "dur.onnx").exists():
        raise SystemExit(f"Missing Nishiren duration models under {dsdur_root}.")

    ph_id_map = _load_json(dsdur_root / "phonemes.json")
    lang_map = _load_json(dsdur_root / "languages.json")
    if language not in lang_map:
        raise SystemExit(f"Nishiren language {language!r} not found in {lang_map}.")

    ling = ort.InferenceSession(str(dsdur_root / "linguistic.onnx"), providers=["CPUExecutionProvider"])
    dur_sess = ort.InferenceSession(str(dsdur_root / "dur.onnx"), providers=["CPUExecutionProvider"])

    seconds_per_beat = 60.0 / tempo_bpm

    word_div: list[int] = []
    word_dur: list[int] = []
    ph_seq: list[str] = []
    ph_ids: list[int] = []
    ph_lang_ids: list[int] = []
    ph_midi: list[int] = []
    ph_to_event: list[int] = []

    for ev_idx, ev in enumerate(events):
        lyric = str(ev.get("lyric", "")).strip()
        if lyric == "":
            continue
        explicit_ph = ev.get("phonemes", None)
        if isinstance(explicit_ph, list) and explicit_ph:
            phones = _normalize_nishiren_phonemes(explicit_ph, language)
        else:
            phones = _normalize_nishiren_phonemes(_word_to_phones(lyric, lexicon), language)
        if not phones:
            continue

        dur_sec = float(ev["duration_beats"]) * seconds_per_beat
        frames = max(1, int(round(dur_sec * sr / HOP)))
        word_div.append(len(phones))
        word_dur.append(frames)

        # Midi note id per phoneme.
        hz = _pitch_to_hz(str(ev["pitch"]))
        midi = int(round(69 + 12 * math.log2(hz / 440.0))) if hz > 0 else 0

        for ph in phones:
            if ph not in ph_id_map:
                raise KeyError(f"Missing Nishiren phoneme id for {ph}.")
            ph_seq.append(ph)
            ph_ids.append(int(ph_id_map[ph]))
            ph_lang_ids.append(int(lang_map[language]))
            ph_midi.append(int(midi))
            ph_to_event.append(ev_idx)

    if not ph_ids:
        raise SystemExit("No phonemes produced; check lyric/phonemes in vocal_events.json.")

    dur_tokens = np.array([ph_ids], dtype=np.int64)
    dur_languages = np.array([ph_lang_ids], dtype=np.int64)
    word_div_arr = np.array([word_div], dtype=np.int64)
    word_dur_arr = np.array([word_dur], dtype=np.int64)

    encoder_out, x_masks = ling.run(
        None, {"tokens": dur_tokens, "languages": dur_languages, "word_div": word_div_arr, "word_dur": word_dur_arr}
    )

    style_emb_path = dsdur_root / f"{style}.emb"
    if not style_emb_path.exists():
        style_emb_path = nishiren_root / "dsmain" / f"{style}.emb"
    spk_tok = _load_nishiren_embedding(style_emb_path, HIDDEN)
    spk_embed_tok = np.tile(spk_tok.reshape(1, 1, HIDDEN), (1, dur_tokens.shape[1], 1)).astype(np.float32)
    ph_midi_arr = np.array([ph_midi], dtype=np.int64)

    ph_dur_pred = dur_sess.run(
        None, {"encoder_out": encoder_out, "x_masks": x_masks, "ph_midi": ph_midi_arr, "spk_embed": spk_embed_tok}
    )[0].reshape(-1).astype(np.float32)

    # Rescale predicted phoneme durations so per-word sums match the note durations.
    ph_frames: list[int] = []
    cur = 0
    for w_len, w_frames in zip(word_div, word_dur):
        seg = np.maximum(ph_dur_pred[cur : cur + w_len], 1.0)
        cur += w_len
        scale = float(w_frames) / float(seg.sum()) if float(seg.sum()) > 0 else 1.0
        seg_scaled = np.maximum(np.round(seg * scale), 1.0).astype(int)
        drift = int(w_frames) - int(seg_scaled.sum())
        if drift != 0:
            seg_scaled[-1] = max(1, int(seg_scaled[-1]) + drift)
        ph_frames.extend([int(x) for x in seg_scaled.tolist()])

    durations = np.array([ph_frames], dtype=np.int64)
    n_frames = int(durations.sum())

    # Piecewise-constant f0 per phoneme (per event pitch).
    f0 = np.zeros((1, n_frames), dtype=np.float32)
    t = 0
    for ph_f, ev_idx in zip(ph_frames, ph_to_event):
        hz = _pitch_to_hz(str(events[ev_idx]["pitch"]))
        f0[0, t : t + ph_f] = float(hz) if hz > 0 else 0.0
        t += int(ph_f)

    base_pitch = f0.copy()

    # Pitch model (dspitch): predicts a more realistic pitch curve from notes + phonemes.
    dspitch_root = nishiren_root / "dspitch"
    pitch_curve = f0.copy()
    if (dspitch_root / "linguistic.onnx").exists() and (dspitch_root / "pitch.onnx").exists():
        pitch_ph_map = _load_json(dspitch_root / "phonemes.json")
        pitch_lang_map = _load_json(dspitch_root / "languages.json")
        pitch_tokens = np.array([[int(pitch_ph_map[p]) for p in ph_seq]], dtype=np.int64)
        pitch_languages = np.array([[int(pitch_lang_map[language]) for _ in ph_seq]], dtype=np.int64)
        pitch_ling = ort.InferenceSession(str(dspitch_root / "linguistic.onnx"), providers=["CPUExecutionProvider"])
        pitch_onx = ort.InferenceSession(str(dspitch_root / "pitch.onnx"), providers=["CPUExecutionProvider"])
        pitch_encoder_out, _ = pitch_ling.run(None, {"tokens": pitch_tokens, "languages": pitch_languages, "ph_dur": durations})

        note_midi: list[float] = []
        note_rest: list[bool] = []
        note_dur: list[int] = []
        for ev in events:
            dur_sec = float(ev["duration_beats"]) * seconds_per_beat
            frames = max(1, int(round(dur_sec * sr / HOP)))
            hz = _pitch_to_hz(str(ev["pitch"]))
            midi = float(69 + 12 * math.log2(hz / 440.0)) if hz > 0 else 0.0
            note_midi.append(midi)
            note_rest.append(hz <= 0)
            note_dur.append(frames)

        pitch_spk_path = dspitch_root / f"{style}.emb"
        if not pitch_spk_path.exists():
            pitch_spk_path = nishiren_root / "dsmain" / f"{style}.emb"
        pitch_spk = _load_nishiren_embedding(pitch_spk_path, HIDDEN)
        pitch_spk_embed = np.tile(pitch_spk.reshape(1, 1, HIDDEN), (1, n_frames, 1)).astype(np.float32)

        expr = np.zeros((1, n_frames), dtype=np.float32)
        retake = np.zeros((1, n_frames), dtype=bool)
        steps_arr = np.array(int(steps), dtype=np.int64)
        pitch_curve_pred = pitch_onx.run(
            None,
            {
                "encoder_out": pitch_encoder_out,
                "ph_dur": durations,
                "note_midi": np.array([note_midi], dtype=np.float32),
                "note_rest": np.array([note_rest], dtype=bool),
                "note_dur": np.array([note_dur], dtype=np.int64),
                "pitch": pitch_curve.astype(np.float32),
                "expr": expr,
                "retake": retake,
                "spk_embed": pitch_spk_embed,
                "steps": steps_arr,
            },
        )[0].astype(np.float32)

        # Fallback: if the pitch model collapses to near-monotone, keep the note-derived pitch.
        voiced = pitch_curve_pred[pitch_curve_pred > 1.0]
        voiced_std = float(np.std(voiced)) if voiced.size else 0.0
        if voiced_std < 8.0:
            pitch_curve = base_pitch
        else:
            pitch_curve = pitch_curve_pred

    # Variance model (dsvariance): predicts breathiness/voicing/tension curves given pitch + phonemes.
    dsvar_root = nishiren_root / "dsvariance"
    breathiness = np.zeros((1, n_frames), dtype=np.float32)
    voicing = np.zeros((1, n_frames), dtype=np.float32)
    tension = np.zeros((1, n_frames), dtype=np.float32)
    if (dsvar_root / "linguistic.onnx").exists() and (dsvar_root / "variance.onnx").exists():
        var_ph_map = _load_json(dsvar_root / "phonemes.json")
        var_lang_map = _load_json(dsvar_root / "languages.json")
        var_tokens = np.array([[int(var_ph_map[p]) for p in ph_seq]], dtype=np.int64)
        var_languages = np.array([[int(var_lang_map[language]) for _ in ph_seq]], dtype=np.int64)
        var_ling = ort.InferenceSession(str(dsvar_root / "linguistic.onnx"), providers=["CPUExecutionProvider"])
        var_onx = ort.InferenceSession(str(dsvar_root / "variance.onnx"), providers=["CPUExecutionProvider"])
        var_encoder_out, _ = var_ling.run(None, {"tokens": var_tokens, "languages": var_languages, "ph_dur": durations})

        var_spk_path = dsvar_root / f"{style}.emb"
        if not var_spk_path.exists():
            var_spk_path = nishiren_root / "dsmain" / f"{style}.emb"
        var_spk = _load_nishiren_embedding(var_spk_path, HIDDEN)
        var_spk_embed = np.tile(var_spk.reshape(1, 1, HIDDEN), (1, n_frames, 1)).astype(np.float32)

        retake3 = np.zeros((1, n_frames, 3), dtype=bool)
        steps_arr = np.array(int(steps), dtype=np.int64)
        breathiness, voicing, tension = var_onx.run(
            None,
            {
                "encoder_out": var_encoder_out,
                "ph_dur": durations,
                "pitch": pitch_curve.astype(np.float32),
                "breathiness": breathiness,
                "voicing": voicing,
                "tension": tension,
                "retake": retake3,
                "spk_embed": var_spk_embed,
                "steps": steps_arr,
            },
        )
        breathiness = breathiness.astype(np.float32)
        voicing = voicing.astype(np.float32)
        tension = tension.astype(np.float32)

    gender = np.full((1, n_frames), float(gender), dtype=np.float32)
    velocity = np.full((1, n_frames), float(vel), dtype=np.float32)

    # Add a tiny vibrato to reduce “robotic” output, but keep it subtle.
    # Only apply where pitch is voiced.
    vib_rate_hz = 5.5
    vib_depth = 0.015
    tt = (np.arange(n_frames, dtype=np.float32) * (HOP / float(sr))).reshape(1, -1)
    vib = (1.0 + vib_depth * np.sin(2.0 * math.pi * vib_rate_hz * tt)).astype(np.float32)
    pitch_curve = np.where(pitch_curve > 1.0, pitch_curve * vib, pitch_curve).astype(np.float32)

    # Acoustic model uses dsmain phoneme ids per dsconfig.yaml.
    acoustic_ph_map = _load_nishiren_phoneme_map(nishiren_root)
    acoustic_lang_map = _load_nishiren_language_map(nishiren_root)
    acoustic_tokens = np.array([[int(acoustic_ph_map[p]) for p in ph_seq]], dtype=np.int64)
    acoustic_languages = np.array([[int(acoustic_lang_map[language]) for _ in ph_seq]], dtype=np.int64)

    emb_path = nishiren_root / "dsmain" / f"{style}.emb"
    if not emb_path.exists():
        raise SystemExit(f"Nishiren style embedding not found: {emb_path}")
    spk = _load_nishiren_embedding(emb_path, HIDDEN)
    spk_embed = np.tile(spk.reshape(1, 1, HIDDEN), (1, n_frames, 1)).astype(np.float32)

    acoustic = ort.InferenceSession(str(nishiren_root / "dsmain" / "acoustic.onnx"), providers=["CPUExecutionProvider"])
    vocoder_candidates = sorted((nishiren_root / "dsvocoder").glob("*.onnx"))
    if not vocoder_candidates:
        raise SystemExit(f"No vocoder ONNX found under {nishiren_root / 'dsvocoder'}")
    vocoder = ort.InferenceSession(str(vocoder_candidates[0]), providers=["CPUExecutionProvider"])

    steps_arr = np.array(int(steps), dtype=np.int64)
    mel = acoustic.run(
        None,
        {
            "tokens": acoustic_tokens,
            "languages": acoustic_languages,
            "durations": durations,
            "f0": pitch_curve.astype(np.float32),
            "breathiness": breathiness,
            "voicing": voicing,
            "tension": tension,
            "gender": gender,
            "velocity": velocity,
            "spk_embed": spk_embed,
            "steps": steps_arr,
        },
    )[0].astype(np.float32)

    waveform = vocoder.run(None, {"mel": mel, "f0": pitch_curve.astype(np.float32)})[0].reshape(-1).astype(np.float32)

    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    if peak > 1.0:
        waveform = waveform / peak * 0.95

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_wav, waveform, sr)

    log = {
        "backend": "nishiren_onnx",
        "nishiren_root": str(nishiren_root),
        "language": language,
        "style": style,
        "vocoder": str(vocoder_candidates[0]),
        "output": str(out_wav),
        "sample_rate": sr,
        "phoneme_count": int(len(ph_seq)),
        "duration_seconds": float(waveform.size) / float(sr) if sr else None,
        "peak": peak,
        "warnings": [
            f"Optional {group} models absent; note-derived defaults used."
            for group in ("dspitch", "dsvariance") if not (nishiren_root / group).exists()
        ],
    }
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if debug_out is not None:
        debug_out.parent.mkdir(parents=True, exist_ok=True)
        debug_out.write_text(
            json.dumps(
                {
                    "text": " ".join([str(ev.get("lyric", "")).strip() for ev in events if str(ev.get("lyric", "")).strip()]),
                    "ph_seq": " ".join(ph_seq),
                    "note_seq": " ".join(str(events[index]["pitch"]) for index in ph_to_event),
                    "note_dur_seq": " ".join([str(int(x)) for x in ph_frames]),
                    "is_slur_seq": " ".join(["0"] * len(ph_seq)),
                    "input_type": "phoneme",
                    "metadata": {
                        "backend": "nishiren_onnx",
                        "duration_unit": "frames",
                        "hop": HOP,
                        "sr": sr,
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description="Render vocal events using a configured Nishiren ONNX voicebank")
    ap.add_argument("vocal_events_json", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--debug-out", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--nishiren-lang", default="en")
    ap.add_argument("--nishiren-style", default="Standard")
    ap.add_argument("--nishiren-vel", type=float, default=1.25)
    ap.add_argument("--nishiren-gender", type=float, default=0.0)
    ap.add_argument("--nishiren-steps", type=int, default=30)
    ap.add_argument("--sample-rate", type=int, default=44100)
    add_config_argument(ap)
    args = ap.parse_args()
    config = load_project(args.config_root)
    source = data_path(config, args.vocal_events_json, must_exist=True)
    output = data_path(config, args.out)
    debug = data_path(config, args.debug_out)
    log = data_path(config, args.log)
    if len({source, output, debug, log}) != 4:
        raise ValueError("Input, WAV, debug, and log paths must be distinct")
    nishiren_root = resource_path(config, "nishiren_root", directory=True)
    if Path(args.nishiren_style).name != args.nishiren_style or "\\" in args.nishiren_style:
        raise ValueError("Nishiren style must be a single embedding name")
    _preflight_models(nishiren_root, args.nishiren_style)
    lexicon = {}
    if config.get("resources", {}).get("pronunciation_lexicon"):
        lexicon = _load_json(resource_path(config, "pronunciation_lexicon"))
        if not isinstance(lexicon, dict):
            raise ValueError("pronunciation_lexicon must be a JSON object of word to phoneme list")
    payload = _load_json(source)
    tempo = float(payload["global"]["tempo_bpm"])
    events = payload["vocal_events"]
    if not math.isfinite(tempo) or tempo <= 0 or args.sample_rate <= 0 or args.nishiren_steps <= 0:
        raise ValueError("Tempo, sample rate, and inference steps must be positive")
    if not events:
        raise ValueError("vocal_events must not be empty")
    _validate_event_timing(events, payload["global"]["meter"])
    for event in events:
        duration = float(event["duration_beats"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Every event must have a finite positive duration")
        _pitch_to_hz(str(event["pitch"]))
        if str(event.get("lyric", "")).strip() and not event.get("phonemes"):
            _word_to_phones(str(event["lyric"]), lexicon)
    _run_nishiren_onnx(
        nishiren_root=nishiren_root, language=args.nishiren_lang, style=args.nishiren_style,
        events=events, tempo_bpm=tempo, sr=args.sample_rate, out_wav=output,
        log_path=log, debug_out=debug, vel=args.nishiren_vel, gender=args.nishiren_gender,
        steps=args.nishiren_steps, lexicon=lexicon,
    )


if __name__ == "__main__":
    main()
