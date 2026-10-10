"""Source and event invariants extracted from the collaborator's renderer."""
from collections import Counter
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from scripts.project_runtime import data_path, resource_path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_auditor(config):
    """Do not substitute an unverified parser for the missing upstream helper."""
    path = resource_path(config, "midi_audit")
    spec = importlib.util.spec_from_file_location("arrangement_midi_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(callable(getattr(module, "read_midi", None)) and callable(getattr(module, "triples", None)),
            "midi_audit must export read_midi(path) and triples(track, ppq)")
    return module


def counts(parsed, drums):
    return Counter((p, t, d, ch, v) for tr in parsed["tracks"] for p, t, d, ch, v in tr["notes"] if (ch == 9) == drums)


def check_child_events(actual, reference, operation):
    require(actual["ppq"] == reference["ppq"], "Baseline PPQ changed")
    require(counts(actual, False) == counts(reference, False), "Pitched baseline changed")
    expected = counts(reference, True) if operation["baseline_percussion"] == "preserve" else Counter()
    ppq = actual["ppq"]
    for pitch, beat, duration, velocity in operation["events"]:
        expected[(pitch, round(beat * ppq), round((beat + duration) * ppq) - round(beat * ppq), 9, velocity)] += 1
    require(counts(actual, True) == expected, "Unexpected percussion changes")


def check_backing(actual, backing, guide_channel):
    expected = Counter((p, t, d, ch, v) for tr in actual["tracks"] for p, t, d, ch, v in tr["notes"] if ch != guide_channel)
    found = Counter(tuple(note) for tr in backing["tracks"] for note in tr["notes"])
    require(expected == found, "Backing must omit precisely the guide melody")
    require(not [e for tr in backing["tracks"] for e in tr["errors"] if e[0] != "overlapping_same_pitch"], "Backing note pairing errors")


def verify(folder, config, auditor):
    cfg = json.loads((folder / "parameters.json").read_text(encoding="utf-8"))
    component(cfg["stem"])
    component(cfg["id"])
    component(cfg["filename"])
    mid = artifact_file(config, folder, cfg["filename"] + ".mid", must_exist=True)
    for key, hashkey in (("source_xml", "source_sha256"), ("source_midi", "source_midi_sha256")):
        require(sha(data_path(config, cfg[key], must_exist=True)) == cfg[hashkey], f"Changed {key}")
    base = auditor.read_midi(data_path(config, cfg["source_midi"], must_exist=True))
    melody = next(t for t in base["tracks"] if t["notes"])
    actual = auditor.read_midi(mid)
    lead = next(t for t in actual["tracks"] if any(k == 3 and b"Original melody" in bytes.fromhex(v) for tick, k, v in t["meta"]))
    require(auditor.triples(lead, actual["ppq"]) == auditor.triples(melody, base["ppq"]), "Melody change")
    exact = lambda track, ppq: sorted((p, Fraction(t, ppq), Fraction(d, ppq), v) for p, t, d, c, v in track["notes"])
    require(exact(lead, actual["ppq"]) == exact(melody, base["ppq"]), "Melody timing/velocity change")
    errors = [e for tr in actual["tracks"] for e in tr["errors"]]
    serious = [e for e in errors if e[0] != "overlapping_same_pitch"]
    require(not serious, f"MIDI note pairing errors: {serious}")
    num, den = map(int, cfg["meter"].split("/"))
    expected = [(round(c["bar"] * num * 4 / den + c["beat"], 6), c["name"]) for c in cfg["chords"]]
    markers = [(round(t / actual["ppq"], 6), bytes.fromhex(v).decode()) for tr in actual["tracks"] for t, k, v in tr["meta"] if k == 6 and bytes.fromhex(v).decode() in {c["name"] for c in cfg["chords"]}]
    require(not Counter(expected) - Counter(markers), "Missing source chord")
    extras = list((Counter(markers) - Counter(expected)).elements())
    for tick, name in extras:
        require(cfg.get("variation") == "evolving" and name == [c for pos, c in expected if pos <= tick][-1], "Changed harmony")
    tempos = [int(v, 16) for tr in actual["tracks"] for tick, k, v in tr["meta"] if k == 81]
    require(tempos and all(abs(60000000 / tempo - cfg["tempo"]) < .01 for tempo in tempos), "Tempo mismatch")
    meters = [bytes.fromhex(v)[:2] for tr in actual["tracks"] for tick, k, v in tr["meta"] if k == 88]
    require(meters and all(x == bytes([num, int(math.log2(den))]) for x in meters), "Meter mismatch")
    require((folder / "native_reload_verified.txt").is_file(), "Native project not reopened")
    return cfg, {"source_files_unchanged": True, "melody_pitch_onset_duration_velocity_exact": True,
                 "chord_change_times_and_names_preserved": True, "redundant_section_chord_markers": extras,
                 "meter_and_requested_tempo_verified": True, "note_pairing_errors": serious,
                 "overlapping_same_pitch_events": len(errors), "native_project_reopened": True, "midi_sha256": sha(mid)}


def component(value):
    """Require one portable filename component, never an embedded path."""
    require(isinstance(value, str) and value not in ("", ".", "..")
            and not any(character in '<>:"/\\|?*' or ord(character) < 32 for character in value)
            and not value.endswith((".", " ")), "Unsafe filename/directory component")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    require(value.split(".")[0].upper() not in reserved, "Reserved filename/directory component")
    return value


def artifact_file(config, directory, filename, must_exist=False):
    directory = Path(directory).resolve()
    path = data_path(config, directory / component(filename), must_exist=must_exist)
    require(path.parent == directory, "Artifact file escapes its declared directory")
    return path


def check_frozen_messages(actual_path, baseline_path):
    """Check expression/programs/pitch bends and timing metadata, not only notes."""
    import mido
    def frozen_events(path):
        events = Counter()
        for track in mido.MidiFile(path).tracks:
            tick = 0
            for message in track:
                tick += message.time
                if getattr(message, "channel", None) == 9 or message.type in ("end_of_track", "track_name"):
                    continue
                events[(tick, str(message.copy(time=0)))] += 1
        return events
    require(frozen_events(actual_path) == frozen_events(baseline_path),
            "Pitched MIDI/controller/program/tempo events differ from frozen baseline")
