
import fnmatch
from collections import deque
from typing import List, Dict
from itertools import chain

from src.Common import dotdict, Profile, Print, err_print, find_variant
from src.InstructionBlockDescription import InstructionBlockDescription, InstructionDescription
from src.Timings import Timings
from src.TimingsPrinter import TimingsPrinter

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant as SchedVariant, SchedulingFunction, Node
from meta_models.structural_model.StructuralModel import StructuralModel, Variant as StructVariant

def get_pipeline_timings(next_stages, used_stages, cc=1):
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
                    assert stage_depth == 0, f"Multiple sub-pipleines for stage '{stage.name}' are active at the same time!"
                    results = get_pipeline_timings(next_stages=[substage], used_stages=used_stages, cc=cc)
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


class SequenceTimingModel:

    def __init__(self):
        self.variants:List['SequenceTimingVariant'] = []

    def create_variant(self, name: str) -> 'SequenceTimingVariant':
        variant = SequenceTimingVariant(name)
        self.variants.append(variant)
        return variant


class SequenceTimingVariant:

    def __init__(self, name: str):
        self.name    = name
        self.timings = {}
        self.timings_history = {}

    def add_code_block_timings(self, code_block: 'InstructionBlockDescription', timings: 'Timings', timings_history: List['Timings'] = []):
        self.timings[code_block.name]         = timings
        self.timings_history[code_block.name] = timings_history


class SequenceTransformer:
    """ Performs a static timing analysis on a code block similarly to how the C++ timing model operates. """

    def __init__(self, verbose=False, print_timings=True, print_stalls=True, default_dynamic_delay=None):
        self.verbose       = verbose
        self.print_timings = print_timings
        self.print_stalls  = print_stalls
        # default delay for all unmatched dynamic delays
        self.default_dynamic_delay = default_dynamic_delay
        # cache for scheduling functions
        self.instr2schedfunc       = {}

    def __find_scheduling_function(self, sched_variant, instr_name):
        """
        Helper function to find the schedule function for a given isntruction name.
        """
        # access cache
        try: return self.instr2schedfunc[instr_name]
        except KeyError: pass

        for function in filter(lambda e: e.name == instr_name, sched_variant.getAllSchedulingFunctions()):
            self.instr2schedfunc[instr_name] = function
            return function
        raise RuntimeError(f"Scheduling function '{instr_name}' not found!")

    def analyze_all_variants(self, sched_model: 'SchedulingModel', struct_model: 'StructuralModel', code_blocks: List['InstructionBlockDescription']) -> 'SequenceTimingModel' :
        """
        Performs the sequence analysis for all variants in the schedule model on all code blocks.
        """
        print("\n-- TRANSFORM: SEQUENCE_TRANSFORMER --")

        model = SequenceTimingModel()
        with Profile(" > applying sequence transform to all variants"):
            for sched_variant in sched_model.getAllVariants():
                self.instr2schedfunc = {}
                print(f" > applying sequence transform to variant {sched_variant.name}")
                struct_variant = find_variant(struct_model, sched_variant.name)
                variant = model.create_variant(sched_variant.name)
                self.__analyze_variant(variant, sched_variant, struct_variant, code_blocks)
        return model

    def __analyze_variant(self, variant: 'SequenceTimingVariant', sched_variant: 'SchedulingModel', struct_variant: 'StructuralModel', code_blocks: List['InstructionBlockDescription']):
        """
        Performs the sequence analysis on all code blocks for the given schedule model variant.
        """
        with Profile("  > applying sequence transform to all code blocks"):
            for code_block in code_blocks:
                with Profile(f"   >"):
                    timings, timings_history = self.__analyze_basic_block(sched_variant, struct_variant, code_block)
                    variant.add_code_block_timings(code_block=code_block, timings=timings, timings_history=timings_history)

    def __analyze_basic_block(self, sched_variant: 'SchedVariant', struct_variant: 'StructVariant', code_block: 'InstructionBlockDescription') -> 'Timings':
        """
        Performs the sequence analysis on the given code block for the given schedule model variant.
        """
        print(f"  > applying sequence transform to code block '{code_block.name}'...")

        if not code_block.is_basic_block():
            instructions = list((idx, instr) for idx, instr in enumerate(code_block.instructions) if instr.is_branch())
            err_print(f"WARN: Code block '{code_block.name}' is not a basic block:\n{'\n'.join(f'\tinstr. {e[0]}. {e[1]}' for e in instructions)}")

        timings = Timings(sched_variant=sched_variant)
        timings_history = []

        if timings.connector_models:
            err_print(f"WARN: The following connector models may not be handled correctly:\n{'\n'.join(f"\t'{key}'" for key in timings.connector_models)}")

        expected_end_cycle = 0
        actual_end_cycle   = 0
        accumulated_stalls = 0
        total_stall_cycles = 0

        num_instr = len(code_block.instructions)
        for instr_idx, instr in enumerate(code_block.instructions):

            sched_function = self.__find_scheduling_function(sched_variant, instr.name)

            pipeline = struct_variant.getPipeline()
            used_timing_vars    = list(edge.getTimingVariable().name for node in sched_function.getAllNodes() for edge in node.getAllOutEdges() if not edge.isDynamic() and edge.getTimingVariable())
            expected_timings    = get_pipeline_timings(pipeline.getFirstStages(), used_timing_vars).stages
            main_stages         = ( stage.name for stage in pipeline.getAllStages() if stage.parent == pipeline and stage.name in expected_timings )

            target_stage        = max((dotdict({ "name": name, "value": expected_timings[name]}) for name in main_stages), key=lambda obj: obj.value)
            expected_end_cycle  = target_stage.value + instr_idx

            # evaluate scheduling instruction
            output_timings = self.__append_instruction(sched_function, instr, instr_idx, timings, dynamic_vars=code_block.dynamic_vars)

            # outputs of this scheduling function feed into the next scheduling function
            timings = output_timings

            if self.print_timings:
                timings_history.append(output_timings)

            actual_end_cycle = output_timings.timing_vars[target_stage.name][0]

            if self.print_stalls and actual_end_cycle > (expected_end_cycle + accumulated_stalls):
                diff = actual_end_cycle - expected_end_cycle - accumulated_stalls
                accumulated_stalls += diff
                print(f"{' ' * Print.indent}> {instr_idx:>3}. instr. {f"'{instr.name}'":>12} experienced +{diff} stall cycle(s)")

        total_stall_cycles = actual_end_cycle - expected_end_cycle

        if self.print_stalls:
            assert accumulated_stalls == total_stall_cycles, f"Stall cycles mismatch! ({accumulated_stalls} vs expected {total_stall_cycles})"

        # print table
        if self.print_timings:
            TimingsPrinter.print_history(timings_history, code_block)
            print("STALLS:", total_stall_cycles, "\tCPI:", (num_instr + total_stall_cycles) / num_instr)

        return timings, timings_history

    def __append_instruction(self, sched_function: 'SchedulingFunction', instr: 'InstructionDescription', instr_idx:int, input_timings: 'Timings', dynamic_vars: Dict[str, int|float]) -> 'Timings':
        """
        Evaluates the instruction (idx in instr) for the given input timings and returns the updated timings.
        """
        if self.verbose:
            print(f"   > {instr_idx}. instr: '{instr.name}' {'-'*(40-len(instr.name))}")

        root_node = sched_function.getRootNode()
        assert root_node is not None, f"Scheduling function '{sched_function.name}' has no root node!"

        # delays of visited nodes
        node_delays = {}
        # make copy to avoid overriding input timings 
        output_timings = input_timings.copy()

        visited = set()
        queue   = deque([root_node])

        while queue:

            node = queue.popleft()
            assert node not in visited, f"Node '{node.name}' visited twice!"
            visited.add(node)
            
            # delays of all ingoing nodes
            in_node_delays = self.__get_delays_of_in_nodes(node, node_delays)

            # inputs from ingoing edges
            input_delays   = self.__get_input_delays(node, instr, input_timings)

            # dynamic delay
            dynamic_delay  = self.__get_dynamic_delays(node, dynamic_vars, instr_idx)

            # evaluate delay
            node_delay  = max(0, 0, *input_delays, *in_node_delays)
            node_delay += node.getDelay() + dynamic_delay

            node_delays[node.name] = node_delay

            if self.verbose:
                print(f"    > {node.name:<20} = {node_delay:>3} = " +\
                     (f"max({', '.join(str(v) for v in chain(input_delays, in_node_delays) if v > 0)})") + \
                     (f" + {node.getDelay()}" if node.getDelay() > 0 else '') + \
                     (f" + {dynamic_delay}"   if dynamic_delay > 0 else ''))

            # set outgoing edges
            self.__set_output_delays(node, node_delay, instr, output_timings)

            # iterate over all sucessor nodes for which all dependencies have been met
            for next_node in node.getAllOutNodes():
                if all(predecessor in visited for predecessor in next_node.getAllInNodes()):
                    queue.append(next_node)

        # making sure all nodes were processed
        assert all(n in visited for n in sched_function.getAllNodes()), \
                f"{instr_idx}. {instr.name}: Failed to visit all nodes! Missing: {', '.join(n.name for n in sched_function.getAllNodes() if n not in visited)}"

        return output_timings

    def __get_delays_of_in_nodes(self, node: 'Node', node_delays: Dict[str, int|float]) -> "iterable":
        """ 
        Returns the delays of all preceeding nodes. 
        """
        return list(node_delays[in_node.name] for in_node in node.getAllInNodes() if in_node.name in node_delays)

    def __get_dynamic_delays(self, node: 'Node', dynamic_vars: Dict[str, int|float], instr_idx: int) -> int|float :
        """ 
        Returns the dynamic delay in case the node is associated with a resource model. Otherwise returns a null delay. 
        """
        if not node.hasDynamicDelay():
            return 0
        # build unique name for each dynamic variable
        # NOTE: could also use 'node.getResourceModel().name' here
        dynamic_delay_name = f"{node.name}_{instr_idx}"
        # find value for dynamic delay in code block descritpion
        for dynamic_variable, delay in dynamic_vars.items():
            if fnmatch.fnmatch(dynamic_delay_name, dynamic_variable):
                return delay
        # use default delay
        if self.default_dynamic_delay is not None:
            return self.default_dynamic_delay
        # unmatched delay
        raise RuntimeError(f"Unknown dynamic delay for node '{node.name}'!")

    def __get_input_delays(self, node: 'Node', instr: 'InstructionDescription', timings: 'Timings') -> "iterable":
        """ 
        Returns a list of ingoing timings derived from the timing variables, registers, and other connector models. 
        """
        static_delays = []
        for edge in node.getAllInEdges():
            if edge.isDynamic():
                connector_model = edge.getConnectorModel()
                assert connector_model, f"Expected ingoing dynamic edge of '{instr.name}:{node.name}' to be linked to a connector model!"
                static_delays.append(timings.get_connector(connector_model, edge.name, instr))
                continue
            # timing variable
            timing_var = edge.getTimingVariable()
            assert timing_var, f"Expected ingoing static edge of '{instr.name}:{node.name}' to be linked to a timing variable!"
            static_delays.append(timings.get_timing_var(timing_var, edge.depth))

        return static_delays

    def __set_output_delays(self, node: 'Node', node_delay: int|float, instr: 'InstructionDescription', output_timings: 'Timings'):
        """ 
        Updates the outgoing timings of timing variables, registers, and other connector models. 
        """
        for edge in node.getAllOutEdges():
            if edge.isDynamic():
                connector_model = edge.getConnectorModel()
                assert connector_model, f"Expected outgoing dynamic edge of '{instr.name}:{node.name}' to be linked to a connector model!"
                output_timings.update_connector(connector_model, edge.name, instr, node_delay)
                continue
            # timing variable
            timing_var = edge.getTimingVariable()
            assert timing_var, f"Expected outgoing static edge of '{instr.name}:{node.name}' to be linked to a timing variable!"
            output_timings.update_timing_var(timing_var, edge.depth, node_delay)
            continue