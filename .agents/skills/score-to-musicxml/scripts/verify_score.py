"""Audit MusicXML and an optional reviewed reference; not a source-fidelity certificate."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, fresh_output, load_project



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
    inputs = ["score", *(["expectations"] if a.expectations else []), *(["reference"] if a.reference else [])]
    for name in inputs:
        setattr(a, name, data_path(config, getattr(a, name), must_exist=True))
    if a.output:
        a.output = data_path(config, a.output)
        produce(a)
        text = a.output.read_text(encoding="utf-8")
    else:
        text = report(a)
    print(text, end="")
    return bool(json.loads(text)["issues"])


def report(args):
    from validate import audit, canonical
    score = Path(args.score)
    expectations = Path(args.expectations) if args.expectations else None
    reference = Path(args.reference) if args.reference else None
    read = lambda f: json.loads(f.read_text(encoding="utf-8-sig"))
    result = audit(score, Path(__file__).resolve().parents[1] / "schema/musicxml.xsd",
                   read(expectations) if expectations else None)
    result["sha256"] = hashlib.sha256(score.read_bytes()).hexdigest()
    if reference:
        result["reviewed_reference_matches"] = json.loads(json.dumps(canonical(score))) == read(reference)
        result["reviewed_file_matches"] = result["sha256"] == args.reviewed_sha256.lower()
        if not result["reviewed_reference_matches"]:
            result["issues"].append("Canonical events differ from reviewed reference")
        if not result["reviewed_file_matches"]:
            result["issues"].append("File hash differs from independently reviewed file")
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    return text


def produce(args):
    output = fresh_output(args.output, inputs=[p for p in (args.score,args.expectations,args.reference) if p])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report(args), encoding="utf-8")



if __name__ == "__main__":
    raise SystemExit(main())
