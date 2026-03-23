# Stage 1: Build the React application
FROM node:20-alpine AS builder

WORKDIR /app

# Allow overriding Vite API URL at build time (empty = use relative /api via nginx)
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}

# Install dependencies from lockfile for reproducible builds
COPY package.json package-lock.json ./
RUN npm ci

# Copy sources and build production bundle
COPY . .
RUN npm run build

# Stage 2: Serve the app with Nginx
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
	CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
