# FEA toolchain: CalculiX (solver) from Debian, Python deps via uv (see pyproject.toml).
FROM debian:bookworm-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
# python3-gmsh: PyPI has no linux-aarch64 gmsh wheel, so the venv sees Debian's via system site-packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
      calculix-ccx python3 python3-gmsh \
    && rm -rf /var/lib/apt/lists/*
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON=/usr/bin/python3 UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH
COPY pyproject.toml uv.lock /opt/project/
RUN cd /opt/project && uv venv --system-site-packages /opt/venv \
    && uv sync --frozen --no-dev --no-install-project
WORKDIR /work
