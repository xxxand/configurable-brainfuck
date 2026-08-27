"""A configurable Brainfuck interpreter with unrestricted defaults."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


COMMANDS = frozenset("><+-.,[]")
UNBOUNDED = "unbounded"


class TapeBoundsError(IndexError):
    """Raised when a pointer movement leaves the configured Tape range."""

    def __init__(self, pointer: int, tape_min: int | None, tape_max: int | None) -> None:
        self.pointer = pointer
        self.tape_min = tape_min
        self.tape_max = tape_max
        super().__init__(f"pointer {pointer} is outside Tape range [{tape_min}, {tape_max}]")


class StepLimitExceeded(RuntimeError):
    """Raised before executing an instruction beyond ``max_steps``."""

    def __init__(self, max_steps: int, executed_steps: int) -> None:
        self.max_steps = max_steps
        self.executed_steps = executed_steps
        super().__init__(f"maximum step count {max_steps} reached after {executed_steps} steps")


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


PROFILES = {
    "unlimited": _RuntimeConfig(UNBOUNDED, None, None, None, "zero", "unicode"),
    "standard": _RuntimeConfig("wrap", 8, None, None, "zero", "byte"),
    "standard-one-way": _RuntimeConfig("wrap", 8, 0, None, "zero", "byte"),
    "strict": _RuntimeConfig("wrap", 8, 0, 29999, "zero", "byte"),
}


def _build_jumps(program: str) -> dict[int, int]:
    """Return matching bracket positions, rejecting malformed programs."""
    stack: list[int] = []
    jumps: dict[int, int] = {}

    for position, command in enumerate(program):
        if command == "[":
            stack.append(position)
        elif command == "]":
            if not stack:
                raise SyntaxError(f"unmatched ']' at command {position}")
            opening = stack.pop()
            jumps[opening] = position
            jumps[position] = opening

    if stack:
        raise SyntaxError(f"unmatched '[' at command {stack[-1]}")
    return jumps


def _compile(
    sourcecode: str, optimize_moves: bool, optimize_additions: bool
) -> list[tuple[str, int, int]]:
    """Compile source into ``(operation, argument, source_step_count)`` tuples."""
    program = "".join(character for character in sourcecode if character in COMMANDS)
    jumps = _build_jumps(program)
    operations: list[tuple[str, int, int]] = []
    bracket_operations: dict[int, int] = {}
    position = 0

    while position < len(program):
        command = program[position]
        if command in "><" and optimize_moves:
            delta = 0
            start = position
            while position < len(program) and program[position] in "><":
                delta += 1 if program[position] == ">" else -1
                position += 1
            if delta:
                operations.append(("move", delta, position - start))
            continue
        if command in "+-" and optimize_additions:
            delta = 0
            start = position
            while position < len(program) and program[position] in "+-":
                delta += 1 if program[position] == "+" else -1
                position += 1
            if delta:
                operations.append(("add", delta, position - start))
            continue

        if command == ">":
            operations.append(("move", 1, 1))
        elif command == "<":
            operations.append(("move", -1, 1))
        elif command == "+":
            operations.append(("add", 1, 1))
        elif command == "-":
            operations.append(("add", -1, 1))
        elif command == ".":
            operations.append(("output", 0, 1))
        elif command == ",":
            operations.append(("input", 0, 1))
        elif command == "[":
            bracket_operations[position] = len(operations)
            operations.append(("jump_if_zero", 0, 1))
        else:
            bracket_operations[position] = len(operations)
            operations.append(("jump_if_nonzero", 0, 1))
        position += 1

    for position, target in jumps.items():
        # Bracket destinations use compiled indexes, not source positions.
        operation, _, step_count = operations[bracket_operations[position]]
        operations[bracket_operations[position]] = (
            operation,
            bracket_operations[target],
            step_count,
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
    mode: str,
    cell_mode: str | None,
    cell_bits: int | str | None,
    tape_min: int | str | None,
    tape_max: int | str | None,
    eof_mode: str | None,
    output_mode: str | None,
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
    if resolved_tape_min is not None and resolved_tape_max is not None:
        if resolved_tape_min > resolved_tape_max:
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

    return _RuntimeConfig(
        resolved_cell_mode,
        resolved_cell_bits,
        resolved_tape_min,
        resolved_tape_max,
        resolved_eof_mode,
        resolved_output_mode,
    )


def _store_cell(tape: dict[int, int], pointer: int, value: int, config: _RuntimeConfig) -> None:
    if config.cell_mode == "wrap":
        value %= 1 << config.cell_bits
    if value:
        tape[pointer] = value
    else:
        tape.pop(pointer, None)


def interpret(
    sourcecode: str,
    input_data: str = "",
    input_reader: Callable[[], str] | None = None,
    *,
    mode: str = "unlimited",
    cell_mode: str | None = None,
    cell_bits: int | str | None = None,
    tape_min: int | str | None = None,
    tape_max: int | str | None = None,
    eof_mode: str | None = None,
    output_mode: str | None = None,
    max_steps: int | None = None,
    optimize: bool = True,
) -> str:
    """Execute Brainfuck source and return its output.

    ``mode`` selects a compatibility profile. Non-``None`` configuration
    arguments override that profile; use ``'unbounded'`` to remove a profile
    Cell or Tape limit. ``max_steps`` counts original executed BF commands.
    """
    if max_steps is not None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0:
            raise ValueError("max_steps must be a non-negative integer or None")
    if not isinstance(optimize, bool):
        raise ValueError("optimize must be a boolean")

    config = _resolve_config(
        mode,
        cell_mode,
        cell_bits,
        tape_min,
        tape_max,
        eof_mode,
        output_mode,
    )
    # Exact step limits and bounded Tape movement require source-level moves.
    optimize_moves = optimize and max_steps is None and config.tape_min is None and config.tape_max is None
    optimize_additions = optimize and max_steps is None
    operations = _compile(sourcecode, optimize_moves, optimize_additions)
    tape: dict[int, int] = {}
    pointer = 0
    instruction = 0
    input_position = 0
    steps = 0
    output: list[str] = []

    while instruction < len(operations):
        operation, argument, step_count = operations[instruction]
        if max_steps is not None and steps + step_count > max_steps:
            raise StepLimitExceeded(max_steps, steps)
        steps += step_count

        if operation == "move":
            pointer += argument
            if (config.tape_min is not None and pointer < config.tape_min) or (
                config.tape_max is not None and pointer > config.tape_max
            ):
                raise TapeBoundsError(pointer, config.tape_min, config.tape_max)
        elif operation == "add":
            _store_cell(tape, pointer, tape.get(pointer, 0) + argument, config)
        elif operation == "output":
            value = tape.get(pointer, 0)
            if config.output_mode == "byte":
                output.append(chr(value & 0xFF))
            else:
                try:
                    output.append(chr(value))
                except ValueError as error:
                    raise ValueError(
                        f"cell {pointer} contains {value}, which is not a Unicode code point"
                    ) from error
        elif operation == "input":
            if input_position < len(input_data):
                character = input_data[input_position]
                input_position += 1
            elif input_reader is not None:
                character = input_reader()
                if len(character) > 1:
                    raise ValueError("input_reader must return at most one character")
            else:
                character = ""

            if character:
                _store_cell(tape, pointer, ord(character), config)
            elif config.eof_mode == "zero":
                _store_cell(tape, pointer, 0, config)
            elif config.eof_mode == "error":
                raise EOFInputError("input exhausted")
        elif operation == "jump_if_zero" and tape.get(pointer, 0) == 0:
            instruction = argument
        elif operation == "jump_if_nonzero" and tape.get(pointer, 0) != 0:
            instruction = argument

        instruction += 1

    return "".join(output)


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


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    """Run a Brainfuck source file and write its output to standard output."""
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
    arguments = parser.parse_args(argv)

    sourcecode = Path(arguments.source_file).read_text(encoding="utf-8")
    input_stream = sys.stdin if stdin is None else stdin
    # Reading here would block programs that never execute ','.
    sys.stdout.write(
        interpret(
            sourcecode,
            input_reader=lambda: input_stream.read(1),
            mode=arguments.mode,
            cell_mode=arguments.cell_mode,
            cell_bits=arguments.cell_bits,
            tape_min=arguments.tape_min,
            tape_max=arguments.tape_max,
            eof_mode=arguments.eof_mode,
            output_mode=arguments.output_mode,
            max_steps=arguments.max_steps,
            optimize=not arguments.no_optimize,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
