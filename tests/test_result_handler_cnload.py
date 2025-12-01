import os
import tempfile
from perfbench.utils.result_handler import Result


SAMPLE_CNLOAD = '''+=========================================================================================================================================================+
 NODE_ID   CPUID  STRUCT_NO   IP_ADDRESS      STATUS     UPTIME         1'LOAD MPES SPES MPEMEM SPEMEM NI0_STATE   NI1_STATE   GFS_STATE ATTR  QUEUEID
=========================================================================================================================================================+
 vn000012  12     0:0:3:0     100.0.3.1       busy      11Day 00:12      3.64   6    384  1000M   3.5G OK          OK          1,2ok     exclu q_linpack
        +-------------+--------------------+--------------------+
        |    MiniOS   |     ValidBitmap    |    EmployBitmap    |
        +-------------+--------------------+--------------------+
        |     MPE     | 0x000000000000003F | 0x000000000000003F |
        +-------------+--------------------+--------------------+
        |     SPE0    | 0xFFFFFFFFFFFFFFFF | 0xFFFFFFFFFFFFFFFF |
        |     SPE1    | 0xFFFFFFFFFFFFFFFF | 0xFFFFFFFFFFFFFFFF |
        |     SPE2    | 0xFFFFFFFFFFFFFFFF | 0xFFFFFFFFFFFFFFFF |
        |     SPE3    | 0xFFFFFFFFFFFFFFFF | 0xFFFFFFFFFFFFFFFF |
        |     SPE4    | 0xFFFFFFFFFFFFFFFF | 0xFFFFFFFFFFFFFFFF |
        |     SPE5    | 0xFFFFFFFFFFFFFFFF | 0xFFFFFFFFFFFFFFFF |
        +-------------+--------------------+--------------------+
'''


def test_parse_cnload_bitmap_counts():
    tmpdir = tempfile.mkdtemp()
    fname = os.path.join(tmpdir, 'cnload_b_job_3508759_20251201_120000.log')
    with open(fname, 'w') as f:
        f.write(SAMPLE_CNLOAD)
    r = Result(cmd_name='cnload', out_dir=tmpdir, interval=3)
    # parse_log_files runs parse_cnload_bitmap in __init__, ensure data exists
    assert r.data, 'no parsed data'
    # There should be one row
    row = r.data[0]
    # MPE active bits = 6, SPE0-SPE5 each 64 => total_active = 6 + 6*64
    expected_active = 6 + 6*64
    assert row['total_active'] == expected_active
    # group_size computation uses hex width * 4 bits; MPE may present as 16-hex digits => 64 bits
    expected_total_bits = 7 * 64
    assert row['total_bits'] == expected_total_bits
    # utilization should be expected_active / expected_total_bits * 100
    expected_util = round(100.0 * expected_active / expected_total_bits, 2)
    assert row['utilization_percent'] == expected_util
