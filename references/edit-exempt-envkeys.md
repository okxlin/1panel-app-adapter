# edit:true Exception Allowlist (based on v1/v2 store frequency analysis)

Goal: Our adapted artifacts typically enable `edit: true`, but for a few **panel-injected / cluster-internal** envKeys we don't enforce it (allowing missing or `edit: false`), to align with common store patterns and panel injection semantics.

Data Sources:
- v2: `1Panel-dev/appstore` (dev branch) `apps/**/<ver>/data.yml`
- v1/mixed: `okxlin/appstore` (local cache) `apps/**/<ver>/data.yml`

Filtering Rules:
- Merge statistics from both stores
- **Minimum sample size: n > 8**
- `edit` missing rate (edit_missing / n) **≥ 70%**

---

## Suggested Exception Prefixes (covering all hits)

- `PANEL_DB_`
- `PANEL_REDIS_`
- `PANEL_MINIO_`
- `MASTER_`
- `REPLICATION_`

> Note: Under current statistics, all envKeys meeting the threshold are covered by the above prefixes, so no additional individual allowlist is needed.

---

## EnvKeys Meeting Threshold (reference)

| envKey | n | edit missing rate |
|---|---:|---:|
| REPLICATION_USER | 16 | 100.0% |
| REPLICATION_PASSWORD | 16 | 100.0% |
| MASTER_PORT | 11 | 100.0% |
| MASTER_HOST | 11 | 100.0% |
| PANEL_DB_TYPE | 35 | 97.1% |
| PANEL_DB_USER | 106 | 95.3% |
| PANEL_DB_NAME | 104 | 95.2% |
| PANEL_DB_USER_PASSWORD | 107 | 94.4% |
| PANEL_DB_ROOT_PASSWORD | 51 | 88.2% |
| PANEL_DB_ROOT_USER | 25 | 84.0% |
| PANEL_REDIS_ROOT_PASSWORD | 35 | 77.1% |
| PANEL_DB_HOST | 67 | 76.1% |
| REDIS_HOST | 10 | 70.0% |
