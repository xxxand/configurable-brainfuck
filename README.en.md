# Configurable Brainfuck

[中文](README.md) | English

A configurable Brainfuck interpreter, formatter, Python generator, and local web workbench built with the Python standard library. The default uses an unbounded bidirectional Tape and arbitrary-precision Cells, with classic 8-bit compatibility modes available.

## Features

- Supports the complete BF instruction set: `>`, `<`, `+`, `-`, `.`, `,`, `[`, and `]`.
- Provides `unlimited`, `standard`, `standard-one-way`, and `strict` runtime profiles.
- Configures Cell width, Tape bounds, EOF, output mode, step limits, and optimization levels.
- Provides tracing, profiling, IR output, qdb `#` debugging, block comments, and Python code generation.
- Includes a CLI, module API, formatter, and local browser workbench.

Fixed-width Cells are bit patterns modulo `2^N`; `.`, qdb `#`, and debugger number formats only control I/O or presentation, never Cell execution semantics. See [SEMANTICS.en.md](SEMANTICS.en.md) for the complete definition.

## Requirements

Python 3.10 or later is required. No third-party dependencies are needed.

## Quick Start

Run the example:

```powershell
python brainfuck.py code.b
```

Use the module API:

```python
from brainfuck import interpret

print(interpret("++++++++++[>+++++++>++++++++++>+++>+<<<<-]>++.>+.+++++++..+++.>++.<<+++++++++++++++.>.+++.------.--------.>+.>."), end="")
```

Use classic 8-bit semantics:

```powershell
python brainfuck.py --mode strict code.b
```

## Configuration

`unlimited` uses arbitrary-precision Cells and a bidirectional unbounded Tape; `standard` uses 8-bit Cells; `standard-one-way` prevents the pointer from moving below `0`; `strict` uses 30,000 one-way 8-bit Cells. See [SEMANTICS.en.md](SEMANTICS.en.md) for the full parameter table and Cell, Tape, EOF, step, and I/O rules.

```python
from brainfuck import interpret

interpret(sourcecode, mode="strict", max_steps=100_000)
```

## Tools

Format BF source:

```powershell
python bf_formatter.py --in-place code.b
```

Generate a standalone Python script:

```powershell
python brainfuck.py --compile-python program.py code.b
```

Start the local web workbench:

```powershell
python bf_web.py
```

Then open `http://127.0.0.1:8000`. The workbench uses the local Python API for execution, formatting, and code generation, and stores source, input, and runtime settings in browser LocalStorage.

## Debugging And Extensions

```powershell
python brainfuck.py --trace --profile --dump-ir code.b
python brainfuck.py -m strict --comment-style block --debug-command qdb code.b
```

`--trace-format jsonl` provides machine-readable tracing. `comment_style="block"` enables `/* ... */`, and `debug_command="qdb"` enables the `#` debugging instruction. Full rules are in [SEMANTICS.en.md](SEMANTICS.en.md).

## Tests

```powershell
python -m unittest -v
```

The suite includes semantic-matrix cases, randomized differential testing, and an external Brainfuck.org regression sample.

## References

- [Brainfuck.org](https://brainfuck.org/)
- [Wikipedia: Brainfuck](https://en.wikipedia.org/wiki/Brainfuck)
