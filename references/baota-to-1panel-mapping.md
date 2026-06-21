# Baota to 1Panel Mapping Reference

This document defines the complete mapping rules from Baota Docker Store app format to 1Panel v2 app format.

## Metadata Mapping

| Baota Field | 1Panel Field | Notes |
|-------------|-------------|-------|
| `appname` | `appKey` | Lowercase, used as directory name |
| `apptitle` | `title` | Display title |
| `appdesc` | `description` | Short description |
| `apptype` | `type` | See type mapping table below |
| `appTypeCN` | Tag candidate | Used to suggest a tag |
| `home` | `website` / `github` / `repository` | URL classification |
| `help` | `document` / `dockerDocs` | URL classification |
| `appversion` | Version candidates | Expanded per version rules |
| `icon.png` | `logo.png` | Copied, optionally normalized |

## App Type Mapping

| Baota `apptype` | 1Panel `type` |
|----------------|---------------|
| `BuildWebsite` | `Website` |
| `Database` | `Database` |
| `Storage` | `Storage` |
| `Tools` | `Tool` |
| `Middleware` | `Middleware` |
| `AI` | `AI` |
| `Media` | `Media` |
| `Email` | `Email` |
| `DevOps` | `DevOps` |
| `System` | `Tool` |
| Unknown | `Tool` (with warning) |

## Field Type Mapping

| Baota `field.type` | 1Panel `formFields.type` | Additional |
|-------------------|------------------------|------------|
| `number` | `number` | — |
| `string` | `text` | — |
| `textarea` | `text` | — |
| `checkbox` | `select` | values: true/false |
| `select` | `select` | — |
| `path` | `text` | — |
| `port` | `number` | `rule: paramPort` |
| `password` / key | `password` | — |

## Field to FormField Mapping

| Baota `field[]` | 1Panel `formFields[]` |
|----------------|---------------------|
| `attr` | `envKey` candidate |
| `name` | `labelZh` |
| `type` | `type` (mapped) |
| `default` | `default` |
| `suffix` | `description` |
| `unit` | Appended to description |

## Env to FormField Mapping

| Baota `env[]` | 1Panel `formFields[]` |
|--------------|---------------------|
| `key` | `envKey` candidate (uppercased) |
| `desc` | `labelZh` |
| `default` | `default` |

## Compose Transformation Rules

### Ports

**Baota input:**
```yaml
ports:
  - ${HOST_IP}:${WEB_PORT}:5244
```

**1Panel output:**
```yaml
ports:
  - ${PANEL_APP_PORT_HTTP}:5244
```

Port naming rules:
- First HTTP/Web port → `PANEL_APP_PORT_HTTP`
- HTTPS port → `PANEL_APP_PORT_HTTPS`
- Other ports → `PANEL_APP_PORT_<SERVICE>_<CONTAINER_PORT>`

### Volumes

**Baota input (path type):**
```yaml
volumes:
  - ${APP_PATH}/data:/app/data
```

**1Panel output:**
```yaml
volumes:
  - ${APP_DATA_DIR}:/app/data
```

When the source app has multiple `${APP_PATH}/<name>` mount roots, the importer generates one directory field per root:

```yaml
volumes:
  - ${APP_DATA_DIR_DATA}:/opt/alist/data
  - ${APP_DATA_DIR_MNT}:/mnt/data
```

The matching version `data.yml` form fields default to `./data/data`, `./data/mnt`, etc. The converter only rewrites the compose volume source side and preserves the container target path and optional mode.

**Baota input (file type):**
```yaml
volumes:
  - ${APP_PATH}/config.yml:/app/config.yml
```

**1Panel output:**
```yaml
# File volume: config.yml → /app/config.yml
# Requires manual review for config file content
volumes:
  - ${APP_DATA_DIR}/config.yml:/app/config.yml
```

### Networks

**Baota input:**
```yaml
networks:
  - baota_net

networks:
  baota_net:
    external: true
```

**1Panel output:**
```yaml
networks:
  - 1panel-network

networks:
  1panel-network:
    external: true
```

### Labels

**Baota input:**
```yaml
labels:
  createdBy: "bt_apps"
```

**1Panel output:**
```yaml
labels:
  createdBy: "Apps"
```

If no labels exist, add `createdBy: "Apps"`.

### Container Name

**Primary service:**
```yaml
container_name: ${CONTAINER_NAME}
```

**Secondary services:**
```yaml
container_name: ${CONTAINER_NAME}-<service-name>
```

### Resource Limits

Baota `deploy.resources.limits` referencing `${CPUS}` or `${MEMORY_LIMIT}` are removed entirely. The resource limitation is noted in `migrationNotes` and the import report.

### Preserved Fields

The following Compose fields are preserved unchanged during transformation:
- `image`
- `restart`
- `environment`
- `env_file`
- `command`
- `entrypoint`
- `depends_on`
- `healthcheck`
- `extra_hosts`
- `privileged`
- `cap_add`
- `devices`
- `user`
- `working_dir`
- `logging`

## Evidence Level Mapping

| Condition | Evidence Level |
|-----------|---------------|
| Both `home` and `help` resolve to known official sources | `official_complete` |
| One of `home` or `help` resolves to known official source | `official_partial` |
| Neither resolves to recognized official pattern | `third_party_only` |
| Multi-service, complex config, or scripts requiring manual assessment | `manual_review_required` |
