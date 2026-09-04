FROM mcr.microsoft.com/devcontainers/base:trixie

ENV DEBIAN_FRONTEND=noninteractive

# Parity with Linux container: same dependencies (omc, omlibrary, pipx, Python 3.11 via base)
COPY .devcontainer/install_dependencies.sh /tmp/install_dependencies.sh
RUN bash /tmp/install_dependencies.sh && rm /tmp/install_dependencies.sh

# Windows ergonomics: install PowerShell (pwsh) for `devcontainer exec ... pwsh/powershell`.
# Debian trixie has libicu76, but the PowerShell .deb only lists up to libicu74, so use the
# binary tarball which works on trixie (GitHub release). Keeps parity - install_dependencies.ps1
# remains for native Windows containers (Dockerfile.windows-native).
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates \
    && POWERSHELL_VERSION="7.5.2" \
    && wget -q "https://github.com/PowerShell/PowerShell/releases/download/v${POWERSHELL_VERSION}/powershell-${POWERSHELL_VERSION}-linux-x64.tar.gz" -O /tmp/powershell.tar.gz \
    && mkdir -p /opt/microsoft/powershell/7 \
    && tar -xzf /tmp/powershell.tar.gz -C /opt/microsoft/powershell/7 \
    && chmod +x /opt/microsoft/powershell/7/pwsh \
    && ln -sf /opt/microsoft/powershell/7/pwsh /usr/bin/pwsh \
    && ln -sf /usr/bin/pwsh /usr/bin/powershell \
    && rm -f /tmp/powershell.tar.gz \
    && rm -rf /var/lib/apt/lists/* \
    && pwsh --version && powershell --version
