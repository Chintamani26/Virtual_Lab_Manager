"""Lab catalog: seeded practicals, reference solutions and faculty templates.

Everything here is plain data so it can be shared by the in-memory seed, the SQL seed
generator (scripts/generate_seed_sql.py) and the tests.
"""

from __future__ import annotations

import json

from app.models import RubricCriterion, TestCaseSpec
from app import worksheet_labs as _W


def notebook(cells: list[tuple[str, str]]) -> str:
    """Build a minimal nbformat-4 notebook JSON string from (cell_type, source) tuples."""
    nb_cells = []
    for cell_type, source in cells:
        cell: dict = {"cell_type": cell_type, "metadata": {}, "source": source.strip("\n")}
        if cell_type == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        nb_cells.append(cell)
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
            "cells": nb_cells,
        },
        indent=1,
    )


def _t(name: str, description: str, code: str = "", hidden: bool = False) -> TestCaseSpec:
    return TestCaseSpec(name=name, description=description, code=code.strip("\n"), hidden=hidden)


def _ct(name: str, description: str, inputs: dict, expected: dict, hidden: bool = False) -> TestCaseSpec:
    return TestCaseSpec(name=name, description=description, inputs=inputs, expected=expected, hidden=hidden)


def _r(id_: str, name: str, description: str, pts: float) -> RubricCriterion:
    return RubricCriterion(id=id_, name=name, description=description, max_points=pts)


# =====================================================================================
# CS201 · Lab 4: Binary Search Trees (coding · main.py) — the hero demo lab
# =====================================================================================
BST_DESCRIPTION = """## Lab 4: Binary Search Trees

Implement a `BST` class in **main.py** that stores **unique integer keys**.

| Method | Expected behaviour |
|---|---|
| `insert(key)` | Insert `key`. **Duplicate keys must be ignored** (size stays the same). |
| `search(key) -> bool` | `True` if the key exists, else `False`. |
| `inorder() -> list[int]` | All keys in ascending order. |
| `min()` / `max()` | Smallest / largest key, or `None` for an empty tree. |
| `height() -> int` | Nodes on the longest root-to-leaf path (empty tree = `0`). |
| `len(tree)` | Number of keys stored. |

**Learning outcomes:** the BST ordering invariant, recursion vs. iteration, and edge cases
(empty trees, duplicates, skewed trees).

> Tip: press **Run Tests** often. If you get stuck, ask the **Socratic Tutor** — it will
> guide you with questions instead of handing you the answer.
"""

BST_STARTER = '''class Node:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None


class BST:
    """Binary Search Tree that stores unique integer keys."""

    def __init__(self):
        self.root = None
        self._size = 0

    def insert(self, key):
        # TODO: insert key while keeping the BST invariant (ignore duplicates)
        pass

    def search(self, key):
        # TODO: return True if key exists
        return False

    def inorder(self):
        # TODO: return keys in ascending order
        return []

    def min(self):
        # TODO
        return None

    def max(self):
        # TODO
        return None

    def height(self):
        # TODO: empty tree has height 0
        return 0

    def __len__(self):
        return self._size


if __name__ == "__main__":
    tree = BST()
    for k in [50, 30, 70, 20, 40, 60, 80]:
        tree.insert(k)
    print("Inorder:", tree.inorder())
    print("Height:", tree.height())
'''

# The demo student's saved draft: everything works except duplicate handling,
# so Run Tests shows "4 of 5 Tests Passed" with test_duplicate_keys failing.
BST_DEMO_DRAFT = '''class Node:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None


class BST:
    """Binary Search Tree that stores unique integer keys."""

    def __init__(self):
        self.root = None
        self._size = 0

    def insert(self, key):
        """Insert key into the tree."""
        if self.root is None:
            self.root = Node(key)
            self._size += 1
            return
        node = self.root
        while True:
            if key < node.key:
                if node.left is None:
                    node.left = Node(key)
                    self._size += 1
                    return
                node = node.left
            else:
                if node.right is None:
                    node.right = Node(key)
                    self._size += 1
                    return
                node = node.right

    def search(self, key):
        """Return True if key is present."""
        node = self.root
        while node:
            if key == node.key:
                return True
            node = node.left if key < node.key else node.right
        return False

    def inorder(self):
        """Return keys in ascending order."""
        out = []

        def walk(node):
            if node:
                walk(node.left)
                out.append(node.key)
                walk(node.right)

        walk(self.root)
        return out

    def min(self):
        node = self.root
        if node is None:
            return None
        while node.left:
            node = node.left
        return node.key

    def max(self):
        node = self.root
        if node is None:
            return None
        while node.right:
            node = node.right
        return node.key

    def height(self):
        def h(node):
            if node is None:
                return 0
            return 1 + max(h(node.left), h(node.right))

        return h(self.root)

    def __len__(self):
        return self._size


if __name__ == "__main__":
    tree = BST()
    for k in [50, 30, 70, 20, 40, 60, 80, 50]:
        tree.insert(k)
    print("Inorder:", tree.inorder())
    print("Size:", len(tree), "Height:", tree.height())
'''

BST_SOLUTION = BST_DEMO_DRAFT.replace(
    """            else:
                if node.right is None:""",
    """            elif key > node.key:
                if node.right is None:""",
).replace(
    """                node = node.right

    def search""",
    """                node = node.right
            else:
                return  # duplicate key: ignore

    def search""",
)

BST_TESTS = [
    _t(
        "test_insert_and_search",
        "Inserted keys are found; missing keys are not.",
        """
t = BST()
for k in [50, 30, 70, 20, 40]:
    t.insert(k)
assert t.search(40) is True, "search(40) should be True after inserting 40"
assert t.search(99) is False, "search(99) should be False for a key that was never inserted"
""",
    ),
    _t(
        "test_inorder_traversal",
        "inorder() returns keys in ascending order.",
        """
t = BST()
for k in [50, 30, 70, 20, 40, 60, 80]:
    t.insert(k)
assert t.inorder() == [20, 30, 40, 50, 60, 70, 80], f"inorder() returned {t.inorder()}"
""",
    ),
    _t(
        "test_min_max",
        "min()/max() work, and return None on an empty tree.",
        """
t = BST()
assert t.min() is None and t.max() is None, "empty tree: min()/max() should return None"
for k in [15, 6, 23, 4, 7, 71]:
    t.insert(k)
assert (t.min(), t.max()) == (4, 71), f"expected (4, 71), got {(t.min(), t.max())}"
""",
    ),
    _t(
        "test_height",
        "height() counts nodes on the longest path (empty = 0).",
        """
t = BST()
assert t.height() == 0, "empty tree height should be 0"
for k in [10, 5, 15, 3]:
    t.insert(k)
assert t.height() == 3, f"expected height 3, got {t.height()}"
""",
    ),
    _t(
        "test_duplicate_keys",
        "Inserting an existing key must not change the tree.",
        """
t = BST()
for k in [8, 3, 10, 3, 8, 10]:
    t.insert(k)
assert len(t) == 3, f"duplicates must be ignored: expected size 3, got {len(t)}"
assert t.inorder() == [3, 8, 10], f"expected [3, 8, 10], got {t.inorder()}"
""",
    ),
    _t(
        "test_skewed_tree",
        "Sorted insertion produces a skewed tree of height n.",
        """
t = BST()
for k in range(1, 201):
    t.insert(k)
assert t.height() == 200, f"expected height 200, got {t.height()}"
assert t.inorder() == list(range(1, 201))
""",
        hidden=True,
    ),
    _t(
        "test_single_negative_key",
        "Works with a single negative key.",
        """
t = BST()
t.insert(-5)
assert t.inorder() == [-5] and t.height() == 1
assert t.min() == t.max() == -5
""",
        hidden=True,
    ),
]

BST_RUBRIC = [
    _r("correctness", "Correctness", "All BST operations behave as specified, including hidden tests.", 5),
    _r("edge_cases", "Edge cases", "Duplicates, empty tree and skewed trees handled.", 2),
    _r("code_quality", "Code quality", "Readable names, docstrings, no dead code or leftover TODOs.", 2),
    _r("efficiency", "Efficiency", "Operations run in O(h); no unnecessary full-tree scans.", 1),
]

# =====================================================================================
# CS201 · Lab 3: Singly Linked Lists (coding)
# =====================================================================================
LL_DESCRIPTION = """## Lab 3: Singly Linked Lists

Implement `LinkedList` in **main.py** with:

- `append(value)` / `prepend(value)`
- `delete(value) -> bool` — remove the **first** occurrence, return `True` if removed
- `reverse()` — reverse the list **in place**
- `to_list() -> list` and `len(lst)`

Edge cases matter: deleting the head, deleting from an empty list, reversing an empty list.
"""

LL_STARTER = '''class Node:
    def __init__(self, value, next=None):
        self.value = value
        self.next = next


class LinkedList:
    def __init__(self):
        self.head = None
        self._size = 0

    def append(self, value):
        pass  # TODO

    def prepend(self, value):
        pass  # TODO

    def delete(self, value):
        return False  # TODO

    def reverse(self):
        pass  # TODO

    def to_list(self):
        return []  # TODO

    def __len__(self):
        return self._size
'''

LL_SOLUTION = '''class Node:
    def __init__(self, value, next=None):
        self.value = value
        self.next = next


class LinkedList:
    """Singly linked list."""

    def __init__(self):
        self.head = None
        self._size = 0

    def append(self, value):
        node = Node(value)
        if self.head is None:
            self.head = node
        else:
            cur = self.head
            while cur.next:
                cur = cur.next
            cur.next = node
        self._size += 1

    def prepend(self, value):
        self.head = Node(value, self.head)
        self._size += 1

    def delete(self, value):
        prev, cur = None, self.head
        while cur:
            if cur.value == value:
                if prev is None:
                    self.head = cur.next
                else:
                    prev.next = cur.next
                self._size -= 1
                return True
            prev, cur = cur, cur.next
        return False

    def reverse(self):
        prev, cur = None, self.head
        while cur:
            cur.next, prev, cur = prev, cur, cur.next
        self.head = prev

    def to_list(self):
        out, cur = [], self.head
        while cur:
            out.append(cur.value)
            cur = cur.next
        return out

    def __len__(self):
        return self._size
'''

LL_TESTS = [
    _t(
        "test_append_and_to_list",
        "append() keeps insertion order.",
        """
l = LinkedList()
for v in [1, 2, 3]:
    l.append(v)
assert l.to_list() == [1, 2, 3] and len(l) == 3
""",
    ),
    _t(
        "test_prepend",
        "prepend() inserts at the head.",
        """
l = LinkedList()
l.append(2); l.prepend(1)
assert l.to_list() == [1, 2]
""",
    ),
    _t(
        "test_delete_middle",
        "delete() removes the first matching value.",
        """
l = LinkedList()
for v in [1, 2, 3, 2]:
    l.append(v)
assert l.delete(2) is True
assert l.to_list() == [1, 3, 2] and len(l) == 3
""",
    ),
    _t(
        "test_delete_missing",
        "delete() returns False when the value is absent.",
        """
l = LinkedList()
assert l.delete(42) is False
l.append(1)
assert l.delete(42) is False and l.to_list() == [1]
""",
    ),
    _t(
        "test_reverse",
        "reverse() reverses in place.",
        """
l = LinkedList()
for v in [1, 2, 3, 4]:
    l.append(v)
l.reverse()
assert l.to_list() == [4, 3, 2, 1]
""",
    ),
    _t(
        "test_delete_head",
        "Deleting the head updates the head pointer.",
        """
l = LinkedList()
for v in [7, 8, 9]:
    l.append(v)
assert l.delete(7) is True and l.to_list() == [8, 9] and len(l) == 2
""",
        hidden=True,
    ),
    _t(
        "test_reverse_empty",
        "Reversing an empty list is a no-op.",
        """
l = LinkedList()
l.reverse()
assert l.to_list() == [] and len(l) == 0
""",
        hidden=True,
    ),
]

LL_RUBRIC = [
    _r("correctness", "Correctness", "All operations pass visible and hidden tests.", 6),
    _r("edge_cases", "Edge cases", "Head deletion, empty list, missing values.", 2),
    _r("code_quality", "Code quality", "Clear structure and naming.", 2),
]

# =====================================================================================
# EE210 · Electrical Lab: logic circuits (circuit · circuit.sim)
# =====================================================================================
HALF_ADDER_DESCRIPTION = """## Lab 2: Half Adder

Design a half adder in **circuit.sim** with inputs `A`, `B` and outputs `SUM`, `CARRY`.

| A | B | SUM | CARRY |
|---|---|-----|-------|
| 0 | 0 | 0 | 0 |
| 0 | 1 | 1 | 0 |
| 1 | 0 | 1 | 0 |
| 1 | 1 | 0 | 1 |

Available gates: `AND OR NOT XOR NAND NOR XNOR BUF`.
"""

HALF_ADDER_STARTER = """# Lab 2: Half Adder
INPUT A B
OUTPUT SUM CARRY

# TODO: define SUM and CARRY
SUM = OR(A, B)
CARRY = 0
"""

HALF_ADDER_SOLUTION = """# Lab 2: Half Adder
INPUT A B
OUTPUT SUM CARRY

SUM = XOR(A, B)
CARRY = AND(A, B)
"""

HALF_ADDER_TESTS = [
    _ct("test_zero_zero", "0 + 0 = 0, carry 0", {"A": 0, "B": 0}, {"SUM": 0, "CARRY": 0}),
    _ct("test_zero_one", "0 + 1 = 1, carry 0", {"A": 0, "B": 1}, {"SUM": 1, "CARRY": 0}),
    _ct("test_one_zero", "1 + 0 = 1, carry 0", {"A": 1, "B": 0}, {"SUM": 1, "CARRY": 0}),
    _ct("test_one_one", "1 + 1 = 0, carry 1", {"A": 1, "B": 1}, {"SUM": 0, "CARRY": 1}),
]

FULL_ADDER_DESCRIPTION = """## Lab 3: Full Adder

Build a **full adder** in **circuit.sim**: inputs `A`, `B`, `CIN`; outputs `SUM`, `COUT`.

- `SUM` is 1 when an **odd** number of inputs are 1.
- `COUT` is 1 when **at least two** inputs are 1.

Hint from the syllabus: a full adder can be composed of **two half adders and an OR gate**.
You may declare intermediate wires, e.g. `P = XOR(A, B)`.
"""

FULL_ADDER_STARTER = """# Lab 3: Full Adder
INPUT A B CIN
OUTPUT SUM COUT

# TODO: compose two half adders. This first attempt ignores CIN!
SUM = XOR(A, B)
COUT = AND(A, B)
"""

FULL_ADDER_SOLUTION = """# Lab 3: Full Adder
INPUT A B CIN
OUTPUT SUM COUT

P = XOR(A, B)
SUM = XOR(P, CIN)
COUT = OR(AND(A, B), AND(P, CIN))
"""


def _fa(a: int, b: int, c: int) -> dict:
    return {"SUM": (a + b + c) % 2, "COUT": int(a + b + c >= 2)}


FULL_ADDER_TESTS = [
    _ct("test_all_zero", "0+0+0", {"A": 0, "B": 0, "CIN": 0}, _fa(0, 0, 0)),
    _ct("test_only_a", "1+0+0", {"A": 1, "B": 0, "CIN": 0}, _fa(1, 0, 0)),
    _ct("test_only_b", "0+1+0", {"A": 0, "B": 1, "CIN": 0}, _fa(0, 1, 0)),
    _ct("test_only_cin", "0+0+1 — carry-in must reach SUM", {"A": 0, "B": 0, "CIN": 1}, _fa(0, 0, 1)),
    _ct("test_a_and_b", "1+1+0", {"A": 1, "B": 1, "CIN": 0}, _fa(1, 1, 0)),
    _ct("test_carry_propagation", "1+0+1 — carry must propagate", {"A": 1, "B": 0, "CIN": 1}, _fa(1, 0, 1)),
    _ct("test_b_and_cin", "0+1+1", {"A": 0, "B": 1, "CIN": 1}, _fa(0, 1, 1), hidden=True),
    _ct("test_all_ones", "1+1+1", {"A": 1, "B": 1, "CIN": 1}, _fa(1, 1, 1), hidden=True),
]

CIRCUIT_RUBRIC = [
    _r("correctness", "Truth table correctness", "Outputs match the full truth table.", 6),
    _r("design", "Gate-level design", "Sensible decomposition (e.g. half adders), minimal redundant gates.", 3),
    _r("documentation", "Documentation", "Comments explain the design.", 1),
]

# =====================================================================================
# MA201 · Lab 2: Exploratory Data Analysis (notebook · data.ipynb)
# =====================================================================================
EDA_DATASET = """student,branch,score,attempts
S01,CE,78,2
S02,IT,64,3
S03,ENTC,35,5
S04,CE,91,1
S05,IT,47,4
S06,ENTC,58,2
S07,CE,83,2
S08,IT,29,6
S09,ENTC,72,3
S10,CE,66,2
S11,IT,88,1
S12,ENTC,38,4"""

EDA_DESCRIPTION = """## Lab 2: Exploratory Analysis of Lab Scores

Work in **data.ipynb**. The first cell loads a small CSV of student lab scores into `rows`
(a list of dicts). Using only the Python standard library (`csv`, `statistics`):

1. `mean_score` and `median_score` of the `score` column.
2. `branch_avg`: a dict mapping branch → average score, **rounded to 2 decimals**.
3. `at_risk`: **sorted** list of student IDs whose score is **below 40**.

Run all cells, then press **Run Tests**.
"""

EDA_LOAD_CELL = f'''import csv, io, statistics

RAW = """{EDA_DATASET}"""
rows = list(csv.DictReader(io.StringIO(RAW)))
print(len(rows), "rows loaded; columns:", list(rows[0].keys()))'''

EDA_STARTER = notebook(
    [
        ("markdown", "# Lab 2: Exploratory Analysis of Lab Scores\nRun the cell below to load the dataset."),
        ("code", EDA_LOAD_CELL),
        ("markdown", "## Task 1 — central tendency\nCompute `mean_score` and `median_score`."),
        ("code", "# TODO\nmean_score = None\nmedian_score = None\nprint(mean_score, median_score)"),
        ("markdown", "## Task 2 — average score per branch\nBuild `branch_avg` (rounded to 2 decimals)."),
        ("code", "# TODO\nbranch_avg = {}\nprint(branch_avg)"),
        ("markdown", "## Task 3 — students at risk\n`at_risk`: sorted IDs with score < 40."),
        ("code", "# TODO\nat_risk = []\nprint(at_risk)"),
    ]
)

EDA_SOLUTION = notebook(
    [
        ("markdown", "# Lab 2: Exploratory Analysis of Lab Scores"),
        ("code", EDA_LOAD_CELL),
        (
            "code",
            "scores = [int(r['score']) for r in rows]\n"
            "mean_score = statistics.mean(scores)\nmedian_score = statistics.median(scores)\n"
            "print(round(mean_score, 2), median_score)",
        ),
        (
            "code",
            "groups = {}\nfor r in rows:\n    groups.setdefault(r['branch'], []).append(int(r['score']))\n"
            "branch_avg = {b: round(statistics.mean(v), 2) for b, v in groups.items()}\nprint(branch_avg)",
        ),
        ("code", "at_risk = sorted(r['student'] for r in rows if int(r['score']) < 40)\nprint(at_risk)"),
    ]
)

EDA_TESTS = [
    _t(
        "test_mean_score",
        "mean_score is correct (2 dp).",
        "assert mean_score is not None, 'mean_score is not set'\n"
        "assert round(mean_score, 2) == 62.42, f'expected 62.42, got {mean_score}'",
    ),
    _t(
        "test_median_score",
        "median_score is correct.",
        "assert median_score == 65, f'expected 65, got {median_score} (did you convert scores to numbers?)'",
    ),
    _t(
        "test_branch_avg",
        "branch_avg matches per-branch means.",
        "assert branch_avg == {'CE': 79.5, 'IT': 57.0, 'ENTC': 50.75}, f'got {branch_avg}'",
    ),
    _t(
        "test_at_risk",
        "at_risk lists the right students, sorted.",
        "assert at_risk == ['S03', 'S08', 'S12'], f'got {at_risk}'",
    ),
    _t(
        "test_numeric_types",
        "Aggregates are numeric, not strings.",
        "assert all(isinstance(v, (int, float)) for v in branch_avg.values())\n"
        "assert isinstance(mean_score, (int, float))",
        hidden=True,
    ),
]

EDA_RUBRIC = [
    _r("correctness", "Correct analysis", "All computed values are correct.", 6),
    _r("method", "Method", "Uses appropriate standard-library tools; no hard-coded answers.", 2),
    _r("presentation", "Presentation", "Cells are tidy and outputs are readable.", 2),
]

# =====================================================================================
# CS201 · Lab 5: Graph Traversal (coding · draft for the faculty demo)
# =====================================================================================
GRAPH_DESCRIPTION = """## Lab 5: Graph Traversal

Implement `bfs(graph, start)` and `dfs(graph, start)` for an adjacency-list graph
(`dict[int, list[int]]`). Visit neighbours in the order they are listed. Return the visit order.
"""

GRAPH_STARTER = '''from collections import deque


def bfs(graph, start):
    # TODO
    return []


def dfs(graph, start):
    # TODO
    return []
'''

GRAPH_TESTS = [
    _t(
        "test_bfs_order",
        "BFS visits level by level.",
        "g = {1: [2, 3], 2: [4], 3: [4], 4: []}\nassert bfs(g, 1) == [1, 2, 3, 4], f'got {bfs(g, 1)}'",
    ),
    _t(
        "test_dfs_order",
        "DFS goes deep first.",
        "g = {1: [2, 3], 2: [4], 3: [], 4: []}\nassert dfs(g, 1) == [1, 2, 4, 3], f'got {dfs(g, 1)}'",
    ),
    _t(
        "test_cycle",
        "Cycles do not cause infinite loops.",
        "g = {1: [2], 2: [1]}\nassert bfs(g, 1) == [1, 2] and dfs(g, 1) == [1, 2]",
        hidden=True,
    ),
]

GRAPH_RUBRIC = [
    _r("correctness", "Correctness", "Traversal orders are correct.", 6),
    _r("visited", "Visited-set handling", "Handles cycles and disconnected nodes.", 2),
    _r("code_quality", "Code quality", "Readable and idiomatic.", 2),
]

DEFAULT_CODING_RUBRIC = [
    _r("correctness", "Correctness", "Passes visible and hidden tests.", 5),
    _r("edge_cases", "Edge cases", "Handles boundary inputs.", 2),
    _r("code_quality", "Code quality", "Readable, documented, idiomatic.", 2),
    _r("efficiency", "Efficiency", "Appropriate time/space complexity.", 1),
]

# ---------------------------------------------------------------- faculty templates
TEMPLATES: dict[str, dict] = {
    "coding": {
        "description": "## Lab N: <title>\n\nDescribe the task, the functions to implement and the edge cases.\n",
        "starter_files": {
            "main.py": 'def solve(values):\n    """TODO: describe."""\n    return None\n\n\nif __name__ == "__main__":\n    print(solve([3, 1, 2]))\n'
        },
        "test_cases": [
            _t("test_basic", "Basic behaviour.", "assert solve([3, 1, 2]) is not None"),
            _t("test_edge_empty", "Empty input.", "solve([])", hidden=True),
        ],
        "rubric": DEFAULT_CODING_RUBRIC,
    },
    "circuit": {
        "description": "## Lab N: <circuit>\n\nList inputs, outputs and the expected truth table.\n",
        "starter_files": {"circuit.sim": "# Circuit\nINPUT A B\nOUTPUT Y\n\nY = AND(A, B)\n"},
        "test_cases": [
            _ct("test_row_00", "A=0, B=0", {"A": 0, "B": 0}, {"Y": 0}),
            _ct("test_row_11", "A=1, B=1", {"A": 1, "B": 1}, {"Y": 1}),
        ],
        "rubric": CIRCUIT_RUBRIC,
    },
    "notebook": {
        "description": "## Lab N: <analysis>\n\nDescribe the dataset and the variables students must compute.\n",
        "starter_files": {
            "data.ipynb": notebook(
                [
                    ("markdown", "# Analysis"),
                    ("code", "import statistics\ndata = [4, 8, 15, 16, 23, 42]\nresult = None  # TODO"),
                ]
            )
        },
        "test_cases": [
            _t("test_result", "result is the mean of data.", "assert result == statistics.mean(data)"),
        ],
        "rubric": EDA_RUBRIC,
    },
    # worksheet labs need a WorksheetSpec as well (PracticalInput.worksheet); this template is the maths worksheet
    "worksheet": {
        "description": _W.NM_DESCRIPTION,
        "starter_files": {"answers.json": _W.EMPTY_ANSWERS},
        "test_cases": _W.NM_TESTS,
        "rubric": _W.NM_RUBRIC,
        "worksheet": _W.NM_WORKSHEET,
    },
}

# Reference solutions keyed by a stable practical slug (used for seeding + tests).
REFERENCE_SOLUTIONS = {
    "bst": {"main.py": BST_SOLUTION},
    "linked_list": {"main.py": LL_SOLUTION},
    "half_adder": {"circuit.sim": HALF_ADDER_SOLUTION},
    "full_adder": {"circuit.sim": FULL_ADDER_SOLUTION},
    "eda": {"data.ipynb": EDA_SOLUTION},
}


# =====================================================================================
# Seeded integrity case studies for Lab 4 (faculty demo of AI / copy detection)
# =====================================================================================
# A recursive implementation written by one student and copied verbatim by another.
BST_PEER_SOLUTION = '''class Node:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None


class BST:
    def __init__(self):
        self.root = None
        self._size = 0

    def insert(self, key):
        def add(node):
            if node is None:
                self._size += 1
                return Node(key)
            if key < node.key:
                node.left = add(node.left)
            elif key > node.key:
                node.right = add(node.right)
            return node

        self.root = add(self.root)

    def search(self, key):
        def find(node):
            if node is None:
                return False
            if key == node.key:
                return True
            return find(node.left) if key < node.key else find(node.right)

        return find(self.root)

    def inorder(self):
        keys = []

        def visit(node):
            if node is not None:
                visit(node.left)
                keys.append(node.key)
                visit(node.right)

        visit(self.root)
        return keys

    def min(self):
        if self.root is None:
            return None
        node = self.root
        while node.left is not None:
            node = node.left
        return node.key

    def max(self):
        if self.root is None:
            return None
        node = self.root
        while node.right is not None:
            node = node.right
        return node.key

    def height(self):
        def depth(node):
            return 0 if node is None else 1 + max(depth(node.left), depth(node.right))

        return depth(self.root)

    def __len__(self):
        return self._size
'''

# Code with strong hallmarks of AI generation (type hints, Args/Returns docstrings,
# narrative "Step N" comments, em dashes) — far beyond the starter's style.
BST_AI_STYLE = '''from typing import List, Optional


class Node:
    """A node in the binary search tree."""

    def __init__(self, key: int) -> None:
        self.key: int = key
        self.left: Optional["Node"] = None
        self.right: Optional["Node"] = None


class BST:
    """Binary Search Tree implementation that stores unique integer keys.

    Time complexity: O(h) for insert and search, where h is the height of the tree.
    """

    def __init__(self) -> None:
        self.root: Optional[Node] = None
        self._size: int = 0

    def insert(self, key: int) -> None:
        """Insert a key into the BST, ignoring duplicates.

        Args:
            key: The integer key to insert.

        Returns:
            None
        """
        # Edge case: empty tree — the new node becomes the root
        if self.root is None:
            self.root = Node(key)
            self._size += 1
            return
        current = self.root
        while True:
            # Step 1: smaller keys go to the left subtree
            if key < current.key:
                if current.left is None:
                    current.left = Node(key)
                    self._size += 1
                    return
                current = current.left
            # Step 2: larger keys go to the right subtree
            elif key > current.key:
                if current.right is None:
                    current.right = Node(key)
                    self._size += 1
                    return
                current = current.right
            # Step 3: duplicate key — nothing to do
            else:
                return

    def search(self, key: int) -> bool:
        """Search for a key in the BST.

        Args:
            key: The key to look for.

        Returns:
            True if the key exists, otherwise False.
        """
        current = self.root
        while current is not None:
            if key == current.key:
                return True
            current = current.left if key < current.key else current.right
        return False

    def inorder(self) -> List[int]:
        """Return all keys in ascending order using an iterative in-order traversal."""
        result: List[int] = []
        stack: List[Node] = []
        current = self.root
        while stack or current is not None:
            while current is not None:
                stack.append(current)
                current = current.left
            current = stack.pop()
            result.append(current.key)
            current = current.right
        return result

    def min(self) -> Optional[int]:
        """Return the minimum key, or None if the tree is empty."""
        if self.root is None:
            return None
        current = self.root
        while current.left is not None:
            current = current.left
        return current.key

    def max(self) -> Optional[int]:
        """Return the maximum key, or None if the tree is empty."""
        if self.root is None:
            return None
        current = self.root
        while current.right is not None:
            current = current.right
        return current.key

    def height(self) -> int:
        """Return the height of the tree — the number of nodes on the longest root-to-leaf path."""

        def _height(node: Optional[Node]) -> int:
            # Base case: an empty subtree has height 0
            if node is None:
                return 0
            return 1 + max(_height(node.left), _height(node.right))

        return _height(self.root)

    def __len__(self) -> int:
        """Return the number of keys stored in the tree."""
        return self._size
'''
