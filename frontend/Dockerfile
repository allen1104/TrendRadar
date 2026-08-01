FROM node:22-alpine AS build

WORKDIR /app

RUN corepack enable

# 1) 只 COPY manifest + lockfile，先装依赖（充分利用 Docker layer 缓存）
COPY package.json pnpm-lock.yaml* .npmrc* ./
RUN pnpm install --frozen-lockfile || pnpm install

# 2) 再 COPY 源码（.dockerignore 排除 node_modules / dist / .git 等）
COPY . .

# 3) 先 gen:api 生成类型（openapi.json 由后端在另一个容器提供；这里用空 fallback）
RUN pnpm build || (echo "build failed — check if backend openapi.json is available" && exit 1)

FROM nginx:alpine

# nginx 静态站点：/ → /usr/share/nginx/html；/api → 后端（可选，见 nginx.conf）
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
