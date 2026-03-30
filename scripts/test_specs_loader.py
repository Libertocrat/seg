"""Manual helper script to inspect parsed SEG DSL module specs."""

from pathlib import Path
from pprint import pprint

from seg.actions.specs_engine.loader import load_module_specs


def main() -> None:
    """Load core SEG DSL specs and print a readable summary."""

    specs_dir = Path("src/seg/actions/specs")

    modules = load_module_specs(specs_dir)

    print("\n=== MODULES LOADED ===\n")

    for module in modules:
        print(f"Module: {module.module}")
        print(f"Version: {module.version}")
        print(f"Binaries: {module.binaries}")
        print(f"Actions: {list(module.actions.keys())}")
        print()

    print("\n=== DETAILED MODULES ===\n")

    for module in modules:
        print(f"Module: {module.module}")
        pprint(module.model_dump(), depth=5)
        print()


if __name__ == "__main__":
    main()
