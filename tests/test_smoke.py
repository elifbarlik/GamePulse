def test_scaffold_importable():
    import fastapi
    import pandas
    import pydantic

    assert pydantic.VERSION and pandas.__version__ and fastapi.__version__
