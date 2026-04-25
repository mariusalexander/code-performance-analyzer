#!/usr/bin/python3

import pathlib
import argparse
import fnmatch
import pickle
import json
from objprint import op

from backends.schedule_viewer.SchedulingModelViewer import SchedulingModelViewer

from src.Common import Profile, Print, dotdict, find_variant
from src.InstructionBlockDescription import InstructionBlockDescription
from src.BlockSchedulingTransformer import BlockSchedulingTransformer
from src.DelayGraph import DelayGraphTransformer
from src.DelayGraphViewer import DelayGraphViewer
from src.DelayAnalyzer import DelayAnalyzer
from src.InputVectorGenerator import InputVector, InputVectorGenerator, PipelineDescription
from src.MaxPlusAlgebra import DelayVariable, DelayFunction_v2, DelayFunctionList
from src.SequenceTransformer import SequenceTransformer
from src.TimingsAnalyzer import TimingsAnalyzer
from src.TimingsPrinter import TimingsPrinter

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
    args_parser.add_argument("-p", "--print"      , action="store_true", help="Prints the results.")
    args_parser.add_argument("-b", "--print-bb"   , action="store_true", help="Prints the code_block.")
    args_parser.add_argument("-i", "--print-iv"   , action="store_true", help="Prints the iput vectors.")
    # inputs
    args_parser.add_argument("--tests"            , action="store_true", help="Executes all unittests.")
    args_parser.add_argument("--examples"         , nargs='?', type=str, const='*', help="Loads example basic blocks. A Wildcard pattern can be used to load only certain tests.")
    args_parser.add_argument("--files"            , nargs='+', type=valid_path, const=None, help="Parses code blocks from disk. Multiple input files can be specified.")

    args_parser.add_argument("--symbolic-vars"    , nargs=  1, type=str, default=[""], help="Comma separated list of keywords to find nodes whose delay should be made symbolic.")
    args_parser.add_argument("--brpred"           , nargs=  1, type=str, default=None, help="...")
    args_parser.add_argument("--resolve-later"    , action="store_true", help="Whether to resolve the outputs as a function of the inputs")
    args_parser.add_argument("--dynamic-delays"   , nargs=  1, type=int, default=[None], help="...")
    args_parser.add_argument("--loopback"         , action="store_true", help="...")
    args_parser.add_argument("--ign-dyn"          , action="store_true", help="Ignore dynamic delays in metadata")
    args_parser.add_argument("--no-dyn"           , action="store_true", help="Abort if unmatched dynamic delays are present")
    # targets
    args_parser.add_argument("--schedule-graph"   , action="store_true", help="Generates schedule graphs for the generated instruction block schedules (writes to `out-dir`, uses M2-ISA-R-Perf internally)")
    args_parser.add_argument("--delay-graph"      , action="store_true", help="Generates delay graphs for the selected instruction blocks (writes to `out-dir`). (WIP)")
    args_parser.add_argument("--cpi"              , nargs='?', type=valid_path, const=True, help="Estimates the CPI for each instruction block. Prints to stdout. If given a file name exports results to file")
    args_parser.add_argument("--exit"             , action="store_true", help="Exits the programm before estimating the CPI.")
    args_parser.add_argument("--suffix"           , nargs=  1, type=str, default=[None], help="...")

    args_parser.add_argument("-s", "--sequenced"  , action="store_true", help="Analyze basic blocks ")
    
    args = args_parser.parse_args()

    if isinstance(args.out_dir, list):
        [args.out_dir] = args.out_dir

    ### initializations ###
    print("-- INITIALIZING --")
    print(" > Arguments:\n  >" + ",\n  > ".join(f"'{f}': {args.__getattribute__(f)}" for f in vars(args)))

    # parse arguments
    schedule_model = struct_model = None
    model_path = pathlib.Path(args.schedule_model).resolve()

    [args.dynamic_delays] = args.dynamic_delays
    [args.suffix]         = args.suffix

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
    elif args.cpi or not args.resolve_later:
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
    code_blocks = []
    block_schedule = delay_model = None

    # load code blocks from file(s)
    if args.files:
        code_blocks = InstructionBlockDescription.load_from_files(args.files, ignore_variants=args.ign_dyn, verbose=args.verbose)
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

    if args.sequenced:
        sequence_model = SequenceTransformer(verbose=args.verbose, 
                                         default_dynamic_delay=args.dynamic_delays) \
            .analyze_all_variants(schedule_model, struct_model, code_blocks)

        print("\n-- FRONTEND: DELAY ANALYSIS --")
        final_results = {}
        for sequence_variant in sequence_model.variants:
            assert sequence_variant.name not in final_results, \
                   f"Duplicate result entry for variant '{variant.name}'!"
            
            final_results[sequence_variant.name] = {}
            sched_variant  = find_variant(schedule_model, sequence_variant.name)
            struct_variant = find_variant(struct_model, sequence_variant.name)

            analyzer = TimingsAnalyzer(sched_variant=sched_variant, struct_variant=struct_variant)

            for code_block in code_blocks:
                timings_history = sequence_variant.timings_history[code_block.name]
                results = analyzer.analyse_steady_state(code_block=code_block, timings_history=timings_history)
                
                if args.print:
                    print()
                    print(f" > Timings of '{code_block.name}' ({sequence_variant.name}):")
                    TimingsPrinter.print_history(code_block=code_block, timings_history=timings_history, stall_history=results.stall_history)
                    print()

                if args.cpi:
                    print(f"Variant: {sequence_variant.name:>15},", 
                          f"Code Block: {code_block.name:>10},", 
                          f"CPI: {results.cpi:>8.6f},",
                          f"Instructions: {results.num_instructions:>3},",
                          f"Stall cycles: {results.total_stall_cycles:>3},",
                          f"Rel. Weight: {f'{code_block.weight:.5f}%' if code_block.weight else "??"}")

                    assert code_block.name not in final_results[sequence_variant.name], \
                           f"Duplicate result entry for code block '{code_block.name}'!"

                    final_results[sequence_variant.name][code_block.name] = dotdict({
                        "num_instructions"  : results.num_instructions,
                        "stall_cycles"      : results.total_stall_cycles,
                        "cpi"               : results.cpi,
                        "weight"            : code_block.weight
                    })

        # export results
        if isinstance(args.cpi, pathlib.Path):
            for variant_name in final_results:
                result = final_results[variant_name]
                with open(args.cpi / f"{variant_name}_{args.suffix + "_" if args.suffix else ""}results.json", "w") as f:
                    f.write(json.dumps(result, indent=4))

        # print total CPI if possible
        print()
        for variant_name in final_results:
            result = final_results[variant_name]
            total_weight = sum(bb.weight for bb in result.values() if bb.weight is not None)
            if total_weight == 0:
                print("WARNING: Cannot determine total CPI, missing weights for basic blocks!")
                continue
            print(variant_name.ljust(30), f"total CPI: {sum((bb.cpi * bb.weight / total_weight) for bb in result.values()):.6f} \ttotal weight: {total_weight * 100:.3f}%")

        exit(0)

    resolve_dynamic_delays = args.dynamic_delays is not None
    block_schedule = BlockSchedulingTransformer(verbose=args.verbose).transform(schedule_model, code_blocks, brpred_option=args.brpred)

    ### Backends ###

    # visualizations
    if args.schedule_graph:
        SchedulingModelViewer().execute(block_schedule, args.out_dir, alternate_color=True, show_delays=True)
    if args.delay_graph:
        DelayGraphViewer().execute(delay_model, args.out_dir)
    if args.exit:
        exit(0)

    # generate input vector upfront
    if not args.resolve_later:
        DelayFunctionList.use_v2 = True

        for variant in block_schedule.getAllVariants():
            [struct_variant] = tuple(filter(lambda v: v.name == variant.name, struct_model.variants))
            pipeline = PipelineDescription.generate(struct_variant)
            
            idx = 0
            for block_function in variant.getAllSchedulingFunctions():
                input_vector = InputVectorGenerator(struct_variant, block_function, verbose=args.print_iv or args.verbose) \
                                .assume_all_registers_available() \
                                .assume_pc_available() \
                                .assume_perfect_pipeline(pipeline=pipeline)
                if resolve_dynamic_delays:
                    input_vector.assume_fix_dynamic_delays(value=args.dynamic_delays)
                elif code_blocks[idx].dynamic_vars:
                    input_vector.apply_dynamic_delays(code_blocks[idx].dynamic_vars)
                elif block_function.dynamic_variables() and args.no_dyn:
                    print("Error: Unmatched dynamic delays:", block_function.name)
                    for name in block_function.dynamic_variables():
                        print(" >", name)
                    raise RuntimeError("Unmatched dynamic delays!")
                input_vector = input_vector.finalize()

                block_function.set_input_vector(input_vector)
                idx += 1

    # delay model
    delay_model = DelayGraphTransformer(verbose=args.verbose, 
                                        default_dynamic_delay=args.dynamic_delays) \
        .transform(block_schedule, code_blocks, symbolic_vars=args.symbolic_vars)

    results = {}
    # cpi analysis 
    analyzer = DelayAnalyzer(verbose=args.verbose)

    for variant in delay_model.variants:
        results[variant.name] = {}

        if args.resolve_later:
            [struct_variant] = tuple(filter(lambda v: v.name == variant.name, struct_model.variants))
            pipeline = PipelineDescription.generate(struct_variant)

        for delay_graph in variant.delay_graphs:
            [block_function] = [s for v in block_schedule.getAllVariants() if v.name == variant.name for s in v.getAllSchedulingFunctions() if s.name == delay_graph.name]
            input_vector      = block_function.input_vector()
            source_functions  = delay_graph.outputs()
            applied_functions = source_functions

            if args.resolve_later:
                input_vector = InputVectorGenerator(struct_variant, delay_graph, verbose=args.verbose) \
                                    .assume_all_registers_available() \
                                    .assume_pc_available() \
                                    .assume_perfect_pipeline(pipeline=pipeline)
                if resolve_dynamic_delays:
                    input_vector.assume_fix_dynamic_delays(value=args.dynamic_delays)
                input_vector = input_vector.finalize()
                applied_functions = analyzer.apply_input_vector(input_vector=input_vector, functions=source_functions)

            # can only evaluate term if there are no symbolic variables
            output_vector_1st_iter = None
            if not args.symbolic_vars and all(dyn.lower() in input_vector for dyn in block_function.dynamic_variables()):
                output_vector_1st_iter = analyzer.evaluate(applied_functions)
            elif args.cpi:
                print(f"Error: Unknown delays! ({block_function.name})\n", input_vector)
                for v in (dyn.lower() for dyn in block_function.dynamic_variables() if dyn.lower() not in input_vector):
                    print(" >", v)
                raise RuntimeError("Failed to determince CPI, graph contains unknown delays!")
            elif args.loopback:
                raise RuntimeError("Failed to perform loopback, graph contains unknown delays!")
            output_vector = output_vector_1st_iter

            # feed outputs as an input and evaluate delay graph once more
            output_vector_2nd_iter = None
            if args.loopback and output_vector != None:
                input_vector = block_function.input_vector()
                input_vector.merge(output_vector)
                block_function.set_input_vector(input_vector)

                delay_graph_2nd_iter = DelayGraphTransformer(verbose=args.verbose).transform_block(block_function, delay_graph.code_block, symbolic_vars=args.symbolic_vars)
                output_vector_2nd_iter = analyzer.evaluate(delay_graph_2nd_iter.outputs())
                output_vector = output_vector_2nd_iter

            if args.print:
                analyzer.print({
                    "original"  : (source_functions if args.resolve_later else None), 
                    "resolved"  : applied_functions, 
                    "evaluated" : output_vector_1st_iter,
                    "2nd evaluation" : output_vector_2nd_iter
                })

            if args.cpi:
                num_instructions = len(delay_graph.code_block.instructions)
                cpi, stage = analyzer.estimate_cpi(pipeline, output_vector, num_instructions, offset=input_vector[pipeline.start()].delay)
                if args.print_bb:
                    print(delay_graph.code_block)
                print(variant.name.ljust(30), delay_graph.name.ljust(20), 
                      f"CPI: {cpi:>8.6f} ({stage.name:>5}={stage.delay:>3})\t{len(delay_graph.code_block.instructions):>3} instructions,",
                       "rel weight:", (f"{delay_graph.code_block.weight:.5f}%" if delay_graph.code_block.weight is not None else "rel weight: ??"))
                
                assert delay_graph.name not in results[variant.name], "Duplicate result entry!"
                results[variant.name][delay_graph.name] = dotdict({
                    "cpi": cpi,
                    "weight": delay_graph.code_block.weight,
                    "diciding_stage"   : stage.name[2:],
                    "diciding_timing"  : stage.delay,
                    "num_instructions" : len(delay_graph.code_block.instructions),
                    "input_vector"     : { n:v.delay for n, v in input_vector.items() },
                    "output_vector"    : { v[2:]:d for v, d in output_vector.items() }
                })
    
    # export results
    if isinstance(args.cpi, pathlib.Path):
        for variant_name in results:
            result = results[variant_name]
            with open(args.cpi / f"{variant_name}_{args.suffix + "_" if args.suffix else ""}results.json", "w") as f:
                f.write(json.dumps(result, indent=4))

    # print total cpi if possible
    print()
    for variant_name in results:
        result = results[variant_name]
        total_weight = sum(bb.weight for bb in result.values() if bb.weight is not None)
        if total_weight == 0:
            print("WARNING: Cannot determine total CPI, missing weights for basic blocks!")
            continue
        print(variant_name.ljust(30), f"total CPI: {sum((bb.cpi * bb.weight / total_weight) for bb in result.values()):.6f} \ttotal weight: {total_weight * 100:.3f}%")

if __name__ == "__main__":
    main()