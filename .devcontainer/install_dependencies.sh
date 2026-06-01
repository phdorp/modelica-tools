#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends ca-certificates curl gnupg pipx
curl -fsSL https://build.openmodelica.org/apt/openmodelica.asc | gpg --dearmor | $SUDO tee /usr/share/keyrings/openmodelica-keyring.gpg >/dev/null
CODENAME="$(grep -E '(UBUNTU|DEBIAN|VERSION)_CODENAME' /etc/os-release | sort | cut -d= -f2 | head -1)"
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/openmodelica-keyring.gpg] https://build.openmodelica.org/apt ${CODENAME} stable" | $SUDO tee /etc/apt/sources.list.d/openmodelica.list >/dev/null
$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends omc omlibrary
$SUDO rm -rf /var/lib/apt/lists/*
