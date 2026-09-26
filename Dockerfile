FROM debian:bookworm-slim AS radio-base
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    liquidsoap=2.1.3-2 icecast2=2.4.4-4+b1 ffmpeg ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

FROM golang:1.23.12-bookworm AS radio-build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY radio/ ./radio/
RUN CGO_ENABLED=0 go build -trimpath -o /out/radio ./radio

FROM radio-base AS radio
ARG S6_VERSION=3.2.0.2
RUN arch="$(dpkg --print-architecture)"; \
    case "$arch" in arm64) s6arch=aarch64 ;; amd64) s6arch=x86_64 ;; *) exit 1 ;; esac; \
    for archive in s6-overlay-noarch.tar.xz "s6-overlay-${s6arch}.tar.xz"; do \
      curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/${archive}" -o /tmp/s6.tar.xz \
      && tar -C / -Jxpf /tmp/s6.tar.xz || exit 1; \
    done; rm /tmp/s6.tar.xz
RUN groupadd -g 1000 yogurt && useradd -u 1000 -g yogurt -M yogurt
COPY --from=radio-build /out/radio /app/radio
COPY stations.yml /app/stations.yml
COPY radio/init/prepare /etc/cont-init.d/prepare
COPY radio/services/ /etc/services.d/
ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s CMD curl -fsS http://127.0.0.1/healthz || exit 1
ENTRYPOINT ["/init"]

FROM python:3.12.11-slim-bookworm AS generator-base
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg libsndfile1 util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 yogurt && useradd -u 1000 -g yogurt -m yogurt
WORKDIR /app
RUN pip install --no-cache-dir pyyaml==6.0.2
COPY generator/ /app/generator/
COPY stations.yml /app/stations.yml
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/app/generator/entrypoint.sh"]
CMD ["python", "-m", "generator.main"]

FROM generator-base AS generator-test
COPY tests/test_generator.py /app/tests/test_generator.py
ENTRYPOINT ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]

# Build this pinned upstream runtime with `make ace-runtime` before deployment.
FROM yogurt-acestep:ca1e85fe9430179831e6bc6be790c332190a3866 AS generator
USER root
RUN apt-get update && apt-get install -y --no-install-recommends util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 yogurt && useradd -u 1000 -g yogurt -m yogurt \
    && rmdir /app/checkpoints && ln -s /data/checkpoints /app/checkpoints
WORKDIR /app
COPY generator/ /app/generator/
COPY stations.yml /app/stations.yml
ENV PATH="/app/.venv/bin:$PATH" HOME=/home/yogurt PYTHONUNBUFFERED=1 \
    ACESTEP_CHECKPOINTS_DIR=/data/checkpoints HF_HOME=/data/huggingface \
    TOKENIZERS_PARALLELISM=false
HEALTHCHECK NONE
ENTRYPOINT ["/app/generator/entrypoint.sh"]
CMD ["python", "-m", "generator.main"]
