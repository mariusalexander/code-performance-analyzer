#!/usr/bin/python3

import argparse
import pathlib
import json
import re
import os
import shutil
import pandas as pd

def main():
    def result_dir_type(path):
        # match timestamp format
        if not re.search(r"\d{8}T\d{6}", path):
            raise ValueError()
        path = pathlib.Path(path).resolve()
        if not path.is_dir():
            raise ValueError()
        return path

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "results_dir",
        type=result_dir_type,
        help="Path to a result directory with a  name in the form of <yyyymmdd>T<hhmmss>"
    )
    parser.add_argument(
        "-o", "--out_dir",
        type=lambda path: pathlib.Path(path).resolve(),
        help="Optional directory, to export the extracted basic blocks. " + \
             "Generates directory structure based on input benchmark and timestamp."
    )
    parser.add_argument(
        "-x", "--use_extension",
        action="store_true",
        help="Extracts basic blocks with custom instruction instead."
    )
    parser.add_argument(
        "-p", "--print",
        action="store_true",
        help="Prints the results metadata."
    )
    parser.add_argument(
        "-c", "--copy-core-perf",
        action="store_true",
        help="Copies core-perf if it exists"
    )
    args = parser.parse_args()

    timestamp = os.path.basename(args.results_dir)
    print(timestamp)

    benchmark = os.path.basename(args.results_dir.parent)
    print(benchmark)

    working_dir = args.results_dir / ("sess_new_filtered_selected" if args.use_extension else "sess")

    choices_file  = args.results_dir / "sess" / "table" / "choices.pkl"
    llvm_bbs_file = working_dir / "table" / "llvm_bbs.pkl"
    op_trace_file = working_dir / "trace" / "operands_trace.pkl.zst"
    instr_trace_file = working_dir / "instr_trace" / "etiss_instrs.log.pkl.zst"

    for file in choices_file, llvm_bbs_file, op_trace_file, instr_trace_file:
        if not file.is_file() or not file.exists():
            parser.error(f"File '{file}' not found!")

    print(f"Loading '{str(choices_file).replace(str(args.results_dir), "")}'...")
    choices = pd.read_pickle(choices_file)
    print(f"Loading '{str(llvm_bbs_file).replace(str(args.results_dir), "")}'...")
    llvm_bbs = pd.read_pickle(llvm_bbs_file)
    print(f"Loading '{str(op_trace_file).replace(str(args.results_dir), "")}'...")
    op_trace = pd.read_pickle(op_trace_file)
    print(f"Loading '{str(instr_trace_file).replace(str(args.results_dir), "")}'...")
    instr_trace = pd.read_pickle(instr_trace_file)

    tohex = lambda arg: f"0x{arg:08x}"

    print(f"Parsing data...")
    experiment   = []
    total_weight = 0
    for choice in choices.itertuples():
        func_name = choice.func_name
        bb_name   = choice.bb_name

        filtered  = llvm_bbs[(llvm_bbs.func_name == func_name) & (llvm_bbs.bb_name == bb_name)]
        assert len(filtered) == 1
        [pc_begin, pc_end] = list(filtered.pcs)[0]
        target_pcs  = list(range(pc_begin, pc_end, 4))
        instr_count = (pc_end - pc_begin) // 4
        print(func_name, bb_name, "\tbegin:", pc_begin, "\tend:", pc_end, "\tinstructions:", instr_count)

        bb = instr_trace[instr_trace.pc.isin(target_pcs)].drop_duplicates()
        bb_with_op = op_trace.loc[bb.index]

        if instr_count != len(bb):
            print(f"WARNING: Some instructions were not found (expected {instr_count} isntructions, got {len(bb.instr)})!")
            instr_count = len(bb)

        assert bb.instr.equals(bb_with_op.instr)

        normalized_bbs = pd.concat([bb.pc.apply(tohex), bb.bytecode.apply(tohex), bb_with_op.instr, bb_with_op.operands.apply(lambda d: ', '.join(f"{k}={v}" for k, v in d.items()))], axis=1)
        print(normalized_bbs)

        if args.out_dir:
            out_dir = f"{args.out_dir}/{benchmark}/{timestamp}/{"xisaac" if args.use_extension else "default"}"
            print("exporting to", out_dir)
            os.makedirs(out_dir, exist_ok=True)
            normalized_bbs.to_csv(f"{out_dir}/0x{pc_begin:08x}.txt", sep='\t', index=False, header=False)

        experiment.append({
            "name":   f"0x{pc_begin:08x}.txt",
            "weight_per_instr": choice.rel_weight / choice.num_instrs,
            "weight": (choice.rel_weight / choice.num_instrs) * instr_count, # scale weight according to actual len of bb (only needed with `-x`)
            "num_instrs": instr_count,
        })

        total_weight += choice.rel_weight

    # scale weights to be comparable to weights from choices.pkl
    factor = total_weight / sum(bb["weight"] for bb in experiment)
    for bb in experiment:
        bb["weight"] *= factor

    if args.print:
        print("experiment.json")
        print(json.dumps(experiment, indent=4))

    if args.out_dir:
        out_dir = f"{args.out_dir}/{benchmark}/{timestamp}/"
        bb_out_dir = f"{out_dir}/{"xisaac" if args.use_extension else "default"}"
        with open(f"{bb_out_dir}/experiment.json", "w") as f:
            f.write(json.dumps(experiment, indent=4))
        if args.copy_core_perf:
            print("copying CV32E40PXISAAC.corePerfDsl to", out_dir)
            try:
                shutil.copy(f"{args.results_dir}/work/local/etiss_perf_filtered_selected/CV32E40PXISAAC.corePerfDsl", out_dir)
            except FileNotFoundError:
                print("ERROR: cannot locate .corePerfDsl!")


if __name__ == "__main__":
    main()
