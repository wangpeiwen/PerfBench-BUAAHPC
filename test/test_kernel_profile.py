import json
import os
import tempfile
import unittest

from perfbench.core.job_runner import run_evaluation
from perfbench.profile.base import KernelProfileConfig, parse_counter_groups
from perfbench.profile.isa_analyzer import analyze_isa_dump
from perfbench.profile.rocprofv3 import RocprofV3Backend
from perfbench.profile.script_transform import (
    ProfileScriptError,
    validate_profile_markers,
)


SCRIPT = """#!/bin/bash
#SBATCH --job-name=kp
# PERFBENCH_PROFILE_TARGET
srun -n 2 __PERFBENCH_PROFILE__ ./app input
"""


class KernelProfileTests(unittest.TestCase):
    def write_script(self, directory, content=SCRIPT):
        path = os.path.join(directory, "job.slurm")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_marker_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = self.write_script(tmp)
            validate_profile_markers(valid)

            missing = self.write_script(
                tmp,
                "#!/bin/bash\nsrun -n 1 __PERFBENCH_PROFILE__ ./app\n",
            )
            with self.assertRaises(ProfileScriptError):
                validate_profile_markers(missing)

            duplicate = self.write_script(tmp, SCRIPT + "__PERFBENCH_PROFILE__ echo\n")
            with self.assertRaises(ProfileScriptError):
                validate_profile_markers(duplicate)

    def test_formal_and_profile_script_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.write_script(tmp)
            backend = RocprofV3Backend(
                KernelProfileConfig(counters="SQ_WAVES;GRBM_GUI_ACTIVE")
            )

            formal = backend.inject_formal_run(source, tmp)
            with open(formal, encoding="utf-8") as handle:
                formal_text = handle.read()
            self.assertIn("ROCM_DUMP_ISA=1", formal_text)
            self.assertIn("ROCM_DUMP_ISA_DIR=", formal_text)
            self.assertNotIn("__PERFBENCH_PROFILE__", formal_text)

            profile_dir = os.path.join(tmp, "kernel_profile")
            profile = backend.inject_profile_run(source, profile_dir)
            with open(profile, encoding="utf-8") as handle:
                profile_text = handle.read()
            launcher = os.path.join(profile_dir, "perfbench_profile_launcher.sh")
            self.assertIn("PERFBENCH_PROFILE_RUN=1", profile_text)
            self.assertIn(launcher, profile_text)
            self.assertNotIn("__PERFBENCH_PROFILE__", profile_text)

            with open(launcher, encoding="utf-8") as handle:
                launcher_text = handle.read()
            self.assertIn("rocprofv3", launcher_text)
            self.assertIn("--pmc 'SQ_WAVES'", launcher_text)
            self.assertIn("SLURM_PROCID", launcher_text)

    def test_counter_group_parsing(self):
        self.assertEqual(
            parse_counter_groups("SQ_WAVES, GRBM_GUI_ACTIVE; SQ_INSTS_VALU"),
            ["SQ_WAVES,GRBM_GUI_ACTIVE", "SQ_INSTS_VALU"],
        )
        self.assertEqual(
            parse_counter_groups(" ; "),
            ["SQ_WAVES,GRBM_GUI_ACTIVE"],
        )

    def test_isa_analyzer(self):
        with tempfile.TemporaryDirectory() as tmp:
            isa_dir = os.path.join(tmp, "isa_dump")
            os.makedirs(isa_dir)
            with open(os.path.join(isa_dir, "kernel_1.isa"), "w", encoding="utf-8") as handle:
                handle.write(
                    "NumVgprs: 96\n"
                    "NumSgprs: 48\n"
                    "v_add_f32 v0, v1, v2\n"
                    "global_load_dword v3, v[0:1]\n"
                    "ds_write_b32 v4, v5\n"
                    "s_cbranch_scc1 label\n"
                    "s_waitcnt vmcnt(0)\n"
                )

            output = os.path.join(tmp, "summary.json")
            summary = analyze_isa_dump(isa_dir, output)
            self.assertEqual(summary["file_count"], 1)
            kernel = summary["kernels"][0]
            self.assertEqual(kernel["categories"]["valu"], 1)
            self.assertEqual(kernel["categories"]["vmem"], 1)
            self.assertEqual(kernel["categories"]["lds"], 1)
            self.assertEqual(kernel["metadata"]["vgpr_count"], 96)
            self.assertEqual(kernel["hints"]["register_pressure"], "high")
            self.assertTrue(os.path.exists(output))

    def test_rocprof_csv_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = os.path.join(tmp, "job")
            profile_dir = os.path.join(job_dir, "kernel_profile")
            rocprof_dir = os.path.join(profile_dir, "rocprof")
            os.makedirs(rocprof_dir)
            os.makedirs(os.path.join(job_dir, "isa_dump"))

            with open(
                os.path.join(rocprof_dir, "counter_collection.csv"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    "KernelName,SQ_WAVES,GRBM_GUI_ACTIVE\n"
                    "kernel_a,10,20\n"
                    "kernel_a,30,40\n"
                )

            backend = RocprofV3Backend(KernelProfileConfig())
            summary = backend.parse_outputs(job_dir, profile_dir)
            self.assertEqual(summary["rocprof"]["file_count"], 1)
            kernel = summary["rocprof"]["kernels"][0]
            self.assertEqual(kernel["kernel"], "kernel_a")
            self.assertEqual(kernel["samples"], 2)
            self.assertEqual(kernel["metrics"]["SQ_WAVES"]["mean"], 20.0)

            summary_path = os.path.join(profile_dir, "kernel_profile_summary.json")
            with open(summary_path, "r", encoding="utf-8") as handle:
                persisted = json.load(handle)
            self.assertEqual(persisted["backend"], "rocprofv3")

    def test_job_runner_uses_script_transformer(self):
        class Progress:
            def next(self, *args, **kwargs):
                return None

        class Adapter:
            def __init__(self):
                self.prepared_source = None

            def parse_script(self, script_path):
                return {"job_name": "mock", "nodes": 1}

            def prepare_script(self, script_path, script_info, interval, output_dir):
                self.prepared_source = script_path
                return script_path

            def submit_job(self, script_path):
                return "42"

            def start_monitoring(self, jobid, interval, output_dir):
                return 1

            def wait_for_job(self, jobid):
                return "COMPLETED"

            def capture_final_logs(self, jobid, output_dir):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            source = self.write_script(tmp)
            transformed = os.path.join(tmp, "transformed.slurm")
            adapter = Adapter()

            def transformer(script_path, script_info, interval, job_dir):
                with open(transformed, "w", encoding="utf-8") as handle:
                    handle.write("#!/bin/bash\n")
                return transformed

            run_evaluation(
                source,
                10,
                tmp,
                adapter,
                Progress(),
                script_transformer=transformer,
            )
            self.assertEqual(adapter.prepared_source, transformed)


if __name__ == "__main__":
    unittest.main()
