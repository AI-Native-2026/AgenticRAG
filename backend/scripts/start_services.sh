#!/usr/bin/env bash
# 一键启动 v2 服务：API + 队列消费者
# 用法: bash scripts/start_services.sh [start|stop|status]
set -e

ROOT=/root/autodl-tmp/agentic_rag_v2
LOG=$ROOT/logs
CONDA=/root/miniconda3/etc/profile.d/conda.sh
ACT="conda activate /root/autodl-tmp/conda_envs/agentic_rag"

mkdir -p "$LOG"

start_one() {
  local name=$1 script=$2
  if pgrep -f "$script" > /dev/null; then
    echo "[$name] 已在运行"
  else
    # nohup + setsid 保证 ssh 断开后进程不退出
    setsid bash -lc "source $CONDA; $ACT; cd $ROOT; python $script" \
      > "$LOG/$name.log" 2>&1 &
    echo "[$name] 已启动 (日志: $LOG/$name.log)"
  fi
}

case "${1:-start}" in
  start)
    echo "== 先检查依赖服务 =="
    redis-cli ping >/dev/null 2>&1 || { echo "Redis 未启动"; exit 1; }
    mongosh --quiet --eval "db.runCommand({ping:1}).ok" >/dev/null 2>&1 || { echo "MongoDB 未启动"; exit 1; }
    cd /root/autodl-tmp/kafka && bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1 \
      || { echo "Kafka 未启动"; exit 1; }
    echo "依赖服务正常，启动应用…"
    start_one api    "scripts/run_api.py"
    start_one consumer "scripts/run_consumer.py"
    ;;
  stop)
    pkill -f "scripts/run_api.py" || true
    pkill -f "scripts/run_consumer.py" || true
    echo "已停止 api / consumer"
    ;;
  status)
    pgrep -af "run_api.py|run_consumer.py" || echo "无运行中的服务"
    ;;
  *) echo "用法: $0 [start|stop|status]"; exit 1;;
esac
