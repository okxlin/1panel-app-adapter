# PHP runtime adaptation

Use this guide when adapting a PHP runtime package for 1Panel, or when replacing a legacy package such as `php-unofficial` with a real PHP runtime.

## Source-backed rules

These rules were verified against local 1Panel source and the official `1Panel-dev/appstore` PHP package:

- The PHP runtime picker filters apps by `type: php`, not by a generic runtime/tool type.
- The runtime create/detail flow still loads version detail through the runtime app-detail path.
- Runtime creation injects `PANEL_WEBSITE_DIR`, forces localhost-only FPM publish form (`127.0.0.1:${PANEL_APP_PORT_HTTP}:9000`), adds the default PHP runtime volumes, and manages `PHP_EXTENSIONS` as part of the runtime build/install flow.
- For PHP runtimes, `buildRuntimeWithResult()` does not finish at `docker compose build`: it builds, starts the container, runs `docker exec <container> install-ext <extensions>`, commits the container to the final runtime image, then restarts from that committed image.

Relevant source anchors used during validation:

- `frontend/src/views/website/runtime/php/create/index.vue`
- `agent/app/repo/app.go`
- `agent/app/service/app.go`
- `agent/app/service/runtime_utils.go`
- `agent/constant/runtime.go`

## Packaging shape

Do not scaffold this as a normal app first.

Start from the official PHP package shape in `1Panel-dev/appstore/apps/php` and preserve that layout unless source-backed behavior proves a change is required:

- root `apps/php/data.yml`
  - `additionalProperties.key: php`
  - `additionalProperties.type: php`
- major-line version directories such as `5/`, `7/`, `8/`
- each version directory contains:
  - `data.yml`
  - `docker-compose.yml`
  - `.env`
  - `build/`
  - `conf/`
  - `supervisor/`

The official package is the right baseline because the runtime flow expects the PHP-specific build/context assets, not only a compose file and generic form fields.

## Field and compose expectations

- Keep PHP version selection in version-level `data.yml` as `PHP_VERSION`.
- Keep extension selection in version-level `data.yml` as `PHP_EXTENSIONS`.
- Keep package mirror/source selection in version-level `data.yml` as `CONTAINER_PACKAGE_URL`.
- Keep the published FPM port field as `PANEL_APP_PORT_HTTP`; 1Panel rewrites it to a localhost-only mapping for runtime usage.
- Expect `IMAGE_NAME` to be the final runtime image and `PHP_IMAGE` to be the base image build arg; they serve different roles.
- Audit every version-line `build/Dockerfile`, not only the shared `install-ext` helper, but do not assume the Dockerfile itself should run `install-ext "${PHP_EXTENSIONS}"`.
- In the real PHP runtime flow, selected extensions are installed after `compose up` by `docker exec install-ext ...`. Preinstalling them during `docker build` can backfire because the runtime later mounts `./extensions:/usr/local/lib/php/extensions`, masking build-layer `.so` files and causing false `pecl/... is already installed` failures during the post-start install step.
- Helper hardening is still useful: `install-ext` should tolerate reruns and enable an existing module from `extension_dir` when the `.so` is already present.

## Recommended workflow

1. Read the 1Panel source files listed above and confirm the target really belongs to the PHP runtime flow.
2. Diff the historical package against the official `apps/php` package instead of trying to repair it incrementally if the old package predates current runtime conventions.
3. Replace the legacy package with the official PHP runtime shape when the official package already models the target behavior.
4. Keep the app key as `php` when the goal is to align with the canonical runtime package, not to ship an alternate fork.
5. Preserve the historical package intent in metadata and README when it helps users understand continuity. For example, a migrated `php-unofficial` replacement can describe itself as the PHP-FPM runtime used by 1Panel websites, as long as the runtime contract itself still follows the official PHP package shape.
6. Validate with a real `/runtimes` creation flow, not only a generic app-install smoke.

## Validation notes

- 1Panel does support a built-in local PHP runtime template path. In the PHP runtime create flow, users can choose `resource=local`, enter only a version string, and create a local runtime record without any appstore package lookup.
- That built-in local-template path is different from syncing a local app package under `resource/apps/local/<app-key>`. Do not treat success or failure of one path as proof about the other.
- A local app sync cannot reliably shadow a built-in store app that already uses the same key. For example, a local `php` package may never appear as `localphp` if the panel already ships an official remote `php` app.
- A generic app-install smoke that posts to the normal Applications install flow is not a valid PHP runtime test. It can fail early with `PANEL_WEBSITE_DIR` unset and `invalid spec: :/www/: empty section between colons` because that flow never injects the website runtime directory that `/runtimes` creation provides.
- When that collision exists, use two checks together:
  1. diff your package against the official `1Panel-dev/appstore/apps/php` source
  2. run a real PHP runtime creation test against the panel's store `php` app
- If lab isolation is required, use a temporary test-only key in a copied artifact, but do not treat that temporary key as the shipping package decision.
- For synced local-app validation, match the actual frontend behavior: the app search resource may be `custom`, but the PHP runtime create payload still keeps `resource: appstore`. Do not infer the `/runtimes` payload only from the app-search resource.
- A passing validation case should include at least one non-empty `PHP_EXTENSIONS` selection such as `redis`, then confirm the runtime reaches `Running` and the running container reports the module in `php -m`.
