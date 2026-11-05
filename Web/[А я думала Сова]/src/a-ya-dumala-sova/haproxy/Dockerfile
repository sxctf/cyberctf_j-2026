FROM haproxy:2.9-alpine

USER root
RUN apk add --no-cache openssl

RUN mkdir -p /usr/local/etc/haproxy/certs && \
    openssl req -x509 -newkey rsa:2048 -nodes \
      -subj "/CN=sova.local" \
      -keyout /tmp/key.pem \
      -out /tmp/cert.pem \
      -days 3650 && \
    cat /tmp/cert.pem /tmp/key.pem > /usr/local/etc/haproxy/certs/challenge.pem && \
    rm -f /tmp/key.pem /tmp/cert.pem

COPY haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg
COPY coraza.cfg /usr/local/etc/haproxy/coraza.cfg

USER haproxy
