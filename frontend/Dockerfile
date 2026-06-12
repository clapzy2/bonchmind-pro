# Frontend image for BonchMind Pro (Next.js standalone).
#
# Two stages: build the app, then ship only the standalone server + static
# assets on a slim node runtime.
#
# BONCHMIND_API_URL is a build ARG because Next evaluates next.config rewrites
# at build time and bakes the destination into the routes manifest. The default
# (http://backend:8000) matches the docker-compose service name, so the image
# works out of the box; override the ARG to point elsewhere.

FROM node:20-slim AS builder
WORKDIR /app

ARG BONCHMIND_API_URL=http://backend:8000
ENV BONCHMIND_API_URL=$BONCHMIND_API_URL \
    NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone output bundles a minimal node_modules + server.js; static assets
# are copied separately (they are not included in the standalone folder).
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
