from src.Common import dotdict

class InstructionBlockDescription:
    """Denotes a code block and its instructions."""

    def __init__(self, name, starting_address=0x0):
        self.name = name
        self.starting_address = starting_address
        self.instructions = []

    def __str__(self) -> str:
        return f"code block '{self.name}' ({hex(self.starting_address)}), {len(self.instructions)} instructions:\n " + \
                ("\n ".join([str(r) for r in self.instructions]))

    def __repr__(self) -> str:
        return self.__str__()

    def addInstruction(self, instr_name, rd=None, rs1=None, rs2=None, imm=None, **kwargs):
        instr = dotdict({
            "address": self.starting_address + (4 * len(self.instructions)),
            "name": instr_name,
            "rd"  : rd,
            "rs1" : rs1,
            "rs2" : rs2,
            "imm" : imm,
            # RV32 and CVA6 specific
            "Xd"  : rd,
            "Xa"  : rs1,
            "Xb"  : rs2,
            # CVA6 clobberModel specific
            "Cb_in" : rd,
            "Cb_out" : rd,
        })
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