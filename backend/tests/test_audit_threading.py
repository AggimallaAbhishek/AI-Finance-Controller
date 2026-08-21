from concurrent.futures import ThreadPoolExecutor

import audit


def test_connection_usable_from_a_different_thread_than_it_was_created_on(tmp_path):
    """Regression: FastAPI's threadpool doesn't guarantee a dependency
    generator's yield and the route handler's body run on the same OS
    thread — under concurrent requests, audit.connect()'s connection could
    be created on one thread and used on another, and plain sqlite3
    connections reject that by default. Only surfaced under real
    concurrent load (Phase 10's frontend added the first concurrent
    requests); every previous manual/automated test was sequential."""
    conn = audit.connect(tmp_path / "test.db")

    def use_from_other_thread():
        return conn.execute("SELECT 1").fetchone()[0]

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(use_from_other_thread).result()

    assert result == 1
    conn.close()
