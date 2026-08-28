# Configurable Brainfuck

中文 | [English](README.en.md)

使用 Python 标准库实现的可配置 Brainfuck 解释器、格式化器、Python 代码生成器和本地 Web 工作台。默认是双向无限 Tape 与任意精度 Cell，也提供经典 8-bit 兼容模式。

## 特性

- 支持完整 BF 指令集：`>`、`<`、`+`、`-`、`.`、`,`、`[`、`]`。
- 提供 `unlimited`、`standard`、`standard-one-way`、`strict` 运行预设。
- 支持可配置 Cell 位宽、Tape 边界、EOF、输出模式、步数限制和优化级别。
- 提供 trace、profile、IR 输出、qdb `#` 调试、块注释和 Python 代码生成。
- 包含命令行、模块 API、格式化器和本地浏览器工作台。

固定宽度 Cell 是模 `2^N` 的位模式；`.`, qdb `#` 和调试数值格式只决定 I/O 或展示方式，不改变 Cell 的执行语义。完整定义见 [SEMANTICS.md](SEMANTICS.md)。

## 环境

需要 Python 3.10 或更新版本，不需要第三方依赖。

## 快速开始

运行示例：

```powershell
python brainfuck.py code.b
```

作为模块调用：

```python
from brainfuck import interpret

print(interpret("++++++++++[>+++++++>++++++++++>+++>+<<<<-]>++.>+.+++++++..+++.>++.<<+++++++++++++++.>.+++.------.--------.>+.>."), end="")
```

标准 8-bit 模式：

```powershell
python brainfuck.py --mode strict code.b
```

## 配置

`unlimited` 使用任意精度 Cell 和双向无限 Tape；`standard` 使用 8-bit Cell；`standard-one-way` 限制指针不得小于 `0`；`strict` 使用 30,000 个单向 8-bit Cell。完整的参数、Cell/Tape 语义、EOF、步数与 I/O 规则见 [SEMANTICS.md](SEMANTICS.md)。

```python
from brainfuck import interpret

interpret(sourcecode, mode="strict", max_steps=100_000)
```

## 工具

格式化 BF 源码：

```powershell
python bf_formatter.py --in-place code.b
```

生成独立 Python 脚本：

```powershell
python brainfuck.py --compile-python program.py code.b
```

启动本地 Web 工作台：

```powershell
python bf_web.py
```

然后访问 `http://127.0.0.1:8000`。工作台通过本机 Python API 执行、格式化和生成代码，并在浏览器 LocalStorage 中保存源码、输入和运行配置。

## 调试与扩展

```powershell
python brainfuck.py --trace --profile --dump-ir code.b
python brainfuck.py -m strict --comment-style block --debug-command qdb code.b
```

`--trace-format jsonl` 提供机器可读追踪。`comment_style="block"` 启用 `/* ... */`，`debug_command="qdb"` 启用 `#` 调试指令。完整规则见 [SEMANTICS.md](SEMANTICS.md)。

## 测试

```powershell
python -m unittest -v
```

测试包含语义矩阵、随机差分测试和 Brainfuck.org 外部回归样本。

## 参考资料

- [Brainfuck.org](https://brainfuck.org/)
- [Wikipedia: Brainfuck](https://en.wikipedia.org/wiki/Brainfuck)
