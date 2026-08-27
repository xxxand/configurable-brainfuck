# Brainfuck Semantic Matrix

[中文](SEMANTICS.md) | English

This document is the interpreter's normative behavioral definition. Matrix cases in the test file use the same category and ID prefixes so that the documentation and implementation do not diverge.

## Configuration

The default `interpret()` mode, `mode="unlimited"`, preserves unrestricted semantics. The other modes are compatibility presets:

| Mode | `cell_mode` | `cell_bits` | `tape_min` | `tape_max` | `pointer_bounds` | `eof_mode` | `output_mode` | `comment_style` | `debug_command` |
|---|---|---:|---:|---:|---|---|---|---|---|
| `unlimited` | `unbounded` | none | none | none | `error` | `zero` | `unicode` | `none` | `none` |
| `standard` | `wrap` | 8 | none | none | `error` | `zero` | `byte` | `none` | `none` |
| `standard-one-way` | `wrap` | 8 | 0 | none | `error` | `zero` | `byte` | `none` | `none` |
| `strict` | `wrap` | 8 | 0 | 29999 | `error` | `zero` | `byte` | `none` | `none` |

Non-`None` fine-grained arguments override the preset. `cell_bits`, `tape_min`, and `tape_max` accept the string `"unbounded"` to explicitly remove the corresponding preset limit; `None` inherits the preset.

When `cell_mode="wrap"` is explicitly selected without an inheritable `cell_bits` value, the interpreter defaults to 8-bit Cells. Explicit `cell_mode="unbounded"` cancels an inherited bit width. Changing Cell mode alone does not change a preset's output mode.

| Parameter | Values | Rule |
|---|---|---|
| `cell_mode` | `unbounded`, `wrap` | `unbounded` uses Python `int`; `wrap` uses unsigned modular arithmetic. |
| `cell_bits` | positive integer, `unbounded`, `None` | The `wrap` range is `0..2**bits-1`. |
| `tape_min` | integer, `unbounded`, `None` | Minimum allowed pointer position. |
| `tape_max` | integer, `unbounded`, `None` | Maximum allowed pointer position. |
| `pointer_bounds` | `error`, `wrap` | Raise at a finite Tape boundary or wrap to the opposite end. |
| `eof_mode` | `zero`, `unchanged`, `error` | Behavior of `,` when input is exhausted. |
| `output_mode` | `unicode`, `byte` | Text encoding semantics of `.`. |
| `comment_style` | `none`, `block` | Whether to preprocess non-nested `/* ... */` blocks. |
| `debug_command` | `none`, `qdb` | Whether `#` is a qdb debugging instruction. |
| `max_steps` | non-negative integer, `None` | Limit on executed original BF instructions. |
| `optimize` | `True`, `False` | Whether to combine consecutive operations without changing semantics. |

The initial pointer is always `0`, so configured ranges must include `0`. A `tape_min` greater than `tape_max`, a range excluding `0`, or conflicting Cell parameters raises `ValueError`.

`pointer_bounds="wrap"` is valid only when both `tape_min` and `tape_max` are finite. A half-unbounded or bidirectionally unbounded Tape has no opposite end to wrap to and raises `ValueError`. The default, `error`, preserves the existing out-of-bounds error behavior for every mode.

## Instruction Matrix

| Instruction | Unbounded Cell | Wrap Cell | Pointer / I/O behavior |
|---|---|---|---|
| `>` | unchanged | unchanged | Increments the pointer; exceeding `tape_max` raises `TapeBoundsError` or wraps to `tape_min` according to `pointer_bounds`. |
| `<` | unchanged | unchanged | Decrements the pointer; going below `tape_min` raises `TapeBoundsError` or wraps to `tape_max` according to `pointer_bounds`. |
| `+` | Increments without an upper bound | Increments modulo `2**cell_bits` | An unused Cell starts at `0`. |
| `-` | Decrements without a lower bound | Decrements modulo `2**cell_bits` | With 8-bit Cells, `0 - 1` becomes `255`. |
| `.` | The value must be a Unicode code point or `ValueError` is raised | Same unless byte output is selected | `byte` outputs the character for the Cell's low 8 bits. |
| `,` | Writes the input character's Unicode code point | Writes then wraps modulo `2**cell_bits` | Input exhaustion is governed by `eof_mode`. |
| `[` | Skips the matching `]` when the current Cell is `0` | Same | Brackets must match. |
| `]` | Jumps to after the matching `[` when the current Cell is nonzero | Same | Brackets must match. |

By default, all non-BF characters, including `#`, are ignored. `comment_style="block"` first replaces non-nested `/* ... */` blocks with equal-length whitespace while retaining source locations; an unclosed block raises `SyntaxError`. `debug_command="qdb"` makes `#` a ninth extension instruction, requires 8-bit wrapping Cells, and writes qdb's blank line, signed-byte Cell view for indexes `0..63`, and pointer `^` to program output. Original qdb leaves negative pointers undefined; this project anchors `^` at the left margin in that case. Both extensions are disabled by default.

## EOF Matrix

| `eof_mode` | Behavior when `,` cannot read a character |
|---|---|
| `zero` | Writes `0` to the current Cell. |
| `unchanged` | Leaves the current Cell unchanged. |
| `error` | Raises `EOFInputError`. |

In command-line mode, standard input's `read(1)` is called only when `,` actually executes. A program without `,` never waits for input.

In `standard`, `standard-one-way`, and `strict` modes, the CLI reads and writes raw byte streams. `interpret_bytes()` is the equivalent byte-oriented module API. In these modes, `interpret()` accepts only ASCII text input; other text input raises `ValueError`.

## Trace, Profile, And IR

By default, `--trace` writes the `step`, source location, internal operation, argument, pointer, and current Cell to standard error. `--trace-format jsonl` emits one JSON object with the same fields per line, and `--trace-file` redirects it to a file. `--profile` writes JSON to standard error with `steps`, `elapsed_seconds`, `pointer_min`, `pointer_max`, `nonzero_cells`, and `instruction_counts`. `--dump-ir` shows compiled operations and their source locations.

With trace or profiling enabled, pointer moves and Cell changes are not combined so events and pointer ranges correspond to original BF instructions.

## Optimization And Code Generation

`--optimization-level 0` executes original BF instructions one at a time. Level `1` (the default) combines consecutive `+` / `-`, and combines consecutive `>` / `<` when there are no Tape bounds, step limit, trace, or profile. Level `2` folds loops exactly matching `[-]` or `[+]` into a clear operation only with fixed-width `wrap` Cells and no step limit, trace, or profile. This optimization is not used for unbounded integer Cells because negative values may not terminate.

`compile_to_python()` and `--compile-python [OUTPUT] code.b` generate a standalone Python script. Without `OUTPUT`, the script is written to standard output; otherwise it is written to the target path. Generated scripts embed the resolved configuration and `OPERATIONS` IR: O0 has one operation per original instruction, O1 combines consecutive operations while preserving their original step count, and O2 adds `clear` operations when eligible. With `max_steps` or bounded Tape, the generator disables combinations that would affect exact step counting or intermediate bounds checks.

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
| `S-INPUT-01` | `,.`, standard mode, byte input `255` | Byte value `255` output. The text API rejects non-ASCII input. |
| `C-CELL-01` | 16 `+`, `cell_bits=4` | NUL output after 4-bit wrap. |
| `C-EOF-01` | `+,.`, `eof_mode=unchanged` | SOH output. |
| `C-OUTPUT-01` | `-.`, `output_mode=byte` | Byte value 255 output. |
| `B-TAPE-01` | `<`, `standard-one-way` | `TapeBoundsError`. |
| `B-TAPE-02` | `>` repeated 30000 times, strict mode | `TapeBoundsError`. |
| `B-EOF-01` | `,`, `eof_mode=error` | `EOFInputError`. |
| `L-STEPS-01` | `++++.`, `max_steps=4` | `StepLimitExceeded(executed_steps=4)`. |

## Verification Strategy

In addition to semantic-matrix cases, the test suite uses a fixed random seed to generate terminating 8-bit programs and compares O0, O1, and O2 results with an independent one-instruction-at-a-time reference machine. `tests/external/brainfuck.org-obscure-problems.bf` is sourced from Daniel B. Cristofani's [Brainfuck.org implementation tests](https://brainfuck.org/tests.b) for external regression coverage.
