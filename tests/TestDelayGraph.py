from src.BlockSchedulingTransformer import BlockSchedulingTransformer
from src.InstructionBlockDescription import InstructionBlockDescription

from src.DelayGraph import DelayGraphTransformer

class AbiRegisters:
    """Maps RISC-V ABI registers onto actual register numbers."""

    def __init__(self):
        self.zero = 0
        self.ra   = 2
        self.sp   = 2
        self.gp   = 3
        self.tp   = 4
        self.t0   = 5
        self.t1   = 6
        self.t2   = 7
        self.s0   = 8
        self.s1   = 9
        self.a0   = 10
        self.a1   = 11
        self.a2   = 12
        self.a3   = 13
        self.a4   = 14
        self.a5   = 15
        self.a6   = 16
        self.a7   = 17
        self.s2   = 18
        self.s3   = 19
        self.s4   = 20
        self.s5   = 21
        self.s6   = 22
        self.s7   = 23
        self.s8   = 24
        self.s9   = 25
        self.s10  = 26
        self.s11  = 27
        self.t3   = 28
        self.t4   = 29
        self.t5   = 30
        self.t6   = 31

def test_vectors(schedModel, verbose=False):

    r = AbiRegisters()

    descs = []

    desc = InstructionBlockDescription("bb_custom_1", 0x100047c)
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
    descs.append(desc)

    desc = InstructionBlockDescription("bb_ppt_example", 0x100047c)
    desc.addInstruction("andi", rd =15, rs1=15)
    desc.addInstruction("slli", rd =15, rs1=15)
    desc.addInstruction("add" , rd =15, rs1=18, rs2=15)
    desc.addInstruction("lw"  , rd =15, rs1=15)
    desc.addInstruction("srli", rd = 8, rs1= 8)
    desc.addInstruction("addi", rd = 9, rs1= 9)
    desc.addInstruction("xor" , rd = 8, rs1=15, rs2= 8)
    desc.addInstruction("bne" , rs1= 9, rs2= 0, imm=8080)
    descs.append(desc)

    desc = InstructionBlockDescription("bb_addi_add_add", 0x000003c4)
    desc.addInstruction("addi", rd=15, rs1=15, imm=255)
    desc.addInstruction("add" , rd=16, rs1=15, rs2=7)
    desc.addInstruction("add" , rd=15, rs1=15, rs2=16)
    descs.append(desc)

    desc = InstructionBlockDescription("bb_lw_addi_sw", 0x000003c4)
    desc.addInstruction("lw"  , rd=3 , rs1=2)
    desc.addInstruction("addi", rd=4, rs1=3, imm=16)
    desc.addInstruction("sw"  , rs1=3, rs2=4)
    descs.append(desc)

    desc = InstructionBlockDescription("bb_mul_example", 0x000003c4)
    desc.addInstruction("mul" , rd=4, rs1=5, rs2=6)
    desc.addInstruction("mul" , rd=7, rs1=8, rs2=9)
    descs.append(desc)

    desc = InstructionBlockDescription("bb_meeting_example", 0x000003c4)
    desc.addInstruction("mul" , rd=1, rs1=10, rs2=11)
    desc.addInstruction("add" , rd=2, rs1=10, rs2=11)
    desc.addInstruction("add" , rd=3, rs1=10, rs2=11)
    desc.addInstruction("add" , rd=4, rs1=1 , rs2=11)
    descs.append(desc)

    blockSchedule = BlockSchedulingTransformer(verbose=verbose).transform(schedModel, descs)
    
    delayModel = DelayGraphTransformer(verbose=verbose).transform(blockSchedule, simplify=False)
    delayModelSimplified = DelayGraphTransformer(verbose=False).transform(blockSchedule, simplify=True)
    assert len(delayModel.variants) == len(delayModelSimplified.variants)
    for variant_name in delayModel.variants:
        delayVariant = delayModel.variants[variant_name]
        delayVariantSimplified = delayModelSimplified.variants[variant_name]
        assert len(delayVariant.scheduling_functions) == len(delayVariantSimplified.scheduling_functions)
        for function in delayVariant.scheduling_functions:
            delayGraph = delayVariant.scheduling_functions[function]
            delayGraphSimplified = delayVariantSimplified.scheduling_functions[function]
            assert len(delayGraph.outputs()) == len(delayGraphSimplified.outputs())
            for output_name in delayGraph.outputs():
                #print(output_name, "\t", delayGraph.get_output(output_name), "\t", delayGraphSimplified.get_output(output_name).expanded(delayGraphSimplified.intermediates()))
                assert delayGraph.get_output(output_name) == delayGraphSimplified.get_output(output_name).expanded(delayGraphSimplified.intermediates())    
        
        