# Phase0 Storage Checklist

## Required environment variables

- `FEATURE_STORAGE_ENABLED=true`
- `R2_ENDPOINT_URL`
- `R2_BUCKET`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_REGION` (optional, defaults to `auto`)
- `SIGNED_URL_EXPIRES` (optional, defaults to `900` seconds)

## Presign smoke test

```bash
python - <<'PY'
import os
from gateway.app.storage import r2

os.environ.setdefault("FEATURE_STORAGE_ENABLED", "true")
print("enabled:", r2.enabled())
key = r2.key_for("demo_task", "raw.mp4")
print("key:", key)
if r2.enabled():
    print("presign:", r2.presign_get(key, filename="raw.mp4")[:80] + "…")
PY
```
