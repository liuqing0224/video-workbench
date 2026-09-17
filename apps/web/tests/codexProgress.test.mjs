import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCodexProgress,mergeCodexProgress} from '../src/codexProgress.ts';
const event=(type,item)=>JSON.stringify({type,item});
test('handles truncated tails, excludes reasoning and tool bodies, updates existing operation',()=>{
 const log=['broken',event('item.completed',{id:'r',type:'reasoning',text:'private'}),event('item.started',{id:'t',type:'mcp_tool_call',arguments:{title:'核对素材',code:'secret'}}),event('item.completed',{id:'t',type:'mcp_tool_call',arguments:{title:'核对素材'},result:{text:'secret'}}),event('item.completed',{id:'m',type:'agent_message',text:'脚本已整理'}),'incomplete{'].join('\n');
 assert.deepEqual(parseCodexProgress(log),[{id:'t',text:'核对素材',state:'已记录'},{id:'m',text:'脚本已整理',state:'已记录'}]);
});
test('preserves polling window and reports failed tool truthfully',()=>{
 const log=Array.from({length:8},(_,i)=>event('item.completed',{id:String(i),type:'command_execution',status:i===7?'failed':'completed'})).join('\n');
 const entries=parseCodexProgress(log); assert.equal(entries.length,8); assert.equal(entries.at(-1).state,'失败');
});
test('shows a readable summary for structured final output',()=>{
 const entries=parseCodexProgress(event('item.completed',{id:'m',type:'agent_message',text:JSON.stringify({summary:'方案完成',artifacts:['internal/file']})}));
 assert.equal(entries[0].text,'方案完成');
});

test('overlapping windows retain history, update operations and avoid duplicate rerenders',()=>{
 const a={id:'a',text:'读取文章',state:'执行中'};
 const b={id:'b',text:'写入脚本',state:'执行中'};
 const first=mergeCodexProgress([a],[{...a,state:'已记录'},b]);
 assert.equal(first.length,2);assert.equal(first[0].state,'已记录');
 assert.equal(mergeCodexProgress(first,[b]),first);
 const many=Array.from({length:600},(_,i)=>({...a,id:String(i)}));
 assert.equal(mergeCodexProgress([],many).length,500);
});
test('real-time log keeps tool start and completion as separate events', async()=>{
 const {parseCodexLog}=await import('../src/codexProgress.ts');
 const item={id:'tool1',type:'mcp_tool_call',server:'local',tool:'read',arguments:{title:'读取脚本'}};
 const rows=parseCodexLog([event('item.started',item),event('item.completed',item),event('item.completed',{id:'r',type:'reasoning',text:'private'})].join('\n'));
 assert.equal(rows.length,2);assert.notEqual(rows[0].id,rows[1].id);assert.match(rows[0].text,/item.started \[local\/read\]/);
});
