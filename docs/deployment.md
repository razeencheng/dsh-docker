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
| `HOME=/data/home` | 用户配置、SSH 和用户安装的软件 |
| `GOPATH=/data/home/go` | Go 工作目录和 `go install` 的程序 |
| `NPM_CONFIG_PREFIX=/data/home/.local` | 非 root 用户安装 npm 全局工具的位置 |
| `/workspace` | 默认工作目录 |
| `/plugins` | 本地插件源码 |
| `/config` | 自定义配置，只读 |

入口程序创建用户目录；重建容器会保留挂载到 `data` 的内容。镜像内其他临时修改不会因此持久化，系统工具应写入 Dockerfile 后重新构建。

默认构建缓存放在 `/tmp/dsh-cache`：Go 的 `GOCACHE` 和 `GOMODCACHE` 分别使用 `go-build`、`go-mod` 子目录，`NPM_CONFIG_CACHE`、`PIP_CACHE_DIR`、`XDG_CACHE_HOME` 分别使用 `npm`、`pip`、`xdg` 子目录。pnpm 的 `PNPM_CONFIG_STORE_DIR` 和 `PNPM_CONFIG_STATE_DIR` 分别使用 `pnpm/store`、`pnpm/state`。这样工具在 `workspace-write` 中无需写入被限制的 `/data` 主目录；这些缓存可重新生成，容器重建后不保留。`HOME`、`GOPATH` 中的程序和 npm 全局安装目录仍位于持久化的 `/data/home`，全局安装需要相应写入权限，项目依赖和 Python 虚拟环境优先放在 `/workspace` 内。

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

在服务器读取启动日志：

```sh
docker compose logs dsh
```

找到包含 `token` 查询参数的启动登录 URL。日志里的容器 IP 通常不能从自己电脑直接访问；通过上述隧道连接时，仅将 URL 的主机和端口替换为 `127.0.0.1:3080`，保留完整路径、token 和其他查询参数，再在浏览器打开。首次访问裸地址不能提供登录凭据。如果改用 `localhost` 或不同本地端口，应同步调整 `DSH_TRUSTED_HOST`。

Harness 使用启动 token 交换签名 cookie，为 API 和 WebSocket 连接认证。包含 token 的 URL 和启动日志应按敏感登录凭据保管，分享排错日志前先移除 token。

### 域名与反向代理

在服务器部署带身份认证和 TLS 的反向代理，转发到 `http://127.0.0.1:3080`，并支持 WebSocket。保留浏览器使用的 Host 信息，将 `DSH_TRUSTED_HOST` 设置为对应域名或域名加显式端口，例如 `harness.example.com` 或 `harness.example.com:8443`，不包含协议或路径。

同样从启动日志取得登录 URL，将协议和主机端口换成外部 HTTPS 地址，并保留完整 token 查询参数。如果部署配置了路径前缀，也使用相应的外部前缀。代理认证是额外的访问控制，不取代 Harness 自身的 token/cookie 登录流程。

反向代理若也运行在容器中，其 `127.0.0.1` 指向自己。此时应显式配置共享 Docker 网络或可访问的宿主机地址，再据此设置代理目标。不要简单开放公网端口来绕过网络配置。

`DSH_TRUSTED_HOST` 只校验访问地址，与 Harness 的 token/cookie 登录认证相互独立。默认 Compose 仅向宿主机回环地址发布端口；若更改 `DSH_BIND_ADDRESS`，需同时考虑防火墙与认证边界。

### 容器内监听与健康检查

上游 CLI 不接受通配监听地址。本镜像入口在启动 `web` 时选择容器的非回环 IPv4 地址，并传入端口；无此地址时回退到 `127.0.0.1`。通常无需设置 `DSH_LISTEN_ADDRESS`。特殊网络配置需要覆盖时，传入容器实际拥有的地址。

健康检查使用同样的地址选择逻辑：

```sh
docker compose exec dsh /usr/local/bin/dsh-healthcheck
docker compose logs --tail=100 dsh
```

健康检查请求实际存在、公开可访问的前端 JavaScript 静态资源，收到 HTTP 200 时退出码为 0。它不要求受认证保护的首页在未登录时返回 200，也不验证 API Key、模型调用或外部服务是否可用。

完整的 `make smoke` 另行验证登录流程：未认证首页返回 401，启动 token 交换返回 303 并设置 cookie，携带该 cookie 访问首页返回 200；同时检查启动日志中没有插件激活或模块导入失败。

## 沙箱要求

`workspace-write` 和 `read-only` 需要至少一个真实沙箱后端可用。当前打包的上游 `LocalSandboxProvider` 会先探测 Bubblewrap，失败时尝试原生 Landlock 后端。宿主机不允许 Bubblewrap 的用户命名空间或挂载操作时，Landlock 仍可能可用，取决于内核与运行环境支持。

Compose 保留非 root 用户、全部 capabilities 移除和 `no-new-privileges`，并为兼容 Bubblewrap 调用设置 `seccomp=unconfined`，不禁用 Docker AppArmor。应验证实际文件限制，而不是要求每个后端单独成功。

对已经构建或拉取的镜像运行完整启动测试，将 `TAG` 替换为所选标签：

```sh
make smoke IMAGE=razeencheng/dsh TAG=local
```

该测试在临时容器中加载 Harness 的实际沙箱插件，确认 `workspace-write` 能写入 `/workspace`，不能修改或创建 `/data` 中原本有权限写入的文件，并确认 `read-only` 不能写入工作目录。它还检查工具、CLI 和 Web。禁用可选工具的自定义镜像需传入对应的 `INSTALL_*` 参数，见[贡献指南](../CONTRIBUTING.md)。

下面的命令只诊断 Bubblewrap 后端：

```sh
docker compose exec dsh bwrap \
  --ro-bind / / --dev /dev --proc /proc --die-with-parent -- true
```

无输出且退出码为 0 表示此次 Bubblewrap 调用可用；失败不表示 Landlock 也不可用。确实需要排查 Bubblewrap 时，可以检查宿主机用户命名空间配置：

```sh
sysctl kernel.unprivileged_userns_clone
sysctl user.max_user_namespaces
sysctl kernel.apparmor_restrict_unprivileged_userns
```

部分系统没有其中某些参数。Ubuntu 的用户命名空间限制或 Docker AppArmor 的挂载限制也可能阻止 Bubblewrap。CI 对一次性 runner 的相关 sysctl 调整只为支持 Bubblewrap，不是 Landlock 的必需条件，也不等于禁用 Docker AppArmor。不要为了使某个后端探测通过就自动放开宿主机策略；若真实沙箱测试失败，应检查日志与内核支持，不要切换到 `danger-full-access` 来掩盖问题。

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
3. 新镜像的 `HOME` 改为 `/data/home`。如果旧容器在 `/home/node` 中保存了 Git/SSH 配置或用户工具，先从旧容器提取所需文件，再复制到 `data/home`；仅挂载旧 `data` 不会自动迁移这些文件。默认构建缓存可重新生成，无需复制旧缓存。
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
