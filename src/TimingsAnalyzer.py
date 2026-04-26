

from typing import List, Dict, Optional
from collections import deque

from src.Common import Print, dotdict, err_print
from src.InstructionBlockDescription import InstructionBlockDescription
from src.Timings import Timings

from meta_models.scheduling_model.SchedulingModel import Variant as SchedVariant, SchedulingFunction, Node
from meta_models.structural_model.StructuralModel import Variant as StructVariant, Stage

class TimingsAnalyzer:

    def __init__(self, sched_variant: 'SchedVariant', struct_variant: 'StructVariant', accumulate_stalls=True):
        self.sched_variant      = sched_variant
        self.accumulate_stalls  = accumulate_stalls
        self.pipeline           = struct_variant.getPipeline()
        # cache for expected lantecies per scheduling function
        self.instr2latencies    = {} 

    def analyse_steady_state(self, 
                             code_block: 'InstructionBlockDescription', 
                             final_timings:'Timings' = None, 
                             timings_history: List['Timings'] = []):
        """
        Calculates the CPI for the steady state by calculating the expected end cycle 
        and comparing it to the actual end cycle.
        Can also determine which instructions experience a stall cycle.
        """
        if final_timings is None:
            assert len(timings_history) == len(code_block.instructions), "Invalid timings history!"
            final_timings = timings_history[-1]
        if self.accumulate_stalls:
            assert len(timings_history) == len(code_block.instructions), "Invalid timings history!"

        expected_end_cycle = 0
        num_instructions   = len(code_block.instructions)
        stall_history      = []

        if self.accumulate_stalls:
            for instr_idx, instr in enumerate(code_block.instructions):
                # NOTE: assuming commit-in-order
                end_stage          = self.__get_expected_latency(instr.name)
                expected_end_cycle = end_stage.value + instr_idx

                current_timings    = timings_history[instr_idx].timing_vars
                current_end_cycle  = current_timings[end_stage.name][0]
                diff = current_end_cycle - expected_end_cycle - sum(stall_history)
                assert diff >= 0, f"Expected {instr_idx}. instr. ('{instr.name}') to finish at CC {expected_end_cycle} " + \
                                  f"but finished earlier at CC {current_end_cycle - sum(stall_history)}! (diff: {diff} CC) " + \
                                   "-> instr. latency miscalculated?"
                stall_history.append(diff)

        # NOTE: assuming commit-in-order -> expected end cycle is simply the latency of
        #       the last instructions plus the number of preceeding instructions
        end_stage          = self.__get_expected_latency(code_block.instructions[-1].name)
        expected_end_cycle = end_stage.value + num_instructions - 1
        
        actual_end_cycle   = final_timings.timing_vars[end_stage.name][0]
        total_stall_cycles = actual_end_cycle - expected_end_cycle
        cpi = (num_instructions + total_stall_cycles) / num_instructions

        if self.accumulate_stalls:
            assert sum(stall_history) == total_stall_cycles, \
                   f"Stall cycles mismatch! ({sum(stall_history)} vs. expected {total_stall_cycles})"

        return dotdict({ 
            "cpi": cpi, 
            "total_stall_cycles": total_stall_cycles, 
            "num_instructions": num_instructions, 
            "stall_history": stall_history 
        })

    def __get_expected_latency(self, instr_name: str):
        """
        Helper function to determine the cycle when the given instruction finishes (i.e. its latency).
        """
        # access cache
        try: return self.instr2latencies[instr_name]
        except KeyError: pass

        has_timing_var = lambda e: not e.isDynamic() and e.getTimingVariable()
        [sched_function] = filter(lambda e: e.name == instr_name, self.sched_variant.getAllSchedulingFunctions())
        used_timing_vars = list(edge.getTimingVariable().name for node in sched_function.getAllNodes()
                                                                  for edge in node.getAllOutEdges() if has_timing_var(edge))
        end_stage = self.__get_expected_end_cycle(used_timing_vars, sched_function, instr_name=instr_name)
        # cache expected latency of stage for current instruction
        self.instr2latencies[instr_name] = end_stage
        return end_stage

    @staticmethod
    def __uses_timing_var(node: 'Node', timing_var_name: str, is_input=True):
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

    def __get_expected_end_cycle(self,
                                 used_stages: List[str],
                                 sched_function: 'SchedulingFunction',
                                 next_stages:List['Stage'] = None,
                                 input_stage:Optional['Stage'] = None,
                                 input_cc:int = 0,
                                 instr_name:str = None):
        """
        Returns the end cycle of the used stages.
        """
        if next_stages is None:
            next_stages = self.pipeline.getFirstStages()
        
        next_stages = list(stage for stage in next_stages if stage.name in used_stages)
        if not next_stages:
            return dotdict({ "name": input_stage.name, "value": input_cc })

        [current_stage] = next_stages
        
        current_cc = None
        if sub_stages := current_stage.getFirstSubStages():
            result = self.__get_expected_end_cycle(used_stages, sched_function, next_stages=sub_stages, input_stage=current_stage, input_cc=input_cc, instr_name=instr_name)
            # expected cc of this stage is the end cycle of the used substages (if any)
            if result.name != current_stage.name:
                current_cc = result.value

        if current_cc is None:
            # NOTE: this step is needed as some stages may not have any latencies (dummy stages?)
            # determine mirco operation that uses current timing variable
            [source_mirco_op] = (node for node in sched_function.getAllNodes() if TimingsAnalyzer.__uses_timing_var(node, current_stage.name, is_input=True))
            latency = self.__get_latency_of_stage(source_mirco_op, current_stage.name)
            # resources along the way need more than one cycle -> stage will always cause stalls
            if latency > 1:
                err_print(f"WARN: mirco-op. '{current_stage.name}' of instr. '{instr_name}' will always induce +{latency - 1} stall cycle(s)!")
                latency = 1
            assert latency >= 0, f"Stage '{current_stage.name}' of instr. '{instr_name}' finishes before mirco-op started '{source_mirco_op.name}'?"
            current_cc = input_cc + latency

        # traverse next stages
        next_stages = current_stage.getNextStages()
        if not next_stages:
            return dotdict({ "name": current_stage.name, "value": current_cc })

        return self.__get_expected_end_cycle(used_stages, sched_function, next_stages=next_stages, input_stage=current_stage, input_cc=current_cc, instr_name=instr_name)

    def __get_latency_of_stage(self, current_mirco_op:'Node', timing_var_name:str, instr_name=None):
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
        return current_delay + max(self.__get_latency_of_stage(next_node, timing_var_name) for next_node in next_nodes)
