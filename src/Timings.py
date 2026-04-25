import copy
from typing import List

from src.InstructionBlockDescription import InstructionDescription

from meta_models.scheduling_model.SchedulingModel import Variant as SchedVariant

class Timings:
    """ Data struct denoting timings of a schedule (i.e. values of timing variables and which registers are available). """

    # NOTE: corePerfDsl models that should be interpreted like register models have to be added here!
    __known_register_models = ["regModel", "clobberModel"]

    def __init__(self, sched_variant: 'SchedVariant'):
        # NOTE: assuming all pipeline stages are available (here -1 to indicates unset timing variables)
        # each timing variable has a "history" (depth of edges/stage's capacity)
        self.timing_vars      = { timing_var.name : [ -1 for _ in range(0, timing_var.getNumElements()) ] for timing_var in sched_variant.getAllTimingVariables() }
        # register models
        self.register_models  = { model.name : {} for model in sched_variant.getAllConnectorModels() if model.name in Timings.__known_register_models }
        # other connector models that are ignored (e.g. branch prediction)
        self.connector_models = { model.name : {} for model in sched_variant.getAllConnectorModels() if model.name not in Timings.__known_register_models }
    
    def copy(self):
        """ 
        Creates a deep copy of the current timings. 
        """
        return copy.deepcopy(self)

    def get_timing_var(self, timing_var: 'TimingVariable', depth: int):
        """
        Returns the value of the given timing variable for the given depth
        """
        assert depth > 0, f"Expected ingoing static edges to have a depth > 1 (actual depth: {depth})!"
        assert timing_var.name in self.timing_vars, f"Unknown timing variable '{timing_var.name}'!"
        assert len(self.timing_vars[timing_var.name]) >= depth, f"Ingoing static edge exceeds capacity of timing variable '{timing_var.name}'!"
        return self.timing_vars[timing_var.name][depth - 1]

    def update_timing_var(self, timing_var: 'TimingVariable', depth: int, node_delay: int|float):
        """
        Updates the value of the given timing variable for the given depth
        """
        assert depth == 1, f"Expected outgoing static edges to have a depth == 1 (actual depth: {depth})!"
        assert timing_var.name in self.timing_vars, f"Unknown timing variable '{timing_var.name}'!"
        # shift history of timing vars for edges with depth
        self.timing_vars[timing_var.name] = [node_delay] + self.timing_vars[timing_var.name][:-1]

    def get_connector(self, connector_model: 'ConnectorModel', connector_name: str, instr: 'InstructionDescription'):
        """
        Returns the value of the given connector. If the connector belongs the to a register model, the value of the corresponding register is returned.
        """
        # register model
        if connector_model.name in Timings.__known_register_models:
            register_model = self.register_models[connector_model.name]
            # get which register was used from instruction operands
            assert connector_name in instr, f"Instruction '{instr.name}' requires operand '{connector_name}'! (undefined)"
            register_no = instr[connector_name]
            if register_no not in register_model:
                # NOTE: assuming all registers are available
                return 0 # register was not set yet -> assume 0 delay -> no effect
            return register_model[register_no]

        # non-register connector model
        assert connector_model.name in self.connector_models, f"Unknown connector model '{connector_model.name}'!"
        model = self.connector_models[connector_model.name]
        if connector_name not in model:
            # NOTE: assuming all connectors are available
            return 0 # edge was not set yet -> assume 0 delay -> no effect
        return model[connector_name]

    def update_connector(self, connector_model: 'ConnectorModel', connector_name: str, instr: 'InstructionDescription', node_delay: int|float):
        """
        Updates the value of the given connector. If the connector belongs the to a register model, the value of the corresponding register is updated.
        """
        # register model
        if connector_model.name in Timings.__known_register_models:
            assert connector_name in instr, f"Instruction '{instr.name}' requires operand '{connector_name}'! (undefined)"
            register_no = instr[connector_name]
            self.register_models[connector_model.name][register_no] = node_delay
            return

        # non-register connector model
        # NOTE: to include branch taken/not taken, map outgoing edges to input edges (e.g. for staBranchPred: map 'Pc_np' to 'Pc')
        assert connector_model.name in self.connector_models, f"Unknown connector model '{connector_model.name}'!"
        self.connector_models[connector_model.name][connector_name] = node_delay
