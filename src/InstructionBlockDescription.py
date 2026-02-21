from src.Common import dotdict


class InstructionDescription(dotdict):
    """ Denotes a single instruction. """

    def __init__(self, address, instr_name, rd=None, rs1=None, rs2=None, imm=None):
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
        for entry in ["rd", "rs1", "rs2", "imm"]:
            string += f"{entry:>3}={self[entry]:>2}, " if self[entry] else " "*(max(3, len(entry)) + 4)
        if len(string) > 0:
            idx = string.rindex(", ")
            string = string[:idx]
        return string
        
    def __str__(self) -> str:
        return f"0x{hex(self.address)} {self.name:<4}{self.registers_to_str()}"

    def __repr__(self) -> str:
        return self.__str__()

class InstructionBlockDescription:
    """ Denotes a code block and its instructions. """

    def __init__(self, name, starting_address=0x0):
        self.name = name
        self.starting_address = starting_address
        self.instructions = []

    def __str__(self) -> str:
        return f"code block '{self.name}' ({hex(self.starting_address)}), {len(self.instructions)} instructions:\n " + \
                "\n ".join([f"{(instr.address - self.starting_address) // 4:>3}. {instr}" for instr in self.instructions])

    def __repr__(self) -> str:
        return self.__str__()

    def addInstruction(self, instr_name, rd=None, rs1=None, rs2=None, imm=None, **kwargs):
        address = self.starting_address + (4 * len(self.instructions))
        instr = InstructionDescription(address, instr_name, rd=rd, rs1=rs1, rs2=rs2, imm=imm)
        for i in kwargs:
            print(f" > ignoring register '{i}': {kwargs[i]}!")
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