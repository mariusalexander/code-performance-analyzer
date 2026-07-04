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

#include "BlockExtractor.h"

#include "models/cv32e40p/CustomICacheModel.h"
#include "models/cv32e40p/CustomDCacheModel.h"
#include "models/cv32e40p/DividerModel.h"
#include "models/cv32e40p/DividerUnsignedModel.h"

#include "PerformanceModel.h"
#include "Channel.h"

#include <iostream>
#include <memory>
#include <fstream>
#include <algorithm>
#include <stdexcept>

static SchedulingFunctionSet _dummySchedSet{{}};

class DummyPerformanceModel : public PerformanceModel
{
public:
    DummyPerformanceModel() : PerformanceModel("DummyModel", &_dummySchedSet) {}

    void connectChannel(Channel*) override {};
    uint64_t getCycleCount(void) override { return 0; }
    std::string getPipelineStream(void) override { return {}; }
    std::string getPrintHeader(void) override { return {}; }
};
static DummyPerformanceModel _dummyModel{};

static cv32e40p::CustomICacheModel _iCache{&_dummyModel};
static cv32e40p::CustomDCacheModel _dCache{&_dummyModel};
static cv32e40p::DividerModel _divider{&_dummyModel};
static cv32e40p::DividerUnsignedModel _divider_u{&_dummyModel};

static cv32e40p::CustomICacheModel* iCache{};
static cv32e40p::CustomDCacheModel* dCache{};
static cv32e40p::DividerModel* divider{};
static cv32e40p::DividerUnsignedModel* divider_u{};

// struct Entry{
//     uint64_t count = 0;
//     int      value = 0;
// };

// std::vector<Entry> iCache;
// std::vector<Entry> dCache;
// std::vector<Entry> divider;
// std::vector<Entry> divider_u;

void BlockExtractor::initialize(void){
    std::cout << "BlockExtractor initialized" << std::endl;
}

void BlockExtractor::execute(void){

    static auto init_once = [&](){
        _iCache.pc_ptr          = (uint64_t*)channel->getTraceValueHook("pc");
        _dCache.addr_ptr        = (uint64_t*)channel->getTraceValueHook("addr");
        _divider.rs2_data_ptr   = (uint64_t*)channel->getTraceValueHook("rs2_data");
        _divider_u.rs2_data_ptr = (uint64_t*)channel->getTraceValueHook("rs2_data");

        if (_iCache.pc_ptr)          iCache    = &_iCache;
        if (_dCache.addr_ptr)        dCache    = &_dCache;
        if (_divider.rs2_data_ptr)   divider   = &_divider;
        if (_divider_u.rs2_data_ptr) divider_u = &_divider_u;

        std::cout << std::hex;
        std::cout << "iCache    " << iCache     << std::endl;
        std::cout << "dCache    " << dCache     << std::endl;
        std::cout << "divider   " << divider    << std::endl;
        std::cout << "divider_u " << divider_u  << std::endl;
        std::cout << std::dec;
        return 0;
    }();

    for(uint64_t instrIdx_i=0; instrIdx_i < *ch_instrCnt_ptr; instrIdx_i++){
        _dummyModel.instrIndex = instrIdx_i;
        globalInstrCnt++;

        uint64_t curPc = ch_pc_ptr[instrIdx_i];
        
        while(1){
            // Check if Block-Start
            if(!activeBlock){
                activeBlock = true;
                lastPc = curPc - 4;
                globalBlockCnt++;

                // Check if block has been observed before
                auto it = blockMap.find(curPc);
                registeredBlock = true;
                if(it == blockMap.end()){
                    it = blockMap.insert({curPc, Block_Extractor::Block{blockMap.size(), curPc, *blockInstrGen}}).first;
                    registeredBlock = false;
                }
                curBlock = &(it->second);
                curBlock->increaseCallCnt();
            }

            if (curPc != lastPc + 4)
            {
                if (curBlock->getFinalPc() != 0){
                    std::stringstream error;
                    error << "### WARNING: Block 0x" << std::hex << curBlock->getPc() << " - 0x" << curBlock->getFinalPc() << " ended at 0x" << lastPc << "! Need to split BB?" << std::endl;
                    throw std::logic_error(error.str());
                }
            
                // std::cout << "### BB 0x" << std::hex << curBlock->getPc() << " - 0x" << lastPc << " ended: pc change at 0x" << curPc << std::dec << ", typeId: " << ch_typeId_ptr[instrIdx_i] << std::endl;
                curBlock->forceEnd(lastPc);
                activeBlock = false;
                continue;
            }
            break;
        }

        // Append instrType if block has not been observed before
        if(!registeredBlock){
            if (curBlock->getFinalPc() > 0) {
                std::stringstream error;
                error << "### WARNING: Block 0x" << std::hex << curBlock->getPc() << " - 0x" << curBlock->getFinalPc() << " was assumed finished!" << std::endl;
                throw std::logic_error(error.str());
            }
            // std::cout << "### appending: 0x" << std::hex << curBlock->getPc() << " -> pc: 0x" << curPc << " typeId: " << std::dec << ch_typeId_ptr[instrIdx_i] << std::endl;
            curBlock->appendInstr(
                ch_typeId_ptr[instrIdx_i],
                channel,
                curPc,
                instrIdx_i
            );
            uniqueInstrsCnt++;
        }

        // std::cout << "current pc: " << std::hex << " 0x" << curPc << std::dec << " typeId: " << ch_typeId_ptr[instrIdx_i]<< std::endl;

        // get dynamic delays
        if (curBlock->usesICache(curPc)) {
            assert(iCache);
            int delay = iCache->getDelay();
            // std::cout << "iCache    " << " GET_DELAY = " << delay << std::hex << " 0x" << curPc << std::dec << std::endl;
            auto it = dynamicData.find(curPc);
            if(it == dynamicData.end()){
                it = dynamicData.insert({curPc, DynamicData{}}).first;
            }
            DynamicData::update(it->second.iCacheDelays, delay);
        }
        if (curBlock->usesDCache(curPc)) {
            assert(dCache);
            int delay = dCache->getDelay();
            // std::cout << "dCache    " << " GET_DELAY = " << delay << std::hex << " 0x" << curPc << std::dec << std::endl;
            auto it = dynamicData.find(curPc);
            if(it == dynamicData.end()){
                it = dynamicData.insert({curPc, DynamicData{}}).first;
            }
            DynamicData::update(it->second.dCacheDelays, delay);
        }
        if (curBlock->usesDiv(curPc)) {
            assert(divider);
            int delay = divider->getDelay();
            // std::cout << "divider   " << " GET_DELAY = " << delay << std::hex << " 0x" << curPc << " vs 0x" << ((curBlock->getPc() - curPc) >> 4) << std::dec << std::endl;
            auto it = dynamicData.find(curPc);
            if(it == dynamicData.end()){
                it = dynamicData.insert({curPc, DynamicData{}}).first;
            }
            DynamicData::update(it->second.divDelays, delay);
        }
        if (curBlock->usesDivU(curPc)) {
            assert(divider_u);
            int delay = divider_u->getDelay();
            // std::cout << "divider_u " << " GET_DELAY = " << delay << std::hex << " 0x" << curPc << std::dec << std::endl;
            auto it = dynamicData.find(curPc);
            if(it == dynamicData.end()){
                it = dynamicData.insert({curPc, DynamicData{}}).first;
            }
            DynamicData::update(it->second.divUDelays, delay);
        }
        // std::cout << "done!" << std::endl;

        lastPc = curPc;
        // Check if Block-End
        if(!registeredBlock){
            if(curBlock->checkEnd(curPc)){
                activeBlock = false;
                // std::cout << "### BB 0x" << std::hex << curBlock->getPc() << " - 0x" << curBlock->getFinalPc() << " ended: branch instr with id: " << std::dec << ch_typeId_ptr[instrIdx_i] << std::endl;
            }
        }
        else{
            if(curBlock->getFinalPc() == curPc){
                activeBlock = false;
            }
        }
    }
}

void BlockExtractor::finalize(void){

    // Sort blocks from unordered map into a vector (sorted by id)
    std::vector<const Block_Extractor::Block*> blockVector;
    blockVector.reserve(blockMap.size());
    for (const auto& pair : blockMap) {
        blockVector.push_back(&(pair.second));
    }
    std::sort(blockVector.begin(), blockVector.end(),
        [](const Block_Extractor::Block* a, const Block_Extractor::Block* b){ return a->getId() < b->getId(); }
    );

    // Write json file
    std::ofstream file(outputPath);

    file << "[\n";
    bool isFirst = true;
    for (const auto& block_i : blockVector) {
        if (isFirst) {
            isFirst = false;
        } else {
            file << ",\n";
        }

        file << "\t{\n";
        file << "\t\t\"id\": " << block_i->getId() << ",\n";
        file << "\t\t\"startPc\": " << block_i->getPc() << ",\n";
        file << "\t\t\"endPc\": " << block_i->getFinalPc() << ",\n";
        file << "\t\t\"callCnt\": " << block_i->getCallCnt() << ",\n";
        file << "\t\t\"instrs\": [\n";
        bool isFirstInstr = true;
        const char* offset = "\t\t\t";

        int idx = -1;
        for (const auto& instr_i : block_i->getInstrVector()) {
            idx += 1;
            if (isFirstInstr) {
                isFirstInstr = false;
            } else {
                file << ",\n";
            }

            file << offset << "{ " << instr_i->getJsonStr();

            auto it = dynamicData.find(block_i->getPc() + idx * 4);
            if (it == dynamicData.end()) {
                file << " }";
                continue;
            }

            const auto& dynamicDelays = it->second;

            // Add dynamicDelays if not empty
            bool hasDelays = !dynamicDelays.iCacheDelays.empty() ||
                            !dynamicDelays.dCacheDelays.empty() ||
                            !dynamicDelays.divDelays.empty() ||
                            !dynamicDelays.divUDelays.empty();

            if (hasDelays) {
                file << ",\n" << offset << "  \"dynamicDelays\": {";

                // Helper lambda to print delays for a specific type as a flat object
                auto printDelays = [&](const std::string& type, const std::vector<DynamicData::Entry>& entries) {
                    if (!entries.empty()) {
                        file << " \"" << type << "\": {";
                        bool isFirstEntry = true;
                        for (const auto& entry : entries) {
                            if (!isFirstEntry) {
                                file << ", ";
                            }
                            isFirstEntry = false;
                            file << "\"" << entry.value << "\": " << entry.count;
                        }
                        file << "}";
                    }
                };

                // Print delays for each type, with proper comma handling
                bool firstType = true;
                if (!dynamicDelays.iCacheDelays.empty()) {
                    printDelays("iCache", dynamicDelays.iCacheDelays);
                    firstType = false;
                }
                if (!dynamicDelays.dCacheDelays.empty()) {
                    if (!firstType) file << ", ";
                    printDelays("dCache", dynamicDelays.dCacheDelays);
                    firstType = false;
                }
                if (!dynamicDelays.divDelays.empty()) {
                    if (!firstType) file << ", ";
                    printDelays("div", dynamicDelays.divDelays);
                    firstType = false;
                }
                if (!dynamicDelays.divUDelays.empty()) {
                    if (!firstType) file << ", ";
                    printDelays("divU", dynamicDelays.divUDelays);
                }

                file << "}";
            }

            file << " }";
        }

        file << "\n";
        file << "\t\t]\n";
        file << "\t}";
    }

    file << "\n]\n";
    file.close();

    int maxCount = 0;
    for(const auto& block_i: blockVector){
        maxCount = std::max(maxCount, block_i->getCallCnt());
    }

    // Summary to terminal
    std::cout << "+++++++++++++++++++++++++++++++++++++++++++++++++++++" << std::endl;
    std::cout << "Writing block list to: " << outputPath << std::endl;
    std::cout << "+++++++++++++++++++++++++++++++++++++++++++++++++++++" << std::endl;
    std::cout << "SUMMARY:" << std::endl;

    std::cout << "Number of counted instructions: " << globalInstrCnt << std::endl;
    std::cout << "Number of unique instructions:  " << uniqueInstrsCnt << std::endl;
    std::cout << "Number of counted blocks:       " << globalBlockCnt << std::endl;
    std::cout << "Number of registered blocks:    " << blockMap.size() << std::endl;
    std::cout << "Highest call count:             " << maxCount << std::endl;

    std::cout << "+++++++++++++++++++++++++++++++++++++++++++++++++++++" << std::endl;

    return;

    // Helper lambda to print a vector of Entry
    auto printEntries = [](const std::string& label, uint64_t pc, const std::vector<DynamicData::Entry>& entries) {
        if (entries.size() == 0) return;
        std::cout << std::hex << "0x" << pc << std::dec << " -> " << label << ":" << std::endl;
        for (const auto& entry : entries) {
            std::cout << "  - Value: " << entry.value << ", Count: " << entry.count << std::endl;
        }
    };

    for (auto data: dynamicData){
        // Print stats for each delay type
        printEntries("iCacheDelays", data.first, data.second.iCacheDelays);
        printEntries("dCacheDelays", data.first, data.second.dCacheDelays);
        printEntries("divDelays", data.first, data.second.divDelays);
        printEntries("divUDelays", data.first, data.second.divUDelays);
    }

    // Helper lambda to print accumulated delay values
    auto printAccumulatedEntries = [](const std::string& label, const std::unordered_map<int, uint64_t>& accumulatedDelays) {
        if (accumulatedDelays.empty()) return;

        std::cout << label << ":" << std::endl;
        for (const auto& [value, totalCount] : accumulatedDelays) {
            std::cout << "  - Value: " << value << ", Total Count: " << totalCount << std::endl;
        }
    };

    // Iterate over all dynamicData entries and accumulate counts
    std::unordered_map<int, uint64_t> accumulatedICacheDelays;
    std::unordered_map<int, uint64_t> accumulatedDCacheDelays;
    std::unordered_map<int, uint64_t> accumulatedDivDelays;
    std::unordered_map<int, uint64_t> accumulatedDivUDelays;

    // Accumulate counts for each delay type
    for (const auto& [pc, data] : dynamicData) {
        for (const auto& entry : data.iCacheDelays) {
            accumulatedICacheDelays[entry.value] += entry.count;
        }
        for (const auto& entry : data.dCacheDelays) {
            accumulatedDCacheDelays[entry.value] += entry.count;
        }
        for (const auto& entry : data.divDelays) {
            accumulatedDivDelays[entry.value] += entry.count;
        }
        for (const auto& entry : data.divUDelays) {
            accumulatedDivUDelays[entry.value] += entry.count;
        }
    }

    // Print accumulated stats for each delay type
    printAccumulatedEntries("iCacheDelays", accumulatedICacheDelays);
    printAccumulatedEntries("dCacheDelays", accumulatedDCacheDelays);
    printAccumulatedEntries("divDelays", accumulatedDivDelays);
    printAccumulatedEntries("divUDelays", accumulatedDivUDelays);
    
    // Calculate the total number of all delays
    uint64_t totalDelays = 0;

    // Sum up counts for each delay type
    for (const auto& [pc, data] : dynamicData) {
        for (const auto& entry : data.iCacheDelays) {
            totalDelays += entry.count;
        }
        for (const auto& entry : data.dCacheDelays) {
            totalDelays += entry.count;
        }
        for (const auto& entry : data.divDelays) {
            totalDelays += entry.count;
        }
        for (const auto& entry : data.divUDelays) {
            totalDelays += entry.count;
        }
    }

    // Print the total number of all delays
    std::cout << "Total number of all delays: " << totalDelays << std::endl;
}