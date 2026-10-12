# Tool Server 子树仓库操作

> 类型:流程规范。
> 性质:现行文档。
> 归属:文档自身。
> 适用版本:平台 `4.0.0+`。

## 1. 两个仓库的关系

继续在 AAgent 的 `tool_server/` 中开发和提交，通过 Git subtree 将该目录发布到独立的 GitHub 仓库。

| 项目 | AAgent 仓库 | Tool Server 仓库 |
| --- | --- | --- |
| 远端名 | `origin` | `tool-server` |
| 地址 | `https://github.com/g-Ironfox/AAgent.git` | `https://github.com/g-Ironfox/AAgent-tool-server.git` |
| 服务文件位置 | `tool_server/` | 仓库根目录 |
| 开发与提交 | 在这里完成 | 接收子树发布 |
| 更新命令 | `git push origin main` | `git subtree push --prefix=tool_server tool-server main` |

下文使用 Windows PowerShell，命令由操作者自行执行，每一步成功后再继续。示例地址是计划使用的地址，不表示远端已经创建。

普通 `git push` 不会同时更新两个仓库。在 `main` 的上游仍为 `origin/main`，且没有额外覆盖推送配置的情况下，添加 `tool-server` remote 不改变默认推送目标。

`git subtree split` 从已提交的历史派生出一条只包含 `tool_server/` 的提交历史，并把目录内容提升到仓库根。它不会切换当前分支，也不会修改工作区文件或父仓库原有提交。派生提交的哈希通常不同于父仓库提交，但文件内容相同。

派生历史按路径筛选提交：不触及 `tool_server/` 的提交不会进入服务仓库，只改 `agent/`、`manager_webui/`、根目录文件等改动的提交和空提交都不会出现在那里。跨服务提交只保留该目录的改动，提交信息仍沿用原文。

此流程只发布 `tool_server/`。父仓库根的 README、LICENSE、部署配置、版本清单和 `docs/` 不会一起发布；服务可独立运行所需的说明和配置需要另行准备。

## 2. 首次发布

### 2.1 创建空远端

在 GitHub 创建 `g-Ironfox/AAgent-tool-server`，选择 Public，不初始化 README、`.gitignore` 或 LICENSE。

公开前检查要发布的文件和历史中是否含凭据或私人数据。子树会保留该目录的历史，不只发布最新文件。

### 2.2 检查并提交服务内容

```powershell
cd D:\AAgent
git status --short
git ls-files tool_server
git remote -v
```

子树只包含当前 `HEAD` 中已提交的内容。未跟踪、未暂存、已暂存但未提交的文件都不会进入发布。

例如，要发布 `tool_server/VERSION`，必须先把它纳入提交。不要为了发布服务而顺带提交其他未完成的修改。

### 2.3 添加远端

仅在 `git remote -v` 中还没有 `tool-server` 时执行：

```powershell
git remote add tool-server https://github.com/g-Ironfox/AAgent-tool-server.git
```

这会修改本地 `.git/config`，不产生提交。若远端名已存在，先核对地址，不重复添加。

### 2.4 派生并推送

下面的 `ts-publish` 是临时本地分支。先确认没有同名分支；若存在，先检查其用途，或换一个临时分支名。

```powershell
git branch --list ts-publish
git subtree split --prefix=tool_server -b ts-publish
git log --oneline ts-publish
git ls-tree -r --name-only ts-publish
git push tool-server ts-publish:main
```

推送的是临时子树分支到远端 `main`。不要用 `git push tool-server main` 代替，它会尝试推送整个 AAgent 主分支。

确认推送成功后可以清理临时分支：

```powershell
git branch -D ts-publish
```

此前操作曾创建过 `ts-split-test`。如果它仍存在且不再需要，可以单独删除；删除它不会删除父仓库代码或远端分支。

## 3. 日常更新

服务修改仍然是在 AAgent 中完成的普通提交：`tool_server/` 没有独立仓库，验证通过后先提交，再分别更新两个仓库。

```powershell
cd D:\AAgent
git status --short
git add tool_server/
git commit -m "..."
git push origin main
git subtree push --prefix=tool_server tool-server main
```

不要进入 `tool_server/` 单独提交，该目录与 `agent/`、`manager_webui/` 一样属于父仓库。一次提交可以同时包含平台改动和服务改动，不需要刻意拆分；`split` 只提取触及 `tool_server/` 的部分，提交信息沿用原文。

提交是发布的前提。日常执行的 `git subtree push --prefix=tool_server tool-server main` 会先执行子树拆分（`split`），再把派生的历史推送到服务仓库；不是把 AAgent 的 `main` 原样推过去。未来只改其他目录的提交不会出现在派生历史中，因此即使执行子树推送，也不会进入服务仓库；筛选由内部的 `split` 完成，发布由 `push` 完成。

子树只包含当前 `HEAD` 中已提交的内容，未跟踪、未暂存、已暂存未提交的改动都不会进入服务仓库。此前多个涉及 `tool_server/` 却尚未同步的提交，会在下一次子树推送时一起发布，不只推最新那一个。

两次推送相互独立，一次成功不代表另一次也成功。只推 `origin` 时，Tool Server 仓库不会更新。

在历史未改写、子树参数一致、服务远端没有独立新增提交的情况下，后续子树推送通常是 fast-forward，不需要强推。

无需保留临时分支，也无需在 `tool_server/` 中执行 `git init`。Git subtree 使用父仓库的提交历史。

## 4. 推送前预览和推送后核对

服务远端已有 `main` 时，可先派生到临时分支查看增量：

```powershell
git fetch tool-server
git subtree split --prefix=tool_server -b ts-publish
git log --oneline tool-server/main..ts-publish
git diff --stat tool-server/main ts-publish
git diff tool-server/main ts-publish
```

确认后推送，并重新获取远端结果：

```powershell
git push tool-server ts-publish:main
git fetch tool-server
git rev-parse ts-publish
git rev-parse tool-server/main
git rev-parse 'ts-publish^{tree}'
git rev-parse HEAD:tool_server
git status --short
```

前两个提交哈希应相同；后两个树哈希应相同，表示服务仓库根内容与父仓库已提交的服务目录一致。工作区原有未提交修改仍会出现在 `status` 中，推送不会清除它们。

核对完成后执行 `git branch -D ts-publish`。不准备推送时也可删除临时分支，结束预览。

## 5. 对齐版本与发布标签

子树发布不改变现有[版本与归属规范](版本与归属规范.md)。服务版本信息仍先在 AAgent 中按规范更新和提交，然后随服务目录发布。分仓库本身不会生成独立的版本序列，也不会自动完成跨仓库版本同步。

平台标签与服务标签是两套互相独立的标签：前者属于 AAgent 仓库、指向整个平台提交，后者属于 Tool Server 仓库、指向只含 `tool_server/` 的服务提交。两者分别创建、分别推送，命名和推送对象都不同。

### 5.1 平台标签（AAgent 仓库）

平台标签仍按[版本与归属规范](版本与归属规范.md) §6 在 AAgent 中创建：`vMAJOR.MINOR.PATCH`、附注标签（`git tag -a`）、只打在 `main` 上、该提交测试全绿。它归属于 AAgent 仓库，由 `git push origin` 发布，与 Tool Server 仓库无关。例如发布 `4.0.1` 时：

```powershell
cd D:\AAgent
git checkout main
git status --short
git log --oneline -5
git tag -a v4.0.1 -m "v4.0.1 — 一句话概括" -m "正文写本版发布记录：与上一版的不同 + 携带的 event / workflow 协议版本"
git show v4.0.1
git push origin v4.0.1
```

示例版本必须替换为实际版本。`git push origin main` 不会推送标签，标签要单独推送；`git push origin main --follow-tags` 只会带上从 `main` 可达的附注标签。不要用 `git push --tags`，它会把本地所有标签（含 legacy 锚点 `v2` / `v3` 与本地服务标签 `tool-server-v*`）一起推到 `origin`。

平台标签指向的提交包含 `agent/`、`manager_webui/`、根目录等全部内容，服务仓库没有这些路径，因此**不能**把它直接推到 `tool-server` 当作服务发布标签。`git subtree push` 只同步分支，也不会自动发布标签。

### 5.2 服务标签（Tool Server 仓库）

服务标签从对应的平台标签派生：先用 `git subtree split` 从平台标签拆出只含 `tool_server/` 的服务提交，再给这条派生提交打标签，然后推送到 `tool-server` 远端。例如平台发布为 `v4.0.1`，且按版本规范本次服务版本也为 `4.0.1` 时：

```powershell
git subtree split --prefix=tool_server v4.0.1 -b ts-release
git ls-tree -r --name-only ts-release
git show ts-release:version.json
git tag -a tool-server-v4.0.1 ts-release -m "Tool Server 4.0.1"
git push tool-server refs/tags/tool-server-v4.0.1:refs/tags/v4.0.1
git branch -D ts-release
```

示例版本必须替换为实际存在的平台标签和服务版本。执行前确保临时分支、标签名未被占用，并已完成发布要求的容器测试。先发布相应服务代码，再发布标签；核对远端 `main` 已包含该发布提交。

本地标签名为 `tool-server-v4.0.1`，服务远端标签名为 `v4.0.1`：本地用带前缀的名字，避免与 AAgent 仓库中同名的平台标签冲突；远端按平台同一版本号命名。未参与本次平台迭代的服务按规范保留原服务版本，不必为每次平台发布重复打标签。

不要对服务远端执行 `git push --tags`、`git push --all` 或 `git push --mirror`，这些命令可能把平台标签或其他分支一起发布过去。

## 6. 推送被拒时

先停止推送并查看差异，不直接强推：

```powershell
git fetch tool-server
git subtree split --prefix=tool_server -b ts-publish
git log --oneline --left-right tool-server/main...ts-publish
git diff --stat tool-server/main ts-publish
```

常见原因包括：服务远端直接提交了修改、父仓库改写了已发布历史、改动了目录路径或 split 参数。并非每次 rebase/amend 都必然影响子树历史，是否分叉以上述检查为准。

本流程约定在父仓库开发；如果在 GitHub 上直接编辑服务文件，那些提交不会自动回到 AAgent。需要先决定如何保留并导入这些改动，再继续同步。

如果已确认要用当前父仓库服务内容覆盖远端历史，先保存远端当前提交的备份引用，再使用带期望哈希的 lease。以下步骤会改写远端 `main`，只在明确决定覆盖后执行：

```powershell
$expectedHead = git rev-parse tool-server/main
$backupBranch = 'tool-server-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
git branch $backupBranch $expectedHead
git push "--force-with-lease=refs/heads/main:$expectedHead" tool-server ts-publish:main
```

如果期间远端发生变化，lease 会拒绝覆盖。重新获取并检查变化，不改用无条件 `--force`。备份分支留在本地供追溯，不自动删除。

## 7. 更换电脑或工作副本

`tool-server` remote 是本地配置，clone AAgent 不会自动带上它。在新工作副本中重新添加该 remote，即可继续子树发布，无需重新初始化服务目录。

独立 clone Tool Server 仓库可以获得服务文件，用于查看、构建和部署；若要按本流程继续发布，仍在 AAgent 工作副本中开发和提交。