const $ = (id) => document.getElementById(id);
const source = $("source"), output = $("output"), inspect = $("inspect");
const HELLO = "++++++++++[>+++++++>++++++++++>+++>+<<<<-]>++.>+.+++++++..+++.>++.<<+++++++++++++++.>.+++.------.--------.>+.>.";
const PROFILES = {
  unlimited: { cellMode: "unbounded", bits: null, min: null, max: null, bounds: "error", eof: "zero", output: "unicode" },
  standard: { cellMode: "wrap", bits: 8, min: null, max: null, bounds: "error", eof: "zero", output: "byte" },
  "standard-one-way": { cellMode: "wrap", bits: 8, min: 0, max: null, bounds: "error", eof: "zero", output: "byte" },
  strict: { cellMode: "wrap", bits: 8, min: 0, max: 29999, bounds: "error", eof: "zero", output: "byte" }
};
const STORAGE_KEY = "configurable-brainfuck:web:v1";
const state = { result: null, view: "profile" };
source.value = HELLO;

function saveWorkbench() {
  try {
    const controls = {};
    document.querySelectorAll(".settings select,.settings input").forEach((element) => { controls[element.id] = element.value; });
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ source: source.value, input: $("input").value, controls, view: state.view }));
  } catch (_) { /* Browser storage may be unavailable. */ }
}

function restoreWorkbench() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (!saved) return;
    if (typeof saved.source === "string") source.value = saved.source;
    if (typeof saved.input === "string") $("input").value = saved.input;
    for (const [id, value] of Object.entries(saved.controls || {})) if ($(id) && typeof value === "string") $(id).value = value;
    if (["profile", "ir", "trace"].includes(saved.view)) state.view = saved.view;
  } catch (_) { /* Ignore malformed or obsolete saved state. */ }
}

function options() {
  const profile = PROFILES[$("mode").value];
  const pick = (id, fallback) => $(id).value === "inherit" ? fallback : $(id).value;
  const number = (id, fallback) => $(id).value === "" ? fallback : Number($(id).value);
  const cellMode = pick("cellMode", profile.cellMode);
  return {
    mode: $("mode").value, cell_mode: cellMode, cell_bits: cellMode === "wrap" ? (number("cellBits", profile.bits) || 8) : null,
    tape_min: number("tapeMin", profile.min), tape_max: number("tapeMax", profile.max),
    pointer_bounds: pick("pointerBounds", profile.bounds), eof_mode: pick("eofMode", profile.eof),
    output_mode: pick("outputMode", profile.output), max_steps: number("maxSteps", null),
    optimization_level: Number($("optimization").value), comment_style: $("commentStyle").value,
    debug_command: $("debugCommand").value, debug_number_format: $("debugNumber").value
  };
}

async function request(path) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source: source.value, input: $("input").value, options: options() }) });
  const payload = await response.json();
  if (!response.ok) throw Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

async function run() {
  try {
    output.textContent = "Running...";
    const payload = await request("/api/run");
    state.result = payload;
    output.textContent = payload.output || "(no output)";
    renderInspect();
  } catch (error) { output.textContent = `Error: ${error.message}`; inspect.textContent = ""; }
}

function renderInspect() {
  if (!state.result) return;
  if (state.view === "profile") inspect.textContent = JSON.stringify(state.result.profile, null, 2);
  else if (state.view === "ir") {
    const header = "INDEX  OPERATION         ARGUMENT  STEPS";
    const divider = "-----  ----------------  --------  -----";
    inspect.textContent = [header, divider, ...state.result.ir.map((op, index) => `${String(index).padStart(5)}  ${op.operation.padEnd(16)}  ${String(op.argument).padStart(8)}  ${String(op.steps).padStart(5)}`)].join("\n");
  } else {
    const header = "STEP    LOCATION       OPERATION         ARGUMENT  POINTER  CELL";
    const divider = "------  -------------  ----------------  --------  -------  ----";
    inspect.textContent = [header, divider, ...state.result.trace.map((event) => {
      const location = (event.location || "").replace("line ", "L").replace(", column ", ":");
      return `${String(event.step).padStart(6)}  ${location.padEnd(13)}  ${event.operation.padEnd(16)}  ${String(event.argument).padStart(8)}  ${String(event.pointer).padStart(7)}  ${event.cell}`;
    })].join("\n");
  }
}

async function format() {
  try { const payload = await request("/api/format"); source.value = payload.source; updateStats(); saveWorkbench(); }
  catch (error) { output.textContent = `Error: ${error.message}`; }
}

async function generatePython() {
  try { output.textContent = (await request("/api/compile")).python; }
  catch (error) { output.textContent = `Error: ${error.message}`; }
}

function updateStats() { $("sourceStats").textContent = `${[...source.value].filter((char) => "><+-.,[]".includes(char)).length} commands`; }
restoreWorkbench();
$("runCode").onclick = run;
$("formatCode").onclick = format;
$("generatePython").onclick = generatePython;
$("loadHello").onclick = () => { source.value = HELLO; updateStats(); saveWorkbench(); };
$("resetSettings").onclick = () => { document.querySelectorAll(".settings select,.settings input").forEach((element) => { if (element.tagName === "SELECT") element.selectedIndex = 0; else element.value = ""; }); saveWorkbench(); };
$("copyOutput").onclick = () => navigator.clipboard?.writeText(output.textContent);
document.querySelectorAll(".tab").forEach((button) => { if (button.dataset.view === state.view) button.classList.add("active"); else button.classList.remove("active"); button.onclick = () => { document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active")); button.classList.add("active"); state.view = button.dataset.view; saveWorkbench(); renderInspect(); }; });
source.oninput = () => { updateStats(); saveWorkbench(); };
$("input").oninput = saveWorkbench;
document.querySelectorAll(".settings select,.settings input").forEach((element) => element.onchange = saveWorkbench);
updateStats();
