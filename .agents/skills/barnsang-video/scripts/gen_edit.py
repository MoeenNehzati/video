"""Edit an image using explicit predecessor and character references."""
from __future__ import annotations

from contextlib import ExitStack
import mimetypes
import time

import requests

from gen_image import data_path, parser, prepare, save_response


def main(argv=None):
    p = parser(__doc__)
    p.add_argument("--reference", action="append", required=True,
                   help="Repeat for the preceding keyframe and character sheets")
    p.add_argument("--input-fidelity", choices=["high", "low"],
                   help="Set only for models that support this option")
    args = p.parse_args(argv)
    config, out, metadata, prompt, key = prepare(args)
    refs = [data_path(config, ref, must_exist=True) for ref in args.reference]
    data = {"model": args.model, "quality": args.quality, "size": args.size,
            "prompt": prompt, "n": "1", "output_format": "png"}
    if args.input_fidelity:
        data["input_fidelity"] = args.input_fidelity
    started = time.monotonic()
    with ExitStack() as stack:
        files = [("image[]", (ref.name, stack.enter_context(ref.open("rb")),
                              mimetypes.guess_type(ref.name)[0] or "application/octet-stream"))
                 for ref in refs]
        response = requests.post("https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {key}"}, data=data, files=files, timeout=900)
    record = {"model": args.model, "quality": args.quality, "size": args.size,
              "prompt": prompt, "refs": [str(ref) for ref in refs],
              "input_fidelity": args.input_fidelity}
    save_response(response, out, metadata, record, started)


if __name__ == "__main__":
    main()
