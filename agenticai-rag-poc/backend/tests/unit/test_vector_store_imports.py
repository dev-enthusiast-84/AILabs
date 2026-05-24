"""Smoke-import test for langchain_chroma.Chroma."""

import inspect


def test_langchain_chroma_is_importable():
    """Assert that langchain_chroma.Chroma can be imported and is a class."""
    from langchain_chroma import Chroma  # noqa: PLC0415

    assert inspect.isclass(Chroma), "langchain_chroma.Chroma must be a class"
