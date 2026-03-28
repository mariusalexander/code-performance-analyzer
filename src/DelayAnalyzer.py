
from typing import List, Dict, Tuple

from src.Common import Profile, Print, dotdict
from src.MaxPlusAlgebra import DelayVariable, DelayFunctionList

class DelayAnalyzer:

    def __init__(self, verbose=True):
        print()
        print("-- BACKENDS: Delay Anaylzer --")
        self.verbose = verbose

    def apply_input_vector(self, input_vector:'dotdict', functions:Dict[str, 'DelayFunctionList']) -> Dict[str, 'DelayFunctionList']:
        print(f" > Applying input vector to {", ".join(functions.keys())}")
        results = dotdict()
        for name, function in functions.items():
            function = function.simplified()
            function.replace(input_vector)
            results[name] = function.simplified().simplified()
        return results

    def print(self, entries):
        function_names = []
        entries = { key:value for key, value in entries.items() if value is not None }
        for _, functions_dict in entries.items():
            function_names = list(functions_dict.keys())
            break

        old_indent = Print.indent
        with Print.indent_scope(24):
            for function_name in function_names:
                print(f"{" " * old_indent}> node '{function_name}':")
                for entry_name, functions in entries.items():
                    assert function_name in functions, "Incompatible functions!"
                    print(f"{" " * (old_indent + 1)}> {entry_name:<10} => {functions[function_name]}")

    def evaluate(self, functions:Dict[str, 'DelayFunctionList']) -> Dict[str, int]:
        outputs = dotdict()
        for name, function_list in functions.items():
            outputs[name] = function_list.evaluate()
        return outputs

    def estimate_cpi(self, pipeline:'PipelineDescription', output_vector:Dict[str, int], num_instructions, offset=0) -> Tuple[float, str]:
        start = pipeline.start()
        assert all(isinstance(name, str) and isinstance(value, int) for name, value in output_vector.items()), f"Invalid type, excpected an output_vector (Dict[str, int])"

        # accumulate timing variables for each stage in the pipeline
        estimations = []
        for output_name, value in output_vector.items():
            output_name = output_name.replace("o_", "")
            if output_name in pipeline:
                estimations.append(DelayVariable(output_name, value))

        pipeline_offsets = {start:0}
        # generate the expected offset for each stage
        stages = [start]
        while stages:
            next_stages = []
            for stage in stages:
                assert stage in pipeline_offsets, f"{stage} has no predecessor!"
                variable = pipeline_offsets[stage] + 1
                for next_stage in pipeline[stage]:
                    if next_stage not in next_stages:
                        next_stages.append(next_stage)
                    pipeline_offsets[next_stage] = variable
            stages = next_stages

        estimations.sort(key=lambda e: tuple(pipeline.keys()).index(e.name))

        # TODO: properly determine offset for pc-variables?
        #for output_name, value in output_vector.items():
        #    if "pc" in output_name:
        #        estimations.append(DelayVariable(output_name, value - 1))

        for e in estimations:
            e.delay -= (offset + pipeline_offsets[e.name]) if e.name in pipeline_offsets else offset
        
        max_val = max(reversed(estimations), key=lambda v: v.delay)
        cpi = max_val.delay / num_instructions
        if self.verbose:
            print(f"   > max({", ".join([f"{e.name}+{e.delay}" for e in estimations])})")
            print(f"   > bb={output_name} \tCPI = {f"{max_val.delay}/{num_instructions}":<10} = {cpi:.3f} \t({max_val.name})")

        return cpi, max_val