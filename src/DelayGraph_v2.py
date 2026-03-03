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
from typing import List, Dict
from collections import deque

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, Edge

from src.Common import Profile, PrintDisabled
from src.InstructionBlockDescription import InstructionBlockDescription
from src.MaxPlusAlgebra import DelayVariable, MaxTerm, MaxFunction, MaxFunctionList

class DelayGraphModel_v2:

    def __init__(self):
        self.variants: Dict[str, 'DelayGraphVariant'] = {}

class DelayGraphVariant_v2:

    def __init__(self):
        self.scheduling_functions: Dict[str, 'DelayGraph'] = {}

class DelayGraph_v2:

    def __init__(self, code_block:InstructionBlockDescription):
        self.code_block = code_block
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

    def set_node(self, node:str, functions:List['MaxTerm']):
        for function in functions:
            assert all(v.name in self._variable_mapping for v in function.iter_all_vars()), \
                f"Function contains unregistered variable names!"
            self.__verify(node, function, check_name=False)
        #print("SETTING NODE", node, "->", functions)
        self._nodes[node] = functions

    def get_node(self, node:str) -> List['MaxTerm']:
        return self._nodes[node]

    def outputs(self) -> List[str]:
        return self._outputs.keys()

    def set_output(self, variable_name:str, functions:List['MaxTerm'], full_name:str = None) -> None:
        if full_name is not None:
            self.__register_variable(full_name, variable_name)
        for function in functions:
            self.__verify(variable_name, function)
        #print("SETTING OUT", variable_name, "->", functions)
        self._outputs[variable_name] = functions

    def get_output(self, node:str) -> List['MaxTerm']:
        return self._outputs[node]

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
        assert not any(v.delay < 0 for v in function.iter_all_vars()), f"Term of '{variable_name}' contains negative cofactors!"

class DelayGraphTransformer_v2:
    """Delay Graph V2"""

    def __init__(self, verbose=True):
        # whether to unroll all delay functions
        self.verbose  = verbose

    def transform(self, block_model:SchedulingModel, block_descriptions:List[InstructionBlockDescription]) -> 'DelayGraphModel':
        """
        Transforms a (block) scheduling model into a delay graph.
        For each scheduling function a dict of its outputs and the respective delay functions (max term) is returned.
        Setting `unroll_delays` to `True` will yield a delay graph with a depth of one, i.e. no max terms are shared.
        """
        print()
        print("-- TRANSFORM: DELAY_GRAPH_MODEL_V2 --")

        model = DelayGraphModel_v2()
        # iterate over each variant
        for block_variant in block_model.getAllVariants():
            print(f" > Generating delay graph for '{block_variant.name}'")
            model.variants[block_variant.name] = self.__generateDelayGraphForEachFunction(block_variant, block_descriptions)
        return model

    def __generateDelayGraphForEachFunction(self, block_variant:Variant, block_descriptions:List[InstructionBlockDescription]) -> 'DelayGraphVariant':
        block_functions = block_variant.getAllSchedulingFunctions()
        variant = DelayGraphVariant_v2()
        idx = 0
        for block_function in block_functions:
            print(f"  > Generating delay graph for '{block_function.name}'")
            with Profile(f"  > took"):
                variant.scheduling_functions[block_function.name] = self.__generateDelayGraphForFunction(block_variant, block_function, block_descriptions[idx])
            idx += 1
        return variant

    def __generateDelayGraphForFunction(self, block_variant:Variant, block_function:SchedulingFunction, block_description:InstructionBlockDescription):
        graph = DelayGraph_v2(code_block=block_description)

        # find all root nodes
        queue = deque(n for n in block_function.getAllNodes() if len(n.getAllInNodes()) == 0)
        while queue:
            node = queue.popleft()
            assert node.name not in graph.nodes()

            # create max term, discarding redundant variables
            functions = self.__get_inputs(node, graph)
            functions.sort()

            # store function of current node
            graph.set_node(node.name, functions)
            if self.verbose:
                self.print_function(node.name, functions, indent=3)

            # set outputs if any
            self.__set_output(node, functions, graph)

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

    def __get_inputs(self, node:Node, graph:'DelayGraph') -> List['MaxFunction']:
        """
        Accumulates all input variables for the given node.
        Returns a non-simplified term.
        """
        functions = MaxFunctionList()

        for in_node in node.getAllInNodes():
            other_functions = graph.get_node(in_node.name)
            for other_function in other_functions:
                functions.merge(other_function)

        for in_edge in node.getAllInEdges():
            edge_name = self.__variable_name(in_edge)
            variable  = self.__simplify_variable_name(edge_name)
            if variable == 'r0':
                continue
            graph.register_input(edge_name, variable)
            functions.append_static_var(DelayVariable(variable))

        functions.plus(node.delay)

        if node.resourceModel or "MUL_" in node.name:
            variable = self.__simplify_variable_name(node.name)
            graph.register_dynamic_variable(node.name, variable)
            functions.append_coefficient(DelayVariable(variable))

        return functions

    def __set_output(self, node:Node, functions:List['MaxTerm'], graph:'DelayGraph') -> str:
        """
        Sets the node's function to all outputs of this node.
        Yields the name of the last output that was set (if any)
        """
        output_name = None
        for edge in node.getAllOutEdges():
            edge_name = self.__variable_name(edge, prefix="o_")
            variable  = self.__simplify_variable_name(edge_name)
            graph.set_output(variable, functions, full_name=edge_name)
            output_name = variable
            if self.verbose:
                print(" " * 23 + f"- sets '{output_name}'")
        return output_name

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
    def print_function(name:str, functions:List['MaxTerm'], indent=0):
        """
        Prints the node and its function in a standardized manner. Used for stdout
        """
        function_strs = tuple(DelayGraphTransformer_v2.function_to_str(function, indent=20 + 9 + 4) for function in functions)
        print(f"{" " * indent}> {name.ljust(20 - indent)} = max({function_strs[0] if len(function_strs) > 0 else '/'}{',' if len(function_strs) > 1 else ')'}")
        if len(function_strs) > 1:
            for function in function_strs[1:-1]:
                print(f"{" " * 29}{function},")
            print(f"{" " * 29}{function_strs[-1]})")