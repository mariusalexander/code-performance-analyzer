import fnmatch

from src.InstructionBlockDescription import InstructionBlockDescription

class RISCVAbiRegisters:
    """Maps 32bit RISC-V ABI register names onto their actual register numbers."""

    def __init__(self):
        self.zero = 0
        self.ra = 1
        self.sp = 2
        self.gp = 3
        self.tp = 4
        self.t0 =  5; self.t1 =  6; self.t2 =  7
        self.t3 = 28; self.t4 = 29; self.t5 = 30; self.t6  = 31
        self.s0 =  8; self.s1 =  9
        self.a0 = 10; self.a1 = 11; self.a2 = 12; self.a3  = 13
        self.a4 = 14; self.a5 = 15; self.a6 = 16; self.a7  = 17
        self.s2 = 18; self.s3 = 19; self.s4 = 20; self.s5  = 21; self.s6  = 22
        self.s7 = 23; self.s8 = 24; self.s9 = 25; self.s10 = 26; self.s11 = 27


def test_vectors(pattern=None):
    r = RISCVAbiRegisters()

    code_blocks      = []
    desc = InstructionBlockDescription("bb_custom_example", 0x100047c)
    desc.addInstruction("addi", rd =r.sp  , rs1=r.sp, imm=(-0x1b0))
    desc.addInstruction("sw"  , rs1=r.s0  , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s1  , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s2  , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s3  , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s4  , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s5  , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s6  , rs2=r.sp)
    desc.addInstruction("sw"  , rs1=r.s7  , rs2=r.sp)
    desc.addInstruction("lui" , rd =r.a0  ,           imm=(0x1800))
    desc.addInstruction("addi", rd =r.a0  , rs1=r.a0, imm=(0x760))
    desc.addInstruction("bge" , rs1=r.zero, rs2=r.a1, imm=(0x1000644))
    code_blocks.append(desc)

    desc = InstructionBlockDescription("bb_ppt_example", 0x100047c)
    desc.addInstruction("andi", rd =15, rs1=15)
    desc.addInstruction("slli", rd =15, rs1=15)
    desc.addInstruction("add" , rd =15, rs1=18, rs2=15)
    desc.addInstruction("lw"  , rd =15, rs1=15)
    desc.addInstruction("srli", rd = 8, rs1= 8)
    desc.addInstruction("addi", rd = 9, rs1= 9)
    desc.addInstruction("xor" , rd = 8, rs1=15, rs2= 8)
    desc.addInstruction("bne" , rs1= 9, rs2= 0, imm=8080)
    code_blocks.append(desc)

    desc = InstructionBlockDescription("bb_triple_add", 0x000003c4)
    desc.addInstruction("addi", rd=15, rs1=15, imm=255)
    desc.addInstruction("add" , rd=16, rs1=15, rs2=7)
    desc.addInstruction("add" , rd=15, rs1=15, rs2=16)
    code_blocks.append(desc)

    desc = InstructionBlockDescription("bb_load_incr_store", 0x000003c4)
    desc.addInstruction("lw"  , rd =3, rs1=2)
    desc.addInstruction("addi", rd =4, rs1=3, imm=1)
    desc.addInstruction("sw"  , rs1=2, rs2=4)
    code_blocks.append(desc)

    desc = InstructionBlockDescription("bb_mul_dd", 0x000003c4)
    desc.addInstruction("mul" , rd=1, rs1=10, rs2=11)
    desc.addInstruction("add" , rd=2, rs1=10, rs2=11)
    desc.addInstruction("add" , rd=3, rs1=10, rs2=11)
    desc.addInstruction("add" , rd=4, rs1= 1, rs2=11)
    code_blocks.append(desc)

    desc = InstructionBlockDescription("bb_test", 0x000003c4)
    desc.addInstruction("mul" , rd=1, rs1=10, rs2=11)
    desc.addInstruction("mul" , rd=2, rs1=10, rs2=11)
    code_blocks.append(desc)

    assert all(block.is_basic_block() for block in code_blocks)
    assert all(block.has_valid_instructions() for block in code_blocks)

    if pattern is not None:
        code_blocks = [block for block in code_blocks if fnmatch.fnmatch(block.name, pattern)]

    return code_blocks