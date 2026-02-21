#
# Copyright 2025 Chair of EDA, Technical University of Munich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import copy
from collections import deque
from typing import List, Dict

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, StaticEdge

from src.Common import dotdict, Profile
from src.InstructionBlockDescription import InstructionBlockDescription


class BlockSchedulingTransformer:
    """Block Scheduling Transformer"""

    def __init__(self, verbose=True):
        self._id = 1024
        self.verbose = verbose
        # whether to use more descriptive names for edges to registers, like 'r2 (Xa)' instead of 'Xa'
        self.rename_edges = True
        # TODO: infer these attributes dynamically from core perf dsl or the struct model
        self._register_count   = 32
        self._register_models  = ["regModel", "clobberModel"]
        self._target_register_mapping = {
            "regModel" : "Xd",
            "clobberModel": "Cb_in",
        }
        self._branch_prediction_models  = ["noBranchPredModel", "staBranchPredModel", "dynBranchPredModel"]
        self._supported_models = self._register_models + self._branch_prediction_models

    def transform(self, sched_model:SchedulingModel, block_descriptions:List[InstructionBlockDescription]) -> SchedulingModel:
        """
        Transforms basic blocks (BB) into a block scheudling model.
        The model is a regular Scheduling Model which only contains a scheduling function for each BB.
        """
        print()
        print("-- TRANSFORM: BLOCK_SCHEDULING_MODEL --")

        blockSchedulingModel = SchedulingModel()

        # iterate over each variant
        for sched_variant in sched_model.getAllVariants():
            print(f" > Generating block scheduling model for '{sched_variant.name}'")

            block_variant = blockSchedulingModel.createVariant(sched_variant.name)

            # simply copy over timing variables and external models
            block_variant.timingVariables = copy.deepcopy(sched_variant.timingVariables)
            block_variant.externalModels  = copy.deepcopy(sched_variant.externalModels)

            # iterate over each BB
            for block_desc in block_descriptions:
                assert block_desc.has_valid_instructions()
                with Profile(f"  > took"):
                    self.__generateBlockSchedulingFunction(sched_variant, block_variant, block_desc)

        return blockSchedulingModel

    def __generateBlockSchedulingFunction(self, sched_variant:Variant, block_variant:Variant, block_desc:InstructionBlockDescription):
        """
        """
        print(f"  > Generating block scheduling function for '{block_desc.name}'...")

        # create block scheudling function
        block_function = block_variant.createSchedulingFunction(block_desc.name, self._id)
        self._id += 1

        # helper struct to resolve external and internal edges
        mappings = dotdict()
        # mappings for timing variables
        mappings.timingVariables = {}
        for timing_var in block_variant.getAllTimingVariables():
            mappings.timingVariables[timing_var.name] = [ None for _ in range(0, timing_var.getNumElements()) ]
        # mappings for register models
        for reg_model in self._register_models:
            mappings[reg_model] = { reg:None for reg in range(0, self._register_count) }
        # mappings for branch prediction
        # TODO: infer connectors automatically
        for pred_model in self._branch_prediction_models:
            mappings[pred_model] = { c:None for c in ["Pc", "Pc_p", "Pc_np"] }

        sched_functions = sched_variant.getAllSchedulingFunctions()

        # iterate over each instruction in the BB
        for block_idx in range(0, len(block_desc.instructions)):
            block_instr = block_desc.instructions[block_idx]

            # find instruction of BB in base scheduling model and append nodes to block function
            sched_function = sched_variant.getSchedulingFunction(block_instr.name)
            self.__appendSchedulingFunction(sched_function, block_function, block_desc, block_idx, mappings)

            #op("[FINAL] Timing Variables:", { var:[ n.name if n else None for n in mappings.timingVariables[var] ] for var in mappings.timingVariables})
            #op("[FINAL] Register Mapping:", { reg: mappings.regModel[reg].name if mappings.regModel[reg] else None for reg in mappings.regModel if mappings.regModel[reg]})
            #op("[FINAL] Clobber Mapping: ", { reg: mappings.clobberModel[reg].name if mappings.clobberModel[reg] else None for reg in mappings.clobberModel if mappings.clobberModel[reg]})

        self.__resolveOutgoingEdges(block_function, mappings)

    def __appendSchedulingFunction(self, sched_function:SchedulingFunction, block_function:SchedulingFunction, block_desc:InstructionBlockDescription, block_idx:int, mappings):
        """
        """
        block_instr = block_desc.instructions[block_idx]
        if self.verbose:
            print(f"   > Appending instruction '{block_instr.name}' (id: {sched_function.identifier})...")

        root_node = sched_function.getRootNode()
        assert root_node

        visited   = []
        queue     = deque([root_node])

        while queue:
            source_node = queue.popleft()
            assert source_node not in visited
            visited.append(source_node)

            # create node
            block_node  = block_function.createNode(f"{source_node.name}_{block_idx}")
            self.__copyNode(source_node, block_node)

            # setup ingoing connections
            for in_node_i in source_node.getAllInNodes():
                dependency = self.__findNode(block_function, block_idx, in_node_i)
                dependency.connectNode(block_node)

            # resolve edges
            self.__resolveInternalEdges(source_node, block_node, block_desc, block_idx, mappings)

            # iterate over children if all dependencies have been met
            for next_node_i in source_node.getAllOutNodes():
                if all((predecessor in reversed(visited)) for predecessor in next_node_i.getAllInNodes()):
                    queue.append(next_node_i)

        # make sure all nodes are processed
        assert all([ self.__findNode(block_function, block_idx, n) for n in sched_function.getAllNodes() ])

        # setup root node respectively
        if not block_function.getRootNode():
            root_node = self.__findNode(block_function, block_idx, root_node)
            if self.verbose:
                print(f"   > Setting root node: '{root_node.name}'")
            block_function.setRootNode(root_node)

        assert not sched_function.endNode, "It is assumed, that `SchedulingFunction.endNode` is not used"

    def __resolveInternalEdges(self, source_node:Node, block_node:Node, block_desc:InstructionBlockDescription, block_idx:int, mappings):
        # in edges
        for edge in source_node.inEdges:
            if not edge.isDynamic():
                # static edge
                assert edge.timingVariable, "Expected static edges to timing variables only!"
                self.__resolveTimingVariableInEdge(block_node, edge, mappings.timingVariables)
                continue
            # dynamic edge
            assert edge.connectorModel, "Expected dynamic edges to connector models only!"
            connector_model = edge.connectorModel.name
            if connector_model in self._register_models:
                self.__resolveRegisterInEdge(block_node, edge, block_desc, block_idx, mappings, connector_model)
                continue
            if connector_model in self._branch_prediction_models:
                self.__resolveBranchPredictionInEdge(block_node, edge, block_desc, block_idx, mappings, connector_model)
                continue
            raise RuntimeError(f"Ingoing edge to '{connector_model}' is not handeld! Supported are {", ".join(self._supported_models)}")
        # out edges
        for edge in source_node.outEdges:
            if not edge.isDynamic():
                # static edge
                assert edge.timingVariable, "Expected static edges to timing variables only!"
                self.__resolveTimingVariableOutEdge(block_node, edge, block_idx, mappings.timingVariables)
                continue
            # dynamic edge
            assert edge.connectorModel, "Expected dynamic edges to connector models only!"
            connector_model = edge.connectorModel.name
            if connector_model in self._register_models:
                self.__resolveRegisterOutEdge(block_node, edge, block_desc, block_idx, mappings, connector_model)
                continue
            if connector_model in self._branch_prediction_models:
                self.__resolveBranchPredictionOutEdge(block_node, edge, block_desc, block_idx, mappings, connector_model)
                continue
            raise RuntimeError(f"Outgoing edge to '{connector_model}' is not handeld! Supported are {", ".join(self._supported_models)}")

    def __resolveOutgoingEdges(self, block_function:SchedulingFunction, mappings):
        self.__resolveOutgoingTimingVariables(block_function, mappings)
        self.__resolveOutgoingRegisters(mappings)
        self.__resolveOutgoingBranchPredictions(mappings)

    def __resolveTimingVariableInEdge(self, block_node:Node, edge:StaticEdge, mappings):
        timing_variable = edge.timingVariable.name
        history = mappings[timing_variable]
        assert edge.depth > 0, f"Expected ingoing edges to have a depth > 1 (actual depth: {in_edge.depth})!"
        assert len(history) >= edge.depth, f"Edge exceeds capacity of timing variable '{timing_variable}' (expected {len(history)} vs. depth {edge.depth})"

        last_node = history[edge.depth - 1]
        if not last_node:
            # append global input edge
            current_depth = len(history) - history.count(None)
            block_node.createStaticInEdge(timing_variable, edge.depth - current_depth)
            return
        # connect to previous node
        if self.verbose:
            print(f"   > Resolved timing variable: Node '{block_node.name}' links to '{last_node.name}' ({timing_variable}[{edge.depth}])")
        last_node.connectNode(block_node)

    def __resolveTimingVariableOutEdge(self, block_node:Node, edge:StaticEdge, block_idx:int, mappings):
        timing_variable = edge.timingVariable.name
        history = mappings[timing_variable]
        assert edge.depth == 1, f"Expected outgoing edges to have a depth == 1 (acutal depth: {out_edge.depth})!"
        # update and right-shift history
        if self.verbose:
            print(f"    > Resolved timing variable: Node '{block_node.name}' sets '{timing_variable}'")
        mappings[timing_variable] = [block_node] + history[:-1]

    def __resolveOutgoingTimingVariables(self, block_function:SchedulingFunction, mappings):
        for timing_variable in mappings.timingVariables:
            history = mappings.timingVariables[timing_variable]
            last_valid_node = None
            for idx in range(0, len(history)):
                last_node = history[idx]
                if not last_node:
                    if not last_valid_node:
                        continue
                    # create dummy node to express shift in nodes
                    dummy = block_function.createNode(f"dummy_{idx}_{timing_variable}")
                    dummy.createStaticInEdge(timing_variable, idx)
                    last_node = dummy
                else:
                    last_valid_node = last_node
                edge = last_node.createStaticOutEdge(timing_variable)
                # TODO: we need to properly support depth > 1 for outgoing edges in M2-ISA-R-Perf
                edge.depth = idx + 1

    def __resolveRegisterInEdge(self, block_node:Node, edge:StaticEdge, block_desc:InstructionBlockDescription, block_idx:int, mappings, model:str):
        instr = block_desc.instructions[block_idx]
        registers  = mappings[model]
        registerNo = instr[edge.name]
        assert registerNo is not None, f"{block_desc.name}: Instruction '{instr.name}' requires register '{edge.name}'! (undefined)"
        last_node  = registers[registerNo]
        if not last_node:
            if self.verbose:
                print(f"    > Resolved {model}: Node '{block_node.name}' uses 'r{registerNo} ({edge.name})'")
            edge_name = f"r{registerNo} ({edge.name})" if self.rename_edges else edge.name
            block_node.createDynamicInEdge(edge_name, model) # append edge
            return
        if self.verbose:
            print(f"    > Resolved {model}: Node '{block_node.name}' uses 'r{registerNo} ({edge.name})' set by '{last_node.name}'")
        last_node.connectNode(block_node)

    def __resolveRegisterOutEdge(self, block_node:Node, edge:StaticEdge, block_desc:InstructionBlockDescription, block_idx:int, mappings, model:str):
        instr = block_desc.instructions[block_idx]
        assert edge.name == self._target_register_mapping[model], f"'{edge.name}' was not recognized as a target register (e.g. Xd, Rd, ...)"
        registers  = mappings[model]
        registerNo = instr[edge.name]
        if self.verbose:
            print(f"    > Resolved {model}: Node '{block_node.name}' sets 'r{registerNo} ({edge.name})'")
        registers[registerNo]  = block_node

    def __resolveOutgoingRegisters(self, mappings):
        for model in self._register_models:
            mapping = mappings[model]
            for registerNo in mapping:
                block_node = mapping[registerNo]
                assert not (block_node and registerNo == 0), f"r0 (zero) should not be used set!"
                if not block_node:
                    continue
                target_register = self._target_register_mapping[model]
                if self.verbose:
                    print(f"    > Resolved register: Node '{block_node.name}' outputs 'r{registerNo} ({target_register})' ({model})")
                edge_name = f"r{registerNo} ({target_register})" if self.rename_edges else target_register
                block_node.createDynamicOutEdge(edge_name, model)

    def __resolveBranchPredictionInEdge(self, block_node:Node, edge:StaticEdge, block_desc:InstructionBlockDescription, block_idx:int, mappings, model:str):
        instr = block_desc.instructions[block_idx]
        pred_model = mappings[model]
        last_node  = pred_model[edge.name]
        assert edge.name == "Pc"
        if not last_node:
            if self.verbose:
                print(f"    > Resolved {model}: Node '{block_node.name}' uses '{edge.name}'")
            block_node.createDynamicInEdge(edge.name, model) # append edge
            return
        if self.verbose:
            print(f"    > Resolved {model}: Node '{block_node.name}' uses '{edge.name}' set by '{last_node.name}'")
        last_node.connectNode(block_node)

    def __resolveBranchPredictionOutEdge(self, block_node:Node, edge:StaticEdge, block_desc:InstructionBlockDescription, block_idx:int, mappings, model:str):
        instr = block_desc.instructions[block_idx]
        pred_model = mappings[model]
        assert edge.name in ["Pc_p", "Pc_np"]
        if self.verbose:
            print(f"    > Resolved {model}: Node '{block_node.name}' sets 'Pc' ({edge.name})")
        if edge.name == "Pc_np":
            # The pc_np path has no effect if branch prediction predicts correctly.
            # TODO: Can we model more dynamic branch prediction?
            if model != "noBranchPredModel":
                return
            #def twos_comp(val, bits):
            #    """compute the 2's complement of int value val"""
            #    if (val & (1 << (bits - 1))) != 0: # if sign bit is set e.g., 8bit: 128-255
            #        val = val - (1 << bits)        # compute negative value
            #    return val                         # return positive value as is

            #imm  = instr["imm"]
            #assert imm is not None, f"branch instruction has no target (imm value is empty)! {instr}"
            #comp = twos_comp(int(imm), 13)
            #new_node = block_node.parentSchedulingFunction.createNode(f"{model}_{block_idx}")
            #block_node.connectNode(new_node)
            #block_node = new_node
        # pc_p and pc_np become the new pc inputs
        pred_model["Pc"]      = block_node
        pred_model[edge.name] = block_node

    def __resolveOutgoingBranchPredictions(self, mappings):
        for model in self._branch_prediction_models:
            mapping = mappings[model]
            for connector in mapping:
                # pc path is input only
                if connector == "Pc":
                    continue
                block_node = mapping[connector]
                if not block_node:
                    continue
                if self.verbose:
                    print(f"    > Resolved {model}: Node '{block_node.name}' outputs '{connector}'")
                block_node.createDynamicOutEdge(connector, model)

    def __findElementByName(self, elements, name, error_str = ""):
        element = list(filter(lambda e: e.name == name, elements))
        assert len(element) == 1, error_str
        return element[0]

    def __findNode(self, block_function:SchedulingFunction, block_idx:int, source_node:Node) -> Node :
        return self.__findElementByName(block_function.nodes, f"{source_node.name}_{block_idx}")

    def __copyNode(self, source_node:Node, block_node:Node):
        # apply delay
        block_node.delay = source_node.delay
        # link resource model
        if source_node.resourceModel:
            block_node.resourceModel = block_node.parentVariant.getResourceModel(source_node.resourceModel.name)
