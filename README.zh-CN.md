# 1panel-app-adapter

[![README-English](https://img.shields.io/badge/README-English-1f6feb)](./README.md) [![README-简体中文](https://img.shields.io/badge/README-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-fa8c16)](./README.zh-CN.md)

另见：[`DELIVERY_REPORT.md`](./DELIVERY_REPORT.md)，用于维护者查看规则决策与回归说明。

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
- `scripts/import-baota-app.py` — 导入宝塔/aaPanel Docker 商店应用
- `scripts/finalize_runtime_scripts.sh`
- `scripts/validate-v2.sh`
- `scripts/generate.sh` — v2 生成器包装脚本（兼容 CLI）
- `scripts/validate.sh` — v2 校验包装脚本
- `scripts/cleanup-migrate-backups.sh` — 清理迁移备份
- `scripts/test-env-sample-closure.sh` — 回归测试：.env.sample 闭合检查

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
  [--website <url>] \
  [--document <url>] \
  [--github <url>] \
  [--volumes <host:container,...>] \
  [--with-panel-deps] \
  [--force]
```

说明：

- `--with-panel-db-redis` 是 `--with-panel-deps` 的别名
- 生成的 compose 使用 `container_name: ${CONTAINER_NAME}`
- 宿主机路径类型的 volume 会在版本级 `data.yml` 中生成对应的 `APP_DATA_DIR_*` 字段
- 生成的 compose 会保留上游显式 healthcheck，但不会自动添加默认探针
- 未显式传入 `--tag` 时，脚手架会根据 `--type`、标题和镜像推断更合适的默认标签
- 来源证据是必填项，会落盘到 `<app>/source-evidence.json`
- `--timezone` 用于控制版本级 `data.yml` 里 `TZ` 的默认值
- 默认不会覆盖非空目标应用目录；如确认要覆盖，需显式传 `--force`
- raw scaffold 输出只是起点，不应直接视为 strict-store 可交付产物
- `--force` 只是允许写入已有非空目录，不会替你清理残留文件

## 从 scaffold 到 strict-store 的最短路径

```bash
# 1）先生成脚手架
bash scripts/scaffold-v2.sh   --app-key demo   --title "Demo"   --image nginx:latest   --version 1.0.0   --source-repository <repo-url>   --source-docker-docs <docs-url>   --source-compose-file <compose-url>

# 2）替换脚手架占位内容：
#    - README.md
#    - root data.yml 中的 description / shortDesc / 多语言文案

# 3）如果改过 envKey 或 compose 内容，检查 compose 变量与 .env.sample

# 4）对“已补齐真实内容”的产物跑 strict-store
bash scripts/validate-v2.sh --dir ./1panel-apps/demo --strict-store
```

## 从 AppSpec 生成

```bash
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --strict-store-validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate --require-validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --strict-store-validate --require-validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate --report artifacts/run-report.json
```

当启用校验时，报告 JSON 会包含 `validateSummary.fail/warn/info`。其中 `--validate` 运行基础校验；`--strict-store-validate` 仅适用于已替换 placeholder 的交付态产物。
报告 JSON 还会包含 `qualityGate`（`not_run` / `passed` / `failed`）。

参考：

- `references/appspec.md`
- `assets/sample-appspec.json`

## 导入宝塔/aaPanel Docker 商店应用

```bash
# 单应用目录，包含 app.json/icon.png/<version>/docker-compose.yml
python3 scripts/import-baota-app.py \
  --input <baota-app-dir> \
  --out-dir ./1panel-apps \
  --version latest \
  --validate \
  --require-validate

# 批量导入 apphub 目录，其直接子目录是各个应用目录
python3 scripts/import-baota-app.py \
  --input <apphub-dir> \
  --batch \
  --out-dir ./1panel-apps \
  --validate \
  --report artifacts/baota-import-report.json

# 只导出标准化 AppSpec，再走 AppSpec 生成路径
python3 scripts/import-baota-app.py \
  --input <baota-app-dir> \
  --version latest \
  --emit-appspec artifacts/app.appspec.json
```

导入器基于公开的 `aaPanel/apphub` 格式和 aaPanel Docker 应用运行逻辑实现。它会把 `${HOST_IP}:${APP_PORT}:<container>` 端口转换为 `PANEL_APP_PORT_*`，把 `${APP_PATH}` 挂载转换为可配置的 `APP_DATA_DIR*` 字段，将 `baota_net` 替换为 `1panel-network`，将 `createdBy: bt_apps` 改为 `Apps`，移除宝塔 CPU/内存 deploy 限制，并把迁移说明写入 `source-evidence.json`。

参考：

- `references/baota-app-format.md`
- `references/baota-to-1panel-mapping.md`

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
- root/version/compose 的重复 YAML key 检测
- 基于 `.env.sample` 与安全兜底 `CONTAINER_NAME` 的 `docker compose config` 解析校验
- 完整的 compose 渲染校验依赖执行环境中可用的 `docker compose` CLI
- `--strict-store` 下对 README/元数据占位模板残留的阻断检测
- `references/implicit-envkeys.md` 中声明的隐式变量例外
- 在 `--strict-store` 下执行 `references/readme-style.md` 约定的 README 结构检查
- 可配置的 i18n 质量告警，覆盖 `additionalProperties.description` 与表单 `label` 多语言映射
- 表单 `label map` 缺项、旧版 `zh-hant` 命名等提示
- service 级 `networks:` 与 `1panel-network` 相关的桥接网络检查
- healthcheck 作为可选运行增强项处理，不作为交付门禁

## 策略与风格参考

- `references/source-policy.md`
- `references/readme-style.md`
- `references/implicit-envkeys.md`
- `references/edit-exempt-envkeys.md` — edit:true 例外清单
- `references/schema.md` — 1Panel AppStore v2 字段事实表

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
