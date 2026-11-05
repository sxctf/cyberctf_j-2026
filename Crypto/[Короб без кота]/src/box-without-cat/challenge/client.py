"""Для проверки корректности схемы ее нужно отправить на удаленный сервер"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/solve",
        data=args.circuit.read_bytes(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            print(json.dumps(json.load(response), indent=2))
    except urllib.error.HTTPError as error:
        print(error.read().decode())
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
