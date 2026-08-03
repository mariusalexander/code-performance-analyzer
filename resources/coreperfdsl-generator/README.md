# coreperfdsl-generator

### `generate_core_perf_dsl.py`

Generates CorePerfDSL files for a CV32E40P, similar to what the GenIE/XISAAC workflow generates. Each custom instruction is implemented using an I, X, and O stage.

**Signature:**

```bash
python3 generate_core_perf_dsl.py
    [-i A,B,C] [-ei EXPERIMENT_DIR] [-ev EXPERIMENT_DIR]
    [--auto-generate [MAX_DELAY]] [-n N_VARIANTS]
    [-t FILE] [--trace-template FILE]
    [--suffix SUFFIX] [--branch-pred-model BR_RPED_MODEL]
    [-O FILE] [-o FILE] [--output-trace FILE]
    [-p] [--print-coreperf] [--print-trace]
    [-h]
```

- `-h`: Help
- either use:
  - `-i`: Defines the custom instructions as a comma separated list, e.g. 0,1 becomes CUSTOM0,CUSTOM1.
  - `-ei`: Extract the custom instructions from a GenIE experiment. Useful, when defining custom latency vectors.
  - `-ev`: Extract the custom variants from a GenIE experiment, uses the latency defined for each variant and custom instruction.
- `--auto-generate`: Automatically generates sample latency vectors for each variant. Optional argument defines the maximum delay per stage.
- `-n`: Defines the maximum number of variants to generates.
- `-t`: Path to .corePerfDSL template file.
- `--trace-template`: Path to instruction trace JSON template file.
- `--suffix`: Optional suffix for each generated performance model.
- `--branch-pred-model`: Defines what branch prediction model the variants should use.
- either use:
  - `-O`: Output path. Generates both the .corePerfDSL and .json file for the given base file name.
  - `-o`/`--output_coreperf`: Output path for the .corePerfDSL only.
  - `-o`/`--output_trace`: Output path for the .json file only.
- `-p`: Prints the latency vector for each generated variant.
- `--print-coreperf`: Prints the resulting .corePerfDSL.
- `--print-trace`: Prints the resulting trace.json.

**Example Usage:**

Generate variants for the custom instructions CUSTOM1, CUSTOM3, and CUSTOM5:

```bash
python3 generate_core_perf_dsl.py -i 1,3,5 -O MY_CV32E40P -p
```

Extract instructions from an experiment, upto 100 variants:

```bash
EXPERIMENT=out/embench_iot/crc32/20260423T075325/
python3 generate_core_perf_dsl.py -ev $EXPERIMENT -n=100 --suffix=crc32 -O CV32E40P_CRC32 -p
```

Extract variants from an experiment:

```bash
EXPERIMENT=out/embench_iot/crc32/20260423T075325/
python3 generate_core_perf_dsl.py -ev $EXPERIMENT --suffix=crc32 -O CV32E40P_CRC32 -p
```

Extract variants from an experiment but use a dynamic branch prediction model:

```bash
EXPERIMENT=out/embench_iot/crc32/20260423T075325/
python3 generate_core_perf_dsl.py -ev $EXPERIMENT --branch-pred-model=dynBranchPredModel --suffix=crc32_dyn -O CV32E40P_CRC32_dyn -p
```

### `CV32E40PXISAAC.template`

Template .corePerfDSL file for a CV32E40P emplyoing **only** static delays.

### `CV32E40PXISAAC_dynamic_resources.template`

Template .corePerfDSL file for a CV32E40P emplyoing dynamic delays.

### `InstructionTrace_XISAAC.template`

Template instruction trace a CV32E40P.

### `CV32E40PXISAAC.ini`

Sample .ini file for ETISS. Need to define µArch and elf-file
