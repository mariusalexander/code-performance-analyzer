from src.Common import PrintDisabled
from src.DelayGraph import DelayVariable, MaxTerm

def term_simple():
    term = MaxTerm()
    term.append(DelayVariable("a", 3))
    term.append(DelayVariable("b", 2))
    term.append(DelayVariable("c", 1))
    return term

def term_with_duplicates():
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
    return (term_with_duplicates, reference), (term_simple, reference)

###############################################################################

def MaxTerm_max_value():
    for factory, reference in test_vectors():
        term = factory()
        assert all(term.max_value(v.name) == reference[v.name] for v in term), f"max_value: {term} != {reference}"

def MaxTerm_plus():
    for factory, reference in test_vectors():
        term = factory()
        term.plus(1)
        assert all(term.max_value(v.name) == (reference[v.name] + 1) for v in term), f"plus: {term} != {reference}"

def MaxTerm_names():
    for factory, reference in test_vectors():
        term = factory()
        reference = list(reference.keys())
        assert term.names() == reference, f"names: {term.names()} != {reference}"

def MaxTerm_resolved():
    for factory, reference in test_vectors():
        term = factory()
        term = term.resolved("a")
        assert all(term.max_value(v.name) == reference["a"] for v in term), f"resolved: {term} vs {reference}"

def tests():
    MaxTerm_max_value()
    MaxTerm_plus()
    MaxTerm_names()
    MaxTerm_resolved()
    return 0