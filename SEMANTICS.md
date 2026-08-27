# Brainfuck Semantic Matrix

[English](SEMANTICS.en.md)

本文件是解释器的规范性行为定义。测试文件中的矩阵案例使用相同的类别和编号前缀，以避免文档与实现偏离。

## Configuration

`interpret()` 的默认 `mode="unlimited"` 保持无限制语义。其余模式是兼容性预设：

| Mode | `cell_mode` | `cell_bits` | `tape_min` | `tape_max` | `pointer_bounds` | `eof_mode` | `output_mode` |
|---|---|---:|---:|---:|---|---|---|
| `unlimited` | `unbounded` | none | none | none | `error` | `zero` | `unicode` |
| `standard` | `wrap` | 8 | none | none | `error` | `zero` | `byte` |
| `standard-one-way` | `wrap` | 8 | 0 | none | `error` | `zero` | `byte` |
| `strict` | `wrap` | 8 | 0 | 29999 | `error` | `zero` | `byte` |

非 `None` 的细调参数覆盖预设。`cell_bits`、`tape_min` 和 `tape_max` 可以传入字符串 `"unbounded"`，明确取消预设的相应限制；`None` 表示继承预设。

当显式设置 `cell_mode="wrap"` 而没有可继承的 `cell_bits` 时，解释器默认使用 8-bit。显式设置 `cell_mode="unbounded"` 会取消继承的位宽；Cell 模式本身不会改变预设的输出模式。

| Parameter | Values | Rule |
|---|---|---|
| `cell_mode` | `unbounded`, `wrap` | `unbounded` 使用 Python `int`；`wrap` 使用无符号模算术。 |
| `cell_bits` | positive integer, `unbounded`, `None` | `wrap` 的范围为 `0..2**bits-1`。 |
| `tape_min` | integer, `unbounded`, `None` | 指针允许的最小位置。 |
| `tape_max` | integer, `unbounded`, `None` | 指针允许的最大位置。 |
| `pointer_bounds` | `error`, `wrap` | 越过有限 Tape 边界时抛错或绕回另一端。 |
| `eof_mode` | `zero`, `unchanged`, `error` | `,` 在输入耗尽时的行为。 |
| `output_mode` | `unicode`, `byte` | `.` 的文本编码语义。 |
| `max_steps` | non-negative integer, `None` | 原始执行 BF 指令数的上限。 |
| `optimize` | `True`, `False` | 是否合并不影响语义的连续操作。 |

初始指针固定为 `0`，因此配置范围必须包含 `0`。`tape_min > tape_max`、不包含 `0` 的范围和冲突的 Cell 参数会引发 `ValueError`。

`pointer_bounds="wrap"` 仅可用于同时设置有限 `tape_min` 与 `tape_max` 的 Tape。半无限或双向无限 Tape 没有可绕回的另一端，会引发 `ValueError`。默认值 `error` 保持所有模式原有的越界报错行为。

## Instruction Matrix

| Instruction | Unlimited Cell | Wrap Cell | Pointer / I/O behavior |
|---|---|---|---|
| `>` | unchanged | unchanged | 指针加一；超过 `tape_max` 时按 `pointer_bounds` 抛 `TapeBoundsError` 或绕回 `tape_min`。 |
| `<` | unchanged | unchanged | 指针减一；小于 `tape_min` 时按 `pointer_bounds` 抛 `TapeBoundsError` 或绕回 `tape_max`。 |
| `+` | 加一，无上限 | 加一后模 `2**cell_bits` | 未使用 Cell 初始值为 `0`。 |
| `-` | 减一，无下限 | 减一后模 `2**cell_bits` | 8-bit 下 `0 - 1` 为 `255`。 |
| `.` | 当前值必须是 Unicode 码点，否则 `ValueError` | 同左，除非使用 byte 输出 | `byte` 输出当前值低 8 位对应的字符。 |
| `,` | 写入输入字符的 Unicode 码点 | 写入后模 `2**cell_bits` | 输入耗尽由 `eof_mode` 决定。 |
| `[` | 当前 Cell 为 `0` 时跳过匹配 `]` | 相同 | 括号必须匹配。 |
| `]` | 当前 Cell 非 `0` 时跳回匹配 `[` 后 | 相同 | 括号必须匹配。 |

所有非 BF 指令字符会被忽略。源码中的空白与注释不影响指令位置之外的语义。

## EOF Matrix

| `eof_mode` | `,` 读取不到字符时 |
|---|---|
| `zero` | 当前 Cell 写入 `0`。 |
| `unchanged` | 当前 Cell 保持原值。 |
| `error` | 抛出 `EOFInputError`。 |

命令行模式只在实际执行 `,` 时调用标准输入的 `read(1)`。没有 `,` 的程序不会等待输入。

在 `standard`、`standard-one-way` 和 `strict` 模式中，命令行通过原始字节流读取和输出。`interpret_bytes()` 是模块 API 中对应的字节入口；这些模式下 `interpret()` 只接受 ASCII 文本输入，其他文本输入引发 `ValueError`。

## Trace、Profile 与 IR

`--trace` 默认向标准错误输出 `step`、源位置、内部操作、参数、指针和当前 Cell。`--trace-format jsonl` 每行输出一个具有相同字段的 JSON 对象，`--trace-file` 可将结果重定向到文件。`--profile` 在标准错误输出 JSON，字段包括 `steps`、`elapsed_seconds`、`pointer_min`、`pointer_max`、`nonzero_cells` 和 `instruction_counts`。`--dump-ir` 显示编译后的操作及其源位置。

启用 trace 或 profile 时不合并指针移动或 Cell 增减，确保事件和指针范围对应原始 BF 指令。

## 优化与代码生成

`--optimization-level 0` 逐条执行原始 BF 指令。级别 `1`（默认）会合并连续的 `+` / `-`，并在没有 Tape 边界、步数限制、trace 或 profile 时合并连续 `>` / `<`。级别 `2` 仅在固定宽度 `wrap` Cell、没有步数限制、trace 或 profile 时，将恰好匹配 `[-]` 或 `[+]` 的循环折叠为清零；无限整数 Cell 下不使用该优化，因为负数值可能不终止。

`compile_to_python()` 和 `--compile-python [OUTPUT] code.bf` 生成独立 Python 脚本。未指定 `OUTPUT` 时脚本写到标准输出，指定后写入目标路径。生成脚本嵌入已解析的配置及 `OPERATIONS` IR：O0 为逐原始指令，O1 合并连续操作并保留其原始步数，O2 在符合条件时加入 `clear` 操作。启用 `max_steps` 或有限 Tape 时，生成器禁用会影响精确步数或中间边界检查的合并。

## Step Matrix

| Source | Executed source instructions | Notes |
|---|---:|---|
| `++++` | 4 | 每个 `+` 独立计步，即使优化后合并。 |
| `+-.` | 3 before completion | `+`、`-`、`.` 各计一步。 |
| `+[.-]` | 5 | 首次 `+`、`[`、`.`、`-`、`]` 各计一步。 |
| non-BF characters | 0 | 注释与空白不计步。 |

`max_steps` 为 `N` 时，解释器最多执行 `N` 条原始 BF 指令。在执行第 `N + 1` 条之前抛出 `StepLimitExceeded`，异常中的 `executed_steps` 为已完成的步数。启用步数限制时，解释器不合并 `+`、`-`、`>`、`<`，保证计数与关闭优化时一致。

## Matrix Cases

| ID | Source / configuration | Expected result |
|---|---|---|
| `U-CELL-01` | `+` repeated 256 times, unlimited mode | Unicode character U+0100, not byte wrap. |
| `U-TAPE-01` | `<+.>+.` | Both negative and positive pointer positions read and write. |
| `S-CELL-01` | `+` repeated 256 times, standard mode | NUL output after 8-bit wrap. |
| `S-CELL-02` | `-[-].`, standard mode | NUL output; `[-]` clears wrapped byte value 255. |
| `S-INPUT-01` | `,.`, standard mode, byte input `255` | Byte value `255` output. Text API rejects non-ASCII input. |
| `C-CELL-01` | 16 `+`, `cell_bits=4` | NUL output after 4-bit wrap. |
| `C-EOF-01` | `+,.`, `eof_mode=unchanged` | SOH output. |
| `C-OUTPUT-01` | `-.`, `output_mode=byte` | Byte value 255 output. |
| `B-TAPE-01` | `<`, `standard-one-way` | `TapeBoundsError`. |
| `B-TAPE-02` | `>` repeated 30000 times, strict mode | `TapeBoundsError`. |
| `B-EOF-01` | `,`, `eof_mode=error` | `EOFInputError`. |
| `L-STEPS-01` | `++++.`, `max_steps=4` | `StepLimitExceeded(executed_steps=4)`. |
