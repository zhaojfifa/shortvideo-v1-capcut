# Changelog

## 1.8.0

- Converged routing under `gateway/app/routers` and added route-table logging to spot duplicates.
- Wired storage via a port/provider to keep services off adapters and centralized composition in entrypoints.
- Removed legacy pack shims and duplicate pack download route; kept v1.7 YouCut behavior intact.
- Added tests for route uniqueness and import stability on Windows.

## 1.6.2

- Added Admin Tools UI and `provider_config` persistence for provider defaults.
- Workbench now injects task JSON safely and uses V1 endpoints for downloads.
- Task pipeline step outputs persist into DB and pack marks tasks as `ready`.
- Added `/files/{rel_path}` gateway for workspace artifact downloads.
