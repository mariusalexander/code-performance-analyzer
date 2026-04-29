

from typing import List, Dict, Optional
from collections import deque

from src.Common import Print, Profile, dotdict, find_variant
from src.InstructionBlockDescription import InstructionBlockDescription
from src.Timings import Timings
from src.TimingsPrinter import TimingsPrinter
from src.SequenceTransformer import SequenceTransformer, SequenceTimingModel, SequenceTimingVariant
from src.MaxPlusAlgebra import DelayFunctionList_v2

from meta_models.scheduling_model.SchedulingModel import Variant as SchedulingModel, Variant as SchedVariant, SchedulingFunction, Node
from meta_models.structural_model.StructuralModel import Variant as StructuralModel, Variant as StructVariant, Stage

class TimingsAnalyzer:

    def __init__(self,
                 assume_same_pipeline=False,
                 print_history=False,
                 accumulate_stalls=False,
                 print_code_blocks=False):
        self.assume_same_pipeline   = assume_same_pipeline
        self.print_history          = print_history
        self.print_code_blocks      = print_code_blocks
        self.accumulate_stalls      = accumulate_stalls
        # cache for expected lantecies per scheduling function
        self.instr2latencies        = {}

    def estimate_cpi(self, 
                     sequence_model: SequenceTimingModel,
                     schedule_model: SchedulingModel, 
                     struct_model: StructuralModel):
        print("\n-- FRONTEND: TIMING ANALYSIS --")

        sched_variant = struct_variant = None
        results = {}
        print(" > performing timing analysis...")
        with Profile(" > performing entire timing analysis"):
            for sequence_variant in sequence_model.variants:
                if not self.assume_same_pipeline or not sched_variant:
                    sched_variant  = find_variant(schedule_model, sequence_variant.name)
                    struct_variant = find_variant(struct_model, sequence_variant.name)
                    self.instr2latencies = {}

                assert sequence_variant.name not in results, \
                    f"Duplicate result entry for variant '{sequence_variant.name}'!"
                results[sequence_variant.name] = self.__estimate_cpi_for_variant(sequence_variant, sched_variant, struct_variant, sequence_model.code_blocks)
        return results

    def solve_symbolic_delay(self, 
                             sequence_model: SequenceTimingModel,
                             schedule_model: SchedulingModel, 
                             struct_model: StructuralModel,
                             symbolic_delay_vectors):
        print("\n-- FRONTEND: SYMBOLIC TIMING ANALYSIS --")
        try:
            [sequence_variant] = sequence_model.variants
        except ValueError:
            raise RuntimeError("Symbolic timing analysis assumes a single base variant!")
        results = {}
        sched_variant  = find_variant(schedule_model, sequence_variant.name)
        struct_variant = find_variant(struct_model, sequence_variant.name)

        print(" > performing symbolic timing analysis...")
        with Profile(" > performing entire timing analysis"):
            for variant_name, vector in symbolic_delay_vectors.items():
                assert variant_name not in results, \
                    f"Duplicate result entry for variant '{variant_name}'!"

                self.input_vector = symbolic_delay_vectors[variant_name]
                results[variant_name] = self.__estimate_cpi_for_variant(sequence_variant, sched_variant, struct_variant, sequence_model.code_blocks)

        return results

    def __estimate_cpi_for_variant(self,
                                   sequence_variant: SequenceTimingVariant,
                                   sched_variant: SchedVariant,
                                   struct_variant: StructVariant,
                                   code_blocks: List['InstructionBlockDescription']):
        print(f"  > performing timing analysis for variant '{sequence_variant.name}'...")

        results = {}
        for code_block in code_blocks:
            assert code_block.name not in results, \
                   f"Duplicate result entry for code block '{code_block.name}'!"

            final_timings   = sequence_variant.timings[code_block.name]
            timings_history = sequence_variant.timings_history[code_block.name]

            result = self.__estimate_cpi_for_code_block(code_block, final_timings, timings_history, sched_variant, struct_variant)
            results[code_block.name] = result

            print( "   >",
                f"code block: {code_block.name:>10},",
                f"CPI: {result.cpi:>8.6f},",
                f"instructions: {result.num_instructions:>3},",
                f"stall cycles: {result.total_stall_cycles:>3},",
                f"rel. weight: {result.weight:.5f}")

            if self.print_code_blocks:
                with Print.indent_scope(3):
                    print("   >", code_block)

            if self.print_history:
                print(f"   > timings for code block '{code_block.name}:")
                TimingsPrinter.print_history(code_block=code_block, timings_history=timings_history, stall_history=result.stall_history)
                print()

        return results

    def __estimate_cpi_for_code_block(self,
                                      code_block: InstructionBlockDescription,
                                      final_timings:Timings,
                                      timings_history: List['Timings'],
                                      sched_variant,
                                      struct_variant):
        """
        Calculates the CPI for the steady state by calculating the expected end cycle
        and comparing it to the actual end cycle.
        Can also determine which instructions experience a stall cycle.
        """
        num_instructions = len(code_block.instructions)

        if self.accumulate_stalls:
            assert len(timings_history) == len(code_block.instructions), \
                   "Cannot map timings to instructions!"

            stall_history = []
            for instr_idx, instr in enumerate(code_block.instructions):
                # NOTE: assuming commit-in-order
                end_stage          = self.__get_expected_latency(instr.name, sched_variant, struct_variant)
                expected_end_cycle = end_stage.value + instr_idx

                current_timings    = timings_history[instr_idx].timing_vars
                current_end_cycle  = current_timings[end_stage.name][0]

                diff = current_end_cycle - expected_end_cycle - sum(stall_history)
                assert diff >= 0, f"Expected {instr_idx}. instr. ('{instr.name}') to finish at CC {expected_end_cycle + sum(stall_history)} " + \
                                  f"but finished earlier at CC {current_end_cycle}! (diff: {diff} CC) " + \
                                   "-> instr. latency miscalculated?"
                stall_history.append(diff)

        # NOTE: assuming commit-in-order -> expected end cycle is simply the latency of
        #       the last instructions plus the number of preceeding instructions
        end_stage          = self.__get_expected_latency(code_block.instructions[-1].name, sched_variant, struct_variant)
        expected_end_cycle = end_stage.value + num_instructions - 1

        actual_end_cycle   = final_timings.timing_vars[end_stage.name][0]
        if isinstance(actual_end_cycle, DelayFunctionList_v2):
            actual_end_cycle = actual_end_cycle.resolve(self.input_vector)
            
        total_stall_cycles = actual_end_cycle - expected_end_cycle
        cpi = (num_instructions + total_stall_cycles) / num_instructions

        results = dotdict({
            "cpi": cpi,
            "total_stall_cycles": total_stall_cycles,
            "num_instructions": num_instructions,
            "weight": code_block.weight if code_block.weight else -1
        })

        if self.accumulate_stalls:
            assert sum(stall_history) == total_stall_cycles, \
                   f"Stall cycles mismatch! ({sum(stall_history)} vs. expected {total_stall_cycles})"
            results.stall_history = stall_history

        return results

    def __get_expected_latency(self, instr_name: str, sched_variant: SchedVariant, struct_variant: StructVariant):
        """
        Helper function to determine the cycle when the given instruction finishes (i.e. its latency).
        """
        # access cache
        if instr_name in self.instr2latencies:
            return self.instr2latencies[instr_name]

        # timings, _ = SequenceTransformer().analyze_basic_block(sched_variant, InstructionBlockDescription("dummy").addInstruction(instr_name, rd=0, rs1=0, rs2=0))
        # max_timing = max((dotdict({ "name": name, "value": max(history)}) for name, history in timings.timing_vars.items()), key=lambda e: e.value)
        # self.instr2latencies[instr_name] = max_timing
        # return max_timing

        pipeline = struct_variant.getPipeline()
        has_timing_var = lambda e: not e.isDynamic() and e.getTimingVariable()
        [sched_function] = filter(lambda e: e.name == instr_name, sched_variant.getAllSchedulingFunctions())
        used_timing_vars = list(edge.getTimingVariable().name for node in sched_function.getAllNodes()
                                                              for edge in node.getAllOutEdges() if has_timing_var(edge))
        end_stage = TimingsAnalyzer.__get_expected_end_cycle(used_timing_vars, sched_function, next_stages=pipeline.getFirstStages(), instr_name=instr_name)
        # print(max_timing, "vs", end_stage)
        # cache expected latency of stage for current instruction
        self.instr2latencies[instr_name] = end_stage
        return end_stage

    @staticmethod
    def __uses_timing_var(node: Node, timing_var_name: str, is_input=True):
        """
        Returns whether the node (mirco-op) sets or uses the given timing variable.
        """
        for edge in node.getAllInEdges() if is_input else node.getAllOutEdges():
            if edge.isDynamic(): continue
            timing_var = edge.getTimingVariable()
            if timing_var.name != timing_var_name: continue
            if edge.depth == (timing_var.getNumElements() if is_input else 1):
                return True
        return False

    @staticmethod
    def __get_expected_end_cycle(used_stages: List[str],
                                 sched_function: 'SchedulingFunction',
                                 next_stages:List['Stage'],
                                 input_stage:Optional['Stage'] = None,
                                 input_cc:int = 0,
                                 instr_name:str = None):
        """
        Returns the end cycle of the used stages.
        """
        next_stages = list(stage for stage in next_stages if stage.name in used_stages)
        if not next_stages:
            return dotdict({ "name": input_stage.name, "value": input_cc })

        [current_stage] = next_stages

        current_cc = None
        if sub_stages := current_stage.getFirstSubStages():
            sub_pipeline_end_cycle = TimingsAnalyzer.__get_expected_end_cycle(
                used_stages,
                sched_function,
                next_stages=sub_stages,
                input_stage=current_stage,
                input_cc=input_cc,
                instr_name=instr_name
            )
            # expected cc of this stage is the end cycle of the used substages (if any)
            if sub_pipeline_end_cycle.name != current_stage.name:
                current_cc = sub_pipeline_end_cycle.value

        if current_cc is None:
            # NOTE: this step is needed as some stages may not have any latencies (dummy stages?)
            # determine mirco operation that uses current timing variable
            [source_mirco_op] = (node for node in sched_function.getAllNodes()
                                      if TimingsAnalyzer.__uses_timing_var(node, current_stage.name, is_input=True))
            latency = TimingsAnalyzer.__get_latency_of_stage(source_mirco_op, current_stage.name)
            # resources along the way need more than one cycle -> stage will always cause stalls
            if latency > 1:
                print( "   > WARNING:",
                      f"mirco-op. '{current_stage.name}' of instr. '{instr_name}' " + \
                      "will always induce +{latency - 1} stall cycle(s)!")
                latency = 1
            assert latency >= 0, f"Stage '{current_stage.name}' of instr. '{instr_name}'" + \
                                 f"finishes before mirco-op started '{source_mirco_op.name}'?"
            current_cc = input_cc + latency

        # traverse next stages
        next_stages = current_stage.getNextStages()
        if not next_stages:
            return dotdict({ "name": current_stage.name, "value": current_cc })

        return TimingsAnalyzer.__get_expected_end_cycle(
            used_stages,
            sched_function,
            next_stages=next_stages,
            input_stage=current_stage,
            input_cc=current_cc,
            instr_name=instr_name
        )

    @staticmethod
    def __get_latency_of_stage(current_mirco_op: Node, timing_var_name:str, instr_name=None):
        """
        Returns the latency (CCs) from the given mirco op to a mirco op that sets the given timing variable.
        """
        # NOTE: assuming dynamic delays are always > 0
        current_delay = max(current_mirco_op.getDelay(), int(current_mirco_op.hasDynamicDelay()))
        if TimingsAnalyzer.__uses_timing_var(current_mirco_op, timing_var_name, is_input=False):
            return current_delay
        next_nodes = current_mirco_op.getAllOutNodes()
        if not next_nodes:
            raise RuntimeError(f"Timing variable '{timing_var_name}' is never set by instr. '{instr_name}'!")
        return current_delay + max(TimingsAnalyzer.__get_latency_of_stage(next_node, timing_var_name) for next_node in next_nodes)
