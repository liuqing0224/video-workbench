# Menza 文章转视频：案例设计回归

日期：2026-09-17。项目 378f051cc1d9483da9cb5987fe6f5e8f。

## 偏差与修正

第一版绕过案例选择与镜头映射，直接使用统一卡片版式。技术验收通过不等于完成案例驱动设计。用户指出后保留第一版，制作 v2。

v2 主参考 3Blue1Brown 的对象拆解与关系逐步显现，辅助参考 Linear Loops 的一致节点/路径语言。8镜分别实现包装对照、记录关联、假设分离、数据线索、专业核查、证据分层、迁移自检、答案收束。没有借用参考素材或声称复刻其音轨。

制作方案：recipes/menza-customer-insights/menza-v2-video-recipe.json。具体镜头映射存放在方案的 reference_plan，以及运行副本 documents/REFERENCES.md。

## 实际执行与验证

通过内置浏览器上传方案并启动 article 任务；运行 f291dff4cadb4eaead655afa1275838d。

成片：workspace/projects/378f051cc1d9483da9cb5987fe6f5e8f/runs/f291dff4cadb4eaead655afa1275838d/work/exports/article-video.mp4。

SHA-256：1b0bdbafde5483cc2d3b77d41581c7138766a5858c54c51e87db41ea2f325f0f。

1920×1080、30fps、79.833333秒、H.264/AAC、48kHz双声道；综合响度-18.01 LUFS、峰值-2.00 dBTP。最终文件的自动技术检查通过，报告在运行副本 qa/final/report.json。

关键片段检查及全片采样图位于 workspace/service-tests/menza-case-v2/。检查报告含时间边界重叠提示（相邻背景覆盖）、8镜同轨维护性警告，无运行或动效错误。内置浏览器实际播放至20秒并定位79.7秒，画面正确，末尾保持收束画面。

测试：原27项测试通过；新增案例方案校验测试后，文章模块4项通过。前端构建通过。项目 Skill 增加案例映射要求；声音缓存增加原请求文本与配置比对，避免文案修改复用旧声。

## 状态边界

平台状态 awaiting_review。未代替用户确认声音或完整预览，学习效果未验证；未发布。小样采样时间来自制作前时间表，最终时间以运行副本为准。
