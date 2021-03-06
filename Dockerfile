FROM pypy:2

WORKDIR /usr/src/app
COPY . ./src/
RUN pip wheel --no-cache-dir ./src -w wheelhouse

FROM pypy:2-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 sqlite3 \
 && rm -rf /var/lib/apt/lists/*
RUN adduser --system --group --home /usr/src/app --disabled-login infobob

WORKDIR /usr/src/app
COPY --from=0 /usr/src/app/wheelhouse wheelhouse
RUN pip install --no-cache-dir --no-deps --no-index ./wheelhouse/*

COPY infobob.cfg.example db.schema ./
RUN mkdir -p /app/db
RUN sqlite3 <db.schema /app/db/infobob.sqlite
RUN chown -R infobob: /app

ARG INFOBOB_COMMIT=<unknown>
ENV INFOBOB_COMMIT=${INFOBOB_COMMIT}
LABEL infobob_commit=${INFOBOB_COMMIT}

VOLUME /app
USER infobob
ENTRYPOINT ["twistd", "--pidfile=", "-n", "infobob"]
CMD ["infobob.cfg.example"]
