import os
import sys
import time

# wrapper to support dot-notation on dictionaries
# (see https://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary)
class dotdict(dict):
    """Allows using 'dot.notation' to access dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

# temporarily disables output of the builtin `print` function
# (see https://stackoverflow.com/questions/8391411/how-to-block-calls-to-print)
class PrintDisabled:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, *args):
        sys.stdout.close()
        sys.stdout = self._original_stdout

# logs time taken for a code block
class Profile:
    def __init__(self, text: str):
        self.text  = text

    def __enter__(self):
        self.start = time.perf_counter_ns()

    def __exit__(self, *args):
        self.end  = time.perf_counter_ns()
        print(f"{self.text} took {(self.end - self.start) / 1_000_000}ms!")

# global variable for setting the indentation
class Print:
    indent:int = 0
