from finance_app import app as app_module


def test_import_app_module():
    assert app_module.app
