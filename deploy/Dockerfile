# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS node

FROM python:3.11-slim-bookworm AS build
ENV PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 PATH="/app/venv/bin:$PATH"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config libopencv-dev libgl1 libglib2.0-0 libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY deploy/requirements.txt /app/deploy/requirements.txt
RUN python -m venv /app/venv \
    && python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
       torch==2.7.1+cpu torchvision==0.22.1+cpu \
       --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r deploy/requirements.txt \
    && python -m pip check

COPY . /app
RUN python rebrand_devbim.py \
    && python setup_imagerouter.py --no-env \
    && python setup_ifcviewer.py \
    && python setup_pdfviewer.py \
    && python setup_designcode.py \
    && python setup_threed.py \
    && python setup_site_auth.py --no-env \
    && python setup_style_presets.py --no-db-sync \
    && python setup_navbar_labels.py \
    && python deploy/test_deploy.py \
    && python deploy/check_build.py \
    && python tests/test_userauth_login.py \
    && python deploy/check_style_presets.py \
    && python tests/test_threed.py

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 PATH="/app/venv/bin:$PATH" \
    INVOKEAI_ROOT=/data INVOKEAI_HOST=0.0.0.0 INVOKEAI_PORT=9090 \
    INVOKEAI_DEVICE=cpu INVOKEAI_PRECISION=float32 \
    HF_HOME=/data/cache/huggingface MPLCONFIGDIR=/data/cache/matplotlib \
    XDG_CACHE_HOME=/data/cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libgl1 libglib2.0-0 libgomp1 libsndfile1 \
    libopencv-core406 libopencv-imgproc406 libopencv-imgcodecs406 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 studio \
    && mkdir -p /data/cache \
    && chown -R studio:studio /data
WORKDIR /app
COPY --from=build /app/venv /app/venv
COPY --from=build /app/deploy/entrypoint.py /app/deploy/healthcheck.py /app/deploy/invokeai.yaml /app/deploy/
COPY --from=build /app/siteauth /app/siteauth
COPY --from=build /app/user_manager.py /app/company_manager.py /app/
USER studio
EXPOSE 9090
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 \
    CMD ["python", "/app/deploy/healthcheck.py"]
ENTRYPOINT ["python", "/app/deploy/entrypoint.py"]
CMD ["python", "-u", "-c", "from invokeai.app.run_app import run_app; run_app()"]
