# 教师考编信息雷达｜高可靠自动搜集版

这版只保留一条自动化链路：

**GitHub 定时采集 → 写入 JSON → 网页直接读取 GitHub 最新数据（失败则回退 EdgeOne 本地备份）**

不使用 EdgeOne Cloud Functions，不会再出现 `/api/... 404`、预览 token、Blob 等问题。

## 自动频率
- 快速巡检：约每 3 小时一次，检查 87 个官方入口。
- 历史深度回溯：每天一次。
- 第一次上传本版本到 `main` 后会自动触发首轮采集，不要求你去点 Actions 的 Run workflow。

## 只需确认一次的 GitHub 设置
仓库 `Settings → Actions → General`：
- Actions permissions：允许 Actions 运行。
- Workflow permissions：建议 Read and write permissions。

之后正常情况下不用再操作。

## 网站
EdgeOne 保持：根目录 `./`，输出目录 `docs`。网页会优先从 GitHub 仓库读取最新 JSON，所以即使 EdgeOne 对数据 commit 的重新部署稍有延迟，也能看到新数据。
