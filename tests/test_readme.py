"""The README keeps up with the code: it names every MCP toolset, the default toolsets and every setting."""

from pathlib import Path

from test_junkie.decorators import Suite, test

from test_junkie_tcms.api.operations import TOOLSETS
from test_junkie_tcms.settings import Settings

README = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")


@Suite()
class Readme:
    @test()
    def names_every_toolset(self):
        missing = [name for name in TOOLSETS if f"| `{name}` |" not in README]
        assert not missing, f"README's toolset table lacks {missing}"

    @test()
    def states_the_default_toolsets(self):
        default = Settings.model_fields["mcp_default_toolsets"].default
        assert f"`{default}`" in README, f"README doesn't state the default toolsets {default!r}"
        assert "?toolsets=" in README

    @test()
    def lists_every_setting(self):
        missing = [
            f"TJ_TCMS_{field.upper()}"
            for field in Settings.model_fields
            if f"`TJ_TCMS_{field.upper()}`" not in README
        ]
        assert not missing, f"README's settings table lacks {missing}"
