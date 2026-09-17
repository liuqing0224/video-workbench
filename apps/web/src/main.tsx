import { ProjectRequestGuard } from "./projectRequests";
import React, { useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  Clapperboard,
  Plus,
  ArrowUpRight,
  Play,
  Check,
  ChevronRight,
  FolderOpen,
  Settings,
  FileText,
  AudioLines,
  Package,
  LoaderCircle,
  RefreshCw,
  Upload,
  Save,
  Square,
  MessageSquare,
} from "lucide-react";
import "./style.css";
import { VideoPlayer } from "./VideoPlayer";
type Project = {
  id: string;
  name: string;
  branch: string;
  config: Record<string, any>;
  config_revision?: string;
  runs?: Run[];
  artifacts?: Artifact[];
  comments?: any[];
  automation_events?: {id: number; data: {stage: string; status: string; details: string}}[];
};
type Run = {
  id: string;
  stage: string;
  kind: string;
  status: string;
  stale: boolean;
  message: string;
  created: number;
};
type Artifact = { id: string; path: string; sha256: string; run_id: string | null; role?: string; available?: boolean; version?: string };
type Doc = { path: string; content: string; revision: string | null };
const stages = [
  "brief",
  "content",
  "storyboard",
  "sample",
  "timing",
  "preview",
  "render",
  "delivery",
];
const labels = [
  "目标与证据",
  "内容设计",
  "镜头设计",
  "关键小样",
  "素材与时间",
  "整片预览",
  "渲染验收",
  "交付复盘",
];
const states: Record<string, string> = {
  queued: "排队中",
  running: "制作中",
  succeeded: "已完成",
  awaiting_review: "待你确认",
  blocked: "需要处理",
  failed: "运行失败",
  cancelled: "已取消",
};
async function api(path: string, body?: unknown, method?: string) {
  const r = await fetch("/api" + path, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers:
      body instanceof FormData
        ? { "X-Video-Request": "workbench" }
        : {
            "Content-Type": "application/json",
            "X-Video-Request": "workbench",
          },
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok)
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
function App() {
  const [projects, setProjects] = useState<Project[]>([]),
    [project, setProject] = useState<Project | null>(null),
    [tab, setTab] = useState("work"),
    [stage, setStage] = useState("brief"),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [newOpen, setNewOpen] = useState(false),
    [name, setName] = useState(""),
    [branch, setBranch] = useState("marketing"),
    [audioMode, setAudioMode] = useState("qwen"),
    [orientation, setOrientation] = useState("horizontal"),
    [brief, setBrief] = useState(""),
    [instruction, setInstruction] = useState(""),
    [files, setFiles] = useState<any[]>([]),
    [doc, setDoc] = useState<Doc | null>(null),
    [dirty, setDirty] = useState(false),
    [logs, setLogs] = useState<Record<string, string>>({}),
    [services, setServices] = useState<Record<string, any>>({}),
    [qwenUrl, setQwenUrl] = useState("http://127.0.0.1:8001"),
    [speech, setSpeech] = useState(""),
    [segmentId, setSegmentId] = useState("SEG01"),
    [voiceStyle, setVoiceStyle] = useState("自然清晰，适合教学与产品解说"),
    [voice, setVoice] = useState("Serena"),
    [selected, setSelected] = useState(""),
    [note, setNote] = useState(""),
    [settings, setSettings] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const requests = useRef(new ProjectRequestGuard());
  const eventCursors = useRef<Record<string, string>>({});
  async function act(fn: () => Promise<any>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }
  async function refresh(pid = requests.current.projectId) {
    const accept = requests.current.begin(pid);
    const list = await api("/projects");
    if (!accept()) return;
    setProjects(list);
    if (pid) {
      const [p, nextFiles] = await Promise.all([
        api("/projects/" + pid), api(`/projects/${pid}/files`),
      ]);
      if (!accept()) return;
      setProject(p);
      setFiles(nextFiles);
    }
  }
  useEffect(() => {
    act(async () => {
      await api("/session");
      await refresh();
    });
  }, []);
  useEffect(() => {
    if (!project?.id) return;
    const pid = project.id;
    let closed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const es = new EventSource(`/api/projects/${pid}/events?after=${eventCursors.current[pid] || "0"}`);
    es.onmessage = (event) => {
      if (closed || requests.current.projectId !== pid) return;
      eventCursors.current[pid] = event.lastEventId;
      // Coalesce a replay batch into one refresh instead of one request per event.
      if (timer !== undefined) return;
      timer = setTimeout(() => {
        timer = undefined;
        if (!closed && requests.current.projectId === pid) refresh(pid).catch(() => {});
      }, 150);
    };
    return () => { closed = true; clearTimeout(timer); es.close(); };
  }, [project?.id]);
  const runs = project?.runs ?? [],
    active = runs.find((r) => ["queued", "running"].includes(r.status));
  const artifacts = project?.artifacts ?? [],
    media = artifacts.filter(a => a.available !== false)
      .sort((a, b) => Number(!!b.run_id) - Number(!!a.run_id))
      .filter((a, i, all) => all.findIndex((x) => x.sha256 === a.sha256) === i)
      .filter((a) => /\.(mp4|webm|wav|mp3|m4a|png|jpg)$/i.test(a.path));
  const current =
    media.find((a) => a.id === selected) ??
    media.find((a) => /\.(mp4|webm)$/.test(a.path)) ??
    media[0];
  const latest = runs.find((r) => r.stage === stage);
  const waiting = runs.find((r) => r.status === "awaiting_review" && !r.stale);
  async function start(
    kind = "agent",
    payload: Record<string, any> = { instruction },
    st = stage,
  ) {
    await api(`/projects/${project!.id}/runs`, {
      stage: st,
      kind,
      idempotency_key: crypto.randomUUID(),
      payload,
    });
    setInstruction("");
    await refresh();
  }
  async function pick(p: Project) {
    if (dirty && !confirm("当前文档有未保存内容，放弃修改？")) return;
    requests.current.select(p.id);
    setProject(p);
    setFiles([]);
    setDoc(null);
    setDirty(false);
    setSelected("");
    setTab("work");
    setStage("brief");
    await refresh(p.id);
  }
  async function loadDoc(path: string) {
    if (dirty && !confirm("放弃未保存的修改？")) return;
    setDoc(
      await api(
        `/projects/${project!.id}/document?path=${encodeURIComponent(path)}`,
      ),
    );
    setDirty(false);
  }
  function badge(r: Run) {
    return (
      <span className={"badge " + (r.stale ? "stale" : r.status)}>
        {r.stale ? "检查已失效" : states[r.status]}
      </span>
    );
  }
  return (
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="片场首页">
          <Clapperboard size={25} />
          <span>
            片场<small>视频制作工作台</small>
          </span>
        </a>
        <div className="side-heading">
          工作空间
          <button aria-label="新建项目" onClick={() => setNewOpen(true)}>
            <Plus size={17} />
          </button>
        </div>
        <nav>
          {projects.map((p) => (
            <button
              key={p.id}
              className={
                "project-link " + (p.id === project?.id ? "chosen" : "")
              }
              onClick={() => act(() => pick(p))}
            >
              <FolderOpen size={17} />
              <span>
                {p.name}
                <small>
                  {p.branch === "marketing" ? "营销视频" : "教学自媒体"}
                </small>
              </span>
            </button>
          ))}
        </nav>
        {!projects.length && (
          <p className="side-empty">
            从一个选题开始，
            <br />
            把每次修改留成版本。
          </p>
        )}
        <div className="side-bottom">
          <button
            onClick={() => {
              setTab("services");
              act(async () => setServices(await api("/services/probe", {})));
            }}
          >
            <Settings size={17} /> 服务设置
          </button>
          <span className="local">
            <i /> 本机工作空间
          </span>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumb">
            工作空间 <ChevronRight size={14} /> {project?.name ?? "所有项目"}
          </div>
          <button className="light" onClick={() => setNewOpen(true)}>
            <Plus size={16} /> 新建视频
          </button>
        </header>
        <div className="page">
          <div className="title-row">
            <div>
              <div className="eyebrow">VIDEO WORKBENCH</div>
              <h1>
                {tab === "services"
                  ? "制作服务"
                  : (project?.name ?? "把想法，做成下一条视频。")}
              </h1>
              <p className="subtitle">
                {tab === "services"
                  ? "查看本机工具与语音服务的真实连接状态。"
                  : project
                    ? "一个目标、一条时间线，每次交付都有据可查。"
                    : "营销与教学，共用一套可以修改、确认和交付的制作流程。"}
              </p>
            </div>
            {project && (
              <span className="type-label">
                {project.branch === "marketing" ? "营销视频" : "教学自媒体"}
              </span>
            )}
          </div>
          {error && (
            <div className="alert" role="alert">
              {error}
              <button onClick={() => setError("")}>关闭</button>
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              {notice}
            </div>
          )}
          {tab === "services" ? (
            <section className="panel services">
              <div className="section-title">
                <h2>工具连接</h2>
                <button
                  disabled={busy}
                  onClick={() =>
                    act(async () =>
                      setServices(await api("/services/probe", {})),
                    )
                  }
                >
                  <RefreshCw size={15} />
                  重新检测
                </button>
              </div>
              <div className="service-list">
                {Object.entries(services).map(([key, value]) => (
                  <div key={key}>
                    <strong>{key}</strong>
                    <span
                      className={
                        "badge " +
                        (value.status === "ready" ? "succeeded" : "blocked")
                      }
                    >
                      {value.status === "ready" ? "可连接" : "未就绪"}
                    </span>
                    <p>
                      {value.version ?? value.health?.model ?? value.message}
                    </p>
                    {value.health?.voice && (
                      <small>服务当前音色：{value.health.voice}</small>
                    )}
                  </div>
                ))}
              </div>
              <label>
                Qwen 本机地址
                <input
                  value={qwenUrl}
                  onChange={(e) => setQwenUrl(e.target.value)}
                />
              </label>
              <button
                className="primary"
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    await api("/services/qwen", { base_url: qwenUrl }, "PUT");
                    setNotice("服务地址已保存。");
                  })
                }
              >
                保存连接
              </button>
              <p className="hint">
                声音仍需试听。服务可连接不等于已通过成片验收。
              </p>
            </section>
          ) : !project ? (
            <>
              <div className="welcome">
                <div className="welcome-copy">
                  <span className="overline">从简报到成片</span>
                  <h2>
                    让创作向前走，
                    <br />
                    让版本有迹可循。
                  </h2>
                  <p>
                    整理证据，设计镜头，试听声音。
                    <br />
                    在关键节点确认，让 Codex 接着完成制作。
                  </p>
                  <button className="primary" onClick={() => setNewOpen(true)}>
                    创建第一个项目 <ArrowUpRight size={17} />
                  </button>
                </div>
                <div className="process-art">
                  <div className="film-label">YOUR NEXT STORY</div>
                  <div className="frame-lines">
                    <span>01</span>
                    <strong>
                      想法有了。
                      <br />
                      开始制作。
                    </strong>
                    <div className="frame-footer">
                      <span>营销 / 教学</span>
                      <Clapperboard size={35} />
                    </div>
                  </div>
                  <div className="mini-track">
                    <i />
                    <i />
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
              </div>
              <div className="intro-row">
                <div>
                  <b>01 / 公共流程</b>
                  <p>八个阶段，连接资料、声音与画面。</p>
                </div>
                <div>
                  <b>02 / 内容分支</b>
                  <p>营销讲清价值，教学帮助观众完成任务。</p>
                </div>
                <div>
                  <b>03 / 可复用模板</b>
                  <p>留住有效的方法，开始下一条视频。</p>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="tabs">
                {[
                  ["work", "制作工作台", Clapperboard],
                  ["documents", "内容与素材", FileText],
                  ["audio", "声音与字幕", AudioLines],
                  ["preview", "预览与确认", Play],
                  ["delivery", "验收与交付", Package],
                ].map(([id, title, Icon]) => (
                  <button
                    key={id as string}
                    className={tab === id ? "selected" : ""}
                    onClick={() => setTab(id as string)}
                  >
                    {React.createElement(Icon as any, { size: 16 })}
                    {title as string}
                  </button>
                ))}
              </div>
              {tab === "work" && (
                <div className="work-grid">
                  <section className="panel stages">
                    <h2>制作流程</h2>
                    {stages.map((id, i) => {
                      const r = runs.find((x) => x.stage === id);
                      const automated = project.automation_events?.find((e) => e.data.stage === id)?.data;
                      return (
                        <button
                          key={id}
                          className={
                            "stage " + (stage === id ? "selected" : "")
                          }
                          onClick={() => setStage(id)}
                        >
                          <span className="stage-num">
                            {r?.status === "succeeded" && !r.stale ? (
                              <Check size={15} />
                            ) : (
                              String(i + 1).padStart(2, "0")
                            )}
                          </span>
                          <span>
                            {labels[i]}
                            <small>
                              {r
                                ? r.stale
                                  ? "输入已修改"
                                  : states[r.status]
                                : automated
                                  ? automated.status === "completed" ? "自动制作完成 · 未人工确认" : automated.status === "running" ? "自动制作中" : "自动制作需处理"
                                  : "尚未开始"}
                            </small>
                          </span>
                          {stage === id && <ChevronRight size={16} />}
                        </button>
                      );
                    })}
                  </section>
                  <section className="panel task">
                    <div className="section-title">
                      <h2>{labels[stages.indexOf(stage)]}</h2>
                      {latest && badge(latest)}
                    </div>
                    {project.config.execution_mode === "delegated_automation" && (
                      <p className="muted">本项目通过授权自动化脚本制作。阶段记录与产物可供复核；自动检查不等于人工试听、预览确认或学习效果验证。</p>
                    )}
                    <p className="muted">
                      {
                        [
                          "明确观众、结果与证据，把未知项留在简报里。",
                          "把一个核心目标拆成脚本，确认后再设计画面。",
                          "确定每镜的焦点、变化与阅读时间。",
                          "先验证最容易返工的一段。",
                          "试听正式旁白，校正字幕，再锁定时间。",
                          "检查完整内容、节奏和画幅，确认当前版本。",
                          "对最终编码文件执行技术分析与抽帧。",
                          "将工程、素材和验收记录打包，保留可编辑版本。",
                        ][stages.indexOf(stage)]
                      }
                    </p>
                    <label>
                      本次制作要求
                      <textarea
                        value={instruction}
                        onChange={(e) => setInstruction(e.target.value)}
                        placeholder="例如：先展示最终结果，缩短开场；保留观众需要跟做的步骤。"
                      />
                    </label>
                    <div className="actions">
                      <button
                        className="primary"
                        disabled={busy || !!active}
                        onClick={() =>
                          act(() =>
                            start(
                              stage === "render"
                                ? "render"
                                : stage === "delivery"
                                  ? "package"
                                  : "agent",
                            ),
                          )
                        }
                      >
                        {busy ? (
                          <LoaderCircle size={16} className="spin" />
                        ) : (
                          <Play size={16} />
                        )}
                        开始此阶段
                      </button>
                      {active && (
                        <button
                          onClick={() =>
                            act(async () => {
                              await api(`/runs/${active.id}/cancel`, {});
                              await refresh();
                            })
                          }
                        >
                          <Square size={14} />
                          取消任务
                        </button>
                      )}
                    </div>
                    {latest && (
                      <div className="run-detail">
                        <h3>最近一次运行</h3>
                        <p>
                          {latest.message ||
                            "任务已进入队列，由本机 Worker 执行。"}
                        </p>
                        <div className="actions">
                          <button
                            onClick={() =>
                              act(async () =>
                                setLogs(await api(`/runs/${latest.id}/logs`)),
                              )
                            }
                          >
                            查看运行日志
                          </button>
                          {["blocked", "failed", "cancelled"].includes(
                            latest.status,
                          ) && (
                            <button
                              disabled={busy}
                              onClick={() =>
                                act(async () => {
                                  await api(`/runs/${latest.id}/retry`, {});
                                  await refresh();
                                })
                              }
                            >
                              按当前输入重试
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                    {Object.entries(logs).map(([name, text]) => (
                      <details key={name}>
                        <summary>{name}</summary>
                        <pre>{text}</pre>
                      </details>
                    ))}
                  </section>
                  <aside className="panel guide">
                    <h2>本阶段产物</h2>
                    <p>
                      文档、声音和预览会保留在运行记录中。确认只对当前版本有效。
                    </p>
                    {artifacts
                      .filter((a) => a.run_id === latest?.id)
                      .slice(0, 8)
                      .map((a) => (
                        <a
                          className="file-item"
                          key={a.id}
                          href={`/api/artifacts/${a.id}/file`}
                        >
                          <FileText size={14} />
                          {a.path.split("/").pop()}
                        </a>
                      ))}
                    {waiting && (
                      <div className="review-callout">
                        <MessageSquare size={20} />
                        <h3>有一版等待确认</h3>
                        <p>{labels[stages.indexOf(waiting.stage)]}</p>
                        <button onClick={() => setTab("preview")}>
                          查看并确认 <ChevronRight size={15} />
                        </button>
                      </div>
                    )}
                  </aside>
                </div>
              )}
              {tab === "documents" && (
                <div className="editor-grid">
                  <section className="panel file-list">
                    <div className="section-title">
                      <h2>项目文件</h2>
                      <label className="upload" title="导入素材">
                        <Upload size={17} />
                        <input
                          type="file"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f)
                              act(async () => {
                                const data = new FormData();
                                data.append("file", f);
                                await api(
                                  `/projects/${project.id}/assets`,
                                  data,
                                );
                                await refresh();
                                setNotice("素材已导入。");
                              });
                          }}
                        />
                      </label>
                    </div>
                    {files.map((f) => (
                      <button
                        key={f.path}
                        title={f.path}
                        onClick={() => act(() => loadDoc(f.path))}
                        className={doc?.path === f.path ? "selected" : ""}
                      >
                        <FileText size={14} />
                        {f.path.replace("documents/", "")}
                      </button>
                    ))}
                  </section>
                  <section className="panel editor">
                    <div className="section-title">
                      <h2>{doc?.path ?? "选择一份文档"}</h2>
                      <button
                        disabled={!doc || busy || !dirty}
                        onClick={() =>
                          act(async () => {
                            const r = await api(
                              `/projects/${project.id}/document`,
                              doc,
                              "PUT",
                            );
                            setDoc({ ...doc!, revision: r.revision });
                            setDirty(false);
                            setNotice("已保存新版本；相关检查将重新评估。");
                            await refresh();
                          })
                        }
                      >
                        <Save size={15} />
                        保存{dirty ? " *" : ""}
                      </button>
                    </div>
                    {doc ? (
                      <textarea
                        className="code-editor"
                        spellCheck={false}
                        value={doc.content}
                        onChange={(e) => {
                          setDoc({ ...doc, content: e.target.value });
                          setDirty(true);
                        }}
                      />
                    ) : (
                      <div className="empty">
                        从左侧打开简报、脚本或分镜。素材和成片可在预览页查看。
                      </div>
                    )}
                  </section>
                </div>
              )}
              {tab === "audio" && (
                <div className="two-cols">
                  <section className="panel">
                    <h2>本地 Qwen 旁白</h2>
                    <p className="muted">
                      短试音 → 修正 → 正式生成 → 试听与字幕校正
                    </p>
                    <label>
                      分段发音文本
                      <textarea
                        maxLength={500}
                        value={speech}
                        onChange={(e) => setSpeech(e.target.value)}
                        placeholder="输入一段旁白，最多 500 字。正式拼写保留在脚本里。"
                      />
                    </label>
                    <label>
                      请求音色
                      <input
                        value={voice}
                        onChange={(e) => setVoice(e.target.value)}
                      />
                    </label>
                    <label>
                      关联脚本段落
                      <input
                        value={segmentId}
                        onChange={(e) => setSegmentId(e.target.value)}
                        placeholder="SEG01"
                      />
                    </label>
                    <label>
                      声音表达
                      <input
                        value={voiceStyle}
                        onChange={(e) => setVoiceStyle(e.target.value)}
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={busy || !!active || !speech.trim()}
                      onClick={() =>
                        act(() =>
                          start(
                            "tts",
                            {
                              text: speech,
                              voice,
                              segment_id: segmentId,
                              style: voiceStyle,
                            },
                            "timing",
                          ),
                        )
                      }
                    >
                      <AudioLines size={16} />
                      生成此段声音
                    </button>
                    <p className="hint">
                      实际生效的音色以服务元数据与试听为准。
                    </p>
                  </section>
                  <section className="panel">
                    <h2>音频与字幕</h2>
                    <label className="upload-button">
                      <Upload size={16} />
                      导入音频或 SRT
                      <input
                        type="file"
                        accept="audio/*,.srt"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f)
                            act(async () => {
                              const data = new FormData();
                              data.append("file", f);
                              await api(
                                `/projects/${project.id}/assets?folder=${f.name.endsWith(".srt") ? "captions" : "audio"}`,
                                data,
                              );
                              await refresh();
                            });
                        }}
                      />
                    </label>
                    {files
                      .filter(
                        (f) =>
                          f.path.startsWith("audio/") ||
                          f.path.startsWith("captions/"),
                      )
                      .map((f) => (
                        <div className="audio-row" key={f.path}>
                          <span>{f.path}</span>
                          {/\.(wav|mp3|m4a)$/.test(f.path) && (
                            <button
                              disabled={busy || !!active}
                              onClick={() =>
                                act(() =>
                                  start(
                                    "transcribe",
                                    { path: f.path },
                                    "timing",
                                  ),
                                )
                              }
                            >
                              转录
                            </button>
                          )}
                          {f.path.endsWith(".srt") && (
                            <button
                              onClick={() => {
                                setTab("documents");
                                act(() => loadDoc(f.path));
                              }}
                            >
                              校正
                            </button>
                          )}
                        </div>
                      ))}
                    {media
                      .filter((a) => /\.(wav|mp3|m4a)$/.test(a.path))
                      .slice(0, 4)
                      .map((a) => (
                        <div key={a.id} className="audio-player">
                          <small>{a.path.split("/").pop()}</small>
                          <audio controls src={`/api/artifacts/${a.id}/file`} />
                        </div>
                      ))}
                  </section>
                </div>
              )}
              {tab === "preview" && (
                <div className="preview-grid">
                  <section className="panel">
                    <div className="section-title">
                      <h2>版本预览</h2>
                      <select
                        aria-label="预览版本"
                        value={current?.id ?? ""}
                        onChange={(e) => setSelected(e.target.value)}
                      >
                        {media.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.path.split("/").slice(-2).join("/")} ·{" "}
                            {a.sha256.slice(0, 6)}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="player">
                      {!current ? (
                        <div className="empty">
                          <Play size={30} />
                          <p>完成关键小样后，在这里查看画面。</p>
                        </div>
                      ) : /\.(mp4|webm)$/.test(current.path) ? (
                        <VideoPlayer
                          key={current.id}
                          ref={video}
                          src={`/api/artifacts/${current.id}/file`}
                        />
                      ) : /\.(png|jpg)$/.test(current.path) ? (
                        <img src={`/api/artifacts/${current.id}/file`} />
                      ) : (
                        <audio
                          controls
                          src={`/api/artifacts/${current.id}/file`}
                        />
                      )}
                    </div>
                    <label>
                      修改意见
                      <textarea
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="指出具体段落、时间或需要调整的内容。"
                      />
                    </label>
                    <button
                      disabled={!current || !note.trim()}
                      onClick={() =>
                        act(async () => {
                          await api(`/projects/${project.id}/comments`, {
                            artifact_id: current!.id,
                            at_s: video.current?.currentTime ?? 0,
                            note,
                          });
                          setNote("");
                          await refresh();
                          setNotice("已保存带时间点的意见。");
                        })
                      }
                    >
                      记录当前时间点意见
                    </button>
                    {project.comments?.map((c) => (
                      <p className="comment" key={c.id}>
                        {c.at_s.toFixed(1)}s · {c.note}
                      </p>
                    ))}
                  </section>
                  <section className="panel">
                    <h2>确认当前交接</h2>
                    {waiting ? (
                      <>
                        <span className="badge awaiting_review">
                          {labels[stages.indexOf(waiting.stage)]} · 待确认
                        </span>
                        <p>{waiting.message}</p>
                        {artifacts
                          .filter((a) => a.run_id === waiting.id)
                          .map((a) => (
                            <a
                              className="file-item"
                              href={`/api/artifacts/${a.id}/file`}
                              key={a.id}
                            >
                              {a.path.split("/").pop()}
                            </a>
                          ))}
                        <p className="hint">
                          请先检查该运行的产物。确认绑定这一次运行；其他版本的播放不代表它已通过。
                        </p>
                        <div className="actions">
                          <button
                            className="primary"
                            disabled={busy}
                            onClick={() =>
                              act(async () => {
                                await api(`/runs/${waiting.id}/review`, {
                                  decision: "approve",
                                  note,
                                });
                                setNote("");
                                await refresh();
                              })
                            }
                          >
                            <Check size={16} />
                            确认此版本
                          </button>
                          <button
                            disabled={busy || !note.trim()}
                            onClick={() =>
                              act(async () => {
                                await api(`/runs/${waiting.id}/review`, {
                                  decision: "revise",
                                  note,
                                });
                                await refresh();
                              })
                            }
                          >
                            需要修改
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="empty">暂无有效的待确认版本。</div>
                    )}
                  </section>
                </div>
              )}
              {tab === "delivery" && (
                <div className="two-cols">
                  <section className="panel">
                    <h2>技术目标与交付配置</h2>
                    <p className="muted">
                      保留实际画幅、帧率、编码与响度目标。未配置的检查不会自动通过。
                    </p>
                    <button
                      onClick={() =>
                        setSettings(JSON.stringify(project.config, null, 2))
                      }
                    >
                      读取当前配置
                    </button>
                    <textarea
                      className="config-editor"
                      aria-label="项目配置"
                      value={settings}
                      onChange={(e) => setSettings(e.target.value)}
                      placeholder={
                        '{"audio_mode":"none","targets":{"width":1920,"height":1080,"fps":30,"video_codec":"h264"}}'
                      }
                    />
                    <button
                      disabled={!settings || busy}
                      onClick={() =>
                        act(async () => {
                          await api(
                            `/projects/${project.id}`,
                            {
                              revision: project.config_revision,
                              config: JSON.parse(settings),
                            },
                            "PATCH",
                          );
                          await refresh();
                          setNotice("配置已更新。");
                        })
                      }
                    >
                      保存项目配置
                    </button>
                  </section>
                  <section className="panel">
                    <h2>交付文件</h2>
                    <p className="muted">
                      已有成片可直接进行技术复检。检查完成后，请到「预览与确认」检查对应版本并确认；技术通过不代表人工验收通过。
                    </p>
                    {artifacts
                      .filter((a) => a.available !== false && a.path.endsWith(".mp4") && !a.path.endsWith("/render.mp4"))
                      .slice(0, 4)
                      .map((a) => (
                        <button
                          key={a.id}
                          disabled={busy || !!active}
                          onClick={() =>
                            act(() =>
                              start("qa", { artifact_id: a.id }, "render"),
                            )
                          }
                        >
                          重新检查 {a.path.split("/").pop()}
                        </button>
                      ))}
                    {artifacts
                      .filter(
                        (a) =>
                          a.available !== false && a.role !== "source" &&
                          (a.path.includes("/exports/") || a.path.endsWith("/qa/final/report.json")) &&
                          !a.path.endsWith("/render.mp4") && /\.(mp4|zip|json|jpg|srt)$/.test(a.path),
                      )
                      .map((a) => (
                        <a
                          className="delivery-file"
                          key={a.id}
                          href={`/api/artifacts/${a.id}/file`}
                        >
                          <FileText size={18} />
                          <span>
                            {a.path.split("/").pop()}
                            <small>{a.version} · SHA-256 {a.sha256.slice(0, 16)}…</small>
                          </span>
                          <ArrowUpRight size={16} />
                        </a>
                      ))}
                    <details><summary>失效历史记录（不可下载）</summary>
                      {artifacts.filter(a => a.available === false).map(a => <p key={a.id}>{a.version} · {a.path.split('/').pop()} · {a.sha256.slice(0,8)} · 文件已变化或不存在</p>)}
                    </details>
                    {!artifacts.length && (
                      <div className="empty">尚无交付产物。</div>
                    )}
                  </section>
                </div>
              )}
            </>
          )}
        </div>
        <footer>
          片场 · 本机制作与版本管理<span>公开发布与投放需单独授权</span>
        </footer>
      </main>
      {newOpen && (
        <div className="modal-backdrop">
          <form
            className="modal"
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                const p = await api("/projects", {
                  name,
                  branch,
                  config: {
                    brief,
                    audio_mode: audioMode,
                    targets: {
                      width: orientation === "vertical" ? 1080 : 1920,
                      height: orientation === "vertical" ? 1920 : 1080,
                      fps: 30,
                      video_codec: "h264",
                      ...(audioMode === "none"
                        ? {}
                        : { audio_codec: "aac", sample_rate: 48000 }),
                    },
                  },
                });
                setNewOpen(false);
                setName("");
                setBrief("");
                await pick(p);
              });
            }}
          >
            <div className="section-title">
              <h2>开始一条新视频</h2>
              <button type="button" onClick={() => setNewOpen(false)}>
                关闭
              </button>
            </div>
            <label>
              项目名称
              <input
                autoFocus
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：三分钟讲清产品的核心用法"
              />
            </label>
            <label>
              内容分支
              <select
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
              >
                <option value="marketing">营销视频 · 让价值被看见</option>
                <option value="teaching">教学自媒体 · 帮观众完成任务</option>
              </select>
            </label>
            <div className="two-cols">
              <label>
                画幅
                <select
                  value={orientation}
                  onChange={(e) => setOrientation(e.target.value)}
                >
                  <option value="horizontal">横版 16:9</option>
                  <option value="vertical">竖版 9:16</option>
                </select>
              </label>
              <label>
                声音
                <select
                  value={audioMode}
                  onChange={(e) => setAudioMode(e.target.value)}
                >
                  <option value="qwen">本地 Qwen</option>
                  <option value="imported">导入原声</option>
                  <option value="none">无旁白</option>
                </select>
              </label>
            </div>
            <label>
              目标与可用资料
              <textarea
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                placeholder="给谁看？希望观众看完做什么？有哪些资料和素材？"
              />
            </label>
            <button className="primary" disabled={busy || !name.trim()}>
              创建项目 <ArrowUpRight size={16} />
            </button>
            <p className="hint">创建后可以继续补充简报、画幅和声音配置。</p>
          </form>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
