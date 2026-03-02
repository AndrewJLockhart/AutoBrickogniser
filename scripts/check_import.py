import sys
import traceback
from pathlib import Path


def main():
    # Ensure project root is on sys.path so `import app` succeeds when run from other cwd
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    try:
        import app
        print("IMPORT_OK")
    except Exception:
        print("IMPORT_FAIL")
        traceback.print_exc()
        sys.exit(2)


if __name__ == '__main__':
    main()
