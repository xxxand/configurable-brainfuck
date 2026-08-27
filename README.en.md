# Configurable Brainfuck

[中文](README.md) | English

A configurable Brainfuck (BF) interpreter implemented with the Python standard library. The default is an unrestricted mode without artificial boundaries, and it can also run in 8-bit standard-compatible modes.

## Features

- The default Tape is a sparse dictionary indexed by signed integers. The pointer can move indefinitely in either direction, and unused Cells read as `0`.
- The default Cell type is Python `int`, so `+` and `-` do not truncate values. Cells can instead use fixed-width bit patterns with modulo `2^N` arithmetic at any configured width.
- Supports the complete BF instruction set: `>`, `<`, `+`, `-`, `.`, `,`, `[`, and `]`.
- Bracket pairs are validated before execution. An unmatched `[` or `]` raises `SyntaxError`.
- Consecutive pointer moves and Cell changes are combined to reduce interpretation overhead. Necessary source-level execution is preserved when a step limit or Tape boundary is enabled.
- There are no artificial Tape, Cell, or pointer limits beyond available memory, execution time, and Python integer resources.

## Cell, I/O, And Debug Views

Fixed-width Cells are bit patterns modulo `2^N`; there is no signed/unsigned Cell mode that affects BF execution. `+`, `-`, `[`, and `]` operate only on the bit pattern and whether it is `0`.

`output_mode` controls only how `.` represents the current Cell and never changes that Cell: `unicode` outputs the value as a Unicode code point, while `byte` outputs `value & 0xFF`. An unbounded Cell with value `1000` therefore produces byte `232` in byte-output mode while the Cell remains `1000`.

The qdb `#` debugger can display an 8-bit pattern as a `signed` number (the default) or an `unsigned` number, such as `-24` or `232` for the same pattern. This is a display option and does not affect BF execution, loop tests, or `.` output.

## Requirements

Python 3.10 or later is required. No third-party dependencies are needed.

## Command Line

Run from the project directory:

```powershell
python brainfuck.py code.b
```

Use the 8-bit standard mode, one-way standard mode, or the common strict 30,000-Cell mode:

```powershell
python brainfuck.py --mode standard code.b
python brainfuck.py --mode standard-one-way code.b
python brainfuck.py --mode strict code.b
```

Frequently used options have short forms: `-m` (mode), `-b` (Cell bit width), `-e` (EOF behavior), `-o` (output mode), `-s` (maximum steps), and `-O` (disable optimization).

```powershell
python brainfuck.py -m strict -s 100000 code.b
python brainfuck.py -b 16 -o byte code.b
```

Use `--optimization-level 0`, `1`, or `2`: `0` executes one instruction at a time, `1` combines consecutive moves and changes (the default), and `2` additionally folds safe `[-]` and `[+]` clear loops in fixed-width wrapping-Cell modes. With `max_steps`, tracing, or profiling enabled, the interpreter preserves the source-level operations needed for exact semantics.

Fine-grained configuration examples:

```powershell
python brainfuck.py --cell-bits 16 --tape-min 0 --tape-max 65535 code.b
python brainfuck.py --mode strict --tape-max unbounded --max-steps 100000 code.b
python brainfuck.py --mode strict --pointer-bounds wrap code.b
```

`code.b` is a Hello World example and prints:

```text
Hello World!
```

The interpreter reads one standard-input character only when the BF program executes `,`. Programs without `,` do not wait for input. For example:

```powershell
python brainfuck.py input.b
```

If `input.b` contains `,.`, enter one character and press Enter; the program outputs that character. If input is exhausted and a later `,` executes, the default behavior writes `0` to the current Cell.

## Import As A Module

```python
from brainfuck import interpret

sourcecode = """
    ++++++++++[>+++++++>++++++++++>+++>+<<<<-]
    >++.>+.+++++++..+++.>++.<<+++++++++++++++.
    >.+++.------.--------.>+.>.
"""

print(interpret(sourcecode), end="")
```

`interpret(sourcecode, input_data="")` returns the BF program's complete output string. Characters in `input_data` are consumed in order by `,` and written to Cells as Unicode code points.

Runtime settings are keyword-only arguments:

```python
# 8-bit wrapping Cells, one-way Tape, 30,000 Cells.
interpret(sourcecode, mode="strict")

# 16-bit wrapping Cells, one-way Tape, 65,536 Cells.
interpret(sourcecode, cell_bits=16, tape_min=0, tape_max=65535)

# Keep unbounded Cells, but run at most 100,000 BF instructions.
interpret(sourcecode, max_steps=100_000)

# Wrap a finite Tape pointer: moving left from 0 goes to 29999.
interpret(sourcecode, mode="strict", pointer_bounds="wrap")

# Enable /* ... */ block comments and qdb's # debugging extension.
interpret(sourcecode, mode="strict", comment_style="block", debug_command="qdb")

# O0 executes one instruction at a time; O1 is the default; O2 safely optimizes clear loops.
interpret(sourcecode, optimization_level=0)
```

`interpret()` and `compile_to_python()` share the same `optimize` and `optimization_level` interface. `optimize=False` is equivalent to `optimization_level=0`; O1 is the default, and O2 optimizes `[-]` and `[+]` only for fixed-width wrapping Cells. Both disable combinations that would skip original steps or intermediate bounds checks when `max_steps` or bounded Tape is enabled.

```python
from brainfuck import compile_to_python

generated = compile_to_python(sourcecode, mode="strict", optimization_level=2)
```

## Semantics

- Non-BF characters are ignored, so source can include whitespace and comments.
- The default `unicode` output mode interprets the current Cell as a Unicode code point; an invalid code point raises `ValueError`. The `byte` mode outputs the Cell's low 8 bits.
- The default EOF behavior for `,` writes `0`; `eof_mode="unchanged"` retains the previous value and `eof_mode="error"` raises an exception.
- `[` skips to just after its matching `]` when the current Cell is `0`; `]` jumps to just after its matching `[` when the current Cell is nonzero.

See [SEMANTICS.en.md](SEMANTICS.en.md) for the complete definition of modes, options, instruction behavior, exceptions, and step counting.

## Debugging And Observability

`--trace` writes execution details to standard error and leaves BF program standard output clean. `--trace-format jsonl` emits stable JSON Lines, and `--trace-file` writes the trace to a separate file.

```powershell
python brainfuck.py --trace code.b
python brainfuck.py --trace --trace-format jsonl --trace-file trace.jsonl code.b
python brainfuck.py --profile --dump-ir code.b
```

`--profile` writes JSON to standard error with original instruction steps, elapsed time, pointer range, nonzero Cell count, and operation counts. `--dump-ir` shows internal operations, combined runs, jump targets, and source locations. With `--trace` or `--profile`, moves and changes are not combined so observations remain source-accurate.

Standard-compatible modes (`standard`, `standard-one-way`, and `strict`) use raw byte streams for CLI I/O. The module API's `interpret_bytes()` provides the same binary semantics; `interpret()` accepts only ASCII text input in byte-output modes.

## Optional Extensions

By default, only the eight BF instructions are active, so `#` and `/* ... */` do not change existing program behavior. Two nonstandard extensions can be enabled explicitly:

```powershell
python brainfuck.py -m strict --comment-style block --debug-command qdb code.b
```

- `comment_style="block"` removes non-nested `/* ... */` blocks, so BF instructions inside them do not execute. An unclosed block reports its original source location.
- `debug_command="qdb"` recognizes `#` as Daniel B. Cristofani's `qdb.c` debugging instruction: it outputs the first 64 Cells and a pointer `^`. This extension requires 8-bit wrapping Cells and writes to BF program standard output. `debug_number_format="signed"` (default) or `"unsigned"` changes only the displayed numbers.

## Compile To Python

`compile_to_python(sourcecode, optimize=True, optimization_level=None)` returns standalone Python program text that depends only on the Python standard library. Generated scripts embed BF source, the selected configuration, and compiled `OPERATIONS` IR. O0 emits one operation per original instruction, O1 combines consecutive operations while retaining original step counts, and O2 emits `clear` operations when safe. Generated scripts do not provide the interpreter's runtime `trace` or `profile` callbacks.

Use `--compile-python [OUTPUT] code.b` on the command line. With no `OUTPUT`, generated code goes to standard output; with an output path, it is written to that file:

```powershell
python brainfuck.py --compile-python code.b > program.py
python brainfuck.py --compile-python program.py code.b
python brainfuck.py --compile-python code.b | python
```

When interpreting BF, program results always go to standard output. Use shell redirection to save them, for example `python brainfuck.py code.b > result.bin`.

## Format Source Code

`bf_formatter.py` keeps consecutive non-bracket BF instructions in one instruction block; `[` and `]`, plus `#` when qdb is enabled, occupy their own lines and define indentation. Ignored text on an instruction's source line becomes a trailing annotation two spaces after that instruction; text on its own line remains standalone. With block-comment mode enabled, `/* ... */` retains its line count and relative indentation.

```powershell
python bf_formatter.py code.b
python bf_formatter.py -o formatted.b code.b
python bf_formatter.py --in-place code.b
python bf_formatter.py --comment-style block --debug-command qdb code.b
```

Import it as a module:

```python
from bf_formatter import format_source

formatted = format_source(sourcecode, comment_style="block", debug_command="qdb")
```

## Browser Frontend

`web/` is a browser workbench with no build step. It calls a local Python API backed by the project's actual interpreter, formatter, and generator. Start it and open `http://localhost:8000`:

```powershell
python bf_web.py
```

The frontend provides source editing, modes and runtime configuration, input/output, formatting, qdb debugging, IR, tracing, profiling, and standalone Python generation. All BF execution uses the local Python runtime, so browser and Python interpreter semantics cannot drift apart. Source, input, runtime settings, and the active Inspect tab are restored from browser LocalStorage; output and execution records are not restored.

## Tests

```powershell
python -m unittest -v
```

The test suite covers imports, command-line execution, lazy CLI input, standard modes, bidirectional and bounded Tape configurations, bit-width wrapping, EOF, loops, input, bracket errors, and step limits. Fixed-seed randomized differential tests compare O0/O1/O2 with an independent raw 8-bit reference machine; `tests/external/` also contains an attributed Brainfuck.org regression sample.

## References

- [Brainfuck.org](https://brainfuck.org/)
- [Wikipedia: Brainfuck](https://en.wikipedia.org/wiki/Brainfuck)
