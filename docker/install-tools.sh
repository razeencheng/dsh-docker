#!/bin/sh
set -eu
for value in "$INSTALL_PYTHON" "$INSTALL_GO" "$INSTALL_DOCKER"; do
    case "$value" in true|false) ;; *) echo 'INSTALL_PYTHON, INSTALL_GO and INSTALL_DOCKER must be true or false' >&2; exit 2 ;; esac
done
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    bash ca-certificates curl git openssh-client jq ripgrep unzip zip \
    build-essential pkg-config bubblewrap procps less file rsync
if [ "$INSTALL_PYTHON" = true ]; then
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv python-is-python3
fi
if [ "$INSTALL_GO" = true ]; then
    case "$TARGETARCH" in amd64|arm64) ;; *) echo "Unsupported Go architecture: $TARGETARCH" >&2; exit 2 ;; esac
    filename="go${GO_VERSION}.linux-${TARGETARCH}.tar.gz"
    curl --fail --silent --show-error --location --retry 3 'https://go.dev/dl/?mode=json&include=all' -o /tmp/go-releases.json
    checksum=$(jq -er --arg file "$filename" '[.[].files[] | select(.filename == $file) | .sha256] | first | select(type == "string" and test("^[a-f0-9]{64}$"))' /tmp/go-releases.json)
    curl --fail --location --retry 3 "https://go.dev/dl/${filename}" -o /tmp/go.tar.gz
    printf '%s  /tmp/go.tar.gz\n' "$checksum" | sha256sum --check --strict -
    tar -C /usr/local -xzf /tmp/go.tar.gz
    rm /tmp/go.tar.gz /tmp/go-releases.json
fi
if [ "$INSTALL_DOCKER" = true ]; then
    install -m 0755 -d /etc/apt/keyrings
    curl --fail --silent --show-error --location --retry 3 https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable\n' "$(dpkg --print-architecture)" > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin docker-compose-plugin
fi
rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*
