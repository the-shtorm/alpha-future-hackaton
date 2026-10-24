import copy
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import MODEL_ID, Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


class FakeEncoder:
    model_id = MODEL_ID
    revision = "f" * 40
    dimension = 384

    def __init__(self):
        self.calls = []
        self.lengths = None

    def token_lengths(self, texts):
        return self.lengths or [10] * len(texts)

    def encode(self, texts):
        self.calls.append(texts)
        vectors = np.zeros((len(texts), 384), dtype=np.float32)
        vectors[:, 0] = 1
        return vectors


@pytest.fixture
def payload():
    return copy.deepcopy(json.loads((ROOT / "examples/rank-request.json").read_text(encoding="utf-8")))


@pytest.fixture
def encoder():
    return FakeEncoder()


@pytest.fixture
def settings():
    return Settings(
        environment="test", ml_internal_api_key="test-key", docs_enabled=True, admission_timeout_seconds=0.03
    )


@pytest.fixture
def application(settings, encoder):
    return create_app(settings, lambda _: encoder)


@pytest.fixture
def client(application):
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def headers():
    return {"X-Internal-API-Key": "test-key"}
