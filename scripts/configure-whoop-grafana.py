#!/usr/bin/env python3
"""Create a view-only Grafana reader and publish its TLS datasource to Doppler.

Run from a machine with kubectl access to forge and a Doppler CLI login with
write access to whoop-scraper/prd. No port-forward or local psql is needed.
Reruns reuse the password in Doppler and refresh the CNPG public CA certificate.
Run again after restoring this database or replacing its CA. Never paste the
WHOOP_GRAFANA_DATASOURCE value into Git: it contains the reader password.
"""

import argparse
import base64
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time


KEY = "WHOOP_GRAFANA_DATASOURCE"
DOPPLER_CONFIG = ["--project", "whoop-scraper", "--config", "prd"]


def run(command, *, error, payload=None):
    result = subprocess.run(command, input=payload, text=True, capture_output=True)
    if result.returncode:
        # Commands may return credentials or SQL containing a password in their
        # output. Never forward subprocess output in an error or traceback.
        raise RuntimeError(error)
    return result.stdout


def reader_password(values):
    if KEY not in values:
        return secrets.token_urlsafe(32)
    try:
        previous = json.loads(values[KEY])["datasources"]
        source = next(ds for ds in previous if ds["uid"] == "whoop-postgres")
        password = source["secureJsonData"]["password"]
        # Our generated alphabet also avoids Grafana's $ environment expansion.
        if source["user"] != "whoop_grafana" or not re.fullmatch(r"[A-Za-z0-9_-]{32,}", password):
            raise ValueError
        return password
    except (ValueError, TypeError, KeyError, StopIteration):
        raise RuntimeError(f"Existing {KEY} is not in the expected format; refusing to replace it.") from None


def datasource_document(password, ca):
    return {
        "apiVersion": 1,
        "datasources": [{
            "name": "WHOOP PostgreSQL",
            "uid": "whoop-postgres",
            "type": "postgres",
            "access": "proxy",
            "url": "whoop-postgres-rw.whoop.svc.cluster.local:5432",
            "user": "whoop_grafana",
            "isDefault": False,
            "editable": False,
            "version": int(time.time()),
            "jsonData": {
                "database": "whoop",
                "sslmode": "verify-full",
                "tlsConfigurationMethod": "file-content",
                "maxOpenConns": 5,
                "maxIdleConns": 2,
                "maxIdleConnsAuto": False,
                "connMaxLifetime": 14400,
                "postgresVersion": 1800,
                "timescaledb": False,
            },
            "secureJsonData": {"password": password, "tlsCACert": ca},
        }],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", help="kubectl context; defaults to the current context")
    args = parser.parse_args()
    kubectl = ["kubectl"] + (["--context", args.context] if args.context else [])
    cluster = json.loads(run(
        kubectl + ["-n", "whoop", "get", "cluster.postgresql.cnpg.io", "whoop-postgres", "-o", "json"],
        error="Cannot read whoop-postgres. Check your kubectl context and cluster access.",
    ))
    primary = cluster.get("status", {}).get("currentPrimary", "")
    if not re.fullmatch(r"whoop-postgres-\d+", primary):
        raise RuntimeError("whoop-postgres has no recognized primary; wait for the database to be ready.")
    encoded_ca = run(
        kubectl + ["-n", "whoop", "get", "secret", "whoop-postgres-ca",
                   "-o", r"jsonpath={.data.ca\.crt}"],
        error="Cannot read the database CA certificate.",
    )
    ca = base64.b64decode(encoded_ca, validate=True).decode()
    if "-----BEGIN CERTIFICATE-----" not in ca or "PRIVATE KEY" in ca:
        raise RuntimeError("The database CA certificate is missing or invalid.")
    values = json.loads(run(
        ["doppler", "secrets", "download", "--no-file", "--no-fallback", "--format", "json"] + DOPPLER_CONFIG,
        error="Cannot read Doppler whoop-scraper/prd. Log in with a token that can read and write this config.",
    ))
    password = reader_password(values)
    grants = Path(__file__).with_name("whoop-grafana-reader.sql").read_text()
    # Password travels only through stdin, not command-line arguments or files.
    # This is a local Unix-socket admin connection inside the current CNPG primary.
    sql = (
        "SET log_statement = 'none';\nSET log_min_error_statement = 'panic';\n"
        "SET standard_conforming_strings = on;\nSET password_encryption = 'scram-sha-256';\nBEGIN;\n"
        + grants
        + "\nALTER ROLE whoop_grafana PASSWORD '" + password.replace("'", "''") + "';\nCOMMIT;\n"
    )
    run(
        kubectl + ["-n", "whoop", "exec", "-i", primary, "-c", "postgres", "--",
                   "psql", "-X", "-U", "postgres", "-d", "whoop", "--set", "ON_ERROR_STOP=1", "--quiet"],
        payload=sql,
        error="Database reader setup failed (transaction rolled back). Verify the WHOOP view migrations "
              "exist and that whoop_grafana has no extra grants or ownership. No secret output was displayed.",
    )
    document = json.dumps(datasource_document(password, ca))
    run(
        ["doppler", "secrets", "set", KEY, "--silent", "--no-interactive"] + DOPPLER_CONFIG,
        payload=document,
        error="Reader created, but Doppler update failed. Log in with write access to whoop-scraper/prd "
              "and rerun this helper before deploying the dashboard.",
    )
    print("Created/updated whoop_grafana with SELECT on the three dashboard views only.")
    print(f"Updated whoop-scraper/prd {KEY} with the reader password and public CA.")
    print("No credentials were displayed or written locally. Commit/push the Grafana manifests next.")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        sys.exit("Install kubectl and Doppler CLI; keep whoop-grafana-reader.sql beside this helper.")
    except (RuntimeError, ValueError, KeyError, TypeError) as error:
        # JSON/decode errors are deliberately generic to avoid echoing secrets.
        sys.exit(str(error) if isinstance(error, RuntimeError) else "Unexpected configuration response; no secrets displayed.")
    except KeyboardInterrupt:
        sys.exit("\nCancelled. Rerun the helper to complete setup.")
