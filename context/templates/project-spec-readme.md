# 项目 Spec

`index.json` 只绑定“现有规范事实源”和“受它约束的代码路径”，不复制规范正文。

每条记录包含：

- `id`：稳定、唯一的小写标识，只使用字母、数字和连字符。
- `source`：项目根目录内现有规范文件的相对路径。
- `description`：修改目标路径前需要读取该规范的原因。
- `paths`：受规范约束的项目相对路径，支持 `*`、`**`、`?`。

示例：

```json
{
  "version": 1,
  "specs": [
    {
      "id": "api-contract",
      "source": "docs/api-contract.md",
      "description": "接口字段、错误码和兼容性约束",
      "paths": ["src/api/**", "tests/api/**"]
    }
  ]
}
```

登记后运行：

```bash
xman spec validate
xman spec match "src/api/example.py"
```
