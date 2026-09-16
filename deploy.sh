#!/usr/bin/env bash
# 单机Compose发布；远程由CI通过SSH调用本脚本。镜像tag必须可追溯。
set -euo pipefail
cd "$(dirname "$0")"
environment="${1:-dev}"
action="${2:-deploy}"
case "$environment" in dev|staging|prod) ;; *) echo '环境必须是dev/staging/prod' >&2; exit 2;; esac
case "$action" in deploy|--rollback|--build) ;; *) echo '动作必须是deploy/--rollback/--build' >&2; exit 2;; esac
command -v docker >/dev/null
: "${APP_IMAGE:?请设置固定tag或digest的APP_IMAGE}"
if [[ "$APP_IMAGE" == *:latest ]]; then echo '禁止使用latest发布' >&2; exit 2; fi
if [[ ! -f .env ]]; then echo '缺少.env，请按.env.example配置服务和密钥' >&2; exit 2; fi
mkdir -p .data
state=".data/release-${environment}"
lock=".data/deploy-${environment}.lock"
if ! mkdir "$lock" 2>/dev/null; then echo '已有发布执行中，请先核实部署进程' >&2; exit 1; fi
trap 'rmdir "$lock"' EXIT
previous=''
if [[ -f "$state.current" ]]; then previous="$(cat "$state.current")"; fi
if [[ "$action" == '--build' ]]; then
  docker build -t "$APP_IMAGE" .
  exit 0
fi
if [[ "$action" == '--rollback' ]]; then
  if [[ ! -s "$state.previous" ]]; then echo '没有可回退版本' >&2; exit 1; fi
  APP_IMAGE="$(cat "$state.previous")"
fi
export APP_IMAGE
if [[ "$environment" == 'prod' ]]; then export APP_ENV=production; fi
docker compose config --quiet
docker compose pull app
if ! docker compose up -d --no-deps --wait --wait-timeout 120 app; then
  echo '新版本健康检查失败，尝试恢复原镜像' >&2
  if [[ -n "$previous" ]]; then
    export APP_IMAGE="$previous"
    docker compose up -d --no-deps --wait --wait-timeout 120 app
  fi
  exit 1
fi
if [[ -n "$previous" ]]; then printf '%s\n' "$previous" > "$state.previous"; fi
printf '%s\n' "$APP_IMAGE" > "$state.current"
echo "发布完成：$environment $APP_IMAGE"
