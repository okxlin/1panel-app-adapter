# Baota App Format Reference

This document describes the actual input format for Baota (宝塔) Docker Store application directories,
based on the public `aaPanel/apphub` repository format and aaPanel Docker app runtime source.

Verified public sources:

- `https://github.com/aaPanel/apphub` (`template.md`, `apphub/alist`, `apphub/deeplx`)
- `https://github.com/aaPanel/aaPanel` (`mod/project/docker/app/base.py`, `appManageMod.py`)

Note: `btpanel/apphub` was not publicly accessible during verification; use the public aaPanel apphub as the auditable format source unless the user provides private Baota apphub data.

## Intake Boundary

This reference describes the prepared directory consumed by `scripts/import-baota-app.py`. A live Baota/aaPanel market may instead expose catalog JSON and downloadable template archives. Those are acquisition inputs, not importer inputs.

Snapshot and safely extract live-market artifacts into task-owned prepared directories first. Reject archive path traversal and links that escape the staging root. Prepared required files, version directories, and Compose files must be regular non-symlink entries. The importer does not download URLs, parse a market-wide catalog, or extract archives. Follow `baota-migration-workflow.md` for the complete staged process.

## Directory Structure

### Single App Directory

```
<app-name>/
├── app.json              # Application metadata (required)
├── icon.png              # Application icon (required)
└── latest/               # Version directory (required)
    ├── docker-compose.yml # Docker Compose configuration (required)
    └── .env              # Environment variables (required)
```

### Multi-Version Directory

```
<app-name>/
├── app.json
├── icon.png
├── latest/
│   ├── docker-compose.yml
│   └── .env
└── 3.42.0/              # Additional version directory
    ├── docker-compose.yml
    └── .env
```

### Batch Directory (apphub)

```
apphub/
├── alist/
│   ├── app.json
│   ├── icon.png
│   └── latest/docker-compose.yml
└── adguardhome/
    ├── app.json
    ├── icon.png
    └── latest/docker-compose.yml
```

## app.json Specification

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `appid` | integer | Unique application identifier |
| `appname` | string | Application key name (lowercase, alphanumeric) |
| `apptitle` | string | Display title |
| `apptype` | string | Application type (see Type Mapping) |
| `appTypeCN` | string | Chinese type display name |
| `appversion` | array | Version entries (see Version Format) |
| `appdesc` | string | Application description |
| `appstatus` | integer | Status: 1=enabled, 0=disabled |
| `updateat` | integer | Unix timestamp (e.g. `1752027587`) — **NOT** a date string |
| `depend` | null or array | Dependencies (typically `null`, not `[]`) |
| `field` | array | Form field definitions |
| `env` | array | Environment variable definitions |
| `volumes` | object | Volume mount definitions — **object/map**, not array |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `home` | string | Project homepage URL (can be empty `""`) |
| `help` | string | Documentation/help URL |

### Version Format (appversion)

```json
{
  "appversion": [
    {
      "m_version": "latest",
      "s_version": []
    },
    {
      "m_version": "3",
      "s_version": ["42.0"]
    }
  ]
}
```

Version expansion rules:
- `m_version: "latest"` → candidate `"latest"`
- `m_version: "3"`, `s_version: ["42.0"]` → candidate `"3.42.0"`
- `m_version: "3"`, `s_version: ["42.0", "41.0"]` → candidates `"3.42.0"`, `"3.41.0"`

The array declares candidates; it does not define a trustworthy newest-version order. Each selected version must have a local directory and must be converted, qualified, strictly validated, and runtime-tested explicitly.

### Field Definition (field[])

```json
{
  "attr": "alist_web_port",
  "name": "web管理端口",
  "type": "number",
  "default": 15244,
  "suffix": "alist的web管理端口",
  "unit": ""
}
```

| Field | Description |
|-------|-------------|
| `attr` | Variable attribute name (lowercase, app-prefixed) |
| `name` | Display name (Chinese) |
| `type` | Field type: `number`, `string`, `textarea`, `checkbox`, `select` |
| `default` | Default value — **native JSON type** (bool `true`, int `15244`, string `""`) |
| `suffix` | Suffix/description text |
| `unit` | Unit label |

### Environment Variable Definition (env[])

```json
{
  "key": "alist_web_port",
  "type": "port",
  "default": null,
  "desc": "web管理端口"
}
```

| Field | Description |
|-------|-------------|
| `key` | Variable name (lowercase, app-prefixed) |
| `type` | Variable type: `"port"`, `"path"`, `"string"`, `"number"` |
| `default` | Default value — **`null`** when no default |
| `desc` | Description |

### Volume Definition (volumes)

Volumes is an **object/map** keyed by volume name, NOT an array:

```json
{
  "volumes": {
    "data": {
      "type": "path",
      "desc": "数据目录"
    },
    "mnt": {
      "type": "path",
      "desc": "挂载目录"
    }
  }
}
```

| Field | Description |
|-------|-------------|
| `<key>` | Volume name (used in compose path) |
| `type` | Volume type: `"path"` (directory) or `"file"` (single file) |
| `desc` | Description |

### Standard Platform Fields (field[])

These fields are standard Baota platform fields and will NOT be migrated as 1Panel form fields:

| attr | Purpose | Migration Handling |
|------|---------|-------------------|
| `domain` | Domain configuration | Written to migrationNotes, not formFields |
| `allow_access` | External access toggle | Used for HOST_IP semantics, written to migrationNotes |
| `cpus` | CPU limit | Removed from deploy.resources, written to migrationNotes |
| `memory_limit` | Memory limit | Removed from deploy.resources, written to migrationNotes |

### Standard Platform Environment Variables (env[])

| key | Purpose | Migration Handling |
|-----|---------|-------------------|
| `app_path` | Application root path | `${APP_PATH}` bind-mount sources become configurable `APP_DATA_DIR*` form fields |
| `host_ip` | Host IP address | Mapped to HOST_IP, port bindings converted to PANEL_APP_PORT_* |
| `cpus` | CPU limit | Mapped to CPUS, removed from deploy.resources |
| `memory_limit` | Memory limit | Mapped to MEMORY_LIMIT, removed from deploy.resources |

## Docker Compose Format

Baota/aaPanel docker-compose.yml typically includes:

- `services.<name>.image` — Docker image reference
- `services.<name>.ports` — Port mappings using `${HOST_IP}:${PORT}:containerPort`
- `services.<name>.volumes` — Volume mappings using `${APP_PATH}/...`
- `services.<name>.networks` — Reference to `baota_net`
- `services.<name>.labels.createdBy` — Set to `"bt_apps"`
- `services.<name>.deploy.resources.limits` — CPU/memory limits using `${CPUS}`, `${MEMORY_LIMIT}`
- `networks.baota_net.external: true` — External network definition

The aaPanel runtime checks for `baota_net` and creates it when missing before app installation. Imported 1Panel artifacts should not require that Baota-specific network name; the importer rewrites it to `1panel-network`.

## Environment File (.env)

Standard KEY=VALUE format:

```
ALIST_WEB_PORT=
S3_SERVER_PORT=
HOST_IP=
CPUS=
MEMORY_LIMIT=
APP_PATH=
```

- Lines starting with `#` are comments (ignored)
- Blank lines are skipped
- Variable names are typically UPPERCASE (but env[] key fields are lowercase)
- Values may be empty (common for port/host variables)
- Field names often use app-specific prefixes: `alist_web_port`, `ag_web_port`
