#!/usr/bin/python3

import pathlib
import argparse
import fnmatch
import pickle
import json
from objprint import op

from backends.schedule_viewer.SchedulingModelViewer import SchedulingModelViewer

from src.Common import Profile, Print
from src.InstructionBlockDescription import InstructionBlockDescription
from src.BlockSchedulingTransformer import BlockSchedulingTransformer
from src.MaxPlusAlgebra import DelayVariable

from src.SequenceTransformer import SequenceTransformer
from src.TimingsAnalyzer import TimingsAnalyzer

import tests.TestVectors as Examples
import tests.UnitTests as UnitTests

def main():

    # helper function to filter out unneeded variants
    def filter_variants(model, pattern, verbose=True):
        invert = pattern.startswith("-")
        if invert:
            pattern = pattern[1:]
        variants = model.variants
        model.variants = [var for var in model.variants if fnmatch.fnmatch(var.name, pattern) != invert]
        if not verbose:
            return (var for var in variants if var not in model.variants)
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
    args_parser.add_argument("-o", "--out-dir"    , type=valid_path, default=dirname, help="Directory to store generated files.")
    args_parser.add_argument("--cores"            , type=str, help="Filters out any core variants that do not match the given Wildcard pattern.")
    args_parser.add_argument("-v", "--verbose"    , action="store_true", help="Enables verbose output.")
    args_parser.add_argument("-p", "--print"      , action="store_true", help="Prints the results.")
    # TODO: keep? add more options?
    args_parser.add_argument("-b", "--print-bb"   , action="store_true", help="Prints the code_block.")
    # TODO: remove?
    args_parser.add_argument("--brpred"           , nargs=  1, type=str, default=None, help="...")
    # inputs
    args_parser.add_argument("--tests"            , action="store_true", help="Executes all unittests.")
    args_parser.add_argument("--examples"         , nargs='?', type=str, const='*', help="Loads example basic blocks. A Wildcard pattern can be used to load only certain tests.")
    args_parser.add_argument("--files"            , nargs='+', type=valid_path, const=None, help="Parses code blocks from disk. Multiple input files can be specified.")

    args_parser.add_argument("-d", "--default-dynamic-delay", nargs=  1, type=int, default=[None], help="Sets a default value for dynamic delays.")
    # targets
    args_parser.add_argument("--sequence-analysis", action="store_true", help="Determine CPI of basic blocks by sequentially evaluating the timing model for each instruction.")
    args_parser.add_argument("--symbolic-analysis", nargs=  1, type=str, default=[""], 
                                                    help="Comma separated list of keywords to find nodes whose delay should be made symbolic. " +\
                                                         "Initiates symbolic sequenced timing analysis.")
    args_parser.add_argument("--cpi"              , action="store_true", help="Estimates the CPI for each instruction block. Prints to stdout.")
    # TODO: generalize?
    args_parser.add_argument("--xisaac"           , action="store_true", help="")
    args_parser.add_argument("--export"           , nargs=  1, type=valid_path, default=[None], help="Exports the results to the given path")
    args_parser.add_argument("--export-suffix"    , nargs=  1, type=str, default=[None], help="Optional suffix for exported results.")

    args_parser.add_argument("--block-schedule"   , action="store_true", help="Generates a scheduling function for the given code blocks.")
    args_parser.add_argument("--schedule-graph"   , action="store_true", help="Generates scheduling functions graphs for the generated instruction block schedules. " + \
                                                                              "(writes to `out-dir`, uses M2-ISA-R-Perf internally)")

    args = args_parser.parse_args()

    if isinstance(args.out_dir, list):
        [args.out_dir] = args.out_dir

    ### initializations ###
    print("-- INITIALIZING --")
    print(" > Arguments:\n  >" + ",\n  > ".join(f"'{f}': {args.__getattribute__(f)}" for f in vars(args)))

    # parse arguments

    [args.default_dynamic_delay] = args.default_dynamic_delay
    [args.export_suffix]  = args.export_suffix
    [args.export]         = args.export

    symbolic_names = list(filter(lambda arg: len(arg) > 0, (arg.strip() for arg in args.symbolic_analysis[0].split(","))))
    args.symbolic_analysis = len(symbolic_names)

    # corePerfDsl models
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

    if args.schedule_graph and not args.block_schedule:
        args.block_schedule = True

    if sum(bool(arg) for arg in (args.files, args.tests, args.examples)) > 1:
        args_parser.error(f"Conflicting arguments: either use --files, --examples, or --tests!")
    if sum(bool(arg) for arg in (args.sequence_analysis, args.symbolic_analysis, args.block_schedule)) > 1:
        args_parser.error(f"Conflicting arguments: either use --sequence-analysis, --symbolic-names, or --block-schedule!")
    if args.cpi and not symbolic_names:
        args.sequence_analysis = True

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

    symbolic_delay_vectors = {}
    if args.xisaac:
        for variant in struct_model.getAllVariants():
            pipeline = variant.getPipeline()
            mirco_ops = pipeline.getAllMicroactions()
            resources = (res for op in mirco_ops for res in op.getResources())
            resources = (res for res in resources for var in symbolic_names if var in res.name)
            symbolic_delay_vectors[variant.name] = { f"V0{r.name[r.name.index('_'):]}": DelayVariable('', r.delay) for r in resources }

    # filter out variants
    if args.cores:
        print(" > filtering variants...")
        filter_variants(schedule_model, args.cores)
        if struct_model is not None:
            filter_variants(struct_model, args.cores, verbose=False)

    if len(schedule_model.variants) == 0:
        print(" > ERROR: No variants available!")
        exit(1)

    ### extract instruction blocks ###

    # generate block and delay models
    code_blocks = []
    block_schedule = delay_model = None

    # load code blocks from file(s)
    if args.files:
        with Print.indent_scope(3):
            code_blocks = InstructionBlockDescription.load_from_files(args.files, verbose=args.verbose)
    # load example code blocks
    elif args.examples:
        code_blocks = Examples.test_vectors(pattern=args.examples)
    # run unittests
    elif args.tests:
        success = UnitTests.run()
        exit(success)

    if len(code_blocks) == 0:
        print(" > ERROR: No code blocks to generate schedule models!")
        exit(1)

    ### Backends ###

    # generate block scheduling functions
    if args.block_schedule:

        block_schedule = BlockSchedulingTransformer(verbose=args.verbose, 
                                                    rename_edges=False) \
            .transform(schedule_model, code_blocks, brpred_option=args.brpred)

        # render block schedules
        if args.schedule_graph:
            SchedulingModelViewer() \
                .execute(block_schedule, args.out_dir, alternate_color=True, show_delays=True)

    # timing analysis
    if not args.sequence_analysis and not args.symbolic_analysis:
        print(" > WARNING: nothing to do!")
        exit(0)
    
    sequence_model = SequenceTransformer(verbose=args.verbose,
                                         symbolic_vars=symbolic_names,
                                         default_dynamic_delay=args.default_dynamic_delay,
                                         accumulate_timings=args.print) \
        .analyze_all_variants(schedule_model, code_blocks)

    # exit early
    if not args.cpi:
        exit(0)

    final_results = None

    # sequence timing analysis
    if args.sequence_analysis:
        final_results = TimingsAnalyzer(print_history=args.print, 
                                   print_code_blocks=args.print_bb, 
                                   assume_same_pipeline=args.xisaac) \
            .estimate_cpi(sequence_model, schedule_model, struct_model)

    # symbolic timing analysis
    elif args.symbolic_analysis:
        final_results = TimingsAnalyzer(print_history=False, # not fully supported yet
                                        print_code_blocks=args.print_bb, 
                                        assume_same_pipeline=args.xisaac) \
            .solve_symbolic_delay(sequence_model, schedule_model, struct_model, symbolic_delay_vectors)

    ### Post Processing ###
    if not final_results:
        exit(0)

    # export results
    if isinstance(args.export, pathlib.Path):
        for variant_name in final_results:
            blocks = final_results[variant_name]
            with open(args.cpi / f"{variant_name}_{args.export_suffix + "_" if args.export_suffix else ""}results.json", "w") as f:
                f.write(json.dumps(blocks, indent=4))

    # print total CPI if possible
    print()
    for variant_name in final_results:
        blocks       = final_results[variant_name]
        total_weight = sum(bb.weight for bb in blocks.values() if bb.weight is not None)
        if total_weight == 0:
            print("ERROR: Cannot determine total CPI, missing weights for basic blocks!")
            break

        print(f"Variant: {variant_name:>15},\t",
                f"total CPI: {sum((bb.cpi * bb.weight / total_weight) for bb in blocks.values()):.6f},\t",
                f"total weight: {total_weight * 100:.5f}%")

if __name__ == "__main__":
    main()