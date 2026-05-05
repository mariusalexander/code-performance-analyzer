
import fnmatch
from collections import deque
from typing import List, Dict
from itertools import chain

from src.Common import Profile, Print
from src.InstructionBlockDescription import InstructionBlockDescription, InstructionDescription
from src.Timings import Timings
from src.TimingsPrinter import TimingsPrinter
from src.MaxPlusAlgebra import DelayExpression

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant as SchedVariant, SchedulingFunction, Node


class SequenceTimingModel:

    def __init__(self):
        self.variants: List['SequenceTimingVariant'] = []
        self.code_blocks: List['InstructionBlockDescription'] = []

    def create_variant(self, name: str) -> 'SequenceTimingVariant':
        variant = SequenceTimingVariant(name)
        self.variants.append(variant)
        return variant


class SequenceTimingVariant:

    def __init__(self, name: str):
        self.name    = name
        self.timings = {}
        self.timings_history = {}

    def add_code_block_timings(self, 
                               code_block: InstructionBlockDescription,
                               timings: Timings, 
                               timings_history: List[Timings] = []):
        self.timings[code_block.name]         = timings
        self.timings_history[code_block.name] = timings_history


class SequenceTransformer:
    """ Performs a static timing analysis on a code block similarly to how the C++ timing model operates. """

    _ignored_connector_models = set()

    def __init__(self, 
                 verbose=False,
                 accumulate_timings=True, 
                 print_history=False, 
                 default_dynamic_delay=None,
                 symbolic_vars: List[str] = []): 
        use_symbolic_analysis = len(symbolic_vars) > 0
        self.verbose                = verbose
        # NOTE: determine which calculation method to use upfront
        self.calculate_node_delay   = self.___calculate_symbolic_node_delay if use_symbolic_analysis else self.___calculate_node_delay
        self.symbolic_vars          = symbolic_vars
        # whether to accumulate the timings of each instructions, may have slight performance impact
        self.accumulate_timings     = print_history or accumulate_timings
        self.print_history          = print_history
        # default delay for all unmatched dynamic delays
        self.default_dynamic_delay  = default_dynamic_delay
        # cache for scheduling functions
        self.instr2schedfunc        = {}

    def __find_scheduling_function(self, 
                                   sched_variant: SchedVariant, 
                                   instr_name: InstructionDescription):
        """
        Helper function to find the schedule function for a given isntruction name.
        """
        # access cache
        if instr_name in self.instr2schedfunc:
            return self.instr2schedfunc[instr_name]
        try:
            # update cache
            [function] = filter(lambda e: e.name == instr_name, sched_variant.getAllSchedulingFunctions())
            self.instr2schedfunc[instr_name] = function
            return function
        except ValueError:
            raise RuntimeError(f"Scheduling function '{instr_name}' not found!")

    def analyze_all_variants(self, 
                             sched_model: SchedulingModel, 
                             code_blocks: List['InstructionBlockDescription']) -> SequenceTimingModel :
        """
        Performs the sequence analysis for all variants in the schedule model on all code blocks.
        """
        print("\n-- TRANSFORM: SEQUENCE_TRANSFORMER --")

        model = SequenceTimingModel()
        model.code_blocks = code_blocks
        with Profile(" > applying sequence transform to all variants"):
            for sched_variant in sched_model.getAllVariants():
                print(f" > applying sequence transform to variant {sched_variant.name}")
                variant = model.create_variant(sched_variant.name)
                self.__analyze_variant(variant, sched_variant, code_blocks)
        return model

    def __analyze_variant(self, 
                          variant: SequenceTimingVariant, 
                          sched_variant: SchedulingModel, 
                          code_blocks: List['InstructionBlockDescription']):
        """
        Performs the sequence analysis on all code blocks for the given schedule model variant.
        """
        self.instr2schedfunc = {}
        with Profile("  > applying sequence transform to all code blocks"):
            for code_block in code_blocks:
                with Profile(f"   >"):
                    timings, timings_history = self.analyze_basic_block(sched_variant, code_block)
                    variant.add_code_block_timings(code_block=code_block, timings=timings, timings_history=timings_history)

    def analyze_basic_block(self,
                            sched_variant: SchedVariant, 
                            code_block: InstructionBlockDescription) -> Timings:
        """
        Performs the sequence analysis on the given code block for the given schedule model variant.
        """
        print(f"  > applying sequence transform to code block '{code_block.name}'...")

        input_timings   = Timings(sched_variant=sched_variant)
        output_timings  = input_timings.copy()
        timings_history = []

        for connector_model in (c for c in input_timings.connector_models if c not in SequenceTransformer._ignored_connector_models):
            print(f"   > WARNING: The connector model '{connector_model}' may not be handled correctly!")
            SequenceTransformer._ignored_connector_models.add(connector_model)

        for instr in code_block.instructions:

            sched_function = self.__find_scheduling_function(sched_variant, instr.name)

            # evaluate scheduling instruction
            self.__append_instruction(
                sched_function, 
                instr,
                input_timings=input_timings,
                output_timings=output_timings,
                dynamic_vars=code_block.dynamic_vars
            )

            # outputs of this scheduling function feed into the next scheduling function
            input_timings.assign_to(output_timings)

            if self.accumulate_timings:
                timings_history.append(output_timings.copy())

        # print table
        if self.print_history:
            TimingsPrinter.print_history(code_block=code_block, timings_history=timings_history)

        return output_timings, timings_history

    def __append_instruction(self, 
                             sched_function: SchedulingFunction, 
                             instr: InstructionDescription, 
                             input_timings: Timings, 
                             output_timings: Timings, 
                             dynamic_vars: Dict[str, int|float]):
        """
        Evaluates the instruction (idx in instr) for the given input timings and returns the updated timings.
        """
        if self.verbose:
            print(f"   > {instr.idx}. instr: '{instr.name}' {'-'*(40-len(instr.name))}")

        root_node = sched_function.getRootNode()
        assert root_node is not None, f"Scheduling function '{sched_function.name}' has no root node!"

        # delays of visited nodes
        node_delays = {}

        visited = set()
        queue   = deque([root_node])

        while queue:

            node = queue.popleft()
            assert node not in visited, f"Node '{node.name}' visited twice!"
            visited.add(node)

            # delays of all ingoing nodes
            in_node_delays = self.__get_delays_of_in_nodes(node, node_delays)

            # inputs from ingoing edges
            in_connector_delays = self.__get_input_delays(node, instr, input_timings)

            # dynamic delay
            dynamic_delay = self.__get_dynamic_delays(node, dynamic_vars, instr)

            node_delay = self.calculate_node_delay(node, in_node_delays, in_connector_delays, dynamic_delay)
            node_delays[node.name] = node_delay

            # set outgoing edges
            self.__set_output_delays(node, node_delay, instr, output_timings)
            
            # iterate over all sucessor nodes for which all dependencies have been met
            for next_node in node.getAllOutNodes():
                if all(predecessor in visited for predecessor in next_node.getAllInNodes()):
                    queue.append(next_node)

        # making sure all nodes were processed
        assert all(n in visited for n in sched_function.getAllNodes()), \
                f"{instr.idx}. {instr.name}: Failed to visit all nodes! Missing:" + \
                 ", ".join(n.name for n in sched_function.getAllNodes() if n not in visited)

    def ___calculate_node_delay(self,
                                node: Node,
                                in_node_delays,
                                in_connector_delays,
                                dynamic_delay):
        if self.verbose:
            in_node_delays = list(in_node_delays)

        # evaluate delay
        node_delay  = max(0, 0, *in_connector_delays, *in_node_delays)
        node_delay += node.getDelay() + dynamic_delay

        if self.verbose:
            print(f"    > {node.name:<22} = {node_delay:>3} = " +\
                 (f"max({', '.join(str(v) for v in chain(in_connector_delays, in_node_delays) if v > 0)})") + \
                 (f" + {node.getDelay()}" if node.getDelay() > 0 else '') + \
                 (f" + {dynamic_delay}"   if dynamic_delay > 0 else ''))

        return node_delay

    def ___calculate_symbolic_node_delay(self,
                                         node: Node,
                                         in_node_delays,
                                         in_connector_delays,
                                         dynamic_delay):
        # NOTE: adapt logic once corePerfDsl support symbolic delays
        is_symbolic = any(name in node.name and "stage" not in node.name for name in self.symbolic_vars)

        result = DelayExpression.merge(
            inputs=chain(in_connector_delays, in_node_delays), 
            node_delay=(node.getDelay() + dynamic_delay) if not is_symbolic else 0,
            symbolic_name=node.name if is_symbolic else None
        )

        if self.verbose:
            with Print.indent_scope(31):
                print(f"    > {node.name:<22} = {result}")

        return result


    def __get_delays_of_in_nodes(self, 
                                 node: Node, 
                                 node_delays: Dict[str, int|float]) -> "iterable":
        """
        Returns the delays of all preceeding nodes.
        """
        return (node_delays[in_node.name] for in_node in node.getAllInNodes() if in_node.name in node_delays)

    def __get_dynamic_delays(self,
                             node: Node, 
                             dynamic_vars: Dict[str, int|float], 
                             instr: InstructionDescription) -> int|float:
        """
        Returns the dynamic delay in case the node is associated with a resource model. Otherwise returns a null delay.
        """
        if not node.hasDynamicDelay():
            return 0
        # build unique name for each dynamic variable
        # NOTE: could also use 'node.getResourceModel().name' here
        dynamic_delay_name = f"{node.name}_{instr.idx}"
        # find value for dynamic delay in code block descritpion
        for dynamic_variable, delay in dynamic_vars.items():
            if fnmatch.fnmatch(dynamic_delay_name, dynamic_variable):
                return delay
        # use default delay
        if self.default_dynamic_delay is not None:
            return self.default_dynamic_delay
        # unmatched delay
        raise RuntimeError(f"Unknown dynamic delay for node '{node.name}'!")

    def __get_input_delays(self, 
                           node: Node, 
                           instr: InstructionDescription, 
                           timings: Timings) -> "iterable":
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

    def __set_output_delays(self, 
                            node: Node, 
                            node_delay: int|float, 
                            instr: InstructionDescription, 
                            output_timings: Timings):
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