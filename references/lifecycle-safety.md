# Lifecycle Safety Contract

Apply this contract to every generated, migrated, imported, updated, or reviewed package. Structural validation cannot prove these application semantics. Resolve each item from official sources and the exact artifact before claiming delivery readiness.

## 1. Build the path and mount ledger first

Record one row for every bind mount and named volume before writing lifecycle scripts:

| Required field | Record |
| --- | --- |
| host source | The exact package-relative path, named volume, or documented external source. |
| container target | The exact path and whether the application reads, writes, or initializes it. |
| file or directory | The required source type; do not infer it from a filename alone. |
| runtime UID/GID | The source-backed writer/reader identity for the exact published image. |
| creation | Which packaged file or lifecycle step creates the exact source before Compose starts. |
| ownership | The smallest path whose owner or mode must change, with the source-backed identity. |
| upgrade | Whether the path is retained, migrated, regenerated, or validated. |
| uninstall | Whether 1Panel removes it or intentionally preserves user data. |

Keep this ledger in the adaptation report or delivery evidence; do not add process-only evidence to the AppStore artifact unless the target repository expects it. Stop when a required row contains an assumption that affects startup, persistence, security, or upgrade safety.

## 2. Prove the runtime identity

- Determine the effective runtime user from the exact published image's OCI `Config.User` and any explicit Compose `user`. Inspect the fresh image by immutable digest when possible and record the command/result without leaking registry credentials.
- Treat an empty OCI `Config.User` with no Compose override as root. Do not claim a non-root runtime merely because a Dockerfile creates a user, changes ownership, or describes an intended UID/GID.
- When Compose overrides `user`, verify that the selected UID/GID can execute the image entrypoint, read required configuration, and write every writable mount.
- Do not add `chown` for a guessed identity. If the image is intentionally root, preserve that upstream behavior unless verified hardening proves the full application workflow still works.
- For every non-root writable bind mount, create the host directory with a source-backed ownership/permission plan before startup. A root-created `0755` directory is not writable by an arbitrary non-root container user.

## 3. Confine every host path

- Prefer fixed package-local defaults such as `./data`, `./config`, and `./certs/app.p12`. Expose a custom host path only when the upstream contract or user requirement needs it.
- Treat `.env` and form values as untrusted. Parse only exact known keys; never `source` or `eval` the file.
- Reject empty values, absolute paths, bare `.` or `..`, `..` traversal, newline/control characters, and symbolic links in the target or any existing parent component.
- Resolve the candidate canonically from the version root before `mkdir`, `touch`, `install`, `chmod`, `chown`, copy, move, or deletion. Require the resolved target to equal the version root or start with `<version-root>/`; for persistent data, normally require a child rather than the root itself.
- Reject on any resolution error. Do not fall back to the raw path, the process working directory, `/`, or a home directory.
- Use `scripts/finalize_runtime_scripts.sh` only as a safe baseline. Review the generated script against the ledger and replace generic handling when the application needs ownership changes, exact file generation, or application-specific validation.

The generated helper intentionally accepts package-local relative paths only. Keep equivalent checks in hand-written scripts:

```bash
resolve_confined_path() {
  local key="$1" raw="$2" candidate resolved
  case "$raw" in
    ""|/*|.|..|../*|*/../*|*/..) echo "unsafe ${key} path" >&2; return 1 ;;
  esac
  candidate="$ROOT_DIR/${raw#./}"
  resolved="$(realpath -m -- "$candidate")" || return 1
  case "$resolved" in
    "$ROOT_DIR"/*) printf '%s\n' "$resolved" ;;
    *) echo "unsafe ${key} path" >&2; return 1 ;;
  esac
}
```

This lexical/canonical boundary check does not by itself authorize ownership changes. Also reject symbolic links and recheck the resolved target immediately before each mutation to reduce time-of-check/time-of-use exposure.

## 4. Bound ownership and permission changes

- Avoid recursive `chown`. Prefer creating the exact known directories with `install -d -o <uid> -g <gid> -m <mode>` or changing only newly created paths.
- If recursion is unavoidable, first prove the target is package-local, reject symbolic links, re-resolve the boundary, stay on one filesystem when practical, and use `--no-dereference` (plus `--preserve-root` where supported). Record why every descendant belongs to the application.
- Never run `chown -R`, `chmod -R`, deletion, or copy operations on an arbitrary absolute/form path, the version root, `/`, a home directory, or a path accepted after only checking that it is not `/`.
- Do not use `chmod 777` as an ownership substitute. Preserve the narrowest mode that the application and its backup/upgrade flow require.
- Run lifecycle tests with the same effective runtime UID/GID as the delivered Compose, not merely as root.

## 5. Distinguish file binds from directory binds

- For every file bind, create or validate the exact source file before Compose starts. Creating only its parent directory is insufficient; Docker can create a missing bind source as a directory and the container then receives the wrong type.
- For a packaged static file, ship the file at the exact relative path. For a generated file, write to a same-directory temporary file, validate its format and permissions, then atomically rename it into place.
- For a user-supplied file, fail initialization when the source is missing, is a directory, is a symbolic link, has the wrong format, or is unreadable by the runtime identity.
- Validate application-specific material, not only the extension. Examples include a parseable PKCS#12 certificate with the matching stable passphrase, a PEM key with the required type, and a non-empty SQL initialization file.
- On clean install, inspect the mounted object inside the container and exercise the feature that consumes it.

## 6. Generate and preserve secrets correctly

- Derive every secret contract from official documentation or source: byte length, encoded length, alphabet/encoding, prefix, checksum, and whether empty is allowed. A generic random form flag does not prove the application's exact format.
- Use a cryptographically secure generator and validate the result before writing it. For example, distinguish 32 random bytes encoded as Base64 from a 32-character string; they are not equivalent.
- Generate an install secret once, persist it atomically in the intended state file, and keep it stable across upgrades and restarts. Do not silently regenerate encryption keys, signing passwords, session secrets, or database credentials.
- Keep real secrets out of `.env.sample`, reports, logs, commits, and command output. Use explicit placeholders in samples.
- If a credential must appear inside a connection URL, URL-encode each username/password component with a standard encoder before assembling the URL. Prefer separate upstream variables when supported. Do not interpolate raw random credentials into a URL.
- Validate coupled values together: a PKCS#12 path and passphrase, an encryption key and its format, or database credentials and the resulting connection URL.

## 7. Preserve lifecycle behavior

- Make initialization idempotent. Do not overwrite user state, rotate stable secrets, or replace user-modified configuration on restart or upgrade.
- Define clean-install, restart, direct-upgrade, backup/restore, and uninstall behavior for every ledger row. Treat unknown database major-version transitions and irreversible migrations as blockers until tested.
- Exercise an application-specific ready path. A running container, healthy status, open TCP port, or generic HTTP `200` alone is not sufficient.
- Test the exact delivered files in a real 1Panel development/test instance. Verify the file/directory types, ownership and modes on the host and in the container before and after restart and upgrade.

## 8. Keep topology gates terminal

Selecting an AIO image does not satisfy a `specialized_conditional` route. Keep the route stopped until every recorded process-supervision, proxy/TLS, stateful dependency, migration, upgrade, backup/restore, and uninstall prerequisite has direct evidence. If the application is a platform stack whose lifecycle cannot be represented safely by an ordinary AppStore package, retain `platform_stack_terminal` and report the evidence instead of scaffolding.

## Delivery checklist

Before a pass claim, answer all items with evidence:

1. Does every mount have a complete path and mount ledger row?
2. Does runtime UID/GID come from OCI `Config.User` or an explicit Compose `user` for the exact image?
3. Are all mutable host paths package-local, confined, non-symlink, and rechecked before mutation?
4. Is each ownership change minimal, source-backed, and protected against traversal and dereference?
5. Does every file bind have the exact source file before Compose starts?
6. Does every generated secret match the application's exact format and remain stable across upgrades?
7. Are credentials URL-encoded when embedded in URLs?
8. Do clean install, readiness, restart, upgrade, uninstall, and cleanup evidence cover the actual application behavior?

Any unresolved item blocks a runtime-ready or delivery-ready claim even when structural, strict-store, i18n, environment-closure, and Compose-render checks pass.
