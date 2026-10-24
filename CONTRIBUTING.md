# 贡献指南

欢迎改进镜像打包、开发工具、部署文档和发布自动化。DeepSeek Harness 本身的问题请先确认能否在[上游项目](https://github.com/deepseek-ai/deepseek-harness)中复现；本仓库负责容器环境与发布流程。

## 开发与验证

需要 Git、Docker Engine/Compose/Buildx，以及运行发布规划测试的 Python 3。ShellCheck 和 actionlint 用于额外的静态检查。

```sh
make test
make check
make build
make smoke
```

`make test` 不访问 GitHub 或 Docker Hub；它检查版本排序、首次发现、待发布队列、重试、修订号和别名规则。`make check` 还检查启动测试脚本语法与两个 Compose 配置。

修改工具安装逻辑时，同时验证全部可选工具关闭的镜像：

```sh
make build TAG=lite INSTALL_PYTHON=false INSTALL_GO=false INSTALL_DOCKER=false
make smoke TAG=lite INSTALL_PYTHON=false INSTALL_GO=false INSTALL_DOCKER=false
```

`scripts/smoke-test.sh` 检查非 root 用户、基础工具、可选工具是否符合构建开关、Bubblewrap、CLI 启动及 Web 健康检查。运行环境必须支持非特权用户命名空间，参见[部署指南](docs/deployment.md#沙箱要求)。

## 提交要求

- 描述具体问题、修改后的行为和实际完成的验证。
- 修改环境变量、标签策略或目录布局时，同步更新相关文档。
- 保持 Python 发布规划逻辑只依赖标准库；状态变更需有覆盖失败与重试场景的测试。
- 不要提交 `.env`、API Key、SSH 私钥、Docker 登录配置、`data/` 中的会话或项目私有文件。
- 第三方 Actions 固定到提交 SHA；Dependabot 负责提出更新。
- 未运行的架构或测试请明确说明，不要将构建成功等同于运行验证通过。

## CI 与发布边界

PR 和手动运行的 CI 会构建三个组合：默认工具的 `amd64`、默认工具的 `arm64`、禁用全部可选工具的 `amd64`。每个组合运行镜像启动检查。推送 `main` 执行静态检查和发布规划测试，不自动覆盖 Docker Hub 镜像。

发布工作流独立运行，只在 `razeencheng/dsh-docker` 的 `main` 分支执行；Fork 默认不能向该镜像仓库发布。Docker Hub 凭据只交给需要发布的步骤。具体发布策略见[发布指南](docs/releases.md)。

`make push TAG=...` 是维护者手动发布入口，直接构建并推送指定标签，**不会执行 Actions 中的双架构启动验证和状态记录**。日常发行应使用发布工作流，避免手动覆盖受管理的版本标签。

## 文档与许可证

`README.md` 为中文主文档，`README.en.md` 为英文概览。详细部署与维护说明保存在 `docs/`。贡献本仓库代码即按仓库的 [MIT 许可证](LICENSE) 提供；引入其他项目文件时应保留其要求的版权和许可证声明。
