
import fnmatch
from collections import deque
from typing import List, Dict
from itertools import chain

from src.Common import dotdict, Profile, Print, print_err, find_variant
from src.InstructionBlockDescription import InstructionBlockDescription, InstructionDescription
from src.Timings import Timings
from src.TimingsPrinter import TimingsPrinter

from src.MaxPlusAlgebra import DelayVariable, MaxTerm, DelayFunction, DelayFunctionList_v2

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant as SchedVariant, SchedulingFunction, Node
from meta_models.structural_model.StructuralModel import StructuralModel, Variant as StructVariant

class SymbolicTimings(Timings):
    pass

class SymbolicSequenceTimingModel:

    def __init__(self):
        self.variants:List['SymbolicSequenceTimingVariant'] = []

    def create_variant(self, name: str) -> 'SymbolicSequenceTimingVariant':
        variant = SymbolicSequenceTimingVariant(name)
        self.variants.append(variant)
        return variant


class SymbolicSequenceTimingVariant:

    def __init__(self, name: str):
        self.name    = name
        self.timings = {}
        self.timings_history = {}

    def add_code_block_timings(self, code_block: 'InstructionBlockDescription', timings: 'Timings', timings_history: List['Timings'] = []):
        self.timings[code_block.name]         = timings
        self.timings_history[code_block.name] = timings_history


class SymbolicSequenceTransformer:

    def __init__(self, verbose=False, accumulate_timings=True, print_history=False, default_dynamic_delay=None, symbolic_vars=[]):
        self.verbose                = verbose
        # whether to accumulate the timings of each instructions, may have slight performance impact
        self.accumulate_timings     = print_history or accumulate_timings
        self.print_history          = print_history
        # default delay for all unmatched dynamic delays
        self.default_dynamic_delay  = default_dynamic_delay
        # cache for scheduling functions
        self.instr2schedfunc        = {}
        self.symbolic_vars          = symbolic_vars

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

    def analyze_all_variants(self, sched_model: 'SchedulingModel', struct_model: 'StructuralModel', code_blocks: List['InstructionBlockDescription']) -> 'SymbolicSequenceTimingModel' :
        """
        Performs the symbolic sequence analysis for all variants in the schedule model on all code blocks.
        """
        print("\n-- TRANSFORM: SYMBOLIC_SEQUENCE_TRANSFORMER --")

        model = SymbolicSequenceTimingModel()
        with Profile(" > applying symbolic sequence transform to all variants"):
            for sched_variant in sched_model.getAllVariants():
                print(f" > applying symbolic sequence transform to variant {sched_variant.name}")
                struct_variant = find_variant(struct_model, sched_variant.name)
                variant = model.create_variant(sched_variant.name)
                self.__analyze_variant(variant, sched_variant, struct_variant, code_blocks)
        return model

    def __analyze_variant(self, variant: 'SymbolicSequenceTimingVariant', sched_variant: 'SchedulingModel', struct_variant: 'StructuralModel', code_blocks: List['InstructionBlockDescription']):
        """
        Performs the symbolic sequence analysis on all code blocks for the given schedule model variant.
        """
        self.instr2schedfunc = {}
        with Profile("  > applying symbolic sequence transform to all code blocks"):
            for code_block in code_blocks:
                with Profile(f"   >"):
                    timings, timings_history = self.__analyze_basic_block(sched_variant, struct_variant, code_block)
                    variant.add_code_block_timings(code_block=code_block, timings=timings, timings_history=timings_history)

    def __analyze_basic_block(self, sched_variant: 'SchedVariant', struct_variant: 'StructVariant', code_block: 'InstructionBlockDescription') -> 'Timings':
        """
        Performs the symbolic sequence analysis on the given code block for the given schedule model variant.
        """
        print(f"  > applying symbolic sequence transform to code block '{code_block.name}'...")

        if not code_block.is_basic_block():
            instructions = list((idx, instr) for idx, instr in enumerate(code_block.instructions[:-1]) if instr.is_branch())
            print_err(f"WARN: Code block '{code_block.name}' is not a basic block:\n{'\n'.join(f'\tinstr. {e[0]}. {e[1]}' for e in instructions)}")

        timings = Timings(sched_variant=sched_variant)
        timings_history = []

        if timings.connector_models:
            print_err(f"WARN: The following connector models may not be handled correctly:\n{'\n'.join(f"\t'{key}'" for key in timings.connector_models)}")

        for instr_idx, instr in enumerate(code_block.instructions):

            sched_function = self.__find_scheduling_function(sched_variant, instr.name)

            # evaluate scheduling instruction
            output_timings = self.__append_instruction(sched_function, instr, instr_idx, timings, dynamic_vars=code_block.dynamic_vars)

            # outputs of this scheduling function feed into the next scheduling function
            timings = output_timings

            if self.accumulate_timings:
                timings_history.append(output_timings)

        # print table
        if self.print_history:
            TimingsPrinter.print_history(code_block=code_block, timings_history=timings_history)

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

            functions = DelayFunctionList_v2()
            # delays of all ingoing nodes
            in_node_delays = self.__get_delays_of_in_nodes(node, node_delays)
            for in_node in in_node_delays:
                for other_function in in_node:
                    functions.merge(other_function)

            # inputs from ingoing edges
            input_delays   = self.__get_input_delays(node, instr, input_timings)
            for in_delay in input_delays:
                if isinstance(in_delay, DelayFunctionList_v2):
                    for other_function in in_delay:
                        functions.merge(other_function)
                else:
                    functions.append_static_var(DelayVariable('', in_delay))

            dynamic_delay  = self.__get_dynamic_delays(node, dynamic_vars, instr_idx)
            if dynamic_delay > 0:
                functions.plus(dynamic_delay)

            # symbolic variable
            is_symbolic = any(name in node.name and "stage" not in node.name for name in self.symbolic_vars)
            if is_symbolic:
                print(node.name, "SYMBOLIC!")
                functions.append_coefficient(DelayVariable(node.name, 1))
            elif node.getDelay() > 0:
                    functions.plus(node.getDelay())

            #functions = functions.simplified()
            node_delays[node.name] = functions

            if self.verbose:
                with Print.indent_scope(31):
                    print(f"    > {node.name:<22} = {functions}")

            # set outgoing edges
            self.__set_output_delays(node, functions, instr, output_timings)

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

    def __get_input_delays(self, node: 'Node', instr: 'InstructionDescription', timings: 'SymbolicTimings') -> "iterable":
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

    def __set_output_delays(self, node: 'Node', node_delay: int|float, instr: 'InstructionDescription', output_timings: 'SymbolicTimings'):
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