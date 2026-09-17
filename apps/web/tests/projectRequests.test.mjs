import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const source = readFileSync(new URL('../src/projectRequests.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { ProjectRequestGuard } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
test('late A response cannot replace B or become valid after returning to A', () => {
  const guard = new ProjectRequestGuard();
  guard.select('A'); const oldA = guard.begin('A');
  guard.select('B'); const b = guard.begin('B');
  assert.equal(oldA(), false); assert.equal(b(), true);
  guard.select('A'); assert.equal(oldA(), false); assert.equal(b(), false);
  assert.equal(guard.begin('A')(), true);
});
test('out-of-order refresh responses cannot overwrite latest data', () => {
  const guard = new ProjectRequestGuard(); guard.select('A');
  const earlier = guard.begin('A'), later = guard.begin('A');
  assert.equal(earlier(), false); assert.equal(later(), true);
});
