FROM golang:1.25.13-alpine3.24@sha256:1e0126852075c9c60731c8ba49088448b91f63e2aed97ca9d1a9791622a05946 AS gosu-build

ARG GOSU_COMMIT=6456aaa0f3c854d199d0f037f068eb97515b7513
RUN CGO_ENABLED=0 go install -trimpath -ldflags="-s -w" \
    "github.com/tianon/gosu@${GOSU_COMMIT}"

FROM postgres:16.15-alpine3.24@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685

RUN apk upgrade --no-cache libcrypto3 libssl3
COPY --from=gosu-build /go/bin/gosu /usr/local/bin/gosu
RUN gosu --version \
    && gosu nobody true
