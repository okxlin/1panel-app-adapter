# Submission profiles

Choose the target before generating or validating. Use `third-party` when the user does not name a target; use `official` for a submission to `1Panel-dev/appstore`. Pass `--submission-profile official` consistently to scaffold, AppSpec generation, Baota import, migration, and validation. AppSpec also accepts `submissionProfile`; an explicit CLI flag takes precedence.

| Contract | `third-party` (default) | `official` |
| --- | --- | --- |
| Directory form fields already needed by the selected topology | Preserve their reviewed editability | Keep the defaults; set `disabled: true` and `edit: false` |
| Fixed bind mounts and named volumes | Preserve the upstream mechanism and options | Preserve the upstream mechanism and options |
| `.env.sample` | Deliver beside Compose | Keep only a run-side rendering sample; omit from the app |
| Product docs | Chinese `README.md` and English `README_en.md` | Chinese `README.md` and English `README_en.md` |
| Source and test evidence | Outside the app directory | Outside the app directory |
| Lifecycle hooks | Only for a demonstrated lifecycle operation | Only for a demonstrated lifecycle operation |

The mode changes packaging conventions, not the service graph, security controls, persistence mechanism, capability set, or image/runtime evidence requirements. It does not select a reduced topology, convert named volumes into binds, or authorize submission. A fixed upstream path does not need a new form field in either mode. Official mode can lock an existing path field because 1Panel implements `disabled`; do not invent a new parameter just to lock it.

## Output boundary

For `--out-dir <parent>`, deliver only `<parent>/<app-key>/`:

```text
<parent>/
├── .evidence/<app-key>/
│   ├── source-evidence.json
│   └── <version>/.env.sample       # official-mode rendering input only
└── <app-key>/
    ├── data.yml
    ├── logo.png
    ├── README.md
    ├── README_en.md
    └── <version>/
        ├── data.yml
        ├── docker-compose.yml
        ├── .env.sample            # third-party only
        └── scripts/init.sh        # only when initialization is needed
```

Extra configuration, hooks, and legally required notices belong in the app only when the application actually needs them. Do not copy run reports, source archives, test fixtures, credentials, or `source-evidence.json` into it. Do not generate application `LICENSE.txt` files merely because Compose references an image: referencing an image is not copying the application's source into the package. Preserve notices required by material actually redistributed. The bundled fallback icon keeps its MIT notice inside `README.md`; its source SVG stays in the skill repository. Do not substitute an unverified license for an upstream logo.

The validator discovers the sibling `.evidence/<app-key>/source-evidence.json`. It accepts historical in-package evidence for inspection. After copying an app away from its run directory, pass `--source-evidence <exact-file>` explicitly. Conflicting sidecar and historical evidence is an error. Evidence remains required for final delivery; moving it outside the package does not waive it. Changes to a hash-bound README, icon, or notice require updating and rechecking its evidence.

Generate into a new output directory when changing profiles. Generators reject a profile that conflicts with existing output before writing files. AppSpec generation, Baota import, and migration also reject replacing a nonempty version directory; adding a new version under the same profile remains supported. Scaffold's explicit `--force` can refresh an existing package under the same profile and preserves existing lifecycle hooks for review.

For an official package without `.env.sample`, validation derives a temporary environment from the panel form defaults and deletes it after the check. For `random: true`, it appends a deterministic `_` plus six-character suffix, matching the panel's value shape even when the default is empty. This simulation is only a Compose validation input; it is not a password generator, a delivered default, or evidence of application startup or secret correctness. Ordinary required fields with empty defaults remain empty and must be resolved through the source-backed startup contract. Direct `gen_env_sample.py` calls opt in with `--simulate-panel-random`; normal sample generation is unchanged.

## Final checks

```bash
bash scripts/validate-v2.sh --dir <app-dir> --version <version> \
  --submission-profile third-party --strict-store --i18n-mode strict \
  --source-evidence-mode required --require-delivery-evidence
```

Use `official` for the other profile. Both need the same source, licensing, image identity, path safety, and runtime acceptance evidence. Current source pins and the distinction between panel behavior and repository conventions are in [1panel-sources.md](1panel-sources.md).
