import copy
from typing import List, Self
from objprint import op

from src.Common import PrintDisabled, Print
from src.MaxPlusAlgebra import DelayVariable, MaxTerm, DelayFunction, DelayFunctionList, DelayFunction_v2, DelayFunctionList_v2

def test_term_simple():
    term = MaxTerm()
    term.append(DelayVariable("a", 3))
    term.append(DelayVariable("b", 2))
    term.append(DelayVariable("c", 1))
    return term

def test_term_with_duplicates():
    term = MaxTerm()
    term.append(DelayVariable("a", 3))
    term.append(DelayVariable("b", 2))
    term.append(DelayVariable("c", 1))
    term.append(DelayVariable("a", 2))
    term.append(DelayVariable("c", 1))
    term.append(DelayVariable("a", 0))
    return term

def test_vectors():
    reference = {"a":3, "b":2, "c":1}
    return (test_term_with_duplicates, reference), (test_term_simple, reference)

###############################################################################

def MaxTerm_max_delay():
    for factory, reference in test_vectors():
        term = factory()
        assert all(term.max_delay(v.name) == reference[v.name] for v in term), f"max_delay{term} should yield {reference}"

def MaxTerm_plus():
    for factory, reference in test_vectors():
        term = factory()
        term.plus(1)
        assert all(term.max_delay(v.name) == (reference[v.name] + 1) for v in term), f"max{term} should equal {reference} + 1"

def MaxTerm_names():
    for factory, reference in test_vectors():
        term = factory()
        reference = list(reference.keys())
        assert term.names() == reference, f"names: {term.names()} != {reference}"

def MaxFunction_plus():
    reference = {"a":3, "b":2, "c":1}

    function = DelayFunction()
    function.append_static_var(DelayVariable("a", 3))
    function.append_static_var(DelayVariable("b", 2))
    function.append_static_var(DelayVariable("c", 1))
    function.plus(1)
    assert all(function.max_delay(v.name) == (reference[v.name] + 1) for v in function.iter_static_vars()), f"function {function} should equal {reference} + 1"

    function.append_coefficient(DelayVariable("d1", 0))
    function.plus(1)
    assert all(function.max_delay(v.name) == (reference[v.name] + 2) for v in function.iter_static_vars()), f"function {function} should equal {reference} + 1"

    function.append_coefficient(DelayVariable("d2", 2))
    function.plus(1)
    assert all(function.max_delay(v.name) == (reference[v.name] + 3) for v in function.iter_static_vars()), f"function {function} should equal {reference} + 1"


def MaxFunction_is_covered_by():
    # 1.
    function1 = DelayFunction()
    function1.append_static_var(DelayVariable("if", 2))
    function1.append_static_var(DelayVariable("pc", 2))
    function1.append_static_var(DelayVariable("id", 1))
    function1.append_coefficient(DelayVariable("d1", 1))
    function1.append_coefficient(DelayVariable("d2", 2))
    function1.append_coefficient(DelayVariable("d3", 1))

    function2 = DelayFunction()
    function2.append_static_var(DelayVariable("if", 2))
    function2.append_static_var(DelayVariable("pc", 1))
    function2.append_static_var(DelayVariable("id", 1))
    function2.append_coefficient(DelayVariable("d1", 2))
    function2.append_coefficient(DelayVariable("d2", 1))

    assert function2.is_covered_by(function1), f"{function2} should be covered by {function1}"

    # 2.
    function1 = DelayFunction()
    function1.append_static_var(DelayVariable("if", 2))
    function1.append_coefficient(DelayVariable("d1", 2))
    function1.append_coefficient(DelayVariable("d2", 1))

    function2 = DelayFunction()
    function2.append_static_var(DelayVariable("if", 4))
    function2.append_coefficient(DelayVariable("d1", 1))

    assert function2.is_covered_by(function1), f"{function2} should be covered by {function1}"

def MaxFunction_merge():
    static = DelayFunction()
    static.append_static_var(DelayVariable("X", 3))
    static.append_static_var(DelayVariable("Y", 2))
    static.append_static_var(DelayVariable("Z", 3))
    static.append_static_var(DelayVariable("U", 0))
    static_orig = copy.deepcopy(static)

    dynamic = DelayFunction()
    dynamic.append_static_var(DelayVariable("X", 2))
    dynamic.append_static_var(DelayVariable("Y", 1))
    dynamic.append_static_var(DelayVariable("Z", 1))
    dynamic.append_coefficient(DelayVariable("d1"))
    dynamic_orig = copy.deepcopy(dynamic)

    # 1. merging function with empty list should add function to list
    functions = DelayFunctionList()
    functions.merge(static)

    reference = DelayFunctionList((static, ))
    assert functions == reference, f"DelayFunctionList().merge({static}) should equal {reference}"

    # 2. merging dyanmic function with static function should remove redundant terms from static function
    reference = DelayFunction()
    reference.append_static_var(DelayVariable("Z", 3))
    reference.append_static_var(DelayVariable("U", 0))
    reference = DelayFunctionList((reference, dynamic))

    assert functions.merge(dynamic) == reference, f"DelayFunctionList([{static}]).merge({dynamic}) should equal {reference}"
    
    # 3. merging should create deep copies of the input function 
    assert static == static_orig, f"DelayFunctionList().merge() should not alter input function!"
    assert dynamic == dynamic_orig, f"DelayFunctionList().merge() should not alter input function!"



def MaxFunction_merge_v2():
    Print.indent = 0

    f1 = DelayFunction_v2()
    f1.append_static_var(DelayVariable("", 5))

    f2 = DelayFunction_v2()
    f2.append_static_var(DelayVariable("", 2))
    f2.append_coefficient(DelayVariable("d1"))

    funcs = DelayFunctionList_v2()
    op(funcs.instances)
    funcs.merge(f1)
    op(funcs.instances)
    funcs.merge(f2)
    op(funcs.instances)
    funcs.merge(f2)
    op(funcs.instances)

    f3 = DelayFunction_v2()
    f3.append_static_var(DelayVariable("", 1))
    f3.append_coefficient(DelayVariable("d1"))
    funcs.merge(f3)
    op(funcs.instances)

    #print("#"*10)
    f4 = DelayFunction_v2()
    f4.append_static_var(DelayVariable("", 4))
    f4.append_coefficient(DelayVariable("d2"))
    funcs.merge(f4)
    op(funcs.instances)
    #op(funcs, funcs.instances)

    f5 = DelayFunction_v2()
    f5.append_static_var(DelayVariable("", 5))
    f5.append_coefficient(DelayVariable("d1", 1))
    f5.append_coefficient(DelayVariable("d2", 2))
    funcs.merge(f5)
    op(funcs.instances)
    #op(funcs, funcs.instances)

    f6 = DelayFunction_v2()
    f6.append_static_var(DelayVariable("", 10))
    funcs.merge(f6)
    op(funcs.instances)





def MaxFunction_resolved():
    function = DelayFunction()
    function.append_static_var(DelayVariable("X", 3))
    function.append_static_var(DelayVariable("Y", 3))
    function = function.replace({"X":DelayVariable("", 1)})
    assert function.max_delay("Y") == 3, f"{function.max_delay("Y")} != 3"
    
    function.append_coefficient(DelayVariable("X", 2))
    function = function.replace({"X":DelayVariable("", 1)})
    assert function.max_delay("Y") == 5, f"{function.max_delay("Y")} != 5"

def tests():
    print("  > Testing 'MaxTerm':")
    # deactivated: MaxFunction_is_covered_by, MaxFunction_merge
    for test_function in MaxTerm_max_delay, MaxTerm_plus, MaxTerm_names, \
                         MaxFunction_plus, MaxFunction_merge_v2, MaxFunction_resolved:
        print(f"   > executing {test_function.__name__}...")
        test_function()
    print("   > success!")
    return 0