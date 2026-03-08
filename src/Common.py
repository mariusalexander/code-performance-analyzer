import os
import sys
import time

# The pc_np path has no effect if branch prediction predicts correctly.
def twos_complement(val, bits):
    """ compute the 2's complement of int value """
    if (val & (1 << (bits - 1))) != 0: # if sign bit is set e.g., 8bit: 128-255
        val = val - (1 << bits)        # compute negative value
    return val                         # return positive value as is

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

    # creates a scope for which the indentation can be temporarily altered
    class indent_scope:
        def __init__(self, new_indent:int):
            self.new_indent = new_indent

        def __enter__(self):
            self.old_indent = Print.indent
            Print.indent = self.new_indent

        def __exit__(self, *args):
            Print.indent = self.old_indent

