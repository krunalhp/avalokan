from fractions import Fraction
from uuid import uuid4

import av
import numpy as np
import psycopg
import pytest
from psycopg import sql

from avalokan.settings import Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Real PostgreSQL, disposable schema only; never clear the workbench DB."""
    original = Settings()
    schema = "test_" + uuid4().hex
    try:
        connection = psycopg.connect(original.dsn, autocommit=True)
    except psycopg.OperationalError:
        pytest.fail("PostgreSQL required: run .agents/setup and amp orb services ensure")
    connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    monkeypatch.setenv(
        "AVALOKAN_DATABASE_URL", original.dsn + f" options='-c search_path={schema}'"
    )
    monkeypatch.delenv("AVALOKAN_WORKER", raising=False)
    monkeypatch.delenv("AVALOKAN_ALLOWED_ACTIVITIES", raising=False)
    configured = Settings(data=tmp_path / "app", demo=True)
    configured.model.parent.mkdir(parents=True)
    if original.model.exists():
        configured.model.symlink_to(original.model.resolve())
    yield configured
    connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    connection.close()


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "irregular.mp4"
    with av.open(str(path), "w") as out:
        stream = out.add_stream("libx264", rate=10)
        stream.width, stream.height = 160, 96
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 1000)
        stream.codec_context.time_base = Fraction(1, 1000)
        for pts in [0, 500, 1000, 1500, 2000, 4500, 5000]:
            frame = av.VideoFrame.from_ndarray(
                np.zeros((96, 160, 3), dtype=np.uint8), format="rgb24"
            )
            frame.pts, frame.time_base = pts, Fraction(1, 1000)
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return path
