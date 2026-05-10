# Other Resources

Here, other resources are saved that are not necessary for this code-project but were used to compile or extract results.

### `normalize_choices.py`

Extracts basic blocks for the CPI prediction from traces generated in the GenIE/XISAAC workflow.

**Signature:**

```bash
python3 normalize_choices.py <path-to-experiment> [-h] [-x] [-p] [-o OUT_DIR]
```

- `-h`: Help
- `-p`: Prints the results (experiment.json)
- `-x`: Extracts basic blocks from `sess_new_filtered_selected` instead of `sess` (i.e. basic blocks with custom instructions)
- `-o`: Output directory. Generates the necessary scaffolding:
    - `<bench>/<timestamp>/...`        for basic blocks without custom instructions
    - `<bench>/<timestamp>/xisaac/...` for basic blocks with custom instructions (when using `-x`)

**Example Usage:**

```bash
python3 normalize_choices.py out/embench_iot/crc32/20260423T075325/ -x -p -o=exports/
```

The CPI-analysis can then be executed using

```bash
BENCH=exports/crc32/20260423T075325/xisaac
PYTHONPATH=<path-to-m2isar-perf>/m2isar_perf/ python3 ./main.py <path-to-pickled-models> --files $BENCH/xisaac/experiment.json --cores="*" --cpi --rank
```

> **Note:** CorePerfDsl-model must be exported (dumped) using M2-ISA-R-Perf - both the structural model and scheudling model!