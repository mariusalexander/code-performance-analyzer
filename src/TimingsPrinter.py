from typing import List

from src.Timings import Timings
from src.InstructionBlockDescription import InstructionDescription


class TimingsPrinter:
    """ Helper class to pretty-print the timings during the analysis. """
    
    def __init__(self, timings: 'Timings', code_block: 'InstructionBlockDescription', digits=3, s_spacer='|', w_spacer='||', h_line='-'):
        # default spacer 
        self.s_spacer  = s_spacer 
        # spacer inbetween timing variables
        self.t_spacer  = w_spacer if any(len(values) > 1 for values in timings.timing_vars.values()) else s_spacer
        # spacer for other connector models
        self.w_spacer  = w_spacer
        # character for drawing horizontal line (line omitted if character is empty)
        self.h_line    = h_line
        # spacing for each column in digits
        self.digits    = digits

        self.registers = sorted(set(instr.rd for instr in code_block.instructions if instr.rd is not None))
        self.register_header = self.__register_column({ reg:f"r{reg}" for reg in self.registers })
        self.timing_vars_entries = { name : len(history) for name, history in timings.timing_vars.items()}
        self.timing_vars_spacing = { name : max(len(self.__simplify_name(name)), len(self.__timing_var_column(history))) for name, history in timings.timing_vars.items() }
        self.register_spacing    = { name : max(len(name), len(self.register_header)) for name in timings.register_models }

    def __simplify_name(self, name):
        """ Simplifies the name of a timing variable. """
        return name.replace("_stage", "").replace("stage", "").replace("CUSTOM", "cstm")

    def __timing_var_column(self, history):
        """" Generates the columns for the history of a timing variable."""
        return self.s_spacer.join(f'{value:>{self.digits}}' if value >= 0 else f'{'-':>{self.digits}}' for value in history)

    def __register_column(self, model):
        """" Generates the columns for the given register model. """
        return self.s_spacer.join(f'{model[reg]:>{self.digits+1}}' if reg in model else f'{'-':>{self.digits+1}}' for reg in self.registers)

    @staticmethod
    def print_history(timings_history: List['Timings'], code_block: 'InstructionBlockDescription', s_spacer='|', w_spacer='||', h_line='-', fprint=print):
        if len(timings_history) == 0: 
            return

        # determine how many digits are necessary
        digits = len(str(max(value for timing in timings_history for values in timing.timing_vars.values() for value in values)))
        # filter out columns with no values
        timings_header = timings_history[0].copy()
        timings_header.timing_vars = { name : history for name, history in timings_header.timing_vars.items() if any(value >= 0 for value in history) }

        table = TimingsPrinter(timings=timings_header, code_block=code_block, digits=digits, s_spacer=s_spacer, w_spacer=w_spacer, h_line=h_line)
        table.print_header(fprint=fprint)
        for idx, [timing, instr] in enumerate(zip(timings_history, code_block.instructions)):
            table.print_row(timings=timing, instr_name=instr.name, idx=idx, fprint=fprint)

    def print_header(self, fprint=print):
        # ommit indicies for the history of a timing variable if its capacity is one
        generate_timing_var_columns = lambda name: range(1, self.timing_vars_entries[name] + 1) if self.timing_vars_entries[name] > 1 else []

        header_row1  = f"index {self.s_spacer} instruction {self.w_spacer} "
        header_row2  = f"      {self.s_spacer}             {self.w_spacer} "
        header_row1 += f" {self.t_spacer} ".join(f'{self.__simplify_name(name):>{spacing}}' for name, spacing in self.timing_vars_spacing.items())
        header_row1 += f" {self.w_spacer} "
        header_row2 += f" {self.t_spacer} ".join(self.__timing_var_column(generate_timing_var_columns(name)).rjust(spacing) for name, spacing in self.timing_vars_spacing.items())
        header_row2 += f" {self.w_spacer} "
        header_row1 += f" {self.w_spacer} ".join(f'{name:>{spacing}}' for name, spacing in self.register_spacing.items())
        header_row2 += f" {self.w_spacer} ".join(self.register_header.rjust(spacing) for spacing in self.register_spacing.values())

        fprint(header_row1)
        fprint(header_row2)
        if self.h_line:
            #fprint("".join(':' if char in (*self.s_spacer, *self.w_spacer) else self.h_line for char in header_row2))
            fprint(self.h_line * len(max(header_row1, header_row2)))

    def print_row(self, timings: 'Timings', instr_name:str, idx:int, fprint=print):
        row =  f"{idx:>4}. {self.s_spacer} {instr_name:>11} {self.w_spacer} "
        row += f" {self.t_spacer} ".join(self.__timing_var_column(timings.timing_vars[name]).rjust(spacing) for name, spacing in self.timing_vars_spacing.items())
        row += f" {self.w_spacer} "
        row += f" {self.w_spacer} ".join(self.__register_column(timings.register_models[model]).rjust(spacing) for model, spacing in self.register_spacing.items())
        fprint(row)
