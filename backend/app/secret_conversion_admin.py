"""Internal PH-4C legacy credential conversion command."""

import argparse
import json

from app.db.database import engine
from app.services.secret_legacy_conversion import (
    LegacyConversionError,
    convert_legacy_secrets,
    load_conversion_manifest,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Convert exact-0010 legacy credentials")
    parser.add_argument("--manifest", required=True, help="Absolute path to version-1 manifest")
    parser.add_argument("--apply", action="store_true", help="Apply conversions; default is dry-run")
    args = parser.parse_args(argv)
    try:
        result = convert_legacy_secrets(
            engine, load_conversion_manifest(args.manifest), apply=args.apply
        )
    except LegacyConversionError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
