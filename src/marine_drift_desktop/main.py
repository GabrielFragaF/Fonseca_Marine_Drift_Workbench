import sys

from .app import create_application


def run() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--gui-check":
        from .gui_check import run_gui_check

        return run_gui_check(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .runtime_check import run_check

        return run_check(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] == "--example-worker":
        from .example_worker import run_worker

        return run_worker(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] == "--simulation-worker":
        from .simulation_worker import run_worker

        return run_worker(sys.argv[2])
    if len(sys.argv) == 4 and sys.argv[1] == "--results-worker":
        from .results_worker import run_worker

        return run_worker(sys.argv[2], sys.argv[3])
    app, window = create_application()
    window.show()
    return app.exec()
