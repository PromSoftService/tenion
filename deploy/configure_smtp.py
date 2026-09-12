#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import os
from pathlib import Path
import tempfile


KEY = "TENION_SMTP_PASSWORD_B64"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Store the Tenion SMTP application password without echoing it"
    )
    parser.add_argument(
        "env_file",
        nargs="?",
        type=Path,
        default=Path("/srv/pss/infra/tenion/.env"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_file = args.env_file.resolve()
    if not env_file.is_file():
        raise SystemExit(f"Environment file does not exist: {env_file}")

    password = getpass.getpass("Yandex Mail application password: ")
    confirmation = getpass.getpass("Repeat application password: ")
    if not password:
        raise SystemExit("Password must not be empty")
    if password != confirmation:
        raise SystemExit("Passwords do not match")

    encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
    lines = env_file.read_text(encoding="utf-8").splitlines()
    replacement = f"{KEY}={encoded}"
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(f"{KEY}="):
            output.append(replacement)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(replacement)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{env_file.name}.", dir=env_file.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, env_file)
    finally:
        temporary.unlink(missing_ok=True)

    print(f"SMTP application password stored in {env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

