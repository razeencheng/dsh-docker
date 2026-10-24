# DeepSeek Harness Docker

[English](README.en.md) · [部署指南](docs/deployment.md) · [镜像发布](docs/releases.md) · [贡献指南](CONTRIBUTING.md)

将 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 打包为可用于编码、编译和日常自动化的 Docker 镜像。本项目是社区维护的**非官方打包项目**，不属于 DeepSeek 官方发行渠道。

- 支持 `linux/amd64`、`linux/arm64`，镜像仓库为 [`razeencheng/dsh`](https://hub.docker.com/r/razeencheng/dsh)。
- 内置 Git、SSH 客户端和常用开发工具；Python、Go、Docker CLI 默认安装，可在构建时关闭。
- 默认以 UID/GID `1000:1000` 运行，持久化助手状态、用户主目录和项目文件。
- 自动发现上游新版本标签，双架构构建和启动检查通过后发布对应镜像。

镜像只有在发布工作流成功后才可拉取；首次发布完成前，可以按下方说明在本地构建。`latest` 包含上游 alpha、rc 等预发布版本，需要固定环境时请选择带 `-rN` 的版本或镜像摘要。

## 快速开始

在 Linux 服务器上安装 Docker Engine 与 Compose 插件，然后：

```sh
git clone https://github.com/razeencheng/dsh-docker.git
cd dsh-docker
cp .env.example .env
mkdir -p data workspace plugins config
sudo chown -R 1000:1000 data workspace plugins
chmod 700 data
chmod 600 .env
```

编辑 `.env`，填写 `DEEPSEEK_API_KEY`。通过下述 SSH 隧道访问时，保持默认的 `DSH_TRUSTED_HOST=127.0.0.1:3080` 和 `DSH_BIND_ADDRESS=127.0.0.1`：

```sh
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f dsh
```

在自己电脑上建立隧道，将 `user@server` 换成服务器登录地址：

```sh
ssh -N -L 3080:127.0.0.1:3080 user@server
```

打开 <http://127.0.0.1:3080>。默认端口仅绑定服务器回环地址，不能直接通过服务器公网 IP 访问。域名访问、认证反向代理、目录权限和沙箱要求见[部署指南](docs/deployment.md)。`DSH_TRUSTED_HOST` 校验访问地址，不提供登录认证。

## 内置工具

| 类别 | 工具 | 默认安装 | 构建开关 |
| --- | --- | --- | --- |
| JavaScript | Node.js、npm、pnpm | 是 | — |
| 版本控制与连接 | Git、OpenSSH 客户端 | 是 | — |
| 开发与文件处理 | curl、jq、ripgrep、zip/unzip、rsync、make、GCC/G++、pkg-config 等 | 是 | — |
| 命令隔离 | Bubblewrap、上游原生 Landlock 后端 | 是 | — |
| Python | Python 3、pip、venv、`python` 命令 | 是 | `INSTALL_PYTHON` |
| Go | Go 工具链 | 是 | `INSTALL_GO` |
| Docker | Docker CLI、Buildx、Compose 插件 | 是 | `INSTALL_DOCKER` |

可选开关接受 `true` 或 `false`，只在**构建镜像时**生效。给运行中的容器设置同名环境变量不会卸载工具。发布到 Docker Hub 的默认镜像包含全部工具。

上游会先探测 Bubblewrap，不可用时尝试 Landlock。单独运行 `bwrap` 失败不能判定整个沙箱不可用；镜像启动测试会通过 Harness 的实际后端检查工作目录内外的写入限制，详见[沙箱要求](docs/deployment.md#沙箱要求)。

Docker 工具只包含客户端，镜像内没有 Docker daemon，默认也不挂载宿主机 Docker socket。需要构建镜像或管理容器时，按[显式启用 Docker 访问](docs/deployment.md#显式启用宿主机-docker-访问)配置。

## 本地构建

```sh
# 构建本机架构镜像 razeencheng/dsh:local
make build
make smoke

# 构建不含 Python、Go、Docker 客户端的镜像
make build TAG=lite INSTALL_PYTHON=false INSTALL_GO=false INSTALL_DOCKER=false
make smoke TAG=lite INSTALL_PYTHON=false INSTALL_GO=false INSTALL_DOCKER=false

# 分别构建并载入两个架构，标签为 local-amd64 / local-arm64
make build-all
```

默认上游提交固定在 `Dockerfile` 和 `Makefile` 中。自定义源码时，`DSH_REF` 必须是完整的 40 位小写提交 SHA；`DSH_TAG` 用于记录版本，不能代替提交 SHA：

```sh
make build DSH_REF='<完整提交SHA>' DSH_TAG='dsh-v<版本号>'
```

在 `.env` 设置 `DSH_IMAGE=razeencheng/dsh:local` 后，可直接运行 `docker compose up -d` 使用本地镜像，不执行 `docker compose pull`。跨架构本地构建需要 Docker 提供相应的模拟或原生构建节点。

## 数据与日常使用

| 宿主机路径 | 容器路径 | 内容 |
| --- | --- | --- |
| `./data/.dsh` | `/data/.dsh` | Harness 配置、会话、插件与凭据 |
| `./data/home` | `/data/home` | 用户主目录、缓存、Git/SSH 配置和用户安装工具 |
| `./workspace` | `/workspace` | 项目和工作文件 |
| `./plugins` | `/plugins` | 本地插件源码 |
| `./config` | `/config` | 自定义配置，只读挂载 |

将项目放进 `workspace`，或调整 Compose 挂载到自己选择的项目目录。挂载目录中的修改会直接影响宿主机文件，代码仍应使用 Git 管理并定期备份。

```sh
# 进入容器，查看工具
docker compose exec dsh bash

# 将本地插件安装到 Web 配置
docker compose exec dsh dsh plugin --profile web add /plugins/my-plugin

# 为 Python 项目创建隔离环境
docker compose exec dsh python3 -m venv /workspace/my-project/.venv
```

## 自动发布

[Release images 工作流](.github/workflows/release.yml) 每 30 分钟检查上游 `dsh-v*` Git 标签，包括 alpha、rc。首次只构建最新版本，此后发现的新标签均进入队列。发布示例：

| 镜像标签 | 含义 |
| --- | --- |
| `0.2.1-rc.3-r1` | 固定的打包修订版，用于可回滚部署 |
| `0.2.1-rc.3` | 该上游版本最近一次成功打包 |
| `dsh-v0.2.1-rc.3` | 保留上游原名的同版本别名 |
| `latest` | 版本顺序最高且成功发布的镜像，包括预发布版本 |

示例仅说明命名规则，不代表这些镜像已经发布。旧版本补构建不会把 `latest` 降级。仓库代码变更不会自动重建已发布版本；需要时手动发起新的打包修订。配置 Secrets、手动构建和失败重试见[发布指南](docs/releases.md)。

自动发布只更新 Docker Hub，**不会自动升级服务器上的容器**。

## 项目结构

```text
.github/workflows/     检查、构建和自动发布
docker/               工具安装、运行时打包、入口与健康检查
scripts/              发布规划和镜像启动检查
tests/                发布状态与版本规则测试
docs/                 部署和发布说明
Dockerfile            多阶段镜像构建
docker-compose.yml    默认部署
docker-compose.docker.yml  宿主机 Docker 访问的可选覆盖配置
```

本项目使用 [MIT 许可证](LICENSE)。上游代码与镜像内依赖仍受各自许可证约束。报告问题与提交改进前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。
