import re
import json
import copy
from typing import List
from objprint import op

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

    def is_branch(self):
        match self.name:
            # jump and branch instructions
            case "jal" | "jalr" | "beq" | "bne" | "blt" | "bltu" | "bge" | "bgeu":
                return True
        return False

    def is_valid(self):
        match self.name:
            # pseudo instructions/instruction not fully implemented
            case "j" | "mret" | "call" | "ret" | "ecall" | "fence":
                return False
        return True

    def __str__(self) -> str:
        return f"{hex(self.address)} {self.name:>8}{self.registers_to_str()}"

    def __repr__(self) -> str:
        return self.__str__()


class InstructionBlockDescription:
    """ Denotes a code block and its instructions. """

    def __init__(self, name:str, starting_address:int=0x0):
        self.name = name
        self.starting_address = starting_address
        # relative weight of the code block for CPI analysis
        self.weight           = None
        # dictionary to map dynamic variables to an delay
        self.dynamic_vars     = {}
        # list of instructions in code block
        self.instructions     = []

    def __str__(self) -> str:
        header   = f"code block '{self.name}' (0x{self.starting_address:08x}), {len(self.instructions)} instructions, {f"{self.weight * 100:2.2f}% weight" if self.weight else ""}:"
        instrs   = "\n ".join(f"{" " * Print.indent}{idx:>3}. {instr}" for idx, instr in enumerate(self.instructions))
        dyn_vars = "\n ".join(f"{" " * Print.indent}  {name}: {value:.4f}" for name,value in self.dynamic_vars.items())
        return f"{header}\n {instrs}" + (f"\n {" " * Print.indent}with:\n {dyn_vars}" if self.dynamic_vars else "")

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

    def target_registers(self):
        return sorted(set(instr.rd for instr in self.instructions if instr.rd is not None))

    def is_valid_code_block(self):
        return all(i.is_valid() for i in self.instructions)

    def is_basic_block(self, is_basic_block=True):
        return not any(i.is_branch() for i in self.instructions[:-1])

    @staticmethod
    def parse_stringlist(raw_instructions:List['str'], name:str, address_start:int) -> 'InstructionBlockDescription':
        desc = InstructionBlockDescription(name, address_start)
        printed = False
        for raw_instruction in raw_instructions:
            if len(raw_instruction.strip()) == 0:
                continue
            address = re.search(r"^0x[a-z0-9]{8}\s", raw_instruction)
            if address:
                address = int(address.group().strip(), 16)
                if len(desc.instructions) == 0 and address_start == 0:
                    desc.starting_address = address
            elif not printed:
                print(f"{" " * Print.indent}> WARNING: cannot determine address of instruction (instr. idx = {len(desc.instructions)})")
                printed = True
            instr_name = re.search(r"(^|\s)([a-z][a-z0-9]*?)+\s", raw_instruction).group().strip()
            registers  = re.findall(r"([a-z][a-z0-9]+)=(\d+)", raw_instruction)
            registers  = { r[0]:int(r[1]) for r in registers }
            desc.addInstruction(instr_name, address=address, **registers)
        return desc

    @staticmethod
    def load_from_files(files:List['pathlib.Path'], ignore_variants=False, verbose=True):
        code_blocks = []
        weights = {}
        variants = {}
        print(" > loading from files...")

        # read metadata
        if len(files) == 1 and files[0].name.endswith(".json"):
            [file] = files
            path = file.parent
            with open(file, "r") as f:
                data = json.load(f)
            bbs = list(data)
            files   = [ path / bb["name"] for bb in bbs ]
            weights = { bb["name"] : bb["weight"] for bb in bbs }
            if not ignore_variants:
                variants = { bb["name"] : bb["dynamic_delays"] for bb in bbs if "dynamic_delays" in bb}
            assert all(0 <= w <= 1 for w in weights.values())

        # parse files
        for file in files:
            print(f"  > loading from file '{file.name}'...")
            assert file.exists()
            try:
                address_start = int(file.stem, 16)
            except ValueError:
                address_start = 0
            with open(file, "r") as f:
                raw_instructions = f.readlines()
                desc = InstructionBlockDescription.parse_stringlist(raw_instructions, name=file.stem, address_start=address_start)
                if file.name in weights:
                    desc.weight = weights[file.name]
                if file.name in variants:
                    for idx, variant in enumerate(variants[file.name]):
                        code_block_variant = copy.deepcopy(desc)
                        code_block_variant.name        += f"_v{idx}" if len(variants[file.name]) > 1 else ""
                        code_block_variant.weight      *= variant["weight"]
                        code_block_variant.dynamic_vars = variant["variables"]
                        if verbose:
                            print("   >", code_block_variant, "(variant)")
                        assert code_block_variant.weight > 0
                        assert(desc.is_valid_code_block()), f"{desc}"
                        code_blocks.append(code_block_variant)
                    continue

                if verbose:
                    print("   >", desc)
                assert(desc.is_valid_code_block()), f"{desc}"
                code_blocks.append(desc)
        return code_blocks