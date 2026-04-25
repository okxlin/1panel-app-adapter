# 1panel-app-adapter

[![README-English](https://img.shields.io/badge/README-English-1f6feb)](./README.md) [![README-简体中文](https://img.shields.io/badge/README-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-fa8c16)](./README.zh-CN.md)

`1panel-app-adapter` 是一个面向公开发布的 1Panel 应用适配 skill，用于把 Docker 应用输入整理为 1Panel 应用产物。它保留了生成、迁移、补丁和校验所需的运行脚本，同时移除了研究过程材料、重放日志和第三方仓库快照。

## 规则优先级

当规则冲突时，按以下顺序判断：

1. `1Panel-dev/1Panel` 运行时行为与源码硬规则
2. 1Panel 官方 wiki 与官方文档
3. 官方 appstore 仓库约定
4. 外部参考文章与第三方示例

只有被运行时行为或明确官方文档支持的规则，才应升级为阻断生成或阻断校验的硬约束。仓库习惯默认属于指导信息，除非校验器显式把它升级为严格规则。

## 内置脚本

- `scripts/scaffold-v2.sh`
- `scripts/migrate-v1-to-v2.sh`
- `scripts/normalize-logo.sh`
- `scripts/detect_architectures.sh`
- `scripts/patch_root_data_yml.py`
- `scripts/patch_version_data_yml.py`
- `scripts/patch_compose_yml.py`
- `scripts/hint-panel-deps.sh`
- `scripts/gen-env-sample.sh`
- `scripts/gen_env_sample.py`
- `scripts/generate-from-appspec.py`
- `scripts/finalize_runtime_scripts.sh`
- `scripts/validate-v2.sh`

## 生成新的应用骨架

```bash
bash scripts/scaffold-v2.sh \
  --app-key <key> \
  --title <title> \
  --image <image> \
  --version <version> \
  --source-repository <url> \
  --source-docker-docs <url> \
  --source-compose-file <url> \
  [--timezone <tz>] \
  [--out-dir <dir>] \
  [--port <host-port>] \
  [--target-port <container-port>] \
  [--type <type>] \
  [--tag <tag>] \
  [--volumes <host:container,...>] \
  [--with-panel-deps]
```

说明：

- `--with-panel-db-redis` 是 `--with-panel-deps` 的别名
- 生成的 compose 使用 `container_name: ${CONTAINER_NAME}`
- 宿主机路径类型的 volume 会在版本级 `data.yml` 中生成对应的 `APP_DATA_DIR_*` 字段
- 生成的 compose 默认包含适用于常见 Web 服务的最小 HTTP healthcheck 模板
- 未显式传入 `--tag` 时，脚手架会根据 `--type`、标题和镜像推断更合适的默认标签
- 来源证据是必填项，会落盘到 `<app>/source-evidence.json`
- `--timezone` 用于控制版本级 `data.yml` 里 `TZ` 的默认值

## 从 AppSpec 生成

```bash
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate --require-validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate --report artifacts/run-report.json
```

当启用校验时，报告 JSON 会包含 `validateSummary.fail/warn/info`。
报告 JSON 还会包含 `qualityGate`（`not_run` / `passed` / `failed`）。

参考：

- `references/appspec.md`
- `assets/sample-appspec.json`

## 迁移已有应用目录

```bash
bash scripts/migrate-v1-to-v2.sh --src <app-dir> [--out <out-root>] [--version <source-ver>] [--target-version <target-ver>]
```

## 校验结果

```bash
bash scripts/validate-v2.sh --dir <app-dir>
bash scripts/validate-v2.sh --dir <app-dir> --strict-store
bash scripts/validate-v2.sh --dir <app-dir> --strict-c
bash scripts/validate-v2.sh --dir <app-dir> --i18n-mode warn --i18n-scope description
bash scripts/validate-v2.sh --dir <app-dir> --i18n-mode strict --i18n-scope all
```

当前校验覆盖：

- `source-evidence.json` 是否存在，以及 `repository` / `dockerDocs` / `composeFile` 是否齐全
- 来源证据键是否满足 `https://` URL 形态
- compose `${VAR}` 与版本级 `data.yml` 的 `envKey` 闭环关系
- `references/implicit-envkeys.md` 中声明的隐式变量例外
- 在 `--strict-store` 下执行 `references/readme-style.md` 约定的 README 结构检查
- 可配置的 i18n 质量告警，覆盖 `additionalProperties.description` 与表单 `label` 多语言映射
- 表单 `label map` 缺项、旧版 `zh-hant` 命名等提示
- service 级 `networks:` 与 `1panel-network` 相关的桥接网络检查
- 可选 `--strict-c` 健康检查门禁，用于更严格的交付校验

## 策略与风格参考

- `references/source-policy.md`
- `references/readme-style.md`
- `references/implicit-envkeys.md`

## 运行脚本补齐

```bash
bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir>
```

当你需要在最终校验前确保 `init.sh`、`upgrade.sh`、`uninstall.sh` 存在时，使用这个脚本。

## 打包与平台预期

- 面向 GitHub 托管仓库与 Linux 执行环境
- 文本文件应使用 LF 换行
- shell 脚本以 `bash` 为目标环境
- Python 脚本依赖 `python3` 与 `PyYAML`
- `scripts/normalize-logo.sh` 额外需要 ImageMagick（`convert`、`identify`）和 GNU 兼容 `stat`
- 公开包内容应限制在 docs、references、assets 与运行脚本本身

## 当前实现范围

这个公开包按阶段逐步增强：

1. 先明确规则优先级与权威来源
2. 提供不含研究材料的干净公开 skill 目录
3. 提供 scaffold、migrate、patch、env-sample、runtime-script-finalize、validate 等脚本
4. 让 OpenClaw 工作流描述和实际公开脚本表面保持一致
5. 继续提升默认生成质量，减少 scaffold / migrate 之后还要手工回填的内容，逐步逼近一键交付

文档描述必须和脚本真实能力一致。随着当前版本默认生成质量提升，README 和 SKILL 也应同步更新，但不要夸大尚未实现的智能能力。
