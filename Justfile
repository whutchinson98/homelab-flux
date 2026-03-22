# homelab-flux — dev tasks

# Install the pre-push hook that blocks unencrypted secrets from being pushed
setup-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    HOOK=.git/hooks/pre-push
    ln -sf ../../scripts/check-secrets.sh "$HOOK"
    chmod +x "$HOOK"
    echo "pre-push hook installed at $HOOK"
