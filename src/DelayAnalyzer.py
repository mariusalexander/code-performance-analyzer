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

import time

# TODO: remove me, for debugging purpose only
from objprint import op

from backends.basic_block_analyzer.DelayGraph import DelayGraphModel, DelayGraphVariant, DelayGraph, SymbolicVariable
from meta_models.structural_model.StructuralModel import StructuralModel, Variant

class DelayAnalyzer:

    def __init__(self, structural_model:StructuralModel, delay_graph_model:DelayGraphModel, verbose=True):
        print()
        print("-- BACKENDS: DELAY_GRAPH_ANALYZER --")
        self.verbose = verbose
        self.structural_model = structural_model
        self.delay_graph_model = delay_graph_model
        self.target_variable = SymbolicVariable("if")
        self.mappings = { var_name:{} for var_name in self.delay_graph_model.variants }
        self._zero = SymbolicVariable("zero")

    def assume_registers_available(self):
        """
        Replaces all input registers with a zero delay -> initial availability of registers has no effect.
        """
        if self.verbose:
            print(f" > assuming all registers are available")
        for variant in self.delay_graph_model.variants:
            mappings = self.mappings[variant]
            self.mappings[variant] = mappings | { f"r{reg}":self._zero for reg in range(1, 32) }
        return self

    def assume_no_dynamic_delays(self):
        """
        Replaces all dynamic delay with a zero delay -> dynamic delays have no effect and ignored.
        """
        if self.verbose:
            print(f" > assuming no dynamic delays")
        for variant in self.delay_graph_model.variants:
            delay_graph_variant = self.delay_graph_model.variants[variant]
            mappings = self.mappings[variant]
            for function_name in delay_graph_variant.scheduling_functions:
                delay_graph = delay_graph_variant.scheduling_functions[function_name]
                for var in delay_graph.dynamic_variables():
                    mappings[var] = self._zero
        return self

    def assume_pc_available(self):
        """
        Replaces all instances of pc with an equivalent instance of if.
        """
        if self.verbose:
            print(f" > assuming: pc = if")
        for variant in self.delay_graph_model.variants:
            # TODO: check that 'self.target_variable.name' exists in variables
            self.mappings[variant]["pc"] = self.target_variable
        return self

    def assume_perfect_pipeline(self):
        printed = []
        for structural_variant in self.structural_model.getAllVariants():
            mappings = self.mappings[structural_variant.name]
            delay_graph_variant = self.delay_graph_model.variants[structural_variant.name]

            pipeline = structural_variant.getPipeline()
            stages = pipeline.getFirstStages()
            for function_name in delay_graph_variant.scheduling_functions:
                delay_graph = delay_graph_variant.scheduling_functions[function_name]
                while stages:
                    next_stages = []
                    for stage in stages:
                        assert stage.capacity == 1
                        timing_variable = stage.name
                        variable_name = delay_graph.input_to_variable_name(timing_variable)
                        if variable_name is None: # timing variable not used
                            continue
                        # link all succeeding timing variables to the current timing variable
                        next_stages += pipeline.getNextStages(stage)
                        for next_stage in pipeline.getNextStages(stage):
                            assert next_stage.capacity == 1
                            next_timing_variable = next_stage.name
                            next_variable_name   = delay_graph.input_to_variable_name(next_timing_variable)
                            if next_variable_name is None: # timing variable not used
                                continue
                            if next_variable_name not in printed:
                                if self.verbose:
                                    print(f" > assuming {next_variable_name} = 1 + {variable_name}")
                                printed.append(next_variable_name)
                            mappings[next_variable_name] = SymbolicVariable(variable_name, 1)
                            if next_stage not in next_stages:
                                next_stages.append(next_stage)
                    stages = next_stages
                break
        return self

    def resolve(self, estimate_cpi=False):
        """
        Attempts to simplify all scheduling functions according to assumptions set prior to calling this function.
        """
        # TODO: determine dynamically from structural model
        relationships = {
            "o_pc_np" : self.target_variable.merged(0), # branch prediction
            "o_if"    : self.target_variable.merged(0),
            "o_id"    : self.target_variable.merged(1),
            "o_ex"    : self.target_variable.merged(2),
            "o_mem"   : self.target_variable.merged(3),
            "o_wb"    : self.target_variable.merged(4)
        }
        # TODO: allow defining input vector
        initial_value = self.target_variable.merged(0)

        for variant_name in self.delay_graph_model.variants:

            print(f" > Resolving delay graph for '{variant_name}'")

            delay_graph_variant = self.delay_graph_model.variants[variant_name]
            mappings = self.mappings[variant_name]

            for function_name in delay_graph_variant.scheduling_functions:
                print(f"  > Resolving delay graph of '{function_name}'")
                start = time.perf_counter_ns()

                delay_graph = delay_graph_variant.scheduling_functions[function_name]

                num_instructions = sum([int("Enter" in node) for node in delay_graph.nodes()])
                estimations = []

                for output_name in delay_graph.outputs():
                    output = delay_graph.get_output(output_name)
                    output = output.expanded(delay_graph.intermediates())
                    before = output
                    for i in range(0, len(mappings)):
                        for mapping in mappings:
                            output = output.replaced(mapping, mappings[mapping])
                    output = output.resolved(self._zero.name)
                    output = output.replaced(self.target_variable.name, initial_value)
                    if self.verbose:
                        print(f"   > Resolved {output_name.ljust(10)} :  {before}\t \n" + \
                              f"              {"".ljust(10)} => {output}")
                    if estimate_cpi and output_name in relationships:
                        relation = relationships[output_name]
                        estimations.append(SymbolicVariable(output_name, output.max_value(relation.name)))

                if estimations:
                    estimations.sort(key=lambda e: list(relationships.keys()).index(e.name))
                    print(f"   > max({", ".join([f"{e}" for e in estimations])})")
                    # choose the variable with biggest change in its delay
                    max_val = max(estimations, key=lambda v: (v.delay - relationships[v.name].delay))
                    max_val.delay -= initial_value.delay
                    print(f"core={variant_name} \tbb={function_name} \tCPI = {f"{max_val.delay}/{num_instructions}":<10} = {(max_val.delay / num_instructions):.3f} \t({max_val.name})")

                end = time.perf_counter_ns()
                print(f"  > took {(end - start) / 1_000_000}ms!")
