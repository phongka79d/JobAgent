# JobAgent frontend — production-shaped multi-stage image.
# Build context: repository root (see infrastructure/docker-compose.yml).
# Only the approved public VITE_API_BASE_URL is accepted at build time.
# Does not copy root .env or backend-only secrets.

FROM node:22-bookworm-slim AS build

WORKDIR /frontend

# Reproducible install (Batch01 command: npm ci --ignore-scripts).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

COPY frontend/ ./

# Exact public key only; injected via Compose build arg (not a copied .env file).
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# Static runtime: non-root nginx serving the production build.
FROM nginx:1.27-alpine AS runtime

# Minimal server on unprivileged port 8080.
COPY infrastructure/docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /frontend/dist /usr/share/nginx/html

RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid \
    && sed -i 's|^pid\s\+.*|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
    && sed -i 's/user  nginx;/# user nginx; (non-root container)/' /etc/nginx/nginx.conf

USER nginx

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
