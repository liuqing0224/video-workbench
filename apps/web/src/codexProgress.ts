export type CodexActivity = {id: string; text: string; state: string};
// Only public messages and tool summaries, never reasoning or raw tool arguments/results.
export function parseCodexProgress(log: string): CodexActivity[] {
  const items = new Map<string, CodexActivity>();
  for (const line of log.split('\n')) {
    let event;
    try { event = JSON.parse(line); } catch { continue; } // Log tail may start/end mid-record.
    const item = event.item;
    if (!item || !['item.started','item.updated','item.completed'].includes(event.type)) continue;
    let text = '';
    if (item.type === 'agent_message') text = typeof item.text === 'string' ? item.text : '';
    if (item.type === 'mcp_tool_call') text = typeof item.arguments?.title === 'string' ? item.arguments.title : `调用工具：${item.tool || '工具'}`;
    if (item.type === 'command_execution') text = '执行本地检查或文件操作';
    if (item.type === 'file_change') text = '更新制作文件';
    if (item.type === 'agent_message') {
      try {
        const result = JSON.parse(text);
        if (typeof result.summary === 'string') text = result.summary;
      } catch { /* Ordinary public narrative */ }
    }
    if (!text) continue;
    const id = String(item.id ?? items.size);
    items.set(id, {id, text: text.slice(0, 700), state: item.status === 'failed' || item.error ? '失败' : event.type === 'item.completed' ? '已记录' : '执行中'});
  }
  return [...items.values()];
}

// Polling windows overlap: update an existing operation in place, append new IDs.
export function mergeCodexProgress(previous: CodexActivity[], incoming: CodexActivity[]): CodexActivity[] {
  const result = new Map(previous.map(item=>[item.id,item]));
  let changed=false;
  for (const item of incoming) {
    const old=result.get(item.id);
    if (!old || old.text!==item.text || old.state!==item.state) {result.set(item.id,item);changed=true;}
  }
  return changed ? [...result.values()].slice(-500) : previous;
}

// Chronological public execution events; unlike the summary, start/end are separate rows.
export function parseCodexLog(log: string): CodexActivity[] {
  const rows: CodexActivity[]=[];
  for (const line of log.split('\n')) {
    let event;
    try {event=JSON.parse(line);} catch {continue;}
    const item=event.item;
    if(item?.type==='reasoning') continue;
    if(item) {
      const summary=parseCodexProgress(line)[0];
      if(!summary) continue;
      const tool=item.type==='mcp_tool_call' ? ` [${item.server ?? 'tool'}/${item.tool ?? ''}]` : '';
      rows.push({...summary,state:event.type==='item.started'?'开始':summary.state,id:`${summary.id}:${event.type}`,text:`${event.type}${tool}\n${summary.text}`});
    } else if (['thread.started','turn.started','turn.completed','turn.failed','error'].includes(event.type)) {
      rows.push({id:`${event.type}:${event.thread_id ?? ''}`,state:event.type.includes('failed')||event.type==='error'?'失败':'事件',text:event.type+(event.error?.message?`\n${String(event.error.message).slice(0,700)}`:'')});
    }
  }
  return rows;
}
