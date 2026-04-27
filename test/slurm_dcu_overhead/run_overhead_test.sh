#!/usr/bin/env bash
# Batch driver for measuring PerfBench overhead on SLURM + DCU.
#
# Usage:
#   bash run_overhead_test.sh [repeat]
#
# Optional environment overrides:
#   PROJ_ROOT=/path/to/PerfBench-BUAAHPC
#   WORKLOAD=/path/to/overhead_bare.slurm
#   OUTPUT_ROOT=/path/to/results_parent
#   LOGIN_INTERVAL=10
#   DCU_INTERVAL_STD=10
#   DCU_INTERVAL_FAST=2

set -euo pipefail

REPEAT=${1:-5}
LOGIN_INTERVAL=${LOGIN_INTERVAL:-10}
DCU_INTERVAL_STD=${DCU_INTERVAL_STD:-10}
DCU_INTERVAL_FAST=${DCU_INTERVAL_FAST:-2}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJ_ROOT=${PROJ_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}
PERFBENCH=${PERFBENCH:-"${PROJ_ROOT}/perfbench.py"}
WORKLOAD=${WORKLOAD:-"${SCRIPT_DIR}/overhead_bare.slurm"}
OUTPUT_ROOT=${OUTPUT_ROOT:-"${SCRIPT_DIR}"}

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BASE_DIR="${OUTPUT_ROOT}/overhead_results_${TIMESTAMP}"

mkdir -p "$BASE_DIR"

if [[ ! -f "$PERFBENCH" ]]; then
    echo "[ERROR] perfbench launcher not found: $PERFBENCH" >&2
    exit 1
fi

if [[ ! -f "$WORKLOAD" ]]; then
    echo "[ERROR] workload script not found: $WORKLOAD" >&2
    exit 1
fi

echo "=== PerfBench SLURM+DCU overhead benchmark ==="
echo "Project:        $PROJ_ROOT"
echo "Workload:       $WORKLOAD"
echo "Repeats:        $REPEAT"
echo "Login interval: ${LOGIN_INTERVAL}s"
echo "DCU intervals:  ${DCU_INTERVAL_STD}s, ${DCU_INTERVAL_FAST}s"
echo "Output:         $BASE_DIR"
echo "Start:          $(date)"
echo ""

sinfo -N -o "%N %t %f %m %G" > "$BASE_DIR/cluster_snapshot.log" 2>&1 || true

run_bare() {
    local idx=$1
    local out_dir="$BASE_DIR/bare_${idx}"
    mkdir -p "$out_dir"

    echo "  bare run ${idx}/${REPEAT}"
    local t_start t_end jobid_raw jobid
    t_start=$(date +%s.%N)
    jobid_raw=$(sbatch --parsable --wait \
        -o "$out_dir/job_%j.out" \
        -e "$out_dir/job_%j.err" \
        "$WORKLOAD")
    jobid=${jobid_raw%%;*}
    t_end=$(date +%s.%N)

    echo "jobid=$jobid start=$t_start end=$t_end" > "$out_dir/timing.txt"
    sacct -j "$jobid" \
        --format=JobID,JobName%20,State,Elapsed,CPUTimeRAW,MaxRSS,AveRSS,AllocCPUS \
        -P > "$out_dir/sacct.log" 2>&1 || true
    echo "  -> JobID=$jobid done"
}

run_perfbench() {
    local mode=$1
    local idx=$2
    shift 2

    local out_dir="$BASE_DIR/${mode}_${idx}"
    mkdir -p "$out_dir"

    echo "  ${mode} run ${idx}/${REPEAT}"
    local t_start t_end
    t_start=$(date +%s.%N)
    python3 "$PERFBENCH" \
        -s "$WORKLOAD" \
        -t "$LOGIN_INTERVAL" \
        -o "$out_dir" \
        --platform slurm \
        --overhead \
        "$@"
    t_end=$(date +%s.%N)

    echo "start=$t_start end=$t_end" > "$out_dir/timing.txt"
    echo "  -> done"
}

echo "[Phase 1/4] bare: direct sbatch, no PerfBench"
for i in $(seq 1 "$REPEAT"); do
    run_bare "$i"
done

echo ""
echo "[Phase 2/4] pb_nodcu: PerfBench login-node sampling only"
for i in $(seq 1 "$REPEAT"); do
    run_perfbench "pb_nodcu" "$i" --accelerator none
done

echo ""
echo "[Phase 3/4] pb_dcu10: PerfBench login-node sampling + DCU ${DCU_INTERVAL_STD}s"
for i in $(seq 1 "$REPEAT"); do
    run_perfbench "pb_dcu10" "$i" \
        --accelerator dcu \
        --accelerator-interval "$DCU_INTERVAL_STD"
done

echo ""
echo "[Phase 4/4] pb_dcu2: PerfBench login-node sampling + DCU ${DCU_INTERVAL_FAST}s"
for i in $(seq 1 "$REPEAT"); do
    run_perfbench "pb_dcu2" "$i" \
        --accelerator dcu \
        --accelerator-interval "$DCU_INTERVAL_FAST"
done

echo ""
echo "=== All runs complete ==="
echo "Results: $BASE_DIR"
echo "End:     $(date)"
echo ""
echo "Analyze with:"
echo "  python3 ${SCRIPT_DIR}/analyze_overhead.py ${BASE_DIR}"
