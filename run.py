import argparse
import importlib
from pkg.utils.blackboard import initialize_global_blackboard, GlobalBlackboard


def main():
    parser = argparse.ArgumentParser(description="Run project entry point")
    parser.add_argument(
        "--project",
        default="shimadzu_logic",
        help="Project package name to run",
    )
    args = parser.parse_args()

    initialize_global_blackboard(
        f"projects/{args.project}/configs/blackboard.json"
    )    

    module_name = f"projects.{args.project}.main"
    module = importlib.import_module(module_name)

    if not hasattr(module, "main"):
        raise SystemExit(f"Module '{module_name}' does not define main()")
    module.main()


if __name__ == "__main__":    
    main()

