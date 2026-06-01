import os
import tempfile
import unittest

from perfbench.adapters.platform.slurm import SlurmAdapter


class SlurmOutputCaptureTests(unittest.TestCase):
    def prepare(self, script_text):
        with tempfile.TemporaryDirectory() as tmp:
            script_path = os.path.join(tmp, "job.slurm")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(script_text)

            adapter = SlurmAdapter()
            modified = adapter.prepare_script(script_path, {}, 10, tmp)
            with open(modified, "r", encoding="utf-8") as handle:
                modified_text = handle.read()
            return tmp, modified_text

    def test_rewrites_existing_slurm_stdout_stderr(self):
        tmp, modified = self.prepare(
            "#!/bin/bash\n"
            "#SBATCH -J demo\n"
            "#SBATCH -o old_%j.out\n"
            "#SBATCH -e old_%j.err\n"
            "srun ./app\n"
        )

        self.assertIn(
            f"#SBATCH --output={os.path.abspath(tmp)}{os.sep}slurm_%j.out",
            modified,
        )
        self.assertIn(
            f"#SBATCH --error={os.path.abspath(tmp)}{os.sep}slurm_%j.err",
            modified,
        )
        self.assertNotIn("old_%j.out", modified)
        self.assertNotIn("old_%j.err", modified)

    def test_adds_slurm_stdout_stderr_when_missing(self):
        tmp, modified = self.prepare(
            "#!/bin/bash\n"
            "#SBATCH -J demo\n"
            "#SBATCH -N 1\n"
            "srun ./app\n"
        )

        self.assertIn(
            f"#SBATCH --output={os.path.abspath(tmp)}{os.sep}slurm_%j.out",
            modified,
        )
        self.assertIn(
            f"#SBATCH --error={os.path.abspath(tmp)}{os.sep}slurm_%j.err",
            modified,
        )


if __name__ == "__main__":
    unittest.main()
