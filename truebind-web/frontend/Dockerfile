# Production image: builds with `next build` and serves with `next
# start`. docker-compose.yml overrides CMD with `npm run dev` for local
# development (bind-mounts the source for hot reload), so this Dockerfile
# as written is only ever used as-is outside docker-compose -- e.g. a
# standalone `docker build`/`docker run`, or a platform that builds this
# Dockerfile directly. Previously this image's own CMD was `npm run dev`,
# which is unoptimized and not meant to serve real traffic.
FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22-slim AS runner

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./

EXPOSE 3000
CMD ["sh", "-c", "npm start -- --port ${PORT:-3000}"]
