FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN test -n "$VITE_API_BASE_URL" && npm run build

FROM node:20-alpine AS runtime

ENV NODE_ENV=production \
    PORT=8080
WORKDIR /app

COPY --from=build --chown=node:node /app/dist ./dist
COPY --chown=node:node scripts/static-server.mjs ./static-server.mjs

USER node
EXPOSE 8080
CMD ["node", "static-server.mjs"]
