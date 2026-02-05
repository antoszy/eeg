#!/usr/bin/env bash
# Connect to a Muse 2 headband via Bluetooth.
# Scans for a device whose name starts with "Muse", pairs, trusts, and connects.
#
# Usage: ./connect-muse.sh [timeout_seconds]

set -euo pipefail

SCAN_TIMEOUT="${1:-10}"
MUSE_ADDR=""

echo "Powering on Bluetooth adapter..."
bluetoothctl power on >/dev/null 2>&1 || true

echo "Scanning for Muse device (${SCAN_TIMEOUT}s)..."
# Start scan in background, capture output
SCAN_OUTPUT=$(timeout "$SCAN_TIMEOUT" bluetoothctl --timeout "$SCAN_TIMEOUT" scan on 2>&1 || true)

# Find Muse device address
MUSE_ADDR=$(bluetoothctl devices | grep -i "muse" | head -1 | awk '{print $2}')

if [[ -z "$MUSE_ADDR" ]]; then
    echo "ERROR: No Muse device found. Make sure the headband is powered on."
    exit 1
fi

MUSE_NAME=$(bluetoothctl devices | grep -i "muse" | head -1 | sed 's/^Device [^ ]* //')
echo "Found: $MUSE_NAME ($MUSE_ADDR)"

echo "Pairing..."
bluetoothctl pair "$MUSE_ADDR" 2>/dev/null || true

echo "Trusting..."
bluetoothctl trust "$MUSE_ADDR" 2>/dev/null || true

echo "Connecting..."
bluetoothctl connect "$MUSE_ADDR" 2>/dev/null || true

# Verify connection
if bluetoothctl info "$MUSE_ADDR" 2>/dev/null | grep -q "Connected: yes"; then
    echo "Muse connected successfully."
else
    echo "WARNING: Muse may not be fully connected (BrainFlow will handle BLE directly)."
fi
