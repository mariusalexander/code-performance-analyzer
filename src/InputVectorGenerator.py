import re
from objprint import op
from typing import List, Dict, Self
from itertools import chain

from meta_models.structural_model.StructuralModel import Variant

from src.Common import Profile, Print, dotdict
from src.DelayGraph import DelayGraph, DelayGraphTransformer
from src.MaxPlusAlgebra import DelayVariable

class PipelineDescription(dotdict):

    def __init__(self):
        pass

    def start(self):
        all_dependencies = tuple(other for i in self for other in self[i])
        filtered = tuple(current for current in self if current not in all_dependencies)
        assert len(filtered)  > 0, f"No start-stage found!"
        assert len(filtered) <= 1, f"Multiple start-stages defined: {", ". join(filtered)}"
        return filtered[0]

    def end(self):
        filtered = tuple(var for var in self if len(self[var]) == 0)
        assert len(filtered)  > 0, f"No end-stage found!"
        assert len(filtered) <= 1, f"Multiple end-stages defined: {", ". join(filtered)}"
        return filtered[0]

    @staticmethod
    def generate(structural_variant:Variant):
        timing_variables = PipelineDescription()
        pipeline = structural_variant.getPipeline()
        stages   = pipeline.getFirstStages()

        while stages:
            next_stages = []
            for stage in stages:
                assert stage.capacity == 1
                timing_variable = stage.name
                # TODO: this is hacky -> access variable of stage 
                # name without accessing delay graph
                edge = dotdict({"timingVariable":dotdict({"name":timing_variable, "numElements":1}), "dynamic":False, "depth":1})
                variable_name = DelayGraphTransformer.variable_name(edge=edge)
                timing_variables[variable_name] = tuple()
                for next_stage in chain(stage.getNextStages(), stage.getFirstSubStages()):
                    assert next_stage.capacity == 1
                    next_stages.append(next_stage)
                    next_timing_variable = next_stage.name
                    edge.timingVariable.name = next_timing_variable
                    next_variable_name = DelayGraphTransformer.variable_name(edge=edge)
                    timing_variables[variable_name] = timing_variables[variable_name] + (next_variable_name,)
            stages = next_stages
        return timing_variables

class InputVector(dotdict):

    def merge(self, other:'dotdict') -> Self:
        for name, value in other.items():
            trimmed = name.replace('o_', '')
            self[trimmed] = DelayVariable('', value)
        return self

class InputVectorGenerator:

    def __init__(self, structural_variant:Variant, delay_graph:DelayGraph, verbose=True):
        print()
        print("-- GENERATOR: INPUT_VECTOR_GENERATOR --")
        assert isinstance(structural_variant, Variant)

        self.structural_variant = structural_variant
        self.delay_graph  = delay_graph
        self.input_vector = InputVector()
        self._zero_delay  = DelayVariable(name='')
        self.verbose = verbose

    def assume_all_registers_available(self) -> Self:
        """
        Replaces all input registers with a zero delay -> initial availability of registers has no effect.
        """
        if self.verbose:
            print(f" > assuming all registers are available")
        for variable_name in self.delay_graph.inputs():
            is_register = re.search(r"^(r\d+)", variable_name)
            if is_register:
                self.input_vector[is_register.group(1).lower()] = self._zero_delay
        return self

    def assume_fix_dynamic_delays(self, value=1):
        if self.verbose:
            print(f" > assuming all dynamic delays = {value}")
        assert value > 0, "dynamic delays are expected to be > 1"
        for variable_name in self.delay_graph.dynamic_variables():
            self.__assume_input_value(variable_name.lower(), self._zero_delay.added(value))
        return self

    def assume_pc_available(self):
        """
        Replaces all instances of pc with a zero delay.
        """
        pcs = [name.lower() for name in self.delay_graph.inputs() if "pc" in name.lower()]
        # TODO: how to handle multiple pc inputs?
        assert len(pcs) == 1, f"  > WARNING: found multiple inputs which could map to 'pc': {", ".join(pcs)}"
        for pc in pcs:
            self.__assume_input_value(pc, self._zero_delay)
        return self

    def assume_perfect_pipeline(self, pipeline:'PipelineDescription', use_zero_delay=False):
        start = pipeline.start()
        self.__assume_input_value(start, self._zero_delay)

        stages = [start]
        while stages:
            next_stages = []
            for stage in stages:
                assert stage in self.input_vector, f"{stage} has no predecessor!"
                variable = self.input_vector[stage].copy()
                if use_zero_delay:
                    variable.delay = 0
                else:
                    variable.add(1)
                for next_stage in pipeline[stage]:
                    if next_stage not in next_stages:
                        next_stages.append(next_stage)
                    self.__assume_input_value(next_stage, variable)
            stages = next_stages
        return self

    def __assume_input_value(self, variable_name, variable):
        self.input_vector[variable_name] = variable
        if self.verbose:
            print(f" > assuming {variable_name:<5} = {variable}")

    def finalize(self):
        if self.verbose:
            print( " > generated:", self.input_vector)
            unresolved = ", ".join(v for v in self.delay_graph.all_variables() if v not in self.input_vector)
            print( " > unresolved variables:", unresolved if len(unresolved) > 0 else None)
        return self.input_vector