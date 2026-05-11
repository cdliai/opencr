from pathlib import Path


def test_local_requirements_include_deepseek_remote_code_dependencies():
    requirements = (Path(__file__).parents[1] / "requirements-local.txt").read_text(
        encoding="utf-8"
    )
    assert "easydict" in requirements
