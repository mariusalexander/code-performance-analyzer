#!/bin/python3
# Helper script to generate CV32E40P XISAAC UARCH Variants

import argparse
import csv
import re
import os
from pathlib import Path
from itertools import product

# helpers
ENDL   = lambda indent=1: ("\n" + " " * (indent * 2))
STAGES = lambda         : ("I", "X", "O")

VIRTUAL_RESOURCE     = lambda instr, suffix:      f"vCUSTOM{instr}_{suffix}"
VIRTUAL_MIRCO_ACTION = lambda instr, suffix:      f"vuA_CUSTOM{instr}_{suffix}"
VARIANT_RESOURCE     = lambda idx, instr, suffix: f"V{idx}_CUSTOM{instr}_{suffix}"
VARIANT_MIRCO_ACTION = lambda idx, instr, suffix: f"uA_V{idx}_CUSTOM{instr}_{suffix}"
SUB_STAGE            = lambda instr, suffix:      f"EX_substage_CUSTOM{instr}_{suffix}"
SUB_PIPELINE         = lambda instr:              f"EX_subpipe_CUSTOM{instr}"
INSTR_GROUP          = lambda instr:              f"XIsaac_CUSTOM{instr}"

# scope generators
SCOPE_NL = lambda name, iterable, indent=0, new_line=False: \
     " " * (indent * 2) + \
    f"{name} {{" + ENDL(indent + 1) + \
    f",{ENDL(indent + 1)}".join(iterable) + \
     "\n" + \
     " " * (indent * 2) + \
     "}" + \
    ("\n" if new_line else "")

SCOPE = lambda name, iterable, new_line=False: \
    f"{name} {{" + f", ".join(iterable) + "}" + ("\n" if new_line else "")

# predefined strings
MIRCO_ACTION_MAPPING = "uA_Decode, uA_OF_A, uA_OF_B" + \
    ", "

TRACE_VALUE_MAPPING = \
"""{
    rd = "$bitfield{rd}",
    rd_data = "$reg{$bitfield{rd}}",

    rs1 = "$bitfield{rs1}",
    rs1_data = "$reg{$bitfield{rs1}}",

    rs2 = "$bitfield{rs2}",
    rs2_data = "$reg{$bitfield{rs2}}"
  },"""

PERFMODEL_DESC = \
"""
  core : "XIsaacCore"
  use Pipeline : CV32E40PXISAAC_pipeline
  use ConnectorModel : {regModel, |BRANCH_MODEL|}
"""

INSTRUCTION_TRACE_CUSTOM_INSTRUCTION = lambda instr: \
"""    {
        "name": "CUSTOM|INSTR|_Type",
        "instructions": [{"name": "CUSTOM|INSTR|"}],
        "mappings": [
            {"traceValue": "code", "description": "$code"},
            {"traceValue": "pc", "description": "$pc"},
            {"traceValue": "assembly", "description": "$asm"},
                {"traceValue": "rd_data", "description": "$reg{$bitfield{rd}}"},
                {"traceValue": "rs1_data", "description": "$reg{$bitfield{rs1}}"},
                {"traceValue": "rs2_data", "description": "$reg{$bitfield{rs2}}"}
        ]
    },""".replace("|INSTR|", instr)

DELAY_VECTORS = [] # set at runtime, must updated in-place
MODEL_SUFFIX  = ""

# main dictionary
def load_identifiers() -> dict[str, callable]:
    return {
        'V_RESOURCE_DEFS': lambda instrs, *_: \
            SCOPE_NL(
                name="virtual Resource",
                iterable=(VIRTUAL_RESOURCE(instr, suffix) for instr in instrs for suffix in STAGES())
            )
        ,
        'RESOURCE_INSTANCES': lambda instrs, num_vars, *_: \
            "\n\n".join(
                f"// Variant: V{idx}\n" + \
                "\n".join(
                    SCOPE(
                        name="Resource",
                        iterable=(VARIANT_RESOURCE(idx, instr, suffix) + f"({DELAY_VECTORS[idx][instr][suffix]})" for suffix in STAGES()),
                    ) \
                    for instr in instrs)
                for idx in range(num_vars))
        ,
        'V_MICRO_ACTION_DEFS': lambda instrs, *_: \
            SCOPE_NL(
                name="virtual Microaction",
                iterable=(VIRTUAL_MIRCO_ACTION(instr, suffix) for instr in instrs for suffix in STAGES())
            )
        ,
        'MICRO_ACTION_INSTANCES': lambda instrs, num_vars, *_: \
            "\n".join(
                f"// Variant: V{idx}\n" + \
                SCOPE_NL(
                    name="Microaction",
                    iterable=(VARIANT_MIRCO_ACTION(idx, instr, suffix) + (" " * 4) + \
                              "(" + VARIANT_RESOURCE(idx, instr, suffix) + (" -> Xd" if suffix == "O" else "") + ")" \
                                    for instr in instrs for suffix in STAGES())
                ) \
                for idx in range(num_vars)
            )
        ,
        'SUBSTAGE_DEFS': lambda instrs, *_: \
            SCOPE_NL(
                name="Stage",
                iterable=(SUB_STAGE(instr,suffix) + " (" + VIRTUAL_MIRCO_ACTION(instr, suffix) + ")" for instr in instrs for suffix in STAGES())
            )
        ,
        'PIPELINE_DEFS': lambda instrs, *_: \
            SCOPE_NL(
                name="Pipeline",
                iterable=(SUB_PIPELINE(instr) + " (" + " -> ".join(SUB_STAGE(instr, suffix) for suffix in STAGES()) + ")"  for instr in instrs)
            )
        ,
        'STAGE_DEFS': lambda instrs, *_: \
            f",{ENDL(indent=2)}".join(SUB_PIPELINE(instr) for instr in instrs) + ","
        ,
        'INSTR_GROUP_DEFS': lambda instrs, *_: \
            SCOPE_NL(
                name="InstrGroup",
                iterable=(INSTR_GROUP(instr) + f" (custom{instr})" for instr in instrs)
            )
        ,
        'MIRCO_ACTION_MAPPINGS': lambda instrs, *_: \
            SCOPE_NL(
                name="MicroactionMapping",
                iterable=(INSTR_GROUP(instr) + f" : {{{MIRCO_ACTION_MAPPING}{", ".join(VIRTUAL_MIRCO_ACTION(instr, suffix) for suffix in STAGES())}}}" for instr in instrs)
            )
        ,
        'TRACE_VALUE_MAPPINGS': lambda instrs, *_: \
            ENDL(indent=1).join(INSTR_GROUP(instr) + " : " + TRACE_VALUE_MAPPING for instr in instrs)
        ,
        'VARIANTS': lambda instrs, num_vars, *_: \
            "\n".join(
                f"// Variant: V{idx}\n" + \
                f"CorePerfModel CV32E40PXISAAC{MODEL_SUFFIX}V{idx} (" + PERFMODEL_DESC + \
                SCOPE_NL(
                    name="assign Resource :",
                    iterable=(VIRTUAL_RESOURCE(instr, suffix) + " = " + VARIANT_RESOURCE(idx, instr, suffix) \
                                for instr in instrs for suffix in STAGES()),
                    indent=1,
                    new_line=True
                ) + \
                SCOPE_NL(
                    name="assign Microaction :",
                    iterable=(VIRTUAL_MIRCO_ACTION(instr, suffix) + " = " + VARIANT_MIRCO_ACTION(idx, instr, suffix) \
                                for instr in instrs for suffix in STAGES()),
                    indent=1,
                    new_line=True
                ) + \
                ")\n"
                for idx in range(num_vars)
            )
        ,
        'CUSTOM_INSTRUCTIONS': lambda instrs, *_: \
            "\n".join(INSTRUCTION_TRACE_CUSTOM_INSTRUCTION(instr) for instr in instrs)
    }

def replace_placeholders(template: str, instructions: list[str], num_variants:int) -> str:
    """Replace every |IDENTIFIER| found in the template using the registry."""

    identifiers = load_identifiers()

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        handler = identifiers.get(key)
        if handler is None:
            print(f"Warning: no handler registered for |{key}|!")
            # keep the original placeholder
            return match.group(0)

        return handler(instructions, num_variants)

    return re.sub(r"\|([A-Z_]+)\|", replacer, template)

def generate_combinations(max_latency: int, keys: list[str]) -> list[dict]:
    patterns = [(0, 0), (0, 1), (1, 1)]  # (X_mul, O_mul)

    result = []
    for i in range(1, max_latency + 1):
        per_key_patterns = [patterns] * len(keys)
        for combo in product(*per_key_patterns):
            entry = {}
            for key, (x_mul, o_mul) in zip(keys, combo):
                entry[key] = {"I": i, "X": x_mul * i, "O": o_mul * i}
            result.append(entry)
    return result

def lat_ii_to_ixo(ii: int, lat: int) -> dict:
    """
    Convert ii and lat to I, X, O values.
    """
    if lat % ii != 0:
        raise ValueError(f"Expected lat to be multiple of ii! (lat/ii = {lat}/{ii})")

    n = lat // ii
    if n < 0 or n > 3:
        raise ValueError(f"Expected lat/ii to be within the range [0, 3].")

    return {
        "I": ii,
        "O": ii if n >= 2 else 0,
        "X": ii if n >= 3 else 0,
    }

def parse_ranking_row(details_string: str) -> dict[str, dict]:
    """
    Parse a string like:
      SG1(II=1, lats={CUSTOM3: 1}, full_lats={CUSTOM3: 3}), SG2(...)
    and return a dict of {name: {"ii": int, "lat": int}} for each entry.
    """
    results = {}
    # match SGx(...) block
    for block in re.finditer(r'\w+\(([^)]+)\)', details_string):
        content = block.group(1)

        ii_match = re.search(r'II=(\d+)', content)
        assert ii_match, f"No II value found in block: {content}"
        ii = int(ii_match.group(1))

        # Extract lats={NAME: value} — first lats= only (not full_lats)
        lats_match = re.search(r'(?<!full_)lats=\{(\w+):\s*(\d+)\}', content)
        assert lats_match, f"No lats found in block: {content}"
        name = lats_match.group(1).replace("CUSTOM", "")
        lat  = int(lats_match.group(2))

        results[name] = {"ii": ii, "lat": lat}
    return results

def main() -> None:
    global DELAY_VECTORS, PERFMODEL_DESC, MODEL_SUFFIX

    auto_generate_default=3

    parser = argparse.ArgumentParser(
        description="Generates CV32ISAAC variants for a list of custom instructions. " + \
                    "Pipeline has three stages (I, X, O) per custom instruction."
    )
    parser.add_argument(
        "-i", "--custom-instructions",
        type=lambda s: [item.strip() for item in s.split(",")],
        default=None,
        metavar="A,B,C",
        help="Comma-separated list of custom instructions (just the indicies).",
    )
    parser.add_argument(
        "-n", "--nvariants",
        type=int,
        default=-1,
        metavar="N_VARIANTS",
        help="Defines the max number of variants to generate (use -1 to get all variants)",
    )
    parser.add_argument(
        "--auto-generate",
        nargs='?',
        type=int,
        const=auto_generate_default,
        metavar="MAX_DELAY",
        help="Auto generates adequate number of variants (argument defines max delay per stage)",
    )
    parser.add_argument(
        "-ev", "--extract-variants",
        type=lambda s: Path(s).resolve(),
        metavar="EXPERIMENT_DIR",
        help="Extracts the variants from an xisaac-demo experiment",
    )
    parser.add_argument(
        "-ei", "--extract-instructions",
        type=lambda s: Path(s).resolve(),
        metavar="EXPERIMENT_DIR",
        help="Extracts the instructions names only from an xisaac-demo experiment",
    )
    parser.add_argument(
        "-t", "--template",
        type=Path,
        metavar="FILE",
        default=Path(os.path.dirname(__file__) + "/CV32E40PXISAAC.template"),
        help="Path to the template Core Perf DSL file.",
    )
    parser.add_argument(
        "--trace-template",
        type=Path,
        metavar="FILE",
        default=Path(os.path.dirname(__file__) + "/InstructionTrace_XISAAC.template"),
        help="Path to the template Instruction Trace JSON file.",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="",
        metavar="SUFFIX",
        help="Optional suffix for the generated CorePerfModel models.",
    )
    parser.add_argument(
        "--branch-pred-model",
        type=str,
        default="staBranchPredModel",
        metavar="BR_RPED_MODEL",
        help="Sets the branch prediction model (e.g. staBranchPredModel or dynBranchPredModel).",
    )

    parser.add_argument(
        "-o", "--output-coreperf",
        type=Path,
        default=None,
        metavar="FILE",
        help="Write the resulting corePerfDSl to this file instead.",
    )
    parser.add_argument(
        "--output-trace",
        type=Path,
        default=None,
        metavar="FILE",
        help="Write the resulting trace.json to this file instead.",
    )
    parser.add_argument(
        "-O", "--output-all",
        type=Path,
        default=None,
        metavar="FILE",
        help="Writes the resulting corePerf and trace.json to base file path instead.",
    )

    parser.add_argument(
        "-p", "--print-vector",
        action="store_true",
        help="Prints the latency vector for all custom instructions",
    )
    parser.add_argument(
        "--print-coreperf",
        action="store_true",
        help="Prints the generated core perf dsl file",
    )
    parser.add_argument(
        "--print-trace",
        action="store_true",
        help="Prints the generated instruction trace json file",
    )

    args = parser.parse_args()

    if args.nvariants != -1 and args.nvariants < 1:
        parser.error("`nvariants` must be >= 1!")

    if sum(int(bool(arg)) for arg in (args.custom_instructions, args.extract_variants, args.extract_instructions)) != 1:
        parser.error("conflicting or missing arguments: either use `--custom-instructions`, `--extract-variants` or `--extract-instructions`")

    if args.custom_instructions:
        if not args.auto_generate:
            args.auto_generate = auto_generate_default
    if args.extract_instructions:
        if not args.auto_generate:
            args.auto_generate = auto_generate_default
    if args.extract_variants:
        if args.auto_generate:
            parser.error("conflicting arguments: must not use `--extract_variants` with `--auto-generate`")

    if args.output_all:
        if args.output_coreperf or args.output_trace:
            parser.error("conflicting arguments: either use `-O` or `--output-coreperf` and `--output-trace` separately")
        args.output_coreperf = Path(f"{args.output_all}.corePerfDsl").resolve()
        args.output_trace    = Path(f"{args.output_all}.json").resolve()

    if args.suffix:
        assert not any(c.isspace() for c in args.suffix), "Suffix cannot contain spaces!"
        MODEL_SUFFIX = args.suffix

    # update branch prediction model
    PERFMODEL_DESC = PERFMODEL_DESC.replace('|BRANCH_MODEL|', args.branch_pred_model)

    # extract instructions
    if args.extract_instructions:
        path = args.extract_instructions / "compare_filtered_selected.csv"
        with open(path) as f:
            content = f.read()
            matches = re.finditer(r"custom(\d+)", content)
        args.custom_instructions = [ match.group(1) for match in matches ]

    # auto generate latency vectors
    if args.auto_generate:
        delay_vectors = generate_combinations(max_latency=args.auto_generate, keys=args.custom_instructions)
        DELAY_VECTORS = delay_vectors[:args.nvariants]

    # extract variants (with latency vectors)
    elif args.extract_variants:
        path = args.extract_variants / "uarch_ranking_filtered_selected.csv"
        with open(path, "r") as f:
            reader = csv.reader(f)
            header = next(reader)
            details_idx = header.index("details")
            variant_idx = header.index("")
            vectors = []
            for idx, row in enumerate(reader):
                variant  = int(row[variant_idx])
                parsed   = parse_ranking_row(row[details_idx])
                # compute I, X, O for each instruction type
                vector   = { name: lat_ii_to_ixo(vals["ii"], vals["lat"]) for name, vals in parsed.items() }
                vectors.append((variant, vector))

        vectors.sort(key=lambda e: e[0])
        DELAY_VECTORS = [ vector for _, vector in vectors ]
        # update arguments
        args.custom_instructions = list(DELAY_VECTORS[0].keys())

    if args.print_vector:
        for idx, instrs in enumerate(DELAY_VECTORS):
            print(SCOPE_NL(f"V{idx} =", (f"CUSTOM_{instr:<3}: {stages}" for instr, stages in instrs.items())))

    # create instruction trace json
    if args.output_trace or args.print_trace:
        template_text = args.trace_template.read_text(encoding="utf-8")
        content = replace_placeholders(template_text, instructions=args.custom_instructions, num_variants=-1)
        if args.output_trace:
            args.output_trace.parent.mkdir(parents=True, exist_ok=True)
            print(f"Writing trace.json to {args.output_trace}...")
            args.output_trace.write_text(content, encoding="utf-8")
            print( "done!")
        if args.print_trace:
            print(content)

    # create core perf dsl
    template_text = args.template.read_text(encoding="utf-8")
    content = replace_placeholders(template_text, instructions=args.custom_instructions, num_variants=len(DELAY_VECTORS))
    if args.output_coreperf:
        args.output_coreperf.parent.mkdir(parents=True, exist_ok=True)
        print(f"Writing coreperf to {args.output_coreperf}...")
        args.output_coreperf.write_text(content, encoding="utf-8")
        print( "done!")
    if args.print_coreperf:
        print(content)

if __name__ == "__main__":
    main()