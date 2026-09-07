FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build

WORKDIR /app
ARG PNPM_VERSION=10.15.0
RUN corepack enable && corepack prepare pnpm@$PNPM_VERSION --activate

COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_C3PO_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_C3PO_BUILD_SHA=development
ARG NEXT_PUBLIC_SENTRY_DSN=
ARG NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=0
ARG NEXT_PUBLIC_SENTRY_ENVIRONMENT=production
ENV NEXT_PUBLIC_C3PO_API_URL=$NEXT_PUBLIC_C3PO_API_URL
ENV NEXT_PUBLIC_C3PO_BUILD_SHA=$NEXT_PUBLIC_C3PO_BUILD_SHA
ENV NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN
ENV NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=$NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE
ENV NEXT_PUBLIC_SENTRY_ENVIRONMENT=$NEXT_PUBLIC_SENTRY_ENVIRONMENT

RUN pnpm build && node scripts/build-nginx-config.cjs

FROM nginx:1.31.4-alpine@sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913
ARG C3PO_SECURITY_REBUILD=bootstrap
# Full stable-channel upgrade (Alpine has no proposed-updates channel) and no curl:
# nothing in the web image calls curl/libcurl (the deploy health probes run on the host).
RUN test -n "$C3PO_SECURITY_REBUILD" \
    && apk upgrade --no-cache \
    && apk del --no-cache curl
COPY --from=build /app/nginx.production.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/out /usr/share/nginx/html
EXPOSE 80
