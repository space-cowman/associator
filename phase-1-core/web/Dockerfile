# The web image. Build from the repository root.
FROM --platform=$BUILDPLATFORM node:24.22.1-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 NPM_CONFIG_UPDATE_NOTIFIER=false
COPY phase-1-core/web/package.json phase-1-core/web/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY phase-1-core/web/ ./
ARG ATTACHMENTS_ORIGIN=""
ENV ATTACHMENTS_ORIGIN=$ATTACHMENTS_ORIGIN
RUN npm run build

FROM node:24.22.1-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER 10001
EXPOSE 3000
CMD ["node", "server.js"]
