# peformance-sim

### [CustomDCacheModel.h](CustomDCacheModel.h)

Data cache model with compile-time defined variables, defining the layout of the cache (number of sets, entries per set, etc.)

Must be installed to [`SoftwareEval-Backends/libs/externalModels/include/models/cv32e40p`](https://github.com/tum-ei-eda/SoftwareEval-Backends/tree/main/libs/externalModels/include/models/cv32e40p).

### [CustomICacheModel.h](CustomICacheModel.h)

Instruction cache model with compile-time defined variables, defining the layout of the cache (number of sets, entries per set, etc.)

Must be installed to [`SoftwareEval-Backends/libs/externalModels/include/models/cv32e40p`](https://github.com/tum-ei-eda/SoftwareEval-Backends/tree/main/libs/externalModels/include/models/cv32e40p).

### [PerfectBranhcPredictModel.h](PerfectBranhcPredictModel.h)

Simple branch prediction model, that does not induce any delays on a branch miss -> perfect branch prediction.

Must be installed to [`SoftwareEval-Backends/libs/externalModels/include/models/common`](https://github.com/tum-ei-eda/SoftwareEval-Backends/tree/main/libs/externalModels/include/models/common).
