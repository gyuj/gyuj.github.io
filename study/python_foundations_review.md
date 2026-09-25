# Python Foundations Review

---

## 1. Arrays (Lists)

### Concept

Python lists are dynamic arrays — ordered, mutable sequences that can hold mixed types (though typically you'll use one type).

**Key properties:**
- O(1) access by index
- O(1) append to end
- O(n) insert/delete at arbitrary position
- O(n) search (unsorted)

### Essential Operations

```python
# Creation
nums = [1, 2, 3, 4, 5]
zeros = [0] * 5            # [0, 0, 0, 0, 0]

# Access & Slicing
nums[0]       # 1
nums[-1]      # 5
nums[1:3]     # [2, 3]
nums[::-1]    # [5, 4, 3, 2, 1] (reversed)

# Modification
nums.append(6)             # Add to end
nums.insert(0, 0)         # Insert at index
nums.pop()                # Remove & return last
nums.pop(2)               # Remove & return at index

# Useful patterns
len(nums)
min(nums), max(nums), sum(nums)
sorted(nums)              # Returns new list
nums.sort()               # In-place sort
nums.reverse()            # In-place reverse

# List comprehension
squares = [x**2 for x in range(10)]
evens = [x for x in nums if x % 2 == 0]
```

### Q&A Examples

**Q1: Two Sum — Given an array and a target, return indices of two numbers that add up to target.**

```python
def two_sum(nums, target):
    seen = {}  # value -> index
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i

# Example: two_sum([2, 7, 11, 15], 9) -> [0, 1]
```

**Q2: Remove Duplicates from Sorted Array (in-place) — Return new length.**

```python
def remove_duplicates(nums):
    if not nums:
        return 0
    write = 1
    for read in range(1, len(nums)):
        if nums[read] != nums[read - 1]:
            nums[write] = nums[read]
            write += 1
    return write

# Example: remove_duplicates([1,1,2,3,3]) -> 3, array becomes [1,2,3,...]
```

**Q3: Maximum Subarray (Kadane's Algorithm)**

```python
def max_subarray(nums):
    current_sum = max_sum = nums[0]
    for num in nums[1:]:
        current_sum = max(num, current_sum + num)
        max_sum = max(max_sum, current_sum)
    return max_sum

# Example: max_subarray([-2,1,-3,4,-1,2,1,-5,4]) -> 6 (subarray [4,-1,2,1])
```

---

## 2. Strings

### Concept

Python strings are **immutable** sequences of characters. Any "modification" creates a new string.

**Key properties:**
- O(1) access by index
- O(n) concatenation (creates new string)
- O(n) slicing
- Immutable — cannot do `s[0] = 'x'`

### Essential Operations

```python
s = "hello world"

# Access & Slicing
s[0]          # 'h'
s[-1]         # 'd'
s[0:5]        # 'hello'
s[::-1]       # 'dlrow olleh'

# Methods (all return NEW strings)
s.upper()               # 'HELLO WORLD'
s.lower()               # 'hello world'
s.strip()               # Remove whitespace from ends
s.split()               # ['hello', 'world']
s.split(',')            # Split by delimiter
s.replace('hello', 'hi')# 'hi world'
s.startswith('hello')   # True
s.find('world')         # 6 (index or -1)

# Character checks
c.isalpha()             # Is letter?
c.isdigit()             # Is digit?
c.isalnum()             # Is letter or digit?

# Building strings efficiently
chars = ['h', 'e', 'l', 'l', 'o']
result = ''.join(chars)  # 'hello' — O(n), preferred over += in loops

# ASCII conversions
ord('a')   # 97
chr(97)    # 'a'
```

### Q&A Examples

**Q1: Valid Palindrome — Check if string is palindrome (ignoring non-alphanumeric, case-insensitive).**

```python
def is_palindrome(s):
    cleaned = [c.lower() for c in s if c.isalnum()]
    return cleaned == cleaned[::-1]

# Two-pointer approach (more space efficient):
def is_palindrome(s):
    left, right = 0, len(s) - 1
    while left < right:
        while left < right and not s[left].isalnum():
            left += 1
        while left < right and not s[right].isalnum():
            right -= 1
        if s[left].lower() != s[right].lower():
            return False
        left += 1
        right -= 1
    return True

# Example: is_palindrome("A man, a plan, a canal: Panama") -> True
```

**Q2: Valid Anagram — Check if two strings are anagrams.**

```python
from collections import Counter

def is_anagram(s, t):
    return Counter(s) == Counter(t)

# Manual approach:
def is_anagram(s, t):
    if len(s) != len(t):
        return False
    count = {}
    for c in s:
        count[c] = count.get(c, 0) + 1
    for c in t:
        count[c] = count.get(c, 0) - 1
        if count[c] < 0:
            return False
    return True

# Example: is_anagram("anagram", "nagaram") -> True
```

**Q3: Longest Substring Without Repeating Characters**

```python
def length_of_longest_substring(s):
    char_index = {}
    left = 0
    max_len = 0
    for right, char in enumerate(s):
        if char in char_index and char_index[char] >= left:
            left = char_index[char] + 1
        char_index[char] = right
        max_len = max(max_len, right - left + 1)
    return max_len

# Example: length_of_longest_substring("abcabcbb") -> 3
```

---

## 3. Hash Maps (Dictionaries)

### Concept

Dictionaries are hash tables — unordered key-value stores with average O(1) lookup, insert, and delete.

**Key properties:**
- Keys must be hashable (immutable): strings, ints, tuples
- O(1) average for get/set/delete
- O(n) space

### Essential Operations

```python
# Creation
d = {}
d = {'a': 1, 'b': 2}
d = dict.fromkeys(['a', 'b', 'c'], 0)  # {'a': 0, 'b': 0, 'c': 0}

# Access
d['a']                  # 1 (KeyError if missing)
d.get('a')              # 1 (None if missing)
d.get('z', 0)           # 0 (default if missing)

# Modification
d['c'] = 3              # Add/update
del d['a']              # Delete key
d.pop('b', None)        # Remove & return (None if missing)

# Iteration
for key in d:                    # Keys
for key, val in d.items():       # Key-value pairs
for val in d.values():           # Values

# Useful tools
from collections import defaultdict, Counter

counts = Counter("hello")        # {'h':1, 'e':1, 'l':2, 'o':1}
graph = defaultdict(list)        # Missing keys auto-create empty lists
graph['a'].append('b')
```

### Q&A Examples

**Q1: Group Anagrams — Group words that are anagrams of each other.**

```python
from collections import defaultdict

def group_anagrams(strs):
    groups = defaultdict(list)
    for s in strs:
        key = tuple(sorted(s))
        groups[key].append(s)
    return list(groups.values())

# Example: group_anagrams(["eat","tea","tan","ate","nat","bat"])
# -> [["eat","tea","ate"], ["tan","nat"], ["bat"]]
```

**Q2: Top K Frequent Elements**

```python
from collections import Counter

def top_k_frequent(nums, k):
    return [x for x, _ in Counter(nums).most_common(k)]

# Bucket sort approach (O(n)):
def top_k_frequent(nums, k):
    count = Counter(nums)
    buckets = [[] for _ in range(len(nums) + 1)]
    for num, freq in count.items():
        buckets[freq].append(num)

    result = []
    for i in range(len(buckets) - 1, -1, -1):
        for num in buckets[i]:
            result.append(num)
            if len(result) == k:
                return result

# Example: top_k_frequent([1,1,1,2,2,3], 2) -> [1, 2]
```

**Q3: Subarray Sum Equals K — Count subarrays that sum to k.**

```python
def subarray_sum(nums, k):
    count = 0
    prefix_sum = 0
    prefix_counts = {0: 1}  # sum -> number of times seen

    for num in nums:
        prefix_sum += num
        # If (prefix_sum - k) was seen before, those subarrays sum to k
        count += prefix_counts.get(prefix_sum - k, 0)
        prefix_counts[prefix_sum] = prefix_counts.get(prefix_sum, 0) + 1

    return count

# Example: subarray_sum([1,1,1], 2) -> 2
```

---

## 4. Sliding Window

### Concept

A technique for problems involving **contiguous subarrays/substrings**. Instead of recalculating from scratch for each window position, you slide the window by removing the leftmost element and adding the next right element.

**Two types:**
1. **Fixed-size window** — window size is given (k)
2. **Variable-size window** — expand right, shrink left based on a condition

**Template:**

```python
# Variable-size sliding window template
def sliding_window(arr):
    left = 0
    window_state = ...  # track what's in the window

    for right in range(len(arr)):
        # 1. Expand: add arr[right] to window state

        # 2. Shrink: while window is invalid, remove arr[left]
        while window_is_invalid():
            # remove arr[left] from window state
            left += 1

        # 3. Update answer (window [left..right] is valid)
```

### Q&A Examples

**Q1: Maximum Sum Subarray of Size K (Fixed Window)**

```python
def max_sum_subarray(nums, k):
    window_sum = sum(nums[:k])
    max_sum = window_sum

    for i in range(k, len(nums)):
        window_sum += nums[i] - nums[i - k]  # slide: add right, remove left
        max_sum = max(max_sum, window_sum)

    return max_sum

# Example: max_sum_subarray([2, 1, 5, 1, 3, 2], 3) -> 9 (subarray [5,1,3])
```

**Q2: Minimum Size Subarray Sum — Shortest subarray with sum >= target.**

```python
def min_subarray_len(target, nums):
    left = 0
    current_sum = 0
    min_len = float('inf')

    for right in range(len(nums)):
        current_sum += nums[right]

        while current_sum >= target:
            min_len = min(min_len, right - left + 1)
            current_sum -= nums[left]
            left += 1

    return min_len if min_len != float('inf') else 0

# Example: min_subarray_len(7, [2,3,1,2,4,3]) -> 2 (subarray [4,3])
```

**Q3: Longest Substring with At Most K Distinct Characters**

```python
def longest_k_distinct(s, k):
    char_count = {}
    left = 0
    max_len = 0

    for right in range(len(s)):
        char_count[s[right]] = char_count.get(s[right], 0) + 1

        while len(char_count) > k:
            char_count[s[left]] -= 1
            if char_count[s[left]] == 0:
                del char_count[s[left]]
            left += 1

        max_len = max(max_len, right - left + 1)

    return max_len

# Example: longest_k_distinct("eceba", 2) -> 3 ("ece")
```

---

## 5. Sets

### Concept

Unordered collections of **unique** elements. Built on hash tables, so O(1) average for add/remove/lookup.

**Key properties:**
- Elements must be hashable
- No duplicates
- No indexing (unordered)
- O(1) membership test (`in`)

### Essential Operations

```python
# Creation
s = set()
s = {1, 2, 3}
s = set([1, 2, 2, 3])    # {1, 2, 3} — deduplicates

# Modification
s.add(4)
s.remove(4)               # KeyError if missing
s.discard(4)              # No error if missing
s.pop()                   # Remove arbitrary element

# Membership
3 in s                    # True — O(1)

# Set operations
a = {1, 2, 3}
b = {2, 3, 4}
a | b        # Union: {1, 2, 3, 4}
a & b        # Intersection: {2, 3}
a - b        # Difference: {1}
a ^ b        # Symmetric difference: {1, 4}
a.issubset(b)    # False
```

### Q&A Examples

**Q1: Contains Duplicate**

```python
def contains_duplicate(nums):
    return len(nums) != len(set(nums))

# Or early exit:
def contains_duplicate(nums):
    seen = set()
    for num in nums:
        if num in seen:
            return True
        seen.add(num)
    return False

# Example: contains_duplicate([1,2,3,1]) -> True
```

**Q2: Intersection of Two Arrays**

```python
def intersection(nums1, nums2):
    return list(set(nums1) & set(nums2))

# Example: intersection([1,2,2,1], [2,2]) -> [2]
```

**Q3: Longest Consecutive Sequence — Find longest consecutive run in unsorted array, O(n).**

```python
def longest_consecutive(nums):
    num_set = set(nums)
    longest = 0

    for num in num_set:
        # Only start counting from the beginning of a sequence
        if num - 1 not in num_set:
            current = num
            length = 1
            while current + 1 in num_set:
                current += 1
                length += 1
            longest = max(longest, length)

    return longest

# Example: longest_consecutive([100, 4, 200, 1, 3, 2]) -> 4 (sequence [1,2,3,4])
```

---

## 6. Sorting

### Concept

Python's built-in sort uses **Timsort** (hybrid merge sort + insertion sort) — O(n log n) average and worst case, stable.

**Key properties:**
- `sorted(lst)` returns a new list
- `lst.sort()` sorts in-place, returns None
- Both accept `key=` and `reverse=` params
- Stable: equal elements maintain relative order

### Essential Operations

```python
# Basic
nums = [3, 1, 4, 1, 5]
sorted(nums)                    # [1, 1, 3, 4, 5] — new list
nums.sort()                     # In-place
nums.sort(reverse=True)         # Descending

# Custom key
words = ["banana", "pie", "apple"]
sorted(words, key=len)          # ['pie', 'apple', 'banana']
sorted(words, key=lambda w: w[-1])  # Sort by last character

# Multi-criteria: sort by length, then alphabetically
sorted(words, key=lambda w: (len(w), w))

# Sort objects/tuples
intervals = [(1,3), (2,6), (8,10)]
intervals.sort(key=lambda x: x[0])  # Sort by start time

# Useful: sort dict by value
d = {'a': 3, 'b': 1, 'c': 2}
sorted(d.items(), key=lambda x: x[1])  # [('b',1), ('c',2), ('a',3)]
```

### Common Sorting Algorithms (Know the ideas)

| Algorithm      | Time (avg) | Time (worst) | Space | Stable? |
|---------------|-----------|-------------|-------|---------|
| Bubble Sort   | O(n^2)    | O(n^2)      | O(1)  | Yes     |
| Insertion Sort| O(n^2)    | O(n^2)      | O(1)  | Yes     |
| Merge Sort    | O(n log n)| O(n log n)  | O(n)  | Yes     |
| Quick Sort    | O(n log n)| O(n^2)      | O(log n)| No    |
| Heap Sort     | O(n log n)| O(n log n)  | O(1)  | No      |

### Q&A Examples

**Q1: Merge Intervals**

```python
def merge_intervals(intervals):
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]

    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return merged

# Example: merge_intervals([[1,3],[2,6],[8,10],[15,18]])
# -> [[1,6],[8,10],[15,18]]
```

**Q2: Sort Colors (Dutch National Flag) — Sort array of 0s, 1s, 2s in-place, one pass.**

```python
def sort_colors(nums):
    low, mid, high = 0, 0, len(nums) - 1

    while mid <= high:
        if nums[mid] == 0:
            nums[low], nums[mid] = nums[mid], nums[low]
            low += 1
            mid += 1
        elif nums[mid] == 1:
            mid += 1
        else:
            nums[mid], nums[high] = nums[high], nums[mid]
            high -= 1

# Example: sort_colors([2,0,2,1,1,0]) -> [0,0,1,1,2,2]
```

**Q3: Kth Largest Element (Quick Select — O(n) average)**

```python
import random

def find_kth_largest(nums, k):
    target = len(nums) - k  # kth largest = (n-k)th smallest

    def quick_select(left, right):
        pivot_idx = random.randint(left, right)
        nums[pivot_idx], nums[right] = nums[right], nums[pivot_idx]
        pivot = nums[right]

        store = left
        for i in range(left, right):
            if nums[i] < pivot:
                nums[store], nums[i] = nums[i], nums[store]
                store += 1
        nums[store], nums[right] = nums[right], nums[store]

        if store == target:
            return nums[store]
        elif store < target:
            return quick_select(store + 1, right)
        else:
            return quick_select(left, store - 1)

    return quick_select(0, len(nums) - 1)

# Example: find_kth_largest([3,2,1,5,6,4], 2) -> 5
```

---

## Quick Reference: When to Use What

| Problem Pattern | Data Structure / Technique |
|----------------|---------------------------|
| "Find pair/complement" | Hash map |
| "Count occurrences" | Hash map / Counter |
| "Duplicates?" | Set |
| "Contiguous subarray" | Sliding window |
| "Sorted array + find" | Binary search / Two pointers |
| "Top K / Kth element" | Heap or Quick Select |
| "Overlapping intervals" | Sort + merge |
| "Unique characters" | Set or fixed array (26 slots) |
| "Prefix sum needed" | Hash map of prefix sums |

---

## Practice Tips

1. **Understand the constraint** — n <= 10^4 allows O(n^2), n <= 10^5 needs O(n log n), n <= 10^6 needs O(n)
2. **Start with brute force** — then optimize
3. **Talk through examples** — trace through small inputs by hand
4. **Edge cases** — empty input, single element, all same, already sorted, negative numbers
