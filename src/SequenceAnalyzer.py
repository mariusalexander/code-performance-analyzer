
import copy
import fnmatch
import math
from collections import deque
from typing import List, Dict
from itertools import chain
from objprint import op

from src.Common import dotdict, Profile, Print, eprint
from src.InstructionBlockDescription import InstructionBlockDescription

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant as SchedVariant, SchedulingFunction, Node, StaticEdge
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

    def add_code_block_timings(self, code_block: 'InstructionBlockDescription', timings: 'Timings'):
        self.timings[code_block.name] = timings

class Timings:
    """ Data struct denoting timings of a schedule (i.e. values of timing variables and which registers are available). """

    __known_register_models = ["regModel", "clobberModel"]

    def __init__(self, sched_variant: 'SchedVariant'):
        # NOTE: corePerfDsl models that should be interpreted like register models have to be added here!

        # NOTE: assuming all pipeline stages are available (here -1 to indicate unset timing variables)
        # each timing variable has a "history" (depth of edges/stage's capacity)
        self.timing_vars      = { timing_var.name : [ -1 for _ in range(0, timing_var.getNumElements()) ] for timing_var in sched_variant.getAllTimingVariables() }
        # register models
        self.register_models  = { model.name : {} for model in sched_variant.getAllConnectorModels() if model.name in Timings.__known_register_models }
        # other connector models that are ignored (e.g. branch prediction)
        self.connector_models = { model.name : {} for model in sched_variant.getAllConnectorModels() if model.name not in Timings.__known_register_models }
    
    def copy(self):
        """ 
        Creates a copy of the current timings. 
        """
        return copy.deepcopy(self)

    def get_timing_var(self, timing_var: 'TimingVariable', depth: int):
        """
        Returns the value of the given timing variable for the given depth
        """
        assert depth > 0, f"Expected ingoing static edges to have a depth > 1 (actual depth: {depth})!"
        assert timing_var.name in self.timing_vars, f"Unknown timing variable '{timing_var.name}'!"
        assert len(self.timing_vars[timing_var.name]) >= depth, f"Ingoing static edge exceeds capacity of timing variable '{timing_var.name}'!"
        return self.timing_vars[timing_var.name][depth - 1]

    def update_timing_var(self, timing_var: 'TimingVariable', depth: int, node_delay: int|float):
        """
        Updates the value of the given timing variable for the given depth
        """
        assert depth == 1, f"Expected outgoing static edges to have a depth == 1 (actual depth: {depth})!"
        assert timing_var.name in self.timing_vars, f"Unknown timing variable '{timing_var.name}'!"
        # shift history of timing vars for edges with depth
        self.timing_vars[timing_var.name] = [node_delay] + self.timing_vars[timing_var.name][:-1]

    def get_connector(self, connector_model: 'ConnectorModel', connector_name: str, instr: 'InstructionDescription'):
        """
        Returns the value of the given connector. If the connector belongs the to a register model, the value of the corresponding register is returned.
        """
        # register model
        if connector_model.name in Timings.__known_register_models:
            register_model = self.register_models[connector_model.name]
            # get which register was used from instruction operands
            assert connector_name in instr, f"Instruction '{instr.name}' requires operand '{connector_name}'! (undefined)"
            register_no = instr[connector_name]
            if register_no not in register_model:
                # NOTE: assuming all registers are available
                return 0 # register was not set yet -> assume 0 delay -> no effect
            return register_model[register_no]

        # non-register connector model
        assert connector_model.name in self.connector_models, f"Unknown connector model '{connector_model.name}'!"
        model = self.connector_models[connector_model.name]
        if connector_name not in model:
            # NOTE: assuming all connectors are available
            return 0 # edge was not set yet -> assume 0 delay -> no effect
        return model[connector_name]

    def update_connector(self, connector_model: 'ConnectorModel', connector_name: str, instr: 'InstructionDescription', node_delay: int|float):
        """
        Updates the value of the given connector. If the connector belongs the to a register model, the value of the corresponding register is updated.
        """
        # register model
        if connector_model.name in Timings.__known_register_models:
            assert connector_name in instr, f"Instruction '{instr.name}' requires operand '{connector_name}'! (undefined)"
            register_no = instr[connector_name]
            self.register_models[connector_model.name][register_no] = node_delay
            return

        # non-register connector model
        # NOTE: to include branch taken/not taken, map outgoing edges to input edges (e.g. for staBranchPred: map 'Pc_np' to 'Pc')
        assert connector_model.name in self.connector_models, f"Unknown connector model '{connector_model.name}'!"
        self.connector_models[connector_model.name][connector_name] = node_delay

class TimingsPrinter:
    """ Helper class to pretty-print the timings during the analysis. """
    
    def __init__(self, timings: 'Timings', code_block: 'InstructionBlockDescription', digits=3, s_spacer='|', w_spacer='||', h_line='-'):
        # default spacer 
        self.s_spacer  = s_spacer 
        # spacer inbetween timing variables
        self.t_spacer  = w_spacer if any(len(values) > 1 for values in timings.timing_vars.values()) else s_spacer
        # spacer for other connector models
        self.w_spacer  = w_spacer
        self.h_line    = h_line
        self.digits    = digits

        self.registers = sorted(set(instr.rd for instr in code_block.instructions if instr.rd is not None))
        self.register_header = self.__register_column({ reg:f"r{reg}" for reg in self.registers })
        self.timing_vars_entries = { name : len(history) for name, history in timings.timing_vars.items() if all(c not in name for c in ["OM6", "OM12", "OM14"]) }
        self.timing_vars_spacing = { name : max(len(self.__simplify_name(name)), len(self.__timing_var_column(history))) for name, history in timings.timing_vars.items() if all(c not in name for c in ["OM6", "OM12", "OM14"]) }
        self.register_spacing    = { name : max(len(name), len(self.register_header)) for name in timings.register_models }

    def __simplify_name(self, name):
        """ Simplifies the name of a timing variable. """
        return name.replace("_stage", "").replace("stage", "").replace("CUSTOM", "cstm")

    def __timing_var_column(self, history):
        """" Generates the columns for the history of a timing variable."""
        return self.s_spacer.join(f'{value:>{self.digits}}' if value >= 0 else f'{'-':>{self.digits}}' for value in history)

    def __register_column(self, model):
        """" Generates the columns for the given register model. """
        return self.s_spacer.join(f'{model[reg]:>{self.digits+1}}' if reg in model else f'{'-':>{self.digits+1}}' for reg in self.registers)

    @staticmethod
    def print_history(timings_history: List['Timings'], code_block: 'InstructionBlockDescription', s_spacer='|', w_spacer='||', h_line='-', fprint=print):
        if len(timings_history) == 0: return

        # determine how many digits are necessary
        digits = max(len(str(value)) for timing in timings_history for values in timing.timing_vars.values() for value in values)
        table  = TimingsPrinter(timings=timings_history[0], code_block=code_block, digits=digits, s_spacer=s_spacer, w_spacer=w_spacer, h_line=h_line)

        table.print_header(fprint=fprint)
        for idx, [timing, instr] in enumerate(zip(timings_history, code_block.instructions)):
            table.print_row(timings=timing, instr_name=instr.name, idx=idx, fprint=fprint)

    def print_header(self, fprint=print):
        # ommit indicies for the history of a timing variable if its capacity is one
        generate_timing_var_columns = lambda name: range(1, self.timing_vars_entries[name] + 1) if self.timing_vars_entries[name] > 1 else []

        header_row1  = f"index {self.s_spacer} instruction {self.w_spacer} "
        header_row2  = f"      {self.s_spacer}             {self.w_spacer} "
        header_row1 += f" {self.t_spacer} ".join(f'{self.__simplify_name(name):>{spacing}}' for name, spacing in self.timing_vars_spacing.items())
        header_row1 += f" {self.w_spacer} "
        header_row2 += f" {self.t_spacer} ".join(self.__timing_var_column(generate_timing_var_columns(name)).rjust(spacing) for name, spacing in self.timing_vars_spacing.items())
        header_row2 += f" {self.w_spacer} "
        header_row1 += f" {self.w_spacer} ".join(f'{name:>{spacing}}' for name, spacing in self.register_spacing.items())
        header_row2 += f" {self.w_spacer} ".join(self.register_header.rjust(spacing) for spacing in self.register_spacing.values())

        fprint(header_row1)
        fprint(header_row2)
        if self.h_line:
            fprint(self.h_line * len(max(header_row1, header_row2)))

    def print_row(self, timings: 'Timings', instr_name:str, idx:int, fprint=print):
        row =  f"{idx:>4}. {self.s_spacer} {instr_name:>11} {self.w_spacer} "
        row += f" {self.t_spacer} ".join(self.__timing_var_column(timings.timing_vars[name]).rjust(spacing) for name, spacing in self.timing_vars_spacing.items())
        row += f" {self.w_spacer} "
        row += f" {self.w_spacer} ".join(self.__register_column(timings.register_models[model]).rjust(spacing) for model, spacing in self.register_spacing.items())
        fprint(row)

class SequenceAnalyzer:
    """ Performs a static timing analysis on a code block similarly to how the C++ timing model operates. """

    def __init__(self, verbose=False, print_timings=True, default_dynamic_delay=None):
        self.verbose       = verbose
        self.print_timings = print_timings
        # default delay for all unmatched dynamic delays
        self.default_dynamic_delay = default_dynamic_delay
        # NOTE: preliminary optimization
        self.schedf_map         = {} # cache for scheduling functions
        self.schedf_map_variant = "" # name of variant to identify when to invalidate the cache

    def __find_variant(self, model, name):
        """
        Helper function to find a variant with the given name in the scheudle or structural model.
        """
        for variant in model.variants:
            if variant.name == name:
                return variant
        raise RuntimeError(f"Variant '{name}' not found!")

    def __find_scheduling_function(self, sched_variant, instr_name):
        """
        Helper function to find the schedule function for a given isntruction name.
        """
        # access cache
        if self.schedf_map_variant == sched_variant.name:
            try: return self.schedf_map[instr_name]
            except KeyError: pass
        else: self.schedf_map_variant = sched_variant.name

        for function in filter(lambda e: e.name == instr_name, sched_variant.getAllSchedulingFunctions()):
            self.schedf_map[instr_name] = function
            return function
        raise RuntimeError(f"Scheduling function '{instr_name}' not found!")

    def analyze_all_variants(self, sched_model: 'SchedulingModel', struct_model: 'StructuralModel', code_blocks: List['InstructionBlockDescription']) -> 'SequenceTimingModel' :
        """
        Performs the sequence analysis for all variants in the schedule model on all code blocks.
        """
        print("\n-- TRANSFORM: SEQUENCE_ANALYZER --")

        model = SequenceTimingModel()
        with Profile(" > applying sequence transform to all variants"):
            for sched_variant in sched_model.getAllVariants():
                print(f" > applying sequence transform to variant {sched_variant.name}")
                struct_variant = self.__find_variant(struct_model, sched_variant.name)
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
                    timings = self.__analyze_basic_block(sched_variant, struct_variant, code_block)
                    variant.add_code_block_timings(code_block=code_block, timings=timings)

    def __analyze_basic_block(self, sched_variant: 'SchedVariant', struct_variant: 'StructVariant', code_block: 'InstructionBlockDescription') -> 'Timings':
        """
        Performs the sequence analysis on the given code block for the given schedule model variant.
        """
        print(f"  > applying sequence transform to code block '{code_block.name}'...")

        if not code_block.is_basic_block():
            instructions = list((idx, instr) for idx, instr in enumerate(code_block.instructions) if instr.is_branch())
            eprint(f"WARN: Code block '{code_block.name}' is not a basic block:\n{'\n'.join(f'\tinstr. {e[0]}. {e[1]}' for e in instructions)}")

        timings = Timings(sched_variant=sched_variant)
        timings_history = []

        if timings.connector_models:
            eprint(f"WARN: The following connector models may not be handled correctly:\n{'\n'.join(f"\t'{key}'" for key in timings.connector_models)}")

        total_stall_cycles = 0

        instr_idx = 0
        num_instr = len(code_block.instructions)
        for instr in code_block.instructions:

            sched_function = self.__find_scheduling_function(sched_variant, instr.name)

            print_stalls = True
            if print_stalls:
                pipeline = struct_variant.getPipeline()
                used_timing_vars = list(edge.getTimingVariable().name for node in sched_function.getAllNodes() for edge in chain(node.getAllOutEdges()) if not edge.isDynamic() and edge.getTimingVariable())
                expected_timings = get_pipeline_timings(pipeline.getFirstStages(), used_timing_vars).stages
                main_stages      = [ stage.name for stage in pipeline.getAllStages() if stage.parent == pipeline ]

                target_stage        = max((dotdict({ "name": name, "value": expected_timings[name] }) for name in main_stages), key=lambda obj: obj.value)
                target_stage.value += instr_idx + total_stall_cycles

            # evaluate scheduling instruction
            output_timings = self.__append_instruction(sched_function, instr, instr_idx, timings, dynamic_vars=code_block.dynamic_vars)

            if self.print_timings:
                timings_history.append(output_timings)

            if print_stalls:
                target_stage_output = output_timings.timing_vars[target_stage.name][0]
                stall_cycles        = target_stage_output - target_stage.value
                total_stall_cycles += stall_cycles

                if stall_cycles:
                    print(f"{' ' * Print.indent}> {instr_idx:>3}. instr. ({instr.name}) => +{stall_cycles} CC stall")

            # outputs of this scheduling function feed into the next scheduling function
            timings    = output_timings
            instr_idx += 1

        # print table
        if self.print_timings:
            TimingsPrinter.print_history(timings_history, code_block)
            print("STALLS:", total_stall_cycles, "\tCPI:", (len(code_block.instructions) + total_stall_cycles) / len(code_block.instructions))

        return timings

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