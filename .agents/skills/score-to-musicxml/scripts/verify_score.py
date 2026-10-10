"""Audit MusicXML and an optional reviewed reference; not a source-fidelity certificate."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, load_project
from validate import audit, canonical


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    add_config_argument(p)
    p.add_argument("score")
    p.add_argument("--expectations")
    p.add_argument("--reference")
    p.add_argument("--reviewed-sha256", help="Exact file hash recorded at independent review")
    p.add_argument("--output", help="Optional new JSON report under data_root")
    a = p.parse_args(argv)
    if bool(a.reference) != bool(a.reviewed_sha256):
        p.error("--reference and --reviewed-sha256 must be supplied together")
    config = load_project(a.config_root)
    score = data_path(config, a.score, must_exist=True)
    expectations = data_path(config, a.expectations, must_exist=True) if a.expectations else None
    reference = data_path(config, a.reference, must_exist=True) if a.reference else None
    out = data_path(config, a.output) if a.output else None
    if out and out.exists():
        raise ValueError("Choose a new report output path")
    read = lambda f: json.loads(f.read_text(encoding="utf-8-sig"))
    result = audit(score, Path(__file__).resolve().parents[1] / "schema/musicxml.xsd",
                   read(expectations) if expectations else None)
    result["sha256"] = hashlib.sha256(score.read_bytes()).hexdigest()
    if reference:
        result["reviewed_reference_matches"] = json.loads(json.dumps(canonical(score))) == read(reference)
        result["reviewed_file_matches"] = result["sha256"] == a.reviewed_sha256.lower()
        if not result["reviewed_reference_matches"]:
            result["issues"].append("Canonical events differ from reviewed reference")
        if not result["reviewed_file_matches"]:
            result["issues"].append("File hash differs from independently reviewed file")
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text, end="")
    return bool(result["issues"])


if __name__ == "__main__":
    raise SystemExit(main())
