# Git 状态、三方内容与结束操作

## 先读实际状态

以下为只读检查，根据当前操作选择相关项；路径参数替换为实际冲突路径并正确引用。

```bash
git rev-parse --show-toplevel
git status
git ls-files -u
git diff --cached
git diff
git log --oneline --decorate -n 12
```

用 `git rev-parse --git-path <名称>` 定位 `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REBASE_HEAD`、`rebase-merge`、`rebase-apply` 或 `sequencer` 的实际位置，读取与当前状态相符的内容；不要假定 `.git` 一定是目录。操作引用不是都存在，不把缺少无关引用当作错误。当前操作和用户描述不同，先说明差异。

## 索引角色随操作变化

| 操作 | stage 1 基线 | stage 2 / ours | stage 3 / theirs |
|---|---|---|---|
| merge | 合并使用的共同基线 | 当前 HEAD 一侧 | 正在并入的一侧 |
| rebase | 当前重放所用的三方基线，普通提交通常为其父提交版本 | 目标基线加已重放结果 | 正在重放的提交版本 |
| cherry-pick | 被挑选提交的父版本；合并提交取指定主线父版本 | 当前目标 HEAD | 被挑选的提交版本 |

索引里的实际 blob 是判断内容的依据，操作说明只是定位提示。复杂合并可能使用合成基线；保留 merge 的 rebase、重命名及主线选择需要核对真实拓扑，不能套用普通提交的父版本。

```bash
git ls-files -u -- 'actual/path'
git show ':1:actual/path'
git show ':2:actual/path'
git show ':3:actual/path'
git log -p -- 'actual/path'
```

这些 `git show` 只针对索引实际存在的 stage。先保存三方依据，再暂存；暂存会把该路径的多阶段索引替换为解决后的版本。对含特殊字符的路径使用正确引用，自动化处理文件清单时使用 Git 的 NUL 分隔输出，不按空格拆路径。

## 冲突形态决定检查内容

- **修改冲突**：从完整行为判断如何组合，检查调用方和测试，不能只拼接两段文字。
- **修改/删除、重命名冲突**：确认删除或移动的目的、替代入口及剩余引用；恢复旧路径或保留重复路径都是行为决定。
- **二进制、生成文件、依赖锁文件**：二进制不能按文本拼接；生成物按项目现有生成规则处理，先解决其事实源，再验证输出。没有可信规则时保留待裁决，不猜取哪一侧。

### 示例：同一条件中保留两个独立目标

基线代码只允许 `active`。目标分支的提交明确要求允许 `trial`，被合入提交明确要求任何状态都拒绝 `suspended`。双方都改了同一条判断。

先读各提交说明和对应测试，再组合为“状态属于 active 或 trial，且 suspended 为假”。验证 active、trial 都可通过，二者暂停后都拒绝，其他状态仍拒绝。只选择一侧会丢掉另一项要求；仅移除标记却保留两个互相遮蔽的 return 也不能证明合并正确。

## 暂存与继续

已有授权覆盖暂存时，仅对已确认属于本次解决的完整路径执行 `git add -- <path>`；已确认应删除时使用 `git rm -- <path>`。这两个操作会影响整路径，同文件含无关内容时不得直接执行。需要把路径当作字面值时使用 Git 的 `--literal-pathspecs`。

继续前检查 `git ls-files -u` 是否为空，核对全部暂存内容和原有无关改动。无关 staged 内容混入时，当前索引还不能用于提交。已经授权完成操作且没有此类阻塞时：

| 实际操作 | 继续入口 | 中止入口（已有授权且已核对未保存内容） |
|---|---|---|
| merge | `git merge --continue`，或项目约定的 merge commit 入口 | `git merge --abort` |
| rebase | `git rebase --continue` | `git rebase --abort` |
| cherry-pick | `git cherry-pick --continue` | `git cherry-pick --abort` |

continue 可能创建提交或进入下一处冲突；每次返回后都查看真实状态。空提交、失败的 hook、丢失变更或待裁决行为需要分别处理，不能自动跳过提交或禁用检查。中止也可能无法重建操作前的脏内容，不能代替备份或被当作清理手段。

## 来源

- [Matt Pocock 的 resolving-merge-conflicts](https://github.com/mattpocock/skills/blob/c55ee46073ed923f86ce59a5eb3b6d895095d1b7/skills/engineering/resolving-merge-conflicts/SKILL.md)，固定提交 `c55ee46073ed923f86ce59a5eb3b6d895095d1b7`。本仓独立改写，采用读历史与保留意图的思路，按当前授权和工作区范围决定是否暂存、继续、提交或中止。
- [Git checkout 官方文档](https://git-scm.com/docs/git-checkout)：索引 stage 2 / 3 与 rebase 下 ours / theirs 的角色。
- [Git cherry-pick 官方文档](https://git-scm.com/docs/git-cherry-pick)：冲突后的索引、主线选择和 continue / abort 行为。
