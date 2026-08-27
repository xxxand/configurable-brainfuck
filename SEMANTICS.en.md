# Brainfuck Semantic Matrix

[中文](SEMANTICS.md)

This document is the interpreter's normative behavioral definition. Matrix cases in the test file use the same category and ID prefixes so that the documentation and implementation do not diverge.

## Configuration

The default `interpret()` mode, `mode="unlimited"`, preserves unrestricted semantics. The other modes are compatibility presets:

| Mode | `cell_mode` | `cell_bits` | `tape_min` | `tape_max` | `eof_mode` | `output_mode` |
|---|---|---:|---:|---:|---|---|
| `unlimited` | `unbounded` | none | none | none | `zero` | `unicode` |
| `standard` | `wrap` | 8 | none | none | `zero` | `byte` |
| `standard-one-way` | `wrap` | 8 | 0 | none | `zero` | `byte` |
| `strict` | `wrap` | 8 | 0 | 29999 | `zero` | `byte` |

Non-`None` fine-grained arguments override the preset. `cell_bits`, `tape_min`, and `tape_max` accept the string `"unbounded"` to explicitly remove the corresponding preset limit; `None` inherits the preset.

When `cell_mode="wrap"` is explicitly selected without an inheritable `cell_bits` value, the interpreter defaults to 8-bit Cells. Explicit `cell_mode="unbounded"` cancels an inherited bit width. Changing Cell mode alone does not change a preset's output mode.

| Parameter | Values | Rule |
|---|---|---|
| `cell_mode` | `unbounded`, `wrap` | `unbounded` uses Python `int`; `wrap` uses unsigned modular arithmetic. |
| `cell_bits` | positive integer, `unbounded`, `None` | The `wrap` range is `0..2**bits-1`. |
| `tape_min` | integer, `unbounded`, `None` | Minimum allowed pointer position. |
| `tape_max` | integer, `unbounded`, `None` | Maximum allowed pointer position. |
| `eof_mode` | `zero`, `unchanged`, `error` | Behavior of `,` when input is exhausted. |
| `output_mode` | `unicode`, `byte` | Text encoding semantics of `.`. |
| `max_steps` | non-negative integer, `None` | Limit on executed original BF instructions. |
| `optimize` | `True`, `False` | Whether to combine consecutive operations without changing semantics. |

The initial pointer is always `0`, so configured ranges must include `0`. A `tape_min` greater than `tape_max`, a range excluding `0`, or conflicting Cell parameters raises `ValueError`.

## Instruction Matrix

| Instruction | Unbounded Cell | Wrap Cell | Pointer / I/O behavior |
|---|---|---|---|
| `>` | unchanged | unchanged | Increments the pointer; exceeding `tape_max` raises `TapeBoundsError`. |
| `<` | unchanged | unchanged | Decrements the pointer; going below `tape_min` raises `TapeBoundsError`. |
| `+` | Increments without an upper bound | Increments modulo `2**cell_bits` | An unused Cell starts at `0`. |
| `-` | Decrements without a lower bound | Decrements modulo `2**cell_bits` | With 8-bit Cells, `0 - 1` becomes `255`. |
| `.` | The value must be a Unicode code point or `ValueError` is raised | Same unless byte output is selected | `byte` outputs the character for the Cell's low 8 bits. |
| `,` | Writes the input character's Unicode code point | Writes then wraps modulo `2**cell_bits` | Input exhaustion is governed by `eof_mode`. |
| `[` | Skips the matching `]` when the current Cell is `0` | Same | Brackets must match. |
| `]` | Jumps to after the matching `[` when the current Cell is nonzero | Same | Brackets must match. |

All non-BF characters are ignored. Whitespace and comments do not affect semantics beyond their source locations.

## EOF Matrix

| `eof_mode` | Behavior when `,` cannot read a character |
|---|---|
| `zero` | Writes `0` to the current Cell. |
| `unchanged` | Leaves the current Cell unchanged. |
| `error` | Raises `EOFInputError`. |

In command-line mode, standard input's `read(1)` is called only when `,` actually executes. A program without `,` never waits for input.

## Step Matrix

| Source | Executed source instructions | Notes |
|---|---:|---|
| `++++` | 4 | Every `+` counts separately even when optimized into one operation. |
| `+-.` | 3 before completion | `+`, `-`, and `.` each count as one step. |
| `+[.-]` | 5 | The first `+`, `[`, `.`, `-`, and `]` each count as one step. |
| non-BF characters | 0 | Comments and whitespace do not count as steps. |

When `max_steps` is `N`, the interpreter executes at most `N` original BF instructions. Before the `N + 1` instruction, it raises `StepLimitExceeded`; the exception's `executed_steps` is the number of completed steps. With a step limit enabled, the interpreter does not combine `+`, `-`, `>`, or `<`, ensuring the count matches execution with optimization disabled.

## Matrix Cases

| ID | Source / configuration | Expected result |
|---|---|---|
| `U-CELL-01` | `+` repeated 256 times, unlimited mode | Unicode character U+0100, not byte wrap. |
| `U-TAPE-01` | `<+.>+.` | Both negative and positive pointer positions read and write. |
| `S-CELL-01` | `+` repeated 256 times, standard mode | NUL output after 8-bit wrap. |
| `S-CELL-02` | `-[-].`, standard mode | NUL output; `[-]` clears wrapped byte value 255. |
| `S-INPUT-01` | `,.`, standard mode, U+0100 input | NUL output after 8-bit input conversion. |
| `C-CELL-01` | 16 `+`, `cell_bits=4` | NUL output after 4-bit wrap. |
| `C-EOF-01` | `+,.`, `eof_mode=unchanged` | SOH output. |
| `C-OUTPUT-01` | `-.`, `output_mode=byte` | Byte value 255 output. |
| `B-TAPE-01` | `<`, `standard-one-way` | `TapeBoundsError`. |
| `B-TAPE-02` | `>` repeated 30000 times, strict mode | `TapeBoundsError`. |
| `B-EOF-01` | `,`, `eof_mode=error` | `EOFInputError`. |
| `L-STEPS-01` | `++++.`, `max_steps=4` | `StepLimitExceeded(executed_steps=4)`. |
