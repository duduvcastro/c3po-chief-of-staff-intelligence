FROM golang:1.25.14-alpine3.24@sha256:1ae0735f00daffa3aaf1363a5184c0d2dc55c78e3db4ec70241cdac97bf84b59 AS gosu-build

RUN CGO_ENABLED=0 go install -trimpath -ldflags='-s -w' \
    github.com/tianon/gosu@6456aaa0f3c854d199d0f037f068eb97515b7513

FROM postgres:16.15-alpine3.24@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685

COPY --from=gosu-build /go/bin/gosu /usr/local/bin/gosu

RUN apk upgrade --no-cache \
    && gosu --version \
    && gosu nobody true
