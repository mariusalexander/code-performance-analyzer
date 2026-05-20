import math
import atexit
from objprint import op, objstr
from itertools import chain, product
from typing import List, Dict, Optional, Self

from src.Common import Print, Profile, PrintDisabled

symbolic_variable_names = {}

def get_var_name(name):
    """ Shortens symbolic variables names. """
    if name in symbolic_variable_names:
        return symbolic_variable_names[name]
    assert len(symbolic_variable_names) < 26, "exceeding ascii letters!"
    variable_name = chr(ord('A') + len(symbolic_variable_names))
    symbolic_variable_names[name] = variable_name
    return variable_name

def _print_symbolic_abbreviations():
    """ Prints the symbolic variables names at exit. """
    if symbolic_variable_names:
        print(f"with symbolic variables:")
        for name, abbr in symbolic_variable_names.items():
            print(f" - {abbr} = {name}")

atexit.register(_print_symbolic_abbreviations)


class DelayVariable:
    """ Represents a variable in a max or plus term, associated with an added delay. """

    __slots__ = ["name", "delay"] # memory optimization

    def __init__(self, name:str='', delay:int=0):
        self.name  = name
        self.delay = delay

    def __str__(self):
        return f"({self.name},{self.delay})"

    def __repr__(self):
        return self.__str__()

    def add(self, delay:int) -> Self:
        """ Adds the delay. """
        self.delay += delay
        return self

    def added(self, delay:int) -> 'DelayVariable':
        """ Returns a copy with the added delay. """
        return self.copy().add(delay)

    def copy(self) -> Self:
        """ Returns a copy of this variable. """
        return DelayVariable(self.name, self.delay)


class BaseTerm:
    """ Represents a abstract term, a list of variables. """

    __slots__ = ["variables"] # memory optimization

    def __init__(self, iterable_or_arg=None):
        self.variables: List['DelayVariable'] = []
        if iterable_or_arg is None:
            return
        if isinstance(iterable_or_arg, DelayVariable):
            self.append(iterable_or_arg)
            return
        for var in iterable_or_arg:
            self.append(var)

    def __repr__(self) -> str:
        return self.__str__()

    def __contains__(self, variable_name: str) -> bool:
        """
        Returns whether a variable with a given name exists in the term.
        """
        assert isinstance(variable_name, str), \
               f"Incompatible type '{type(variable_name)}', expected 'str'!"
        return any(v.name == variable_name for v in self)

    def __iter__(self) -> 'iterable':
        return self.variables.__iter__()

    def __len__(self) -> int:
        return len(self.variables)

    def __add__(self, other) -> Self:
        for var in other:
            self.append(var)
        return self

    def names(self) -> 'iterable':
        """
        Returns an iterable of all variable names as they appear in order.
        """
        # NOTE: PlustTerm must only contain each variable once
        # assert len(self) == len(set(v.name for v in self)), "PlusTerm contains duplicate variables!"
        return (v.name for v in self)

    def sort(self) -> Self:
        """
        Sorts the term in place by its delay (descending).
        For variables with same delay, alphabetical order is used.
        """
        self.variables.sort(key=lambda v: (-v.delay, v.name))
        return self

    def remove(self, variable_name: str) -> Self:
        """
        Removes each instance of the variable from this term.
        Does nothing if no variable with given name exists in this term.
        Returns self for operator chaining.
        """
        for var in tuple(v for v in self if v.name == variable_name):
            self.variables.remove(var)
        return self

    def copy(self) -> Self:
        """
        Returns a copy of this term.
        """
        return self.__class__(v.copy() for v in self)


# NOTE: unused
class MaxTerm(BaseTerm):
    """
    Represents a max term, made out of a list of variables.
    The delay of each variable is added onto the value of variable.
    Only supports positive delays.
    """

    def __init__(self, iterable_or_arg=None):
        super().__init__(iterable_or_arg)

    def __str__(self) -> str:
        return f"max({", ".join(f"{v.name}+{v.delay}" for v in self)})"

    def __eq__(self, other) -> bool:
        """
        Returns whether two terms are equal.
        """
        assert isinstance(other, MaxTerm), \
               f"Incompatible type '{type(other)}', expected '{type(self)}'!"
        return all((name in other and other.max_delay(name) == self.max_delay(name)) for name in self.names())

    def append(self, variable: DelayVariable) -> Self:
        """
        Appends the variable to the term. Merges the variables if it already exits.
        The delay must be positive. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), \
               f"Incompatible type '{type(value)}', expected {type(DelayVariable)}'!"
        assert variable.delay >= 0, "Variables in a max term must be positive!"
        # update value if variable already exists
        for var in (v for v in self if v.name == variable.name):
            var.add(variable.delay)
            return self
        # else add variable
        self.variables.append(variable)
        return self

    def max_delay(self, variable_name: str) -> Optional[int]:
        """
        Returns the maximum added delay of the variable `name`.
        If the variable does not exist None is returned.
        """
        try:
            return max(v.delay for v in self if v.name == variable_name)
        except ValueError:
            return None

    def plus(self, value:int) -> Self:
        """
        Adds `value` to the delay of each variable.
        Returns self for operator chaining.
        """
        if value < 0:
            raise ValueError("Only positive values are expected")
        for v in self:
            v.add(value)
        return self

    # TODO: not needed? -> term should not contain duplicates
    def simplified(self) -> 'MaxTerm':
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Keeps order of names. Returns a new term.
        """
        return MaxTerm(DelayVariable(name, self.max_delay(name)) for name in self.names())


class PlusTerm(BaseTerm):
    """
    Represents a plus term, made out of a list of variables.
    The delay of each variable is multiplied with the value of variable.
    Each delay must be equal one at least.
    """

    def __init__(self, iterable_or_arg=None):
        super().__init__(iterable_or_arg)

    def __str__(self) -> str:
        return " + ".join(f"{v.delay}*{get_var_name(v.name)}" for v in self)

    def __repr__(self) -> str:
        return "+".join(f"{v.delay}*{get_var_name(v.name)}" for v in self)

    def to_str(self) -> str:
        """
        Returns a brief string representation of this term in max-plus notation.
        """
        return "*".join(f"{v.delay}{get_var_name(v.name)}" for v in self)

    def __eq__(self, other) -> bool:
        """
        Returns whether two terms are equal.
        """
        assert isinstance(other, PlusTerm), \
               f"Incompatible type '{type(other)}', expected '{type(self)}'!"
        # each variable should be listed only once!
        assert len(set(self.names())) == len(self), \
               f"Term {self} contains duplicate variables!"
        return len(other) == len(self) and \
               all((var.name in other and other.count(var.name) == var.delay) for var in self)

    def append(self, variable: DelayVariable) -> Self:
        """
        Appends the variable to the term. Merges the variables if it already exits.
        The delay must be positive. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), \
               f"Incompatible type '{type(value)}', expected {type(DelayVariable)}'!"
        assert variable.delay > 0, "Variables in a plus term must have positive values > 0!"
        # update value if variable already exists
        for var in (v for v in self if v.name == variable.name):
            var.add(variable.delay)
            return self
        # else add variable
        self.variables.append(variable)
        return self

    def count(self, variable_name: str) -> int:
        """
        Returns the magnitude of the variable `name`. If the variable does not exist 0 is returned.
        """
        assert isinstance(variable_name, str), \
               f"Incompatible type '{type(variable_name)}', expected 'str'!"
        return sum(v.delay for v in self if v.name == variable_name)

    # TODO: not needed? -> term should not contain duplicates
    def simplified(self) -> 'PlusTerm':
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Keeps order of names. Returns a new term.
        """
        return PlusTerm(DelayVariable(name, self.count(name)) for name in self.names())


class DelayFunction:

    __slots__ = ["constant", "variables"]

    def __init__(self):
        self.constant  = 0
        self.variables = PlusTerm()

    def __str__(self) -> str:
        if len(self.variables):
            return f"{self.constant} + {self.variables}"
        return str(self.constant)

    def __repr__(self) -> str:
        if len(self.variables):
            return f"{self.constant}+{repr(self.variables)}"
        return str(self.constant)

    def to_str(self) -> str:
        """
        Returns a brief string representation of this function in max-plus notation.
        """
        if len(self.variables):
            return f"{self.constant}*{self.variables.to_str()}"
        return str(self.constant)

    def __eq__(self, other: 'DelayFunction') -> bool:
        assert isinstance(other, DelayFunction), f"Incompatible type '{type(other)}'!"
        return self.constant == other.constant and self.variables == other.variables

    def __len__(self) -> int:
        return len(self.variables)

    def __contains__(self, variable_name: str) -> bool:
        """
        Returns whether a variable with a given name exists in the term.
        """
        return variable_name in self.variables

    def __iter__(self) -> 'iterable':
        return self.variables.__iter__()

    def is_empty(self) -> bool:
        """
        Returns whether both the inner term and outer term are empty.
        """
        return self.constant == 0 and len(self.variables) == 0

    def is_static(self) -> bool:
        """
        Returns whether this function only consists of static variables (i.e. only the inner term).
        """
        return len(self.variables) == 0

    def names(self) -> 'iterable':
        """
        Returns an iterable of all variable names as they appear in order.
        """
        # assert len(self) == len(set(v.name for v in self))
        return self.variables.names()

    def count(self, variable_name: str) -> int:
        """
        Returns the magnitude of the variable `name`. If the variable does not exist 0 is returned.
        """
        return self.variables.count(variable_name)

    def merge_delay(self, value: int|float) -> Self:
        """
        Appends the variable to the static term of this function. Returns self for operator chaining.
        """
        assert isinstance(value, int|float), f"Incompatible type '{type(value)}'!"
        self.constant = max(self.constant, value)
        return self

    def add_coefficient(self, variable: DelayVariable) -> Self:
        """
        Appends the variable as a coefficient to this function. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(variable)}'!"
        assert variable.name != ''
        self.variables.append(variable)
        return self

    def plus(self, value: int|float) -> Self:
        """
        Adds `value` to the delay of static variable. Returns self for operator chaining.
        """
        assert isinstance(value, int|float), f"Incompatible type '{type(value)}'!"
        assert value >= 0, "only positive values are allowed"
        self.constant += value
        return self

    def copy(self) -> 'DelayFunction':
        """
        Returns a deep copy of this function.
        """
        copy = DelayFunction()
        copy.assign_to(self)
        return copy

    def assign_to(self, other: 'DelayFunction') -> Self:
        """
        Assigns this function to be the same as the other function.
        Useful, if a function should be modified in place.
        Returns self for operator chaining.
        """
        assert isinstance(other, DelayFunction), f"Incompatible type '{type(other)}'!"
        self.constant = other.constant
        self.variables = other.variables.copy()
        return self

    def remove(self, variable_name: str) -> Self:
        """
        Removes each instance of the variable from this term.
        Does nothing if no variable with given name exists in this term.
        Returns self for operator chaining.
        """
        self.variables.remove(variable_name)
        return self

    def resolve(self, variables: Dict[str, int|float] = None) -> Optional[int]:
        """
        Evaluates the function for the given values of the coefficients.
        """
        return self.constant + sum(variables[coeff.name] * coeff.delay for coeff in self.variables)

    # TODO remove
    def min_delay(self, static_value:int|float) -> Optional[int]:
        if len(self.variables) == 0:
            return self.constant
        min_delay = min(v.delay * static_value for v in self.variables)
        return self.constant + min_delay


class DelayExpression:

    __slots__ = ["functions"] # memory optimization
    
    def __init__(self, iterable=[DelayFunction()]):
        self.functions = iterable if isinstance(iterable, list) else [i for i in iterable]

    def __str__(self) -> str:
        return f"max({(',\n' + ' ' * (Print.indent + 4)).join(str(f) for f in self.functions)})"

    def to_str(self) -> str:
        """
        Returns a brief string representation of this expression in max-plus notation.
        """
        return f' + '.join(f.to_str() for f in self)

    def __repr__(self) -> str:
        return f"max({(',').join(repr(f) for f in self.functions)})"
        return self.__str__()

    def __iter__(self) -> 'iterable':
        return (f for f in self.functions)

    def __len__(self) -> int:
        return len(self.functions)

    def merge_delay(self, variable: int|float) -> Self:
        """
        Appends and merges the static variable. Returns self for operator chaining.
        """
        for function in self:
            function.merge_delay(variable)
        return self

    def add_coefficient(self, variable: DelayVariable) -> Self:
        """
        Appends the coefficient to each function. Returns self for operator chaining.
        """
        for function in self:
            function.add_coefficient(variable)
        return self

    def plus(self, value: int) -> Self:
        """
        Adds `value` to each function. Returns self for operator chaining.
        """
        for function in self:
            function.plus(value)
        return self

    def copy(self) -> 'DelayExpression':
        """
        Returns a deep copy of this object.
        """
        return DelayExpression(f.copy() for f in self)

    def resolve(self, variables: Dict[str, int|float] = None) -> Optional[int]:
        return max(f.resolve(variables) for f in self)

    def sort(self):
        self.functions.sort(key=lambda f: len(f))
        return self

    # delegate function
    def can_merge(*args):
        return DelayExpression.can_merge_v2(*args) # still fast and should not drop any terms of relevance (may keep some redundant terms?)
        #return DelayExpression.can_merge_v1(*args) # fastest for large BBs but may drop relevant terms?

    @staticmethod
    def merge(inputs, node_delay=0, symbolic_name=None) -> 'DelayExpression':
        result = next(inputs)
        if isinstance(result, int|float):
            result = DelayExpression([DelayFunction().merge_delay(result)])
        else:
            result = result.copy()

        # inputs
        updated = False
        for next_input in inputs:
            if isinstance(next_input, int|float):
                result.merge_delay(next_input)
                continue
            for next_function in next_input:
                new_term = DelayExpression.can_merge(next_function, result)
                if new_term is not None:
                    result.functions.append(new_term)
                    updated = True

        if updated:
            result.remove_redundant_terms()

        if symbolic_name is not None:
            result.add_coefficient(DelayVariable(symbolic_name, 1))
        elif node_delay > 0:
            result.plus(node_delay)
        return result.sort()

    def remove_redundant_terms(self) -> Self:
        changed = True
        # repeat as long as redundant terms are removed
        while changed:
            changed = False
            for idx, function in enumerate(self):
                others = self.functions[:idx] + self.functions[idx + 1:]
                if DelayExpression.can_merge(function, others) is None:
                    self.functions = others
                    changed = len(self) > 1
                    break

    @staticmethod
    def can_merge_v2(candidate: DelayFunction, others: List['DelayFunction']) -> bool:
        """
        Checks whether `candidate` is dominated by `others` by comparing magniutes of each variable.
        Returns new term if term is not dominated else None is returned.
        """
        for other in others:
            # dominates if all coeffictiens = 0
            if candidate.constant > other.constant:
                continue
            # no coefficient -> does not dominate with all coeffictiens = 0
            if candidate.is_static(): 
                return None
            # contains more vrialbes, must dominate
            if len(candidate.variables) > len(other.variables):
                continue
            # contains variables that are not in other or that are of higher magnitude
            if not all((v.name in other.variables and v.delay <= other.count(v.name)) for v in candidate.variables):
                # can reduce other by removing variables dominated by the candidate function
                if candidate.constant == other.constant:
                    for c in candidate.variables:
                        if other.count(c.name) <= c.delay:
                            other.remove(c.name)
                continue
            # all variables dominated by other
            return None
        # term dominates
        return candidate.copy()

    @staticmethod
    def can_merge_v1(candidate: DelayFunction, others: List['DelayFunction']) -> bool:
        """
        Checks whether `candidate` is dominated by `others` by checking all vertecies at the boundries of [0, upper]^n
        (dominance checking of picewise-linear max-plus function)
        Returns new term if term is not dominated else None is returned.
        """
        def assert_uniform_coefficients(candidate: DelayFunction, others: List['DelayFunction']) -> None:
            """
            Asserts that the approach is valid: All coefficients across `candidate` and `others` must be identical.
            """
            coeff_map: Dict[str, int] = {}
            for f in [candidate, *others]:
                for var in f:
                    if var.name not in coeff_map:
                        coeff_map[var.name] = var.delay
            for var in candidate:
                if coeff_map[var.name] != var.delay:
                    raise AssertionError(
                        f"Dominance checking may not be valid! " +
                        f"Candidate: {repr(candidate)} could be of relevance ({repr(others)})"
                    )

        # abort if any function is equal to candidate
        if any((candidate == other) for other in others):
            return None

        # TODO: make this variable externally!
        upper = 5

        others_names = { name for f in others for name in f.names() }

        # build the complete assignment upfront to safe on allocations
        assignment = { name: upper for name in candidate.names()    if name not in others_names } | \
                     { name: 0     for name in others_names         if name not in candidate }
        # shared variables
        shared_names = [ name for name in candidate.names() if name not in assignment ]
        # add shared variables
        assignment  |= { name: -1 for name in shared_names }

        for values in product((0, upper), repeat=len(shared_names)):
            # update in place
            for name, value in zip(shared_names, values):
                assignment[name] = value

            candidate_val = candidate.resolve(assignment)
            others_max    = max(f.resolve(assignment) for f in others)

            # found a vertex where candidate function is not dominated -> must append term
            if candidate_val > others_max:
                return candidate.copy()

        assert_uniform_coefficients(candidate, others)

        return None