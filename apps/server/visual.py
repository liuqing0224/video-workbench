"""Version-bound visual decisions; technical checks cannot grant aesthetic approval."""
import hashlib
import json
from pathlib import Path

from apps.server.core import safe, digest, uid, now, dumps

PLAN = 'documents/VISUAL-PLAN.json'


def state(store, pid):
    root = store.root(pid)
    plan_file = safe(root, PLAN)
    required = bool(store.project(pid)['config'].get('visual_review_required')) or plan_file.exists()
    result = {'required': required, 'candidates': [], 'approved': None, 'history': []}
    if not plan_file.exists():
        return result
    try:
        plan = json.loads(plan_file.read_text())
        candidates = plan['candidates']
        if not isinstance(candidates, list) or len(candidates) > 8:
            raise ValueError('视觉候选数量必须不超过8个')
        ids = set()
        for candidate in candidates:
            cid = candidate['id']
            if not isinstance(cid, str) or not cid or cid in ids:
                raise ValueError('视觉候选编号缺失或重复')
            ids.add(cid)
            hashes = {PLAN: digest(plan_file)}
            paths = ['documents/DESIGN.md', 'documents/REFERENCES.md', candidate['design_path'], candidate['sample_path']]
            paths += candidate.get('evidence_paths', [])
            error = ''
            for path in paths:
                file = safe(root, path)
                if not file.is_file():
                    error = f'缺少视觉证据：{path}'
                    break
                hashes[path] = digest(file)
            if Path(candidate['sample_path']).suffix.lower() != '.mp4':
                error = '视觉小样必须是MP4'
            fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
            result['candidates'].append({**candidate, 'fingerprint': fingerprint, 'dependencies': hashes, 'ready': not error, 'error': error})
    except (KeyError, TypeError, ValueError) as exc:
        result['error'] = str(exc)
        return result
    history = store.rows('SELECT * FROM visual_reviews WHERE project_id=? ORDER BY created DESC', (pid,))
    result['history'] = history
    # The latest user decision supersedes all earlier selections, even when stale.
    latest = next((r for r in history if r['actor'] == 'user'), None)
    if latest and latest['decision'] == 'approve':
        candidate = next((c for c in result['candidates'] if c['id'] == latest['candidate_id']), None)
        if candidate and candidate['ready'] and candidate['fingerprint'] == latest['fingerprint']:
            result['approved'] = candidate['id']
    return result


def require_approved(store, pid):
    data = state(store, pid)
    if data['required'] and not data['approved']:
        raise ValueError('先在预览与确认中选择并确认具体视觉小样；自动化技术检查不替代视觉认可')
    return data


def review(store, pid, candidate_id, fingerprint, actor, decision, note):
    if actor not in ('user', 'automation') or decision not in ('approve', 'revise'):
        raise ValueError('无效的视觉确认类型')
    with store.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        if store.active(c, pid):
            raise ValueError('制作运行中，请结束后再确认视觉方向')
        candidate = next((x for x in state(store, pid)['candidates'] if x['id'] == candidate_id), None)
        if not candidate or not candidate['ready'] or candidate['fingerprint'] != fingerprint:
            raise ValueError('小样或设计依据已变化，请刷新后重新查看')
        c.execute('INSERT INTO visual_reviews VALUES(?,?,?,?,?,?,?,?)',
                  (uid(), pid, candidate_id, fingerprint, actor, decision, note, now()))
        store.event(c, pid, None, 'visual.reviewed', {'candidate_id': candidate_id, 'actor': actor, 'decision': decision})
    return state(store, pid)


def verify_work_copy(visual, work):
    if not visual or not visual['required']:
        return
    candidate = next(c for c in visual['candidates'] if c['id'] == visual['approved'])
    for path, expected in candidate['dependencies'].items():
        file = safe(work, path)
        if not file.is_file() or digest(file) != expected:
            raise ValueError(f'已选择的视觉依据被修改，需要重新确认：{path}')


def register_sample(work, run_id):
    """Stage a checked sample as a candidate in the run copy, before promotion."""
    import shutil
    from apps.server.core import atomic
    folder = work / 'assets' / 'visual-samples' / run_id
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copytree(work / 'hyperframes', folder / 'project', ignore=shutil.ignore_patterns('node_modules'), dirs_exist_ok=True)
    for name in ('DESIGN.md', 'REFERENCES.md'):
        shutil.copyfile(work / 'documents' / name, folder / name)
    shutil.copyfile(work / 'exports/sample.mp4', folder / 'sample.mp4')
    meta_file = work / 'documents/VISUAL-CANDIDATE.json'
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    rel = lambda path: str(path.relative_to(work))
    candidate = {'id': run_id, 'name': str(meta.get('name', '本次关键小样')),
                 'description': str(meta.get('description', '实际渲染的小样，等待选择视觉方向')),
                 'reference': str(meta.get('reference', '参考依据见本次 REFERENCES.md')),
                 'design_path': rel(folder / 'DESIGN.md'), 'sample_path': rel(folder / 'sample.mp4'),
                 'evidence_paths': [rel(f) for f in folder.rglob('*') if f.is_file() and f.name != 'sample.mp4']}
    plan_file = work / PLAN
    plan = json.loads(plan_file.read_text()) if plan_file.exists() else {'candidates': []}
    plan['candidates'] = [c for c in plan['candidates'] if c['id'] != run_id][-7:] + [candidate]
    atomic(plan_file, dumps(plan))
