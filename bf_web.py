"""Serve the browser workbench and its local Python API."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import brainfuck
from bf_codegen import compile_to_python
from bf_formatter import format_source


WEB_DIRECTORY = Path(__file__).with_name("web")
OPTION_NAMES = frozenset(
    {
        "mode", "cell_mode", "cell_bits", "tape_min", "tape_max",
        "pointer_bounds", "eof_mode", "output_mode", "comment_style",
        "debug_command", "debug_number_format", "max_steps", "optimize",
        "optimization_level",
    }
)


def _options(payload: dict[str, Any]) -> dict[str, Any]:
    options = payload.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("options must be an object")
    return {name: options[name] for name in OPTION_NAMES if name in options}


class WorkbenchHandler(SimpleHTTPRequestHandler):
    """Serve static files and expose local-only execution endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIRECTORY), **kwargs)

    def do_POST(self) -> None:
        if self.path not in {"/api/run", "/api/format", "/api/compile"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("source"), str):
                raise ValueError("source must be a string")
            response = self._handle_api(payload)
            self._send_json(HTTPStatus.OK, response)
        except (ValueError, TypeError, UnicodeEncodeError, brainfuck.EOFInputError, brainfuck.TapeBoundsError, brainfuck.StepLimitExceeded, SyntaxError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def _handle_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        return handle_api(self.path, payload)

    @staticmethod
    def _ir(source: str, config: brainfuck._RuntimeConfig, options: dict[str, Any]) -> list[dict[str, object]]:
        level = options.get("optimization_level", 1 if options.get("optimize", True) else 0)
        operations = brainfuck._compile(
            source,
            level >= 1 and options.get("max_steps") is None and config.tape_min is None and config.tape_max is None,
            level >= 1 and options.get("max_steps") is None,
            config.comment_style,
            config.debug_command,
        )
        return [{"operation": operation.kind, "argument": operation.argument, "steps": operation.step_count} for operation in operations]

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def handle_api(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run one browser API request without requiring an HTTP test harness."""
    source = payload["source"]
    options = _options(payload)
    if path == "/api/format":
        return {"source": format_source(source, comment_style=options.get("comment_style", "none"), debug_command=options.get("debug_command", "none"))}
    if path == "/api/compile":
        return {"python": compile_to_python(source, **options)}

    profile: dict[str, object] = {}
    trace: list[dict[str, object]] = []
    config, _ = brainfuck._configuration(
        options.get("mode", "unlimited"), options.get("cell_mode"), options.get("cell_bits"),
        options.get("tape_min"), options.get("tape_max"), options.get("pointer_bounds"),
        options.get("eof_mode"), options.get("output_mode"), options.get("comment_style"),
        options.get("debug_command"), options.get("debug_number_format"), options.get("max_steps"),
        options.get("optimize", True), options.get("optimization_level"),
    )
    input_data = payload.get("input", "")
    if not isinstance(input_data, str):
        raise ValueError("input must be a string")
    if config.output_mode == "byte":
        result = brainfuck.interpret_bytes(source, input_data.encode("latin-1"), trace=trace.append, profile=profile, **options).decode("latin-1")
    else:
        result = brainfuck.interpret(source, input_data, trace=trace.append, profile=profile, **options)
    return {"output": result, "profile": profile, "trace": trace, "ir": WorkbenchHandler._ir(source, config, options)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args(argv)
    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), WorkbenchHandler)
    print(f"Configurable Brainfuck workbench: http://127.0.0.1:{arguments.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
