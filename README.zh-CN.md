# catalog-regress 中文说明

比较更新前后的 gettext PO 文件，保护原来已可用于运行时的翻译。
能发现变成 fuzzy、译文清空、条目删除或废弃、复数译文不完整及复数源文本变化。
即使总翻译数量不变，旧条目的损失仍会被检测。

需要 Python 3.11+。按 [英文 README](README.md) 克隆仓库并建立、激活虚拟环境后：

```sh
python -m pip install .
catalog-regress examples/before.po examples/after.po --json
# 预期退出码 1：发现一条 fuzzy 回退。
catalog-regress examples/before.po examples/fixed.po --json
# 预期退出码 0。
```

默认不允许任何回退；退出码 0 表示符合明确的预算，1 表示超预算，2 表示输入错误。
`--allow-removed` 仅允许删除/废弃旧条目；`--max-regressions N` 设置预算。
条目按上下文及 msgid 精确匹配，不猜测源文本重命名。两份文件必须使用 UTF-8，
且语言与 nplurals 一致；不执行复数表达式。默认每个输入最多 16 MiB。

工具只读输入，报告不含源文本、译文或输入路径，但哈希与行号仍是元数据。
它不评价译文语义，不代替 `msgfmt --check`，也不验证全部 PO 规范。
仅依赖 MIT 许可的 polib，无运行时联网或遥测。

卸载：在专用虚拟环境运行 `python -m pip uninstall catalog-regress polib`，
或退出环境后删除该虚拟环境目录。完整边界、测试命令和安全报告方式见英文说明。
