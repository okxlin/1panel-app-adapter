# Topology Preflight

Use this preflight before generating files or starting deployment tests for a new 1Panel app candidate. Its purpose is to decide whether the candidate belongs in the ordinary adaptation workflow at all.

## 1. Check overlap and maintenance activity

- Search the current official 1Panel store by app key, product name, repository, and image. If the app is already present, route the work to update or maintenance review instead of creating a duplicate.
- Search the target store and open target-store PRs separately. Official-store presence, target-store presence, and open-PR overlap are different facts.
- Record an activity snapshot with its date: archived state, default-branch last push, latest stable or self-hosted release, recent deployment-file changes, and license. Treat stars and forks as context, not maintenance proof.
- Classify activity explicitly, but do not turn a quiet repository into a permanent rejection without release and maintenance evidence.

When a release tag is annotated, record both the tag object and the peeled source commit. Pin Compose, Dockerfile, startup, migration, and upgrade evidence to the source commit rather than assuming the tag object is the source tree.

## 2. Enumerate every official Docker deployment shape

Inspect all upstream-supported Docker shapes relevant to the release, including standard Compose, AIO images, optional overlays, and documented external-service modes. Do not select an AIO image only because it reduces the Compose service count.

For each viable shape, record:

- Compose services and images;
- long-running application roles and one-shot migrations;
- Supervisor, s6, or other internal process managers;
- internal gateways or path routers that an outer 1Panel reverse proxy cannot replace;
- required stateful dependencies and whether they can actually be externalized;
- authoritative persistent state, backup boundary, upgrade order, and rollback boundary;
- upstream positioning for production, evaluation, or testing.

Also build a capability contract for each viable shape. Record its user-visible capabilities,
whether each capability is enabled by default in the full upstream default, and the exact service,
image, environment, and dependency combination that enables it. Mark each capability as core,
optional, or conditional and cite the exact-version official evidence for that classification.

Name the selected profile as the full upstream default, a capability-equivalent alternative, or a
reduced-capability profile. Preserve the full upstream capability set by default. A
capability-equivalent alternative must have official or target-platform evidence that maps every
default user-visible capability to the replacement service, image, environment, and dependency
combination without feature loss.

Select a reduced-capability profile only when the user explicitly requests reduced capability. Do
not choose one merely to remove services, simplify validation, or keep an otherwise conditional
topology on the ordinary route. A reduced-capability profile must list exactly which features
become unavailable, the operator-visible effect, and the supported path for enabling them later.
Do not describe it as the default, minimal default, or source-equivalent topology merely because
the core service can start. Disclosure does not substitute for capability preservation.

An optional sidecar, overlay, or profile may be omitted only when exact-version evidence proves
that the remaining topology is supported and that its selected service, image, environment, and
dependency combination is internally compatible. When omission requires a compatible image
variant or different environment setting, deliver and verify that combination. An `optional`
comment by itself does not prove that every partial combination works. Missing capability or
compatibility evidence blocks scaffolding.

A single Compose service can still be an operationally complex multi-process application. Count both the visible Compose topology and the processes and state hidden inside the image.

## 3. Inspect the published OCI image

Inspect the resolved manifest and OCI config for every Compose service image, including database,
cache, browser, migration, and helper images, not only the primary application image or upstream
Dockerfile. Record at least:

- digest and supported platforms;
- `User`;
- `Healthcheck`;
- `ExposedPorts`;
- `Volumes`;
- source and revision labels;
- entrypoint and command when they affect migrations or process supervision.

Compare OCI metadata with upstream intent. Malformed volume keys, a missing healthcheck, an unexpected root user, or absent source labels are review findings even when the Dockerfile appears correct.

## 4. Prove 1Panel dependency compatibility

Keep these concepts separate:

1. the dependency exists in the official store;
2. its root `additionalProperties.type` is `runtime`;
3. it registers a selectable service through the relevant 1Panel service/resource path;
4. the candidate application is compatible with that runtime's actual contract;
5. 1Panel links and manages the application database lifecycle expected by the form.

A store app typed as `website` or `tool` is not automatically a Runtime selector candidate.

Selector values are app keys, not interchangeable product labels. Verify `mysql` and `localmysql` independently against their exact `/apps/services/<key>` endpoints. A service returned as `Running` proves enumeration and reachability only. For forms that request database name, user, and password, also require a real install report with the host envKey in `services`, then verify `linkDB` or matching `resourceKeys`, schema/user creation, upgrade retention, and uninstall cleanup. Record manually managed external schemas/users as a separate lifecycle boundary.

“Supports external PostgreSQL” is not enough to claim compatibility with the standard PostgreSQL Runtime. Audit:

- required extensions or a specialized PostgreSQL fork;
- predefined roles and ownership;
- superuser operations, event triggers, and initialization scripts;
- encryption or root-key state outside the ordinary database directory;
- database provisioning and migration order;
- major-version upgrade, backup, restore, and rollback procedures.

Apply the same contract-level check to Redis or Valkey, queues, object storage, and other stateful services. Version compatibility and business-path behavior still require runtime evidence.

## 5. Assign a terminal route

Choose exactly one route before scaffolding:

- `ordinary_candidate`: the supported topology fits the normal 1Panel app lifecycle, and required dependencies are bundled deliberately or have credible Runtime/external-service paths.
- `specialized_conditional`: adaptation may be viable, but AIO multi-process behavior, several external stateful services, coordinated migrations, domain constraints, or another explicit prerequisite requires a manual plan. Do not scaffold or deploy until the recorded prerequisites are satisfied.
- `platform_stack_terminal`: the release is an integrated platform with specialized database or identity contracts, many coordinated services or images, and platform-wide backup or major-upgrade lifecycle. Stop the ordinary adaptation workflow. Reconsider only as a separately scoped platform project.

Record temporary blockers separately from the route. A current image with unexcepted Critical vulnerabilities, missing official artifacts, or an unavailable release can block work now without proving the application is permanently unsuitable.

The preflight output should state the selected route, supporting evidence, current blockers, Runtime candidates and incompatibilities, and the next action. Only `ordinary_candidate`, or a `specialized_conditional` candidate whose prerequisites are now satisfied, proceeds to generation and deployment testing.
