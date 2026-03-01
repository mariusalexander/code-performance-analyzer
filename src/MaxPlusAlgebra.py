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
        if value < 0:
            raise ValueError("Only positive values are allowed")
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
        filtered = tuple(filter(lambda v: v.name == variable_name, self))
        if len(filtered) > 0:
            assert len(filtered) == 1
            super().remove(filtered[0])
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
        return MaxTerm(filter(lambda v: v.name not in other.names(), self)).simplified()

    def simplified(self) -> 'MaxTerm':
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Keeps order of names. Returns a new term.
        """
        return MaxTerm(DelayVariable(name, self.max_delay(name)) for name in self.names())

    def sorted(self) -> 'MaxTerm':
        """
        Returns a new term sorted by its delay (descending).
        For variables with same delay, alphabetical order is used.
        """
        return MaxTerm(sorted(self, key=lambda v: (-v.delay, v.name)))

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
        expanded = MaxTerm(chain((i.merged(v.delay) for v in self if v.name in intermediates for i in intermediates[v.name]), \
                                 (v                 for v in self if v.name not in intermediates)))
        assert all(i.name not in intermediates for i in expanded)
        return expanded.simplified()

    def repacked(self, intermediates:Dict[str, 'MaxTerm']) -> 'MaxTerm':
        """
        Attempts to find a new term, that reuses an intermediate variable to simplify the term.
        Returns a new, simplified, and sorted term.
        """
        expanded   = self.expanded(intermediates)
        best_match = expanded.find_best_intermediate(intermediates, expand=False)
        if best_match is None:
            return expanded # no need to simplify
        repacked = expanded.difference(intermediates[best_match.name])
        repacked.append(best_match)
        return repacked.sorted()

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
    Represents a max function, made from an inner term (variables) and an outer term (coefficients).
    Example:
        max(<variables>) + coefficients
    """

    def __init__(self):
        # denoting inner term: max(a, b, c)
        self.variables    = MaxTerm()
        # denoting outer term: max(...) + a + b + c
        self.coefficients = MaxTerm()

    def __str__(self):
        if self.coefficients:
            return f"max{self.variables} + {str(self.coefficients).replace(',', ' +')[1:-1]}"
        return f"max{self.variables}"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        assert isinstance(other, MaxFunction), f"Incompatible type '{type(value)}'!"
        return self.variables == other.variables and self.coefficients == other.coefficients

    def is_empty(self) -> bool:
        return len(self.variables) == 0 and len(self.coefficients) == 0

    def simplified(self):
        new = MaxFunction()
        new.assign_to(self)
        return new

    def iter_all_vars(self):
        return chain(self.variables, self.coefficients)

    def plus(self, value:int):
        if value < 0:
            raise ValueError("Only positive values are allowed")
        for v in self.coefficients if self.coefficients else self.variables:
            v.delay += value
        return self

    def assign_to(self, other:'MaxFunction'):
        self.variables    = other.variables.simplified()
        self.coefficients = other.coefficients.simplified()
        return self

    def is_covered_by(self, other):
        num_this_cofactors  = len(self.coefficients.names())
        num_other_cofactors = len(other.coefficients.names())
        # Each cofactor must be at least equal to one
        #  Other: max(2X, 1Y, 1Z) +  d1    + d2
        #  Self:  max(2X, 1Y, 0Z) + (d1+1)
        #                             ^ covered by other function since d2 is always at least 1
        offset = num_other_cofactors - num_this_cofactors

        return  all((v in other.variables and v.delay <= other.variables.max_delay(v.name)) for v in self.variables) \
            and all((v in other.coefficients) for v in self.coefficients) \
            and sum( v.delay for v in self.coefficients) <= sum(v.delay for v in other.coefficients) + offset \
            and offset >= 0

    def is_static(self) -> bool:
        return len(self.coefficients) == 0

    def append_static_var(self, variable:'DelayVariable'):
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(value)}'!"
        assert variable not in self.coefficients
        self.variables.append(variable)
        return self

    def append_dynamic_var(self, variable:'DelayVariable'):
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(value)}'!"
        assert variable not in self.variables
        self.coefficients.append(variable)
        return self


class MaxFunctionList(list):

    def __init__(self, iterable=None):
        super().__init__(iterable if iterable is not None else [])

    def append_static_var(self, variable:'DelayVariable'):
        print("# appending var:      ", variable.name)
        functions = tuple(f for f in self if f.is_static())
        for function in functions:
            function.append_static_var(variable)
        if len(self) == 0 or len(functions) == 0:
            function = MaxFunction()
            function.append_static_var(variable)
            self.append(function)

    def append_dynamic_var(self, variable:'DelayVariable'):
        print("# appending dynamic:  ", variable.name)
        for function in self:
            function.append_dynamic_var(variable)

    def plus(self, value:int):
        print("# adding:", value)
        for function in self:
            function.plus(value)

    def sort(self):
        for function in self:
            function.variables = function.variables.sorted()
            function.coefficients = function.coefficients.sorted()

    def merge(self, functions:types.GeneratorType):
        if not isinstance(functions, types.GeneratorType):
            raise TypeError("expected GeneratorType")

        mylen = len(self)
        new_functions = []
        for other in functions:
            if other.is_empty(): 
                print("# other is empty", other)
                continue
            handled = False
            for this in self:
                if other.is_covered_by(this):
                    print("# not appending:      ", other, "is covered by")
                    print("#                     ", this)
                    handled = True
                    break
                if this.is_covered_by(other):
                    print("# replacing term:     ", this, "is covered by")
                    print("#                     ", other)
                    this.assign_to(other)
                    handled = True
                    break
            if handled: continue

            for i in range(0, mylen):
                this = self[i]
                if other.is_static():
                    if this.is_static():
                        print("# merging static term:", this, "with")
                        print("#                     ", other)
                        this.variables = MaxTerm(other.variables + this.variables).simplified()
                        handled = True
                        continue
                    distance = this.variables.distance(other.variables)
                    assert distance is None or distance > 0
                    if distance == 1:
                        diff = other.variables.difference(this.variables)
                        if all(v.delay > 0 for v in diff):
                            print("# distance between:   ", this, "and")
                            print("#                     ", other, "=", distance)
                            this.variables += diff
                            handled = True
                            continue
                if this.is_static():
                    assert not other.is_static()
                    distance = other.variables.distance(this.variables)
                    assert distance is None or distance > 0
                    if distance == 1:
                        diff = this.variables.difference(other.variables)
                        if all(v.delay > 0 for v in diff):
                            print("# distance between /: ", other, "and")
                            print("#                     ", this, "=", distance)
                            this.assign_to(other)
                            this.variables += diff
                            handled = True
                        continue
            if handled: continue

            print("# appending term:     ", other)
            new_functions.append(other)

        for function in new_functions:
            self.append(function.simplified())