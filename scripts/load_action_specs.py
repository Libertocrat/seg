"""Manual helper script to inspect parsed SEG DSL module specs."""

from pathlib import Path
from pprint import pprint

from seg.actions.specs_engine.loader import load_module_specs
from seg.actions.specs_engine.validator import validate_modules


def main() -> None:
    """Load core SEG DSL specs and print a readable summary."""

    specs_dir = Path("src/seg/actions/specs")

    try:
        modules = load_module_specs(specs_dir)
    except Exception as e:
        print(f"Failed to load module specs: {e}")
        return

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

    print("\n=== VALIDATING MODULES ===\n")
    try:
        validate_modules(modules)
        print("All modules are valid.")
    except Exception:
        print("Module validation failed")


if __name__ == "__main__":
    main()
