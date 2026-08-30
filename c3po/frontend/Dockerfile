FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build

WORKDIR /app
ARG PNPM_VERSION=10.15.0
RUN corepack enable && corepack prepare pnpm@$PNPM_VERSION --activate

COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_C3PO_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_C3PO_BUILD_SHA=development
ENV NEXT_PUBLIC_C3PO_API_URL=$NEXT_PUBLIC_C3PO_API_URL
ENV NEXT_PUBLIC_C3PO_BUILD_SHA=$NEXT_PUBLIC_C3PO_BUILD_SHA

RUN pnpm build

FROM nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/out /usr/share/nginx/html
EXPOSE 80
