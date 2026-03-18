#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if [ $# -lt 1 ]; then
    echo "Usage: install-hooks.sh <target-directory>" >&2
    exit 1
fi

TARGET_DIR="$1"

echo "Installing cline-hooks as uv tool..."
uv tool install --editable "$SCRIPT_DIR" --force

echo "Linking hooks to $TARGET_DIR..."
cline-hook install "$TARGET_DIR"
