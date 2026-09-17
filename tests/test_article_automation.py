import json
from scripts.run_article_pipeline import input_fingerprint
from apps.server.core import Store
from worker.main import Worker
import fcntl


def test_article_dependencies_invalidate_recipe(tmp_path):
    source = tmp_path / 'article.md'
    source.write_text('source')
    (tmp_path / 'images').mkdir()
    image = tmp_path / 'images/a.png'
    image.write_bytes(b'original')
    recipe = tmp_path / 'recipe.json'
    recipe.write_text(json.dumps({'source': str(source), 'segments': []}))
    initial = input_fingerprint(recipe)
    assert initial == input_fingerprint(recipe)
    image.write_bytes(b'changed')
    assert initial != input_fingerprint(recipe)
    image.write_bytes(b'original')
    source.write_text('changed source')
    assert initial != input_fingerprint(recipe)


def test_automation_does_not_create_human_review(tmp_path):
    s = Store(tmp_path)
    p = s.create('article', 'teaching', {'execution_mode': 'delegated_automation'})
    with s.conn() as c:
        s.event(c, p['id'], None, 'automation.stage', {'stage':'delivery','status':'completed','details':'technical only'})
    s.export_status(p['id'])
    status = (s.root(p['id']) / 'documents/STATUS.md').read_text()
    assert 'delivery · completed' in status
    assert s.rows('SELECT * FROM reviews') == []
    assert s.rows('SELECT * FROM runs') == []


def test_worker_yields_to_article_runner(tmp_path):
    s = Store(tmp_path)
    with (tmp_path / 'article-pipeline.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert Worker(s).claim() is None


def test_qa_last_frame_uses_video_duration(tmp_path):
    import shutil, subprocess, pytest
    from adapters.tools import media_qa, process
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg missing')
    video = tmp_path / 'padded.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=0.7','-f','lavfi','-i','sine=frequency=440:duration=1.1','-c:v','libx264','-c:a','aac',str(video)],check=True)
    report = media_qa(video,tmp_path/'qa',{'width':320,'height':180,'fps':30,'video_codec':'h264'},lambda args,log:process(args,tmp_path,log))
    assert report['frames'][-1]['at_s'] < 0.7
    assert (tmp_path/'qa/frame-2.jpg').exists()
