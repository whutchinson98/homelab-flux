#!/usr/bin/env python3
"""Publish the cluster database URL to Doppler or run a local database command."""

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def read_secret(name, key):
    result = subprocess.run(
        ["kubectl", "-n", "whoop", "get", "secret", name, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode:
        sys.exit(f"Cannot read whoop/{name}. Check your kubectl context and permissions.")
    try:
        return base64.b64decode(json.loads(result.stdout)["data"][key], validate=True).decode()
    except (ValueError, KeyError, UnicodeError):
        sys.exit(f"Secret whoop/{name} does not contain a valid {key} value.")


def local_url(cluster_url, port, ca_path):
    parsed = urlsplit(cluster_url)
    if parsed.scheme not in ("postgres", "postgresql") or "@" not in parsed.netloc:
        raise ValueError("Invalid PostgreSQL URL")
    credentials = parsed.netloc.rsplit("@", 1)[0]
    query = dict(parse_qsl(parsed.query))
    # CNPG's serverAltDNSNames includes localhost for this loopback tunnel.
    # Validate both the server hostname and the CA fetched via Kubernetes.
    query.update(sslmode="verify-full", sslrootcert=str(ca_path))
    for key in ("host", "hostaddr", "port", "ssl-mode", "ssl-root-cert", "ssl-ca"):
        query.pop(key, None)
    return urlunsplit((parsed.scheme, f"{credentials}@localhost:{port}",
                       parsed.path, urlencode(query), ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("publish-url", help="Set whoop-scraper/prd DATABASE_URL in Doppler")
    local = commands.add_parser("local", help="Run a command through an existing local port-forward")
    local.add_argument("--port", type=int, default=55434)
    local.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "local":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("local requires a command after --")
        if not 1 <= args.port <= 65535:
            parser.error("port must be between 1 and 65535")
    cluster_url = read_secret("whoop-postgres-credentials", "DATABASE_URL")
    if args.action == "publish-url":
        # stdin avoids putting credentials in argv or shell history. --silent
        # prevents Doppler from echoing the newly written secret.
        result = subprocess.run(
            ["doppler", "secrets", "set", "DATABASE_URL", "--project", "whoop-scraper",
             "--config", "prd", "--silent", "--no-interactive"],
            input=cluster_url, capture_output=True, text=True,
        )
        if result.returncode:
            sys.exit("Doppler update failed. Log in with write access to whoop-scraper/prd; "
                     "the operator's read-only service token cannot write secrets.")
        print("Updated whoop-scraper/prd DATABASE_URL without displaying its value.")
        return 0

    ca = read_secret("whoop-postgres-ca", "ca.crt")
    # Only the public CA certificate goes to disk; the password stays in memory
    # and the child process environment. Keep the caller's working directory.
    with tempfile.TemporaryDirectory(prefix="whoop-db-ca-") as temp:
        ca_path = Path(temp) / "ca.crt"
        ca_path.write_text(ca)
        try:
            url = local_url(cluster_url, args.port, ca_path)
        except ValueError:
            sys.exit("The database Secret does not contain a valid PostgreSQL URL.")
        env = dict(os.environ, DATABASE_URL=url)
        print(f"Using whoop database through localhost:{args.port} with full TLS verification.", flush=True)
        return subprocess.run(command, env=env).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FileNotFoundError as error:
        sys.exit(f"Required executable not found: {error.filename}")
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
