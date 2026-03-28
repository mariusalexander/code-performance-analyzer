from itertools import chain
from typing import List, Dict, Optional, Self

from src.Common import Print

class DelayVariable:
    """ Represents a variable in a max term, associated with an added delay. """

    def __init__(self, name:str, delay:int=0):
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
    """ Represents a abstract term, a list of variables. How these variables relate must be defined in the derived classes. """

    def __init__(self, iterable_or_arg=None):
        self.variables:List['DelayVariable'] = []
        if iterable_or_arg is None:
            return 
        if isinstance(iterable_or_arg, DelayVariable):
            self.append(iterable_or_arg)
            return 
        for var in iterable_or_arg:
            self.append(var)

    def __repr__(self) -> str:
        return self.__str__()

    def __contains__(self, variable_name) -> bool:
        """ 
        Returns whether a variable with a given name exists in the term. 
        """
        assert isinstance(variable_name, str), \
               f"Incompatible type '{type(variable_name)}', expected 'str'!"
        return any(v.name == variable_name for v in self)

    def __iter__(self) -> List['DelayGraph']:
        return self.variables.__iter__()

    def __len__(self) -> int:
        return len(self.variables)

    def __add__(self, other) -> Self:
        for var in other:
            self.append(var)
        return self

    def names(self) -> List[str]:
        """
        Returns a list of all variable names as they appear in order.
        """
        return list(dict.fromkeys(v.name for v in self)) # keeps order but removes duplicates

    def sort(self) -> Self:
        """
        Sorts the term in place by its delay (descending).
        For variables with same delay, alphabetical order is used.
        """
        self.variables.sort(key=lambda v: (-v.delay, v.name))
        return self

    def remove(self, variable_name:str) -> Self:
        """ 
        Removes each instance of the variable from this term. 
        Does nothing if no variable with given name exists in this term.
        Returns self for operator chaining.
        """
        filtered = tuple(v for v in self if v.name == variable_name)
        if len(filtered) > 0:
            for var in filtered:
                self.variables.remove(var)
        return self

    def copy(self) -> Self:
        """
        Returns a copy of this term.
        """
        return self.__class__(v.copy() for v in self)

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

    def append(self, variable:'DelayVariable') -> Self:
        """
        Appends the variable to the term. The delay must be positive.
        Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), \
               f"Incompatible type '{type(variable)}', expected {type(DelayVariable)}'!"
        assert variable.delay >= 0
        self.variables.append(variable)
        return self

    def max_delay(self, variable_name:str) -> Optional[int]:
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
        return f"{" + ".join(f"{v.delay}*{v.name}" for v in self)}"

    def __eq__(self, other) -> bool:
        """ 
        Returns whether two terms are equal. 
        """
        assert isinstance(other, PlusTerm), \
               f"Incompatible type '{type(other)}', expected '{type(self)}'!"
        return all((name in other and other.count(name) == self.count(name)) for name in self.names())

    def append(self, variable:'DelayVariable') -> Self:
        """
        Appends the variable to the term. The delay must be positive.
        Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), \
               f"Incompatible type '{type(value)}', expected {type(DelayVariable)}'!"
        variable.delay = max(variable.delay, 1)
        # update value if variable already exists
        for var in self:
            if var.name == variable.name:
                var.add(variable.delay)
                return self
        # else add variable
        self.variables.append(variable)
        return self

    def count(self, variable_name:str) -> int:
        """
        Returns the magnitude of the variable `name`. If the variable does not exist 0 is returned.
        """
        assert isinstance(variable_name, str), \
               f"Incompatible type '{type(variable_name)}', expected 'str'!"
        assert all(v.delay > 0 for v in self)
        return sum(v.delay for v in self if v.name == variable_name)

    def simplified(self) -> 'PlusTerm':
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Keeps order of names. Returns a new term.
        """
        return PlusTerm(DelayVariable(name, self.count(name)) for name in self.names())

class DelayFunction:
    """ 
    Represents a delay function, made from an inner term (variables with static delays) and an outer term (coefficients).
    The coefficients cannot be added into the inner term since their delay is considered to be dynamic, variable, or symbolic 
    and thus the delay cannot be resolved yet.

    Example:
        max(<variables>) + <coefficients>
    """

    def __init__(self):
        # denoting inner term: max(a+3, b+2, c+1)
        self.static_vars  = MaxTerm()
        # denoting outer term: max(...) + 3d + 2e + 1f
        self.coefficients = PlusTerm()

    def __str__(self) -> str:
        return str(self.static_vars) + (f" + {self.coefficients}" if len(self.coefficients) > 0 else "")

    def __eq__(self, other) -> bool:
        return self.static_vars == other.static_vars and self.coefficients == other.coefficients

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
        Returns whether this function is covered by the other function. 
        """
        names = self.coefficients.names()
        if not all((name in other.coefficients and self.coefficients.count(name) <= other.coefficients.count(name)) for name in names):
            return False
        
        offset = sum(other.coefficients.count(name) for name in other.coefficients.names()) - sum(self.coefficients.count(name) for name in names)
        assert offset >= 0
        return all((name in other.static_vars and self.static_vars.max_delay(name) <= other.static_vars.max_delay(name) + offset) for name in self.static_vars.names())

    def iter_static_vars(self) -> 'MaxTerm.__iter__':
        return self.static_vars.__iter__()

    def iter_coefficients(self) -> 'PlusTerm.__iter__':
        return self.coefficients.__iter__()

    def append_static_var(self, variable:'DelayVariable') -> Self:
        """ 
        Appends the variable to the static term of this function. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(value)}'!"
        assert variable.name not in self.coefficients
        self.static_vars.append(variable)
        return self

    def append_coefficient(self, variable:'DelayVariable') -> Self:
        """ 
        Appends the variable as a coefficient to this function. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(value)}'!"
        assert variable.name not in self.static_vars
        self.coefficients.append(variable)
        return self

    def max_delay(self, variable_name:str) -> Optional[int]:
        """
        Returns the maximum delay of the variable `name`.
        """
        delay  = self.static_vars.max_delay(variable_name)
        offset = self.coefficients.count(variable_name)
        if delay is not None:
            if offset is None:
                return delay
            return delay + offset
        return offset

    def plus(self, value:int) -> Self:
        """ 
        Adds `value` to the delay of static variable. Returns self for operator chaining.
        """
        if value < 0:
            raise ValueError("Only positive values are allowed")
        assert len(self.static_vars) > 0
        self.static_vars.plus(value)
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

    def copy(self) -> 'DelayFunction':
        """ 
        Returns a deep copy of this function.
        """
        copy = DelayFunction()
        copy.assign_to(self)
        return copy

    def assign_to(self, other:'DelayFunction') -> Self:
        """ 
        Assigns this function to be the same as the other function.
        Useful, if a function should be modified in place.
        Returns self for operator chaining.
        """
        self.static_vars  = other.static_vars.copy()
        self.coefficients = other.coefficients.copy()
        return self

    def simplified(self) -> 'DelayFunction':
        """ 
        Returns a new function in which each term is minimized by listing 
        each variable exactly once. Keeps order of names.
        """
        copy = self.copy()
        copy.static_vars  = copy.static_vars.simplified()
        copy.coefficients = copy.coefficients.simplified()
        return copy

    def replace(self, variables:Dict[str, 'DelayVariable']) -> Self:
        for var_name, new_var in variables.items():
            for var in self.static_vars:
                if var.name == var_name:
                    var.name  = new_var.name
                    var.add(new_var.delay)
            for var in self.coefficients:
                if var.name == var_name:
                    assert new_var.delay > 0
                    var.name   = new_var.name
                    var.delay *= new_var.delay
        
        offset = self.coefficients.count(variable_name="")
        if offset is not None:
            self.coefficients.remove(variable_name="")
            self.plus(offset)
        return self

    def evaluate(self) -> Optional[int]:
        """ 
        Attempts to evaluate this function. Must contain no coefficients and only be made up of null delay variables.
        """
        names = self.coefficients.names()
        if len(names) != 0 and [''] != names:
            raise RuntimeError(f"Function '{self}' contains unresolved coefficients: {", ".join(name for name in names if len(name) > 0)}")
        offset = self.coefficients.count(variable_name='')
        names  = self.static_vars.names()
        if [''] != names:
            raise RuntimeError(f"Function '{self}' contains unresolved delays: {", ".join(name for name in names if len(name) > 0)}")
        value = self.static_vars.max_delay(variable_name='')
        assert value is not None
        return value + offset

    def merge(self, theirs) -> bool:
        assert isinstance(theirs, DelayFunction), f"Incompatible type '{type(value)}'!"
        if theirs.is_empty():
            return 1

        # check if other function covers any exisiting function or is covered
        ours = self
        if theirs.is_covered_by(ours):
            return 1
        if ours.is_covered_by(theirs):
            # replace our term with theirs
            ours.assign_to(theirs)
            return 1

        # attempt to merge other function
        static, dynamic = theirs if theirs.is_static() else ours, theirs if ours.is_static() else ours
        # both terns are static -> can merge inner terms
        if dynamic.is_static():
            ours.static_vars = MaxTerm(theirs.static_vars + ours.static_vars).simplified()
            return 1
        # only one term is static
        # terms may partially cover each other -> remove redundant variables
        # example:
        #  Static:  max(3X, 2Y, 3Z, 1U)
        #  Dynamic: max(2X, 1Y, 1Z) + d1
        # yields:
        #  -> Static:  max(3Z, 1U)
        #  -> Dynamic: max(2X, 1Y, 1Z) + d1
        if static.is_static():
            redundant = []
            # each coefficient must be at least equal to one
            num_coefficients = sum(v.delay for v in dynamic.coefficients.simplified())
            for v in (v for v in static.static_vars if v.name in dynamic.static_vars):
                max_delay = dynamic.static_vars.max_delay(v.name) + num_coefficients
                if v.delay <= max_delay:
                    redundant.append(v.name)
            if len(redundant) == 0:
                return 0
            #assert len(redundant) < len(static.static_vars), \
            #       f"unreachable condition: term '{dynamic}' should not cover term '{static}'!"
            # create copy of other function
            if theirs is static:
                static = theirs = theirs.copy()
            for name in redundant:
                static.static_vars.remove(name)
            return 2
        # both terms are dynamic
        return 0 

class DelayFunction_v2:

    def __init__(self):
        self.static_delay = 0
        # denoting outer term: max(...) + 3d + 2e + 1f
        self.coefficients = PlusTerm()

    def __str__(self) -> str:
        if len(self.coefficients):
            return f"{self.static_delay} + {self.coefficients}"
        return str(self.static_delay)

    def __eq__(self, other) -> bool:
        return self.static_delay == other.static_delay and self.coefficients == other.coefficients

    def is_empty(self) -> bool:
        """ 
        Returns whether both the inner term and outer term are empty.
        """
        return self.static_delay == 0 and len(self.coefficients) == 0

    def is_static(self) -> bool:
        """ 
        Returns whether this function only consists of static variables (i.e. only the inner term).
        """
        return len(self.coefficients) == 0

    def is_covered_by(self, other) -> bool:
        # max(4 + 3A + 2B)
        # max(6 + 2A + 1B)
        if not all((v.name in other.coefficients and self.coefficients.count(v.name) <= other.coefficients.count(v.name)) for v in self.coefficients):
            return False
        
        offset = sum(v.delay for v in other.coefficients) - sum(v.delay for v in self.coefficients)
        assert offset >= 0
        return  self.static_delay <= (other.static_delay + offset)
            
    def iter_static_vars(self) -> 'iterator':
        return iter(())

    def iter_coefficients(self) -> 'iterator':
        return self.coefficients.__iter__()

    def append_static_var(self, variable:'DelayVariable') -> Self:
        """ 
        Appends the variable to the static term of this function. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(value)}'!"
        assert variable.name == '', variable.name
        self.static_delay = max(self.static_delay, variable.delay)
        return self

    def append_coefficient(self, variable:'DelayVariable') -> Self:
        """ 
        Appends the variable as a coefficient to this function. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(value)}'!"
        assert variable.name != ''
        self.coefficients.append(variable)
        return self

    def plus(self, value:int) -> Self:
        """ 
        Adds `value` to the delay of static variable. Returns self for operator chaining.
        """
        assert value >= 0, "only positive values are allowed"
        self.static_delay += value
        return self

    def sort(self) -> Self:
        """
        Sorts the inner and outer term in place by its base-delay (descending).
        For variables with same delay, alphabetical order is used.
        Returns self for operator chaining.
        """
        self.coefficients.sort()
        return self

    def copy(self) -> 'DelayFunction_v2':
        """ 
        Returns a deep copy of this function.
        """
        copy = DelayFunction_v2()
        copy.assign_to(self)
        return copy

    def assign_to(self, other:'DelayFunction_v2') -> Self:
        """ 
        Assigns this function to be the same as the other function.
        Useful, if a function should be modified in place.
        Returns self for operator chaining.
        """
        self.static_delay = other.static_delay
        self.coefficients = other.coefficients.copy()
        return self

    def simplified(self) -> 'DelayFunction_v2':
        """ 
        Returns a new function in which each term is minimized by listing 
        each variable exactly once. Keeps order of names.
        """
        copy = DelayFunction_v2()
        copy.static_delay = self.static_delay
        copy.coefficients = self.coefficients.simplified()
        return copy

    def replace(self, variables:Dict[str, 'DelayVariable']) -> Self:
        for var_name, new_var in variables.items():
            for var in self.coefficients:
                if var.name == var_name:
                    assert new_var.delay > 0
                    var.name   = new_var.name
                    var.delay *= new_var.delay
        
        offset = self.coefficients.count(variable_name="")
        if offset is not None:
            self.coefficients.remove(variable_name="")
            self.plus(offset)
        return self

    def evaluate(self) -> Optional[int]:
        """ 
        Attempts to evaluate this function. Must contain no coefficients and only be made up of null delay variables.
        """
        names = self.coefficients.names()
        assert len(self.coefficients) == len(names)
        if len(names) != 0 and [''] != names:
            raise RuntimeError(f"Function '{self}' contains unresolved coefficients: {", ".join(name for name in names if len(name) > 0)}")
        offset = self.coefficients.count(variable_name='')
        value  = self.static_delay
        return value + offset

    def merge(self, theirs) -> bool:
        assert isinstance(theirs, DelayFunction_v2), f"Incompatible type '{type(value)}'!"
        if theirs.is_empty():
            return 1

        # check if other function covers any exisiting function or is covered
        ours = self
        if theirs.is_covered_by(ours):
            return 1
        if ours.is_covered_by(theirs):
            # replace our term with theirs
            ours.assign_to(theirs)
            return 1

        return 0 


class DelayFunctionList(list):
    use_v2 = False

    def __init__(self, iterable=None):
        super().__init__(iterable if iterable is not None else [])

    def __str__(self) -> str:
        return f"max(" + (f",\n" + " " * Print.indent).join(str(f) for f in self) + ")"

    def __repr__(self) -> str:
        return self.__str__()

    def append_static_var(self, variable:'DelayVariable') -> Self:
        """ 
        Appends and merges the static variable. Returns self for operator chaining.
        """
        functions = tuple(f for f in self if f.is_static())
        for function in functions:
            function.append_static_var(variable)
        # add new term if no static term is available
        if len(self) == 0 or len(functions) == 0:
            function = DelayFunction() if not DelayFunctionList.use_v2 else DelayFunction_v2()
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
        super().sort(key=lambda f: (len(f.static_vars), len(f.coefficients)) if not DelayFunctionList.use_v2 else (f.static_delay, len(f.coefficients))) 
        return self

    def copy(self) -> 'DelayFunction':
        """ 
        Returns a deep copy of this object.
        """
        return DelayFunctionList(f.copy() for f in self)

    def simplified(self) -> 'DelayFunctionList':
        copy = DelayFunctionList()
        for function in self:
            function = function.simplified()
            copy.merge(function)
        return copy

    def replace(self, variables:Dict[str, 'DelayVariable']) -> Self:
        for function in self:
            function.replace(variables)
        return self

    def evaluate(self) -> Optional[int]:
        return max(f.evaluate() for f in self)

    def merge(self, other_function:'DelayFunction') -> Self:
        """
        Merges the other function with the existing functions such that redundant functions are not appended and functions with redundant variables are minimized.
        Returns self for operator chaining.
        """
        for function in self:
            result = function.merge(other_function)
            match result:
                case 1:
                    return self
                case 2:
                    self.append(other_function)
                    return self
                case _:
                    continue
        # cannot be added -> append new function
        self.append(other_function.copy())
        return self
