import argparse
import importlib
import os
from pkg.utils.blackboard import initialize_global_blackboard, GlobalBlackboard


def main():
    parser = argparse.ArgumentParser(description="Run project entry point")
    parser.add_argument(
        "--project",
        default="shimadzu_logic",
        help="Project package name to run",
    )
    args = parser.parse_args()

    run_dir = os.path.dirname(os.path.abspath(__file__))
    blackboard_path = os.path.join(run_dir, f"projects/{args.project}/configs/blackboard.json")
    initialize_global_blackboard(blackboard_path)

    module_name = f"projects.{args.project}.main"
    module = importlib.import_module(module_name)

    if not hasattr(module, "main"):
        raise SystemExit(f"Module '{module_name}' does not define main()")
    module.main()


if __name__ == "__main__":    
    main()
