import multiprocessing
import json
from pathlib import Path
import sys
import traceback


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        from marine_drift_desktop.main import run
        exit_code = run()
    except Exception:
        error = traceback.format_exc()
        if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
            output = Path(sys.argv[2])
            output.mkdir(parents=True, exist_ok=True)
            (output / 'installation-check.json').write_text(
                json.dumps({'success': False, 'error': error}, indent=2), encoding='utf-8')
        else:
            raise
        exit_code = 1
    raise SystemExit(exit_code)
