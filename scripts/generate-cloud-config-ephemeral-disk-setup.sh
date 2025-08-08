#!/bin/bash

# Generate cloud-config.yaml for azure-ephemeral-disk-setup without requiring curl, etc.

set -e

SCRIPT="ephemeral-disk-setup/azure-ephemeral-disk-setup"
SERVICE="ephemeral-disk-setup/azure-ephemeral-disk-setup.service"
CONF="ephemeral-disk-setup/azure-ephemeral-disk-setup.conf"
OUTPUT="cloud-config-ephemeral-disk-setup.yaml"
INSTALL_BIN_DIR="/usr/local/bin"
SYSTEMD_SYSTEM_SERVICE_DIR="/etc/systemd/system"

# Validate all input files
for file in "$SCRIPT" "$SERVICE" "$CONF"; do
  if [ ! -f "$file" ]; then
    echo "❌ Missing required file: $file"
    exit 1
  fi
done

# Indent helper
indent_file() {
  awk '{ print "      " $0 }' "$1"
}

SCRIPT_CONTENT=$(indent_file "$SCRIPT")

# Get service with updated install binary directory.
SERVICE_CONTENT=$(indent_file "$SERVICE" | sed "s|@AZURE_NVME_ID_INSTALL_DIR@|$INSTALL_BIN_DIR|g")

# Get config.
CONF_CONTENT=$(indent_file "$CONF")

# Generate cloud-config
cat <<EOF > "$OUTPUT"
#cloud-config
write_files:
  - path: $INSTALL_BIN_DIR/azure-ephemeral-disk-setup
    permissions: '0755'
    content: |
$SCRIPT_CONTENT

  - path: $SYSTEMD_SYSTEM_SERVICE_DIR/azure-ephemeral-disk-setup.service
    permissions: '0644'
    content: |
$SERVICE_CONTENT

  - path: /etc/azure-ephemeral-disk-setup.conf
    permissions: '0644'
    content: |
$CONF_CONTENT

runcmd:
  - systemctl daemon-reload
  - systemctl enable azure-ephemeral-disk-setup.service
  - systemctl start azure-ephemeral-disk-setup.service
EOF

echo "✅ cloud-config written to $OUTPUT"

