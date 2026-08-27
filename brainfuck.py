"""An unrestricted Brainfuck interpreter.

Import ``interpret`` to execute Brainfuck source code, or run this file with
the path to a .bf file.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, TextIO


COMMANDS = frozenset("><+-.,[]")


def _build_jumps(program: str) -> dict[int, int]:
    """Return matching bracket locations, rejecting malformed programs."""
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


def _compile(sourcecode: str) -> list[tuple[str, int]]:
    """Compile source into operations, combining adjacent moves and changes.

    Brackets remain individual operations because their targets depend on the
    compiled operation positions rather than the original source positions.
    """
    program = "".join(character for character in sourcecode if character in COMMANDS)
    jumps = _build_jumps(program)
    operations: list[tuple[str, int]] = []
    bracket_operations: dict[int, int] = {}
    position = 0

    while position < len(program):
        command = program[position]
        if command in "><":
            delta = 0
            while position < len(program) and program[position] in "><":
                delta += 1 if program[position] == ">" else -1
                position += 1
            if delta:
                operations.append(("move", delta))
            continue
        if command in "+-":
            delta = 0
            while position < len(program) and program[position] in "+-":
                delta += 1 if program[position] == "+" else -1
                position += 1
            if delta:
                operations.append(("add", delta))
            continue

        if command == ".":
            operations.append(("output", 0))
        elif command == ",":
            operations.append(("input", 0))
        elif command == "[":
            bracket_operations[position] = len(operations)
            operations.append(("jump_if_zero", 0))
        else:
            bracket_operations[position] = len(operations)
            operations.append(("jump_if_nonzero", 0))
        position += 1

    for position, target in jumps.items():
        # Jump destinations must use compiled indexes: a run of ten '+'
        # commands may occupy only one operation.
        operation, _ = operations[bracket_operations[position]]
        operations[bracket_operations[position]] = (operation, bracket_operations[target])
    return operations


def interpret(
    sourcecode: str,
    input_data: str = "",
    input_reader: Callable[[], str] | None = None,
) -> str:
    """Execute *sourcecode* and return its output.

    Non-Brainfuck characters are comments. Input characters are consumed in
    order and stored as their Unicode code points. When supplied, *input_reader*
    provides one input character after *input_data* is exhausted. Reading beyond
    input stores zero. Output cell values must be valid Unicode code points.
    """
    operations = _compile(sourcecode)
    tape: dict[int, int] = {}
    pointer = 0
    instruction = 0
    input_position = 0
    output: list[str] = []

    while instruction < len(operations):
        operation, argument = operations[instruction]

        if operation == "move":
            pointer += argument
        elif operation == "add":
            value = tape.get(pointer, 0) + argument
            if value:
                tape[pointer] = value
            else:
                tape.pop(pointer, None)
        elif operation == "output":
            value = tape.get(pointer, 0)
            try:
                output.append(chr(value))
            except ValueError as error:
                raise ValueError(
                    f"cell {pointer} contains {value}, which is not a Unicode code point"
                ) from error
        elif operation == "input":
            if input_position < len(input_data):
                tape[pointer] = ord(input_data[input_position])
                input_position += 1
            elif input_reader is not None:
                character = input_reader()
                tape[pointer] = ord(character) if character else 0
            else:
                tape.pop(pointer, None)
        elif operation == "jump_if_zero" and tape.get(pointer, 0) == 0:
            # The common increment below advances from ']' to the following
            # operation, matching Brainfuck's '[' jump behavior.
            instruction = argument
        elif operation == "jump_if_nonzero" and tape.get(pointer, 0) != 0:
            # The common increment below advances from '[' into the loop body.
            instruction = argument

        instruction += 1

    return "".join(output)


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    """Run a Brainfuck source file and write its output to standard output."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print(f"Usage: {Path(sys.argv[0]).name} code.bf", file=sys.stderr)
        return 2

    sourcecode = Path(arguments[0]).read_text(encoding="utf-8")
    input_stream = sys.stdin if stdin is None else stdin
    # Reading here would block programs that never execute ','.
    sys.stdout.write(interpret(sourcecode, input_reader=lambda: input_stream.read(1)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
