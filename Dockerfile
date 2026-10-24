# syntax=docker/dockerfile:1
ARG NODE_IMAGE=node:24-bookworm-slim
FROM ${NODE_IMAGE} AS builder

ARG DSH_REF=1f81c047fc48fa190a683e469daa699857e9afe8
ENV CI=true ELECTRON_SKIP_BINARY_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /src
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git python3 build-essential musl-tools \
    && rm -rf /var/lib/apt/lists/*
RUN case "$DSH_REF" in *[!0-9a-f]*|'') echo 'DSH_REF must be a full lowercase Git commit SHA' >&2; exit 1;; esac \
    && test "${#DSH_REF}" = 40 \
    && curl --fail --location --retry 3 "https://codeload.github.com/deepseek-ai/deepseek-harness/tar.gz/${DSH_REF}" -o /tmp/dsh.tar.gz \
    && tar -xzf /tmp/dsh.tar.gz --strip-components=1 -C /src \
    && rm /tmp/dsh.tar.gz
RUN npm install --global "$(node -p 'require("./package.json").packageManager')"
RUN --mount=type=cache,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir=/pnpm/store
RUN DSH_CLIENT_COMMIT_HASH="$DSH_REF" pnpm run build:artifacts \
    && pnpm exec tsx native/system/scripts/build.ts
RUN --mount=type=cache,target=/pnpm/store \
    pnpm --filter dsh-python-runtime-closure deploy --legacy --prod \
      --config.store-dir=/pnpm/store \
      --config.allow-unused-patches=true \
      --config.node-linker=hoisted \
      --config.auto-install-peers=false \
      --config.link-workspace-packages=true \
      --config.hoist-workspace-packages=false /opt/dsh \
    && pnpm install --offline --frozen-lockfile --prod=false --ignore-scripts --store-dir=/pnpm/store
COPY docker/package-runtime.mjs /tmp/package-runtime.mjs
RUN node /tmp/package-runtime.mjs \
    && node /opt/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js --help >/dev/null

FROM ${NODE_IMAGE} AS tools
ARG TARGETARCH
ARG DSH_REF=1f81c047fc48fa190a683e469daa699857e9afe8
ARG DSH_TAG=dsh-v0.2.1-rc.3
ARG PACKAGING_REVISION=1
ARG INSTALL_PYTHON=true
ARG INSTALL_GO=true
ARG INSTALL_DOCKER=true
ARG GO_VERSION=1.27.3
ARG PNPM_VERSION=11.28.5
LABEL org.opencontainers.image.title="DeepSeek Harness Docker" \
      org.opencontainers.image.source="https://github.com/razeencheng/dsh-docker" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${DSH_TAG}-r${PACKAGING_REVISION}" \
      org.opencontainers.image.revision="${DSH_REF}" \
      io.deepseek-harness.upstream.repository="https://github.com/deepseek-ai/deepseek-harness" \
      io.deepseek-harness.upstream.tag="${DSH_TAG}" \
      io.deepseek-harness.packaging.revision="${PACKAGING_REVISION}"
COPY docker/install-tools.sh /tmp/install-tools.sh
RUN /bin/sh /tmp/install-tools.sh \
    && npm install --global "pnpm@${PNPM_VERSION}" \
    && npm cache clean --force \
    && rm /tmp/install-tools.sh
ENV NODE_ENV=production \
    HOME=/data/home \
    DSH_HOME=/data/.dsh \
    DSH_PERMISSION_MODE=workspace-write \
    DSH_TELEMETRY_DISABLED=1 \
    PORT=3080 \
    GOPATH=/data/home/go \
    NPM_CONFIG_PREFIX=/data/home/.local \
    PATH=/data/home/.local/bin:/data/home/go/bin:/usr/local/go/bin:${PATH}
RUN mkdir -p /data /workspace /plugins /config \
    && chown node:node /data /workspace /plugins /config
FROM tools AS runtime
COPY --from=builder /opt/dsh /opt/dsh
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/dsh-entrypoint
COPY --chmod=755 docker/dsh.sh /usr/local/bin/dsh
COPY --chmod=755 docker/healthcheck.mjs /usr/local/bin/dsh-healthcheck
COPY docker/listen-address.mjs /opt/dsh/listen-address.mjs
WORKDIR /workspace
USER node
EXPOSE 3080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD ["/usr/local/bin/dsh-healthcheck"]
ENTRYPOINT ["/usr/local/bin/dsh-entrypoint"]
CMD ["web"]
