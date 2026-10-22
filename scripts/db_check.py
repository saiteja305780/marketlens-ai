import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sys

from sqlalchemy import inspect, text

from app.database.session import get_engine


def main() -> int:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            version = conn.execute(text("select version()")).scalar_one()
        tables = sorted(inspect(engine).get_table_names())
    except Exception as exc:  # report the type only; messages can contain connection details
        print(f"DB CHECK FAILED ({type(exc).__name__}). Check DATABASE_URL in .env and that PostgreSQL is running.")
        return 1
    print(f"connected to {engine.url.render_as_string(hide_password=True)}")
    print(version)
    print(f"tables: {tables or 'none yet (run: alembic upgrade head)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
