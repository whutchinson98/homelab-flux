#!/usr/bin/env python3
"""Prompt for a Cloudflare DNS token and write only a SOPS-encrypted Secret."""

import getpass
import json
from pathlib import Path
import shutil
import subprocess
import sys
import warnings


def main():
    root = Path(__file__).resolve().parent.parent
    relative = Path("infrastructure/cert-manager/issuers/cloudflare-api-token.sops.yaml")
    destination = root / relative
    if destination.exists():
        sys.exit(f"Secret already exists. Edit it with: sops {destination}")
    if shutil.which("sops") is None:
        sys.exit("Install sops before running this command.")

    # Refuse getpass's echoing fallback if there is no usable terminal.
    warnings.simplefilter("error", getpass.GetPassWarning)
    try:
        token = getpass.getpass("Cloudflare DNS API token (hidden): ").strip()
    except (getpass.GetPassWarning, EOFError):
        sys.exit("Run this command in an interactive terminal with hidden input support.")
    if not token or any(character.isspace() for character in token):
        sys.exit("Token must be nonempty and contain no whitespace.")

    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "cloudflare-api-token", "namespace": "cert-manager"},
        "type": "Opaque",
        "stringData": {"api-token": token},
    }
    result = subprocess.run(
        [
            "sops", "--encrypt", "--input-type", "json", "--output-type", "yaml",
            "--filename-override", str(relative), "/dev/stdin",
        ],
        input=json.dumps(secret),
        text=True,
        capture_output=True,
        cwd=root,
    )
    if result.returncode:
        sys.exit("SOPS encryption failed; no file was written. Check .sops.yaml and your SOPS installation.")
    # Exclusive creation also prevents overwriting a file created while prompting.
    with destination.open("x") as output:
        output.write(result.stdout)
    print(f"Created {relative}. Only encrypted token data was written to disk.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelled; no token file was written.")
