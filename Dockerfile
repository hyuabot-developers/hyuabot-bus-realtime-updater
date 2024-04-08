FROM python:3.12-alpine AS build
RUN python3.12 -m pip install --upgrade pip setuptools wheel

WORKDIR /app
COPY setup.cfg .
COPY setup.py .
COPY src ./src
RUN apk add --no-cache --virtual .build-deps gcc libc-dev libxslt-dev libpq-dev && \
    apk add --no-cache libxslt && \
    python3.12 -m pip install --disable-pip-version-check -e . && \
    apk del .build-deps

FROM python:3.12-alpine AS runtime

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /app /app
WORKDIR /app/src

ENTRYPOINT ["python3.12", "main.py"]