from typing import List, Self
from objprint import op

from src.Common import PrintDisabled, Print
from src.MaxPlusAlgebra import DelayVariable, PlusTerm, DelayFunction, DelayExpression

def iterable(*iter):
    for i in iter:
        yield i

###############################################################################

DV = DelayVariable

def DelayExpression_merge_timing_vars():
    # case 1
    inputs = iterable(-1, )
    result = DelayExpression.merge(inputs)
    expected = 0
    assert result.resolve() == expected, f"{result} -> {result.resolve()} vs {expected}!"

    # case 2
    inputs = iterable(10, 5, 4)
    result = DelayExpression.merge(inputs)
    expected = 10
    assert result.resolve() == expected, f"{result} -> {result.resolve()} vs {expected}!"
    
    # case 3
    delay  = 1
    inputs = iterable(1, 2, 3)
    result = DelayExpression.merge(inputs, delay)
    expected = 3 + delay
    assert result.resolve() == expected, f"{result} -> {result.resolve()} vs {expected}!"

def DelayExpression_merge_expressions():

    f1 = DelayFunction().merge_delay(10)
    f2 = DelayFunction().merge_delay( 0).add_coefficient(DV("A", 3))
    f3 = DelayFunction().merge_delay( 8).add_coefficient(DV("A", 1))
    f4 = DelayFunction().merge_delay( 6).add_coefficient(DV("A", 2))
    f5 = DelayFunction().merge_delay( 7).add_coefficient(DV("A", 1))

    DelayExpression.max_symbolic_delay = 10
    e1 = DelayExpression([
        f1,
        f2,
        f3,
        f4,
        f4,
        f5,
        f1
    ])
    print(repr(e))
    e.remove_redundant_terms()
    print(repr(e))

    print()

    e = DelayExpression([
        DelayFunction() \
            .merge_delay(4).add_coefficient(DV("A", 1)).add_coefficient(DV("B", 1)).add_coefficient(DV("C", 1)).add_coefficient(DV("D", 1)).add_coefficient(DV("E", 1)).add_coefficient(DV("F", 1)),
        DelayFunction() \
            .merge_delay(5).add_coefficient(DV("D", 1)).add_coefficient(DV("E", 1)).add_coefficient(DV("F", 1)),
        DelayFunction() \
            .merge_delay(5).add_coefficient(DV("A", 1)).add_coefficient(DV("B", 1)).add_coefficient(DV("C", 1)),
        DelayFunction() \
            .merge_delay(6)
    ])
    print(repr(e))
    e.remove_redundant_terms()
    print(repr(e))

def tests():
    Print.indent = 0

    print("  > Testing 'MaxTerm':")
    for test_function in \
            DelayExpression_merge_timing_vars, \
            DelayExpression_merge_expressions:
        print(f"   > executing {test_function.__name__}...")
        test_function()
    print("   > success!")
    return 0