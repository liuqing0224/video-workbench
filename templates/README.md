# 可复用模板组使用说明

本目录是一组统一模板，公共部分只维护一份，营销与教学目录提供补充项。

先阅读 [总工作流](../视频制作总工作流.md)。复制 common 中的文件到新的视频工程根目录，再将 marketing 或 teaching 的内容合并进同一根目录。源模板保持不动。

1. 填 BRIEF 与 STATUS，营销填卖点证据，教学先填 LESSON-PLAN 的选题与标题承诺、自检和答案，再填 PUBLISH-PACK；真实反馈记入 LEARNING-FEEDBACK。
2. 按阶段填写脚本、分镜、设计和 JSON；具体交接见 [文件交接约定](../文件交接约定.md)。
3. 当前不适用的文件可暂不复制：无旁白不需要 voice-config；没有实验不需要 EXPERIMENTS。不要删去公共 QA 中的适用性记录。
4. 模板中 null 表示尚未知，不能按零值或已完成解释。带示例 ID 的记录需按实际内容替换/扩展。
5. 实际工程再建立 assets、audio、hyperframes、qa、exports 等目录；此包没有可运行的视频工程或模型服务。

[营销填写示例](../examples/marketing/README.md) · [教学填写示例](../examples/teaching/README.md)。示例是虚构/演示材料，不是通过验收的成片。
