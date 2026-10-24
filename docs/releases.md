# 镜像发布与上游监控

## 配置 GitHub Actions

在仓库 **Settings → Secrets and variables → Actions → Repository secrets** 中设置：

| Secret | 内容 |
| --- | --- |
| `DSH_HUB_USERNAME` | 有权推送 `razeencheng/dsh` 的 Docker Hub 用户名 |
| `DSH_HUB_TOKEN` | 相应 Docker Hub access token，需具有镜像写入权限 |

它们是 GitHub Actions Secrets，不是提交进 `.env.example` 的值。发布流程通过 `${{ secrets.DSH_HUB_USERNAME }}` 和 `${{ secrets.DSH_HUB_TOKEN }}` 读取，不依赖开发者电脑上的环境变量。

允许仓库运行 Actions。准备与发布作业需要 `contents: write` 来维护 `release-state` 分支；若组织策略或分支规则阻止写入，应对该状态分支提供合适权限。其余作业默认只读。工作流只允许目标仓库 `razeencheng/dsh-docker` 的 `main` 分支发布，Fork 需自行调整仓库与镜像目标后使用自己的凭据。

## 自动发现的范围

[`release.yml`](../.github/workflows/release.yml) 每小时第 17、47 分钟检查一次，按 UTC 调度。它直接读取上游 [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) 的 Git 标签，不依赖是否创建 GitHub Release。

- 支持 `dsh-v<major>.<minor>.<patch>` 以及 `-alpha...`、`-rc...` 等符合当前版本解析规则的预发布标签。
- 首次运行将现有标签记录为基线，只构建语义版本最高的一个。
- 后续发现的所有新标签都会入队，包括低于当前最高版本的维护版本。
- 每次最多选择 4 个上游版本构建，其余保留在队列，下次继续。待办按尝试次数轮转，避免几个持续失败的版本一直占满名额。
- 上游标签解析为固定提交 SHA 后才构建。已观察标签如果被移动到另一提交，流程报错，需调查后处理，不静默覆盖已有版本。
- `-r<数字>` 后缀为打包修订保留；若上游标签占用这一命名范围，会报告冲突，需人工调整规则，不覆盖已有镜像。

这是轮询而非实时触发。GitHub 的定时作业可能排队、延迟或在高负载时被丢弃，公开仓库连续 60 天无活动时还可能停用定时工作流；应定期检查 Actions 状态，必要时手动重新启用。[GitHub 定时工作流说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## 构建和发布顺序

1. 将发现的上游提交、打包仓库提交、预留修订号与待办队列写入 `release-state` 分支的 `state.json`。
2. 分别在原生 `amd64`、`arm64` Linux runner 上构建镜像。
3. 每个架构验证工具、非 root 用户、CLI、Web 健康检查和 Bubblewrap；验证通过后推送临时架构镜像并记录摘要。
4. 只有同一版本的两个架构都通过，才合并发布多架构镜像，并更新版本别名。
5. 检查清单同时包含 `linux/amd64`、`linux/arm64`，验证别名摘要，再记录发布完成。

同批次有版本失败时，其他已具备双架构结果的版本仍可发布；失败版本保留待办。临时 `build-*` 标签供工作流交接使用，不应作为长期部署目标。发布工作流使用统一并发组和排队设置，避免自动与手动任务同时推进发布状态。

## 镜像标签规则

以上游 `dsh-v0.2.1-rc.3` 为例，命名如下；示例不表示对应镜像已经存在：

| 标签 | 规则 |
| --- | --- |
| `0.2.1-rc.3-r1` | 第 1 次打包修订，工作流不覆盖已发布的该修订 |
| `0.2.1-rc.3-r2` | 同一上游版本的后续打包修订 |
| `0.2.1-rc.3` | 指向该上游版本当前发布的修订 |
| `dsh-v0.2.1-rc.3` | 保留上游标签名称的别名 |
| `latest` | 已成功发布的最高语义版本及其最新修订 |

`latest` 包括预发布版本。比较遵循版本号和预发布标识排序，不按 GitHub Release 发布时间排序；例如更高版本号的 rc 可以超过较低版本号的正式版。手动补构建历史版本不会降低 `latest`。

`-rN` 的不可变性由发布流程执行，而不是宣称 Docker Hub 禁止任何维护者手动覆写。需要强制内容固定的部署，请使用摘要。最终镜像清单记录上游提交、打包仓库提交和修订信息，可用于追踪来源。

## 手动运行

在 **Actions → Release images → Run workflow** 中选择 `main`：

- **不填 `upstream_tag`**：立即进行一次自动发现，并处理待办队列。
- **填写完整 `upstream_tag`**：构建该上游标签，例如 `dsh-v0.2.1-rc.3`。对于已经发布的版本，默认预留下一个打包修订号；对于仍待发布的同一任务，继续其待办修订。
- **可选填写 `revision`**：指定未使用的正整数修订号，必须同时提供标签。已经使用或预留的旧修订号不能拿来覆盖历史镜像。

也可以使用 GitHub CLI：

```sh
# 立即检查新标签
gh workflow run release.yml --repo razeencheng/dsh-docker --ref main

# 指定标签，默认选择下一个可用修订号
gh workflow run release.yml --repo razeencheng/dsh-docker --ref main \
  -f upstream_tag=dsh-v0.2.1-rc.3

# 查看发布任务
gh run list --repo razeencheng/dsh-docker --workflow release.yml
```

当前 Dockerfile 适配所选上游结构。手动选择历史标签只是请求尝试构建，不保证早期版本具有相同目录、构建命令或运行时接口。

## 重试与状态维护

`release-state` 是持久发布账本，不是可随时清除的缓存。**不要删除该分支或其中的 `state.json`，也不要合并进 `main`。** 它记录已观察标签、待办任务、预留修订号、成功发布的摘要与 `latest`。

构建、测试或推送失败时，待办任务不标记完成；下次定时运行或手动空参数检查会重试。网络、凭据或权限错误需先修复根因。若上游发布了不兼容版本，需要修改打包逻辑后再重试。

待办任务尚未完成时，如果打包仓库提交发生变化，规划器会保留旧修订号并分配新修订号，避免在发布成功但状态写入失败等情况下覆盖已有内容。因此修订号可能跳号，这是正常行为。

已经成功发布的版本不会因 `main` 更新而自动重建。更新基础镜像、工具、Dockerfile 或修复打包问题后，需要手动指定对应上游标签，生成新的修订版。

若状态写入失败，应先保留分支和现有镜像，查看日志再重试。不要通过删除状态、手动移动别名或复用修订号来“重置”流程；这会破坏重复执行与回滚所依赖的记录。

## CI 和部署的关系

[`ci.yml`](../.github/workflows/ci.yml) 对所有运行执行发布规划测试、ShellCheck、Compose 配置和 actionlint 检查。PR 修改 `Dockerfile`、`docker/**` 或 `scripts/smoke-test.sh` 时，以及手动运行 CI 时，才在前置检查通过后构建三个组合：默认 `amd64`、默认 `arm64` 和可选工具全部关闭的 `amd64`。仅修改文档或 Actions 依赖的 PR、普通 `main` 推送不构建镜像；CI 不推送发行标签。

镜像发布只修改 Docker Hub 与发布状态，不登录用户服务器，不自动执行 `docker compose pull` 或重建运行中的容器。服务器升级、数据备份和固定版本回滚见[部署指南](deployment.md#迁移升级与回滚)。
