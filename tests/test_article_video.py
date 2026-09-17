import copy, json
from pathlib import Path
import pytest
from adapters.article_video import validate_recipe, build_html
from apps.server.core import Store

def recipe():
    return json.loads(Path('recipes/menza-customer-insights/menza-video-recipe.json').read_text())

def test_recipe_limits_and_unique_ids():
    r=recipe();validate_recipe(r)
    r['segments'][1]['id']=r['segments'][0]['id']
    with pytest.raises(ValueError):validate_recipe(r)
    r=recipe();r['segments'][0]['id']='../../escape'
    with pytest.raises(ValueError):validate_recipe(r)

def test_html_escapes_content_and_has_continuous_audio():
    r=recipe();r['segments'][0]['title']='<script>alert(1)</script>'
    shots=[dict(start_s=i*10,duration_s=10) for i in range(8)]
    page=build_html(r,shots,80)
    assert '<script>alert(1)' not in page
    assert '&lt;script&gt;' in page
    assert page.count('<audio ')==1
    assert 'data-duration="80"' in page

def test_article_queue_requires_valid_local_recipe(tmp_path):
    s=Store(tmp_path/'workspace');p=s.create('文章','teaching',{})['id']
    with pytest.raises(ValueError):s.create_run(p,'render','article','bad',{'recipe_path':'../../outside.json'})
    path=s.root(p)/'assets/test-video-recipe.json';path.write_text(json.dumps(recipe()))
    r=s.create_run(p,'render','article','ok',{'recipe_path':'assets/test-video-recipe.json'})
    assert r['status']=='queued'
    assert s.rows('SELECT * FROM reviews')==[]
    assert not s.gate(p,'preview',s.snapshot(p))

def test_case_film_requires_reference_mapping_and_distinct_explanation():
    r=json.loads(Path('recipes/menza-customer-insights/menza-v2-video-recipe.json').read_text())
    validate_recipe(r)
    page=build_html(r,[dict(start_s=i*10,duration_s=10) for i in range(8)],80)
    assert '仓储履约' in page and '解释假设' in page and '财务 / 专业人员' in page
    assert 'window.__timelines.main=tl' in page
    assert page.count('<audio ')==1
    del r['reference_plan']
    with pytest.raises(ValueError):validate_recipe(r)
