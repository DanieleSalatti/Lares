#!/bin/bash
# Setup passwordless sudo for Lares self-restart capability
#
# This script configures sudo to allow the current user to restart the Lares
# systemd service without entering a password. This enables Lares to restart
# itself when needed (e.g., after updates, configuration changes, or periodic
# maintenance).
#
# Usage:
#   sudo ./scripts/setup-sudoers.sh
#
# Security Note:
#   This grants passwordless sudo ONLY for the specific command:
#   'systemctl restart lares.service'
#   No other sudo commands are affected.

set -euo pipefail

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "Error: This script must be run with sudo"
   echo "Usage: sudo ./scripts/setup-sudoers.sh"
   exit 1
fi

# Get the actual user (not root, even when running with sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"

if [[ "$ACTUAL_USER" == "root" ]]; then
    echo "Error: Cannot determine the non-root user"
    echo "Please run with: sudo ./scripts/setup-sudoers.sh"
    exit 1
fi

SUDOERS_FILE="/etc/sudoers.d/lares"

echo "Setting up passwordless sudo for Lares self-restart..."
echo "User: $ACTUAL_USER"
echo "Service: lares.service"
echo ""

# Create sudoers entry
cat > "$SUDOERS_FILE" << EOF
# Allow $ACTUAL_USER to restart Lares service without password
# This enables Lares to restart itself for updates and maintenance
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart lares.service
EOF

# Set proper permissions (sudoers files must be 0440)
chmod 0440 "$SUDOERS_FILE"

# Validate the sudoers file
if visudo -c -f "$SUDOERS_FILE" > /dev/null 2>&1; then
    echo "✓ Sudoers configuration created successfully"
    echo "✓ File: $SUDOERS_FILE"
    echo ""
    echo "Testing the configuration..."

    # Test by checking if sudo -l shows the permission
    if su - "$ACTUAL_USER" -c "sudo -n -l /usr/bin/systemctl restart lares.service" 2>&1 | grep -q "restart lares.service"; then
        echo "✓ Passwordless sudo is working correctly!"
    else
        echo "⚠ Warning: Could not verify sudo permissions (but visudo passed)"
    fi

    echo ""
    echo "Lares can now restart itself using: sudo systemctl restart lares.service"
else
    echo "✗ Error: Invalid sudoers configuration"
    rm -f "$SUDOERS_FILE"
    exit 1
fi
