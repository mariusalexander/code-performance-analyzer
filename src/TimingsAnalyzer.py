

from typing import List, Dict
from collections import deque

from src.Common import Print, dotdict, err_print
from src.InstructionBlockDescription import InstructionBlockDescription
from src.Timings import Timings

from meta_models.scheduling_model.SchedulingModel import Variant as SchedVariant, SchedulingFunction, Node, StaticEdge
from meta_models.structural_model.StructuralModel import Variant as StructVariant

class TimingsAnalyzer:

    def __init__(self, sched_variant: 'SchedVariant', struct_variant: 'StructVariant', accumulate_stalls=True):
        self.sched_variant      = sched_variant
        self.struct_variant     = struct_variant
        self.accumulate_stalls  = accumulate_stalls
        # cache for expected lantecies per scheduling function
        self.instr2latencies    = {} 

    def analyse_steady_state(self, code_block: 'InstructionBlockDescription', final_timings:'Timings' = None, timings_history: List['Timings'] = []):
        """
        Calculates the CPI for the steady state by calculating the expected end cycle and comparing it to the actual end cycle.
        Can also print which instructions experienced a stall cycle.
        """
        if final_timings is None:
            assert len(timings_history) == len(code_block.instructions), "Invalid timings history!"
            final_timings = timings_history[-1]
        if self.accumulate_stalls:
            assert len(timings_history) == len(code_block.instructions), "Invalid timings history!"

        expected_end_cycle = 0
        stall_history      = []

        for instr_idx, instr in enumerate(code_block.instructions):
            # calculate expected end cycle on latency for instr and current instr index
            target_stage        = self.__get_expected_latency(instr.name)
            expected_end_cycle  = target_stage.value + instr_idx

            if self.accumulate_stalls:
                current_timings   = timings_history[instr_idx]
                current_end_cycle = current_timings.timing_vars[target_stage.name][0]
                diff = current_end_cycle - expected_end_cycle - sum(stall_history)
                stall_history.append(diff)

        actual_end_cycle   = final_timings.timing_vars[target_stage.name][0]
        total_stall_cycles = actual_end_cycle - expected_end_cycle
        num_instructions   = len(code_block.instructions)
        cpi = (num_instructions + total_stall_cycles) / num_instructions

        if self.accumulate_stalls:
            assert sum(stall_history) == total_stall_cycles, \
                   f"Stall cycles mismatch! ({sum(stall_history)} vs expected {total_stall_cycles})"

        return dotdict({ 
            "cpi": cpi, 
            "total_stall_cycles": total_stall_cycles, 
            "num_instructions": num_instructions, 
            "stall_history": stall_history 
        })

    def __get_expected_latency(self, instr_name):
        """
        Helper function to find the schedule function for a given isntruction name.
        """
        # access cache
        try: return self.instr2latencies[instr_name]
        except KeyError: pass

        [sched_function] = tuple(filter(lambda e: e.name == instr_name, self.sched_variant.getAllSchedulingFunctions()))
        pipeline         = self.struct_variant.getPipeline()

        used_timing_vars    = list(edge.getTimingVariable().name for node in sched_function.getAllNodes() for edge in node.getAllOutEdges() if not edge.isDynamic() and edge.getTimingVariable())
        expected_timings    = self.__get_expected_stage_timings(pipeline.getFirstStages(), used_timing_vars).stages
        top_level_stages    = (stage.name for stage in pipeline.getAllStages() if stage.parent.isTopPipeline() and stage.name in expected_timings)

        target_stage        = max((dotdict({ "name": name, "value": expected_timings[name]}) for name in top_level_stages), key=lambda obj: obj.value)
        # cache expected latency of stage for current instruction
        self.instr2latencies[instr_name] = target_stage
        return target_stage

    def __get_expected_stage_timings(self, next_stages, used_stages, cc=1):
        stages   = {}
        while next_stages:
            queue        = deque(next_stages)
            next_stages  = []
            cc_increment = cc
            while queue:
                stage = queue.popleft()
                if stage.name not in used_stages:
                    continue

                stage_depth = 0
                for subpipeline in stage.getPipelines():
                    substages = subpipeline.getFirstStages()
                    for substage in substages:
                        if substage.name not in used_stages:
                            continue
                        assert stage_depth == 0, f"Multiple sub-pipelines for stage '{stage.name}' are active at the same time!"
                        results = self.__get_expected_stage_timings(next_stages=[substage], used_stages=used_stages, cc=cc)
                        stage_depth = results.depth
                        stages     |= results.stages
                        break
                
                if stage_depth > 0:
                    current_cc  = stage_depth - 1
                else:
                    current_cc = cc

                stages[stage.name] = current_cc
                cc_increment = max(cc_increment, current_cc)

                next_stages += stage.getNextStages()

            cc = cc_increment + 1

        return dotdict({ "depth": cc, "stages": stages })