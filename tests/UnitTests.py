import tests.TestMaxTerm as TestMaxTerm

from src.Common import PrintDisabled
from src.BlockSchedulingTransformer import BlockSchedulingTransformer
from src.DelayGraph import DelayGraphTransformer

def generate_models(sched_model, code_blocks, verbose=False, simplify=False):
    """ 
    Generates a block scheduling model and a delay graph model. 
    For the delay graph model it checks whether the simplified model matches the non simplified model
    """
    block_schedule = BlockSchedulingTransformer(verbose=verbose).transform(sched_model, code_blocks)
    delay_model    = DelayGraphTransformer(verbose=verbose).transform(block_schedule, code_blocks, simplify=simplify)
    with PrintDisabled():
        delay_model_other = DelayGraphTransformer(verbose=False).transform(block_schedule, code_blocks, simplify=not simplify)

    # both the simplified and non simplified models should be equal in their prediction
    assert_equal(base_model =delay_model       if not simplify else delay_model_other, \
                 other_model=delay_model_other if not simplify else delay_model)

    return block_schedule, delay_model


def assert_equal(base_model, other_model):
    """ Helper method to assert that two delay graph models are equal by comparing their expanded outputs. """
    assert len(base_model.variants) == len(other_model.variants), \
           f"Number of variants mismatches! ({len(base_model.variants)} vs expected {other_model.variants})"
    for variant_name in base_model.variants:
        base_variant  = base_model.variants[variant_name]
        other_variant = other_model.variants[variant_name]
        assert len(base_variant.scheduling_functions) == len(other_variant.scheduling_functions), \
               f"Number of scheduling functions mismatches! ({len(other_variant.scheduling_functions)} vs expected {base_variant.scheduling_functions})"
        for function in base_variant.scheduling_functions:
            baseGraph  = base_variant.scheduling_functions[function]
            otherGraph = other_variant.scheduling_functions[function]
            assert len(baseGraph.outputs()) == len(otherGraph.outputs()), \
                   f"Number of outputs mismatches! ({len(baseGraph.outputs())} vs expected {len(otherGraph.outputs())})"
            for output_name in baseGraph.outputs():
                base_output  = baseGraph.get_output(output_name).expanded(baseGraph.intermediates())
                other_output = otherGraph.get_output(output_name).expanded(otherGraph.intermediates())
                assert base_output == other_output, f"Mistmatch:\n > {output_name} \t {base_output}\t\n > {" " * (len(output_name) + 1)}\t {other_output}"

def run():
    TestMaxTerm.tests()
    return 0