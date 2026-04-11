FROM mcr.microsoft.com/devcontainers/base:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && curl -fsSL https://build.openmodelica.org/apt/openmodelica.asc | gpg --dearmor -o /usr/share/keyrings/openmodelica-keyring.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/openmodelica-keyring.gpg] https://build.openmodelica.org/apt $(grep -E '(UBUNTU|DEBIAN|VERSION)_CODENAME' /etc/os-release | sort | cut -d= -f2 | head -1) stable" > /etc/apt/sources.list.d/openmodelica.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends omc omlibrary pipx \
 && rm -rf /var/lib/apt/lists/*