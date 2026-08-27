"""Public API and command-line entry point for the Brainfuck interpreter."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import time
from typing import Callable


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
    pointer_bounds: str
    eof_mode: str
    output_mode: str
    comment_style: str
    debug_command: str


@dataclass(frozen=True)
class _Operation:
    """An executable IR operation with source-level step accounting."""

    kind: str
    argument: int
    step_count: int
    source_offset: int


PROFILES = {
    "unlimited": _RuntimeConfig(UNBOUNDED, None, None, None, "error", "zero", "unicode", "none", "none"),
    "standard": _RuntimeConfig("wrap", 8, None, None, "error", "zero", "byte", "none", "none"),
    "standard-one-way": _RuntimeConfig("wrap", 8, 0, None, "error", "zero", "byte", "none", "none"),
    "strict": _RuntimeConfig("wrap", 8, 0, 29999, "error", "zero", "byte", "none", "none"),
}


def _location(sourcecode: str, offset: int) -> str:
    """Convert a string offset into a human-readable one-based location."""
    return f"line {sourcecode.count(chr(10), 0, offset) + 1}, column {offset - sourcecode.rfind(chr(10), 0, offset)}"


def _filter_program(sourcecode: str, comment_style: str, debug_command: str) -> tuple[str, list[int]]:
    """Apply extensions, then keep commands and original offsets for diagnostics."""
    filtered_source = sourcecode
    if comment_style == "block":
        characters = list(sourcecode)
        position = 0
        while position < len(sourcecode):
            if sourcecode.startswith("/*", position):
                ending = sourcecode.find("*/", position + 2)
                if ending == -1:
                    raise SyntaxError(f"unclosed block comment at {_location(sourcecode, position)}")
                for index in range(position, ending + 2):
                    if characters[index] != "\n":
                        characters[index] = " "
                position = ending + 2
            else:
                position += 1
        filtered_source = "".join(characters)
    command_set = COMMANDS | ({"#"} if debug_command == "qdb" else set())
    commands: list[str] = []
    offsets: list[int] = []
    for offset, character in enumerate(filtered_source):
        if character in command_set:
            commands.append(character)
            offsets.append(offset)
    return "".join(commands), offsets


def _build_jumps(program: str, offsets: list[int], sourcecode: str) -> dict[int, int]:
    """Match brackets before execution, reporting locations in the original source."""
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


def _compile(
    sourcecode: str, optimize_moves: bool, optimize_additions: bool,
    comment_style: str = "none", debug_command: str = "none",
) -> list[_Operation]:
    """Compile BF text to IR, combining only operations allowed by the caller."""
    program, offsets = _filter_program(sourcecode, comment_style, debug_command)
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
        if command in ">+":
            operations.append(_Operation("move" if command == ">" else "add", 1, 1, offsets[position]))
        elif command in "<-":
            operations.append(_Operation("move" if command == "<" else "add", -1, 1, offsets[position]))
        elif command == ".":
            operations.append(_Operation("output", 0, 1, offsets[position]))
        elif command == ",":
            operations.append(_Operation("input", 0, 1, offsets[position]))
        elif command == "#":
            operations.append(_Operation("debug", 0, 1, offsets[position]))
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
    pointer_bounds: str | None, eof_mode: str | None, output_mode: str | None,
    comment_style: str | None, debug_command: str | None,
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
    resolved_pointer_bounds = profile.pointer_bounds if pointer_bounds is None else pointer_bounds
    if resolved_pointer_bounds not in ("error", "wrap"):
        raise ValueError("pointer_bounds must be 'error' or 'wrap'")
    if resolved_pointer_bounds == "wrap" and (resolved_tape_min is None or resolved_tape_max is None):
        raise ValueError("pointer_bounds='wrap' requires finite tape_min and tape_max")
    resolved_eof_mode = profile.eof_mode if eof_mode is None else eof_mode
    if resolved_eof_mode not in ("zero", "unchanged", "error"):
        raise ValueError("eof_mode must be 'zero', 'unchanged', or 'error'")
    resolved_output_mode = profile.output_mode if output_mode is None else output_mode
    if resolved_output_mode not in ("unicode", "byte"):
        raise ValueError("output_mode must be 'unicode' or 'byte'")
    resolved_comment_style = profile.comment_style if comment_style is None else comment_style
    if resolved_comment_style not in ("none", "block"):
        raise ValueError("comment_style must be 'none' or 'block'")
    resolved_debug_command = profile.debug_command if debug_command is None else debug_command
    if resolved_debug_command not in ("none", "qdb"):
        raise ValueError("debug_command must be 'none' or 'qdb'")
    if resolved_debug_command == "qdb" and (resolved_cell_mode != "wrap" or resolved_cell_bits != 8):
        raise ValueError("debug_command='qdb' requires 8-bit wrapping Cells")
    return _RuntimeConfig(resolved_cell_mode, resolved_cell_bits, resolved_tape_min, resolved_tape_max,
                          resolved_pointer_bounds, resolved_eof_mode, resolved_output_mode,
                          resolved_comment_style, resolved_debug_command)


def _store_cell(tape: dict[int, int], pointer: int, value: int, config: _RuntimeConfig) -> None:
    if config.cell_mode == "wrap":
        value %= 1 << config.cell_bits
    if value:
        tape[pointer] = value
    else:
        tape.pop(pointer, None)


def _qdb_debug_output(tape: dict[int, int], pointer: int) -> str:
    """Render qdb's 64 signed-byte Cell view and its pointer marker."""
    cells = "".join(f"{value if value < 128 else value - 256:4d}" for value in (tape.get(index, 0) for index in range(64)))
    return f"\n{cells}\n{' ' * max(0, pointer * 4 + 4)}^\n"


def _is_clear_loop(operations: list[_Operation], instruction: int) -> bool:
    """Recognize only exact ``[-]`` and ``[+]`` loops in compiled IR."""
    if instruction + 2 >= len(operations):
        return False
    opening, change, closing = operations[instruction : instruction + 3]
    return (opening.kind == "jump_if_zero" and opening.argument == instruction + 2
            and change.kind == "add" and abs(change.argument) == 1 and change.step_count == 1
            and closing.kind == "jump_if_nonzero" and closing.argument == instruction)


def _optimize_clear_operations(operations: list[_Operation]) -> list[_Operation]:
    """Replace clear loops and remap surviving IR jump destinations."""
    rewritten: list[_Operation] = []
    remap: dict[int, int] = {}
    index = 0
    while index < len(operations):
        if _is_clear_loop(operations, index):
            for old_index in range(index, index + 3):
                remap[old_index] = len(rewritten)
            rewritten.append(_Operation("clear", 0, 0, operations[index].source_offset))
            index += 3
        else:
            remap[index] = len(rewritten)
            rewritten.append(operations[index])
            index += 1
    result: list[_Operation] = []
    for operation in rewritten:
        if operation.kind.startswith("jump_"):
            operation = _Operation(operation.kind, remap[operation.argument], operation.step_count, operation.source_offset)
        result.append(operation)
    return result


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


def _configuration(
    mode: str, cell_mode: str | None, cell_bits: int | str | None, tape_min: int | str | None,
    tape_max: int | str | None, pointer_bounds: str | None, eof_mode: str | None, output_mode: str | None,
    comment_style: str | None, debug_command: str | None,
    max_steps: int | None, optimize: bool, optimization_level: int | None,
) -> tuple[_RuntimeConfig, int]:
    if max_steps is not None and (isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0):
        raise ValueError("max_steps must be a non-negative integer or None")
    return (_resolve_config(mode, cell_mode, cell_bits, tape_min, tape_max, pointer_bounds, eof_mode, output_mode, comment_style, debug_command),
            _resolve_optimization_level(optimize, optimization_level))


def _execute(
    sourcecode: str, input_data: str | bytes, input_reader: Callable[[], str | bytes] | None,
    config: _RuntimeConfig, max_steps: int | None, optimization_level: int,
    trace: Callable[[dict[str, object]], None] | None, profile: dict[str, object] | None,
) -> str | bytes:
    observable = trace is not None or profile is not None
    operations = _compile(
        sourcecode,
        optimization_level >= 1 and max_steps is None and config.tape_min is None and config.tape_max is None and not observable,
        optimization_level >= 1 and max_steps is None and not observable,
        config.comment_style,
        config.debug_command,
    )
    tape: dict[int, int] = {}
    pointer = instruction = input_position = steps = 0
    output_text: list[str] = []
    output_bytes = bytearray()
    counts: Counter[str] = Counter()
    pointer_min = pointer_max = 0
    started = time.perf_counter()
    use_clear = optimization_level == 2 and config.cell_mode == "wrap" and max_steps is None and not observable

    while instruction < len(operations):
        operation = operations[instruction]
        location = _location(sourcecode, operation.source_offset)
        if max_steps is not None and steps + operation.step_count > max_steps:
            raise StepLimitExceeded(max_steps, steps, location)
        if trace is not None:
            trace({"step": steps, "location": location, "operation": operation.kind,
                   "argument": operation.argument, "pointer": pointer, "cell": tape.get(pointer, 0)})
        steps += operation.step_count
        counts[operation.kind] += operation.step_count
        if use_clear and _is_clear_loop(operations, instruction):
            _store_cell(tape, pointer, 0, config)
            instruction += 3
            continue
        if operation.kind == "move":
            pointer += operation.argument
            if (config.tape_min is not None and pointer < config.tape_min) or (config.tape_max is not None and pointer > config.tape_max):
                if config.pointer_bounds == "wrap":
                    pointer = config.tape_min + (pointer - config.tape_min) % (config.tape_max - config.tape_min + 1)
                else:
                    raise TapeBoundsError(pointer, config.tape_min, config.tape_max, location)
            pointer_min, pointer_max = min(pointer_min, pointer), max(pointer_max, pointer)
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
                _store_cell(tape, pointer, character if isinstance(character, int) else ord(character), config)
            elif config.eof_mode == "zero":
                _store_cell(tape, pointer, 0, config)
            elif config.eof_mode == "error":
                raise EOFInputError(f"input exhausted at {location}")
        elif operation.kind == "debug":
            debug_output = _qdb_debug_output(tape, pointer)
            if config.output_mode == "byte":
                output_bytes.extend(debug_output.encode("ascii"))
            else:
                output_text.append(debug_output)
        elif operation.kind == "jump_if_zero" and tape.get(pointer, 0) == 0:
            instruction = operation.argument
        elif operation.kind == "jump_if_nonzero" and tape.get(pointer, 0) != 0:
            instruction = operation.argument
        instruction += 1
    if profile is not None:
        profile.clear()
        profile.update({"steps": steps, "elapsed_seconds": time.perf_counter() - started,
                        "pointer_min": pointer_min, "pointer_max": pointer_max,
                        "nonzero_cells": len(tape), "instruction_counts": dict(counts)})
    return bytes(output_bytes) if config.output_mode == "byte" else "".join(output_text)


def interpret(
    sourcecode: str, input_data: str = "", input_reader: Callable[[], str] | None = None, *,
    mode: str = "unlimited", cell_mode: str | None = None, cell_bits: int | str | None = None,
    tape_min: int | str | None = None, tape_max: int | str | None = None,
    pointer_bounds: str | None = None, eof_mode: str | None = None, output_mode: str | None = None,
    comment_style: str | None = None, debug_command: str | None = None,
    max_steps: int | None = None, optimize: bool = True, optimization_level: int | None = None,
    trace: Callable[[dict[str, object]], None] | None = None, profile: dict[str, object] | None = None,
) -> str:
    """Execute BF source through the text API and return its output string."""
    config, level = _configuration(mode, cell_mode, cell_bits, tape_min, tape_max, pointer_bounds, eof_mode, output_mode, comment_style, debug_command, max_steps, optimize, optimization_level)
    if not isinstance(input_data, str):
        raise TypeError("input_data must be str; use interpret_bytes for byte input")
    if config.output_mode == "byte" and any(ord(character) > 127 for character in input_data):
        raise ValueError("text input for byte-output modes must be ASCII; use interpret_bytes for arbitrary bytes")
    result = _execute(sourcecode, input_data, input_reader, config, max_steps, level, trace, profile)
    return result.decode("latin-1") if isinstance(result, bytes) else result


def interpret_bytes(
    sourcecode: str, input_data: bytes = b"", input_reader: Callable[[], bytes] | None = None, *,
    mode: str = "strict", cell_mode: str | None = None, cell_bits: int | str | None = None,
    tape_min: int | str | None = None, tape_max: int | str | None = None,
    pointer_bounds: str | None = None, eof_mode: str | None = None, output_mode: str | None = None,
    comment_style: str | None = None, debug_command: str | None = None,
    max_steps: int | None = None, optimize: bool = True, optimization_level: int | None = None,
    trace: Callable[[dict[str, object]], None] | None = None, profile: dict[str, object] | None = None,
) -> bytes:
    """Execute BF source with byte input and output for canonical BF I/O."""
    config, level = _configuration(mode, cell_mode, cell_bits, tape_min, tape_max, pointer_bounds, eof_mode, output_mode, comment_style, debug_command, max_steps, optimize, optimization_level)
    if config.output_mode != "byte":
        raise ValueError("interpret_bytes requires output_mode='byte'")
    if not isinstance(input_data, bytes):
        raise TypeError("input_data must be bytes")
    result = _execute(sourcecode, input_data, input_reader, config, max_steps, level, trace, profile)
    assert isinstance(result, bytes)
    return result


def compile_to_python(*args: object, **kwargs: object) -> str:
    """Lazily import the generator so runtime users do not load CLI code."""
    from bf_codegen import compile_to_python as compile_program

    return compile_program(*args, **kwargs)


def main(argv: list[str] | None = None, stdin: object | None = None) -> int:
    """Lazily import the CLI while preserving the historical entry point."""
    from bf_cli import main as run_cli

    return run_cli(argv, stdin)


if __name__ == "__main__":
    raise SystemExit(main())
