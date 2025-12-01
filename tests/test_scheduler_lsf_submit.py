import os
import tempfile
from unittest import mock
from perfbench.utils.scheduler import submit_job_lsf


def test_submit_job_lsf_success(tmp_path, monkeypatch):
    # Create a dummy script file
    script_file = tmp_path / 'dummy.sh'
    script_file.write_text('#!/bin/bash\necho hello')

    class DummyResult:
        def __init__(self):
            self.stdout = 'Job <12345> is submitted to queue default.'
            self.stderr = ''
            self.returncode = 0

    # Mock subprocess.run to return DummyResult
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: DummyResult())

    jobid = submit_job_lsf(str(script_file))
    assert jobid == '12345'
