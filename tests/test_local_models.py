import math
import struct

import pytest

from nora.nora_brain import NoraBrain
from nora.nora_embeddings import CACHE_REPO, DIMENSION, MODEL_FILE, LocalEmbeddings
from nora.nora_local_ai import LocalModelMissing
from nora.nora_local_llm import LocalChatModel, strip_reasoning
from nora.nora_local_search import search_store
from nora.nora_store import NoraStore


class FakeEmbedder:
    def __init__(self):
        self.document_calls = []

    def query_embed(self, texts):
        return [[1.0] + [0.0] * (DIMENSION - 1)]

    def embed_query(self, query):
        return self.query_embed([query])[0]

    def embed_documents(self, texts):
        return self.passage_embed(texts)

    def passage_embed(self, texts, batch_size=32):
        self.document_calls.append(list(texts))
        return [
            [1.0] + [0.0] * (DIMENSION - 1)
            if "kahve" in text
            else [0.0, 1.0] + [0.0] * (DIMENSION - 2)
            for text in texts
        ]


def cached_embedding_dir(tmp_path):
    snapshot = tmp_path / CACHE_REPO / "snapshots" / "test"
    snapshot.mkdir(parents=True)
    (snapshot / MODEL_FILE).write_bytes(b"fake")
    return tmp_path


def test_embeddings_require_explicit_download_and_cache_vectors(tmp_path):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeEmbedder()

    embeddings = LocalEmbeddings(tmp_path, model_factory=factory)
    with pytest.raises(LocalModelMissing):
        embeddings.embed_query("kahve")
    assert calls == []
    cached_embedding_dir(tmp_path)
    embeddings._model_factory = factory
    vector = embeddings.embed_query("kahve")
    assert len(vector) == DIMENSION
    assert math.isclose(sum(x * x for x in vector), 1.0)
    embeddings.embed_documents(["kahve", "çay"])
    embeddings.embed_documents(["kahve", "çay"])
    assert len(embeddings._model.document_calls) == 1
    assert calls[0]["local_files_only"] is True
    embeddings.close()


def test_embedding_validation_rejects_bad_vectors(tmp_path):
    cached_embedding_dir(tmp_path)

    class Bad:
        def query_embed(self, texts):
            return [[0.0] * DIMENSION]

    embeddings = LocalEmbeddings(tmp_path, model_factory=lambda **kwargs: Bad())
    with pytest.raises(ValueError):
        embeddings.embed_query("x")
    embeddings.close()


def test_hybrid_search_uses_local_vectors_and_lexical_fallback(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    store.add_note("kahve çekirdeği")
    store.add_note("rapor")
    embedder = FakeEmbedder()
    results = search_store(store, "kahve", embedder=embedder)
    assert results[0]["text"] == "kahve çekirdeği"
    assert results[0]["method"] in {"hibrit", "anlam"}
    assert search_store(store, "kahve")[0]["method"] == "kelime"


def test_local_chat_import_and_no_cloud_fallback(tmp_path):
    class FakeLlama:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def create_chat_completion(self, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "<think>gizli düşünce</think>Merhaba senpai."
                        }
                    }
                ]
            }

    source = tmp_path / "model.gguf"
    source.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 0, 0))
    chat = LocalChatModel(tmp_path / "models", model_factory=FakeLlama)
    chat.import_model(source)
    assert chat.cached()
    brain = NoraBrain(api_key="", offline=True, local_chat=chat, chat_backend="local")
    reply = brain.chat("merhaba")
    assert reply.text == "Merhaba senpai." and not reply.error
    assert "gizli düşünce" not in reply.text
    brain.set_chat_backend("local")
    missing = LocalChatModel(tmp_path / "empty")
    brain.local_chat = missing
    reply = brain.chat("merhaba")
    assert reply.error and "Buluta geçmedim" in reply.text
    assert strip_reasoning("<think>secret") == ""
    chat.close()


def test_local_chat_rejects_unsafe_filename_and_unsupported_extension(tmp_path):
    chat = LocalChatModel(tmp_path / "models")
    with pytest.raises(ValueError):
        chat.configure("../evil.gguf")
    source = tmp_path / "model.txt"
    source.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        chat.import_model(source)
    chat.close()


def test_local_chat_streams_and_cancels_between_tokens(tmp_path):
    from nora.nora_local_llm import LocalChatCancelled

    closed = []

    class Stream:
        def __init__(self):
            self.sent = 0

        def __iter__(self):
            return self

        def __next__(self):
            self.sent += 1
            if self.sent > 3:
                raise StopIteration
            return {"choices": [{"delta": {"content": f"parca{self.sent} "}}]}

        def close(self):
            closed.append(True)

    class FakeLlama:
        def __init__(self, **kwargs):
            pass

        def create_chat_completion(self, **kwargs):
            assert kwargs["stream"] is True
            assert kwargs["max_tokens"] == 256
            return Stream()

    source = tmp_path / "model.gguf"
    source.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 0, 0))
    chat = LocalChatModel(tmp_path / "models", model_factory=FakeLlama)
    chat.import_model(source)
    chat.configure("model.gguf", context_tokens=1024, max_tokens=256)
    assert chat.chat([{"role": "user", "content": "selam"}]) == "parca1 parca2 parca3"
    assert closed == [True]
    calls = []

    def stop_after_first():
        calls.append(True)
        return len(calls) > 2

    with pytest.raises(LocalChatCancelled):
        chat.chat([{"role": "user", "content": "selam"}], should_stop=stop_after_first)
    assert closed == [True, True]
    chat.close()


def test_local_chat_context_budget_keeps_system_and_latest_user(tmp_path):
    seen = {}

    class FakeLlama:
        def __init__(self, **kwargs):
            pass

        def create_chat_completion(self, **kwargs):
            seen.update(kwargs)
            return {"choices": [{"message": {"content": "tamam"}}]}

    source = tmp_path / "model.gguf"
    source.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 0, 0))
    chat = LocalChatModel(tmp_path / "models", model_factory=FakeLlama)
    chat.import_model(source)
    chat.configure("model.gguf", context_tokens=1024, max_tokens=128)
    messages = [{"role": "system", "content": "S" * 4000}]
    messages += [
        {"role": "user", "content": f"eski {i} " + "x" * 300} for i in range(10)
    ]
    messages.append({"role": "user", "content": "en yeni soru"})
    assert chat.chat(messages) == "tamam"
    fitted = seen["messages"]
    assert fitted[0]["role"] == "system" and len(fitted[0]["content"]) < 4000
    assert fitted[-1]["content"] == "en yeni soru"
    assert all("eski 0" not in item["content"] for item in fitted)
    with pytest.raises(ValueError, match="çok uzun"):
        chat.chat([{"role": "user", "content": "x" * 5000}])
    chat.close()


def test_local_chat_cancel_does_not_fall_back_to_cloud(tmp_path):
    class Stream:
        def __iter__(self):
            yield {"choices": [{"delta": {"content": "ilk"}}]}
            yield {"choices": [{"delta": {"content": "ikinci"}}]}

        def close(self):
            pass

    class FakeLlama:
        def __init__(self, **kwargs):
            pass

        def create_chat_completion(self, **kwargs):
            return Stream()

    source = tmp_path / "model.gguf"
    source.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 0, 0))
    chat = LocalChatModel(tmp_path / "models", model_factory=FakeLlama)
    chat.import_model(source)
    brain = NoraBrain(api_key="", offline=True, local_chat=chat, chat_backend="local")
    calls = []

    def stop():
        calls.append(True)
        return len(calls) > 2

    reply = brain.chat("selam", should_stop=stop)
    assert reply.error and "Buluta geçmedim" in reply.text
    assert len(brain.history) == 1
    chat.close()
