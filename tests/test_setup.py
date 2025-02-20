from pyhk3 import create


def test_import():
    assert create is not None


def test_render():
    c = create.hk3s.render_config()
    print(c)
    assert 'master' in c
