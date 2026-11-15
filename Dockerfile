# FEA toolchain: CalculiX (solver) from Debian, Python deps + the fsa package via uv.
FROM debian:bookworm-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /usr/local/bin/uv
# python3-gmsh: PyPI has no linux-aarch64 gmsh wheel, so the venv sees Debian's via system site-packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
      calculix-ccx python3 python3-gmsh \
    && rm -rf /var/lib/apt/lists/*
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON=/usr/bin/python3 UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH MPLCONFIGDIR=/tmp/mpl
WORKDIR /opt/project
COPY pyproject.toml uv.lock ./
RUN uv venv --system-site-packages /opt/venv && uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
WORKDIR /work
ENTRYPOINT ["fsa"]
