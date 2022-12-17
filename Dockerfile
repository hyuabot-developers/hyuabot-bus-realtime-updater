FROM python:3.11-alpine AS build
RUN python3.11 -m venv /venv && \
    /venv/bin/pip install --upgrade pip setuptools wheel

COPY setup.cfg /setup.cfg
COPY setup.py /setup.py
COPY src /src
RUN apk add --no-cache --virtual .build-deps gcc libc-dev libxslt-dev && \
    apk add --no-cache libxslt && \
    /venv/bin/pip install --disable-pip-version-check -e / && \
    apk del .build-deps

COPY . .
WORKDIR /src

ENTRYPOINT ["/venv/bin/python3", "main.py"]