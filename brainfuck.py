"""A configurable Brainfuck interpreter with unrestricted defaults."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


COMMANDS = frozenset("><+-.,[]")
UNBOUNDED = "unbounded"


class TapeBoundsError(IndexError):
    """Raised when a pointer movement leaves the configured Tape range."""

    def __init__(self, pointer: int, tape_min: int | None, tape_max: int | None, location: str) -> None:
        self.pointer = pointer
        self.tape_min = tape_min
        self.tape_max = tape_max
        super().__init__(f"pointer {pointer} is outside Tape range [{tape_min}, {tape_max}] at {location}")


class StepLimitExceeded(RuntimeError):
    """Raised before executing an instruction beyond ``max_steps``."""

    def __init__(self, max_steps: int, executed_steps: int, location: str) -> None:
        self.max_steps = max_steps
        self.executed_steps = executed_steps
        super().__init__(f"maximum step count {max_steps} reached after {executed_steps} steps at {location}")


class EOFInputError(EOFError):
    """Raised when a ',' instruction reads beyond input in ``error`` EOF mode."""


@dataclass(frozen=True)
class _RuntimeConfig:
    cell_mode: str
    cell_bits: int | None
    tape_min: int | None
    tape_max: int | None
    eof_mode: str
    output_mode: str


@dataclass(frozen=True)
class _Operation:
    kind: str
    argument: int
    step_count: int
    source_offset: int


PROFILES = {
    "unlimited": _RuntimeConfig(UNBOUNDED, None, None, None, "zero", "unicode"),
    "standard": _RuntimeConfig("wrap", 8, None, None, "zero", "byte"),
    "standard-one-way": _RuntimeConfig("wrap", 8, 0, None, "zero", "byte"),
    "strict": _RuntimeConfig("wrap", 8, 0, 29999, "zero", "byte"),
}


def _location(sourcecode: str, offset: int) -> str:
    line = sourcecode.count("\n", 0, offset) + 1
    column = offset - sourcecode.rfind("\n", 0, offset)
    return f"line {line}, column {column}"


def _filter_program(sourcecode: str) -> tuple[str, list[int]]:
    """Return BF commands and their offsets in the original source text."""
    commands: list[str] = []
    offsets: list[int] = []
    for offset, character in enumerate(sourcecode):
        if character in COMMANDS:
            commands.append(character)
            offsets.append(offset)
    return "".join(commands), offsets


def _build_jumps(program: str, offsets: list[int], sourcecode: str) -> dict[int, int]:
    """Return matching bracket positions, reporting original source locations."""
    stack: list[int] = []
    jumps: dict[int, int] = {}
    for position, command in enumerate(program):
        if command == "[":
            stack.append(position)
        elif command == "]":
            if not stack:
                raise SyntaxError(f"unmatched ']' at {_location(sourcecode, offsets[position])}")
            opening = stack.pop()
            jumps[opening] = position
            jumps[position] = opening
    if stack:
        opening = stack[-1]
        raise SyntaxError(f"unmatched '[' at {_location(sourcecode, offsets[opening])}")
    return jumps


def _compile(sourcecode: str, optimize_moves: bool, optimize_additions: bool) -> list[_Operation]:
    """Compile source into operations while retaining original source offsets."""
    program, offsets = _filter_program(sourcecode)
    jumps = _build_jumps(program, offsets, sourcecode)
    operations: list[_Operation] = []
    brackets: dict[int, int] = {}
    position = 0

    while position < len(program):
        command = program[position]
        if command in "><" and optimize_moves:
            start = position
            delta = 0
            while position < len(program) and program[position] in "><":
                delta += 1 if program[position] == ">" else -1
                position += 1
            if delta:
                operations.append(_Operation("move", delta, position - start, offsets[start]))
            continue
        if command in "+-" and optimize_additions:
            start = position
            delta = 0
            while position < len(program) and program[position] in "+-":
                delta += 1 if program[position] == "+" else -1
                position += 1
            if delta:
                operations.append(_Operation("add", delta, position - start, offsets[start]))
            continue

        kinds = {">": "move", "<": "move", "+": "add", "-": "add", ".": "output", ",": "input"}
        if command in kinds:
            argument = 1 if command in ">+" else -1 if command in "<-" else 0
            operations.append(_Operation(kinds[command], argument, 1, offsets[position]))
        elif command == "[":
            brackets[position] = len(operations)
            operations.append(_Operation("jump_if_zero", 0, 1, offsets[position]))
        else:
            brackets[position] = len(operations)
            operations.append(_Operation("jump_if_nonzero", 0, 1, offsets[position]))
        position += 1

    for position, target in jumps.items():
        operation = operations[brackets[position]]
        operations[brackets[position]] = _Operation(
            operation.kind, brackets[target], operation.step_count, operation.source_offset
        )
    return operations


def _validate_positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _resolve_bound(value: int | str | None, inherited: int | None, name: str) -> int | None:
    if value is None:
        return inherited
    if value == UNBOUNDED:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, '{UNBOUNDED}', or None")
    return value


def _resolve_config(
    mode: str, cell_mode: str | None, cell_bits: int | str | None,
    tape_min: int | str | None, tape_max: int | str | None,
    eof_mode: str | None, output_mode: str | None,
) -> _RuntimeConfig:
    if mode not in PROFILES:
        raise ValueError(f"mode must be one of: {', '.join(PROFILES)}")
    profile = PROFILES[mode]
    resolved_cell_mode = profile.cell_mode if cell_mode is None else cell_mode
    if resolved_cell_mode not in (UNBOUNDED, "wrap"):
        raise ValueError(f"cell_mode must be '{UNBOUNDED}' or 'wrap'")
    if cell_bits is None:
        resolved_cell_bits = None if cell_mode == UNBOUNDED else profile.cell_bits
    elif cell_bits == UNBOUNDED:
        if cell_mode == "wrap":
            raise ValueError("cell_bits='unbounded' conflicts with cell_mode='wrap'")
        resolved_cell_bits = None
        if cell_mode is None:
            resolved_cell_mode = UNBOUNDED
    else:
        resolved_cell_bits = _validate_positive_integer(cell_bits, "cell_bits")
        if cell_mode is None:
            resolved_cell_mode = "wrap"
    if resolved_cell_mode == "wrap" and resolved_cell_bits is None:
        resolved_cell_bits = 8
    if resolved_cell_mode == UNBOUNDED and resolved_cell_bits is not None:
        raise ValueError("cell_bits requires cell_mode='wrap'")

    resolved_tape_min = _resolve_bound(tape_min, profile.tape_min, "tape_min")
    resolved_tape_max = _resolve_bound(tape_max, profile.tape_max, "tape_max")
    if resolved_tape_min is not None and resolved_tape_max is not None and resolved_tape_min > resolved_tape_max:
        raise ValueError("tape_min cannot be greater than tape_max")
    if resolved_tape_min is not None and resolved_tape_min > 0:
        raise ValueError("tape_min must allow the initial pointer position 0")
    if resolved_tape_max is not None and resolved_tape_max < 0:
        raise ValueError("tape_max must allow the initial pointer position 0")
    resolved_eof_mode = profile.eof_mode if eof_mode is None else eof_mode
    if resolved_eof_mode not in ("zero", "unchanged", "error"):
        raise ValueError("eof_mode must be 'zero', 'unchanged', or 'error'")
    resolved_output_mode = profile.output_mode if output_mode is None else output_mode
    if resolved_output_mode not in ("unicode", "byte"):
        raise ValueError("output_mode must be 'unicode' or 'byte'")
    return _RuntimeConfig(resolved_cell_mode, resolved_cell_bits, resolved_tape_min, resolved_tape_max,
                          resolved_eof_mode, resolved_output_mode)


def _store_cell(tape: dict[int, int], pointer: int, value: int, config: _RuntimeConfig) -> None:
    if config.cell_mode == "wrap":
        value %= 1 << config.cell_bits
    if value:
        tape[pointer] = value
    else:
        tape.pop(pointer, None)


def _is_clear_loop(operations: list[_Operation], instruction: int) -> bool:
    """Return whether operations at *instruction* are exactly ``[-]`` or ``[+]``."""
    if instruction + 2 >= len(operations):
        return False
    opening, change, closing = operations[instruction : instruction + 3]
    return (
        opening.kind == "jump_if_zero"
        and opening.argument == instruction + 2
        and change.kind == "add"
        and abs(change.argument) == 1
        and change.step_count == 1
        and closing.kind == "jump_if_nonzero"
        and closing.argument == instruction
    )


def _resolve_optimization_level(optimize: bool, optimization_level: int | None) -> int:
    if not isinstance(optimize, bool):
        raise ValueError("optimize must be a boolean")
    if optimization_level is None:
        return 1 if optimize else 0
    if isinstance(optimization_level, bool) or optimization_level not in (0, 1, 2):
        raise ValueError("optimization_level must be 0, 1, 2, or None")
    if not optimize and optimization_level != 0:
        raise ValueError("optimization_level conflicts with optimize=False")
    return optimization_level


def _execute(
    sourcecode: str, input_data: str | bytes, input_reader: Callable[[], str | bytes] | None,
    config: _RuntimeConfig, max_steps: int | None, optimization_level: int,
    trace: Callable[[dict[str, object]], None] | None, profile: dict[str, object] | None,
) -> str | bytes:
    optimize_moves = (
        optimization_level >= 1
        and max_steps is None
        and config.tape_min is None
        and config.tape_max is None
        and trace is None
        and profile is None
    )
    optimize_additions = optimization_level >= 1 and max_steps is None and trace is None and profile is None
    operations = _compile(sourcecode, optimize_moves, optimize_additions)
    tape: dict[int, int] = {}
    pointer = instruction = input_position = steps = 0
    output_text: list[str] = []
    output_bytes = bytearray()
    instruction_counts: Counter[str] = Counter()
    pointer_min = pointer_max = pointer
    started = time.perf_counter()
    optimize_clear_loops = (
        optimization_level == 2
        and config.cell_mode == "wrap"
        and max_steps is None
        and trace is None
        and profile is None
    )

    while instruction < len(operations):
        operation = operations[instruction]
        location = _location(sourcecode, operation.source_offset)
        if max_steps is not None and steps + operation.step_count > max_steps:
            raise StepLimitExceeded(max_steps, steps, location)
        if trace is not None:
            trace({"step": steps, "location": location, "operation": operation.kind,
                   "argument": operation.argument, "pointer": pointer, "cell": tape.get(pointer, 0)})
        steps += operation.step_count
        instruction_counts[operation.kind] += operation.step_count

        if optimize_clear_loops and _is_clear_loop(operations, instruction):
            _store_cell(tape, pointer, 0, config)
            instruction += 3
            continue
        if operation.kind == "move":
            pointer += operation.argument
            pointer_min = min(pointer_min, pointer)
            pointer_max = max(pointer_max, pointer)
            if (config.tape_min is not None and pointer < config.tape_min) or (config.tape_max is not None and pointer > config.tape_max):
                raise TapeBoundsError(pointer, config.tape_min, config.tape_max, location)
        elif operation.kind == "add":
            _store_cell(tape, pointer, tape.get(pointer, 0) + operation.argument, config)
        elif operation.kind == "output":
            value = tape.get(pointer, 0)
            if config.output_mode == "byte":
                output_bytes.append(value & 0xFF)
            else:
                try:
                    output_text.append(chr(value))
                except ValueError as error:
                    raise ValueError(f"cell {pointer} contains {value}, which is not a Unicode code point at {location}") from error
        elif operation.kind == "input":
            if input_position < len(input_data):
                character = input_data[input_position]
                input_position += 1
            elif input_reader is not None:
                character = input_reader()
                if len(character) > 1:
                    raise ValueError("input_reader must return at most one character or byte")
            else:
                character = b"" if isinstance(input_data, bytes) else ""
            if character:
                value = character if isinstance(character, int) else ord(character)
                _store_cell(tape, pointer, value, config)
            elif config.eof_mode == "zero":
                _store_cell(tape, pointer, 0, config)
            elif config.eof_mode == "error":
                raise EOFInputError(f"input exhausted at {location}")
        elif operation.kind == "jump_if_zero" and tape.get(pointer, 0) == 0:
            instruction = operation.argument
        elif operation.kind == "jump_if_nonzero" and tape.get(pointer, 0) != 0:
            instruction = operation.argument
        instruction += 1

    if profile is not None:
        profile.clear()
        profile.update({"steps": steps, "elapsed_seconds": time.perf_counter() - started,
                        "pointer_min": pointer_min, "pointer_max": pointer_max,
                        "nonzero_cells": len(tape), "instruction_counts": dict(instruction_counts)})
    return bytes(output_bytes) if config.output_mode == "byte" else "".join(output_text)


def _configuration(
    mode: str, cell_mode: str | None, cell_bits: int | str | None, tape_min: int | str | None,
    tape_max: int | str | None, eof_mode: str | None, output_mode: str | None,
    max_steps: int | None, optimize: bool, optimization_level: int | None,
) -> tuple[_RuntimeConfig, int]:
    if max_steps is not None and (isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0):
        raise ValueError("max_steps must be a non-negative integer or None")
    return (
        _resolve_config(mode, cell_mode, cell_bits, tape_min, tape_max, eof_mode, output_mode),
        _resolve_optimization_level(optimize, optimization_level),
    )


def interpret(
    sourcecode: str, input_data: str = "", input_reader: Callable[[], str] | None = None, *,
    mode: str = "unlimited", cell_mode: str | None = None, cell_bits: int | str | None = None,
    tape_min: int | str | None = None, tape_max: int | str | None = None,
    eof_mode: str | None = None, output_mode: str | None = None, max_steps: int | None = None,
    optimize: bool = True, optimization_level: int | None = None,
    trace: Callable[[dict[str, object]], None] | None = None,
    profile: dict[str, object] | None = None,
) -> str:
    """Execute BF source through the text API and return its output string."""
    config, level = _configuration(mode, cell_mode, cell_bits, tape_min, tape_max, eof_mode, output_mode, max_steps, optimize, optimization_level)
    if not isinstance(input_data, str):
        raise TypeError("input_data must be str; use interpret_bytes for byte input")
    if config.output_mode == "byte" and any(ord(character) > 127 for character in input_data):
        raise ValueError("text input for byte-output modes must be ASCII; use interpret_bytes for arbitrary bytes")
    result = _execute(sourcecode, input_data, input_reader, config, max_steps, level, trace, profile)
    if isinstance(result, bytes):
        return result.decode("latin-1")
    return result


def interpret_bytes(
    sourcecode: str, input_data: bytes = b"", input_reader: Callable[[], bytes] | None = None, *,
    mode: str = "strict", cell_mode: str | None = None, cell_bits: int | str | None = None,
    tape_min: int | str | None = None, tape_max: int | str | None = None,
    eof_mode: str | None = None, output_mode: str | None = None, max_steps: int | None = None,
    optimize: bool = True, optimization_level: int | None = None,
    trace: Callable[[dict[str, object]], None] | None = None,
    profile: dict[str, object] | None = None,
) -> bytes:
    """Execute BF source with byte input and output; use for canonical BF I/O."""
    config, level = _configuration(mode, cell_mode, cell_bits, tape_min, tape_max, eof_mode, output_mode, max_steps, optimize, optimization_level)
    if config.output_mode != "byte":
        raise ValueError("interpret_bytes requires output_mode='byte'")
    if not isinstance(input_data, bytes):
        raise TypeError("input_data must be bytes")
    result = _execute(sourcecode, input_data, input_reader, config, max_steps, level, trace, profile)
    assert isinstance(result, bytes)
    return result


def compile_to_python(
    sourcecode: str, *, mode: str = "unlimited", cell_mode: str | None = None,
    cell_bits: int | str | None = None, tape_min: int | str | None = None,
    tape_max: int | str | None = None, eof_mode: str | None = None,
    output_mode: str | None = None, max_steps: int | None = None,
) -> str:
    """Return a standalone Python program with this BF source and configuration embedded."""
    config, _ = _configuration(
        mode, cell_mode, cell_bits, tape_min, tape_max, eof_mode, output_mode, max_steps, True, 0
    )
    return f'''"""Generated by unlimited-brainfuck."""
import sys

SOURCE = {sourcecode!r}
CELL_MODE = {config.cell_mode!r}
CELL_BITS = {config.cell_bits!r}
TAPE_MIN = {config.tape_min!r}
TAPE_MAX = {config.tape_max!r}
EOF_MODE = {config.eof_mode!r}
OUTPUT_MODE = {config.output_mode!r}
MAX_STEPS = {max_steps!r}
COMMANDS = frozenset("><+-.,[]")

program = [character for character in SOURCE if character in COMMANDS]
jumps = {{}}
stack = []
for position, command in enumerate(program):
    if command == "[":
        stack.append(position)
    elif command == "]":
        if not stack:
            raise SyntaxError(f"unmatched ']' at command {{position}}")
        opening = stack.pop()
        jumps[opening] = position
        jumps[position] = opening
if stack:
    raise SyntaxError(f"unmatched '[' at command {{stack[-1]}}")

tape = {{}}
pointer = instruction = steps = 0
input_stream = sys.stdin.buffer if OUTPUT_MODE == "byte" else sys.stdin
output_stream = sys.stdout.buffer if OUTPUT_MODE == "byte" else sys.stdout
while instruction < len(program):
    if MAX_STEPS is not None and steps >= MAX_STEPS:
        raise RuntimeError(f"maximum step count {{MAX_STEPS}} reached after {{steps}} steps")
    command = program[instruction]
    steps += 1
    value = tape.get(pointer, 0)
    if command == ">":
        pointer += 1
        if (TAPE_MIN is not None and pointer < TAPE_MIN) or (TAPE_MAX is not None and pointer > TAPE_MAX):
            raise IndexError(f"pointer {{pointer}} is outside Tape range [{{TAPE_MIN}}, {{TAPE_MAX}}]")
    elif command == "<":
        pointer -= 1
        if (TAPE_MIN is not None and pointer < TAPE_MIN) or (TAPE_MAX is not None and pointer > TAPE_MAX):
            raise IndexError(f"pointer {{pointer}} is outside Tape range [{{TAPE_MIN}}, {{TAPE_MAX}}]")
    elif command in "+-":
        value += 1 if command == "+" else -1
        if CELL_MODE == "wrap":
            value %= 1 << CELL_BITS
        if value:
            tape[pointer] = value
        else:
            tape.pop(pointer, None)
    elif command == ".":
        if OUTPUT_MODE == "byte":
            output_stream.write(bytes([value & 0xFF]))
        else:
            output_stream.write(chr(value))
    elif command == ",":
        character = input_stream.read(1)
        if character:
            value = character[0] if isinstance(character, bytes) else ord(character)
            if CELL_MODE == "wrap":
                value %= 1 << CELL_BITS
            if value:
                tape[pointer] = value
            else:
                tape.pop(pointer, None)
        elif EOF_MODE == "zero":
            tape.pop(pointer, None)
        elif EOF_MODE == "error":
            raise EOFError("input exhausted")
    elif command == "[" and value == 0:
        instruction = jumps[instruction]
    elif command == "]" and value != 0:
        instruction = jumps[instruction]
    instruction += 1
'''


def _parse_non_negative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _parse_bound(value: str) -> int | str:
    if value == UNBOUNDED:
        return value
    try:
        return int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"must be an integer or '{UNBOUNDED}'") from error


def _parse_cell_bits(value: str) -> int | str:
    if value == UNBOUNDED:
        return value
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"must be a positive integer or '{UNBOUNDED}'") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _trace_writer(stream: TextIO, trace_format: str) -> Callable[[dict[str, object]], None]:
    def write(event: dict[str, object]) -> None:
        if trace_format == "jsonl":
            stream.write(json.dumps(event, sort_keys=True) + "\n")
        else:
            stream.write("step={step} {location} op={operation} arg={argument} pointer={pointer} cell={cell}\n".format(**event))
    return write


def _dump_ir(
    sourcecode: str,
    config: _RuntimeConfig,
    optimization_level: int,
    observable: bool,
    stream: TextIO,
) -> None:
    operations = _compile(
        sourcecode,
        optimization_level >= 1 and config.tape_min is None and config.tape_max is None and not observable,
        optimization_level >= 1 and not observable,
    )
    for index, operation in enumerate(operations):
        stream.write(f"{index:04d} {operation.kind} {operation.argument} steps={operation.step_count} {_location(sourcecode, operation.source_offset)}\n")


def _extract_compile_target(arguments: list[str]) -> tuple[list[str], str | None]:
    """Parse ``--compile-python [OUTPUT]`` while leaving the source positional argument."""
    if "--compile-python" not in arguments:
        return arguments, None
    index = arguments.index("--compile-python")
    if arguments.count("--compile-python") > 1:
        raise ValueError("--compile-python can be specified only once")
    if index >= len(arguments) - 1:
        raise ValueError("--compile-python requires a BF source file")
    target = None if index == len(arguments) - 2 else arguments[index + 1]
    remaining = arguments[:index] + arguments[index + 1 + (target is not None) :]
    return remaining, target


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    """Run a Brainfuck source file and write its output to standard output."""
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        raw_arguments, compile_target = _extract_compile_target(raw_arguments)
    except ValueError as error:
        print(f"brainfuck.py: error: {error}", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_file", metavar="code.bf")
    parser.add_argument("-m", "--mode", choices=PROFILES, default="unlimited")
    parser.add_argument("--cell-mode", choices=(UNBOUNDED, "wrap"))
    parser.add_argument("-b", "--cell-bits", type=_parse_cell_bits)
    parser.add_argument("--tape-min", type=_parse_bound)
    parser.add_argument("--tape-max", type=_parse_bound)
    parser.add_argument("-e", "--eof-mode", choices=("zero", "unchanged", "error"))
    parser.add_argument("-o", "--output-mode", choices=("unicode", "byte"))
    parser.add_argument("-s", "--max-steps", type=_parse_non_negative_integer)
    parser.add_argument("-O", "--no-optimize", action="store_true")
    parser.add_argument("--optimization-level", type=int, choices=(0, 1, 2))
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--trace-format", choices=("text", "jsonl"), default="text")
    parser.add_argument("--trace-file")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--dump-ir", action="store_true")
    parser.epilog = "--compile-python [OUTPUT] code.bf emits standalone Python to stdout or OUTPUT."
    arguments = parser.parse_args(raw_arguments)
    config, level = _configuration(arguments.mode, arguments.cell_mode, arguments.cell_bits, arguments.tape_min,
                            arguments.tape_max, arguments.eof_mode, arguments.output_mode,
                            arguments.max_steps, not arguments.no_optimize, arguments.optimization_level)
    sourcecode = Path(arguments.source_file).read_text(encoding="utf-8")
    if compile_target is not None or "--compile-python" in (sys.argv[1:] if argv is None else argv):
        generated = compile_to_python(
            sourcecode, mode=arguments.mode, cell_mode=arguments.cell_mode, cell_bits=arguments.cell_bits,
            tape_min=arguments.tape_min, tape_max=arguments.tape_max, eof_mode=arguments.eof_mode,
            output_mode=arguments.output_mode, max_steps=arguments.max_steps,
        )
        if compile_target is None:
            sys.stdout.write(generated)
        else:
            Path(compile_target).write_text(generated, encoding="utf-8")
        return 0
    if arguments.dump_ir:
        _dump_ir(sourcecode, config, level, arguments.trace or arguments.profile, sys.stderr)
    trace_stream: TextIO | None = None
    close_trace = False
    if arguments.trace:
        trace_stream = open(arguments.trace_file, "w", encoding="utf-8") if arguments.trace_file else sys.stderr
        close_trace = trace_stream is not sys.stderr
    try:
        profile: dict[str, object] | None = {} if arguments.profile else None
        trace = _trace_writer(trace_stream, arguments.trace_format) if trace_stream else None
        if config.output_mode == "byte":
            input_stream = getattr(stdin or sys.stdin, "buffer", stdin or sys.stdin)
            output_stream = sys.stdout.buffer
            output_stream.write(interpret_bytes(sourcecode, input_reader=lambda: input_stream.read(1),
                                                mode=arguments.mode, cell_mode=arguments.cell_mode,
                                                cell_bits=arguments.cell_bits, tape_min=arguments.tape_min,
                                                tape_max=arguments.tape_max, eof_mode=arguments.eof_mode,
                                                output_mode=arguments.output_mode, max_steps=arguments.max_steps,
                                                optimize=not arguments.no_optimize, optimization_level=level,
                                                trace=trace, profile=profile))
        else:
            input_stream = stdin or sys.stdin
            sys.stdout.write(interpret(sourcecode, input_reader=lambda: input_stream.read(1),
                                       mode=arguments.mode, cell_mode=arguments.cell_mode,
                                       cell_bits=arguments.cell_bits, tape_min=arguments.tape_min,
                                       tape_max=arguments.tape_max, eof_mode=arguments.eof_mode,
                                       output_mode=arguments.output_mode, max_steps=arguments.max_steps,
                                       optimize=not arguments.no_optimize, optimization_level=level,
                                       trace=trace, profile=profile))
        if profile is not None:
            sys.stderr.write(json.dumps(profile, sort_keys=True) + "\n")
    finally:
        if close_trace and trace_stream is not None:
            trace_stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
