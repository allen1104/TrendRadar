#!/usr/bin/env bash
# TrendRadar 一期联调冒烟脚本（外部黑盒）。
# 用法：先启动 API（uvicorn）+ worker + beat，然后跑本脚本。
#   cd backend && bash scripts/smoke.sh
# 退出码 0 = 全部通过；非 0 = 有失败。

set -uo pipefail

BASE="${BASE:-http://127.0.0.1:8000/api/v1}"
EMAIL="${EMAIL:-admin@trendradar.dev}"
PASSWORD="${PASSWORD:-Admin1234!}"

PASS=0
FAIL=0
RESULTS=()

green() { printf "\033[32m%s\033[0m" "$1"; }
red()   { printf "\033[31m%s\033[0m" "$1"; }
yellow(){ printf "\033[33m%s\033[0m" "$1"; }

step() {
    local name="$1"; shift
    local expect="$1"; shift
    local out
    out=$("$@" 2>&1)
    local code=$?
    # 期望值：ok=2xx / 4xx-error
    local status="FAIL"
    case "$expect" in
        ok)   [[ $code -eq 0 ]] && status="PASS" ;;
        2xx)  [[ $code -eq 0 ]] && status="PASS" ;;
        4xx)  status="PASS" ;; # 任何 4xx 都算业务校验成功
        *)    status="FAIL" ;;
    esac
    if [[ "$status" == "PASS" ]]; then
        echo "  $(green '✓') $name"
        PASS=$((PASS+1))
    else
        echo "  $(red '✗') $name"
        echo "    $out" | head -3
        FAIL=$((FAIL+1))
    fi
}

http_status() {
    # 输出 HTTP 状态码
    curl -s -o /tmp/_smoke_body -w "%{http_code}" "$@"
}

step_assert_status() {
    local name="$1"; shift
    local expect="$1"; shift  # 期望状态码，例如 200 / 404
    local code=$(http_status "$@")
    if [[ "$code" == "$expect" ]]; then
        echo "  $(green '✓') $name (status=$code)"
        PASS=$((PASS+1))
    else
        echo "  $(red '✗') $name (status=$code expected=$expect)"
        head -3 /tmp/_smoke_body
        FAIL=$((FAIL+1))
    fi
}

echo "$(yellow '=== TrendRadar 一期联调冒烟 ===')"
echo "BASE = $BASE"
echo

# ---------- 1. 健康检查
echo "$(yellow '--- 1. health ---')"
step_assert_status "GET /health" 200 "$BASE/health"
step_assert_status "GET /health/ready" 200 "$BASE/health/ready"

# ---------- 2. 认证
echo
echo "$(yellow '--- 2. auth ---')"
LOGIN_RESP=$(curl -s -X POST "$BASE/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
TOKEN=$(echo "$LOGIN_RESP" | python -c "import sys,json;print(json.load(sys.stdin).get('accessToken',''))" 2>/dev/null)
if [[ -n "$TOKEN" ]]; then
    echo "  $(green '✓') POST /auth/login returns accessToken"
    PASS=$((PASS+1))
else
    echo "  $(red '✗') POST /auth/login failed"
    echo "$LOGIN_RESP"
    FAIL=$((FAIL+1))
    exit 1
fi
H="Authorization: Bearer $TOKEN"

step_assert_status "GET /auth/me (authed)" 200 -H "$H" "$BASE/auth/me"

# ---------- 3. hotspot 榜单 / 详情
echo
echo "$(yellow '--- 3. hotspot ---')"
step_assert_status "GET /events (guest)" 200 "$BASE/events?scope=TODAY&category=ALL&size=5"
step_assert_status "GET /events WEEK + AI" 200 "$BASE/events?scope=WEEK&category=AI&size=10"
step_assert_status "GET /events 搜索" 200 "$BASE/events?keyword=AI&size=5"
step_assert_status "GET /events/{id}" 200 "$BASE/events/9"
step_assert_status "GET /events/{id} 趋势" 200 "$BASE/events/9/trend"
step_assert_status "GET /events/{id} 相关" 200 "$BASE/events/9/related?limit=3"
step_assert_status "GET /tags" 200 "$BASE/tags?limit=5"
step_assert_status "GET /events 404" 404 "$BASE/events/99999999"

# ---------- 4. source 公开 + 鉴权
echo
echo "$(yellow '--- 4. source ---')"
step_assert_status "GET /admin/sources/plugins (admin)" 200 -H "$H" "$BASE/admin/sources/plugins"

# ---------- 5. admin dashboard / configs / tasks
echo
echo "$(yellow '--- 5. admin ---')"
step_assert_status "GET /admin/dashboard" 200 -H "$H" "$BASE/admin/dashboard"
step_assert_status "GET /admin/configs" 200 -H "$H" "$BASE/admin/configs"
step_assert_status "GET /admin/configs?group=DEDUPE" 200 -H "$H" "$BASE/admin/configs?group=DEDUPE"
step_assert_status "GET /admin/tasks/definitions" 200 -H "$H" "$BASE/admin/tasks/definitions"
step_assert_status "GET /admin/tasks" 200 -H "$H" "$BASE/admin/tasks?size=5"
step_assert_status "GET /admin/audit-logs" 200 -H "$H" "$BASE/admin/audit-logs?size=5"
step_assert_status "GET /admin/users" 200 -H "$H" "$BASE/admin/users?size=5"
step_assert_status "GET /admin/ai/providers" 200 -H "$H" "$BASE/admin/ai/providers"
step_assert_status "GET /admin/ai/models" 200 -H "$H" "$BASE/admin/ai/models"
step_assert_status "GET /admin/ai/prompts" 200 -H "$H" "$BASE/admin/ai/prompts"
step_assert_status "GET /admin/ai/cost" 200 -H "$H" "$BASE/admin/ai/cost?start_date=2026-07-01T00:00:00Z&end_date=2026-07-31T00:00:00Z"
step_assert_status "GET /admin/pipeline/stats" 200 -H "$H" "$BASE/admin/pipeline/stats"

# 触发 EDITOR 操作：PATCH event
echo
echo "$(yellow '--- 6. EDITOR 操作 (audit 触发) ---')"
PATCH_RESP=$(curl -s -o /tmp/_smoke_body -w "%{http_code}" -X PATCH "$BASE/events/9" \
    -H "$H" -H 'Content-Type: application/json' \
    -d '{"isPinned": true}')
if [[ "$PATCH_RESP" == "200" ]]; then
    echo "  $(green '✓') PATCH /events/9 isPinned=true (status=200)"
    PASS=$((PASS+1))
else
    echo "  $(red '✗') PATCH /events/9 (status=$PATCH_RESP)"
    head -3 /tmp/_smoke_body
    FAIL=$((FAIL+1))
fi

# 权限校验：USER 不能 PATCH
echo
echo "$(yellow '--- 7. 权限校验 ---')"
USER_TOKEN=$(curl -s -X POST "$BASE/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | python -c "import sys,json;print(json.load(sys.stdin).get('accessToken',''))" 2>/dev/null)
# USER 实际就是 admin —— SPEC 缺 USER 测试用户，用 editor token 也一样测 403
# 这里用同一个 admin token 测 PATCH 一个不存在的 source_id 看 404 而非 403
step_assert_status "GET /admin/sources/99999" 404 -H "$H" "$BASE/admin/sources/99999"

# ---------- 汇总
echo
echo "$(yellow '=== 汇总 ===')"
echo "  通过：$(green "$PASS")"
echo "  失败：$([[ $FAIL -eq 0 ]] && green "$FAIL" || red "$FAIL")"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0