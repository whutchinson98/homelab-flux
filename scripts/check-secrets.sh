#!/usr/bin/env bash
# Pre-push hook: ensures no unencrypted Kubernetes secrets are pushed.
#
# Two rules:
#   1. Every *.sops.yaml file must have a top-level 'sops:' metadata block
#      and ENC[AES256_GCM,...] values — meaning it was actually encrypted.
#   2. No plain *.yaml file may contain a top-level 'kind: Secret' definition.
#
# Install via: just setup-hooks

RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

ERRORS=0

SOPS_FILES=$(git ls-files '*.sops.yaml' 2>/dev/null | grep -v '^\.sops\.yaml$' || true)
PLAIN_YAML_FILES=$(git ls-files '*.yaml' '*.yml' 2>/dev/null | grep -v '\.sops\.yaml$' || true)

# Rule 1 — *.sops.yaml files must be encrypted
while IFS= read -r file; do
    [ -z "$file" ] && continue
    [ -f "$file" ] || continue

    if ! grep -q '^sops:' "$file"; then
        echo -e "${RED}UNENCRYPTED${NC}: ${BOLD}$file${NC}"
        echo "  Missing 'sops:' block — file was never encrypted."
        echo "  Run: sops --encrypt --in-place $file"
        ERRORS=$((ERRORS + 1))
    elif ! grep -qE 'ENC\[AES256_GCM' "$file"; then
        echo -e "${RED}UNENCRYPTED${NC}: ${BOLD}$file${NC}"
        echo "  Has 'sops:' block but data fields are still plaintext."
        echo "  Run: sops --encrypt --in-place $file"
        ERRORS=$((ERRORS + 1))
    fi
done <<< "$SOPS_FILES"

# Rule 2 — plain YAML files must not define top-level Secret resources
# Uses ^kind: Secret (unindented) to avoid false positives like
# `- kind: Secret` inside HelmRelease valuesFrom blocks.
while IFS= read -r file; do
    [ -z "$file" ] && continue
    [ -f "$file" ] || continue

    if grep -qP '^kind: Secret' "$file"; then
        echo -e "${RED}PLAINTEXT SECRET${NC}: ${BOLD}$file${NC}"
        echo "  Contains a top-level 'kind: Secret' but is not a *.sops.yaml file."
        echo "  Encrypt: sops --encrypt $file > \$(basename $file .yaml).sops.yaml"
        ERRORS=$((ERRORS + 1))
    fi
done <<< "$PLAIN_YAML_FILES"

if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo -e "${RED}${BOLD}Push blocked:${NC} $ERRORS unencrypted secret file(s) found."
    exit 1
fi

exit 0
