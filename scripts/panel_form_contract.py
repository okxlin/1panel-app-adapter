"""Structural eligibility for service-derived variables shared by v1 and v2.

See references/panel-compatibility.md. A selector proves the intended input
path, not that a live database record resolved or that provisioning succeeded.
"""

DATABASE_KEYS = frozenset({"mysql", "mariadb", "postgresql"})


def service_derived_envkeys(metadata: dict) -> set[str]:
    properties = metadata.get("additionalProperties")
    if not isinstance(properties, dict):
        return set()
    fields = properties.get("formFields")
    if not isinstance(fields, list):
        return set()
    hosts = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        if field.get("envKey") == "PANEL_DB_HOST":
            hosts.append((field, None))
        child = field.get("child")
        if isinstance(child, dict) and child.get("envKey") == "PANEL_DB_HOST":
            hosts.append((child, field))
    if len(hosts) != 1:
        return set()
    host, parent = hosts[0]
    if host.get("type") != "service" or host.get("required") is not True:
        return set()
    if parent is None:
        eligible = isinstance(host.get("key"), str) and host["key"] in DATABASE_KEYS
    else:
        values = parent.get("values")
        eligible = (parent.get("type") == "apps" and parent.get("envKey") == "PANEL_DB_TYPE"
                    and parent.get("required") is True and isinstance(values, list) and bool(values))
        if eligible:
            keys = [item.get("value") if isinstance(item, dict) else None for item in values]
            eligible = all(isinstance(key, str) and key in DATABASE_KEYS for key in keys)
            eligible = eligible and parent.get("default") in keys
    return {"PANEL_DB_PORT"} if eligible else set()
