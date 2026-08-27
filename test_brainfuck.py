import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from brainfuck import (
    EOFInputError,
    StepLimitExceeded,
    TapeBoundsError,
    compile_to_python,
    interpret,
    interpret_bytes,
    main,
)


HELLO_WORLD = (
    "+" * 10
    + "[>+++++++>++++++++++>+++>+<<<<-]"
    ">++.>+.+++++++..+++.>++.<<+++++++++++++++."
    ">.+++.------.--------.>+.>."
)

SEMANTIC_CASES = (
    ("U-CELL-01", "+" * 256 + ".", {}, chr(256)),
    ("U-TAPE-01", "<+.>+.", {}, "\x01\x01"),
    ("S-CELL-01", "+" * 256 + ".", {"mode": "standard"}, "\x00"),
    ("S-CELL-02", "-[-].", {"mode": "standard"}, "\x00"),
    ("C-CELL-01", "+" * 16 + ".", {"cell_bits": 4, "output_mode": "byte"}, "\x00"),
    ("C-EOF-01", "+,.", {"eof_mode": "unchanged"}, "\x01"),
    ("C-OUTPUT-01", "-.", {"output_mode": "byte"}, "\xff"),
)

SEMANTIC_ERROR_CASES = (
    ("B-TAPE-01", "<", {"mode": "standard-one-way"}, TapeBoundsError),
    ("B-TAPE-02", ">" * 30000, {"mode": "strict"}, TapeBoundsError),
    ("B-EOF-01", ",", {"eof_mode": "error"}, EOFInputError),
)


class BrainfuckInterpreterTests(unittest.TestCase):
    def test_imported_interpret_function(self) -> None:
        self.assertEqual(interpret(HELLO_WORLD), "Hello World!\n")

    def test_unrestricted_tape_and_cells(self) -> None:
        self.assertEqual(interpret("<+.>+."), "\x01\x01")
        self.assertEqual(interpret("+" * 256 + "."), chr(256))

    def test_semantic_matrix_output_cases(self) -> None:
        for case_id, sourcecode, options, expected in SEMANTIC_CASES:
            with self.subTest(case_id=case_id):
                self.assertEqual(interpret(sourcecode, **options), expected)

    def test_standard_byte_io_and_text_api_validation(self) -> None:
        self.assertEqual(interpret_bytes(",.", bytes([255]), mode="standard"), bytes([255]))
        with self.assertRaises(ValueError):
            interpret(",.", chr(256), mode="standard")

    def test_semantic_matrix_error_cases(self) -> None:
        for case_id, sourcecode, options, error_type in SEMANTIC_ERROR_CASES:
            with self.subTest(case_id=case_id):
                with self.assertRaises(error_type):
                    interpret(sourcecode, **options)

    def test_custom_bounds_and_invalid_configuration(self) -> None:
        with self.assertRaises(TapeBoundsError):
            interpret("<<", tape_min=-1, tape_max=1)
        with self.assertRaises(ValueError):
            interpret("", tape_min=1)
        with self.assertRaises(ValueError):
            interpret("", mode="strict", cell_bits="unbounded", cell_mode="wrap")

    def test_explicit_configuration_overrides_profile(self) -> None:
        self.assertEqual(
            interpret(
                "+" * 256 + ".",
                mode="strict",
                cell_mode="unbounded",
                output_mode="unicode",
            ),
            chr(256),
        )
        self.assertEqual(
            interpret("<+.", mode="strict", tape_min="unbounded"),
            "\x01",
        )

    def test_step_limit_counts_source_instructions(self) -> None:
        with self.assertRaises(StepLimitExceeded) as caught:
            interpret("++++.", max_steps=4)
        self.assertEqual(caught.exception.executed_steps, 4)

    def test_optimization_levels_preserve_semantics(self) -> None:
        for level in (0, 1, 2):
            with self.subTest(level=level):
                self.assertEqual(
                    interpret("-[-].", mode="standard", optimization_level=level),
                    "\x00",
                )
        with self.assertRaises(StepLimitExceeded):
            interpret("-[-].", mode="standard", optimization_level=2, max_steps=10)
        self.assertEqual(interpret("++++.", max_steps=5), chr(4))
        self.assertEqual(interpret("+-.", max_steps=3), "\x00")
        with self.assertRaises(StepLimitExceeded) as caught:
            interpret("+[.-]", max_steps=4)
        self.assertEqual(caught.exception.executed_steps, 4)

    def test_loops_input_and_syntax_errors(self) -> None:
        self.assertEqual(interpret("++[>++<-]>."), chr(4))
        self.assertEqual(interpret(",.,.", "AB"), "AB")
        with self.assertRaises(SyntaxError):
            interpret("[")
        with self.assertRaises(SyntaxError):
            interpret("]")

    def test_command_line_file_execution(self) -> None:
        interpreter = Path(__file__).with_name("brainfuck.py")
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "code.bf"
            source_file.write_text(HELLO_WORLD, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(interpreter), str(source_file)],
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Hello World!\n")
        self.assertEqual(result.stderr, "")

    def test_command_line_consumes_input_at_comma(self) -> None:
        interpreter = Path(__file__).with_name("brainfuck.py")
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "input.bf"
            source_file.write_text(",.", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(interpreter), str(source_file)],
                capture_output=True,
                check=False,
                input="Z",
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Z")

    def test_command_line_standard_mode(self) -> None:
        interpreter = Path(__file__).with_name("brainfuck.py")
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "wrap.bf"
            source_file.write_text("-[-].", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(interpreter), "--mode", "standard", str(source_file)],
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"\x00")

    def test_command_line_strict_uses_byte_io(self) -> None:
        interpreter = Path(__file__).with_name("brainfuck.py")
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "byte-io.bf"
            source_file.write_text(",.", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(interpreter), "-m", "strict", str(source_file)],
                capture_output=True,
                check=False,
                input=bytes([255]),
            )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, bytes([255]))

    def test_python_code_generation(self) -> None:
        generated = compile_to_python("+.")
        self.assertIn("Generated by unlimited-brainfuck", generated)
        self.assertIn("OPERATIONS", generated)
        with tempfile.TemporaryDirectory() as directory:
            generated_file = Path(directory) / "program.py"
            generated_file.write_text(generated, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(generated_file)], capture_output=True, check=False
            )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"\x01")

    def test_python_code_generation_optimization_levels(self) -> None:
        o0 = compile_to_python("+++++.", optimization_level=0)
        o1 = compile_to_python("+++++.", optimization_level=1)
        o2 = compile_to_python("-[-].", mode="strict", optimization_level=2)
        limited = compile_to_python("+++++.", max_steps=6, optimization_level=1)
        self.assertIn("('add', 1, 1)", o0)
        self.assertIn("('add', 5, 5)", o1)
        self.assertNotIn("('add', 1, 1)", o1)
        self.assertIn("('clear', 0, 0)", o2)
        self.assertIn("('add', 1, 1)", limited)

        with tempfile.TemporaryDirectory() as directory:
            generated_file = Path(directory) / "optimized.py"
            generated_file.write_text(o2, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(generated_file)], capture_output=True, check=False
            )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"\x00")

    def test_command_line_python_compilation(self) -> None:
        interpreter = Path(__file__).with_name("brainfuck.py")
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "source.bf"
            output_file = Path(directory) / "program.py"
            source_file.write_text("+.", encoding="utf-8")
            stdout_result = subprocess.run(
                [sys.executable, str(interpreter), "--compile-python", str(source_file)],
                capture_output=True,
                check=False,
                text=True,
            )
            file_result = subprocess.run(
                [
                    sys.executable,
                    str(interpreter),
                    "--optimization-level",
                    "1",
                    "--compile-python",
                    str(output_file),
                    str(source_file),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            generated_result = subprocess.run(
                [sys.executable, str(output_file)], capture_output=True, check=False
            )
            generated_source = output_file.read_text(encoding="utf-8")
        self.assertEqual(stdout_result.returncode, 0, stdout_result.stderr)
        self.assertIn("Generated by unlimited-brainfuck", stdout_result.stdout)
        self.assertEqual(file_result.returncode, 0, file_result.stderr)
        self.assertEqual(file_result.stdout, "")
        self.assertEqual(generated_result.stdout, b"\x01")
        self.assertIn("('add', 1, 1)", generated_source)

    def test_source_locations_trace_profile_and_ir(self) -> None:
        with self.assertRaises(SyntaxError) as caught:
            interpret("comment\n[")
        self.assertIn("line 2, column 1", str(caught.exception))
        with self.assertRaises(TapeBoundsError) as caught:
            interpret("comment\n<", mode="standard-one-way")
        self.assertIn("line 2, column 1", str(caught.exception))

        events: list[dict[str, object]] = []
        profile: dict[str, object] = {}
        self.assertEqual(interpret("++.", trace=events.append, profile=profile), "\x02")
        self.assertEqual([event["operation"] for event in events], ["add", "add", "output"])
        self.assertEqual(profile["steps"], 3)
        self.assertEqual(profile["instruction_counts"], {"add": 2, "output": 1})

        interpreter = Path(__file__).with_name("brainfuck.py")
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "trace.bf"
            source_file.write_text("++.", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(interpreter), "--trace", "--profile", "--dump-ir", str(source_file)],
                capture_output=True,
                check=False,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "\x02")
        self.assertIn("step=0", result.stderr)
        self.assertIn("elapsed_seconds", result.stderr)
        self.assertIn("0000 add", result.stderr)
        self.assertIn("0001 add", result.stderr)

    def test_command_line_short_options(self) -> None:
        interpreter = Path(__file__).with_name("brainfuck.py")
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "short-options.bf"
            source_file.write_text("-[-].", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(interpreter),
                    "-m",
                    "standard",
                    "-b",
                    "8",
                    "-o",
                    "byte",
                    "-s",
                    "1000",
                    "-O",
                    str(source_file),
                ],
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"\x00")

    def test_command_line_does_not_read_input_without_comma(self) -> None:
        class UnreadableInput:
            def read(self, size: int = -1) -> str:
                raise AssertionError("stdin should not be read")

        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "code.bf"
            source_file.write_text("", encoding="utf-8")
            self.assertEqual(main([str(source_file)], UnreadableInput()), 0)


if __name__ == "__main__":
    unittest.main()
