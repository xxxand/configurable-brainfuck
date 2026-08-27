"""Command-line parsing and observability helpers for the Brainfuck runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Callable, TextIO

import brainfuck as runtime
from bf_codegen import compile_to_python


def _parse_non_negative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _parse_bound(value: str) -> int | str:
    if value == runtime.UNBOUNDED:
        return value
    try:
        return int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"must be an integer or '{runtime.UNBOUNDED}'") from error


def _parse_cell_bits(value: str) -> int | str:
    if value == runtime.UNBOUNDED:
        return value
    parsed = _parse_non_negative_integer(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _trace_writer(stream: TextIO, trace_format: str) -> Callable[[dict[str, object]], None]:
    """Create the text or JSON Lines sink used by the runtime trace callback."""
    header_written = False

    def write(event: dict[str, object]) -> None:
        nonlocal header_written
        if trace_format == "jsonl":
            stream.write(json.dumps(event, sort_keys=True) + "\n")
        else:
            if not header_written:
                stream.write("STEP    LOCATION       OPERATION  ARGUMENT  POINTER  CELL\n")
                stream.write("------  -------------  ---------  --------  -------  ----\n")
                header_written = True
            location = str(event["location"]).replace("line ", "L").replace(", column ", ":")
            stream.write(
                f"{int(event['step']):6}  {location:<13}  {str(event['operation']):<9}  "
                f"{int(event['argument']):8}  {int(event['pointer']):7}  {event['cell']}\n"
            )
    return write


def _dump_ir(sourcecode: str, config: runtime._RuntimeConfig, level: int, observable: bool, stream: TextIO) -> None:
    """Show the same IR shape the execution path will use for this invocation."""
    operations = runtime._compile(
        sourcecode,
        level >= 1 and config.tape_min is None and config.tape_max is None and not observable,
        level >= 1 and not observable,
        config.comment_style,
        config.debug_command,
    )
    for index, operation in enumerate(operations):
        stream.write(f"{index:04d} {operation.kind} {operation.argument} steps={operation.step_count} {runtime._location(sourcecode, operation.source_offset)}\n")


def _extract_compile_target(arguments: list[str]) -> tuple[list[str], str | None, bool]:
    """Support ``--compile-python [OUTPUT] code.b`` without a second positional parser."""
    if "--compile-python" not in arguments:
        return arguments, None, False
    index = arguments.index("--compile-python")
    if arguments.count("--compile-python") > 1:
        raise ValueError("--compile-python can be specified only once")
    if index >= len(arguments) - 1:
        raise ValueError("--compile-python requires a BF source file")
    target = None if index == len(arguments) - 2 else arguments[index + 1]
    return arguments[:index] + arguments[index + 1 + (target is not None):], target, True


def main(argv: list[str] | None = None, stdin: object | None = None) -> int:
    """Execute BF or emit standalone Python while keeping program stdout clean."""
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        raw_arguments, compile_target, compiling = _extract_compile_target(raw_arguments)
    except ValueError as error:
        print(f"brainfuck.py: error: {error}", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="A configurable Brainfuck interpreter.")
    parser.add_argument("source_file", metavar="code.b")
    parser.add_argument("-m", "--mode", choices=runtime.PROFILES, default="unlimited")
    parser.add_argument("--cell-mode", choices=(runtime.UNBOUNDED, "wrap"))
    parser.add_argument("-b", "--cell-bits", type=_parse_cell_bits)
    parser.add_argument("--tape-min", type=_parse_bound)
    parser.add_argument("--tape-max", type=_parse_bound)
    parser.add_argument("--pointer-bounds", choices=("error", "wrap"))
    parser.add_argument("-e", "--eof-mode", choices=("zero", "unchanged", "error"))
    parser.add_argument("-o", "--output-mode", choices=("unicode", "byte"))
    parser.add_argument("--comment-style", choices=("none", "block"))
    parser.add_argument("--debug-command", choices=("none", "qdb"))
    parser.add_argument("--debug-number-format", choices=("signed", "unsigned"))
    parser.add_argument("-s", "--max-steps", type=_parse_non_negative_integer)
    parser.add_argument("-O", "--no-optimize", action="store_true")
    parser.add_argument("--optimization-level", type=int, choices=(0, 1, 2))
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--trace-format", choices=("text", "jsonl"), default="text")
    parser.add_argument("--trace-file")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--dump-ir", action="store_true")
    parser.epilog = "--compile-python [OUTPUT] code.b emits standalone Python to stdout or OUTPUT."
    arguments = parser.parse_args(raw_arguments)
    config, level = runtime._configuration(
        arguments.mode, arguments.cell_mode, arguments.cell_bits, arguments.tape_min, arguments.tape_max,
        arguments.pointer_bounds, arguments.eof_mode, arguments.output_mode,
        arguments.comment_style, arguments.debug_command, arguments.debug_number_format, arguments.max_steps,
        not arguments.no_optimize, arguments.optimization_level,
    )
    sourcecode = Path(arguments.source_file).read_text(encoding="utf-8")
    options = dict(mode=arguments.mode, cell_mode=arguments.cell_mode, cell_bits=arguments.cell_bits,
                   tape_min=arguments.tape_min, tape_max=arguments.tape_max,
                   pointer_bounds=arguments.pointer_bounds, eof_mode=arguments.eof_mode,
                    output_mode=arguments.output_mode, comment_style=arguments.comment_style,
                   debug_command=arguments.debug_command, debug_number_format=arguments.debug_number_format,
                   max_steps=arguments.max_steps,
                   optimize=not arguments.no_optimize, optimization_level=level)
    if compiling:
        generated = compile_to_python(sourcecode, **options)
        if compile_target is None:
            sys.stdout.write(generated)
        else:
            Path(compile_target).write_text(generated, encoding="utf-8")
        return 0
    if arguments.dump_ir:
        _dump_ir(sourcecode, config, level, arguments.trace or arguments.profile, sys.stderr)
    trace_stream: TextIO | None = None
    if arguments.trace:
        trace_stream = open(arguments.trace_file, "w", encoding="utf-8") if arguments.trace_file else sys.stderr
    try:
        profile: dict[str, object] | None = {} if arguments.profile else None
        trace = _trace_writer(trace_stream, arguments.trace_format) if trace_stream else None
        if config.output_mode == "byte":
            input_stream = getattr(stdin or sys.stdin, "buffer", stdin or sys.stdin)
            sys.stdout.buffer.write(runtime.interpret_bytes(sourcecode, input_reader=lambda: input_stream.read(1), trace=trace, profile=profile, **options))
        else:
            input_stream = stdin or sys.stdin
            sys.stdout.write(runtime.interpret(sourcecode, input_reader=lambda: input_stream.read(1), trace=trace, profile=profile, **options))
        if profile is not None:
            sys.stderr.write(json.dumps(profile, sort_keys=True) + "\n")
    finally:
        if trace_stream is not None and trace_stream is not sys.stderr:
            trace_stream.close()
    return 0
