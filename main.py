
import argparse
import pickle
from objprint import op

import sys

from src.BlockSchedulingTransformer import BlockSchedulingTransformer
from src.InstructionBlockDescription import InstructionBlockDescription
from src.DelayGraph import DelayGraphTransformer
from src.DelayGraphViewer import DelayGraphViewer
from src.DelayAnalyzer import DelayAnalyzer

import tests.TestDelayGraph as Tests

def main():
    argParser = argparse.ArgumentParser()
    argParser.add_argument("description", help="...")
    argParser.add_argument("--verbose", action="store_true", help="...")
    argParser.add_argument("--test", action="store_true", help="...")
    argParser.add_argument("--delay-graph", action="store_true", help="...")
    argParser.add_argument("--filter", action="store_true", help="...")
    args = argParser.parse_args()

    filepath = args.description
    with open(filepath, 'rb') as file:
        print("Loading schedule model...")
        schedModel = pickle.load(file)

    print(schedModel)

    if args.filter:
        model = schedModel
        variants = model.variants
        filter_name = "StaBrPred" if not args.nobrpred else "NoBrPred"
        model.variants = [ var for var in model.variants if "SimpleRISCV" not in var.name or filter_name in var.name]
        for var in [var for var in variants if var not in model.variants]:
            print(f"WARNING: Filtered out variant '{var.name}'!")

    if args.test:
        return Tests.test_vectors(schedModel=schedModel)

    descs = []
    desc = InstructionBlockDescription("bb_lw_addi_sw", 0x000003c4)
    desc.addInstruction("lw"  , rd=3 , rs1=2)
    desc.addInstruction("addi", rd=4, rs1=3, imm=16)
    desc.addInstruction("sw"  , rs1=3, rs2=4)
    descs.append(desc)

    blockSchedule = BlockSchedulingTransformer(verbose=args.verbose).transform(schedModel, descs)
        
    #if args.info_print:
    #    SchedulingModelViewer().execute(blockSchedule, outDir, alternate_color=True, show_delays=True)

    delayModel = DelayGraphTransformer(verbose=args.verbose).transform(blockSchedule, simplify=False)

    if args.delay_graph:
        DelayGraphViewer().execute(delayModel, outDir)

    #DelayAnalyzer(structModel, delayModel, verbose=args.verbose) \
    #    .assume_registers_available() \
    #    .assume_no_dynamic_delays() \
    #    .assume_pc_available() \
    #    .assume_perfect_pipeline() \
    #    .resolve(estimate_cpi=True)

if __name__ == "__main__":
    main()