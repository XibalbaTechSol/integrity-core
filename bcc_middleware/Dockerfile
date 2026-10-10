FROM python:3.12-slim

# Baked-in content fingerprint of this service's tracked source — see
# scripts/service_content_hash.py and PRODUCTION_GAPS.md §22. Compared against a fresh
# recomputation by `make check-deploy` to detect a running image built from stale source,
# without the false-STALE-on-fresh-clone failure mode a file-mtime comparison has.
ARG SOURCE_HASH=unknown
LABEL source.hash=$SOURCE_HASH

WORKDIR /app

# uv gives us reproducible, lockfile-pinned installs -- matches the rest of
# the monorepo's Python packages (integrity-sdk, integrity-cli).
RUN pip install --no-cache-dir uv

# The build context is the REPOSITORY ROOT (docker-compose.yml: `build.context: .`, `dockerfile:
# bcc_middleware/Dockerfile`), not this directory, because bcc_middleware depends on ../integrity-sdk as a
# path dependency (pyproject.toml [tool.uv.sources]). The relative path survives the move into the image:
# /app/../integrity-sdk is /integrity-sdk. Only what the SDK build needs is copied (see
# Dockerfile.dockerignore); the SDK is installed editable from there, as in a local checkout.
COPY integrity-sdk/pyproject.toml integrity-sdk/README.md /integrity-sdk/
COPY integrity-sdk/integrity_sdk /integrity-sdk/integrity_sdk

COPY bcc_middleware/pyproject.toml bcc_middleware/uv.lock ./
RUN uv sync --frozen --no-dev

COPY bcc_middleware/app ./app
COPY bcc_middleware/policies ./policies

# docker-compose.yml's bcc-middleware service sets OPA_URL / ORACLE_URL and
# maps port 8000 -- see docs/INTERFACE_CONTRACT.md §2.
ENV OPA_URL=http://opa:8181 \
    ORACLE_URL=http://oracle-backend:8080 \
    RPC_URL=http://host.docker.internal:8545

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
