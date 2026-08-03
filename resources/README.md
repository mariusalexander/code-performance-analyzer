# Other Resources

Here, other resources are saved that are not necessary for this code-project but were used to compile or extract results.

### `coreperfdsl-generator/`

Resources for generating .corePerfDSL files based on the XISAAC-Variant of a CV32E40P-core.

### `performance-sim`

Custom resources using in performance simulations.

### `normalize_choices.py`

Extracts basic blocks for the CPI prediction from traces generated in the GenIE/XISAAC workflow.

**Signature:**

```bash
python3 normalize_choices.py <path-to-experiment> [-h] [-x] [-p] [-c] [-o OUT_DIR]
```

- `-h`: Help
- `-p`: Prints the results (experiment.json)
- `-c`: Copy .corePerfDSL file if it exists.
- `-x`: Extracts basic blocks from `sess_new_filtered_selected` instead of `sess` (i.e. basic blocks with custom instructions)
- `-o`: Output directory. Generates the following directory structure:
    - `<bench>/<timestamp>/...`        for basic blocks without custom instructions
    - `<bench>/<timestamp>/xisaac/...` for basic blocks with custom instructions (when using `-x`)

**Example Usage:**

> **Note:** requires venv of xisaac-workspace to run

```bash
EXPERIMENT=out/embench_iot/crc32/20260423T075325/
python3 normalize_choices.py $EXPERIMENT -x -p -c -o=exports/
```

The CPI-analysis can then be executed using:

```bash
BENCH=exports/crc32/20260423T075325
PYTHONPATH=<path-to-m2isar-perf>/m2isar_perf/ python3 ./main.py <path/to/dump_dir> --files $BENCH/xisaac/experiment.json --cores="*" --cpi --rank
```

Symbolic analysis of all custom instructions:

```bash
BENCH=exports/crc32/20260423T075325
PYTHONPATH=<path-to-m2isar-perf>/m2isar_perf/ python3 ./main.py <path/to/dump_dir> --files $BENCH/xisaac/experiment.json --cores="*V0" --cpi --rank --sym=CUSTOM
```

> **Note:** CorePerfDSL-model must be exported (dumped) using M2-ISA-R-Perf - both the structural model and scheduling model!
