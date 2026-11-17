# ==============================================================================
# Corbel Frontend — Multi-Stage Dockerfile (Node.js Build + Nginx Runtime)
# ==============================================================================

# Stage 1: Build static assets with Node.js
FROM node:22-alpine AS builder

WORKDIR /app

# Copy dependency manifests and committed lockfile for deterministic builds (P1-LIM-006)
COPY frontend/package.json frontend/package-lock.json ./

# Install dependencies strictly matching the lockfile
RUN npm ci

# Copy frontend source files
COPY frontend/ .

# Build production bundle
RUN npm run build

# Stage 2: Serve production bundle with lightweight Nginx
FROM nginx:alpine

# Copy custom Nginx proxy configuration
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
