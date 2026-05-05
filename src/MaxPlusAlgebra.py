import math
import atexit
from objprint import op, objstr
from itertools import chain, product
from typing import List, Dict, Optional, Self

from src.Common import Print, Profile

do_print=False #True
do_print_detail=False

symbolic_variable_names = {}

def get_var_name(name):
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
    """ Represents a abstract term, a list of variables. How these variables relate must be defined in the derived classes. """

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
        Returns a list of all variable names as they appear in order.
        """
        return (v.name for v in self) # keeps order but removes duplicates

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
        Appends the variable to the term. The delay must be positive.
        Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), \
               f"Incompatible type '{type(variable)}', expected {type(DelayVariable)}'!"
        assert variable.delay >= 0
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
        return all((name in other and other.count(name) == self.count(name)) for name in self.names())

    def append(self, variable: DelayVariable) -> Self:
        """
        Appends the variable to the term. The delay must be positive.
        Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), \
               f"Incompatible type '{type(value)}', expected {type(DelayVariable)}'!"
        assert variable.delay > 0, "Variables in a plus term must have postive values > 0!"
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

    def simplified(self) -> 'PlusTerm':
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Keeps order of names. Returns a new term.
        """
        return PlusTerm(DelayVariable(name, self.count(name)) for name in self.names())


class DelayFunction:

    __slots__ = ["static_delay", "coefficients"]

    def __init__(self):
        self.static_delay = 0
        self.coefficients = PlusTerm()

    def __str__(self) -> str:
        if len(self.coefficients):
            return f"{self.static_delay} + {self.coefficients}"
        return str(self.static_delay)

    def to_str(self) -> str:
        """
        Returns a brief string representation of this function in max-plus notation.
        """
        if len(self.coefficients):
            return f"{self.static_delay}*{self.coefficients.to_str()}"
        return str(self.static_delay)

    def __eq__(self, other: 'DelayFunction') -> bool:
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

    def merge_delay(self, value: int|float) -> Self:
        """
        Appends the variable to the static term of this function. Returns self for operator chaining.
        """
        self.static_delay = max(self.static_delay, value)
        return self

    def add_coefficient(self, variable: DelayVariable) -> Self:
        """
        Appends the variable as a coefficient to this function. Returns self for operator chaining.
        """
        assert isinstance(variable, DelayVariable), f"Incompatible type '{type(variable)}'!"
        assert variable.name != ''
        self.coefficients.append(variable)
        return self

    def plus(self, value: int) -> Self:
        """
        Adds `value` to the delay of static variable. Returns self for operator chaining.
        """
        assert value >= 0, "only positive values are allowed"
        self.static_delay += value
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
        self.static_delay = other.static_delay
        self.coefficients = other.coefficients.copy()
        return self

    def resolve(self, variables: Dict[str, int|float]) -> Optional[int]:
        """
        Evaluates the function for the given values of the coefficients.
        """
        return self.static_delay + sum(variables[coeff.name] * coeff.delay for coeff in self.coefficients)

    # TODO remove
    def min_delay(self, static_value) -> Optional[int]:
        if len(self.coefficients) == 0:
            return self.static_delay
        min_delay = min(v.delay * static_value for v in self.coefficients)
        return self.static_delay + min_delay


class DelayExpression:

    __slots__ = ["functions"] # memory optimization

    max_symbolic_delay = 3
    
    def __init__(self, iterable=[DelayFunction()]):
        self.functions = iterable if isinstance(iterable, list) else [i for i in iterable]

    def __str__(self) -> str:
        return f"max({(',' + ' ' * 0 * (Print.indent + 4)).join(str(f) for f in self.functions)})"

    def to_str(self) -> str:
        """
        Returns a brief string representation of this expression in max-plus notation.
        """
        return f' + '.join(f.to_str() for f in self)

    def __repr__(self) -> str:
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

    def resolve(self, variables: Dict[str, int|float]) -> Optional[int]:
        return max(f.resolve(variables) for f in self)

    def sort(self):
        self.functions.sort(key=lambda f: len(f.coefficients))
        return self

    @staticmethod
    def is_covered_by(candidate: DelayFunction, others: List['DelayFunction'], others_names) -> bool:
        """
        Returns whether `candidate` is dominated by `others` by checking all critical vertecies over [0, upper]^n
        (dominance checking of picewise-linear-max-plus function over bounded domain)
        """
        upper = DelayExpression.max_symbolic_delay
        
        # build the complete assignment upfront to safe on allocations
        assignment = { name: upper for name in candidate.coefficients.names()    if name not in others_names } | \
                     { name: 0     for name in others_names                      if name not in candidate.coefficients }
        # shared variables
        shared_names = [ name for name in candidate.coefficients.names() if name not in assignment ]
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
                return False

        return True

    @staticmethod
    def merge_v2(inputs, node_delay, symbolic_name=None) -> 'DelayExpression':
        result = next(inputs)

        if isinstance(result, int|float):
            result = DelayExpression([DelayFunction().merge_delay(result)])
        else:
            result = result.copy()

        # Collect variable sets
        others_names = { name for f in result for name in f.coefficients.names() }

        # inputs
        updated = False
        for next_input in inputs:
            if isinstance(next_input, int|float):
                if do_print_detail:
                    print("$ merging delay", next_input, "with", result)
                result.merge_delay(next_input)
                continue
            for next_function in next_input:
                if DelayExpression.is_covered_by(next_function, result, others_names):
                    continue
                if do_print_detail:
                    print("$ appending", next_function, "to", result)
                result.functions.append(next_function.copy())
                others_names.update(next_function.coefficients.names())
                updated = True
        
        if updated:
            changed = True
            while changed:
                changed = False
                for idx, function in enumerate(result):
                    others = result.functions[:idx] + result.functions[idx + 1:]
                    others_names = { name for f in others for name in f.coefficients.names() }
                    if DelayExpression.is_covered_by(function, others, others_names):
                        if do_print_detail:
                            print("$ removing", function, "from", result)
                        result.functions = others
                        changed = len(result) > 1
                        break

        if symbolic_name is not None:
            result.add_coefficient(DelayVariable(symbolic_name, 1))
        elif node_delay > 0:
            result.plus(node_delay)
        
        return result


class DelayExpression_v2:

    __slots__ = ["instances"] # memory optimization

    def __init__(self, iterable=[]):
        self.instances = {}
        for i in iterable:
            self.merge(i)
        self.merge(DelayFunction())

    def __str__(self) -> str:
        return f"max({(',\n' + ' ' * (Print.indent + 4)).join(str(f) for f in self)})"

    def to_str(self) -> str:
        """
        Returns a brief string representation of this expression in max-plus notation.
        """
        return f' + '.join(f.to_str() for f in self)

    def __repr__(self) -> str:
        return self.__str__()

    def __iter__(self) -> 'iterable':
        return (f for functions in self.instances.values() for f in functions)

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def merge_delay(self, variable: int|float) -> Self:
        """
        Appends and merges the static variable. Returns self for operator chaining.
        """
        if do_print:
            print("  max", variable)
        functions = (f for f in self if f.is_static())
        done = False
        for function in functions:
            function.merge_delay(variable)
            done = True
        # add new term if no static term is available
        if len(self) == 0 or not done:
            function = DelayFunction()
            function.merge_delay(variable)
            return self.merge(function)
        return self

    def add_coefficient(self, variable: DelayVariable) -> Self:
        """
        Appends the coefficient to each function. Returns self for operator chaining.
        """
        if do_print:
            print(f"   add ({variable.delay} * {variable.delay})")
        for function in self:
            function.add_coefficient(variable)
        return self

    def plus(self, value: int) -> Self:
        """
        Adds `value` to each function. Returns self for operator chaining.
        """
        if do_print:
            print(" plus", value)
        for function in self:
            function.plus(value)
        return self

    def copy(self) -> 'DelayExpression_v2':
        """
        Returns a deep copy of this object.
        """
        return DelayExpression_v2(f.copy() for f in self)

    def resolve(self, variables: Dict[str, int|float]) -> Optional[int]:
        return max(f.resolve(variables) for f in self)

    def merge(self, other_function: DelayFunction) -> Self:
        """
        Merges the other function with the existing functions such that redundant functions are not appended and functions with redundant variables are minimized.
        Returns self for operator chaining.
        """
        assert isinstance(other_function, DelayFunction), f"Incompatible type '{type(value)}'!"

        if do_print and not do_print_detail:
            print("merge", other_function)
        if do_print_detail:
            print(f"MERGING... '{other_function}'")
            op(self)

        instances = len(self.instances)
        if instances == 0:
            self.instances[0] = [other_function.copy()]
            if do_print_detail:
                their_min_value   = other_function.min_delay(0)
                print(f"{0:>2} ->", their_min_value, "appended\n")
            return self

        def check_merging(function, other_function):
            their_min_value = other_function.min_delay(instance)
            this_min_value  = function.min_delay(instance)
            if do_print_detail:
                max_len = max(7, len(str(function)), len(str(other_function)))
                print(f"{instance:>2} ->", str(this_min_value).ljust(max_len-5), "\tvs.\t", str(their_min_value).ljust(max_len))
            return their_min_value - this_min_value

        merged_at = set()
        merged = False
        for instance, functions in self.instances.items():
            for function in functions:
                covered_by_them   = all((v.name in other_function.coefficients
                                        and function.coefficients.count(v.name) <= other_function.coefficients.count(v.name)
                                        ) for v in function.coefficients)
                covered_by_us     = all((v.name in function.coefficients
                                        and other_function.coefficients.count(v.name) <= function.coefficients.count(v.name)
                                        ) for v in other_function.coefficients)

                value = check_merging(function, other_function)
                if do_print_detail:
                    print("do we cover their coefficients?", covered_by_us)
                    print("do they cover our coefficients?", covered_by_them)

                if value < 0:
                    if covered_by_us:
                        if do_print_detail:
                            print("covering theirs   - idx", instance, "\n")
                        return
                    continue
                if value > 0:
                    if covered_by_them:
                        if merged:
                            if do_print_detail:
                                print("removing this   - idx", instance)
                            function.assign_to(DelayFunction())
                            merged_at.add(instance)
                            continue
                        if do_print_detail:
                            print("assigning this   - idx", instance)
                        function.assign_to(other_function)
                        merged = True
                        merged_at.add(instance)
                    continue

                if covered_by_us:
                    if do_print_detail:
                        print("discarding theirs - idx", instance, f"({value})" "\n")
                    return
                # if covered_by_them:
                #     if do_print_detail:
                #         print("discarding ours   - idx", instance, f"({value})" "\n")
                #     function.assign_to(other_function)
                #     merged = True
                #     merged_at.add(instance)

        if merged:
            for pos in merged_at:
                self.instances[pos] = [f for f in self.instances[pos] if not f.is_empty()]
            return

        if covered_by_them:
            this_min_value  = function.min_delay(instance)
            their_min_value = other_function.min_delay(instance)
            factor          = other_function.min_delay(instance+1) - their_min_value
            new_instance    = math.ceil((this_min_value - their_min_value + 1) / factor)
            if do_print_detail:
                their_min_value = other_function.min_delay(new_instance)
                print(f"{new_instance:>2} ->", their_min_value, "appended (1)\n", "HERE", factor)
        else:
            new_instance    = instance
            if do_print_detail:
                their_min_value = other_function.min_delay(new_instance)
                print(f"{new_instance:>2} ->", their_min_value, "appended (2)\n")

        assert new_instance >= 0
        if new_instance not in self.instances:
            self.instances[new_instance] = []

        self.instances[new_instance] += [other_function.copy()]
        return self
