#!/bin/bash

#SBATCH -J overhead_bare
#SBATCH -N 10
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=7
#SBATCH --exclusive
#SBATCH --gres=dcu:4
#SBATCH -p normal
#SBATCH -o overhead_bare_%j.out
#SBATCH -e overhead_bare_%j.err

module purge
module load  apps/lammps-DCU/2Aug2023/hpcx-2.7.4-dtk23.10

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

echo "OVERHEAD_TEST_START=$(date +%s.%N)"
echo "SLURM_JOB_ID=$SLURM_JOB_ID"
echo "SLURM_JOB_NODELIST=$SLURM_JOB_NODELIST"

mpirun lmp_mpi -sf gpu -pk gpu 4 -in /public/home/buaahpc/retro/PerfBench-BUAAHPC/test/slurm_dcu_overhead/1m_in.lj

echo "OVERHEAD_TEST_END=$(date +%s.%N)"
