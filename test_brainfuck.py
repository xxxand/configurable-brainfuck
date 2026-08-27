import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from brainfuck import EOFInputError, StepLimitExceeded, TapeBoundsError, interpret, main


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
    ("S-INPUT-01", ",.", {"mode": "standard", "input_data": chr(256)}, "\x00"),
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
