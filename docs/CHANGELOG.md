# Changelog

## 1.6.2

- Added Admin Tools UI and `provider_config` persistence for provider defaults.
- Workbench now injects task JSON safely and uses V1 endpoints for downloads.
- Task pipeline step outputs persist into DB and pack marks tasks as `ready`.
- Added `/files/{rel_path}` gateway for workspace artifact downloads.
