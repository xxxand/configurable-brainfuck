# Unlimited Brainfuck Interpreter

一个单文件、无人工边界的 Brainfuck (BF) 解释器，使用 Python 标准库实现。

## 特性

- Tape 使用稀疏字典，以带符号整数作为位置索引。指针可无限向左或向右移动，未使用的 Cell 读取为 `0`。
- Cell 使用 Python `int`，`+` 和 `-` 不进行 8-bit、16-bit 或其他范围截断。
- 支持完整 BF 指令集：`>`、`<`、`+`、`-`、`.`、`,`、`[`、`]`。
- 在执行前检查括号匹配；多余 `[` 或 `]` 会引发 `SyntaxError`。
- 连续的指针移动和 Cell 增减会合并执行，减少解释开销；不会把 `[-]` 优化为清零，因为负数 Cell 下该循环并不一定终止。
- 除实际内存、运行时间和 Python 整数可用资源外，不设置 Tape、Cell 或指针的人为上限。

## 环境

需要 Python 3.10 或更新版本，不需要安装第三方依赖。

## 命令行

在项目目录执行：

```powershell
python brainfuck.py code.bf
```

`code.bf` 是 Hello World 示例，输出：

```text
Hello World!
```

当 BF 程序执行到 `,` 时，解释器才从标准输入读取一个字符。没有 `,` 的程序不会等待标准输入。例如：

```powershell
python brainfuck.py input.bf
```

若 `input.bf` 内容为 `,.`，输入一个字符并按 Enter 后，程序会输出该字符。输入结束后继续执行 `,` 时会向当前 Cell 写入 `0`。

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

## 语义说明

- 非 BF 指令字符会被忽略，因此源码可以包含空白和注释。
- `.` 将当前 Cell 解释为 Unicode 码点并追加到输出。如果值小于 `0` 或大于 `0x10FFFF`，Python 无法将其转换为字符，解释器会引发 `ValueError`。这限制的是文本输出表示，不会限制 Cell 本身的整数范围。
- `,` 在没有更多可用输入时写入 `0`。
- `[` 在当前 Cell 为 `0` 时跳到匹配的 `]` 之后；`]` 在当前 Cell 非 `0` 时跳回匹配的 `[` 之后。

## 测试

```powershell
python -m unittest -v
```

测试覆盖导入调用、命令行执行、CLI 惰性输入、双向 Tape、超过 8-bit 的 Cell、循环、输入和括号错误。
