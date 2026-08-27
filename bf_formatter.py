"""Format Brainfuck source into one instruction per indented line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


COMMANDS = frozenset("><+-.,[]")


def _location(sourcecode: str, offset: int) -> str:
    line = sourcecode.count("\n", 0, offset) + 1
    column = offset - sourcecode.rfind("\n", 0, offset)
    return f"line {line}, column {column}"


def _normalize_annotation(text: str) -> str:
    """Collapse annotation whitespace while retaining its readable content."""
    return " ".join(text.split())


def format_source(
    sourcecode: str,
    *,
    comment_style: str = "none",
    debug_command: str = "none",
    indent_width: int = 1,
    comment_spaces: int = 2,
) -> str:
    """Return a canonical line-oriented layout for Brainfuck source.

    Every active command occupies one line. Opening brackets increase the
    following indentation; closing brackets reduce their own indentation.
    Ignored text on an instruction's source line becomes a trailing annotation,
    separated by ``comment_spaces`` spaces. Ignored text on its own source line
    remains standalone. Enabled block comments preserve their original line
    structure, relative indentation, and surrounding BF indentation.
    """
    if comment_style not in ("none", "block"):
        raise ValueError("comment_style must be 'none' or 'block'")
    if debug_command not in ("none", "qdb"):
        raise ValueError("debug_command must be 'none' or 'qdb'")
    if isinstance(indent_width, bool) or not isinstance(indent_width, int) or indent_width < 1:
        raise ValueError("indent_width must be a positive integer")
    if isinstance(comment_spaces, bool) or not isinstance(comment_spaces, int) or comment_spaces < 1:
        raise ValueError("comment_spaces must be a positive integer")

    active_commands = COMMANDS | ({"#"} if debug_command == "qdb" else set())
    lines: list[str] = []
    opening_brackets: list[int] = []
    annotation_buffer: list[str] = []
    annotation_line: int | None = None
    indentation = 0
    position = 0
    source_line = 1
    last_command_line = 0

    def collect_annotation(text: str) -> None:
        nonlocal annotation_line
        if annotation_line is None:
            annotation_line = source_line
        annotation_buffer.append(text)

    def flush_annotation() -> None:
        nonlocal annotation_line
        annotation = _normalize_annotation("".join(annotation_buffer))
        annotation_buffer.clear()
        line = annotation_line
        annotation_line = None
        if not annotation:
            return
        if lines and line == last_command_line:
            lines[-1] += " " * comment_spaces + annotation
        else:
            lines.append(" " * (indentation * indent_width) + annotation)

    def append_command(command: str) -> None:
        nonlocal indentation, last_command_line
        flush_annotation()
        if command == "]":
            if indentation == 0:
                raise SyntaxError(f"unmatched ']' at {_location(sourcecode, position)}")
            indentation -= 1
            opening_brackets.pop()
        line = " " * (indentation * indent_width) + command
        lines.append(line)
        if command == "[":
            indentation += 1
            opening_brackets.append(position)
        last_command_line = source_line

    def append_block_comment(comment: str, inline: bool) -> None:
        """Preserve comment line count and relative whitespace under BF indentation."""
        comment_lines = [line.rstrip() for line in comment.splitlines()]
        if inline:
            comment_column = len(lines[-1]) + comment_spaces
            lines[-1] += " " * comment_spaces + comment_lines[0]
            lines.extend(" " * comment_column + line for line in comment_lines[1:])
        else:
            prefix = " " * (indentation * indent_width)
            lines.extend(prefix + line for line in comment_lines)

    while position < len(sourcecode):
        if comment_style == "block" and sourcecode.startswith("/*", position):
            ending = sourcecode.find("*/", position + 2)
            if ending == -1:
                raise SyntaxError(f"unclosed block comment at {_location(sourcecode, position)}")
            flush_annotation()
            comment = sourcecode[position : ending + 2]
            append_block_comment(comment, bool(lines) and last_command_line == source_line)
            source_line += comment.count("\n")
            position = ending + 2
            continue
        character = sourcecode[position]
        if character in active_commands:
            append_command(character)
        else:
            collect_annotation(character)
        if character == "\n":
            flush_annotation()
            source_line += 1
        position += 1

    flush_annotation()
    if indentation:
        raise SyntaxError(f"unmatched '[' at {_location(sourcecode, opening_brackets[-1])}")
    return "\n".join(lines) + ("\n" if lines else "")


def main(argv: list[str] | None = None) -> int:
    """Format a source file to standard output, a file, or the input file itself."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_file", metavar="code.b")
    parser.add_argument("-o", "--output")
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--comment-style", choices=("none", "block"), default="none")
    parser.add_argument("--debug-command", choices=("none", "qdb"), default="none")
    parser.add_argument("--indent-width", type=int, default=1)
    parser.add_argument("--comment-spaces", type=int, default=2)
    arguments = parser.parse_args(argv)
    if arguments.output and arguments.in_place:
        parser.error("--output and --in-place cannot be used together")

    source_path = Path(arguments.source_file)
    try:
        formatted = format_source(
            source_path.read_text(encoding="utf-8"),
            comment_style=arguments.comment_style,
            debug_command=arguments.debug_command,
            indent_width=arguments.indent_width,
            comment_spaces=arguments.comment_spaces,
        )
    except (SyntaxError, ValueError) as error:
        print(f"bf_formatter.py: error: {error}", file=sys.stderr)
        return 1

    if arguments.in_place:
        source_path.write_text(formatted, encoding="utf-8")
    elif arguments.output:
        Path(arguments.output).write_text(formatted, encoding="utf-8")
    else:
        sys.stdout.write(formatted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
