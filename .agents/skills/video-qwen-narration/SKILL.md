---
name: video-qwen-narration
description: 准备本地 Qwen 分段旁白与发音修订，关联音频、字幕和统一时间，处理试听反馈。
---

# video-qwen-narration

显示文本和发音文本分开。读取 documents/voice-config.json，保存模型实际版本、音色、参数与 segment_id。单段文本不超过已验证接口上限500字。平台 Worker 执行合成；不要私自换模型或云服务。服务成功不是试听通过。独立转录后校正，不生成伪精确词级时间。无旁白跳过合成；有BGM仍做音频验收。没有正式声音与字幕校正证据不得锁定 timing。

产物只写入任务允许目录。最终返回平台提供的 JSON Schema，列出实际产物、修改摘要、待确认事项与阻塞原因。
