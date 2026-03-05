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

from typing import List, Dict
from collections import deque

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, Edge

from src.Common import Profile
from src.InstructionBlockDescription import InstructionBlockDescription
from src.MaxPlusAlgebra import DelayVariable, MaxTerm

class DelayGraphModel:

    def __init__(self):
        self.variants: Dict[str, 'DelayGraphVariant'] = {}

class DelayGraphVariant:

    def __init__(self):
        self.scheduling_functions: Dict[str, 'DelayGraph'] = {}

class DelayGraph:

    def __init__(self, code_block:InstructionBlockDescription):
        self.code_block = code_block
        # intermediate results, that can be reused by other nodes
        self._intermediates:Dict[str, 'MaxTerm'] = {}
        # outputs of the scheduling function (timing variables and connector models)
        self._outputs:Dict[str, 'MaxTerm']       = {}
        # intermediate nodes (all nodes that are present in a scheduling function)
        self._nodes:Dict[str, 'MaxTerm']         = {}
        # inputs of the scheduling function (initial timing variables and connector models)
        self._inputs:List[str] = []
        # inputs that have not a fixed but a dynamic delay (i.e. resource models)
        self._dynamic_variables:List[str] = []
        # maps full node name to a simplified variable name
        self._variable_mapping:Dict[str, str] = {}

    def nodes(self) -> List[str]:
        return self._nodes.keys()

    def input_to_variable_name(self, input_name:str) -> str:
        try:
            index = tuple(self._variable_mapping.values()).index(input_name)
            return  tuple(self._variable_mapping.keys())[index]
        except ValueError:
            return None

    def variable_name_to_input(self, variable_name:str) -> str:
        try:
            return self._variable_mapping[variable_name]
        except KeyError:
            return None

    def set_node(self, node:str, function:'MaxTerm'):
        assert all(v.name in self._variable_mapping for v in function), \
               f"Function contains unregistered variable names!"
        self.__verify(node, function, check_name=False)
        self._nodes[node] = function

    def get_node(self, node:str) -> 'MaxTerm':
        return self._nodes[node]

    def outputs(self) -> List[str]:
        return self._outputs.keys()

    def set_output(self, variable_name:str, function:'MaxTerm', full_name:str = None) -> None:
        if full_name is not None:
            self.__register_variable(full_name, variable_name)
        self.__verify(variable_name, function)
        self._outputs[variable_name] = function

    def get_output(self, node:str) -> 'MaxTerm':
        return self._outputs[node]

    def intermediates(self) -> List[str]:
        return self._intermediates

    def get_intermediate(self, variable_name:str) -> 'MaxTerm':
        return self._intermediates[variable_name]

    def register_intermediate(self, variable_name:str, function:'MaxTerm') -> None:
        self.__verify(variable_name, function)
        self._intermediates[variable_name] = function

    def replace_intermediate(self, variable_name:str, replacement:str, delay:int=None) -> None:
        assert replacement in self._intermediates, f"Unknown intermediate '{replacement}'!"
        del self._intermediates[variable_name]
        for name in self.nodes():
            for var in self.get_node(name):
                if var.name == variable_name:
                    var.name = replacement
                    if delay is not None:
                        var.delay += delay

    def inputs(self) -> List[str]:
        return self._inputs

    def register_input(self, full_name:str, variable_name:str) -> None:
        self.__register_variable(full_name, variable_name)
        if variable_name not in self._inputs:
            self._inputs.append(variable_name)

    def dynamic_variables(self) -> List[str]:
        return self._dynamic_variables

    def get_dynamic_variable(self, variable_name:str) -> 'MaxTerm':
        return self._dynamic_variables[variable_name]

    def register_dynamic_variable(self, full_name:str, variable_name:str) -> None:
        self.register_input(full_name, variable_name)
        if variable_name not in self._dynamic_variables:
            self._dynamic_variables.append(variable_name)

    def __register_variable(self, full_name:str, variable_name:str) -> None:
        if "Xa" not in full_name and "Xb" not in full_name:
            assert variable_name not in self._variable_mapping or self._variable_mapping[variable_name] == full_name, \
                f"Generated duplicate variable name! ('{variable_name}' from '{full_name}' clashes with '{self._variable_mapping[variable_name]}')"
        self._variable_mapping[variable_name] = full_name

    def __verify(self, variable_name:str, function:'MaxTerm', check_name=True) -> None:
        if check_name:
            assert variable_name in self._variable_mapping, f"Unkown variable name '{variable_name}'!"
        assert not any(v.delay < 0 for v in function), f"Term of '{variable_name}' contains negative cofactors!"

class DelayGraphTransformer:
    """Delay Graph"""

    def __init__(self, verbose=True):
        # whether to unroll all delay functions
        self.simplify = True
        self.verbose  = verbose

    def transform(self, block_model:SchedulingModel, block_descriptions:List[InstructionBlockDescription], simplify=True) -> 'DelayGraphModel':
        """
        Transforms a (block) scheduling model into a delay graph.
        For each scheduling function a dict of its outputs and the respective delay functions (max term) is returned.
        Setting `unroll_delays` to `True` will yield a delay graph with a depth of one, i.e. no max terms are shared.
        """
        print()
        print("-- TRANSFORM: DELAY_GRAPH_MODEL --")

        self.simplify = simplify
        model = DelayGraphModel()
        with Profile(f"  >"):
            # iterate over each variant
            for block_variant in block_model.getAllVariants():
                print(f" > Generating delay graph for '{block_variant.name}'")
                model.variants[block_variant.name] = self.__generateDelayGraphForEachFunction(block_variant, block_descriptions)
        return model

    def __generateDelayGraphForEachFunction(self, block_variant:Variant, block_descriptions:List[InstructionBlockDescription]) -> 'DelayGraphVariant':
        block_functions = block_variant.getAllSchedulingFunctions()
        variant = DelayGraphVariant()
        idx = 0
        for block_function in block_functions:
            print(f"  > Generating delay graph for '{block_function.name}'")
            with Profile(f"   >"):
                variant.scheduling_functions[block_function.name] = self.__generateDelayGraphForFunction(block_variant, block_function, block_descriptions[idx])
            idx += 1
        return variant

    def __generateDelayGraphForFunction(self, block_variant:Variant, block_function:SchedulingFunction, block_description:InstructionBlockDescription):
        graph = DelayGraph(code_block=block_description)

        # find all root nodes
        queue = deque(n for n in block_function.getAllNodes() if len(n.getAllInNodes()) == 0)
        while queue:
            node = queue.popleft()
            assert node.name not in graph.nodes()

            # create max term, discarding redundant variables
            function = self.__get_inputs(node, graph)
            function = function.repacked(graph.intermediates()).sort()

            # store function of current node
            graph.set_node(node.name, function)
            if self.verbose:
                self.print_function(node.name, function, indent=3)

            # set outputs if any
            intermediate = self.__set_output(node, function, graph)

            # create intermediate output if function is a max node (multiple input edges)
            if self.simplify:
                if intermediate is not None and len(function) > 1:
                    self.__update_intermediates(node.name, intermediate, graph)

            # iterate over children if all dependencies have been met
            for next_node_i in node.getAllOutNodes():
                if all((predecessor.name in graph.nodes()) for predecessor in next_node_i.getAllInNodes()):
                    queue.append(next_node_i)

        # make sure all nodes have been processed
        assert all((n.name in graph.nodes()) for n in block_function.getAllNodes())

        if self.verbose:
            print(f"   > outputs:")
            for output in graph.outputs():
                self.print_function(output, graph.get_output(output), indent=4)

        return graph

    def __get_inputs(self, node:Node, graph:'DelayGraph') -> 'MaxTerm':
        """
        Accumulates all input variables for the given node.
        Returns a non-simplified term.
        """
        term = MaxTerm()
        # append in edges to function
        for in_edge in node.getAllInEdges():
            edge_name = self.__variable_name(in_edge)
            variable  = self.__simplify_variable_name(edge_name)
            if variable == 'r0':
                continue
            graph.register_input(edge_name, variable)
            term.append(DelayVariable(variable, node.delay))
        # append in node to function
        for in_node in node.getAllInNodes():
            for variable in graph.get_node(in_node.name):
                term.append(variable.added(node.delay))
        # TODO: properly integrate dynamic delays (cannot be treated as input variables)
        # use name of node as unique resource delay
        if node.resourceModel:
            raise RuntimeError("Dynamic delays are currently not supported")
        return term

    def __set_output(self, node:Node, function:'MaxTerm', graph:'DelayGraph') -> str:
        """
        Sets the node's function to all outputs of this node.
        Yields the name of the last output that was set (if any)
        """
        intermediate = None
        for edge in node.getAllOutEdges():
            edge_name = self.__variable_name(edge, prefix="o_")
            variable = self.__simplify_variable_name(edge_name)
            graph.set_output(variable, function, full_name=edge_name)
            intermediate = variable
            if self.verbose:
                print(" " * 23 + f"- sets '{intermediate}'")
        return intermediate

    def __update_intermediates(self, node_name:str, intermediate:str, graph:'DelayGraph') -> None:
        """
        Creates an intermediate output for the function of the current node, if no other intermediate covers this node.
        Otherwise, all references are updated.
        """
        current_term = graph.get_node(node_name)
        expanded = current_term.expanded(graph.intermediates())
        new_term = MaxTerm(DelayVariable(intermediate))

        # check if term is covered by other intermediate
        best_match = expanded.find_best_intermediate(intermediates=graph.intermediates(), expand=False, allow_negative_distance=True)
        if best_match is not None and best_match.name not in current_term:
            other_term = graph.get_intermediate(best_match.name)
            if best_match.delay >= 0:
                if self.verbose:
                    print(f"INFO: intermediate '{intermediate}' is a multiple of '{best_match.name}'! (distance: {best_match.delay})")
                # link to other intermediate
                new_term = MaxTerm(best_match)
                assert len(other_term) == len(expanded), "Necessary to extend term by missing variables?"
                expanded = new_term
            else:
                # other intermediate is a negative multiple of this term
                if self.verbose:
                    print(f"INFO: intermediate '{best_match.name}' is a negative multiple of '{intermediate}'! (distance: {best_match.delay})")
                assert len(other_term) == len(expanded)
                best_match.delay *= -1
                new_term = MaxTerm(DelayVariable(intermediate, 0))
                out_term = MaxTerm(DelayVariable(intermediate, best_match.delay))
                # update old output
                graph.set_output(best_match.name, out_term)
                graph.register_intermediate(intermediate, expanded)
                graph.replace_intermediate(best_match.name, intermediate, delay=best_match.delay)
                graph.set_node(node_name, new_term)
                return
        # save new intermediate and update output of this node
        graph.register_intermediate(intermediate, expanded)
        graph.set_node(node_name, new_term)

    def __variable_name(self, edge:Edge, prefix:str=""):
        """
        Generates a unique but simplified variable for the given edge.
        """
        var_name = prefix
        if edge.isDynamic():
            var_name += edge.name
        elif edge.timingVariable.getNumElements() == 1:
            var_name += edge.timingVariable.name
        else:
            var_name += f"{edge.timingVariable.name}[{edge.depth}]"
        return var_name

    def __simplify_variable_name(self, var_name:str):
        """
        Simplifies the variable name but gurantees that the variable is unique.
        """
        new_name =  var_name.lower() \
            .replace(" (xa)", "") \
            .replace(" (xb)", "") \
            .replace(" (xd)", "") \
            .replace(" (cb_out)", "_cb_out") \
            .replace(" (cb_in)", "_cb_in") \
            .replace("_stage", "") \
            .replace("_substage", "_sub") \
            .replace("model", "")
        return new_name

    @staticmethod
    def function_to_str(function:'MaxTerm', indent=0, word_wrap_at=150):
        """
        Generates a nicely readable function.
        """
        text  = str(function)
        lines = []
        while len(text) > word_wrap_at:
            try:
                idx  = text.index(", ", word_wrap_at)
                idx += 2
            except ValueError:
                break
            lines += [text[:idx]]
            text   = text[idx:]
        lines += [text]
        return f"\n{" " * (indent)}".join(lines)

    @staticmethod
    def print_function(name:str, function:'MaxTerm', indent=0):
        """
        Prints the node and its function in a standardized manner. Used for stdout
        """
        function_str = DelayGraphTransformer.function_to_str(function, indent=20 + 9)
        print(f"{" " * indent}> {name.ljust(20 - indent)} = max{function_str}")