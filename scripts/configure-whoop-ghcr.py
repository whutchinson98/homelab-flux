#!/usr/bin/env python3
"""Store private GHCR pull credentials in whoop-scraper/prd in Doppler."""

import argparse
import base64
import getpass
import json
import subprocess
import sys
import warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="whutchinson98")
    args = parser.parse_args()
    if not args.username or ":" in args.username or any(c.isspace() for c in args.username):
        parser.error("Enter a valid GitHub username")
    warnings.simplefilter("error", getpass.GetPassWarning)
    try:
        token = getpass.getpass("GitHub PAT (classic), read:packages (hidden): ").strip()
    except (getpass.GetPassWarning, EOFError):
        sys.exit("Run in an interactive terminal with hidden input support.")
    if not token or any(c.isspace() for c in token):
        sys.exit("Token must be nonempty and contain no whitespace.")
    auth = base64.b64encode(f"{args.username}:{token}".encode()).decode()
    docker_config = json.dumps({"auths": {"ghcr.io": {"auth": auth}}})
    result = subprocess.run(
        ["doppler", "secrets", "set", "GHCR_DOCKERCONFIG", "--project", "whoop-scraper",
         "--config", "prd", "--silent", "--no-interactive"],
        input=docker_config, capture_output=True, text=True,
    )
    if result.returncode:
        sys.exit("Doppler update failed. Log in with write access to whoop-scraper/prd; "
                 "the operator's read-only service token cannot write secrets.")
    print("Updated whoop-scraper/prd GHCR_DOCKERCONFIG. No credentials were displayed or saved locally.")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        sys.exit("Install the Doppler CLI and log in before running this command.")
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
