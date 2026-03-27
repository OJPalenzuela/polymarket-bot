def test_setup_install_and_import():
    import importlib

    m = importlib.import_module("polymarket_bot")
    from polymarket_bot import create_client

    assert m is not None
    assert callable(create_client)
