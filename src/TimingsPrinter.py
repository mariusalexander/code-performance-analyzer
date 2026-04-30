from typing import List

from src.Timings import Timings
from src.InstructionBlockDescription import InstructionDescription
from src.MaxPlusAlgebra import DelayExpression


class TimingsPrinter:
    """ 
    Helper class to pretty-print the timings during the analysis. 

    NOTE: 
    - By setting `h_line` to `None`, and `s_spacer` = `w_spacer` = `,` a CSV-compatible table can be printed. 
    - By setting `fprint` to an IO-device, the table can be printed to the disk directly.
    """
    
    @staticmethod
    def is_valid(v):
        return v >= 0 if not isinstance(v, DelayExpression) else len(v) > 0

    @staticmethod
    def to_str(v):
        return str(v) if not isinstance(v, DelayExpression) else v.to_str()

    @staticmethod
    def count_digits(iterable):
        return max(len(TimingsPrinter.to_str(i)) for i in iterable)

    def __init__(self, timings: 'Timings', code_block: 'InstructionBlockDescription', digits=3, s_spacer='|', w_spacer='||', h_line='-', fprint=print):
        self.print     = fprint
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

        self.registers = code_block.target_registers()
        self.register_header = self.__register_column({ reg:f"r{reg}" for reg in self.registers })

        self.timing_vars_entries = { name : len(history) for name, history in timings.timing_vars.items()}
        self.timing_vars_spacing = { name : max(len(self.__simplify_name(name)), 
                                                len(self.__timing_var_column(history, name))
                                                ) for name, history in timings.timing_vars.items() }
        self.register_spacing    = { name : max(len(name),
                                                len(self.register_header)
                                                ) for name in timings.register_models }

    def __digits(self, name):
        if isinstance(self.digits, int):
            return self.digits
        return self.digits[name]

    def __simplify_name(self, name):
        """ Simplifies the name of a timing variable. """
        return name.replace("_stage", "").replace("stage", "").replace("CUSTOM", "cstm")

    def __timing_var_column(self, history, name):
        """" Generates the columns for the history of a timing variable."""
        digits = self.__digits(name)
        return self.s_spacer.join(f'{TimingsPrinter.to_str(value).rjust(digits)}' if TimingsPrinter.is_valid(value) \
            else f'{'-':>{digits}}' for value in history)

    def __register_column(self, model):
        """" Generates the columns for the given register model. """
        return self.s_spacer.join(f'{TimingsPrinter.to_str(model[reg]).rjust(self.__digits(reg))}' if reg in model \
            else f'{'-':>{self.__digits(reg)}}' for reg in self.registers)

    @staticmethod
    def print_history(code_block: 'InstructionBlockDescription',
                      timings_history: List['Timings'],
                      stall_history: List[int] = [],
                      s_spacer='|', w_spacer='||', h_line='-',
                      fprint=print):
        """ Static method. Can be used to print the timings for a code block timings in one go. """

        if len(timings_history) == 0:
            return
        if stall_history:
            assert len(stall_history) == len(timings_history), "Invalid stall history!"

        # filter out columns with no values
        timings_header = timings_history[-1].copy()
        timings_header.timing_vars = { name : history for name, history in timings_header.timing_vars.items()
                                                      if any(TimingsPrinter.is_valid(value) for value in history) }

        # determine how many digits are necessary per column
        digits  = { name: TimingsPrinter.count_digits(value for value in values)
                        for name, values in timings_header.timing_vars.items() }
        digits |= { reg: max(3, TimingsPrinter.count_digits(model[reg] for model in timings_header.register_models.values()))
                        for reg in code_block.target_registers() }

        # print table
        table = TimingsPrinter(timings=timings_header, code_block=code_block, digits=digits,
                               s_spacer=s_spacer, w_spacer=w_spacer, h_line=h_line, fprint=fprint)
        table.print_header()
        for instr_idx, [timing, instr] in enumerate(zip(timings_history, code_block.instructions)):
            stall_cycles = stall_history[instr_idx] if stall_history else 0
            table.print_row(timings=timing, instr_name=instr.name, instr_idx=instr_idx, stall_cycles=stall_cycles)

    def print_header(self):
        # omit indicies for the history of a timing variable if its capacity is one
        generate_timing_var_columns = lambda name: range(1, self.timing_vars_entries[name] + 1) if self.timing_vars_entries[name] > 1 else []

        header_row1  = f"index {self.s_spacer} instruction {self.w_spacer} "
        header_row2  = f"      {self.s_spacer}             {self.w_spacer} "
        header_row1 += f" {self.t_spacer} ".join(f'{self.__simplify_name(name):>{spacing}}' for name, spacing in self.timing_vars_spacing.items())
        header_row1 += f" {self.w_spacer} "
        header_row2 += f" {self.t_spacer} ".join(self.__timing_var_column(generate_timing_var_columns(name), name).rjust(spacing) for name, spacing in self.timing_vars_spacing.items())
        header_row2 += f" {self.w_spacer} "
        header_row1 += f" {self.w_spacer} ".join(f'{name:>{spacing}}' for name, spacing in self.register_spacing.items())
        header_row2 += f" {self.w_spacer} ".join(self.register_header.rjust(spacing) for spacing in self.register_spacing.values())

        self.print(header_row1)
        self.print(header_row2)
        if self.h_line:
            #self.print("".join(':' if char in (*self.s_spacer, *self.w_spacer) else self.h_line for char in header_row2))
            self.print(self.h_line * len(max(header_row1, header_row2)))

    def print_row(self, timings: 'Timings', instr_name:str, instr_idx:int, stall_cycles=0):
        row =  f"{instr_idx:>4}. {self.s_spacer} {instr_name:>11} {self.w_spacer} "
        row += f" {self.t_spacer} ".join(self.__timing_var_column(timings.timing_vars[name], name).rjust(spacing) for name, spacing in self.timing_vars_spacing.items())
        row += f" {self.w_spacer} "
        row += f" {self.w_spacer} ".join(self.__register_column(timings.register_models[model]).rjust(spacing) for model, spacing in self.register_spacing.items())
        if stall_cycles > 0:
            row += f" (+{stall_cycles} CC)"
        self.print(row)
