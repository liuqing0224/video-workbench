---
name: video-orchestrator
description: 创建、继续或修改本平台视频项目时，按公共八阶段组织输入、产物与修改影响。
---

# video-orchestrator

读取运行请求、项目 AGENTS.md、documents/BRIEF.md 及对应分支 Skill。只处理指定阶段。公共方法见 视频制作总工作流.md；字段见 文件交接约定.md（均在平台源码根目录）。先核对已有文件和缺失依赖，不重问已确认事项。声明实际产物与阻塞；不得运行下一阶段或写入平台确认。修改后列出受影响文件。画面制作读取已安装 hyperframes Skill；与用户范围冲突时遵循用户范围。

产物只写入任务允许目录。最终返回平台提供的 JSON Schema，列出实际产物、修改摘要、待确认事项与阻塞原因。
