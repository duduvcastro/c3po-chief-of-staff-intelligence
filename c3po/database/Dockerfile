FROM golang:1.26.10-alpine3.24@sha256:9ce231b28998b32e116927c61aa5c406183061d4f3f2d61b292c88e7f6bdf7ca AS gosu-build

ARG GOSU_COMMIT=6456aaa0f3c854d199d0f037f068eb97515b7513
# gosu 1.19 pins golang.org/x/sys v0.1.0 in its go.mod (upstream master too), which the
# scanner reports (CVE-2026-39824, fixed in x/sys >= 0.44.0). The source is checked out
# at the pinned commit and built with the dependency raised to a fixed release; the
# binary's embedded build info is asserted so the fix is provable from the image.
ARG GOSU_X_SYS_VERSION=v0.47.0
# The same gosu go.mod pins github.com/moby/sys/user v0.1.0, reported by the production scan of 08/10/2026
# (CVE-2026-61801, medium, fixed in 0.4.1; PR #446). Raised and asserted the same way. The builder is Go 1.26.10: the
# PR scan of 19/10/2026 reported 13 fixable Go stdlib findings (3 high) in the gosu binary built with 1.25.13, and the
# production scan of 21/10/2026 one high (CVE-2026-111943) fixed in Go 1.26.10.
ARG GOSU_MOBY_SYS_USER_VERSION=v0.4.1
ARG C3PO_SECURITY_REBUILD=bootstrap
RUN test -n "$C3PO_SECURITY_REBUILD" \
    && apk add --no-cache git \
    && git clone --quiet https://github.com/tianon/gosu /src/gosu \
    && cd /src/gosu \
    && git checkout --quiet "$GOSU_COMMIT" \
    && go mod edit -require="golang.org/x/sys@${GOSU_X_SYS_VERSION}" \
    && go mod edit -require="github.com/moby/sys/user@${GOSU_MOBY_SYS_USER_VERSION}" \
    && go mod tidy \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /go/bin/gosu . \
    && go version -m /go/bin/gosu | grep -E "golang.org/x/sys[[:space:]]+${GOSU_X_SYS_VERSION}([[:space:]]|$)" \
    && go version -m /go/bin/gosu | grep -E "github.com/moby/sys/user[[:space:]]+${GOSU_MOBY_SYS_USER_VERSION}([[:space:]]|$)"

FROM postgres:16.15-alpine3.24@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685

ARG C3PO_SECURITY_REBUILD=bootstrap
# Full stable-channel upgrade (Alpine has no proposed-updates channel).
RUN test -n "$C3PO_SECURITY_REBUILD" \
    && apk upgrade --no-cache
COPY --from=gosu-build /go/bin/gosu /usr/local/bin/gosu
RUN gosu --version \
    && gosu nobody true
