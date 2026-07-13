# JobAgent frontend: pinned Node build, nginx static serve on 5173.
# Build context: frontend/. VITE_API_BASE_URL is a build-time ARG only.

FROM node:24.11.0-bookworm-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Source and config only (host node_modules/dist not required in context).
COPY index.html tsconfig.json vite.config.ts eslint.config.js ./
COPY src ./src

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27.4-alpine

# Serve SPA on container port 5173 (host publishes 127.0.0.1:5173).
RUN printf '%s\n' \
  'server {' \
  '  listen 5173;' \
  '  server_name _;' \
  '  root /usr/share/nginx/html;' \
  '  location / {' \
  '    try_files $uri $uri/ /index.html;' \
  '  }' \
  '}' > /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 5173

# nginx default entrypoint/cmd; listens on 0.0.0.0:5173 inside the container.
