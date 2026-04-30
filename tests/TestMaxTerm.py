from typing import List, Self
from objprint import op

from src.Common import PrintDisabled, Print
from src.MaxPlusAlgebra import DelayVariable, MaxTerm, DelayFunction, DelayExpression

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
        assert list(term.names()) == reference, f"names: {list(term.names())} != {reference}"

def MaxFunction_merge():
    Print.indent = 0

    f1 = DelayFunction()
    f1.merge_delay(5)

    f2 = DelayFunction()
    f2.merge_delay(2)
    f2.add_coefficient(DelayVariable("d1", 1))

    funcs = DelayExpression()
    funcs.merge(f1)
    funcs.merge(f2)
    funcs.merge(f2)

    f3 = DelayFunction()
    f3.merge_delay(1)
    f3.add_coefficient(DelayVariable("d1", 1))
    funcs.merge(f3)

    f4 = DelayFunction()
    f4.merge_delay(4)
    f4.add_coefficient(DelayVariable("d2", 1))
    funcs.merge(f4)

    f5 = DelayFunction()
    f5.merge_delay(5)
    f5.add_coefficient(DelayVariable("d1", 1))
    f5.add_coefficient(DelayVariable("d2", 2))
    funcs.merge(f5)

    f6 = DelayFunction()
    f6.merge_delay(7)
    funcs.merge(f6)

    assert funcs.resolve({ "d1": 0, "d2": 0 }) == 7
    assert funcs.resolve({ "d1": 1, "d2": 0 }) == 7
    assert funcs.resolve({ "d1": 1, "d2": 1 }) == 8
    assert funcs.resolve({ "d1": 2, "d2": 3 }) == 13

def tests():
    print("  > Testing 'MaxTerm':")
    for test_function in MaxTerm_max_delay, MaxTerm_plus, MaxTerm_names, \
                         MaxFunction_merge:
        print(f"   > executing {test_function.__name__}...")
        test_function()
    print("   > success!")
    return 0