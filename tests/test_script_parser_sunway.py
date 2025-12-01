import tempfile
from perfbench.utils.script_parser import parse_sunway_script


def test_parse_sunway_script_basic():
    script = '''#!/bin/bash
JOB_NAME="sw_cg_monitor"
QUEUE_NAME="q_linpack"
NODES=2
MASTER_CORES=6
EXEC_CMD="/home/export/somebinary"
LOG_DIR="/tmp/perf_logs"
INTERVAL=3
'''
    with tempfile.NamedTemporaryFile('w', delete=False) as tmp:
        tmp.write(script)
        fname = tmp.name
    info = parse_sunway_script(fname)
    assert info['job_name'] == 'sw_cg_monitor'
    assert info['nodes'] == 2
    assert info['master_cores'] == 6
    assert info['queue_name'] == 'q_linpack'
    assert info['log_dir'] == '/tmp/perf_logs'
    assert info['interval'] == 3
