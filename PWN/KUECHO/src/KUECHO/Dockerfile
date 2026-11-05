FROM ubuntu:latest AS builder

RUN apt-get update && apt-get install -y gcc

WORKDIR /build/

COPY ./src/main.c /build/main.c

RUN gcc -o vuln main.c \
    -fno-stack-protector \
    -z execstack \
    -no-pie \
    -Wl,-z,norelro

FROM ubuntu:latest AS app

WORKDIR /app/

COPY --from=builder /build/vuln /app/vuln

COPY ./flag.txt /app/flag.txt

RUN chmod 555 /app/vuln && \
    chmod 444 /app/flag.txt

FROM pwn.red/jail

COPY --from=app / /srv

RUN mkdir -p /srv/app
COPY --chmod=555 ./run /srv/app/run

ENV JAIL_PIDS=40 \
    JAIL_MEM=10M \
    JAIL_TIME=120
