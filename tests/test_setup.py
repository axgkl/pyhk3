from pyhk3 import create, hk3s


def test_render():
    c = hk3s.render_config()
    print(c)
    assert 'master' in c


def test_import():
    assert create is not None
