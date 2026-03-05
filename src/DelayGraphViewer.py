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

import graphviz
import pathlib
import os

from backends.common import dirUtils as dir_utils

from src.DelayGraph import DelayGraphModel

class DelayGraphViewer:

    def __init__(self):
        # whether to attempt to keep the order for the nodes (here alphabetical)
        self.prefer_input_order  = False
        self.prefer_output_order = False
        # whether to enforce the same y-pos for the nodes
        self.enforce_inputs_on_same_level  = False
        self.enforce_outputs_on_same_level = False
        # whether to generate a single input node for each input
        # -> setting this to `False` can improve readability of edges for complex graphs but may introduce many more nodes
        self.generate_unique_input_nodes   = True
        # merges the input node with its delay, reducing overall number nodes
        # -> can only be used if `generate_unique_input_nodes` is disabled
        self.merge_input_and_plus_nodes    = False

        # sytling
        self._direction          = "TB" # TB, LR
        self._edge_style         = "polyline" # spline, ortho, line polyline, curved
        self._vertical_spacing   = 1.0
        self._horizontal_spacing = 0.1

        self._input_node_style  = {"style":'filled', "fillcolor":'lightyellow'}
        self._output_node_style = {"style":'filled', "fillcolor":'lightblue'}
        self._alias_node_style  = {"style":'filled', "fillcolor":'lightgray'}
        # helper varriables
        self._temp_dir = pathlib.Path(__file__).parent / "temp"

        # override settings
        if self.generate_unique_input_nodes:
            self.merge_input_and_plus_nodes = False

    def execute(self, delay_graph_model:DelayGraphModel, out_dir:str):

        print()
        print("-- BACKEND: DELAY_GRAPH_VIEWER --")

        for variant in delay_graph_model.variants:

            # Make sure output directories and temp directory exist
            print(f" > Creating output directories for '{variant.name}'")
            temp_dir = self._temp_dir / variant.name
            dir_utils.createOrReplaceDir(temp_dir, suppress_warning=True)
            variant_dir = out_dir / variant.name / "doc_delay"

            # Generate sub-dirs for each basic block function
            for delay_graph in variant.scheduling_functions:
                assert delay_graph.name
                (variant_dir / delay_graph.name).mkdir(parents=True, exist_ok=True)

                dot_graph = graphviz.Digraph(comment=delay_graph.name)
                dot_graph.attr(rankdir=self._direction)
                dot_graph.attr(splines=self._edge_style, nodesep=str(self._horizontal_spacing), ranksep=str(self._vertical_spacing))

                output_names = delay_graph.outputs()
                alias_names  = delay_graph.intermediates()
                input_names  = delay_graph.inputs()

                # create input nodes
                with dot_graph.subgraph() as subgraph:
                    # helper function
                    def generate_input_node(input_var, delay, prev_node):
                        node_name = self.__input(input_var, delay)
                        label = input_var
                        if self.merge_input_and_plus_nodes and delay != 0:
                            label += f"\n+{delay}"
                        node  = subgraph.node(node_name, label=label, shape='box', **self._input_node_style)
                        if self.prefer_input_order and prev_node is not None:
                            subgraph.edge(prev_node, node_name, style='invis')
                        prev_node = node_name

                    if self.enforce_inputs_on_same_level:
                        subgraph.attr(rank='min')

                    prev_node = None
                    if not self.generate_unique_input_nodes:
                        for input_var in input_names:
                            for output in output_names:
                                for var in delay_graph.output(output):
                                    if var.name == input_var:
                                        generate_input_node(input_var, var.delay, prev_node)
                    else:
                        for input_var in input_names:
                            generate_input_node(input_var, 0, prev_node)

                # create output nodes
                with dot_graph.subgraph() as subgraph:
                    if self.enforce_outputs_on_same_level:
                        subgraph.attr(rank='max')
                    prev_node = None
                    for output_var in output_names:
                        node_name = self.__output(output_var)
                        node = subgraph.node(node_name, label=output_var.replace("o_", ""), shape='box', **self._output_node_style)
                        if self.prefer_output_order and prev_node is not None:
                            subgraph.edge(prev_node, node_name, style='invis')
                        prev_node = node_name

                subgraph = dot_graph

                # create all plus nodes originating from input nodes
                if not self.merge_input_and_plus_nodes:
                    for input_var in input_names:
                        self.__generate_out_edges(subgraph, input_var, self.__input, delay_graph, **self._input_node_style)

                # create alias nodes (max nodes) and create all plus nodes originating from alias nodes
                for alias_var in alias_names:
                    node_name = self.__max(alias_var)
                    node = subgraph.node(node_name, label="max", shape='ellipse', **self._alias_node_style)
                    self.__generate_out_edges(subgraph, alias_var, self.__max,  delay_graph, **self._alias_node_style)

                # connect outputs
                for output_var in output_names:
                    node_name = self.__max(output_var)
                    function  = delay_graph.output(output_var)
                    if output_var not in alias_names:
                        # if output is made up of multiple edges -> create max node
                        if len(function) > 1:
                            node = subgraph.node(node_name, label="max", shape='ellipse', **self._output_node_style)
                            subgraph.edge(node_name, self.__output(output_var))
                        # else forward to output node
                        else:
                            node_name = self.__output(output_var)
                    else:
                        # create edge from max node to output node
                        subgraph.edge(node_name, self.__output(output_var))
                    edges = {}
                    for var in function:
                        if var.delay == 0:
                            # if zero is no added delay refer to the correspoding source node
                            if var.name in alias_names:
                                subgraph.edge(self.__max(var.name), node_name)
                            else:
                                subgraph.edge(self.__input(var.name, var.delay), node_name)
                            continue
                        # avoid duplicate edges
                        if not var.name in edges:
                            edges[var.name] = []
                        elif var.delay in edges[var.name]:
                            continue
                        if self.merge_input_and_plus_nodes and var.name in input_names:
                            subgraph.edge(self.__input(var.name, var.delay), node_name)
                            continue
                        # create edge between plus node and output node
                        subgraph.edge(self.__plus(var.name, var.delay), node_name)
                        edges[var.name].append(var.delay)

                temp_file = temp_dir / f"{delay_graph.name}.dot"
                with temp_file.open('w') as f:
                    f.write(dot_graph.source)

                os.chdir(temp_dir)
                os.system(f"dot -Tpdf {delay_graph.name}.dot -o {delay_graph.name}.pdf")
                os.replace(f"{str(temp_dir)}/{delay_graph.name}.pdf", f"{str(variant_dir / delay_graph.name)}/{delay_graph.name}_delay_graph.pdf")

    def __generate_out_edges(self, subgraph, var_name, source_node_func, delay_graph, **kwargs):
        edges = []
        for output in delay_graph.outputs():
            for var in delay_graph.output(output):
                if var.name != var_name:
                    continue
                if var.delay == 0:
                    continue
                # avoid duplicate edges
                if var.delay in edges:
                    continue
                node_name = self.__plus(var.name, var.delay)
                node = subgraph.node(node_name, label=f"+{var.delay}", shape='ellipse', **kwargs)
                if source_node_func == self.__input:
                    subgraph.edge(source_node_func(var.name, var.delay), node_name)
                else:
                    subgraph.edge(source_node_func(var.name), node_name)
                edges.append(var.delay)

    def __input(self, name:str, delay:int) -> str:
        if not self.generate_unique_input_nodes:
            return ("in_" + name + str(delay))
        return ("in_" + name)

    def __output(self, name:str) -> str:
        return name #("out_" + name)

    def __plus(self, name:str, value:int) -> str:
        return f"plus_{value}_{name}"

    def __max(self, name:str) -> str:
        return ("max_" + name)