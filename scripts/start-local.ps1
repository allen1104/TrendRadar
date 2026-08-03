# 快速启动本地服务（仅启动，不做任何初始化 / 迁移 / seed）
#
# 前置条件（脚本不会自动检查）：
#   1. PostgreSQL + pgvector + Redis 已启动且可连接（本地或 docker compose）
#   2. backend/.env 已配置好 DATABASE_URL / REDIS_URL / SECRET_KEY 等
#   3. uv（后端）与 pnpm（前端）已安装
#   4. 后端依赖已 `uv sync`，前端依赖已 `pnpm install`
#
# 启动内容：
#   - FastAPI (uvicorn, :8000, --reload)
#   - Celery worker (solo pool, 适合 Windows)
#   - Celery beat (调度器)
#   - Vite dev server (:5173)
#
# 关闭：在终端按 Ctrl+C 终止本脚本即可

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot/.."
Set-Location $Root

# 端口检查（占用则提示退出，不主动杀进程）
function Test-Port {
    param([int]$Port, [string]$Name)
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
        $listener.Start()
        $listener.Stop()
    } catch {
        Write-Host "✗ 端口 $Port 被占用（$Name）。请先释放端口再运行。" -ForegroundColor Red
        exit 1
    }
}

Write-Host "==> 检查端口..." -ForegroundColor Cyan
Test-Port -Port 8000 -Name "FastAPI"
Test-Port -Port 5173 -Name "Vite"

# 启动后端 API
Write-Host "==> 启动 FastAPI (uvicorn :8000)..." -ForegroundColor Cyan
$apiProc = Start-Process `
    -FilePath "uv" `
    -ArgumentList "run","uvicorn","app.main:app","--reload","--host","127.0.0.1","--port","8000" `
    -WorkingDirectory "$Root/backend" `
    -PassThru `
    -RedirectStandardOutput "$Root/.run/api.out.log" `
    -RedirectStandardError  "$Root/.run/api.err.log"
Write-Host "    pid=$($apiProc.Id), log=backend/.run/api.{out,err}.log" -ForegroundColor DarkGray

# 启动 Celery worker（solo pool = Windows 友好）
Write-Host "==> 启动 Celery worker (solo)..." -ForegroundColor Cyan
$workerProc = Start-Process `
    -FilePath "uv" `
    -ArgumentList "run","celery","-A","app.worker","worker","-l","info","-P","solo","--concurrency","1" `
    -WorkingDirectory "$Root/backend" `
    -PassThru `
    -RedirectStandardOutput "$Root/.run/worker.out.log" `
    -RedirectStandardError  "$Root/.run/worker.err.log"
Write-Host "    pid=$($workerProc.Id), log=backend/.run/worker.{out,err}.log" -ForegroundColor DarkGray

# 启动 Celery beat
Write-Host "==> 启动 Celery beat..." -ForegroundColor Cyan
$beatProc = Start-Process `
    -FilePath "uv" `
    -ArgumentList "run","celery","-A","app.worker","beat","-l","info" `
    -WorkingDirectory "$Root/backend" `
    -PassThru `
    -RedirectStandardOutput "$Root/.run/beat.out.log" `
    -RedirectStandardError  "$Root/.run/beat.err.log"
Write-Host "    pid=$($beatProc.Id), log=backend/.run/beat.{out,err}.log" -ForegroundColor DarkGray

# 启动 Vite 前端
Write-Host "==> 启动 Vite dev (pnpm dev :5173)..." -ForegroundColor Cyan
$webProc = Start-Process `
    -FilePath "pnpm" `
    -ArgumentList "dev" `
    -WorkingDirectory "$Root/frontend" `
    -PassThru `
    -RedirectStandardOutput "$Root/.run/web.out.log" `
    -RedirectStandardError  "$Root/.run/web.err.log"
Write-Host "    pid=$($webProc.Id), log=frontend/.run/web.{out,err}.log" -ForegroundColor DarkGray

# 注册关闭 hook（Ctrl+C 时一起杀）
$children = @($apiProc, $workerProc, $beatProc, $webProc)
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    foreach ($p in $children) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}
$null = Register-EngineEvent -SourceIdentifier Console.CancelKeyPress -Action {
    foreach ($p in $children) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    [Environment]::Exit(0)
}

Write-Host ""
Write-Host "✓ 全部已启动。" -ForegroundColor Green
Write-Host "  API:    http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "  Web:    http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "  日志:   .run/{api,worker,beat,web}.{out,err}.log" -ForegroundColor Green
Write-Host "  停止:   按 Ctrl+C" -ForegroundColor Green

# 主线程阻塞；任一子进程退出则一并杀
while ($true) {
    Start-Sleep -Seconds 2
    foreach ($p in @($apiProc, $workerProc, $beatProc, $webProc)) {
        if ($p.HasExited) {
            Write-Host "✗ 子进程 pid=$($p.Id) 已退出 code=$($p.ExitCode)，关闭全部..." -ForegroundColor Red
            foreach ($q in @($apiProc, $workerProc, $beatProc, $webProc)) {
                if ($q -and -not $q.HasExited) {
                    try { Stop-Process -Id $q.Id -Force -ErrorAction SilentlyContinue } catch {}
                }
            }
            exit 1
        }
    }
}