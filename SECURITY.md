# 安全说明

本仓库是 DeepSeek Harness 的非官方容器打包。助手可以运行命令、修改允许访问的文件，并调用配置的外部服务。容器权限、上游工具权限、挂载目录和凭据共同决定它能操作的范围。

## 默认边界

- 使用 UID/GID `1000:1000`，移除全部 Linux capabilities，并开启 `no-new-privileges`。
- Compose 的 Web 端口默认仅绑定 `127.0.0.1`；外部访问使用 SSH 隧道或带认证的 TLS 反向代理。
- 默认权限模式为 `workspace-write`。上游先探测 Bubblewrap，不可用时尝试原生 Landlock 后端；需要至少一个真实后端可用。Compose 为兼容 Bubblewrap 的用户命名空间调用使用 `seccomp=unconfined`，因此 Docker 默认 seccomp 过滤未启用；配置不禁用 Docker AppArmor，不能把这份配置视作完整隔离保证。
- 默认不安装 Docker daemon，也不挂载宿主机 Docker socket。`docker-compose.docker.yml` 是明确启用宿主机控制能力的选项。
- `config` 只读挂载；`data`、`workspace`、`plugins` 可写。挂载目录中的修改会直接作用于宿主机。

Harness 使用启动 URL 中的 token 交换签名 cookie，为 API 和 WebSocket 连接认证。该 URL 和包含它的日志都是敏感登录凭据，不要公开分享，提交问题前需移除 token。`DSH_TRUSTED_HOST` 是独立的访问地址检查，不能代替认证。域名访问仍建议使用带认证的 TLS 反向代理作为额外控制。网络连接、外部 API 和主动授予的凭据也不受文件目录隔离自动保护。

## Docker socket 与凭据

对于通常以 root 运行的 Docker daemon，获得其控制接口往往意味着能够控制宿主机，包括通过新容器挂载宿主机文件系统。非 root 容器用户不会抵消这一权限，socket 的只读挂载也不能将 Docker API 变成只读。[Docker 官方安全说明](https://docs.docker.com/engine/security/)

尽量使用专用且权限有限的 Git、SSH 和 API 凭据。不要将整个个人主目录挂载给助手。`.env`、`data/.dsh` 和 `data/home` 可能含凭据、会话与用户配置，备份也应按敏感数据保管。不要把它们添加到公开仓库或构建上下文。

## 更新与报告

预发布版本会参与自动构建，`latest` 也可能指向预发布版本。部署时固定已验证的 `-rN` 标签或镜像摘要，升级前备份数据。上游数据格式升级可能使直接降级不可行，参见[迁移与回滚](docs/deployment.md#迁移升级与回滚)。

发现本仓库的安全问题时，优先使用 GitHub 仓库 Security 页面中可用的私密报告入口。如果该入口未启用，请通过维护者 GitHub 主页提供的联系渠道沟通；不要在公开 Issue 中发布密钥、会话数据或可直接利用的细节。上游 Harness 的漏洞应同时遵循上游安全报告流程。

目前不承诺历史版本的长期安全维护或固定响应时限。
