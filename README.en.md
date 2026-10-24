# DeepSeek Harness Docker

[中文](README.md) · [Deployment](docs/deployment.md) · [Releases](docs/releases.md)

Community-maintained, **unofficial** Docker packaging for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness). Images target `linux/amd64` and `linux/arm64` at [`razeencheng/dsh`](https://hub.docker.com/r/razeencheng/dsh).

The image includes Node.js/npm/pnpm, Git, OpenSSH client, common shell utilities, build tools and Bubblewrap. Python 3 with pip/venv, Go, and Docker CLI with Buildx/Compose are enabled by default. It runs as UID/GID `1000:1000`, with `HOME=/data/home` and `DSH_HOME=/data/.dsh`.

## Quick start

Install Docker Engine and the Compose plugin on a Linux server:

```sh
git clone https://github.com/razeencheng/dsh-docker.git
cd dsh-docker
cp .env.example .env
mkdir -p data workspace plugins config
sudo chown -R 1000:1000 data workspace plugins
chmod 700 data
chmod 600 .env
```

Set `DEEPSEEK_API_KEY` in `.env`. For the SSH tunnel below, keep the defaults `DSH_TRUSTED_HOST=127.0.0.1:3080` and `DSH_BIND_ADDRESS=127.0.0.1`.

```sh
docker compose pull
docker compose up -d
docker compose ps
```

On your own computer, replace `user@server` with your SSH login:

```sh
ssh -N -L 3080:127.0.0.1:3080 user@server
```

Open <http://127.0.0.1:3080>. The default deployment is reachable only through the server's loopback interface. Use an authenticated TLS reverse proxy for domain access. The trusted-host setting is an address check, not authentication.

Images become available after a successful release workflow. Before the first release, build locally and set `DSH_IMAGE=razeencheng/dsh:local`; start Compose without pulling.

## Build options

```sh
make build
make smoke

make build TAG=lite INSTALL_PYTHON=false INSTALL_GO=false INSTALL_DOCKER=false
make smoke TAG=lite INSTALL_PYTHON=false INSTALL_GO=false INSTALL_DOCKER=false

make build-all
```

`INSTALL_PYTHON`, `INSTALL_GO` and `INSTALL_DOCKER` are **build-time** booleans (`true`/`false`), all defaulting to `true`. Runtime environment variables do not remove installed tools. Published default images include all three.

`make build-all` loads separate `local-amd64` and `local-arm64` images. Cross-architecture local builds require emulation or suitable native builders. Custom upstream builds require `DSH_REF=<full-40-character-commit-SHA>`; `DSH_TAG=dsh-v<version>` records the upstream version label.

Docker support consists only of client tools. No daemon or host socket is enabled by default. The opt-in `docker-compose.docker.yml` grants access to the host daemon and can grant host-level privileges. See [deployment details](docs/deployment.md) before enabling it.

## Persistent data

| Host directory | Container directory | Purpose |
| --- | --- | --- |
| `data/.dsh` | `/data/.dsh` | Harness state, profiles, sessions and credentials |
| `data/home` | `/data/home` | Home directory, caches and user tools |
| `workspace` | `/workspace` | Project files |
| `plugins` | `/plugins` | Local plugin source |
| `config` | `/config` | Read-only configuration |

Back up `data` and project files before upgrading. Container recreation preserves these mounts but does not roll back application data changes. Python projects should use a virtual environment, such as `python3 -m venv /workspace/my-project/.venv`.

## Releases

GitHub Actions polls upstream `dsh-v*` Git tags every 30 minutes, including prereleases. The first run builds only the newest tag; later runs queue every newly observed tag, including maintenance releases. Both native architectures must build and pass smoke tests before final image tags are published.

For an illustrative upstream tag `dsh-v0.2.1-rc.3`, an immutable packaging revision is `0.2.1-rc.3-r1`. Movable aliases are `0.2.1-rc.3`, `dsh-v0.2.1-rc.3` and, when the version advances, `latest`. **`latest` includes alpha/rc releases.** The examples describe naming, not current registry availability.

The durable queue is stored on the `release-state` branch; do not delete it. Failed work remains pending. GitHub schedules may be delayed, and public repositories can have scheduled workflows disabled after 60 days without activity. Publishing images does not update running containers. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

See [release operations](docs/releases.md) for Docker Hub Secrets, manual builds, revision numbering and retries. See [CONTRIBUTING.md](CONTRIBUTING.md) for validation and [SECURITY.md](SECURITY.md) for security boundaries.

## License

This packaging project uses the [MIT license](LICENSE). Upstream code and bundled dependencies retain their respective licenses.
