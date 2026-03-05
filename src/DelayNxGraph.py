import networkx as nx

from typing import List, Dict, Optional, TypeAlias
from collections import deque

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, Edge

from src.Common import Profile
from src.InstructionBlockDescription import InstructionBlockDescription

class NxVariable:

    def __init__(self, name:str, delay:int=0):
        self.name  = name
        self.delay = delay

    def __str__(self):
        return f"{self.delay} + {self.name}"

    def __repr__(self):
        return self.__str__()

    def __add__(self, other):
        if isinstance(other, int):
            return NxVariable(self.name, self.delay + other)
        if self.name == other.name:
            return NxVariable(self.name, self.delay + other.delay)
        raise RuntimeError(f"UNHANDELED_ADD ({self} vs {other})")

    def __radd__(self, other):
        return self.__add__(other)

    def __lt__(self, other):
        if isinstance(other, int):
            if other <= 0 or self.delay > other:
                return False
            raise RuntimeError(f"UNSURE_LT ({self} vs {other})")
        if self.name == other.name:
            return self.delay < other.delay
        raise RuntimeError(f"UNHANDELED_LT ({self} vs {other})")

    def __gt__(self, other):
        if isinstance(other, int):
            if other <= 0 or self.delay > other:
                return True
            raise RuntimeError(f"UNSURE_GT ({self} vs {other})")
        if self.name == other.name:
            return self.delay > other.delay
        raise RuntimeError(f"UNHANDELED_GT ({self} vs {other})")

    def __eq__(self, other):
        if isinstance(other, int):
            raise False
        if self.name == other.name:
            return self.delay == other.delay
        raise RuntimeError(f"UNHANDELED_EQ ({self} vs {other})")

    def __ge__(self, other):
        if isinstance(other, int):
            if other <= 0 or self.delay > other:
                return True
            raise RuntimeError(f"UNSURE_GE ({self} vs {other})")
        if self.name >= other.name:
            return self.delay >= other.delay
        raise RuntimeError(f"UNHANDELED_GE ({self} vs {other})")

class DelayNxGraphModel:

    def __init__(self):
        self.variants: Dict[str, 'DelayNxGraphVariant'] = {}

class DelayNxGraphVariant:

    def __init__(self):
        self.scheduling_functions: Dict[str, 'DelayNxGraph'] = {}

class DelayNxGraph:

    def __init__(self, code_block:InstructionBlockDescription):
        self.code_block = code_block
        self.G = nx.DiGraph()
        # outputs of the scheduling function (timing variables and connector models)
        self.outputs:List[str] = []
        # inputs of the scheduling function (initial timing variables and connector models)
        self.inputs:List[str]  = []

class DelayNxGraphTransformer:
    """Delay Graph"""

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
        print("-- TRANSFORM: DELAY_NX_GRAPH_MODEL --")

        model = DelayNxGraphModel()
        # iterate over each variant
        for block_variant in block_model.getAllVariants():
            print(f" > Generating delay graph for '{block_variant.name}'")
            model.variants[block_variant.name] = self.__generateDelayGraphForEachFunction(block_variant, block_descriptions)
        return model

    def __generateDelayGraphForEachFunction(self, block_variant:Variant, block_descriptions:List[InstructionBlockDescription]) -> 'DelayGraphVariant':
        block_functions = block_variant.getAllSchedulingFunctions()
        variant = DelayNxGraphVariant()
        idx = 0
        for block_function in block_functions:
            print(f"  > Generating delay graph for '{block_function.name}'")
            with Profile(f"   >"):
                variant.scheduling_functions[block_function.name] = self.__generateDelayGraphForFunction(block_variant, block_function, block_descriptions[idx])
            idx += 1
        return variant

    def __generateDelayGraphForFunction(self, block_variant:Variant, block_function:SchedulingFunction, block_description:InstructionBlockDescription):
        graph = DelayNxGraph(code_block=block_description)

        # find all root nodes
        queue = deque(n for n in block_function.getAllNodes() if len(n.getAllInNodes()) == 0)
        while queue:
            node = queue.popleft()
            #assert node.name not in graph.nodes()

            graph.G.add_node(node)

            # create max term, discarding redundant variables
            self.__get_inputs(node, graph)

            # iterate over children if all dependencies have been met
            next_nodes = node.getAllOutNodes()
            if not next_nodes:
                graph.outputs.append(node.name)
            for next_node_i in node.getAllOutNodes():
                if all((predecessor.name in graph.G.nodes()) for predecessor in next_node_i.getAllInNodes()):
                    queue.append(next_node_i)

        # make sure all nodes have been processed
        assert all((n.name in graph.G.nodes()) for n in block_function.getAllNodes())

        return graph

    def __get_inputs(self, node:Node, graph:'DelayNxGraph'):
        """
        Accumulates all input variables for the given node.
        Returns a non-simplified term.
        """
        # append in edges to function
        for in_edge in node.getAllInEdges():
            edge_name = self.__variable_name(in_edge)
            variable  = self.__simplify_variable_name(edge_name)
            if variable == 'r0':
                continue
            graph.G.add_edge(edge_name, node.name, weight=0)
            graph.inputs.append(edge_name)
        # append in node to function
        for in_node in node.getAllInNodes():
            if "MUL_" in in_node.name:
                var_name = self.__simplify_variable_name(in_node.name)
                print("CREATING VARIABLE", var_name, "INTO NODE", in_node.name)
                graph.G.add_edge(in_node.name, node.name, weight=3) #NxVariable(var_name, in_node.delay))
            else: 
                graph.G.add_edge(in_node.name, node.name, weight=in_node.delay)
        # append variable delay of resource model
        if node.resourceModel:
            # TODO: properly integrate dynamic delays (cannot be treated as input variables)
            # use name of node as unique resource delay
            pass

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
