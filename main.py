import sys
import pathlib
import argparse
import fnmatch
import pickle
from objprint import op

from backends.schedule_viewer.SchedulingModelViewer import SchedulingModelViewer

from src.Common import Profile
from src.InstructionBlockDescription import InstructionBlockDescription
from src.BlockSchedulingTransformer import BlockSchedulingTransformer
from src.DelayGraph import DelayGraphTransformer
from src.DelayGraphViewer import DelayGraphViewer
from src.DelayAnalyzer import DelayAnalyzer

import tests.TestDelayGraph as Tests

def main():

    # helper function to filter out unneeded variants
    def filter_variants(model, pattern, verbose=True):
        variants = model.variants
        model.variants = [var for var in model.variants if fnmatch.fnmatch(var.name, pattern)]
        if not verbose:
            return
        for var in [var for var in variants if var not in model.variants]:
            print(f"  > WARNING: filtered out variant '{var.name}'")
        for var in model.variants:
            print(f"  > using variant '{var.name}'")
    
    # path to folder
    dirname = pathlib.Path(__file__).resolve().parents[0] / "out"

    ### parse arguments
    args_parser = argparse.ArgumentParser()
    # models
    args_parser.add_argument("schedule_model"     , help="Path to the schedule model pickle file.")
    args_parser.add_argument("struct_model"       , nargs='?', help="Path to the structure model pickle file. Required for delay analysis.")
    # options
    args_parser.add_argument("-o", "--out-dir"    , default=dirname, type=lambda o: pathlib.Path(o).resolve(), help="Directory to store generated files")
    args_parser.add_argument("--cores"            , type=str, help="Filters out any core variants that do not match the given Wildcard pattern")
    args_parser.add_argument("-v", "--verbose"    , action="store_true", help="Enables verbose output.")
    args_parser.add_argument("--simplify"         , action="store_true", help="Whether to simplify the generated delay graphs.")
    # inputs
    args_parser.add_argument("--tests"            , nargs='?', type=str, const='*', help="Loads test vectors. A Wildcard pattern can be used to load only certain tests.")
    # targets
    args_parser.add_argument("--schedule-graph"   , action="store_true", help="Generates schedule graphs for the generated instruction block schedules (writes to `out-dir`, uses M2-ISA-R-Perf internally)")
    args_parser.add_argument("--delay-graph"      , action="store_true", help="Generates delay graphs for the selected instruction blocks (writes to `out-dir`).")
    args_parser.add_argument("--cpi"              , action="store_true", help="Estimates the CPI for each instruction block (prints to stdout).")
    args = args_parser.parse_args()

    if isinstance(args.out_dir, list):
        [args.out_dir] = args.out_dir

    ### initializations ###
    print("-- INITIALIZING --")
    sched_model = struct_model = None

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

    # load pickle files
    with open(args.schedule_model, 'rb') as file:
        print(" > loading schedule model...")
        with Profile("  > unpickling schedule model"):
            sched_model = pickle.load(file)

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
        filter_variants(sched_model, args.cores)
        if struct_model is not None:
            filter_variants(struct_model, args.cores, verbose=False)

    if len(sched_model.variants) == 0:
        print(" > ERROR: No variants available!")
        exit(1)

    ### model generation ###

    # generate block and delay models
    block_schedule = delay_model = None
    # TODO: allow loading one or multiple basic blocks from file or stdin
    if args.tests:
        block_schedule, delay_model = Tests.generate_models(sched_model, pattern=args.tests, verbose=args.verbose, simplify=args.simplify)

    if block_schedule is None or delay_model is None:
        print(" > ERROR: No block schedule was generated!")
        exit(1)

    ### backends ###

    # visualizations
    if args.schedule_graph:
        SchedulingModelViewer().execute(block_schedule, args.out_dir, alternate_color=True, show_delays=True)
    if args.delay_graph:
        DelayGraphViewer().execute(delay_model, args.out_dir)
    # cpi analysis
    if args.cpi:
        DelayAnalyzer(struct_model, delay_model, verbose=args.verbose) \
            .assume_registers_available() \
            .assume_no_dynamic_delays() \
            .assume_pc_available() \
            .assume_perfect_pipeline() \
            .resolve(estimate_cpi=True)

if __name__ == "__main__":
    main()