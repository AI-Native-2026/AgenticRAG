#!/usr/bin/env bash
# 知识中台一键启动脚本（AutoDL / Ubuntu）
# 用法: bash deploy/start_all.sh [start|stop|status|restart]
set -uo pipefail

ROOT="${PLATFORM_ROOT:-/root/autodl-tmp/agentic_rag_platform}"
BACKEND="$ROOT/backend"
LOG="$BACKEND/logs"
CONDA_SH=/root/miniconda3/etc/profile.d/conda.sh
ENV=/root/autodl-tmp/conda_envs/agentic_rag
DATA=/root/autodl-tmp/data
KAFKA=/root/autodl-tmp/kafka

mkdir -p "$LOG" "$DATA/mongodb" "$DATA/redis"

log() { echo "[start_all] $*"; }

start_infra() {
  if ! pgrep -x mongod >/dev/null; then
    log "启动 MongoDB…"
    mongod --dbpath "$DATA/mongodb" --bind_ip 127.0.0.1 --port 27017 \
      --fork --logpath "$DATA/mongodb/mongod.log"
  else log "MongoDB 已在运行"; fi

  if ! redis-cli ping >/dev/null 2>&1; then
    log "启动 Redis…"
    redis-server --daemonize yes --dir "$DATA/redis" --appendonly yes \
      --logfile "$DATA/redis/redis.log"
  else log "Redis 已在运行"; fi

  if ! ss -lnt 2>/dev/null | grep -q ':9092'; then
    log "启动 Kafka…"
    ( cd "$KAFKA" && setsid nohup bin/kafka-server-start.sh config/server.properties \
        > logs/kafka-start.log 2>&1 < /dev/null & )
    for i in $(seq 1 30); do
      ss -lnt 2>/dev/null | grep -q ':9092' && break
      sleep 2
    done
  else log "Kafka 已在运行"; fi
}

start_app() {
  if pgrep -f run_api.py >/dev/null; then log "API 已在运行"; else
    log "启动 API…"
    setsid bash -lc "source $CONDA_SH; conda activate $ENV; cd $BACKEND; python scripts/run_api.py" \
      > "$LOG/api.log" 2>&1 < /dev/null &
  fi
  if pgrep -f run_consumer.py >/dev/null; then log "Consumer 已在运行"; else
    log "启动 Consumer…"
    setsid bash -lc "source $CONDA_SH; conda activate $ENV; cd $BACKEND; python scripts/run_consumer.py" \
      > "$LOG/consumer.log" 2>&1 < /dev/null &
  fi
}

stop_app() {
  pkill -f run_api.py 2>/dev/null && log "已停止 API"
  pkill -f run_consumer.py 2>/dev/null && log "已停止 Consumer"
}

status() {
  echo "--- 基础设施 ---"
  pgrep -x mongod >/dev/null && echo "mongod: running" || echo "mongod: stopped"
  redis-cli ping >/dev/null 2>&1 && echo "redis: running" || echo "redis: stopped"
  ss -lnt 2>/dev/null | grep -q ':9092' && echo "kafka: running" || echo "kafka: stopped"
  echo "--- 应用 ---"
  pgrep -af "run_api.py|run_consumer.py" || echo "未运行"
}

case "${1:-start}" in
  start)   start_infra; start_app; sleep 2; status ;;
  stop)    stop_app ;;
  restart) stop_app; sleep 2; start_app; sleep 2; status ;;
  status)  status ;;
  *) echo "用法: $0 [start|stop|status|restart]"; exit 1 ;;
esac
