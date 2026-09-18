import json
import pytest
from fastapi.testclient import TestClient
from apps.server.core import Store, dumps
from apps.server.main import create_app
from apps.server.visual import state, review, require_approved

@pytest.fixture
def env(tmp_path):
    s=Store(tmp_path);p=s.create('视觉测试','marketing',{'visual_review_required':True})['id'];root=s.root(p)
    (root/'assets/a.mp4').write_bytes(b'test-only-video')
    (root/'documents/A.md').write_text('浅色设计')
    (root/'documents/VISUAL-PLAN.json').write_text(json.dumps({'candidates':[{'id':'a','name':'浅色','design_path':'documents/A.md','sample_path':'assets/a.mp4','evidence_paths':[]}]}))
    return s,p

def test_automation_cannot_choose_but_user_can_and_changes_invalidate(env):
    s,p=env;c=state(s,p)['candidates'][0]
    review(s,p,'a',c['fingerprint'],'automation','approve','技术检查')
    with pytest.raises(ValueError,match='视觉小样'):require_approved(s,p)
    review(s,p,'a',c['fingerprint'],'user','approve','本人选择')
    assert require_approved(s,p)['approved']=='a'
    (s.root(p)/'documents/A.md').write_text('新颜色')
    assert state(s,p)['approved'] is None
    with pytest.raises(ValueError,match='已变化'):review(s,p,'a',c['fingerprint'],'user','approve','旧页面')
    assert len(state(s,p)['history'])==2

def test_revision_supersedes_approval(env):
    s,p=env;c=state(s,p)['candidates'][0]
    review(s,p,'a',c['fingerprint'],'user','approve','')
    review(s,p,'a',c['fingerprint'],'user','revise','需要调整')
    assert state(s,p)['approved'] is None

def test_gate_missing_reference_and_path_safety(env):
    s,p=env
    with pytest.raises(ValueError,match='视觉小样'):s.create_run(p,'preview','agent','p',{})
    with pytest.raises(ValueError,match='视觉小样'):s.create_run(p,'render','render','r',{})
    (s.root(p)/'documents/REFERENCES.md').unlink()
    assert not state(s,p)['candidates'][0]['ready']
    (s.root(p)/'documents/REFERENCES.md').write_text('reference restored')
    plan=s.root(p)/'documents/VISUAL-PLAN.json';d=json.loads(plan.read_text());d['candidates'][0]['sample_path']='../outside.mp4';plan.write_text(json.dumps(d))
    assert '路径' in state(s,p)['error']

def test_sample_http_version_and_actor_validation(env):
    s,p=env;client=TestClient(create_app(s));client.get('/api/session');client.headers['x-video-request']='workbench'
    candidate=state(s,p)['candidates'][0];base=f'/api/projects/{p}/visual'
    assert client.get(base+'/a/sample',params={'fingerprint':candidate['fingerprint']}).status_code==200
    assert client.get(base+'/a/sample',params={'fingerprint':'old'}).status_code==409
    assert client.post(base+'/review',json={'candidate_id':'a','fingerprint':candidate['fingerprint'],'actor':'robot','decision':'approve'}).status_code==422
    assert client.post(base+'/review',json={'candidate_id':'a','fingerprint':candidate['fingerprint'],'actor':'automation','decision':'approve'}).json()['approved'] is None

def test_visual_only_edit_preserves_timing_but_invalidates_preview(env):
    s,p=env;before=s.snapshot(p)
    (s.root(p)/'documents/DESIGN.md').write_text('换成暖白')
    (s.root(p)/'hyperframes/index.html').write_text('新的画面')
    after=s.snapshot(p)
    assert s.dependencies('timing',before)==s.dependencies('timing',after)
    assert s.dependencies('preview',before)!=s.dependencies('preview',after)
    (s.root(p)/'documents/SCRIPT.md').write_text('修改旁白')
    assert s.dependencies('timing',after)!=s.dependencies('timing',s.snapshot(p))


def test_preview_cannot_rewrite_approved_design(env, tmp_path):
    import shutil
    from apps.server.visual import verify_work_copy
    s,p=env;c=state(s,p)['candidates'][0]
    review(s,p,'a',c['fingerprint'],'user','approve','')
    locked=require_approved(s,p)
    work=tmp_path/'copy';shutil.copytree(s.root(p),work)
    verify_work_copy(locked,work)
    (work/'documents/DESIGN.md').write_text('偷偷换色')
    with pytest.raises(ValueError,match='重新确认'):verify_work_copy(locked,work)


def test_successful_sample_registers_immutable_candidate(env):
    from apps.server.visual import register_sample
    s,p=env;work=s.root(p)
    (work/'exports/sample.mp4').write_bytes(b'rendered-test-video')
    (work/'hyperframes/index.html').write_text('composition')
    register_sample(work,'sample-run')
    candidate=next(x for x in state(s,p)['candidates'] if x['id']=='sample-run')
    assert candidate['ready'] and state(s,p)['approved'] is None
    old=(work/candidate['design_path']).read_text()
    (work/'documents/DESIGN.md').write_text('new design')
    assert (work/candidate['design_path']).read_text()==old
