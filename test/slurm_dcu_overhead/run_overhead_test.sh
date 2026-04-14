#!/bin/bash
# ============================================================
# PerfBench 开销测试批量驱动脚本
#
# 用法: bash run_overhead_test.sh [repeat]
#   repeat: 每种模式重复次数，默认 5
#
# 前置条件:
#   - 在集群登录节点执行
#   - overhead_bare.slurm 在同目录下
#   - PerfBench 已安装（perfbench.py 可用）
# ============================================================

set -euo pipefail

REPEAT=${1:-5}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PROJ_ROOT="/public/home/buaahpc/retro/PerfBench-BUAAHPC"
BASE_DIR="${PROJ_ROOT}/test/slurm_dcu_overhead/overhead_results_${TIMESTAMP}"
SCRIPT_DIR="${PROJ_ROOT}/test/slurm_dcu_overhead"
PERFBENCH="${PROJ_ROOT}/perfbench.py"
WORKLOAD="${SCRIPT_DIR}/overhead_bare.slurm"

mkdir -p "$BASE_DIR"

echo "=== PerfBench Overhead Benchmark ==="
echo "Workload: LAMMPS 10N×4DCU"
echo "Repeats:  $REPEAT"
echo "Output:   $BASE_DIR"
echo "Start:    $(date)"
echo ""

# 记录集群状态快照
sinfo -N -o "%N %t %f %m %G" > "$BASE_DIR/cluster_snapshot.log" 2>&1 || true

# ----------------------------------------------------------
# Phase 1: 裸跑基准
# ----------------------------------------------------------
echo "[Phase 1/4] Bare runs (direct sbatch)..."
for i in $(seq 1 $REPEAT); do
    echo "  Bare run $i/$REPEAT"
    OUT_DIR="$BASE_DIR/bare_$i"
    mkdir -p "$OUT_DIR"

    T_START=$(date +%s.%N)
    # --wait 同步等待作业完成
    JOBID=$(sbatch --wait -o "$OUT_DIR/job_%j.out" -e "$OUT_DIR/job_%j.err" \
            "$WORKLOAD" 2>&1 | grep -oP '\d+$')
    T_END=$(date +%s.%N)

    echo "jobid=$JOBID start=$T_START end=$T_END" > "$OUT_DIR/timing.txt"
    sacct -j "$JOBID" --format=JobID,JobName%20,State,Elapsed,CPUTimeRAW,MaxRSS,AveRSS,AllocCPUS -P \
        > "$OUT_DIR/sacct.log" 2>&1
    echo "  -> JobID=$JOBID done"
done

# ----------------------------------------------------------
# Phase 2: PerfBench 无 DCU 采样
# ----------------------------------------------------------
echo ""
echo "[Phase 2/4] PerfBench (no DCU sampling)..."
for i in $(seq 1 $REPEAT); do
    echo "  PerfBench-noDCU run $i/$REPEAT"
    OUT_DIR="$BASE_DIR/pb_nodcu_$i"

    T_START=$(date +%s.%N)
    python3 "$PERFBENCH" -s "$WORKLOAD" -t 10 -o "$OUT_DIR" --accelerator none
    T_END=$(date +%s.%N)

    echo "start=$T_START end=$T_END" > "$OUT_DIR/timing.txt"
    echo "  -> done"
done

# ----------------------------------------------------------
# Phase 3: PerfBench + DCU 采样 10s
# ----------------------------------------------------------
echo ""
echo "[Phase 3/4] PerfBench (DCU interval=10s)..."
for i in $(seq 1 $REPEAT); do
    echo "  PerfBench-DCU10 run $i/$REPEAT"
    OUT_DIR="$BASE_DIR/pb_dcu10_$i"

    T_START=$(date +%s.%N)
    python3 "$PERFBENCH" -s "$WORKLOAD" -t 10 -o "$OUT_DIR" --accelerator dcu --accelerator-interval 10
    T_END=$(date +%s.%N)

    echo "start=$T_START end=$T_END" > "$OUT_DIR/timing.txt"
    echo "  -> done"
done

# ----------------------------------------------------------
# Phase 4: PerfBench + DCU 采样 2s（高频）
# ----------------------------------------------------------
echo ""
echo "[Phase 4/4] PerfBench (DCU interval=2s, high-freq)..."
for i in $(seq 1 $REPEAT); do
    echo "  PerfBench-DCU2 run $i/$REPEAT"
    OUT_DIR="$BASE_DIR/pb_dcu2_$i"

    T_START=$(date +%s.%N)
    python3 "$PERFBENCH" -s "$WORKLOAD" -t 10 -o "$OUT_DIR" --accelerator dcu --accelerator-interval 2
    T_END=$(date +%s.%N)

    echo "start=$T_START end=$T_END" > "$OUT_DIR/timing.txt"
    echo "  -> done"
done

# ----------------------------------------------------------
# 汇总
# ----------------------------------------------------------
echo ""
echo "=== All runs complete ==="
echo "Results: $BASE_DIR"
echo "End:     $(date)"
echo ""
echo "--- Quick summary ---"
echo "Mode           | Runs"
echo "---------------|-----"
echo "bare           | $REPEAT"
echo "pb_nodcu       | $REPEAT"
echo "pb_dcu10       | $REPEAT"
echo "pb_dcu2        | $REPEAT"
