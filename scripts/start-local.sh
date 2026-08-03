#!/usr/bin/env bash
# 快速启动本地服务（仅启动，不做任何初始化 / 迁移 / seed）
#
# 前置条件：
#   1. PostgreSQL + pgvector + Redis 已启动且可连接（本地或 docker compose）
#   2. backend/.env 已配置好 DATABASE_URL / REDIS_URL / SECRET_KEY 等
#   3. uv（后端）与 pnpm（前端）已安装
#   4. 后端依赖已 `uv sync`，前端依赖已 `pnpm install`
#
# 启动内容：
#   - FastAPI (uvicorn, :8000, --reload)
#   - Celery worker (solo pool, 适合 Windows；Linux/Mac 可改为 prefork)
#   - Celery beat (调度器)
#   - Vite dev server (:5173)
#
# 关闭：在终端按 Ctrl+C 终止本脚本即可（trap 会自动清理子进程）

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p .run

# 端口检查
check_port() {
    local port=$1 name=$2
    if command -v ss >/dev/null 2>&1; then
        if ss -ltn "sport = :$port" 2>/dev/null | grep -q ":$port"; then
            echo "✗ 端口 $port 被占用（$name）" >&2
            exit 1
        fi
    elif command -v lsof >/dev/null 2>&1; then
        if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "✗ 端口 $port 被占用（$name）" >&2
            exit 1
        fi
    fi
}

echo "==> 检查端口..."
check_port 8000 "FastAPI"
check_port 5173 "Vite"

CHILDREN=()
cleanup() {
    echo ""
    echo "==> 关闭子进程..."
    for pid in "${CHILDREN[@]:-}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

start_proc() {
    local name=$1; shift
    echo "==> 启动 $name..."
    (
        "$@" > ".run/$name.out.log" 2> ".run/$name.err.log"
    ) &
    local pid=$!
    CHILDREN+=("$pid")
    echo "    pid=$pid, log=.run/$name.{out,err}.log"
}

start_proc api \
    uv --directory "$ROOT/backend" run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

start_proc worker \
    uv --directory "$ROOT/backend" run celery -A app.worker worker -l info -P solo --concurrency 1

start_proc beat \
    uv --directory "$ROOT/backend" run celery -A app.worker beat -l info

start_proc web \
    pnpm --dir "$ROOT/frontend" dev

echo ""
echo "✓ 全部已启动。"
echo "  API:    http://127.0.0.1:8000/docs"
echo "  Web:    http://127.0.0.1:5173"
echo "  日志:   .run/{api,worker,beat,web}.{out,err}.log"
echo "  停止:   按 Ctrl+C"

# 阻塞；任一子进程退出则一并 kill
wait -n "${CHILDREN[@]}"
echo "✗ 有子进程退出，关闭全部..."
exit 1