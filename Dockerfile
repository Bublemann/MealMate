# syntax=docker/dockerfile:1.26@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32
#
# MealMate production image (plan § 10.3): the FastAPI backend serving the built frontend.
#
#   docker buildx build --load -t mealmate:local .
#
# Behind a TLS-intercepting proxy, pass its CA as the optional secret `extra_ca`; it is trusted
# only while dependencies download and never ends up in a layer:
#
#   docker buildx build --build-arg HTTPS_PROXY --secret id=extra_ca,src=ca.crt --load -t … .

# Base images are pinned by digest in every FROM line (Dependabot keeps them in sync). The
# BuildKit frontend in the syntax line is pinned, too; Dependabot does not update it, so bump it
# by hand together with the base images.

# --- Frontend: static build, the same for every platform ------------------------------------
FROM --platform=$BUILDPLATFORM node:24-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=extra_ca,required=false \
    --mount=type=cache,target=/root/.npm,sharing=locked \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Python tooling shared by the build and dev stages ----------------------------------------
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS python-tools
ARG UV_VERSION=0.12.19
# Runs a command that also trusts the optional `extra_ca` secret next to the system roots. The
# combined bundle is a temporary file removed before the RUN step ends.
COPY --chmod=0755 <<'EOF' /usr/local/bin/with-extra-ca
#!/bin/sh
set -eu
if [ ! -s /run/secrets/extra_ca ]; then
  exec "$@"
fi
bundle=$(mktemp)
trap 'rm -f "$bundle"' EXIT
cat /etc/ssl/certs/ca-certificates.crt /run/secrets/extra_ca > "$bundle"
SSL_CERT_FILE="$bundle" PIP_CERT="$bundle" "$@"
EOF
RUN --mount=type=secret,id=extra_ca,required=false \
    with-extra-ca pip install --no-cache-dir --root-user-action=ignore "uv==${UV_VERSION}"
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# --- Backend: runtime dependencies and the app (with its migrations) in /opt/venv ---------------
FROM python-tools AS backend-build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1
WORKDIR /src/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=secret,id=extra_ca,required=false \
    --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    with-extra-ca uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
# Non-editable: the wheel carries alembic.ini and alembic/ inside the `app` package
# (backend/hatch_build.py), so /opt/venv is all the runtime stage needs from the backend.
RUN --mount=type=secret,id=extra_ca,required=false \
    --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    with-extra-ca uv sync --frozen --no-dev --no-editable

# --- Development backend for compose.dev.yml (source bind-mounted at /src/backend) ------------
FROM python-tools AS backend-dev
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    MEALMATE_DATA_DIR=/data \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8080
WORKDIR /src/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=secret,id=extra_ca,required=false \
    --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    with-extra-ca uv sync --frozen --no-install-project
EXPOSE 8080
CMD ["sh", "-c", "uv sync --frozen && uv run --no-sync mealmate db upgrade && exec uv run --no-sync uvicorn app.main:create_app --factory --reload --port \"$UVICORN_PORT\""]

# --- Runtime ------------------------------------------------------------------------------------
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS runtime

# Non-root user (SEC-09); pip is a build tool and not needed at runtime.
RUN groupadd --gid 10001 mealmate \
    && useradd --uid 10001 --gid 10001 --home-dir /nonexistent --no-create-home \
        --shell /usr/sbin/nologin mealmate \
    && install -d -o 10001 -g 10001 -m 0750 /data \
    && python -m pip uninstall --yes --root-user-action=ignore pip \
    && rm -rf /root/.cache

COPY --from=backend-build /opt/venv /opt/venv
COPY --from=frontend-build /src/frontend/dist /opt/mealmate/static
# The licence travels with the published image (AGPL-3.0 §§ 4-6, LIC-01).
COPY LICENSE /opt/mealmate/LICENSE
# The verified source of the Pi's host files (compose, scripts, units; plan § 11.5).
COPY deploy/ /opt/mealmate/deploy/
COPY --chmod=0755 backend/bin/mealmate-entrypoint /usr/local/bin/mealmate-entrypoint

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEALMATE_STATIC_DIR=/opt/mealmate/static \
    MEALMATE_DATA_DIR=/data \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8080

ARG MEALMATE_VERSION=0.0.0-dev
ARG MEALMATE_COMMIT=unknown
ENV MEALMATE_VERSION=${MEALMATE_VERSION} \
    MEALMATE_COMMIT=${MEALMATE_COMMIT}
LABEL org.opencontainers.image.title="MealMate" \
      org.opencontainers.image.description="Self-hosted app that turns saved meals into a category-sorted shopping list" \
      org.opencontainers.image.source="https://github.com/Bublemann/MealMate" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.version="${MEALMATE_VERSION}" \
      org.opencontainers.image.revision="${MEALMATE_COMMIT}"

WORKDIR /opt/mealmate
VOLUME /data
USER 10001:10001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as r; r.build_opener(r.ProxyHandler({})).open(f\"http://127.0.0.1:{os.environ.get('UVICORN_PORT', '8080')}/api/health\", timeout=4)"]

ENTRYPOINT ["mealmate-entrypoint"]
