# Unlimited Brainfuck Interpreter

中文 | [English](README.en.md)

一个可配置的 Brainfuck (BF) 解释器，使用 Python 标准库实现。默认提供无人工边界的无限制模式，也可切换为 8-bit 标准兼容模式。

## 特性

- 默认 Tape 使用稀疏字典，以带符号整数作为位置索引。指针可无限向左或向右移动，未使用的 Cell 读取为 `0`。
- 默认 Cell 使用 Python `int`，`+` 和 `-` 不进行范围截断；可配置为任意位宽的无符号回绕 Cell。
- 支持完整 BF 指令集：`>`、`<`、`+`、`-`、`.`、`,`、`[`、`]`。
- 在执行前检查括号匹配；多余 `[` 或 `]` 会引发 `SyntaxError`。
- 连续的指针移动和 Cell 增减会合并执行，减少解释开销；启用步数限制或 Tape 边界时会保留必要的逐指令执行。
- 除实际内存、运行时间和 Python 整数可用资源外，不设置 Tape、Cell 或指针的人为上限。

## 环境

需要 Python 3.10 或更新版本，不需要安装第三方依赖。

## 命令行

在项目目录执行：

```powershell
python brainfuck.py code.b
```

使用 8-bit 标准模式、单向标准模式或常见 30,000 Cell 严格模式：

```powershell
python brainfuck.py --mode standard code.b
python brainfuck.py --mode standard-one-way code.b
python brainfuck.py --mode strict code.b
```

高频参数可使用短形式：`-m`（模式）、`-b`（Cell 位宽）、`-e`（EOF 行为）、`-o`（输出模式）、`-s`（最大步数）和 `-O`（关闭优化）。

```powershell
python brainfuck.py -m strict -s 100000 code.b
python brainfuck.py -b 16 -o byte code.b
```

优化级别使用 `--optimization-level 0`、`1` 或 `2`：`0` 逐条执行，`1` 合并连续移动和增减（默认），`2` 还会在固定宽度回绕 Cell 模式中安全折叠 `[-]` 与 `[+]` 清零循环。开启 `max_steps`、trace 或 profile 时，解释器会保留保证精确语义所需的逐条操作。

细调示例：

```powershell
python brainfuck.py --cell-bits 16 --tape-min 0 --tape-max 65535 code.b
python brainfuck.py --mode strict --tape-max unbounded --max-steps 100000 code.b
python brainfuck.py --mode strict --pointer-bounds wrap code.b
```

`code.b` 是 Hello World 示例，输出：

```text
Hello World!
```

当 BF 程序执行到 `,` 时，解释器才从标准输入读取一个字符。没有 `,` 的程序不会等待标准输入。例如：

```powershell
python brainfuck.py input.b
```

若 `input.b` 内容为 `,.`，输入一个字符并按 Enter 后，程序会输出该字符。输入结束后继续执行 `,` 时会向当前 Cell 写入 `0`。

## 作为模块导入

```python
from brainfuck import interpret

sourcecode = """
    ++++++++++[>+++++++>++++++++++>+++>+<<<<-]
    >++.>+.+++++++..+++.>++.<<+++++++++++++++.
    >.+++.------.--------.>+.>.
"""

print(interpret(sourcecode), end="")
```

`interpret(sourcecode, input_data="")` 返回 BF 程序的完整输出字符串。`input_data` 中的字符依次供 `,` 指令读取，按 Unicode 码点写入 Cell。

运行配置使用关键字参数：

```python
# 8-bit 回绕、单向、30,000 Cell
interpret(sourcecode, mode="strict")

# 16-bit 回绕、单向、65,536 Cell
interpret(sourcecode, cell_bits=16, tape_min=0, tape_max=65535)

# 保持无限 Cell，但限制最多执行 100,000 条 BF 指令
interpret(sourcecode, max_steps=100_000)

# 有限 Tape 的指针绕回：从 0 左移到 29999
interpret(sourcecode, mode="strict", pointer_bounds="wrap")

# 启用 /* ... */ 块注释和 qdb 的 # 调试扩展
interpret(sourcecode, mode="strict", comment_style="block", debug_command="qdb")

# O0：逐条执行；O1 是默认；O2 仅在安全条件下优化清零循环
interpret(sourcecode, optimization_level=0)
```

`interpret()` 与 `compile_to_python()` 使用相同的 `optimize` 和 `optimization_level` 接口。`optimize=False` 等价于 `optimization_level=0`；O1 是默认，O2 仅在固定宽度回绕 Cell 下优化 `[-]` 和 `[+]`。两者在启用 `max_steps` 或有限 Tape 时都会禁用可能跳过原始步数或中间边界检查的合并。

```python
from brainfuck import compile_to_python

generated = compile_to_python(sourcecode, mode="strict", optimization_level=2)
```

## 语义说明

- 非 BF 指令字符会被忽略，因此源码可以包含空白和注释。
- `.` 的默认 `unicode` 输出模式将当前 Cell 解释为 Unicode 码点；无效码点会引发 `ValueError`。`byte` 模式输出 Cell 的低 8 位。
- `,` 的默认 EOF 行为是写入 `0`；可通过 `eof_mode="unchanged"` 保持原值，或通过 `eof_mode="error"` 抛出异常。
- `[` 在当前 Cell 为 `0` 时跳到匹配的 `]` 之后；`]` 在当前 Cell 非 `0` 时跳回匹配的 `[` 之后。

完整的模式、参数、逐指令行为、异常及步数定义见 [SEMANTICS.md](SEMANTICS.md)。

## 调试与观测

`--trace` 将逐条执行信息写到标准错误，不污染 BF 程序的标准输出。`--trace-format jsonl` 输出稳定的 JSON Lines；`--trace-file` 将追踪写入单独文件。

```powershell
python brainfuck.py --trace code.b
python brainfuck.py --trace --trace-format jsonl --trace-file trace.jsonl code.b
python brainfuck.py --profile --dump-ir code.b
```

`--profile` 在标准错误输出 JSON，包含原始指令步数、运行时间、指针访问范围、非零 Cell 数和操作计数。`--dump-ir` 显示内部操作、合并结果、跳转目标与源代码位置。启用 `--trace` 或 `--profile` 时，移动和增减不会合并，从而保留准确的逐条观测结果。

标准兼容模式 (`standard`、`standard-one-way`、`strict`) 的 CLI 使用原始字节流进行 I/O。模块 API 的 `interpret_bytes()` 提供相同的二进制语义；`interpret()` 的文本输入在 byte 输出模式中仅接受 ASCII 字符。

## 可选扩展

默认只有 8 条 BF 指令生效，`#` 和 `/* ... */` 不会改变现有程序行为。可显式启用两项非标准扩展：

```powershell
python brainfuck.py -m strict --comment-style block --debug-command qdb code.b
```

- `comment_style="block"` 移除非嵌套的 `/* ... */` 块，块内的 BF 指令不会执行。未闭合块会报出原始行列位置。
- `debug_command="qdb"` 将 `#` 识别为 Daniel B. Cristofani `qdb.c` 调试指令：输出前 64 个 Cell 的 signed 8-bit 视图及指针 `^`。该扩展要求 8-bit 回绕 Cell，并写到 BF 程序的标准输出。

## 编译为 Python

`compile_to_python(sourcecode, optimize=True, optimization_level=None)` 返回独立、仅依赖 Python 标准库的 Python 程序文本。生成脚本嵌入 BF 源码、选定配置和编译后的 `OPERATIONS` IR。O0 为每条原始指令生成一项，O1 合并连续操作并保留原始步数，O2 在安全条件下生成 `clear` 操作。生成脚本不提供解释器运行期的 `trace` 或 `profile` 回调。

命令行使用 `--compile-python [OUTPUT] code.b`。省略 `OUTPUT` 时生成代码写到标准输出；提供目标时写入该文件：

```powershell
python brainfuck.py --compile-python code.b > program.py
python brainfuck.py --compile-python program.py code.b
python brainfuck.py --compile-python code.b | python
```

执行 BF 时，程序结果始终写到标准输出。需要保存结果时使用 shell 重定向，例如 `python brainfuck.py code.b > result.bin`。

## 测试

```powershell
python -m unittest -v
```

测试覆盖导入调用、命令行执行、CLI 惰性输入、标准模式、双向和受限 Tape、位宽回绕、EOF、循环、输入、括号错误和步数限制。固定种子的随机差分测试将 O0/O1/O2 与独立逐条 8-bit 参考机比较；`tests/external/` 还包含带来源说明的 Brainfuck.org 回归样本。
