import re
from typing import List

from src.Common import dotdict, Print

_ignored_registers_ = set()

class InstructionDescription(dotdict):
    """ Denotes a single instruction. """

    def __init__(self, address:int, instr_name:str, rd:int=None, rs1:int=None, rs2:int=None, imm:int=None):
        super().__init__()
        self.address = address
        self.name    = instr_name
        self.rd      = rd
        self.rs1     = rs1
        self.rs2     = rs2
        self.imm     = imm
        # RV32 and CVA6 specific
        self.Xd      = rd
        self.Xa      = rs1
        self.Xb      = rs2
        # CVA6 clobberModel specific
        self.Cb_in   = rd
        self.Cb_out  = rd

    def registers_to_str(self):
        string = ""
        for entry in ("rd", "rs1", "rs2", "imm"):
            string += f"{entry:>3}={self[entry]:>2}, " if self[entry] else " "*(max(3, len(entry)) + 5)
        if len(string) > 0:
            idx = string.rindex(", ")
            string = string[:idx]
        return string
        
    def __str__(self) -> str:
        return f"{hex(self.address)} {self.name:>8}{self.registers_to_str()}"

    def __repr__(self) -> str:
        return self.__str__()

class InstructionBlockDescription:
    """ Denotes a code block and its instructions. """

    def __init__(self, name:str, starting_address:int=0x0):
        self.name = name
        self.starting_address = starting_address
        self.instructions = []

    def __str__(self) -> str:
        return f"code block '{self.name}' ({hex(self.starting_address)}), {len(self.instructions)} instructions:\n " + \
                "\n ".join(f"{" " * Print.indent}{(instr.address - self.starting_address) // 4:>3}. {instr}" for instr in self.instructions)

    def __repr__(self) -> str:
        return self.__str__()

    def addInstruction(self, instr_name, rd=None, rs1=None, rs2=None, imm=None, address=None, **kwargs):
        if address is None:
            address = self.starting_address + (4 * len(self.instructions))
        instr = InstructionDescription(address, instr_name, rd=rd, rs1=rs1, rs2=rs2, imm=imm)
        for register in (arg for arg in kwargs if arg not in _ignored_registers_):
            print(f"{" " * Print.indent}> WARNING: ignoring all occurrences of register '{register}' " + \
                  f"(instr: {instr_name}, idx: {len(self.instructions)})")
            _ignored_registers_.add(register)
        self.instructions.append(instr)

    def has_valid_instructions(self):
        for instr in self.instructions:
            match instr.name:
                case "j", "mret" | "call" | "ret" | "ecall" | "fence":
                    return False
        return True

    def is_basic_block(self, is_basic_block=True):
        for instr in self.instructions[:-1]:
            match instr.name:
                case "j" | "jal" | "jalr" | "beq" | "bne" | "blt" | "bltu" | "bge" | "bgeu":
                    # only last instruction may be a branch
                    return False
        return True

    @staticmethod
    def parse_stringlist(raw_instructions:List['str'], name:str, address_start:int) -> 'InstructionBlockDescription':
        desc = InstructionBlockDescription(name, address_start)
        printed = False
        for raw_instructions in raw_instructions:
            if len(raw_instructions.strip()) == 0:
                continue
            address = re.search(r"0x[a-z0-9]{7}\s", raw_instructions)
            if address:
                address = int(address.group().strip(), 16)
            elif not printed:
                print(f"{" " * Print.indent}> WARNING: cannot determine pc of instruction (instr. idx = {len(desc.instructions)})")
                printed = True
            instr_name = re.search(r"\s([a-z][a-z0-9]*?)+\s", raw_instructions).group().strip()
            registers  = re.findall(r"([a-z][a-z0-9]+)=(\d+)", raw_instructions)
            registers  = { r[0]:int(r[1]) for r in registers }
            desc.addInstruction(instr_name, address=address, **registers)
        return desc