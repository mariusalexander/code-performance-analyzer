import tests.TestMaxTerm as TestMaxTerm

from src.Common import PrintDisabled

from src.BlockSchedulingTransformer import BlockSchedulingTransformer
from src.DelayGraph import DelayGraphTransformer


# Generates a block scheduling model and a delay graph model. 
# For the delay graph model it checks whether the simplified model matches the non simplified model
def generate_models(sched_model, code_blocks, verbose=False, simplify=False):
    block_schedule = BlockSchedulingTransformer(verbose=verbose).transform(sched_model, code_blocks)
    delay_model    = DelayGraphTransformer(verbose=verbose).transform(block_schedule, code_blocks, simplify=simplify)
    with PrintDisabled():
        delay_model_other = DelayGraphTransformer(verbose=False).transform(block_schedule, code_blocks, simplify=not simplify)

    # both the simplified and non simplified models should be equal in their prediction
    assert_equal(base_model =delay_model       if not simplify else delay_model_other, \
                 other_model=delay_model_other if not simplify else delay_model)

    return block_schedule, delay_model


def run():
    TestMaxTerm.tests()
    return 0