---
name: tdd-guard
disable-model-invocation: false
description: "测试先行：对每个可观察行为执行先失败、最小通过的短循环。用户要求 TDD、先写测试，或当前任务已启用测试先行时使用。"
metadata:
  category: engineering
  tags: [testing, tdd, quality, test-driven]
  dependencies: []
  requires_context: [project]
  hooks:
    pre: []
    post: []
  memory_artifacts: []
  harness:
    requires_tdd: true
  outputs:
    type: progress
---

# 测试先行守护

明确启用 TDD 时生效：每个可观察行为都先看到一个因缺少该行为而失败的测试，再写生产代码。授权按 `.ai-configs/conventions.md`〈授权、实现判断与验证〉。

## 循环

一次只做一个最小可观察行为：

1. **红**：写一个测试，名字说明实际行为。运行它，确认它失败，而且失败原因是目标行为还不存在。
2. **绿**：只写让这个测试通过的代码，立刻用同一条命令再跑一次。
3. **下一个**：再加一个结果或边界，回到第 1 步。

测试一写完就通过，说明它没覆盖尚未实现的行为：先改测试，再进入实现。

重构不在这个循环里。行为都通过之后，结构上的改进放到审查阶段做，改完跑一遍相关测试。

## 写什么样的测试

- 从公共接口测行为，测试在重构后依然成立；私有方法和内部协作者不直接测。不知道该从哪个接口进入，或只能绕过接口才测得到时，读 skill 安装目录里的 `create-plan/references/module-design.md`。
- 外部依赖用最小的 fake、stub 或 mock 隔离，生产逻辑留在生产代码里。
- 选反馈最快的最低层测试；只有跨组件的行为才上集成或端到端测试。
- 修 bug 先写一个能稳定复现原问题的测试。
- 期望值要有独立来源：规格、手算的例子、已验证的参考实现或业务不变量。照着生产算法重算一遍期望值，两边会共享同一个缺陷；用被测结果自己生成期望值，什么也证明不了。
- 断言涉及业务规则、状态、权限或公共接口的名称，含义有冲突或含糊时，调用 Skill 工具（参数为 `domain-terms`），把正常和边界含义写成有依据的断言。还没确认的含义不能当作预期。

## 偏离信号

出现下面任一情况，退回当前这一个行为，修正测试或实现后再继续：

- 生产代码先写完了才补测试。
- 一个循环里加了多个行为。
- 为了通过放宽了断言。
- 测试失败的原因和目标行为无关。

## 输出

每个循环一条，失败和通过用同一条命令：

```text
当前行为：过期合同不进入待续签列表
失败证据：pytest tests/renewal/test_list.py::test_expired_excluded -q
         → 1 failed，AssertionError: 期望 0 条，实际 1 条
通过证据：同一命令 → 1 passed
```

失败证据里的报错必须由「目标行为缺失」造成。报 `ImportError` 或 `fixture not found`，说明测试还没跑到目标行为，不算有效的失败测试。
