# 1Panel sources

- Runtime/source code (highest priority)
  - https://github.com/1Panel-dev/1Panel
- Official appstore repository
  - https://github.com/1Panel-dev/appstore/tree/dev/apps
- Official wiki (submission guidance)
  - https://github.com/1Panel-dev/appstore/wiki/%E5%A6%82%E4%BD%95%E6%8F%90%E4%BA%A4%E8%87%AA%E5%B7%B1%E6%83%B3%E8%A6%81%E7%9A%84%E5%BA%94%E7%94%A8
- Official docs entry
  - https://1panel.cn/docs/v2/user_manual/appstore/appstore/
Rule order for this skill:

1. Runtime and source-code behavior
2. Official wiki and docs
3. Official appstore repository conventions

## Verified source snapshot (2026-09-10)

- 1Panel `dev-v2`: `a02c25ebcc82e467a5e507cb340f5dc4c2eb2ce5`.
- Official appstore `dev`: `b6c6b459738c5dacb05c015cbf4821a45cc8ef21`.

| Fact | Exact source |
| --- | --- |
| Twelve application locale fields, including `tr`, `es-es`, `fa`, and `lo`; `disabled` and `edit` are distinct form booleans | [agent/app/dto/app.go](https://github.com/1Panel-dev/1Panel/blob/a02c25ebcc82e467a5e507cb340f5dc4c2eb2ce5/agent/app/dto/app.go#L125-L160) |
| UI language names use `zh-Hant`, `pt-BR`, and `es-ES`; application label lookup normalizes them to lowercase | [frontend/src/lang/index.ts](https://github.com/1Panel-dev/1Panel/blob/a02c25ebcc82e467a5e507cb340f5dc4c2eb2ce5/frontend/src/lang/index.ts#L9-L22), [frontend/src/utils/app-store.ts](https://github.com/1Panel-dev/1Panel/blob/a02c25ebcc82e467a5e507cb340f5dc4c2eb2ce5/frontend/src/utils/app-store.ts#L7-L37) |
| Install controls bind `disabled` independently of later editability | [detail/params/index.vue](https://github.com/1Panel-dev/1Panel/blob/a02c25ebcc82e467a5e507cb340f5dc4c2eb2ce5/frontend/src/views/app-store/detail/params/index.vue#L1-L20) |
| Missing lifecycle hooks are skipped; custom scripts are optional | [agent/app/service/app_utils.go](https://github.com/1Panel-dev/1Panel/blob/a02c25ebcc82e467a5e507cb340f5dc4c2eb2ce5/agent/app/service/app_utils.go#L998-L1028) |
| Official repository supplies separate Chinese and English READMEs | [Redis README.md](https://github.com/1Panel-dev/appstore/blob/b6c6b459738c5dacb05c015cbf4821a45cc8ef21/apps/redis/README.md), [Redis README_en.md](https://github.com/1Panel-dev/appstore/blob/b6c6b459738c5dacb05c015cbf4821a45cc8ef21/apps/redis/README_en.md) |
| The local app loader reads `README.md`; the source inspected does not prove automatic `README_en.md` selection for local apps | [agent/app/service/app_utils.go](https://github.com/1Panel-dev/1Panel/blob/a02c25ebcc82e467a5e507cb340f5dc4c2eb2ce5/agent/app/service/app_utils.go#L1371-L1374) |

Full twelve-language delivery, sidecar evidence, and the default third-party profile are this skill's policies. They are not additional mandatory fields imposed by the panel. Treat fixed relative mounts and separate README files as repository conventions; preserve exact application deployment requirements when selecting either profile.
