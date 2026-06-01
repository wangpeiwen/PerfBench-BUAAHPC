#!/bin/bash

#SBATCH -J kernel_smoke
#SBATCH -N 1
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=7
#SBATCH --gres=dcu:4
#SBATCH -p normal
#SBATCH -o kernel_smoke_%j.out
#SBATCH -e kernel_smoke_%j.err

module purge
module load  apps/lammps-DCU/2Aug2023/hpcx-2.7.4-dtk23.10

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}

REPO_ROOT="${PERFBENCH_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}"
INPUT_FILE="${PERFBENCH_LAMMPS_INPUT:-${REPO_ROOT}/test/slurm_dcu_overhead/kernel_smoke_in.lj}"

if [ ! -f "$INPUT_FILE" ]; then
  echo "[ERROR] LAMMPS input not found: $INPUT_FILE" >&2
  echo "[ERROR] Set PERFBENCH_REPO_ROOT or PERFBENCH_LAMMPS_INPUT before submitting." >&2
  exit 2
fi

echo "KERNEL_SMOKE_START=$(date +%s.%N)"
echo "SLURM_JOB_ID=$SLURM_JOB_ID"
echo "SLURM_JOB_NODELIST=$SLURM_JOB_NODELIST"
echo "INPUT_FILE=$INPUT_FILE"
echo "ROCPROFV3=$(command -v rocprofv3 || true)"

# PERFBENCH_PROFILE_TARGET
mpirun __PERFBENCH_PROFILE__ lmp_mpi -sf gpu -pk gpu 4 -in "$INPUT_FILE"

echo "KERNEL_SMOKE_END=$(date +%s.%N)"
