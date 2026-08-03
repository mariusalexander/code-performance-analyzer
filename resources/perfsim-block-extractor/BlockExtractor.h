/*
 * Copyright 2026 Chair of EDA, Technical University of Munich
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *	 http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef SWEVAL_BACKENDS_BLOCK_EXTRACTOR_H
#define SWEVAL_BACKENDS_BLOCK_EXTRACTOR_H

#include "BlockInstructionGenerator.h"

#include "Backend.h"
#include "Channel.h"

#include <cstdint>
#include <unordered_map>
#include <vector>
#include <memory>
#include <iostream>
#include <cassert>

using std::uint64_t;

namespace Block_Extractor{

class Block{

public:
    Block(int id_, uint64_t pc_, const BlockInstructionGenerator& blockInstrGen_): 
        id(id_),
        pc(pc_),
        blockInstrGen(blockInstrGen_)
    {}

    void appendInstr(uint64_t typeId_, Channel* channel_, uint64_t pc, uint64_t instrIdx_) {
        instrVector.push_back(blockInstrGen.getCtor(typeId_)(channel_, instrIdx_));
    }

    void increaseCallCnt(void) { callCnt++; }
    int getId(void) const { return id; }
    uint64_t getPc(void) const { return pc; }
    uint64_t getFinalPc(void) const { return finalPc; }
    int getCallCnt(void) const {return callCnt; }
    const std::vector<std::unique_ptr<BlockInstruction>>& getInstrVector(void) const { return instrVector; }

    bool checkEnd(uint64_t pc_) {
        if(instrVector.back()->isBranchInstr()){
            finalPc = pc_;
            return true;
        }
        return false;
    }
    void forceEnd(uint64_t pc_) {
        finalPc = pc_;
    }

    bool usesICache(uint64_t pc_) { return instrVector.at((pc_ - pc) >> 2)->usesICache(); }
    bool usesDCache(uint64_t pc_) { return instrVector.at((pc_ - pc) >> 2)->usesDCache(); }
    bool usesDiv(uint64_t pc_)    { return instrVector.at((pc_ - pc) >> 2)->usesDiv();    }
    bool usesDivU(uint64_t pc_)   { return instrVector.at((pc_ - pc) >> 2)->usesDivU();   }

private:
    int id;
    uint64_t pc;
    uint64_t finalPc = 0;
    int callCnt = 0;
    std::vector<std::unique_ptr<BlockInstruction>> instrVector;
    const BlockInstructionGenerator& blockInstrGen;

};

} // namespace Block_Extractor

class BlockExtractor: public Backend{

public:
    BlockExtractor(){};
    ~BlockExtractor() {};

    virtual void connectChannel(Channel*) = 0;
    void initialize(void);
    void execute(void);
    void finalize(void);

protected:
    std::unique_ptr<BlockInstructionGenerator> blockInstrGen;
    std::string outputPath;

    Channel* channel;
    uint64_t* ch_typeId_ptr;
    uint64_t* ch_instrCnt_ptr;
    uint64_t* ch_pc_ptr;

private:
    bool activeBlock = false;
    bool registeredBlock = false;

    uint64_t globalInstrCnt = 0;
    uint64_t globalBlockCnt = 0;
    uint64_t uniqueInstrsCnt = 0;
    uint64_t lastPc = 0;

    struct DynamicData {
        struct Entry{
            uint64_t count = 0;
            int      value = 0;
        };

        static void update(std::vector<Entry>& delays, int delay) {
            for (auto& entry : delays) {
                if (entry.value == delay) {
                    entry.count += 1;
                    return;
                }
            }
            delays.push_back(Entry{1, delay});
        }

        std::vector<Entry> iCacheDelays;
        std::vector<Entry> dCacheDelays;
        std::vector<Entry> divDelays;
        std::vector<Entry> divUDelays;
    };

    std::unordered_map<uint64_t, Block_Extractor::Block> blockMap;
    std::unordered_map<uint64_t, DynamicData> dynamicData;
    Block_Extractor::Block* curBlock;
};

#endif // SWEVAL_BACKENDS_BLOCK_EXTRACTOR_H
