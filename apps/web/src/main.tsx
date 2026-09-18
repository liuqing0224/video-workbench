import { VisualReview } from "./VisualReview";
import { AudioPlayer } from "./AudioPlayer";
import { CodexLog } from "./CodexLog";
import { parseCodexProgress, parseCodexLog, mergeCodexProgress, type CodexActivity } from "./codexProgress";
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
  heartbeat?: number;
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
const flowSteps = [
  {title:"内容方向", stages:["brief","content"], description:"从文章提炼受众、主题与证据，改写标题、开场和口播，再确认内容方向。"},
  {title:"案例与分镜", stages:["storyboard"], description:"选择已有案例，把讲解逻辑、配色、镜头状态和转场落实到分镜。"},
  {title:"关键小样", stages:["sample"], description:"先制作最难的一段，检查实际画面、节奏与表达，再扩展整片。"},
  {title:"声音与字幕", stages:["timing"], description:"Qwen 试音与正式声音、字幕校正、统一时间；镜头跟随真实声音和阅读时间。"},
  {title:"整片预览", stages:["preview"], description:"观看完整内容、声画同步和连贯性，确认具体预览版本。"},
  {title:"验收交付", stages:["render","delivery"], description:"渲染最终文件、检查编码与响度、绑定哈希，再打包交付并记录复盘。"},
];
const documentNames: Record<string,string> = {"ARTICLE-ANALYSIS.md":"文章分析与选题", "SCRIPT.md":"标题与口播脚本", "STORYBOARD.md":"镜头分镜", "REFERENCES.md":"案例参考", "BRIEF.md":"受众与内容目标", "PRODUCTION-PLAN.md":"后续制作计划", "DESIGN.md":"视觉规范"};
const flowLabel = (id:string) => flowSteps.find(f=>f.stages.includes(id))?.title ?? id;
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
    [sourceFile, setSourceFile] = useState<File | null>(null),
    [importError, setImportError] = useState(""),
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
  const initialStageProject = useRef<string | null>(null);
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
      if (initialStageProject.current === pid) {
        initialStageProject.current = null;
        const pending = p.runs?.find((r:Run)=>["running","queued","awaiting_review"].includes(r.status) && !r.stale) ?? p.runs?.[0];
        if (pending) setStage(pending.stage);
      }
      return p as Project;
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
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    if (!active || !project) return;
    const pid = project.id;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      setClock(Date.now());
      try { if (requests.current.projectId === pid) await refresh(pid); } catch { /* SSE and next poll can recover */ }
      if (!stopped) timer = setTimeout(poll, 5000);
    };
    timer = setTimeout(poll, 5000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [project?.id, active?.id]);
  const activeMinutes = active ? Math.floor(Math.max(0, clock / 1000 - active.created) / 60) : 0;
  const activeSeconds = active ? Math.floor(Math.max(0, clock / 1000 - active.created) % 60) : 0;
  const artifacts = project?.artifacts ?? [],
    media = artifacts.filter(a => a.available !== false)
      .sort((a, b) => Number(!!b.run_id) - Number(!!a.run_id))
      .filter((a, i, all) => all.findIndex((x) => x.sha256 === a.sha256) === i)
      .filter((a) => /\.(mp4|webm|wav|mp3|m4a|png|jpg)$/i.test(a.path));
  const current =
    media.find((a) => a.id === selected) ??
    media.find((a) => /\.(mp4|webm)$/.test(a.path)) ??
    media[0];
  const stageRuns = runs.filter(r=>!["tts","transcribe"].includes(r.kind));
  const latest = stageRuns.find((r) => r.stage === stage);
  const progressRun = active ?? latest;
  const [progress, setProgress] = useState<{runId:string; entries:CodexActivity[]; summary:CodexActivity[]; checked:number; error:boolean}>({runId:"", entries:[], summary:[], checked:0, error:false});
  useEffect(() => {
    if (!project || !progressRun || tab !== "work" || !["agent","article-plan"].includes(progressRun.kind)) return;
    const pid = project.id, rid = progressRun.id;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const update = async () => {
      try {
        const data = await api(`/runs/${rid}/logs`);
        if (!stopped && requests.current.projectId === pid) setProgress(p=>({runId:rid,entries:mergeCodexProgress(p.runId===rid?p.entries:[],parseCodexLog(data["codex.jsonl"] ?? "")),summary:parseCodexProgress(data["codex.jsonl"] ?? "").slice(-6),checked:Date.now(),error:false}));
      } catch {
        if (!stopped && requests.current.projectId === pid) setProgress(p=>({runId:rid,entries:p.runId===rid?p.entries:[],summary:p.runId===rid?p.summary:[],checked:p.checked,error:true}));
      }
      if (!stopped && ["running","queued"].includes(progressRun.status)) timer = setTimeout(update, 3000);
    };
    update();
    return () => { stopped = true; clearTimeout(timer); };
  }, [project?.id, progressRun?.id, progressRun?.status, tab]);
  const activities = progressRun?.id === progress.runId ? progress.entries : [];
  const currentFlow = flowSteps.find(f=>f.stages.includes(stage))!;
  const flowIndex = flowSteps.indexOf(currentFlow);
  function flowRun(ids:string[]) {
    // Content planning from an imported article already includes the brief.
    return [...ids].reverse().map(id=>stageRuns.find(r=>r.stage===id)).find(Boolean);
  }
  function selectFlow(index:number) {
    const ids=flowSteps[index].stages;
    const last=flowRun(ids);
    const next=last && last.status==="succeeded" && !last.stale ? ids[ids.indexOf(last.stage)+1] : undefined;
    setStage(next ?? last?.stage ?? ids[0]);
  }
  const waiting = runs.find((r) => r.status === "awaiting_review" && !r.stale);
  const importAttempt = useRef<{project: Project | null; path: string; key: string}>({project:null,path:"",key:""});
  function openIntake() {
    importAttempt.current = {project:null,path:"",key:crypto.randomUUID()};
    setSourceFile(null); setImportError(""); setName(""); setBrief(""); setNewOpen(true);
  }
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
    initialStageProject.current = p.id;
    setProject(p);
    setFiles([]);
    setLogs({});
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
          <button aria-label="新建项目" onClick={openIntake}>
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
          <button className="light" onClick={openIntake}>
            <Plus size={16} /> 上传文档 / 新建视频
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
                  <button className="primary" onClick={openIntake}>
                    上传文档并解析 <ArrowUpRight size={17} />
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
                  <p>六个步骤，连接内容、案例、声音与交付。</p>
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
                    {flowSteps.map((flow, i) => {
                      const r = flowRun(flow.stages);
                      const automated = project.automation_events?.find(e=>flow.stages.includes(e.data.stage))?.data;
                      const complete = r?.status === "succeeded" && !r.stale && r.stage === flow.stages.at(-1);
                      const selected = flow.stages.includes(stage);
                      return <button key={flow.title} className={"stage " + (selected ? "selected" : "")} onClick={()=>selectFlow(i)}>
                        <span className="stage-num">{complete ? <Check size={15}/> : String(i+1).padStart(2,"0")}</span>
                        <span>{flow.title}<small>{r ? r.stale ? "输入已修改" : complete ? "已完成" : r.status==="succeeded" ? "继续下一项" : states[r.status] : automated ? "已有自动制作记录 · 待复核" : "尚未开始"}</small></span>
                        {selected && <ChevronRight size={16}/>}
                      </button>;
                    })}
                  </section>
                  <section className="panel task">
                    <div className="section-title">
                      <div><span className="step-kicker">第 {flowIndex+1} 步 / 共 6 步</span><h2>{currentFlow.title}</h2></div>
                      {latest && badge(latest)}
                    </div>
                    <div className="next-action">
                      <strong>{active ? (active.status === "queued" ? "等待后台接手" : active.kind === "article-plan" ? "正在拆解文章，生成内容方案" : `正在处理：${flowLabel(active.stage)}`) : latest?.status === "awaiting_review" && !latest.stale ? "方案已准备好，请先看一遍" : latest?.stale ? "内容有变化，需要重新检查" : latest?.status === "succeeded" ? "这项已完成，可以继续了" : "从这里开始"}</strong>
                      <p>{active ? `提交后已等待 ${activeMinutes} 分 ${activeSeconds} 秒。${active.status === "queued" ? "等待本机 Worker 接手。" : active.kind === "article-plan" ? "正在执行文章分析、案例参考与脚本分镜任务，此时尚未生成视频。" : "任务执行中，完成后会提示下一步。"}${active.heartbeat && clock / 1000 - active.heartbeat > 30 ? "后台心跳超过 30 秒未更新，请查看日志。" : ""}` : latest?.status === "awaiting_review" && !latest.stale ? "重点看主题是否准确、表达是否符合你的想法。确认后再进入下一步。" : "按下面的提示操作即可。额外要求可以不填，文件和记录会自动保留。"}</p>
                    </div>
                    {progressRun && ["agent","article-plan"].includes(progressRun.kind) && <CodexLog key={progressRun.id} runId={progressRun.id} entries={activities} checked={progress.runId===progressRun.id?progress.checked:0} running={["queued","running"].includes(progressRun.status)} error={progress.runId===progressRun.id && progress.error}/>}
                    {project.config.execution_mode === "delegated_automation" && (
                      <p className="muted">本项目通过授权自动化脚本制作。阶段记录与产物可供复核；自动检查不等于人工试听、预览确认或学习效果验证。</p>
                    )}
                    <p className="muted">{currentFlow.description}</p>
                    <details className="advanced"><summary>更多任务选项</summary>
                    {currentFlow.stages.length > 1 && <div className="actions" aria-label="步骤内任务">
                      {currentFlow.stages.map(id=><button key={id} className={stage===id ? "selected" : ""} aria-pressed={stage===id} onClick={()=>setStage(id)}>{labels[stages.indexOf(id)]}</button>)}
                    </div>}
                    </details>
                    {stage === "timing" && <button onClick={()=>setTab("audio")}>打开声音与字幕</button>}
                    <details className="advanced" open={!latest || latest.stale || !["succeeded","awaiting_review"].includes(latest.status)} key={stage+":"+latest?.status}><summary>{latest && ["succeeded","awaiting_review"].includes(latest.status) ? "补充要求或重新制作" : "制作要求与操作"}</summary>
                    <label>
                      想调整什么？（可选）
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
                        {stage === "brief" ? "整理目标与证据" : stage === "content" ? "生成内容方案" : stage === "storyboard" ? "生成案例与分镜" : stage === "sample" ? "制作关键小样" : stage === "timing" ? "校正字幕与时间" : stage === "preview" ? "生成整片预览" : stage === "render" ? "渲染并验收" : "打包交付"}
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
                    </details>
                    {latest?.status === "awaiting_review" && !latest.stale && <button className="primary next-button" onClick={()=>setTab("preview")}>查看并确认{currentFlow.title}</button>}
                    {latest?.status === "succeeded" && !latest.stale && <button className="primary next-button" onClick={()=>{
                      const next=currentFlow.stages[currentFlow.stages.indexOf(stage)+1];
                      if(next) setStage(next); else if(flowIndex<flowSteps.length-1) selectFlow(flowIndex+1); else setTab("delivery");
                    }}>{stage==="render" ? "继续打包交付" : stage==="brief" ? "继续内容方案" : flowIndex<flowSteps.length-1 ? `下一步：${flowSteps[flowIndex+1].title}` : "查看交付文件"}</button>}
                    {latest && (
                      <details className="run-detail"><summary>任务记录与问题排查</summary>
                        <p>
                          {latest.message ||
                            (latest.status === "queued" ? "任务已进入队列，等待本机 Worker 接手。" : latest.status === "running" ? "后台正在执行，可展开运行日志查看实际记录。" : "暂无补充说明。")}
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
                      </details>
                    )}
                    {Object.entries(logs).map(([name, text]) => (
                      <details key={name}>
                        <summary>{name}</summary>
                        <pre>{text}</pre>
                      </details>
                    ))}
                  </section>
                  <aside className="panel guide">
                    <h2>本步成果</h2>
                    <p>先看中文方案，技术文件按需展开。</p>
                    {artifacts.filter(a=>a.run_id===latest?.id && documentNames[a.path.split("/").pop()!]).filter((a,i,all)=>all.findIndex(b=>b.path.split("/").pop()===a.path.split("/").pop())===i).map(a=><button className="result-link" key={a.id} onClick={()=>act(async()=>{await loadDoc("documents/"+a.path.split("/").pop());setTab("documents");})}><FileText size={16}/>{documentNames[a.path.split("/").pop()!]}<ChevronRight size={14}/></button>)}
                    {!latest && <p className="empty-hint">完成这一步后，结果会显示在这里。</p>}
                    <details className="advanced"><summary>全部文件与版本记录</summary>
                    {artifacts.filter(a=>a.run_id===latest?.id).map(a=><a className="file-item" key={a.id} href={`/api/artifacts/${a.id}/file`}>{a.path.split("/").pop()}</a>)}
                    </details>
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
                          <AudioPlayer src={`/api/artifacts/${a.id}/file`} />
                        </div>
                      ))}
                  </section>
                </div>
              )}
              {tab === "preview" && (
                <div className="preview-grid">
                  <VisualReview key={project.id} projectId={project.id} api={api} onChange={refresh} />
                  <section className="panel">
                    <div className="section-title">
                      <h2>{current ? "版本预览" : "内容方案"}</h2>
                      {!!media.length && <select
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
                      </select>}
                    </div>
                    <div className={"player" + (!current ? " document-preview" : "")}>
                      {!current ? (
                        <div className="empty">
                          <FileText size={30} />
                          <h3>{waiting?.stage === "content" ? "先看内容方案" : "还没有视频预览"}</h3>
                          <p>{waiting?.stage === "content" ? "这一步确认选题和口播，之后再制作画面与声音。" : "完成关键小样后，这里会出现可播放的视频。"}</p>
                          {waiting?.stage === "content" && <button onClick={()=>act(async()=>{await loadDoc("documents/SCRIPT.md");setTab("documents");})}>阅读标题与口播脚本</button>}
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
                        <AudioPlayer key={current.id} src={`/api/artifacts/${current.id}/file`} />
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
                    {current && <button
                      disabled={!note.trim()}
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
                    </button>}
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
                          {flowLabel(waiting.stage)} · 待确认
                        </span>
                        <p>{waiting.message}</p>
                        <details className="advanced"><summary>查看本版本全部产物</summary>
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
                        </details>
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
                    <details className="advanced"><summary>高级设置：技术目标与交付配置</summary>
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
                    </button></details>
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
                setImportError("");
                try {
                if (sourceFile) {
                  if (!/\.(md|txt)$/i.test(sourceFile.name)) throw Error("目前支持 Markdown 或 TXT 文档");
                  if (sourceFile.size > 500000) throw Error("文档超过500KB，请拆成独立主题");
                  const text = new TextDecoder("utf-8", {fatal:true}).decode(await sourceFile.arrayBuffer());
                  if (!text.trim() || text.includes("\0")) throw Error("文档内容为空或不是有效文本");
                }
                const p = importAttempt.current.project ?? await api("/projects", {
                  name,
                  branch,
                  config: {
                    brief,
                    audio_mode: audioMode,
                    visual_review_required: true,
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
                importAttempt.current.project = p;
                if (sourceFile) {
                  if (!importAttempt.current.path) {
                    const data = new FormData(); data.append("file", sourceFile);
                    const uploaded = await api(`/projects/${p.id}/assets`, data);
                    importAttempt.current.path = uploaded.path;
                  }
                  await api(`/projects/${p.id}/runs`, {
                    stage:"content", kind:"article-plan",
                    idempotency_key:importAttempt.current.key,
                    payload:{article_path:importAttempt.current.path},
                  });
                }
                await pick(p);
                if(sourceFile) {setStage("content");setNotice("文档已导入，正在解析并整理视频制作方案。");}
                setNewOpen(false); setName(""); setBrief(""); setSourceFile(null);
                } catch (err) { setImportError(err instanceof Error ? err.message : String(err)); }

              });
            }}
          >
            <div className="section-title">
              <h2>上传文档，开始制作</h2>
              <button type="button" disabled={busy} onClick={() => setNewOpen(false)}>
                关闭
              </button>
            </div>
            <p className="hint">上传文章后，自动整理选题、口播、案例参考与分镜。也可以不上传，先创建空白项目。</p>
            {importError && <div role="alert" className="alert">{importError}</div>}
            <label className="document-intake">
              上传文档
              <input type="file" aria-label="上传并解析文档" accept=".md,.txt" disabled={busy || !!importAttempt.current.project} onChange={e=>{
                const file=e.target.files?.[0] ?? null;
                setSourceFile(file); setImportError("");
                if(file && !name.trim()) setName(file.name.replace(/\.[^.]+$/, ""));
              }} />
              <small>{sourceFile ? `已选择：${sourceFile.name}` : "支持 Markdown / TXT，UTF-8 编码，最大 500KB"}</small>
            </label>
            <fieldset disabled={busy || !!importAttempt.current.project} className="intake-fields">
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
            </fieldset>
            <button className="primary" disabled={busy || !name.trim()}>
              {busy ? "正在处理…" : sourceFile ? "上传并解析文档" : "创建空白项目"} <ArrowUpRight size={16} />
            </button>
            <p className="hint">创建后可以继续补充简报、画幅和声音配置。</p>
          </form>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
