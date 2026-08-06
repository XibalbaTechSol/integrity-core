# ── BUILD STAGE ─────────────────────────────────────────────────────────────
FROM rustlang/rust:nightly-bookworm AS builder

# Install system dependencies needed for compiling OpenSSL and other crates
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/integrity

# Copy the Cargo workspace files and source code
COPY Cargo.toml Cargo.lock ./
COPY scoring-core/ scoring-core/
COPY backend/ backend/

# Build release binary
RUN cargo build --release --bin oracle-backend

# ── RUNTIME STAGE ───────────────────────────────────────────────────────────
FROM debian:bookworm-slim

# Baked-in content fingerprint of this service's tracked source — see
# scripts/service_content_hash.py and PRODUCTION_GAPS.md §22. ARGs don't cross a `FROM`
# boundary, so this must be redeclared in the stage that carries the LABEL.
ARG SOURCE_HASH=unknown
LABEL source.hash=$SOURCE_HASH

RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary from builder
COPY --from=builder /usr/src/integrity/target/release/oracle-backend /app/oracle-backend

EXPOSE 8080 4317

ENTRYPOINT ["/app/oracle-backend"]
