# Frontend-only image: React build served by nginx.
# Deploys as its own Railway service.

FROM node:20-alpine AS build
WORKDIR /app

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 600000

COPY . ./
# REACT_APP_BACKEND_URL is baked at build time. Railway lets you set build-time
# vars in Service → Variables; declare it there as the backend's public URL.
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
ENV CI=false
RUN yarn build


FROM nginx:1.27-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf.template

# Railway injects $PORT — render it into the nginx config at boot, then start
CMD ["sh", "-c", "envsubst '${PORT}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
