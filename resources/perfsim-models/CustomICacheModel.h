/*
 * Copyright 2022 Chair of EDA, Technical University of Munich
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

#ifndef CV32E40P_CUSTOM_I_CACHE_MODEL_H
#define CV32E40P_CUSTOM_I_CACHE_MODEL_H

#include <stdbool.h>
#include <cstdint>
#include <string>
#include <cmath>
#include <cassert>

#include "PerformanceModel.h"

namespace cv32e40p{

struct ICacheEntry
{
  uint64_t tag = 0;
  bool valid = false;
};

class CustomICacheModel : public ResourceModel
{
    constexpr static unsigned WAYS=1;
    constexpr static unsigned ROWS=32;
    constexpr static unsigned CACHE_DELAY=1;
    constexpr static unsigned MEMORY_DELAY=5;

public:

    CustomICacheModel(PerformanceModel* parent_) :
        ResourceModel("CustomICacheModel", parent_)
    {};

    int getDelay(void) override
    {
        uint64_t pc = pc_ptr[getInstrIndex()];

        isMiss = !inCache(pc);

        if(isMiss)
        {
            return MEMORY_DELAY;
        }
        return CACHE_DELAY;
    }

    // Trace value
    uint64_t* pc_ptr;

private:

    // Cache state
    ICacheEntry tag_cache[WAYS][ROWS];

    // Miss flag. Currently only used for info print
    bool isMiss = false;

    // Support functions
    bool inCache(uint64_t pc_)
    {
        constexpr uint64_t offsetBits = ceil(log2(32 / 8)) +  // offset to index byte in a word
                                        ceil(log2(4));        // offset to index word in a cache line
        constexpr uint64_t indexBits  = ceil(log2(ROWS));     // index for blocks

        uint64_t tag = pc_ >> (offsetBits + indexBits);
        uint64_t index = (pc_ >> offsetBits) & ~(tag << indexBits);

        for(int way_i=0; way_i<WAYS; way_i++)
        {
            assert(way_i < int(WAYS) && "ways!");
            assert(index < int(ROWS) && "rows!");
            if(tag_cache[way_i][index].tag == tag)
            {
                // Cache hit
                return true;
            }
        }

        // Cache miss
        updateCache(tag, index);
        return false;
    }

    void updateCache(uint64_t tag_, uint64_t index_)
    {
        int way = -1;

        for(int i=0; i<WAYS; i++)
        {
            if(!tag_cache[i][index_].valid)
            {
                way = i;
                break;
            }
        }

        if(way == -1)
        {
            way = replacement();
        }

        assert(way < int(WAYS) && "ways!");
        assert(index_ < int(ROWS) && "rows!");

        tag_cache[way][index_].tag = tag_;
        tag_cache[way][index_].valid = true;
    }

    int replacement(void)
    {
        static uint8_t shift_state = 0;
        shift_state = (shift_state + 1) % WAYS;
        return shift_state;
    }
};

} // namespace cv32e40p

#endif // CV32E40P_CUSTOM_I_CACHE_MODEL_H
