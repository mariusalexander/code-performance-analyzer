#!/usr/bin/python3

import pathlib
import argparse
import fnmatch
import pickle

from backends.schedule_viewer.SchedulingModelViewer import SchedulingModelViewer

from src.Common import Profile, Print
from src.InstructionBlockDescription import InstructionBlockDescription
from src.BlockSchedulingTransformer import BlockSchedulingTransformer
from src.DelayNxGraph import DelayNxGraphTransformer
from src.DelayGraph import DelayGraphTransformer
from src.DelayGraphViewer import DelayGraphViewer
from src.DelayAnalyzer import DelayAnalyzer

import tests.TestVectors as Examples
import tests.UnitTests as UnitTests

def main():

    # helper function to filter out unneeded variants
    def filter_variants(model, pattern, verbose=True):
        variants = model.variants
        model.variants = [var for var in model.variants if fnmatch.fnmatch(var.name, pattern)]
        if not verbose:
            return
        for var in (var for var in variants if var not in model.variants):
            print(f"  > WARNING: filtered out variant '{var.name}'")
        for var in model.variants:
            print(f"  > using variant '{var.name}'")
    
    def valid_path(path):
        return pathlib.Path(path).resolve()
    
    # path to folder
    dirname = pathlib.Path(__file__).resolve().parent / "out"

    ### parse arguments
    args_parser = argparse.ArgumentParser()
    # models
    args_parser.add_argument("schedule_model"     , help="Path to the schedule model pickle file.")
    args_parser.add_argument("struct_model"       , nargs='?', help="Path to the structure model pickle file. Required for delay analysis.")
    # options
    args_parser.add_argument("-o", "--out-dir"    , type=valid_path, default=dirname, help="Directory to store generated files")
    args_parser.add_argument("--cores"            , type=str, help="Filters out any core variants that do not match the given Wildcard pattern")
    args_parser.add_argument("-v", "--verbose"    , action="store_true", help="Enables verbose output.")
    # inputs
    args_parser.add_argument("--tests"            , action="store_true", help="Executes all unittests.")
    args_parser.add_argument("--examples"         , nargs='?', type=str, const='*', help="Loads example basic blocks. A Wildcard pattern can be used to load only certain tests.")
    args_parser.add_argument("--files"            , nargs='+', type=valid_path, const=None, help="Parses code blocks from disk. Multiple input files can be specified.")
    args_parser.add_argument("--symbolic-vars"    , nargs=  1, type=str, default=[""], help="Comma separated list of keywords to find nodes whose delay should be made symbolic.")
    args_parser.add_argument("--brpred"           , nargs=  1, type=str, default=None, help="...")
    # targets
    args_parser.add_argument("--schedule-graph"   , action="store_true", help="Generates schedule graphs for the generated instruction block schedules (writes to `out-dir`, uses M2-ISA-R-Perf internally)")
    args_parser.add_argument("--delay-graph"      , action="store_true", help="Generates delay graphs for the selected instruction blocks (writes to `out-dir`). (WIP)")
    args_parser.add_argument("--cpi"              , action="store_true", help="Estimates the CPI for each instruction block (prints to stdout).")
    args = args_parser.parse_args()

    if isinstance(args.out_dir, list):
        [args.out_dir] = args.out_dir

    ### initializations ###
    print("-- INITIALIZING --")
    print(" > Arguments:\n  >" + ",\n  > ".join(f"'{f}': {args.__getattribute__(f)}" for f in vars(args)))

    # parse arguments
    schedule_model = struct_model = None
    model_path = pathlib.Path(args.schedule_model).resolve()

    if model_path.is_dir():
        print(" > Attemping to load default models...")
        if args.struct_model:
            args_parser.error(f"Loading default models would ignore '--struct-model' argument, aborting!")
        args.schedule_model = model_path / "schedule.model"
        args.struct_model   = model_path / "frontend.model"
    elif not model_path.is_file():
        args_parser.error(f"Invalid path to schedule model!")
    elif not args.schedule_model.endswith(".model"):
        args_parser.error(f"Expected model file to end with '.model'!")

    if sum(bool(arg) for arg in (args.files, args.tests, args.examples)) > 1:
        args_parser.error(f"Conflicting arguments: either use --files, --examples, or --tests!")

    args.symbolic_vars = list(filter(lambda arg: len(arg) > 0, (arg.strip() for arg in args.symbolic_vars[0].split(","))))
    #args.symbolic_vars = list(arg         for arg in args.symbolic_vars if len(arg) > 0)

    if args.brpred:
        [args.brpred] = args.brpred
        match args.brpred:
            case "sta_never_taken":
                pass
            case _:
                args_parser.error(f"Unknown branch prediction option!")

    # load pickle files
    with open(args.schedule_model, 'rb') as file:
        print(" > loading schedule model...")
        with Profile("  > unpickling schedule model"):
            schedule_model = pickle.load(file)

    if args.struct_model:
        with open(args.struct_model, 'rb') as file:
            print(" > loading structural model...")
            with Profile("  > unpickling struct model"):
                struct_model = pickle.load(file)
    elif args.cpi:
        args_parser.error(f"Missing structural model for CPI analysis!")

    # filter out variants
    if args.cores:
        print(" > filtering variants...")
        filter_variants(schedule_model, args.cores)
        if struct_model is not None:
            filter_variants(struct_model, args.cores, verbose=False)

    if len(schedule_model.variants) == 0:
        print(" > ERROR: No variants available!")
        exit(1)

    ### model generation ###
    Print.indent = 3

    # generate block and delay models
    descs = []
    block_schedule = delay_model = None

    # load code blocks from file(s)
    if args.files:
        print(" > loading from files...")
        for file in args.files:
            print(f"  > loading from file '{file.name}'...")
            assert file.exists()
            try:
                address_start = int(file.stem, 16)
            except ValueError:
                address_start = 0
            with open(file) as f:
                raw_instructions = f.readlines()
                desc = InstructionBlockDescription.parse_stringlist(raw_instructions, name=file.stem, address_start=address_start)
                print("   >", desc)
                descs.append(desc)
    # load example code blocks
    elif args.examples:
        descs = Examples.test_vectors(pattern=args.examples)
    # run unittests
    elif args.tests:
        success = UnitTests.run()
        exit(success)

    if len(descs) == 0:
        print(" > ERROR: No code blocks to generate schedule models!")
        exit(1)

    block_schedule = BlockSchedulingTransformer(verbose=args.verbose).transform(schedule_model, descs, brpred_option=args.brpred)
    delay_model    = DelayGraphTransformer(verbose=args.verbose).transform(block_schedule, descs, symbolic_vars=args.symbolic_vars)

    ### Backends ###

    # visualizations
    if args.schedule_graph:
        SchedulingModelViewer().execute(block_schedule, args.out_dir, alternate_color=True, show_delays=True)
    if args.delay_graph:
        DelayGraphViewer().execute(delay_model, args.out_dir)
    # cpi analysis
    if args.cpi:
        DelayAnalyzer(struct_model, delay_model, verbose=args.verbose) \
            .assume_registers_available() \
            .assume_fix_dynamic_delays() \
            .assume_pc_available() \
            .assume_perfect_pipeline() \
            .resolve(estimate_cpi=True)

if __name__ == "__main__":
    main()