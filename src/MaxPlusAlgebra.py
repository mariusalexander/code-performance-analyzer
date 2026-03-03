from itertools import chain
from typing import List, Dict, Optional, Self
import types
import copy

class DelayVariable:
    """ Represents a variable in a max term, associated with an added delay. """

    def __init__(self, name:str, delay:int=0):
        self.name  = name
        self.delay = delay

    def __str__(self):
        return f"{self.name}+{self.delay}"

    def __repr__(self):
        return self.__str__()

    def merged(self, delay:int) -> 'DelayVariable':
        return DelayVariable(self.name, self.delay + delay)

class MaxTerm(list):
    """ Represents a max term, made out of a list of variables. """

    def __init__(self, iterable_or_arg=None):
        if iterable_or_arg is None:
            iterable = []
        elif isinstance(iterable_or_arg, DelayVariable):
            iterable = (iterable_or_arg, )
        else:
            iterable = iterable_or_arg
        super().__init__(iterable)

    def __str__(self) -> str:
        return f"({", ".join(str(v) for v in self)})"

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other) -> bool:
        return len(self.names()) == len(other.names()) and all((v.name in other and other.max_delay(v.name) == v.delay) for v in self)

    def __contains__(self, value) -> bool:
        if isinstance(value, str):
            return any(v.name == value for v in self)
        assert isinstance(value, DelayVariable), f"Incompatible type '{type(value)}'!"
        return value.name in self

    def max_delay(self, name:str) -> Optional[int]:
        """
        Returns the maximum added delay of the variable `name`.
        """
        tmp = (v.delay for v in self if v.name == name)
        try:
            return max(tmp)
        except ValueError:
            return None

    def names(self) -> List[str]:
        """
        Returns a list of all variable names as they appear in order.
        """
        return list(dict.fromkeys(v.name for v in self)) # keeps order but removes duplicates

    def plus(self, value:int) -> Self:
        """ 
        Adds `value` to the delay of each variable. Returns self for operator chaining.
        """
        if value < 0:
            raise ValueError("Only positive values are expected")
        for v in self:
            v.delay += value
        return self

    def resolved(self, variable_name:str) -> 'MaxTerm':
        """
        Returns a new term in which the variable's delay is merged with all other variables by evaluating the max delay.
        """
        value = self.max_delay(variable_name)
        if value is None:
            value = 0
        new_term = MaxTerm(DelayVariable(v.name, max(v.delay, value)) for v in self if v.name != variable_name)
        return new_term

    def remove(self, variable_name:str) -> Self:
        """ 
        Removes each instance of the variable from this term. Does nothing if not variable with given name exists in this term.
        Returns self for operator chaining.
        """
        filtered = tuple(v for v in self if v.name == variable_name)
        if len(filtered) > 0:
            for var in filtered:
                super().remove(var)
        return self

    def replaced(self, variable_name:str, new_variable:'DelayVariable') -> 'MaxTerm':
        """
        Replaces all instances of `variable_name` with `new_variable.name` and merges the delays.
        Returns a new, simplified term.
        """
        new_term = MaxTerm(v if v.name != variable_name else new_variable.merged(v.delay) for v in self)
        return new_term.simplified()

    def difference(self, other:'MaxTerm') -> 'MaxTerm':
        """
        Returns a new term with only the variables that this term contains but `other` does not.
        Keeps order of names.
        """
        return MaxTerm(v for v in self if v.name not in other).simplified()

    def simplified(self) -> 'MaxTerm':
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Keeps order of names. Returns a new term.
        """
        return MaxTerm(DelayVariable(name, self.max_delay(name)) for name in self.names())

    def sort(self) -> Self:
        """
        Sorts the term in place by its delay (descending).
        For variables with same delay, alphabetical order is used.
        """
        super().sort(key=lambda v: (-v.delay, v.name))
        return self

    def distance(self, other:'MaxTerm') -> Optional[int]:
        """
        Attempts to find a linear dependency between `self` and `other`.
        For a linear dependency, all variables in `self` must be present in `other` with a consistent offset in their cofactors.
        This offset is called the distance. May return a negative distance, if `self` can be expressed by `other`.
        """
        # self cannot cover other if it has more variables
        if len(self) > len(other):
            return None
        distance = None
        for var in self:
            other_delay = other.max_delay(var.name)
            if other_delay is None:
                return None
            # calculate difference
            current = other_delay - var.delay
            # difference in delay is not linear
            if distance is not None and distance != current:
                return None
            distance = current
        return distance

    def expanded(self, intermediates:Dict[str, 'MaxTerm']) -> 'MaxTerm':
        """
        Expands (unrolls) all intermediate variables by their corresponding variables.
        Returns a new, simplified term.
        """
        if len(intermediates) == 0:
            return self.simplified()
        expanded = MaxTerm(chain((i.merged(v.delay) for v in self if v.name in intermediates for i in intermediates[v.name]), \
                                 (v                 for v in self if v.name not in intermediates)))
        assert all(i.name not in intermediates for i in expanded)
        return expanded.simplified()

    def repacked(self, intermediates:Dict[str, 'MaxTerm']) -> 'MaxTerm':
        """
        Attempts to find a new term, that reuses an intermediate variable to simplify the term.
        Returns a new, simplified, and sorted term.
        """
        if len(intermediates) == 0:
            return self.simplified().sort()
        expanded   = self.expanded(intermediates)
        best_match = expanded.find_best_intermediate(intermediates, expand=False)
        if best_match is None:
            return expanded # no need to simplify
        repacked = expanded.difference(intermediates[best_match.name])
        repacked.append(best_match)
        return repacked.sort()

    def find_best_intermediate(self, intermediates:Dict[str, 'MaxTerm'], expand=True, allow_negative_distance=False) -> Optional['DelayVariable']:
        """
        Attempts to find an intermediate variable that best covers `self` such that it yields the smallest term.
        `self` must be unrolled to find an intermediate.
        """
        this = self
        if expand: this = self.expanded(intermediates)

        last_name   = None
        last_factor = None
        last_len    = None
        for name in intermediates:
            term   = intermediates[name]
            factor = term.distance(this)
            if factor is None:
                continue
            curr_len = len(term)
            if factor < 0:
                # len must match if distance is negative
                if not allow_negative_distance or curr_len != len(this):
                    continue
            if last_name is not None:
                # prefer if variable covers more variables
                if curr_len < last_len:
                    continue
                # keep last variable if its scores a lower
                if curr_len == last_len and factor > last_factor:
                    continue
            last_name   = name
            last_factor = factor
            last_len    = curr_len
        if last_name is None:
            return None
        return DelayVariable(last_name, last_factor)

class MaxFunction:
    """ 
    Represents a max function, made from an inner term (variables with static delays) and an outer term (coefficients).
    The coefficients cannot be merged into the inner term since their delay is considered to be dynamic, variable, or symbolic 
    and thus the delay cannot be resolved yet.

    Example:
        max(<variables>) + <coefficients>
    """

    def __init__(self):
        # denoting inner term: max(a, b, c)
        self.static_vars    = MaxTerm()
        # denoting outer term: max(...) + a + b + c
        self.coefficients = MaxTerm()

    def __str__(self) -> str:
        if self.coefficients:
            return f"max{self.static_vars} + {str(self.coefficients).replace(',', ' +')[1:-1]}"
        return f"max{self.static_vars}"

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other) -> bool:
        assert isinstance(other, MaxFunction), f"Incompatible type '{type(value)}'!"
        return self.static_vars == other.static_vars and self.coefficients == other.coefficients

    def iter_all_vars(self):
        """ 
        Returns an generator that can be used to iterate over all variables, both static and the coefficients.
        """
        return chain(self.static_vars, self.coefficients)

    def is_empty(self) -> bool:
        """ 
        Returns whether both the inner term and outer term are empty.
        """
        return len(self.static_vars) == 0 and len(self.coefficients) == 0

    def is_static(self) -> bool:
        """ 
        Returns whether this function only consists of static variables (i.e. only the inner term).
        """
        return len(self.coefficients) == 0

    def is_covered_by(self, other) -> bool:
        """ 
        Returns whether this function is covered by the other function. A function 'A' covers another function 'B' if 
        1. all static variables in 'B' exist in 'A' and have an equal or higher delay associated (according to the max-operation) and
        2. all coefficients in 'A' also exist in 'B' and
        3. the sum of all coefficients in 'A' and their respective base-delay is equal or less than the sum of coefficients in 'B' 
           and their respective base-delay plus one - since each coefficient must be at least equal to one.
        Example for 3)
         other: max(2X, 1Y, 1Z) +  d1    + d2
         self:  max(2X, 1Y, 1Z) + (d1+1)
                                    ^ covered by other function since d2 is always at least 1
        """
        num_this_coefficients  = len(self.coefficients.names())
        num_other_coefficients = len(other.coefficients.names())
        offset = num_other_coefficients - num_this_coefficients
        return  all((v.name in other.static_vars and v.delay <= other.static_vars.max_delay(v.name)) for v in self.static_vars) \
            and all((v.name in other.coefficients) for v in self.coefficients) \
            and sum( v.delay for v in self.coefficients) <= sum(v.delay for v in other.coefficients) + offset \
            and offset >= 0

    def simplified(self) -> 'MaxFunction':
        """ 
        Returns a new function in which each static variable and each coefficient is listed exactly once. Keeps order of names.
        """
        copy = MaxFunction()
        copy.assign_to(self)
        return copy

    def assign_to(self, other:'MaxFunction') -> Self:
        """ 
        Assigns this function to be the same as the other function. A deepcopy is made by minimizing each term.
        Returns self for operator chaining.
        """
        self.static_vars  = other.static_vars.simplified()
        self.coefficients = other.coefficients.simplified()
        return self

    def plus(self, value:int) -> Self:
        """ 
        Adds `value` to the delay of each variable. Returns self for operator chaining.
        """
        if value < 0:
            raise ValueError("Only positive values are allowed")
        for v in (self.coefficients if len(self.coefficients) > 0 else self.static_vars):
            v.delay += value
        return self

    def sort(self) -> Self:
        """
        Sorts the inner and outer term in place by its base-delay (descending).
        For variables with same delay, alphabetical order is used.
        Returns self for operator chaining.
        """
        self.static_vars.sort()
        self.coefficients.sort()
        return self

    def append_static_var(self, variable:'DelayVariable') -> Self:
        """ 
        Appends the variable to the static term of this function. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(value)}'!"
        assert variable not in self.coefficients
        self.static_vars.append(variable)
        return self

    def append_coefficient(self, variable:'DelayVariable') -> Self:
        """ 
        Appends the variable as a coefficient to this function. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(value)}'!"
        assert variable not in self.static_vars
        self.coefficients.append(variable)
        return self

class MaxFunctionList(list):

    def __init__(self, iterable=None):
        super().__init__(iterable if iterable is not None else [])

    def plus(self, value:int) -> Self:
        """ 
        Adds `value` to each function. Returns self for operator chaining.
        """
        for function in self:
            function.plus(value)
        return self

    def sort(self) -> Self:
        """
        Sorts each function in place by its delay (descending).
        For variables with same delay, alphabetical order is used.
        All functions are then sorted by their number of static variables and coefficients.
        Returns self for operator chaining.
        """
        for function in self:
            function.sort()
        super().sort(key=lambda f: (len(f.static_vars), len(f.coefficients)))
        return self

    def merge(self, other_function:'MaxFunction') -> Self:
        """
        Merges the other function with the existing functions such that redundant functions are not appended and functions with redundant variables are minimized.
        Returns self for operator chaining.
        """
        theirs = other_function
        if theirs.is_empty():
            return self

        # check if other function covers any exisiting function or is covered
        for ours in self:
            if theirs.is_covered_by(ours):
                return self
            if ours.is_covered_by(theirs):
                # replace our term with theirs
                ours.assign_to(theirs)
                return self

        # attempt to merge other function
        for ours in self:
            static, dynamic = theirs if theirs.is_static() else ours, theirs if ours.is_static() else ours
            # both terns are static -> can merge inner terms
            if dynamic.is_static():
                ours.static_vars = MaxTerm(theirs.static_vars + ours.static_vars).simplified()
                return self
            # only one term is static
            # terms may partially cover each other -> remove redundant variables
            # example:
            #  Static:  max(3X, 2Y, 3Z, 1U)
            #  Dynamic: max(2X, 1Y, 1Z) + d1
            # yields:
            #  -> Static:  max(3Z, 1U)
            #  -> Dynamic: max(2X, 1Y, 1Z) + d1
            elif static.is_static():
                redundant = []
                # each coefficient must be at least equal to one
                num_coefficients = sum(v.delay + 1 for v in dynamic.coefficients)
                for v in static.static_vars:
                    max_delay = dynamic.static_vars.max_delay(v.name)
                    max_delay = (0 if max_delay is None else max_delay) + num_coefficients
                    if v.delay >= num_coefficients and v.delay <= max_delay:
                        redundant.append(v.name)
                if len(redundant) > 0:
                    assert len(redundant) != len(static.static_vars), \
                           f"unreachable condition: dynamic term '{dynamic}' should not cover static term '{static}'!"
                    # create copy of other function
                    if theirs is static:
                        static = theirs = theirs.simplified()
                    for name in redundant:
                        static.static_vars.remove(name)
                    self.append(theirs)
                    return self
            # both terms are dynamic
            else: 
                pass
        # cannot be merged -> append new function
        self.append(theirs.simplified())
        return self

    def append_static_var(self, variable:'DelayVariable') -> Self:
        """ 
        Appends and merges the static variable. Returns self for operator chaining.
        """
        functions = tuple(f for f in self if f.is_static())
        for function in functions:
            function.append_static_var(variable)
        # add new term if no static term is available
        if len(self) == 0 or len(functions) == 0:
            function = MaxFunction()
            function.append_static_var(variable)
            self.append(function)
        return self

    def append_coefficient(self, variable:'DelayVariable') -> Self:
        """ 
        Appends the coefficient to each function. Returns self for operator chaining.
        """
        for function in self:
            function.append_coefficient(variable)
        return self