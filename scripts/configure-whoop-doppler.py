#!/usr/bin/env python3
"""Encrypt a WHOOP Doppler service token and enable its Flux secret sync."""

import getpass
import json
from pathlib import Path
import shutil
import subprocess
import sys
import warnings


def main():
    root = Path(__file__).resolve().parent.parent
    relative = Path("apps/whoop-scraper/secrets/doppler-token.sops.yaml")
    destination = root / relative
    kustomization = destination.parent / "kustomization.yaml"
    flux = root / "clusters/forge/whoop-secrets.yaml"
    marker = "  # The setup helper adds the encrypted service token here.\n"
    kustomization_text = kustomization.read_text()
    flux_text = flux.read_text()
    if destination.exists():
        sys.exit(f"Token already exists. To rotate it, edit: sops {destination}")
    if marker not in kustomization_text or "  suspend: true\n" not in flux_text:
        sys.exit("Setup manifests have changed; review them before adding the token.")
    if shutil.which("sops") is None:
        sys.exit("Install sops before running this command.")

    warnings.simplefilter("error", getpass.GetPassWarning)
    try:
        token = getpass.getpass("Doppler service token for whoop-scraper / prd (hidden): ").strip()
    except (getpass.GetPassWarning, EOFError):
        sys.exit("Run this command in an interactive terminal with hidden input support.")
    if not token.startswith("dp.st.") or any(char.isspace() for char in token):
        sys.exit("Enter a Doppler service token (dp.st. prefix) without whitespace.")

    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "whoop-doppler-token", "namespace": "whoop"},
        "type": "Opaque",
        "stringData": {"serviceToken": token},
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
        sys.exit("SOPS encryption failed; no files changed. Check .sops.yaml and SOPS.")
    # Write the encrypted token first; only then include it and resume Flux.
    with destination.open("x") as output:
        output.write(result.stdout)
    kustomization.write_text(kustomization_text.replace(marker, "  - doppler-token.sops.yaml\n", 1))
    flux.write_text(flux_text.replace("  suspend: true\n", "  suspend: false\n", 1))
    print(f"Created {relative} and enabled whoop-secrets. Only encrypted token data was written.")
    print("Review, commit, and push the changes for Flux to start syncing Doppler.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
