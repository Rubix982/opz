# openssl + curl in a pinned image, so certificates are made the same way on every machine.
FROM alpine:3.20
RUN apk add --no-cache openssl curl
COPY issue.sh make-ca.sh /usr/local/bin/
