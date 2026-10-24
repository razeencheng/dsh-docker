# 部署与使用

## 运行环境与目录

镜像支持 Linux `amd64` 和 `arm64`。推荐使用安装了 Docker Engine 与 Compose 插件的 Linux 服务器。默认 Compose 的资源上限为 4 GiB 内存、4 个 CPU 和 512 个进程，可在 `.env` 调整内存、CPU 和日志保留配置。

容器以 UID/GID `1000:1000` 运行，不在启动时自动修改宿主机文件权限。首次部署需准备目录：

```sh
cp .env.example .env
mkdir -p data workspace plugins config
sudo chown -R 1000:1000 data workspace plugins
chmod 700 data
chmod 600 .env
```

仅对本项目专用目录执行上述权限调整。若挂载已有多人共享的项目目录，应通过组权限或 ACL 赋予 UID 1000 所需权限，避免递归改变其他服务的数据所有者。`config` 中的文件需要能被容器用户读取。

| 环境变量或目录 | 用途 |
| --- | --- |
| `DSH_HOME=/data/.dsh` | Harness 配置、profiles、skills、sessions、storages 等 |
| `HOME=/data/home` | 用户配置、SSH、缓存和用户安装的软件 |
| `GOPATH=/data/home/go` | Go 工作目录和 `go install` 的程序 |
| `NPM_CONFIG_PREFIX=/data/home/.local` | 非 root 用户安装 npm 全局工具的位置 |
| `/workspace` | 默认工作目录 |
| `/plugins` | 本地插件源码 |
| `/config` | 自定义配置，只读 |

入口程序创建用户目录；重建容器会保留挂载到 `data` 的内容。镜像内其他临时修改不会因此持久化，系统工具应写入 Dockerfile 后重新构建。

## 访问 Web UI

### SSH 隧道

在 `.env` 填写 API Key。默认地址适用于下述 SSH 隧道：

```dotenv
DEEPSEEK_API_KEY=填写你的密钥
DSH_BIND_ADDRESS=127.0.0.1
DSH_HOST_PORT=3080
DSH_TRUSTED_HOST=127.0.0.1:3080
```

```sh
docker compose pull
docker compose up -d
docker compose ps
```

在自己电脑上执行：

```sh
ssh -N -L 3080:127.0.0.1:3080 user@server
```

打开 <http://127.0.0.1:3080>。如果改用 `localhost` 或不同本地端口，应同步调整 `DSH_TRUSTED_HOST`。

### 域名与反向代理

在服务器部署带身份认证和 TLS 的反向代理，转发到 `http://127.0.0.1:3080`，并支持 WebSocket。保留浏览器使用的 Host 信息，将 `DSH_TRUSTED_HOST` 设置为对应域名或域名加显式端口，例如 `harness.example.com` 或 `harness.example.com:8443`，不包含协议或路径。

反向代理若也运行在容器中，其 `127.0.0.1` 指向自己。此时应显式配置共享 Docker 网络或可访问的宿主机地址，再据此设置代理目标。不要简单开放公网端口来绕过网络配置。

`DSH_TRUSTED_HOST` 不提供登录认证。默认 Compose 仅向宿主机回环地址发布端口；若更改 `DSH_BIND_ADDRESS`，需同时考虑防火墙与认证边界。

### 容器内监听与健康检查

上游 CLI 不接受通配监听地址。本镜像入口在启动 `web` 时选择容器的非回环 IPv4 地址，并传入端口；无此地址时回退到 `127.0.0.1`。通常无需设置 `DSH_LISTEN_ADDRESS`。特殊网络配置需要覆盖时，传入容器实际拥有的地址。

健康检查使用同样的地址选择逻辑：

```sh
docker compose exec dsh /usr/local/bin/dsh-healthcheck
docker compose logs --tail=100 dsh
```

退出码 0 表示 Web HTTP 检查通过。它不验证 API Key、模型调用或外部服务是否可用。

## 沙箱要求

`workspace-write` 和 `read-only` 需要可用的命令沙箱。镜像包含 Bubblewrap，Compose 为其用户命名空间调用设置 `seccomp=unconfined`，同时保留非 root 用户、全部 capabilities 移除和 `no-new-privileges`。这是明确的兼容性取舍，不是特权容器配置。

```sh
docker compose exec dsh bwrap \
  --ro-bind / / --dev /dev --proc /proc --die-with-parent -- true
```

无输出且退出码为 0 表示基础沙箱调用可用。若宿主机限制非特权用户命名空间，检查：

```sh
sysctl kernel.unprivileged_userns_clone
sysctl user.max_user_namespaces
sysctl kernel.apparmor_restrict_unprivileged_userns
```

部分系统没有其中某些参数。Ubuntu 的 AppArmor 限制也可能影响运行；应由管理员根据主机策略配置相应权限。CI 仅在一次性 GitHub runner 上关闭对应的 AppArmor 用户命名空间限制，这不代表共享服务器应自动照搬。不要用切换到 `danger-full-access` 来掩盖沙箱不可用。

## 使用开发工具

基础开发工具固定安装；Python、Go、Docker 客户端由 `INSTALL_PYTHON`、`INSTALL_GO`、`INSTALL_DOCKER` 三个构建参数控制，默认都是 `true`。关闭参数需要重新构建，详见 [README](../README.md#本地构建)。

```sh
docker compose exec dsh git --version
docker compose exec dsh ssh -V
docker compose exec dsh python3 --version
docker compose exec dsh go version
docker compose exec dsh docker compose version
```

Python 项目使用独立虚拟环境，不要向受系统包管理器维护的 Python 环境强行安装依赖：

```sh
docker compose exec dsh python3 -m venv /workspace/my-project/.venv
docker compose exec dsh /workspace/my-project/.venv/bin/pip install -r /workspace/my-project/requirements.txt
```

Git/SSH 配置可以放在持久化的 `data/home`。为助手创建单独的 SSH Key，并按目标服务提供的指纹验证服务器身份；不要把禁用主机指纹检查作为默认设置。

安装本地插件：

```sh
docker compose exec dsh dsh plugin --profile web add /plugins/my-plugin
```

## 显式启用宿主机 Docker 访问

默认安装的 `docker`、`docker buildx`、`docker compose` 是客户端。没有可访问的 daemon 时，版本命令可用，但构建和容器管理命令不会自动工作。

如决定让助手使用本机 rootful Docker daemon，在 Linux 宿主机运行：

```sh
export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
docker compose -f docker-compose.yml -f docker-compose.docker.yml up -d
docker compose -f docker-compose.yml -f docker-compose.docker.yml exec dsh docker version
```

也可以将实际组 ID 写入 `.env` 的 `DOCKER_GID`，此后持续使用这两个 Compose 文件管理服务。Rootless Docker 和 Docker Desktop 可能使用不同 socket 路径，附加配置中的路径需相应调整。

该覆盖文件增加 socket 挂载和补充用户组。对于常见 rootful daemon，这通常赋予宿主机级别的控制能力；容器里的普通用户身份不再能限制通过 daemon 发出的操作。[Docker 权限说明](https://docs.docker.com/engine/security/)

### 注意宿主机与容器路径

Docker CLI 向 daemon 发送命令，但 `docker run --mount` 等绑定挂载的源路径由 **daemon 所在宿主机**解析。例如项目在服务器 `/srv/dsh-docker/workspace/app`，容器内对应 `/workspace/app`：

- 在容器里执行 `docker build /workspace/app`，构建客户端可以把该目录作为构建上下文传给构建器。
- 在容器里执行 `docker run -v /workspace/app:/app ...`，daemon 会寻找宿主机上的 `/workspace/app`，它通常不是预期的项目目录。

需要启动带源码挂载的其他容器时，使用宿主机真实路径，或有计划地让工作目录在宿主机和助手容器中使用相同绝对路径。Compose 文件中的绑定挂载也要考虑这一差别。[Docker 挂载说明](https://docs.docker.com/engine/storage/bind-mounts/)

除了 Docker socket 权限，Harness 自身的工具权限策略仍可能限制执行；按实际需求配置，不要将整台宿主机设为默认可写工作目录。

## 迁移、升级与回滚

### 从旧部署迁移

1. 记录旧镜像标签或摘要以及当前 Compose、`.env`、自定义配置。先停服务，备份整个 `data`，并单独备份 `workspace`、`plugins` 中需要保留的文件。
2. 保持原 `data/.dsh` 挂载到 `/data/.dsh`，保留 profiles、会话、技能和凭据，不要创建空目录覆盖原数据。
3. 新镜像的 `HOME` 改为 `/data/home`。如果旧容器在 `/home/node` 中保存了 Git/SSH 配置、缓存或用户工具，先从旧容器提取所需文件，再复制到 `data/home`；仅挂载旧 `data` 不会自动迁移这些文件。
4. 确认 `data` 和工作目录对 UID 1000 可读写。旧镜像的 `web.cordis.patch.yml` 通配地址补丁不再是新入口的必需项，迁移时改用新 Compose 启动配置；自定义插件配置需按上游版本另行验证。
5. 使用已发布的固定镜像版本启动，检查日志、Web、会话、插件和工具调用后再恢复日常使用。

### 升级与回滚

发布新的 Docker Hub 标签不会改变正在运行的容器。在 `.env` 中选择已发布的固定修订版，例如 `DSH_IMAGE=razeencheng/dsh:<版本>-r<修订号>`，或使用 `razeencheng/dsh@sha256:<摘要>`：

```sh
docker compose pull
docker compose up -d
docker compose ps
```

回滚时将 `DSH_IMAGE` 改回已验证的旧修订版或摘要，再执行上述命令。应用升级可能修改持久化数据格式，回滚镜像并不会回滚数据；必要时在停服务后恢复升级前的备份。

`latest` 和不带 `-rN` 的版本别名会移动，不能用它们保证回到某次具体打包。不要删除 `data` 来解决升级错误。
