"""Shared pytest configuration and fixtures."""


def pytest_addoption(parser):
    parser.addoption("--run-e2e", action="store_true", default=False,
                     help="Run end-to-end tests with live LLM API")


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring live API")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-e2e", default=False):
        import pytest
        skip_e2e = pytest.mark.skip(reason="Need --run-e2e option to run")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)
