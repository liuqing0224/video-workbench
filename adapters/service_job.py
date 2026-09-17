"""Run HTTP adapters in a cancellable child process; server-side synthesis may finish separately."""

import argparse, json
from pathlib import Path
from adapters.tools import qwen_synthesize, transcribe
from apps.server.core import atomic, dumps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text())
    if request["kind"] == "tts":
        meta = qwen_synthesize(
            request["config"],
            request["text"],
            request["voice"],
            request["style"],
            Path(request["output"]),
        )
        atomic(Path(request["metadata"]), dumps(meta))
    else:
        transcribe(request["config"], Path(request["input"]), Path(request["output"]))


if __name__ == "__main__":
    main()
