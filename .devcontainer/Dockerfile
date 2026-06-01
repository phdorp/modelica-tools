FROM mcr.microsoft.com/devcontainers/base:trixie

ENV DEBIAN_FRONTEND=noninteractive

COPY .devcontainer/install_dependencies.sh /tmp/install_dependencies.sh
RUN bash /tmp/install_dependencies.sh && rm /tmp/install_dependencies.sh