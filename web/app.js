const $ = (id) => document.getElementById(id);
const source = $("source"), output = $("output"), inspect = $("inspect");
const HELLO = "++++++++++[>+++++++>++++++++++>+++>+<<<<-]>++.>+.+++++++..+++.>++.<<+++++++++++++++.>.+++.------.--------.>+.>.";
const PROFILES = {
  unlimited: { cellMode: "unbounded", bits: null, min: null, max: null, bounds: "error", eof: "zero", output: "unicode" },
  standard: { cellMode: "wrap", bits: 8, min: null, max: null, bounds: "error", eof: "zero", output: "byte" },
  "standard-one-way": { cellMode: "wrap", bits: 8, min: 0, max: null, bounds: "error", eof: "zero", output: "byte" },
  strict: { cellMode: "wrap", bits: 8, min: 0, max: 29999, bounds: "error", eof: "zero", output: "byte" }
};
const state = { result: null, view: "profile" };
const STORAGE_KEY = "configurable-brainfuck:web:v1";
source.value = HELLO;

function saveWorkbench() {
  try {
    const controls = {};
    document.querySelectorAll(".settings select,.settings input").forEach((element) => { controls[element.id] = element.value; });
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ source: source.value, input: $("input").value, controls, view: state.view }));
  } catch (_) {
    // Storage may be disabled by the browser; the workbench remains usable.
  }
}

function restoreWorkbench() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (!saved) return;
    if (typeof saved.source === "string") source.value = saved.source;
    if (typeof saved.input === "string") $("input").value = saved.input;
    for (const [id, value] of Object.entries(saved.controls || {})) {
      const control = $(id);
      if (control && typeof value === "string") control.value = value;
    }
    if (["profile", "ir", "trace"].includes(saved.view)) state.view = saved.view;
  } catch (_) {
    // Ignore malformed or obsolete saved state rather than blocking startup.
  }
}

function settings() {
  const profile = PROFILES[$("mode").value];
  const choice = (id, fallback) => $(id).value === "inherit" ? fallback : $(id).value;
  const number = (id, fallback) => $(id).value === "" ? fallback : Number($(id).value);
  const cellMode = choice("cellMode", profile.cellMode);
  return {
    cellMode,
    bits: cellMode === "wrap" ? (number("cellBits", profile.bits) || 8) : null,
    min: number("tapeMin", profile.min), max: number("tapeMax", profile.max),
    bounds: choice("pointerBounds", profile.bounds), eof: choice("eofMode", profile.eof),
    output: choice("outputMode", profile.output), maxSteps: number("maxSteps", null),
    optimization: Number($("optimization").value), comments: $("commentStyle").value,
    debug: $("debugCommand").value, debugNumber: $("debugNumber").value
  };
}

function preprocess(text, options) {
  if (options.comments !== "block") return text;
  let result = "", index = 0;
  while (index < text.length) {
    if (!text.startsWith("/*", index)) { result += text[index++]; continue; }
    const end = text.indexOf("*/", index + 2);
    if (end < 0) throw Error(`Unclosed block comment at offset ${index}`);
    result += text.slice(index, end + 2).replace(/[^\n]/g, " ");
    index = end + 2;
  }
  return result;
}

function compile(text, options) {
  const commandSet = new Set("><+-.,[]" + (options.debug === "qdb" ? "#" : ""));
  const commands = [...preprocess(text, options)].filter((char) => commandSet.has(char));
  const jumps = new Map(), stack = [];
  commands.forEach((command, index) => {
    if (command === "[") stack.push(index);
    if (command === "]") {
      if (!stack.length) throw Error("Unmatched ]");
      const opening = stack.pop(); jumps.set(opening, index); jumps.set(index, opening);
    }
  });
  if (stack.length) throw Error("Unmatched [");
  const operations = [];
  for (let index = 0; index < commands.length;) {
    const command = commands[index];
    const group = "><".includes(command) ? "><" : "+-".includes(command) ? "+-" : null;
    if (group && options.optimization > 0 && options.maxSteps === null) {
      let delta = 0, start = index;
      while (index < commands.length && group.includes(commands[index])) {
        delta += ">+".includes(commands[index]) ? 1 : -1; index++;
      }
      if (delta) operations.push({ kind: group === "><" ? "move" : "add", argument: delta, steps: index - start, raw: start });
      continue;
    }
    const kind = { ">": "move", "<": "move", "+": "add", "-": "add", ".": "out", ",": "in", "#": "debug", "[": "jz", "]": "jn" }[command];
    operations.push({ kind, argument: ">+".includes(command) ? 1 : "<-".includes(command) ? -1 : 0, steps: 1, raw: index++ });
  }
  const rawToOperation = new Map(operations.map((operation, index) => [operation.raw, index]));
  operations.forEach((operation) => { if (operation.kind === "jz" || operation.kind === "jn") operation.argument = rawToOperation.get(jumps.get(operation.raw)); });
  return operations;
}

function formatSource(text, options) {
  const active = new Set("><+-.,[]" + (options.debug === "qdb" ? "#" : ""));
  let level = 0, block = ""; const lines = [];
  const flush = () => { if (block) { lines.push(" ".repeat(level) + block); block = ""; } };
  for (const char of preprocess(text, options)) {
    if (!active.has(char)) continue;
    if (char === "[") { flush(); lines.push(" ".repeat(level) + char); level++; continue; }
    if (char === "]") { flush(); level--; }
    if (level < 0) throw Error("Unmatched ]");
    if (char === "]" || char === "#") { lines.push(" ".repeat(level) + char); continue; }
    block += char;
  }
  flush();
  if (level) throw Error("Unmatched [");
  return lines.join("\n") + (lines.length ? "\n" : "");
}

function run() {
  try {
    const options = settings();
    if (options.debug === "qdb" && (options.cellMode !== "wrap" || options.bits !== 8)) throw Error("qdb # requires 8-bit fixed-width Cells");
    if (options.bounds === "wrap" && (options.min === null || options.max === null)) throw Error("Pointer wrap requires finite tape bounds");
    const operations = compile(source.value, options), tape = new Map(), trace = [], counts = {}, input = [...$("input").value], chunks = [];
    let pointer = 0, instruction = 0, steps = 0, inputIndex = 0, pointerMin = 0, pointerMax = 0;
    const get = () => tape.get(pointer) || 0n;
    const put = (value) => { if (options.cellMode === "wrap") { const modulo = 1n << BigInt(options.bits); value = ((value % modulo) + modulo) % modulo; } if (value === 0n) tape.delete(pointer); else tape.set(pointer, value); };
    const debug = () => {
      let row = "\n";
      for (let index = 0; index < 64; index++) { let value = Number(tape.get(index) || 0n); if (options.debugNumber === "signed" && value >= 128) value -= 256; row += String(value).padStart(4); }
      return row + "\n" + " ".repeat(Math.max(0, pointer * 4 + 4)) + "^\n";
    };
    while (instruction < operations.length) {
      const operation = operations[instruction];
      if (options.maxSteps !== null && steps + operation.steps > options.maxSteps) throw Error(`Step limit ${options.maxSteps} reached after ${steps}`);
      if (trace.length < 5000) trace.push({ step: steps, op: operation.kind, arg: operation.argument, pointer, cell: get().toString() });
      steps += operation.steps; counts[operation.kind] = (counts[operation.kind] || 0) + operation.steps;
      if (operation.kind === "move") {
        pointer += operation.argument;
        if ((options.min !== null && pointer < options.min) || (options.max !== null && pointer > options.max)) {
          if (options.bounds !== "wrap") throw Error(`Pointer ${pointer} is outside configured Tape`);
          const width = options.max - options.min + 1; pointer = options.min + ((pointer - options.min) % width + width) % width;
        }
        pointerMin = Math.min(pointerMin, pointer); pointerMax = Math.max(pointerMax, pointer);
      } else if (operation.kind === "add") put(get() + BigInt(operation.argument));
      else if (operation.kind === "out") { const value = get(); chunks.push(options.output === "byte" ? String.fromCharCode(Number(value & 255n)) : String.fromCodePoint(Number(value))); }
      else if (operation.kind === "in") { const char = input[inputIndex++]; if (char) put(BigInt(char.codePointAt(0))); else if (options.eof === "zero") put(0n); else if (options.eof === "error") throw Error("Input exhausted"); }
      else if (operation.kind === "debug") chunks.push(debug());
      else if (operation.kind === "jz" && get() === 0n) instruction = operation.argument;
      else if (operation.kind === "jn" && get() !== 0n) instruction = operation.argument;
      instruction++;
    }
    state.result = { operations, trace, profile: { steps, nonzeroCells: tape.size, pointerMin, pointerMax, instructionCounts: counts }, output: chunks.join("") };
    output.textContent = state.result.output || "(no output)"; renderInspect();
  } catch (error) { output.textContent = `Error: ${error.message}`; inspect.textContent = ""; }
}

function renderInspect() {
  if (!state.result) return;
  if (state.view === "profile") inspect.textContent = JSON.stringify(state.result.profile, null, 2);
  else if (state.view === "ir") inspect.textContent = state.result.operations.map((op, index) => `${String(index).padStart(4, "0")}  ${op.kind.padEnd(6)} ${String(op.argument).padStart(5)}  steps=${op.steps}`).join("\n");
  else inspect.textContent = state.result.trace.map((event) => `${event.step}  ${event.op.padEnd(6)} arg=${String(event.arg).padStart(4)} ptr=${String(event.pointer).padStart(5)} cell=${event.cell}`).join("\n");
}

function generatePython() {
  try {
    const options = settings(), operations = compile(source.value, options);
    const py = (value) => value === null ? "None" : typeof value === "string" ? JSON.stringify(value) : String(value);
    const ops = operations.map((op) => `(${JSON.stringify(op.kind)}, ${op.argument}, ${op.steps})`).join(",\n    ");
    const lines = [
      "# Generated by Configurable Brainfuck Web", "import sys", "", "OPS = [", `    ${ops}`, "]",
      `CELL_MODE = ${py(options.cellMode)}`, `CELL_BITS = ${py(options.bits)}`, `TAPE_MIN = ${py(options.min)}`, `TAPE_MAX = ${py(options.max)}`,
      `POINTER_BOUNDS = ${py(options.bounds)}`, `EOF_MODE = ${py(options.eof)}`, `OUTPUT_MODE = ${py(options.output)}`,
      `DEBUG_NUMBER_FORMAT = ${py(options.debugNumber)}`, `MAX_STEPS = ${py(options.maxSteps)}`, "", "tape = {}", "pointer = instruction = steps = 0",
      "input_stream = sys.stdin.buffer if OUTPUT_MODE == 'byte' else sys.stdin", "output_stream = sys.stdout.buffer if OUTPUT_MODE == 'byte' else sys.stdout",
      "while instruction < len(OPS):", "    operation, argument, step_count = OPS[instruction]", "    if MAX_STEPS is not None and steps + step_count > MAX_STEPS:", "        raise RuntimeError(f'maximum step count {MAX_STEPS} reached after {steps} steps')", "    steps += step_count", "    value = tape.get(pointer, 0)",
      "    if operation == 'move':", "        pointer += argument", "        if (TAPE_MIN is not None and pointer < TAPE_MIN) or (TAPE_MAX is not None and pointer > TAPE_MAX):", "            if POINTER_BOUNDS == 'wrap':", "                pointer = TAPE_MIN + (pointer - TAPE_MIN) % (TAPE_MAX - TAPE_MIN + 1)", "            else: raise IndexError('pointer outside configured Tape')",
      "    elif operation == 'add':", "        value += argument", "        if CELL_MODE == 'wrap': value %= 1 << CELL_BITS", "        if value: tape[pointer] = value", "        else: tape.pop(pointer, None)",
      "    elif operation == 'out':", "        output_stream.write(bytes([value & 255]) if OUTPUT_MODE == 'byte' else chr(value))",
      "    elif operation == 'in':", "        character = input_stream.read(1)", "        if character:", "            value = character[0] if isinstance(character, bytes) else ord(character)", "            if CELL_MODE == 'wrap': value %= 1 << CELL_BITS", "            if value: tape[pointer] = value", "            else: tape.pop(pointer, None)", "        elif EOF_MODE == 'zero': tape.pop(pointer, None)", "        elif EOF_MODE == 'error': raise EOFError('input exhausted')",
      "    elif operation == 'debug':", "        cells = ''.join(f'{v if DEBUG_NUMBER_FORMAT == \"unsigned\" or v < 128 else v - 256:4d}' for v in (tape.get(i, 0) for i in range(64)))", "        debug = f'\\n{cells}\\n{\" \" * max(0, pointer * 4 + 4)}^\\n'", "        output_stream.write(debug.encode('ascii') if OUTPUT_MODE == 'byte' else debug)",
      "    elif operation == 'jz' and value == 0: instruction = argument", "    elif operation == 'jn' and value != 0: instruction = argument", "    instruction += 1", ""
    ];
    output.textContent = lines.join("\n");
  } catch (error) { output.textContent = `Error: ${error.message}`; }
}

function updateStats() { $("sourceStats").textContent = `${[...source.value].filter((char) => "><+-.,[]".includes(char)).length} commands`; }
restoreWorkbench();
$("runCode").onclick = run;
$("formatCode").onclick = () => { try { source.value = formatSource(source.value, settings()); updateStats(); } catch (error) { output.textContent = `Error: ${error.message}`; } };
$("generatePython").onclick = generatePython;
$("loadHello").onclick = () => { source.value = HELLO; updateStats(); saveWorkbench(); };
$("resetSettings").onclick = () => { document.querySelectorAll(".settings select,.settings input").forEach((element) => { if (element.tagName === "SELECT") element.selectedIndex = 0; else element.value = ""; }); saveWorkbench(); };
$("copyOutput").onclick = () => navigator.clipboard?.writeText(output.textContent);
document.querySelectorAll(".tab").forEach((button) => { if (button.dataset.view === state.view) button.classList.add("active"); else button.classList.remove("active"); button.onclick = () => { document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active")); button.classList.add("active"); state.view = button.dataset.view; saveWorkbench(); renderInspect(); }; });
source.oninput = () => { updateStats(); saveWorkbench(); };
$("input").oninput = saveWorkbench;
document.querySelectorAll(".settings select,.settings input").forEach((element) => element.onchange = saveWorkbench);
updateStats();
