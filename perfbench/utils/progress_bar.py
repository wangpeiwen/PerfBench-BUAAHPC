# -*- coding: utf-8 -*-
import sys
import time

def simple_progress_bar(current, total, status_text=""):
    bar_len = 40
    filled_len = int(round(bar_len * current / float(total)))
    percents = round(100.0 * current / float(total), 1)
    bar = '█' * filled_len + '-' * (bar_len - filled_len)
    sys.stdout.write(f'\r[{bar}] {percents}% {status_text}')
    sys.stdout.flush()
    if current == total:
        sys.stdout.write('\n')
        sys.stdout.flush()

# 用于CLI主流程的阶段式进度条
class StepProgress:
    def __init__(self, steps):
        self.steps = steps
        self.current = 0
    def next(self, status=None):
        self.current += 1
        if self.current > len(self.steps):
            self.current = len(self.steps)
        self.show(status)
    def show(self, status=None):
        step_text = f"步骤 {self.current}/{len(self.steps)}: {self.steps[self.current-1]}"
        if status:
            step_text += f" | {status}"
        simple_progress_bar(self.current, len(self.steps), step_text)
    def finish(self):
        self.current = len(self.steps)
        self.show("完成")
        sys.stdout.write('\n')
        sys.stdout.flush()
