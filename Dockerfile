FROM python:3.11-bullseye AS build
RUN apt-get update && \
    apt-get install --no-install-suggests --no-install-recommends --yes gcc && \
    python3.11 -m venv /venv && \
    /venv/bin/pip install --upgrade pip setuptools wheel

FROM build AS build-venv
COPY setup.cfg /setup.cfg
COPY setup.py /setup.py
COPY src /src
RUN /venv/bin/pip install --disable-pip-version-check -e /

FROM python:3.11-slim-bullseye AS runtime
COPY --from=build-venv /venv /venv
COPY . .
WORKDIR ./src
ENTRYPOINT ["/venv/bin/python3", "main.py"]