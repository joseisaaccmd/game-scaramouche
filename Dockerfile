FROM node:22-alpine AS base

FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM base AS builder
WORKDIR /app
# The nginx/Docker deploy is served from /utanomori/. Vercel builds without this arg → base '/'.
ARG VITE_BASE=/utanomori/
ENV VITE_BASE=$VITE_BASE
COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build

FROM nginx:1.27-alpine AS runner
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html/utanomori

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
