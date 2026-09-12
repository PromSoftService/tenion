FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 10002 tenion \
    && useradd --uid 10002 --gid 10002 --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin tenion

WORKDIR /srv/tenion

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/tenion_api ./tenion_api

USER 10002:10002

EXPOSE 8100

CMD ["uvicorn", "tenion_api.app:app", "--host", "127.0.0.1", "--port", "8100", "--workers", "1", "--no-server-header"]
