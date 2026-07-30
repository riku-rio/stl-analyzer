"""Module entry point for ``python -m stl_analyzer``."""

from stl_analyzer.cli import app


def main() -> None:
    """Run the command-line application."""
    app(prog_name="stl-analyzer")


if __name__ == "__main__":
    main()
