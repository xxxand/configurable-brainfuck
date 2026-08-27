# Brainfuck Semantic Matrix

本文件是解释器的规范性行为定义。测试文件中的矩阵案例使用相同的类别和编号前缀，以避免文档与实现偏离。

## Configuration

`interpret()` 的默认 `mode="unlimited"` 保持无限制语义。其余模式是兼容性预设：

| Mode | `cell_mode` | `cell_bits` | `tape_min` | `tape_max` | `eof_mode` | `output_mode` |
|---|---|---:|---:|---:|---|---|
| `unlimited` | `unbounded` | none | none | none | `zero` | `unicode` |
| `standard` | `wrap` | 8 | none | none | `zero` | `byte` |
| `standard-one-way` | `wrap` | 8 | 0 | none | `zero` | `byte` |
| `strict` | `wrap` | 8 | 0 | 29999 | `zero` | `byte` |

非 `None` 的细调参数覆盖预设。`cell_bits`、`tape_min` 和 `tape_max` 可以传入字符串 `"unbounded"`，明确取消预设的相应限制；`None` 表示继承预设。

当显式设置 `cell_mode="wrap"` 而没有可继承的 `cell_bits` 时，解释器默认使用 8-bit。显式设置 `cell_mode="unbounded"` 会取消继承的位宽；Cell 模式本身不会改变预设的输出模式。

| Parameter | Values | Rule |
|---|---|---|
| `cell_mode` | `unbounded`, `wrap` | `unbounded` 使用 Python `int`；`wrap` 使用无符号模算术。 |
| `cell_bits` | positive integer, `unbounded`, `None` | `wrap` 的范围为 `0..2**bits-1`。 |
| `tape_min` | integer, `unbounded`, `None` | 指针允许的最小位置。 |
| `tape_max` | integer, `unbounded`, `None` | 指针允许的最大位置。 |
| `eof_mode` | `zero`, `unchanged`, `error` | `,` 在输入耗尽时的行为。 |
| `output_mode` | `unicode`, `byte` | `.` 的文本编码语义。 |
| `max_steps` | non-negative integer, `None` | 原始执行 BF 指令数的上限。 |
| `optimize` | `True`, `False` | 是否合并不影响语义的连续操作。 |

初始指针固定为 `0`，因此配置范围必须包含 `0`。`tape_min > tape_max`、不包含 `0` 的范围和冲突的 Cell 参数会引发 `ValueError`。

## Instruction Matrix

| Instruction | Unlimited Cell | Wrap Cell | Pointer / I/O behavior |
|---|---|---|---|
| `>` | unchanged | unchanged | 指针加一；超过 `tape_max` 抛出 `TapeBoundsError`。 |
| `<` | unchanged | unchanged | 指针减一；小于 `tape_min` 抛出 `TapeBoundsError`。 |
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
| `S-INPUT-01` | `,.`, standard mode, U+0100 input | NUL output after 8-bit input conversion. |
| `C-CELL-01` | 16 `+`, `cell_bits=4` | NUL output after 4-bit wrap. |
| `C-EOF-01` | `+,.`, `eof_mode=unchanged` | SOH output. |
| `C-OUTPUT-01` | `-.`, `output_mode=byte` | Byte value 255 output. |
| `B-TAPE-01` | `<`, `standard-one-way` | `TapeBoundsError`. |
| `B-TAPE-02` | `>` repeated 30000 times, strict mode | `TapeBoundsError`. |
| `B-EOF-01` | `,`, `eof_mode=error` | `EOFInputError`. |
| `L-STEPS-01` | `++++.`, `max_steps=4` | `StepLimitExceeded(executed_steps=4)`. |
