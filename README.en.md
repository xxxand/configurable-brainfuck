# Unlimited Brainfuck Interpreter

[中文](README.md)

A single-file, configurable Brainfuck (BF) interpreter implemented with the Python standard library. The default is an unrestricted mode without artificial boundaries, and it can also run in 8-bit standard-compatible modes.

## Features

- The default Tape is a sparse dictionary indexed by signed integers. The pointer can move indefinitely in either direction, and unused Cells read as `0`.
- The default Cell type is Python `int`, so `+` and `-` do not truncate values. Cells can instead use unsigned wrapping arithmetic at any configured bit width.
- Supports the complete BF instruction set: `>`, `<`, `+`, `-`, `.`, `,`, `[`, and `]`.
- Bracket pairs are validated before execution. An unmatched `[` or `]` raises `SyntaxError`.
- Consecutive pointer moves and Cell changes are combined to reduce interpretation overhead. Necessary source-level execution is preserved when a step limit or Tape boundary is enabled.
- There are no artificial Tape, Cell, or pointer limits beyond available memory, execution time, and Python integer resources.

## Requirements

Python 3.10 or later is required. No third-party dependencies are needed.

## Command Line

Run from the project directory:

```powershell
python brainfuck.py code.bf
```

Use the 8-bit standard mode, one-way standard mode, or the common strict 30,000-Cell mode:

```powershell
python brainfuck.py --mode standard code.bf
python brainfuck.py --mode standard-one-way code.bf
python brainfuck.py --mode strict code.bf
```

Frequently used options have short forms: `-m` (mode), `-b` (Cell bit width), `-e` (EOF behavior), `-o` (output mode), `-s` (maximum steps), and `-O` (disable optimization).

```powershell
python brainfuck.py -m strict -s 100000 code.bf
python brainfuck.py -b 16 -o byte code.bf
```

Fine-grained configuration examples:

```powershell
python brainfuck.py --cell-bits 16 --tape-min 0 --tape-max 65535 code.bf
python brainfuck.py --mode strict --tape-max unbounded --max-steps 100000 code.bf
```

`code.bf` is a Hello World example and prints:

```text
Hello World!
```

The interpreter reads one standard-input character only when the BF program executes `,`. Programs without `,` do not wait for input. For example:

```powershell
python brainfuck.py input.bf
```

If `input.bf` contains `,.`, enter one character and press Enter; the program outputs that character. If input is exhausted and a later `,` executes, the default behavior writes `0` to the current Cell.

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
```

## Semantics

- Non-BF characters are ignored, so source can include whitespace and comments.
- The default `unicode` output mode interprets the current Cell as a Unicode code point; an invalid code point raises `ValueError`. The `byte` mode outputs the Cell's low 8 bits.
- The default EOF behavior for `,` writes `0`; `eof_mode="unchanged"` retains the previous value and `eof_mode="error"` raises an exception.
- `[` skips to just after its matching `]` when the current Cell is `0`; `]` jumps to just after its matching `[` when the current Cell is nonzero.

See [SEMANTICS.en.md](SEMANTICS.en.md) for the complete definition of modes, options, instruction behavior, exceptions, and step counting.

## Tests

```powershell
python -m unittest -v
```

The test suite covers imports, command-line execution, lazy CLI input, standard modes, bidirectional and bounded Tape configurations, bit-width wrapping, EOF, loops, input, bracket errors, and step limits.
