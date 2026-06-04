# Raqim Frontend (React / Create React App)
# ------------------------------------------
# Multi-stage build:
#   1) "build" stage installs deps and produces the static production bundle.
#   2) runtime stage serves the bundle with a tiny static file server.

# ---- Stage 1: build ----
FROM node:lts AS build

WORKDIR /app

# Allow overriding the backend URL that gets baked into the React bundle.
# CRA only exposes variables prefixed with REACT_APP_ and inlines them at build time.
ARG REACT_APP_API_BASE_URL=http://127.0.0.1:5000
ENV REACT_APP_API_BASE_URL=${REACT_APP_API_BASE_URL}

# Install dependencies first for better layer caching.
COPY package.json package-lock.json ./
RUN npm install

# Build the production bundle.
COPY . .
RUN npm run build

# ---- Stage 2: runtime ----
FROM node:lts-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production

# "serve" is a lightweight static server used to run the built React app.
RUN npm install -g serve@14

# Copy only the compiled static assets from the build stage.
COPY --from=build /app/build ./build

# React is served on port 3000 inside the container.
EXPOSE 3000

# -s = single-page-app mode (all routes fall back to index.html).
CMD ["serve", "-s", "build", "-l", "3000"]
