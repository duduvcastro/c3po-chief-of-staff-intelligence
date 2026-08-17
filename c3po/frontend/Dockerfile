FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable

COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile=false

COPY . .

ARG NEXT_PUBLIC_C3PO_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_C3PO_API_URL=$NEXT_PUBLIC_C3PO_API_URL

RUN pnpm build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/out /usr/share/nginx/html
EXPOSE 80
