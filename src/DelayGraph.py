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

from itertools import chain
from typing import List, Dict, Optional, Self
from collections import deque

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, Edge

from src.Common import Profile
from src.InstructionBlockDescription import InstructionBlockDescription

class DelayVariable:
    """Represents a variable in a max term, associated with an added delay."""

    def __init__(self, name:str, delay:int=0):
        self.name  = name
        self.delay = delay

    def __str__(self):
        return f"{self.delay} + {self.name}"

    def __repr__(self):
        return self.__str__()

    def merged(self, delay:int) -> 'DelayVariable':
        return DelayVariable(self.name, self.delay + delay)

class MaxTerm(list):
    """Represents a max term, made out of a list of variables."""

    def __init__(self, iterable=None):
        super().__init__(iterable if iterable is not None else [])

    def __str__(self) -> str:
        return f"({", ".join(str(v) for v in self)})"

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other) -> bool:
        return len(self) == len(other) and all((v.name in other and other.max_value(v.name) == v.delay) for v in self)

    def __contains__(self, value) -> bool:
        if isinstance(value, str):
            assert self.count(v.name == value for v in self) <= 1, f"Duplicate variable '{value}'!"
            return any(v.name == value for v in self)
        assert isinstance(value, DelayVariable), f"Incompatible type '{type(value)}'!"
        return value.name in self

    def max_value(self, name:str) -> Optional[int]:
        """
        Returns the maximum added delay of the variable `name`.
        """
        tmp = (v.delay for v in self if v.name == name)
        try:
            return max(tmp)
        except ValueError:
            return None

    def names(self) -> List[str]:
        """
        Returns a list of all variable names as they appear in order.
        """
        return list(dict.fromkeys(v.name for v in self)) # keeps order but removes duplicates

    def plus(self, value:int) -> Self:
        if value < 0:
            raise ValueError("Only positive values are allowed")
        for v in self:
            v.delay += value
        return self

    def resolved(self, variable_name:str) -> 'MaxTerm':
        """
        Returns a new term in which the variable's delay is merged with all other variables by evaluating the max delay.
        """
        value = self.max_value(variable_name)
        if value is None:
            value = 0
        new_term = MaxTerm(DelayVariable(v.name, max(v.delay, value)) for v in self if v.name != variable_name)
        return new_term

    def remove(self, variable_name:str) -> 'MaxTerm':
        filtered = list(filter(lambda v: v.name == variable_name, self))
        if len(filtered) > 0:
            assert len(filtered) == 1
            super().remove(filtered[0])

    def replaced(self, variable_name:str, new_variable:'DelayVariable') -> 'MaxTerm':
        """
        Replaces all instances of `variable_name` with `new_variable.name` and merges the delays.
        Returns a new, simplified term.
        """
        new_term = MaxTerm([v if v.name != variable_name else new_variable.merged(v.delay) for v in self])
        return new_term.simplified()

    def expanded(self, intermediates:Dict[str, 'MaxTerm']) -> 'MaxTerm':
        """
        Expands (unrolls) all intermediate variables by their corresponding variables.
        Returns a new, simplified term.
        """
        expanded = MaxTerm(chain((i.merged(v.delay) for v in self if v.name in intermediates for i in intermediates[v.name]), \
                                 (v                 for v in self if v.name not in intermediates)))
        assert all([i.name not in intermediates for i in expanded])
        return expanded.simplified()

    def difference(self, other:'MaxTerm') -> 'MaxTerm':
        """
        Returns a new term with only the variables that `other` contains but this term does not.
        Keeps order of names.
        """
        return MaxTerm(filter(lambda v: v.name not in other.names(), self)).simplified()

    def simplified(self) -> 'MaxTerm':
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Keeps order of names. Returns a new term.
        """
        return MaxTerm(DelayVariable(name, self.max_value(name)) for name in self.names())

    def repacked(self, intermediates:Dict[str, 'MaxTerm']) -> 'MaxTerm':
        """
        Attempts to find a new term, that reuses an intermediate variable to simplify the term.
        Returns a new, simplified, and sorted term.
        """
        expanded   = self.expanded(intermediates)
        best_match = expanded.find_best_intermediate(intermediates, expand=False)
        if best_match is None:
            return expanded # no need to simplify
        repacked = expanded.difference(intermediates[best_match.name])
        repacked.append(best_match)
        return repacked.sorted()

    def sorted(self) -> 'MaxTerm':
        """
        Returns a new term sorted by its delay (descending).
        For variables with same delay, alphabetical order is used.
        """
        return MaxTerm(sorted(self, key=lambda v: (-v.delay, v.name)))

    def distance(self, other:'MaxTerm') -> Optional[int]:
        """
        Attempts to find a linear dependency between `self` and `other`.
        For a linear dependency, all variables in `self` must be present in `other` with a consistent offset in their cofactors.
        This offset is called the distance. May return a negative distance, if `self` can be expressed by `other`.
        """
        # self cannot cover other if it has more variables
        if len(self) > len(other):
            return None
        distance = None
        for var in self:
            other_delay = other.max_value(var.name)
            if other_delay is None:
                return None
            # calculate difference
            current = other_delay - var.delay
            # difference in delay is not linear
            if distance is not None and distance != current:
                return None
            distance = current
        return distance

    def find_best_intermediate(self, intermediates:Dict[str, 'MaxTerm'], expand=True, allow_negative_distance=False) -> Optional['DelayVariable']:
        """
        Attempts to find an intermediate variable that best covers `self` such that it yields the smallest term.
        `self` must be unrolled to find an intermediate.
        """
        this = self
        if expand: this = self.expanded(intermediates)

        last_name   = None
        last_factor = None
        last_len    = None
        for name in intermediates:
            term   = intermediates[name]
            factor = term.distance(this)
            if factor is None:
                continue
            curr_len = len(term)
            if factor < 0:
                # len must match if distance is negative
                if not allow_negative_distance or curr_len != len(this):
                    continue
            if last_name is not None:
                # prefer if variable covers more variables
                if curr_len < last_len:
                    continue
                # keep last variable if its scores a lower
                if curr_len == last_len and factor > last_factor:
                    continue
            last_name   = name
            last_factor = factor
            last_len    = curr_len
        if last_name is None:
            return None
        return DelayVariable(last_name, last_factor)

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
            index = list(self._variable_mapping.values()).index(input_name)
            return  list(self._variable_mapping.keys())[index]
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

    def set_output(self, variable_name:str, function:'MaxTerm', full_name:Optional[str] = None) -> None:
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

    def replace_intermediate(self, variable_name:str, replacement:str, delay=None) -> None:
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
            with Profile(f"  > took"):
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
            function = function.repacked(graph.intermediates()).sorted()

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
        term = MaxTerm([])
        # append in edges to function
        for in_edge in node.getAllInEdges():
            edge_name = self.__variable_name(in_edge)
            variable  = self.__simplify_variable_name(edge_name)
            if variable == 'r0':
                continue
            graph.register_input(edge_name, variable)
            term.append(DelayVariable(variable, node.delay))
            #function.static_term.append(DelayVariable(variable, node.delay))
        # append in node to function
        for in_node in node.getAllInNodes():
            for variable in graph.get_node(in_node.name):
                term.append(variable.merged(node.delay))
            #in_function = graph.get_node(in_node.name)
            #for variable in in_function.static_term:
            #    function.static_term.append(variable.merged(node.delay))
        #if "MUL" in node.name:
        #    return function
            # TODO: properly integrate dynamic delays (cannot be treated as input variables)
            # use name of node as unique resource delay
            #variable = self.__simplify_variable_name(node.name)
            #graph.register_dynamic_variable(node.name, variable)
            #variable = DelayVariable(variable, node.delay)
            #function.append(variable)
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
        new_term = [DelayVariable(intermediate)]

        # check if term is covered by other intermediate
        best_match = expanded.find_best_intermediate(intermediates=graph.intermediates(), expand=False, allow_negative_distance=True)
        if best_match is not None and best_match.name not in current_term:
            other_term = graph.get_intermediate(best_match.name)
            if best_match.delay >= 0:
                if self.verbose:
                    print(f"INFO: intermediate '{intermediate}' is a multiple of '{best_match.name}'! (distance: {best_match.delay})")
                # link to other intermediate
                new_term = MaxTerm([best_match])
                assert len(other_term) == len(expanded), "Necessary to extend term by missing variables?"
                expanded = new_term
            else:
                # other intermediate is a negative multiple of this term
                if self.verbose:
                    print(f"INFO: intermediate '{best_match.name}' is a negative multiple of '{intermediate}'! (distance: {best_match.delay})")
                assert len(other_term) == len(expanded)
                best_match.delay *= -1
                new_term = MaxTerm((DelayVariable(intermediate, 0),))
                out_term = new_term.simplified().plus(best_match.delay)
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