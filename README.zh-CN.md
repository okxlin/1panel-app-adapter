# 1Panel AppStore Docker 应用适配 Skill

[English](./README.md) | [简体中文](./README.zh-CN.md)

`1panel-app-adapter` 是一个 **1Panel app skill**，用于将 Docker 应用适配为 **1Panel 应用商店**（`AppStore`/`appstore`）安装包。它支持创建新应用、转换 Docker Compose 与 AppSpec、导入 aaPanel/宝塔应用、从 v1 迁移到 v2，并校验可提交到应用商店的产物。

## 主要能力

| 任务 | 输入 | 产物 |
| --- | --- | --- |
| 创建应用骨架 | 镜像、端口、卷和官方来源 URL | 1Panel v2 应用骨架 |
| 从规范生成 | AppSpec JSON | 可复现的应用包与可选报告 |
| 导入应用 | aaPanel/宝塔 `apphub` 目录 | 规范化的 1Panel 应用包 |
| 迁移应用 | 现有 v1 或混合结构应用 | 1Panel v2 目录结构 |
| 校验应用 | 生成或手写的应用目录 | 基础、strict-store 与多语言检查结果 |

本 skill 优先依据 1Panel 运行时行为和官方资料，其次才参考仓库约定与第三方示例。如果应用没有可靠的 Docker 部署来源，它不会猜测镜像、端口、存储卷或依赖关系。

## 在 Agent 中使用

可以让兼容 skill 的编码 Agent 显式调用：

```text
使用 $1panel-app-adapter 将这个 Docker 应用适配为通过校验的 1Panel AppStore 应用包。
```

它适用于单应用和批量应用适配、已有应用更新、AppStore 投稿准备以及提交前校验。

## 快速开始

根据官方 Docker 来源创建 v2 应用骨架：

```bash
bash scripts/scaffold-v2.sh \
  --app-key demo \
  --title "Demo" \
  --image nginx:latest \
  --version 1.0.0 \
  --source-repository <repository-url> \
  --source-docker-docs <docker-docs-url> \
  --source-compose-file <compose-url>
```

替换生成的 README 与元数据占位内容，检查 Compose 变量和 `.env.sample`，再执行交付门禁：

```bash
bash scripts/validate-v2.sh \
  --dir ./1panel-apps/demo \
  --strict-store \
  --i18n-mode strict \
  --i18n-scope all
```

脚手架产物只是起点。应用专属元数据、翻译、拓扑、镜像来源和运行行为完成复核后，才能视为可提交应用商店的产物。

## 工作流

### 从 AppSpec 生成

```bash
python3 scripts/generate-from-appspec.py \
  --spec assets/sample-appspec.json \
  --validate \
  --require-validate \
  --report artifacts/run-report.json
```

参见 [AppSpec 说明](./references/appspec.md)与[示例 AppSpec](./assets/sample-appspec.json)。只有将生成的占位内容替换为交付态内容后，才应使用 `--strict-store-validate`。

### 导入 aaPanel 或宝塔应用

导入单个应用：

```bash
python3 scripts/import-baota-app.py \
  --input <baota-app-dir> \
  --out-dir ./1panel-apps \
  --version latest \
  --validate \
  --require-validate
```

批量导入 `apphub` 的直接子目录：

```bash
python3 scripts/import-baota-app.py \
  --input <apphub-dir> \
  --batch \
  --out-dir ./1panel-apps \
  --validate \
  --report artifacts/baota-import-report.json
```

导入器会把 aaPanel/宝塔的端口、绑定挂载、网络设置、资源限制和元数据转换为 1Panel 约定。导入结果仍需对照应用官方来源核验。参见[格式说明](./references/baota-app-format.md)与[映射规则](./references/baota-to-1panel-mapping.md)。

### 从 v1 迁移到 v2

```bash
bash scripts/migrate-v1-to-v2.sh \
  --src <app-dir> \
  --out <out-root> \
  --version <source-version> \
  --target-version <target-version>
```

更新已经发布的应用时，在调整镜像、变量、依赖、存储卷或生命周期脚本前，应先检查[升级与维护安全规则](./references/upgrade-maintenance.md)。

### 补齐生命周期脚本

```bash
bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir>

# 从精确镜像证明非 root 可写挂载的数字身份后：
bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir> \
  --dir-owner APP_DATA_DIR=<uid>:<gid>:0750 --replace-init
```

该命令会补齐缺失的 `init.sh`、`upgrade.sh` 和 `uninstall.sh`，并使用基于应用根目录的路径处理方式。`--dir-owner` 只有在显式给出 `--replace-init` 后才会重新生成 `init.sh`，并仅对可信版本目录的直接子目录做非递归权限设置；执行时必须是 root。不要根据应用名称猜测 UID/GID，也不要把某个镜像的示例值复用于其他镜像。

### 校验应用包

```bash
# 基础校验
bash scripts/validate-v2.sh --dir <app-dir>

# AppStore 交付检查
bash scripts/validate-v2.sh --dir <app-dir> --strict-store \
  --source-evidence-mode required --require-delivery-evidence

# 校验多版本应用中的一个版本
bash scripts/validate-v2.sh --dir <app-dir> --version <version> --strict-store \
  --source-evidence-mode required --require-delivery-evidence

# 在有溯源门禁的流程中强制要求来源证据
bash scripts/validate-v2.sh --dir <app-dir> --source-evidence-mode required

# 强制要求已验证的许可证与哈希绑定的再分发交付证据
bash scripts/validate-v2.sh --dir <app-dir> --source-evidence-mode required \
  --require-delivery-evidence
```

校验覆盖：

- 根目录与版本级 `data.yml` 的结构、必填字段、重复 YAML key 和标签；
- Compose 渲染、变量闭环、`.env.sample`、服务标签、端口、存储卷和网络拓扑；
- 占位内容残留和 AppStore README 结构；
- `en`、`zh`、`zh-Hant`、`ja`、`ko`、`ru`、`ms`、`pt-br` 的描述与表单标签；
- 可选来源证据和 strict-store 交付规则。

完整 Compose 渲染依赖 `docker compose` CLI。来源证据默认只告警，只有显式传入 `--source-evidence-mode required` 时才会成为必需项；该历史模式负责溯源校验，需要把许可证和再分发交付作为发布门禁时，再加 `--require-delivery-evidence`。

## 环境要求

- Linux 或其他带有 `bash` 的环境
- Python 3 与 `PyYAML`
- 用于完整 Compose 校验的 Docker Compose
- `scripts/normalize-logo.sh` 所需的 ImageMagick 与 GNU 兼容 `stat`

文本与 shell 文件应使用 LF 换行。

## 规则参考

- [来源策略](./references/source-policy.md)
- [拓扑预检](./references/topology-preflight.md)
- [生命周期安全](./references/lifecycle-safety.md)
- [1Panel schema 事实表](./references/schema.md)
- [应用 README 风格](./references/readme-style.md)
- [隐式环境变量](./references/implicit-envkeys.md)
- [可编辑字段例外](./references/edit-exempt-envkeys.md)
- [升级与维护安全](./references/upgrade-maintenance.md)

## 常见问题

### 这是一个 1Panel app skill 吗？

是。它为编码 Agent 提供 1Panel 应用适配、生成、迁移和校验所需的来源规则、打包规则与脚本。

### 能把 Docker Compose 转换为 1Panel AppStore 应用包吗？

可以，前提是应用有可信的 Docker 部署来源。生成后仍需完成应用专属复核和运行测试，才能进入投稿流程。

### 会直接发布到 1Panel 应用商店吗？

不会。它只准备并校验本地应用产物；发布、推送分支和创建拉取请求仍属于单独的 Git 与 GitHub 操作。
