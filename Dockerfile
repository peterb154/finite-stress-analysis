# FEA toolchain: gmsh (mesher) + CalculiX (solver), all from Debian's repo.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      calculix-ccx gmsh python3-gmsh python3-numpy python3-matplotlib \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
