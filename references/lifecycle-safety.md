# Lifecycle Safety Contract

Apply this contract to every generated, migrated, imported, updated, or reviewed package. Structural validation cannot prove these application semantics. Resolve each item from official sources and the exact artifact before claiming delivery readiness.

## Contents

1. Build the startup configuration contract first
2. Build the path and mount ledger
3. Prove the runtime identity
4. Confine every host path
5. Bound ownership and permission changes
6. Distinguish file binds from directory binds
7. Generate and preserve secrets correctly
8. Preserve lifecycle behavior
9. Keep topology gates terminal
10. Complete the delivery checklist

## 1. Build the startup configuration contract first

Do not treat the selected official Compose as exhaustive. At the exact target version, inspect
every available exact-version authority among the official install examples, configuration
reference, image environment/defaults, entrypoint, and startup source before scaffolding or
approving an existing artifact. Record unavailable authorities; no single source type is mandatory
when it does not exist or is not published. Search the available authorities for required settings
and startup failure paths, including values absent from the example Compose. Prove the consumer and
startup behavior from source or exact-image/runtime evidence. Missing consumer or startup proof,
or an unresolved conflict between available authorities, blocks delivery.

Record one row for every required, startup-fatal, stability-bearing, or coupled input for the
selected topology. Include a selected or default-dependent optional input only when the selected
topology uses it or its effective default changes startup or usability:

| Required field | Record |
| --- | --- |
| key or input | The exact environment variable, flag, file, or generated value consumed by the application. |
| evidence | The exact-version official install, configuration, image, entrypoint, or startup source location. |
| requirement | Whether it is required or optional, when empty is allowed, and which default applies at which layer. |
| consumer | The service and startup stage that reads the value. |
| validation rule | Every length, alphabet, encoding, path, enum, coupling, or fatal startup check. |
| secret handling | Whether it is secret, who generates it, and how its real value stays out of samples and reports. |
| stability | Whether it must remain stable across restarts and upgrades, and which state preserves it. |
| delivery mapping | Its final Compose, `data.yml`, `.env.sample`, packaged file, or lifecycle logic location. |

For each required value, establish one reviewed source of truth and project it through every
required artifact layer. A required value absent from an upstream sample Compose is still required.
If 1Panel or a lifecycle step generates it, prove the generated value satisfies the application
validation rule and is persisted when stability is required. Use an explicit non-secret placeholder
in `.env.sample` that satisfies static format checks without presenting it as a production secret.

Treat a form schema edit as a contract migration. Whenever `envKey`, `label`, or `type` changes,
re-review the sibling `default`, `rule`, and `values` instead of carrying them over from the old
field. For every top-level form field actually consumed by Compose, require a non-empty `data.yml`
default to match the `.env.sample` value after removing one pair of surrounding quotes and
normalizing YAML booleans to lowercase `true` or `false`. An empty form default may use a non-empty
sample placeholder because `.env.sample` supports standalone Compose rather than supplying the
1Panel install value. Exclude fields with type password, `apps`, `service`, or `random: true` from
this equality rule because their sample values and panel-generated values intentionally have
different roles. Still verify each excluded field against its own source-backed startup contract.
A Compose render does not prove that the panel default passes application startup validation;
trace the submitted default to the exact application consumer and its validation rule.

For each form field, record both its install-time and steady-state consumer before setting `edit`.
Use `edit: false` when a value is generated once, identity-bearing, or copied into persistent
configuration that later starts bypass. Allow edits only when the steady-state consumer reads the
new value directly or an idempotent reconciliation or migration updates the real persisted state.
Changing `.env` while leaving an older persisted value active is a broken control and blocks
delivery; documentation that warns users about the mismatch does not make the field editable.

`required: true` or a generic `paramComplexity` rule does not prove application-specific validation.
For user-provided values, use a source-backed panel rule only when it enforces the complete upstream
contract; otherwise add reviewed generation or validation that rejects invalid input before Compose
starts. If the target package cannot enforce a required format before application startup, the
unresolved input blocks delivery.

Derive and enforce source-backed cross-field constraints, not only each field's standalone syntax.
Examples include two domains that must differ, a certificate that must match a key, or a path and
secret that must be supplied together. Exercise both accepted and rejected combinations before
claiming the generated configuration is valid. When a lifecycle script writes values into a
template, treat each validated value as literal data rather than as a regular-expression or
replacement program. Use a structured serializer or a literal-safe substitution method; otherwise
restrict the accepted characters to the exact source-backed grammar and test replacement-sensitive
characters such as `&` and backslash.

Trace each delivered value to its actual consumer and startup validation. When official examples
and startup enforcement disagree, follow the exact-version startup enforcement and record the
conflict. A successful Compose render proves interpolation and structure, not that the application
accepts its startup configuration. A missing, guessed, invalid, or silently rotating required
value blocks delivery even when schema, environment-closure, and Compose checks pass.

## 2. Build the path and mount ledger

Record one row for every bind mount and named volume before writing lifecycle scripts:

| Required field | Record |
| --- | --- |
| host source | The exact package-relative path, named volume, or documented external source. |
| mount mechanism | `bind`, named volume, or external source, plus the official evidence for that mechanism. |
| mount options | Preserve source/target syntax, read/write mode, propagation, and security options such as `ro`, `rw`, and SELinux `z`/`Z`; justify every change. |
| container target | The exact path and whether the application reads, writes, or initializes it. |
| file or directory | The required source type; do not infer it from a filename alone. |
| operator access | Whether official setup, host-side editing, backup, restore, or support procedures require direct host access. |
| runtime UID/GID | The source-backed startup and steady-state writer/reader identities for the exact published image. |
| creation | Which packaged file or lifecycle step creates the exact source before Compose starts. |
| ownership | The smallest path whose owner or mode must change, with the source-backed identity. |
| upgrade | Whether the path is retained, migrated, regenerated, or validated. |
| uninstall | Whether 1Panel removes it or intentionally preserves user data. |

Keep this ledger in the adaptation report or delivery evidence; do not add process-only evidence to the AppStore artifact unless the target repository expects it. Stop when a required row contains an assumption that affects startup, persistence, security, or upgrade safety.

Treat source, target, read/write mode, propagation, and security options in authoritative Compose
as required delivery defaults. Preserve them exactly. Change a mount default only when target-platform documentation or runtime evidence proves it incompatible and the reviewed replacement preserves
the same access, isolation, and labeling contract. Host-policy variability or an option being "not proven necessary" is not evidence to remove an official default such as SELinux `z`/`Z`.

Preserve the authoritative source-backed mount mechanism as a required delivery default, including
its operator-access contract. A named
volume is not a drop-in replacement for an official configuration bind when the documented setup,
host-side editing, backup, restore, or support flow uses that host path. In that case, keep a fixed
package-local bind such as `./config` unless the user explicitly requires a selectable path. Do not
add an `APP_DATA_DIR` form merely to make a fixed package-local bind configurable. Do not convert an
authoritative bind to a named volume merely because direct host access appears unnecessary or the
lifecycle seems equivalent. Apply the same target-platform incompatibility and equivalent-replacement
gate before changing the mount mechanism.

## 3. Prove the runtime identity

- Record startup identity separately from steady-state identity. Determine the startup identity from the exact published image's OCI `Config.User` and any explicit Compose `user`; then inspect the verified entrypoint/process behavior for any privilege drop before claiming the steady-state UID/GID. Inspect the fresh image by immutable digest when possible and record the command/result without leaking registry credentials.
- For each selected service with a writable bind, encode the result in that service's `source-evidence.json` `runtimeIdentity`: numeric `startupUid`, `startupGid`, `steadyStateUid`, `steadyStateGid`, an exact-version HTTPS `source`, and one `writableBindOwner` policy. Use `host-init` for generated host ownership, `image-managed` only with HTTPS `ownerEvidence` for the entrypoint behavior, or `root-runtime` only for steady UID 0. Strict delivery validation matches non-root `host-init` records to the exact generated helper invocation for every bind.
- Treat an empty OCI `Config.User` with no Compose override as root startup identity. An official entrypoint may later initialize ownership and drop privileges, but prove that from the exact entrypoint and runtime process. Do not claim a non-root steady-state identity merely because a Dockerfile creates a user, changes ownership, or describes an intended UID/GID.
- When Compose overrides `user`, verify that the selected UID/GID can execute the image entrypoint, read required configuration, and write every writable mount.
- Do not add `chown` for a guessed identity. If the image is intentionally root, preserve that upstream behavior unless verified hardening proves the full application workflow still works.
- For every non-root writable bind mount, create the host directory with a source-backed ownership/permission plan before startup. A root-created `0755` directory is not writable by an arbitrary non-root container user.

### Non-root writable bind decision procedure

Use this sequence for every mount that a non-root process must write. Do not skip from a
proven UID/GID directly to `mkdir -p`.

1. When the selected authoritative deployment uses a named volume, preserve its mechanism,
   name/target, operator-access contract, and lifecycle semantics; do not add an `APP_DATA_DIR`
   form merely to replace it with a bind mount.
2. When the selected authoritative deployment uses a bind, record the exact source-backed numeric UID, GID, and narrowest
   usable directory mode. Regenerate the confined init script explicitly after reviewing any
   existing customization:

   ```bash
   bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir> \
     --dir-owner APP_DATA_DIR=<uid>:<gid>:0750 --replace-init

   bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir> \
     --fixed-dir-owner ./config=<uid>:<gid>:0750 --replace-init
   ```

   Use `--dir-owner` for a selectable path backed by a form field. Use `--fixed-dir-owner` for a
   fixed package-local bind without a form field. Repeat the relevant option for independently
   writable directories. The helper rejects unknown path fields, non-local or nested fixed paths,
   non-numeric identities, non-octal modes, owner modes without `rwx`, and duplicate entries. It
   accepts only a direct child beneath a root-owned parent chain that is not writable by group or
   others, requires root for the ownership step, and never performs recursive `chown` or `chmod`.
   Nested bind sources require an upstream named volume or an independently audited,
   descriptor-based initializer; pathname prechecks alone do not close symlink-swap races.
3. Run the exact `init.sh`, inspect the resulting directory with `stat`, and run a write probe as
   the delivered runtime UID/GID (for example with `setpriv` on a disposable clean directory).
   A root-only write test is insufficient. Record the commands and results, not an intended mode.
4. If neither a source-backed named volume nor a verified bind ownership plan is available, the
   unresolved writable mount blocks delivery. Do not claim that a mode or owner was applied when
   the exact delivered script does not apply and verify it.

## 4. Confine every host path

- Prefer fixed package-local defaults such as `./data`, `./config`, and `./certs/app.p12`. Expose a custom host path only when the upstream contract or user requirement needs it.
- Treat `.env` and form values as untrusted. Parse only exact known keys; never `source` or `eval` the file.
- Reject empty values, absolute paths, bare `.` or `..`, `..` traversal, newline/control characters, and symbolic links in the target or any existing parent component.
- Resolve the candidate canonically from the version root before `mkdir`, `touch`, `install`, `chmod`, `chown`, copy, move, or deletion. Require the resolved target to equal the version root or start with `<version-root>/`; for persistent data, normally require a child rather than the root itself.
- Reject on any resolution error. Do not fall back to the raw path, the process working directory, `/`, or a home directory.
- Use `scripts/finalize_runtime_scripts.sh` only as a safe baseline for explicit directories. `--dir-owner` accepts only an environment key with an independent `DIR` segment (for example `APP_DATA_DIR` or `APP_DATA_DIR_CACHE`) or a default ending in `/`; `--fixed-dir-owner` accepts only a fixed package-local direct child. The helper refuses every other path because a name or extension cannot prove the mount type. Implement exact file creation/validation in application-specific code.
- Do not replace the generated confinement when customizing a directory path. Preserve its environment-key validation, control/absolute/traversal rejection, canonical version-root boundary, and symbolic-link rejection. For ownership changes, also preserve the direct-child restriction and trusted-parent-chain check.

The generated helper intentionally accepts package-local relative paths only. Keep equivalent checks in hand-written scripts:

```bash
resolve_confined_path() {
  local key="$1" raw="$2" clean candidate resolved current part
  local -a parts=()
  case "$raw" in
    ""|/*|.|..|../*|*/../*|*/..) echo "unsafe ${key} path" >&2; return 1 ;;
  esac
  [[ ! "$raw" =~ [[:cntrl:]] ]] || { echo "unsafe ${key} path" >&2; return 1; }
  clean="${raw#./}"
  candidate="$ROOT_DIR/$clean"
  resolved="$(realpath -m -- "$candidate")" || return 1
  case "$resolved" in
    "$ROOT_DIR"/*) ;;
    *) echo "unsafe ${key} path" >&2; return 1 ;;
  esac
  current="$ROOT_DIR"
  IFS='/' read -r -a parts <<< "$clean"
  for part in "${parts[@]}"; do
    [[ -z "$part" || "$part" == "." ]] && continue
    current="$current/$part"
    [[ ! -L "$current" ]] || { echo "unsafe ${key} path" >&2; return 1; }
  done
  printf '%s\n' "$resolved"
}
```

This lexical/canonical boundary check does not by itself authorize ownership changes. Also reject symbolic links and recheck the resolved target immediately before each mutation to reduce time-of-check/time-of-use exposure.

Test custom path logic with a normal direct-child path, a nested path, an absolute path, parent traversal, an inside-root symbolic link, and an outside-root symbolic link. Ordinary directory creation may accept a confined nested path; ownership changes must reject it. Require rejection for both symlink cases; resolving a symlink back inside the version root does not make it an approved package path.

## 5. Bound ownership and permission changes

- Avoid recursive `chown`. For a direct child under a trusted parent chain, create and change only that exact directory and use a non-dereferencing ownership operation. Use a descriptor-relative initializer when a mutable or nested parent cannot be excluded.
- If recursion is unavoidable, first prove the target is package-local, reject symbolic links, re-resolve the boundary, stay on one filesystem when practical, and use `--no-dereference` (plus `--preserve-root` where supported). Record why every descendant belongs to the application.
- Never run `chown -R`, `chmod -R`, deletion, or copy operations on an arbitrary absolute/form path, the version root, `/`, a home directory, or a path accepted after only checking that it is not `/`.
- Do not use `chmod 777` as an ownership substitute. Preserve the narrowest mode that the application and its backup/upgrade flow require.
- Run lifecycle tests with the same effective runtime UID/GID as the delivered Compose, not merely as root.

## 6. Distinguish file binds from directory binds

- For every file bind, create or validate the exact source file before Compose starts. Creating only its parent directory is insufficient; Docker can create a missing bind source as a directory and the container then receives the wrong type.
- For a packaged static file, ship the file at the exact relative path. For a generated file, write to a same-directory temporary file, validate its format and permissions, then atomically rename it into place.
- For a user-supplied file, fail initialization when the source is missing, is a directory, is a symbolic link, has the wrong format, or is unreadable by the runtime identity.
- Validate application-specific material, not only the extension. Examples include a parseable PKCS#12 certificate with the matching stable passphrase, a PEM key with the required type, and a non-empty SQL initialization file.
- On clean install, inspect the mounted object inside the container and exercise the feature that consumes it.

## 7. Generate and preserve secrets correctly

- Derive every secret contract from official documentation or source: byte length, encoded length, alphabet/encoding, prefix, checksum, and whether empty is allowed. A generic random form flag does not prove the application's exact format.
- Use a cryptographically secure generator and validate the result before writing it. For example, distinguish 32 random bytes encoded as Base64 from a 32-character string; they are not equivalent.
- Generate an install secret once, persist it atomically in the intended state file, and keep it stable across upgrades and restarts. Do not silently regenerate encryption keys, signing passwords, session secrets, or database credentials.
- Keep real secrets out of `.env.sample`, reports, logs, commits, and command output. Use explicit placeholders in samples.
- Treat every connection string as a grammar, not plain text. Prefer separate upstream variables. If a credential must appear inside a connection URL, URL-encode each username/password component with a standard encoder before assembling the URL. For a keyword/value DSN, quote and escape each credential with the official parser's rules or restrict generation to a source-backed safe alphabet and validate it. Do not interpolate arbitrary random credentials raw into any connection string.
- Validate coupled values together: a PKCS#12 path and passphrase, an encryption key and its format, or database credentials and the resulting connection URL.

## 8. Preserve lifecycle behavior

- Make initialization idempotent. Do not overwrite user state, rotate stable secrets, or replace user-modified configuration on restart or upgrade.
- Define clean-install, restart, direct-upgrade, backup/restore, and uninstall behavior for every ledger row. Treat unknown database major-version transitions and irreversible migrations as blockers until tested.
- Make lifecycle scripts independent of the caller's working directory: resolve the version directory from the script path, then either change to it before Compose commands or pass an equivalent absolute project/Compose path. Preserve bind data and persistent named volumes by default; use `down --volumes` only when the ledger proves every affected volume is package-owned, disposable, and approved for deletion.
- Match 1Panel's Compose command selection: probe `docker compose version` first, then fall back
  to `docker-compose version` when only the supported legacy binary is installed. Fail clearly when
  neither command exists. This order follows `1Panel-dev/1Panel` commit
  `16e3d496ebc4eae6637ce63f17149c6928469af1`.

  ```bash
  if docker compose version >/dev/null 2>&1; then
    docker compose down
  elif docker-compose version >/dev/null 2>&1; then
    docker-compose down
  else
    echo "Docker Compose is not available" >&2
    exit 1
  fi
  ```

- Exercise an application-specific ready path. A running container, healthy status, open TCP port, or generic HTTP `200` alone is not sufficient.
- Test the exact delivered files in a real 1Panel development/test instance. Verify the file/directory types, ownership and modes on the host and in the container before and after restart and upgrade.
- Report an observed owner or mode as an observation tied to the invoking UID/GID and umask. Claim a portable guarantee only when the delivered lifecycle script explicitly enforces that owner or mode and the exact-artifact test verifies it. A host observation alone does not prove behavior under another panel user, filesystem, or umask.

## 9. Keep topology gates terminal

Selecting an AIO image does not satisfy a `specialized_conditional` route. Keep the route stopped until every recorded process-supervision, proxy/TLS, stateful dependency, migration, upgrade, backup/restore, and uninstall prerequisite has direct evidence. If the application is a platform stack whose lifecycle cannot be represented safely by an ordinary AppStore package, retain `platform_stack_terminal` and report the evidence instead of scaffolding.

## 10. Delivery checklist

Before finalizing the README or adaptation report, build a configuration claim ledger. For every
configuration statement, record the key or control, classify it as fixed, defaulted, generated,
optional, or user-configurable, and point to the delivered artifact that enforces that
classification. Compare every report claim against the exact Compose, `data.yml`, `.env.sample`,
and lifecycle scripts instead of copying an earlier plan or upstream description.

If a value has an editable form field, describe it as user-configurable with a default of the
delivered value, not as fixed. Keep application defaults, package defaults, sample placeholders,
generated install values, and runtime observations distinct. A report/README contradiction blocks
a delivery-ready claim even when the artifact itself is structurally valid.

Before a pass claim, answer all items with evidence:

1. Does every required startup value have a complete startup configuration contract row and a verified final-artifact mapping?
2. Do `init.sh`, `upgrade.sh`, and `uninstall.sh` exist and retain executable mode in the delivered tree?
3. Does every mount have a complete path and mount ledger row?
4. Are startup and steady-state runtime UID/GID separately proven from OCI/Compose and verified entrypoint/process behavior?
5. Are all mutable host paths package-local, confined, non-symlink, and rechecked before mutation?
6. Is each ownership change minimal, source-backed, and protected against traversal and dereference?
7. Does every file bind have the exact source file before Compose starts?
8. Does every generated secret match the application's exact format and remain stable across upgrades?
9. Are credentials URL-encoded or otherwise escaped with the exact connection-string grammar?
10. Do clean install, readiness, restart, upgrade, uninstall, and cleanup evidence cover the actual application behavior?
11. Does every Compose lifecycle command target the intended version directory without relying on the caller's working directory, and does uninstall preserve persistent volumes unless their deletion is explicitly proven safe?
12. Does the configuration claim ledger match every delivered control and avoid calling an editable or generated value fixed?

Any unresolved item blocks a runtime-ready or delivery-ready claim even when structural, strict-store, i18n, environment-closure, and Compose-render checks pass.
