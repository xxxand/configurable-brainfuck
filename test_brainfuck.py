import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from brainfuck import interpret, main


HELLO_WORLD = (
    "+" * 10
    + "[>+++++++>++++++++++>+++>+<<<<-]"
    ">++.>+.+++++++..+++.>++.<<+++++++++++++++."
    ">.+++.------.--------.>+.>."
)


class BrainfuckInterpreterTests(unittest.TestCase):
    def test_imported_interpret_function(self) -> None:
        self.assertEqual(interpret(HELLO_WORLD), "Hello World!\n")

    def test_unrestricted_tape_and_cells(self) -> None:
        self.assertEqual(interpret("<+.>+."), "\x01\x01")
        self.assertEqual(interpret("+" * 256 + "."), chr(256))

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
