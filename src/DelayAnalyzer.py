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

from meta_models.structural_model.StructuralModel import StructuralModel, Variant

from src.Common import Profile, Print
from src.DelayGraph import DelayGraphModel
from src.MaxPlusAlgebra import DelayVariable

class DelayAnalyzer:

    def __init__(self, structural_model:StructuralModel, delay_graph_model:DelayGraphModel, verbose=True):
        print()
        print("-- BACKENDS: DELAY_GRAPH_ANALYZER --")
        self.verbose = verbose
        self.structural_model  = structural_model
        self.delay_graph_model = delay_graph_model
        self.mappings = { v.name:{} for v in self.delay_graph_model.variants }
        self._zero = DelayVariable(name="")
        self.target_variable = self._zero

    def assume_registers_available(self):
        """
        Replaces all input registers with a zero delay -> initial availability of registers has no effect.
        """
        if self.verbose:
            print(f" > assuming all registers are available")
        for variant in self.delay_graph_model.variants:
            mappings = self.mappings[variant.name]
            self.mappings[variant.name] = mappings | { f"r{reg}":self._zero for reg in range(0, 32) }
        return self

    def assume_fix_dynamic_delays(self, value=1):
        if self.verbose:
            print(f" > assuming no dynamic delays")
        assert value > 0, "dynamic delays must at least be equal to one"
        for variant in self.delay_graph_model.variants:
            mappings = self.mappings[variant.name]
            for delay_graph in variant.scheduling_functions:
                for name in delay_graph.dynamic_variables():
                    mappings[name] = self._zero.added(value)
        return self

    def assume_pc_available(self):
        """
        Replaces all instances of pc with a zero delay.
        """
        if self.verbose:
            print(f" > assuming: pc = 0")
        for variant in self.delay_graph_model.variants:
            pcs = []
            for delay_graph in variant.scheduling_functions:
                pcs += [name for name in delay_graph.inputs() if "pc" in name.lower() and name not in pcs]
            assert "pc" in pcs
            if len(pcs) > 1:
                print("  > WARNING: found multiple inputs which could map to 'pc':", pcs)
            self.mappings[variant.name]["pc"] = self.target_variable
        return self

    def assume_perfect_pipeline(self):
        printed = []
        idx = -1
        for structural_variant in self.structural_model.getAllVariants():
            idx += 1
            mappings = self.mappings[structural_variant.name]
            variant  = self.delay_graph_model.variants[idx]
            assert variant.name == structural_variant.name
            
            timing_variables = {}
            pipeline = structural_variant.getPipeline()
            stages   = pipeline.getFirstStages()
            for delay_graph in variant.scheduling_functions:
                while stages:
                    next_stages = []
                    for stage in stages:
                        assert stage.capacity == 1
                        timing_variable = stage.name
                        variable_name   = delay_graph.input_to_variable_name(timing_variable)
                        if variable_name is None: # timing variable not used
                            continue
                        # first timing varialbe maps to target variable
                        if len(timing_variables) == 0:
                            variable = self.target_variable
                            mappings[variable_name] = variable
                        # replace timing varialbe with previous variable name
                        elif variable_name in mappings:
                            variable = mappings[variable_name]
                        else:
                            variable = DelayVariable(variable_name)
                        timing_variables[f"o_{variable_name}"] = variable.copy()
                        variable = variable.added(1)
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
                                    print(f" > assuming {next_variable_name}: = {variable}")
                                printed.append(next_variable_name)
                            mappings[next_variable_name] = variable
                            if next_stage not in next_stages:
                                next_stages.append(next_stage)
                    stages = next_stages
                break
            mappings["timing_variables"] = timing_variables
        return self

    def resolve(self, estimate_cpi=False):
        """
        Attempts to simplify all scheduling functions according to assumptions set prior to calling this function.
        """
        printed = not self.verbose
        for variant in self.delay_graph_model.variants:
            print(f" > Resolving delay graph for '{variant.name}'")
            mappings = self.mappings[variant.name]
            relationships = mappings["timing_variables"]

            if not printed:
                printed = True
                mapping = self.mappings[variant.name]
                print(variant.name, "mapping: {\n ", ",\n  ".join(f"{v:>5}:{str(mapping[v]):>6}" for v in mapping), "\n}")

            for delay_graph in variant.scheduling_functions:
                print(f"  > Resolving delay graph of '{delay_graph.name}'")
                Print.indent = 3
                with Profile(f"   >"):
                    num_instructions = sum(int("Enter" in node) for node in delay_graph.nodes())
                    estimations = []

                    for output_name, output in delay_graph.outputs().items():
                        if self.verbose:
                            before = output.copy()
                        output.replace(mappings)
                        output = output.simplified()
                        if self.verbose: 
                            with Print.indent_scope(32):
                                print(f"   > Resolved {output_name.ljust(10)} :  {before}\n" + \
                                      f"              {         "".ljust(10)} => {output}")
                        if estimate_cpi and output_name in relationships:
                            relation = relationships[output_name]
                            estimations.append(DelayVariable(output_name, output.max_delay(relation.name)))

                    if estimations:
                        estimations.sort(key=lambda e: tuple(relationships.keys()).index(e.name))
                        # choose the variable with biggest change in its delay
                        max_val = max(estimations, key=lambda v: (v.delay - relationships[v.name].delay))
                        print(f"   > core={variant.name} \tbb={output_name} \tCPI = {f"{max_val.delay}/{num_instructions}":<10} = {(max_val.delay / num_instructions):.3f} \t({max_val.name})")
                        if self.verbose:
                            print(f"   > max({", ".join([f"{e}" for e in estimations])})")
                            print( "   >", delay_graph.code_block)
                print()
            print()