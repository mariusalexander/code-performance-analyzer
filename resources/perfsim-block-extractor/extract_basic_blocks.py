import argparse
import json
import os
import math
from itertools import product
from typing import List, Dict, Any

def calculate_ninstr(block: Dict[str, Any]) -> int:
    """Calculate the weight of a basic block: call count * instruction length."""
    call_cnt = block['callCnt']
    instr_length = len(block['instrs'])
    return call_cnt * instr_length

def calculate_weight(block: Dict[str, Any], total_ninstructions) -> int:
    """Calculate the weight of a basic block: call count * instruction length."""
    weight = calculate_ninstr(block)
    return(weight / total_ninstructions)

def filter_blocks(blocks: List[Dict[str, Any]], threshold_percent: float) -> List[Dict[str, Any]]:
    """Filter blocks by weight threshold and sort by weight in descending order."""
    total_ninstructions = sum(calculate_ninstr(block) for block in blocks)
    threshold = (threshold_percent / 100) * total_ninstructions

    # Filter blocks exceeding the threshold
    filtered_blocks = [block for block in blocks if calculate_ninstr(block) >= threshold]

    filtered_ninstrs = sum(len(block["instrs"]) for block in filtered_blocks)
    return filtered_blocks, total_ninstructions, filtered_ninstrs

def print_block_summary(block: Dict[str, Any], total_ninstructions: int, overlapping: bool = False) -> None:
    """Print a summary of a basic block with its weight as a percentage."""
    print(f"code block id {f'{block['id']}':>4} " + \
          f"(0x{block['startPc']:08x} - 0x{block['endPc']:08x}), " + \
          f"{len(block['instrs']):>3} instructions, " + \
          f"{calculate_weight(block, total_ninstructions)*100:6.3f}% weight, " + \
          f"count: {block['callCnt']:>6} " + ("(overlapping)" if overlapping else ""))

def print_detailed_block(block: Dict[str, Any]) -> None:
    """Print detailed instruction information for a basic block."""
    start_pc = block['startPc']
    for idx, instr in enumerate(block['instrs']):
        pc = start_pc + idx * 4
        instr_str = instr.get("name", "<unknown>")
        if "rs1" in instr:
            instr_str += f" rs1={instr['rs1']}"
        if "rs2" in instr:
            instr_str += f", rs2={instr['rs2']}"
        if "rd" in instr:
            instr_str += f", rd={instr['rd']}"
        if "imm" in instr:
            instr_str += f", imm={instr['imm']}"
        print(f"    {idx}. 0x{pc:x}    {instr_str}")

def format_instr_line(pc: int, instr: Dict[str, Any]) -> str:
    """Format a single instruction as a tab-separated line for export."""
    name = instr['name']
    registers = []
    for field in ("rd", "rs1", "rs2", "imm"):
        if field in instr:
            registers.append(f"{field}={instr[field]}")
    regs_str = "\t".join(registers) if registers else ""
    return f"0x{pc:08x}\t{name:>8}\t{regs_str}"

def export_block(block: Dict[str, Any], output_dir: str) -> None:
    """Export basic block to a text file."""
    start_pc = block['startPc']
    filename = f"0x{start_pc:08x}.txt"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        for idx, instr in enumerate(block['instrs']):
            pc = start_pc + idx * 4
            f.write(format_instr_line(pc, instr) + "\n")

def export_metadata(blocks: List[Dict[str, Any]], total_ninstructions: int, output_dir: str, dynamic_delays = None) -> None:
    """Export metadata for all exported basic blocks to experiment.json."""
    metadata = []
    for block in blocks:
        start_pc = block['startPc']
        num_instrs = len(block['instrs'])
        weight = calculate_weight(block, total_ninstructions)
        metadata.append({
            "name": f"0x{start_pc:08x}.txt",
            "weight_per_instr": weight / num_instrs if num_instrs > 0 else 0.0,
            "weight": weight,
            "num_instrs": num_instrs,
            "dynamic_delays": (dynamic_delays[block['id']] if dynamic_delays else None)
        })

    filepath = os.path.join(output_dir, "experiment.json")
    with open(filepath, "w") as f:
        json.dump(metadata, f, indent=4)

def find_average_delays(blocks: List[Dict[str, Any]]) -> dict:
    total_delays = {}
    for block in blocks:
        for instr in block['instrs']:
            if not 'dynamicDelays' in instr:
                continue
            for cat, delays in instr['dynamicDelays'].items():
                if cat not in total_delays:
                    total_delays[cat] = delays
                    continue
                for delay, count in delays.items():
                    if delay not in total_delays[cat]:
                        total_delays[cat][delay] = count
                        continue
                    total_delays[cat][delay] += count

    result = {
        'weight': 1,
        'variables': {}
    }

    print(f"Extracted Dynamic Delays:")
    for cat, delays in total_delays.items():
        total_count = sum(count for count in delays.values())
        average = sum(float(delay) * (count / total_count) for delay, count in delays.items())

        # TODO: delay categories must be mapped dynamically to micro-actions (make configurable!)
        # NOTE: must match prediction tool's way of accessing dynamic delays
        match cat:
            case "iCache":
                result['variables']['IPort_R_*'] = average
            case "dCache":
                result['variables']['DPort_?_*'] = average
            case "div":
                result['variables']['DIV_*'] = average
            case "divU":
                result['variables']['DIVU_*'] = average
            case _:
                raise RuntimeError(f"I don't know how '{cat}' maps to which micro-actions!")
        print(f" - Average delay of '{cat}' = {average:.5}")

    return { block['id']: [result] for block in blocks }

def find_average_delays_per_instr(blocks: List[Dict[str, Any]]) -> dict:
    results = {}

    print(f"Extracted Dynamic Delays:")
    for block in blocks:
        result = {
            'weight': 1,
            'variables': {}
        }
        print(f" - Averages for basic-block 0x{block['startPc']:08x}:")
        for idx, instr in enumerate(block['instrs']):
            if not 'dynamicDelays' in instr:
                continue
            for cat, delays in instr['dynamicDelays'].items():
                total_count = sum(count for count in delays.values())
                average = sum(float(delay) * (count / total_count) for delay, count in delays.items())

                # TODO: delay categories must be mapped dynamically to micro-actions (make configurable!)
                # NOTE: must match prediction tool's way of accessing dynamic delays
                match cat:
                    case "iCache":
                        result['variables'][f'IPort_R_{idx}'] = average
                    case "dCache":
                        result['variables'][f'DPort_?_{idx}'] = average
                    case "div":
                        result['variables'][f'DIV_{idx}'] = average
                    case "divU":
                        result['variables'][f'DIVU_{idx}'] = average
                    case _:
                        raise RuntimeError(f"I don't know how '{cat}' maps to which micro-actions!")
                print(f"   - Average delay of {idx:>3}. instr {instr['name']:>8} ('{cat}') = {average:.5}")
        results[block['id']] = [result]

    return results

def find_rounded_delays_per_instr(blocks: List[Dict[str, Any]]) -> dict:
    results = {}

    print(f"Extracted Dynamic Delays:")
    for block in blocks:
        result = {
            'weight': 1,
            'variables': {}
        }
        print(f" - Averages for basic-block 0x{block['startPc']:08x}:")
        for idx, instr in enumerate(block['instrs']):
            if not 'dynamicDelays' in instr:
                continue
            for cat, delays in instr['dynamicDelays'].items():
                total_count = sum(count for count in delays.values())
                average = sum(float(delay) * (count / total_count) for delay, count in delays.items())
                #print(f"   - Average delay of {idx:>3}. instr {instr['name']:>8} ('{cat}') = {average:.5f}")
                average = round(average)
                # TODO: delay categories must be mapped dynamically to micro-actions (make configurable!)
                # NOTE: must match prediction tool's way of accessing dynamic delays
                match cat:
                    case "iCache":
                        result['variables'][f'IPort_R_{idx}'] = average
                    case "dCache":
                        result['variables'][f'DPort_?_{idx}'] = average
                    case "div":
                        result['variables'][f'DIV_{idx}'] = average
                    case "divU":
                        result['variables'][f'DIVU_{idx}'] = average
                    case _:
                        raise RuntimeError(f"I don't know how '{cat}' maps to which micro-actions!")
                print(f"   - Average delay of {idx:>3}. instr {instr['name']:>8} ('{cat}') = {average}")
        results[block['id']] = [result]

    return results

def find_delay_combinations(blocks: List[Dict[str, Any]]) -> dict:
    total_delays = {}
    for block in blocks:
        for instr in block['instrs']:
            if 'dynamicDelays' not in instr:
                continue
            for cat, delays in instr['dynamicDelays'].items():
                if cat not in total_delays:
                    total_delays[cat] = dict(delays)
                    continue
                for delay, count in delays.items():
                    if delay not in total_delays[cat]:
                        total_delays[cat][delay] = count
                    else:
                        total_delays[cat][delay] += count

    # TODO: delay categories must be mapped dynamically to micro-actions (make configurable!)
    # Map categories to variable names
    CAT_TO_VAR = {
        "iCache": "IPort_R_*",
        "dCache": "DPort_?_*",
        "div":    "DIV_*",
        "divU":   "DIVU_*",
    }

    # Convert counts to probabilities, keyed by variable name
    # { "IPort_R_*": { "1": 0.9999, "5": 0.0001 }, ... }
    prob_by_var = {}
    print("Extracted Dynamic Delays:")
    for cat, delays in total_delays.items():
        if cat not in CAT_TO_VAR:
            raise RuntimeError(f"I don't know how '{cat}' maps to which micro-actions!")
        var = CAT_TO_VAR[cat]
        total_count = sum(delays.values())
        probs = {delay: count / total_count for delay, count in delays.items()}
        prob_by_var[var] = probs
        print(f" - '{cat}' ({var}): { {d: f'{p:.5f}' for d, p in probs.items()} }")

    # Cartesian product of all (var, delay) options, weighted by joint probability
    vars_list = list(prob_by_var.keys())
    delay_options = [list(prob_by_var[v].items()) for v in vars_list]  # [(delay, prob), ...]

    combinations = []
    for combo in product(*delay_options):
        # combo is ((delay_for_var0, prob0), (delay_for_var1, prob1), ...)
        weight = 1.0
        variables = {}
        for var, (delay, prob) in zip(vars_list, combo):
            weight *= prob
            variables[var] = float(delay)
        combinations.append({"weight": weight, "variables": variables})

    # Sort descending by weight for readability
    combinations.sort(key=lambda x: x["weight"], reverse=True)

    MIN_WEIGHT = 0.01 # percentage threshold

    combinations = [c for c in combinations if c["weight"] >= MIN_WEIGHT]

    return {block['id']: combinations for block in blocks}

def main():
    # argument parser
    parser = argparse.ArgumentParser(description="Analyze basic blocks in a JSON file.")
    parser.add_argument("json_file", metavar="FILE",
                        help="Path to the JSON file containing basic blocks.")
    parser.add_argument("-t", "--threshold", type=float, default=5.0, metavar="PERCENTAGE",
                        help="Weight threshold percentage (default: 5%%).")
    parser.add_argument("-p", "--print", action="store_true",
                        help="Print detailed instruction information.")
    parser.add_argument("-s", "--sort", nargs="?", const="pc", default="weight", metavar="KEY",
                        help="Sort filtered blocks by key: pc, id, weight (default: pc).")
    parser.add_argument("-e", "--export", metavar="OUTPUT_DIR",
                        help="Export each filtered basic block to a .txt file in the given directory.")
    parser.add_argument("-d", "--delays", nargs="?", const="app_avg", default=None, metavar="METRIC",
                        help="...")
    args = parser.parse_args()

    # load extracted blocks
    try:
        with open(args.json_file, "r") as file:
            all_blocks = json.load(file)
    except FileNotFoundError:
        print(f"Error: File '{args.json_file}' not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: File '{args.json_file}' is not valid JSON.")
        return

    # filter
    filtered_blocks, total_ninstructions, filtered_ninstrs = filter_blocks(all_blocks, args.threshold)

    # extract overlapping bbs
    overlapping = {}
    last_bb = None
    for curr_bb in sorted(filtered_blocks, key=lambda b: b['startPc']):
        if last_bb is not None and curr_bb['startPc'] < last_bb['endPc']:
            overlapping[curr_bb['startPc']] = 1
            overlapping[last_bb['startPc']] = 1
        last_bb = curr_bb

    # sort
    sort_key = None
    reverse  = False
    match args.sort:
        case "id":
            sort_key=lambda b: b['id']
        case "pc":
            sort_key=lambda b: b['startPc']
        case "weight":
            reverse = True
            sort_key=calculate_ninstr
        case _:
            parser.error("Invalid Sort Key specified!")

    filtered_blocks.sort(key=sort_key, reverse=reverse)

    filtered_weight = sum(calculate_weight(block, total_ninstructions) for block in filtered_blocks)

    dynamic_delays = None
    if args.delays is not None:
        match args.delays:
            case "app" | "app_avg" | "app_average":
                dynamic_delays = find_average_delays(all_blocks)
            case "bb"  | "bb_avg"  | "bb_average":
                dynamic_delays = find_average_delays(filtered_blocks)
            case "instr"  | "instr_avg"  | "instr_average":
                dynamic_delays = find_average_delays_per_instr(filtered_blocks)
            case "round" | "instr_round":
                dynamic_delays = find_rounded_delays_per_instr(filtered_blocks)
            case "comb" | "bb_comb":
                dynamic_delays = find_delay_combinations(filtered_blocks)
            case _:
                parser.error("Invalid Delay Metric specified!")

    # print results
    print(f"Filtered BBs with weight exceeding {args.threshold}%:")
    for block in filtered_blocks:
        print_block_summary(block, total_ninstructions, block['startPc'] in overlapping)
        if args.print:
            print_detailed_block(block)
            print()
    # TODO: output number unique instructions
    print(f"Info:      {total_ninstructions:>6} total instructions\n" +
          f"Extracted: filtered {filtered_ninstrs:>4} instructions, total weight {filtered_weight*100:6.3f}%")

    # export results
    if args.export:
        os.makedirs(args.export, exist_ok=True)
        for block in filtered_blocks:
            export_block(block, args.export)
        export_metadata(filtered_blocks, total_ninstructions, args.export, dynamic_delays=dynamic_delays)
        print(f"Exported {len(filtered_blocks)} basic block(s) and experiment.json to '{args.export}/'.")

if __name__ == "__main__":
    main()