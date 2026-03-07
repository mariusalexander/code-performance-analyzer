import tests.TestMaxTerm as TestMaxTerm

from src.Common import PrintDisabled

def assert_equal(base_model, other_model):
    """ Helper method to assert that two delay graph models are equal by comparing their expanded outputs. """
    assert len(base_model.variants) == len(other_model.variants), \
           f"Number of variants mismatches! ({len(base_model.variants)} vs expected {other_model.variants})"
    vidx = -1
    for base_variant in base_model.variants:
        vidx += 1
        other_variant = other_model.variants[vidx]
        assert base_variant.name == other_variant.name
        assert len(base_variant.scheduling_functions) == len(other_variant.scheduling_functions), \
               f"Number of scheduling functions mismatches! ({len(other_variant.scheduling_functions)} vs expected {base_variant.scheduling_functions})"
        gidx = -1
        for base_graph in base_variant.scheduling_functions:
            gidx += 1
            other_graph = other_variant.scheduling_functions[gidx]
            assert base_graph.name == other_graph.name
            assert len(base_graph.outputs()) == len(other_graph.outputs()), \
                   f"Number of outputs mismatches! ({len(base_graph.outputs())} vs expected {len(other_graph.outputs())})"
            for output_name in base_graph.outputs():
                base_output  = base_graph.output(output_name).expanded(base_graph.intermediates())
                other_output = other_graph.output(output_name).expanded(other_graph.intermediates())
                assert base_output == other_output, f"Mistmatch:\n > {output_name} \t {base_output}\t\n > {" " * (len(output_name) + 1)}\t {other_output}"

def run():
    print()
    print("-- UNITTESTS --")
    TestMaxTerm.tests()
    print(" > executed unittests successfully")
    return 0