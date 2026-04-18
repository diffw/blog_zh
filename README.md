# diff-blog-zh

这个目录是 Hugo blog 项目的根目录。

## 目录角色

- Obsidian 写作源目录:
  `/Users/diffwang/Library/Mobile Documents/iCloud~md~obsidian/Documents/notes/diff-blog`
- Hugo 项目目录:
  `/Users/diffwang/NWA/diff-blog-zh`

约定:

- `diff-blog` 是唯一内容源。
- 日常创建、编辑、修改文章都在 Obsidian 的 `diff-blog` 目录里完成。
- Hugo 目录中的 `content/posts` 是同步结果，不手工编辑，避免双向漂移。
- `template.md` 只用于 Obsidian 写作模板，不进入 Hugo 发布目录。

## 发布规则

- 只处理 `diff-blog` 目录中的 `.md` 文件。
- 忽略 `template.md`。
- 只有 front matter 中 `draft: false` 的文章才允许发布。
- `draft: true` 的文章不发布。
- 缺少有效 front matter、缺少 `title`、缺少 `date` 或缺少 `draft` 的文章不会发布。
- 已发布文章后续修改时，仍然通过同一套自动发布流程同步到 Hugo blog。

## Debounce 自动发布

当前采用“自动 debounce 后发布”的设计。

规则如下:

1. 监听 `diff-blog` 目录中的文章变化。
2. 当文章发生新增、修改、删除或 front matter 变化时，不立即发布。
3. 每次变化都会重置计时器。
4. 如果最后一次变化之后连续一段时间没有新的变更，再自动执行一次发布。

### Debounce 时间

测试阶段:

- debounce 时间设置为 `3 分钟`

也就是:

- 文章有改动后，如果连续 `3 分钟` 没有新的变化，就自动触发一次同步和 push。

正式阶段计划:

- 将 debounce 时间调整为 `10 分钟`

## 自动发布动作

当 debounce 到期后，自动发布流程会执行这些动作:

1. 校验文章 front matter。
2. 筛选出 `draft: false` 的文章。
3. 将可发布文章同步到 Hugo 项目内容目录 `content/posts/`。
4. 将不再发布的文章从 Hugo 发布目录中移除。
5. 只对 `content/posts/` 执行 `git add`、`git commit`、`git push`。
6. 由 GitHub Actions 构建并发布 Hugo 站点。

注意:

- 自动发布脚本只提交 `content/posts/`，不会顺带提交这个仓库中的其他开发文件改动。
- 如果仓库里还有其他未提交的代码修改，它们会保留在工作区，不会被自动发布流程一起带上去。

## 安装依赖

```bash
cd /Users/diffwang/NWA/diff-blog-zh
python3 -m pip install --user -r requirements.txt
```

## 手动执行一次同步发布

在启用 watcher 之前，可以先手动跑一次，把 Obsidian 中可发布的文章同步进 Hugo:

```bash
cd /Users/diffwang/NWA/diff-blog-zh
python3 scripts/publish_from_obsidian.py
```

只预览将要发生的变化，不真正写入或提交:

```bash
cd /Users/diffwang/NWA/diff-blog-zh
python3 scripts/publish_from_obsidian.py --dry-run --no-push
```

## 启动本地 watcher

手动启动 3 分钟 debounce 的自动发布 watcher:

```bash
cd /Users/diffwang/NWA/diff-blog-zh
bash ./scripts/start_autopublish.sh --debounce-seconds 180
```

如果测试完成后要改成 10 分钟:

```bash
cd /Users/diffwang/NWA/diff-blog-zh
bash ./scripts/start_autopublish.sh --debounce-seconds 600
```

## launchd 自启动

已提供 launchd 配置模板:

`ops/launchd/com.diffwang.diff-blog-zh.autopublish.plist`

安装方式:

```bash
mkdir -p ~/Library/LaunchAgents
cp ops/launchd/com.diffwang.diff-blog-zh.autopublish.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.diffwang.diff-blog-zh.autopublish.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.diffwang.diff-blog-zh.autopublish.plist
```

停止方式:

```bash
launchctl unload ~/Library/LaunchAgents/com.diffwang.diff-blog-zh.autopublish.plist
```

## 主要脚本

- `scripts/publish_from_obsidian.py`
  单次执行同步、提交和推送
- `scripts/watch_diff_blog.py`
  监听 `diff-blog` 目录，并在 debounce 到期后自动发布
- `scripts/start_autopublish.sh`
  便于手工或 launchd 启动 watcher 的包装脚本

## 测试

运行单元测试:

```bash
cd /Users/diffwang/NWA/diff-blog-zh
python3 -m unittest discover -s tests
```
