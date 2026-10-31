// SPDX-FileCopyrightText: 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <boost/icl/discrete_interval.hpp>
#include <boost/icl/interval_map.hpp>
#include <boost/icl/split_interval_map.hpp>
#include <boost/icl/split_interval_set.hpp>
#include <boost/pool/pool.hpp>
#include <boost/pool/pool_alloc.hpp>
#include <boost/pool/poolfwd.hpp>
#include <algorithm>
#include <iterator>
#include <map>
#include "common/types.h"

namespace VideoCore {

template <class T>
using RangeSetsAllocator =
    boost::fast_pool_allocator<T, boost::default_user_allocator_new_delete,
                               boost::details::pool::default_mutex, 1024, 2048>;

// gow3 26 Oct 2026: disjoint half-open ranges in a std::map (start -> end), touching ones joined.
// This was a boost::icl::interval_set. Boost.ICL looks up the elements a range overlaps with
// lower_bound/upper_bound of an interval key; a key overlapping several elements compares
// "equal" to each of them, which is no strict weak ordering, and with libc++ 22 (MSYS2 clang64)
// those searches land on any of them: every operation spanning two or more intervals went wrong
// (subtracting [15,95) from [10,20) [30,40) [50,60) [70,80) [90,100) removed [30,40) only; their
// intersection with a range returned one interval; ForEachInRange left intervals out). In The
// Last of Us a batched page fetch (CopyFinishedGpuPage) then left the hair physics' state out of
// its copy, FinishPageFetch removed the pages from the GPU ranges anyway and the next upload sent
// the guest's stale copy (zeros) over the state: ~550 times per 5 s, the hair stretched for a
// frame. A key here is one start address, so the lookups are exact.
struct RangeSet {
    explicit RangeSet() = default;
    ~RangeSet() = default;

    void Add(VAddr base_address, size_t size) {
        if (size == 0) {
            return;
        }
        VAddr start = base_address;
        VAddr end = base_address + size;
        // From the last range starting at or before `start` when it reaches it (touching
        // included), every range starting at or before `end` is joined into this one.
        auto it = m_ranges.upper_bound(start);
        if (it != m_ranges.begin()) {
            const auto prev = std::prev(it);
            if (prev->second >= start) {
                // Most adds rewrite a range the set holds or grow one: no node is freed and
                // allocated for them (the draw recording thread adds per written buffer).
                if (prev->second >= end) {
                    return;
                }
                while (it != m_ranges.end() && it->first <= end) {
                    end = std::max(end, it->second);
                    it = m_ranges.erase(it);
                }
                prev->second = end;
                return;
            }
        }
        while (it != m_ranges.end() && it->first <= end) {
            start = std::min(start, it->first);
            end = std::max(end, it->second);
            it = m_ranges.erase(it);
        }
        m_ranges.emplace_hint(it, start, end);
    }

    void Subtract(VAddr base_address, size_t size) {
        if (size == 0 || m_ranges.empty()) {
            return;
        }
        const VAddr start = base_address;
        const VAddr end = base_address + size;
        auto it = FirstEndingAfter(start);
        while (it != m_ranges.end() && it->first < end) {
            const VAddr lo = it->first;
            const VAddr hi = it->second;
            it = m_ranges.erase(it);
            if (lo < start) {
                m_ranges.emplace_hint(it, lo, start);
            }
            if (hi > end) {
                m_ranges.emplace_hint(it, end, hi);
                break;
            }
        }
    }

    void Clear() {
        m_ranges.clear();
    }

    /// Every byte of [base_address, base_address + size) is in the set (an empty range is).
    bool Contains(VAddr base_address, size_t size) const {
        if (size == 0) {
            return true;
        }
        auto it = m_ranges.upper_bound(base_address);
        if (it == m_ranges.begin()) {
            return false;
        }
        --it;
        return it->second >= base_address + size;
    }

    /// gow3: number of disjoint ranges (statistics).
    size_t Count() const {
        return m_ranges.size();
    }

    bool Intersects(VAddr base_address, size_t size) const {
        if (size == 0) {
            return false;
        }
        const auto it = FirstEndingAfter(base_address);
        return it != m_ranges.end() && it->first < base_address + size;
    }

    template <typename Func>
    void ForEach(Func&& func) const {
        for (const auto& [start, end] : m_ranges) {
            func(start, end);
        }
    }

    /// The parts of the set inside [base_addr, base_addr + size), in address order. The set must
    /// not change while it runs.
    template <typename Func>
    void ForEachInRange(VAddr base_addr, size_t size, Func&& func) const {
        if (size == 0 || m_ranges.empty()) {
            return;
        }
        const VAddr start_address = base_addr;
        const VAddr end_address = start_address + size;
        for (auto it = FirstEndingAfter(start_address); it != m_ranges.end() && it->first < end_address;
             ++it) {
            func(std::max(it->first, start_address), std::min(it->second, end_address));
        }
    }

    template <typename Func>
    void ForEachNotInRange(VAddr base_addr, size_t size, Func&& func) const {
        const VAddr end_addr = base_addr + size;
        ForEachInRange(base_addr, size, [&](VAddr range_addr, VAddr range_end) {
            if (size_t gap_size = range_addr - base_addr; gap_size != 0) {
                func(base_addr, gap_size);
            }
            base_addr = range_end;
        });
        if (base_addr != end_addr) {
            func(base_addr, end_addr - base_addr);
        }
    }

private:
    using Map = std::map<VAddr, VAddr>;

    /// The first range ending after `address` (holding it, or the first one after it).
    Map::const_iterator FirstEndingAfter(VAddr address) const {
        auto it = m_ranges.upper_bound(address);
        if (it != m_ranges.begin()) {
            const auto prev = std::prev(it);
            if (prev->second > address) {
                return prev;
            }
        }
        return it;
    }
    Map::iterator FirstEndingAfter(VAddr address) {
        auto it = m_ranges.upper_bound(address);
        if (it != m_ranges.begin()) {
            const auto prev = std::prev(it);
            if (prev->second > address) {
                return prev;
            }
        }
        return it;
    }

    Map m_ranges;
};

// gow3 26 Oct 2026: RangeMap and SplitRangeMap below are Boost.ICL containers with the same
// lookups (see RangeSet): wrong over several intervals with libc++ 22. Nothing uses them.
template <typename T>
class RangeMap {
public:
    using IntervalMap =
        boost::icl::interval_map<VAddr, T, boost::icl::total_absorber, std::less,
                                 boost::icl::inplace_identity, boost::icl::inter_section,
                                 ICL_INTERVAL_INSTANCE(ICL_INTERVAL_DEFAULT, VAddr, std::less),
                                 RangeSetsAllocator>;
    using IntervalType = typename IntervalMap::interval_type;

public:
    RangeMap() = default;
    ~RangeMap() = default;

    RangeMap(RangeMap const&) = delete;
    RangeMap& operator=(RangeMap const&) = delete;

    RangeMap(RangeMap&& other);
    RangeMap& operator=(RangeMap&& other);

    void Add(VAddr base_address, size_t size, const T& value) {
        const VAddr end_address = base_address + size;
        IntervalType interval{base_address, end_address};
        m_ranges_map.add({interval, value});
    }

    void Subtract(VAddr base_address, size_t size) {
        const VAddr end_address = base_address + size;
        IntervalType interval{base_address, end_address};
        m_ranges_map -= interval;
    }

    void Clear() {
        m_ranges_map.clear();
    }

    bool Contains(VAddr base_address, size_t size) const {
        const VAddr end_address = base_address + size;
        IntervalType interval{base_address, end_address};
        return boost::icl::contains(m_ranges_map, interval);
    }

    bool Intersects(VAddr base_address, size_t size) const {
        const VAddr end_address = base_address + size;
        IntervalType interval{base_address, end_address};
        return boost::icl::intersects(m_ranges_map, interval);
    }

    template <typename Func>
    void ForEach(Func&& func) const {
        if (m_ranges_map.empty()) {
            return;
        }

        for (const auto& [interval, value] : m_ranges_map) {
            const VAddr inter_addr_end = interval.upper();
            const VAddr inter_addr = interval.lower();
            func(inter_addr, inter_addr_end, value);
        }
    }

    template <typename Func>
    void ForEachInRange(VAddr base_addr, size_t size, Func&& func) const {
        if (m_ranges_map.empty()) {
            return;
        }
        const VAddr start_address = base_addr;
        const VAddr end_address = start_address + size;
        const IntervalType search_interval{start_address, end_address};
        auto it = m_ranges_map.lower_bound(search_interval);
        if (it == m_ranges_map.end()) {
            return;
        }
        auto end_it = m_ranges_map.upper_bound(search_interval);
        for (; it != end_it; it++) {
            VAddr inter_addr_end = it->first.upper();
            VAddr inter_addr = it->first.lower();
            if (inter_addr_end > end_address) {
                inter_addr_end = end_address;
            }
            if (inter_addr < start_address) {
                inter_addr = start_address;
            }
            func(inter_addr, inter_addr_end, it->second);
        }
    }

    template <typename Func>
    void ForEachNotInRange(VAddr base_addr, size_t size, Func&& func) const {
        const VAddr end_addr = base_addr + size;
        ForEachInRange(base_addr, size, [&](VAddr range_addr, VAddr range_end, const T&) {
            if (size_t gap_size = range_addr - base_addr; gap_size != 0) {
                func(base_addr, gap_size);
            }
            base_addr = range_end;
        });
        if (base_addr != end_addr) {
            func(base_addr, end_addr - base_addr);
        }
    }

private:
    IntervalMap m_ranges_map;
};

template <typename T>
class SplitRangeMap {
public:
    using IntervalMap = boost::icl::split_interval_map<
        VAddr, T, boost::icl::total_absorber, std::less, boost::icl::inplace_identity,
        boost::icl::inter_section, ICL_INTERVAL_INSTANCE(ICL_INTERVAL_DEFAULT, VAddr, std::less),
        RangeSetsAllocator>;
    using IntervalType = typename IntervalMap::interval_type;

public:
    SplitRangeMap() = default;
    ~SplitRangeMap() = default;

    SplitRangeMap(SplitRangeMap const&) = delete;
    SplitRangeMap& operator=(SplitRangeMap const&) = delete;

    SplitRangeMap(SplitRangeMap&& other);
    SplitRangeMap& operator=(SplitRangeMap&& other);

    void Add(VAddr base_address, size_t size, const T& value) {
        const VAddr end_address = base_address + size;
        IntervalType interval{base_address, end_address};
        m_ranges_map.add({interval, value});
    }

    void Subtract(VAddr base_address, size_t size) {
        const VAddr end_address = base_address + size;
        IntervalType interval{base_address, end_address};
        m_ranges_map -= interval;
    }

    void Clear() {
        m_ranges_map.clear();
    }

    bool Contains(VAddr base_address, size_t size) const {
        const VAddr end_address = base_address + size;
        IntervalType interval{base_address, end_address};
        return boost::icl::contains(m_ranges_map, interval);
    }

    bool Intersects(VAddr base_address, size_t size) const {
        const VAddr end_address = base_address + size;
        IntervalType interval{base_address, end_address};
        return boost::icl::intersects(m_ranges_map, interval);
    }

    template <typename Func>
    void ForEach(Func&& func) const {
        if (m_ranges_map.empty()) {
            return;
        }

        for (const auto& [interval, value] : m_ranges_map) {
            const VAddr inter_addr_end = interval.upper();
            const VAddr inter_addr = interval.lower();
            func(inter_addr, inter_addr_end, value);
        }
    }

    template <typename Func>
    void ForEachInRange(VAddr base_addr, size_t size, Func&& func) const {
        if (m_ranges_map.empty()) {
            return;
        }
        const VAddr start_address = base_addr;
        const VAddr end_address = start_address + size;
        const IntervalType search_interval{start_address, end_address};
        auto it = m_ranges_map.lower_bound(search_interval);
        if (it == m_ranges_map.end()) {
            return;
        }
        auto end_it = m_ranges_map.upper_bound(search_interval);
        for (; it != end_it; it++) {
            VAddr inter_addr_end = it->first.upper();
            VAddr inter_addr = it->first.lower();
            if (inter_addr_end > end_address) {
                inter_addr_end = end_address;
            }
            if (inter_addr < start_address) {
                inter_addr = start_address;
            }
            func(inter_addr, inter_addr_end, it->second);
        }
    }

    template <typename Func>
    void ForEachNotInRange(VAddr base_addr, size_t size, Func&& func) const {
        const VAddr end_addr = base_addr + size;
        ForEachInRange(base_addr, size, [&](VAddr range_addr, VAddr range_end, const T&) {
            if (size_t gap_size = range_addr - base_addr; gap_size != 0) {
                func(base_addr, gap_size);
            }
            base_addr = range_end;
        });
        if (base_addr != end_addr) {
            func(base_addr, end_addr - base_addr);
        }
    }

private:
    IntervalMap m_ranges_map;
};

} // namespace VideoCore
