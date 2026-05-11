"""Developer CLI for local smoke checks."""

from __future__ import annotations

import argparse
import json

from sisyphus_hermes import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sisyphus-hermes")
    parser.add_argument("command", nargs="?", default="doctor", choices=["doctor"])
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    args = parser.parse_args(argv)

    result = {"ok": True, "package": "sisyphus-hermes", "version": __version__}
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"sisyphus-hermes {__version__}: doctor ok")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
