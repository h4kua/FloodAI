"""The chat route rejects looping model replies (no real Groq calls)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api.routes import chat

_LOOP = (
    "Selalu tanyakan kapan kamu membutuhkan, kapan dia siap, dan apa yang mereka butuh dari kamu untuk mendukung.\n\n"
    "Selalu tanyakan kapan kamu membutuhkan, kapan dia siap, dan apa yang mereka butuh dari kamu untuk mendukung."
)
_GOOD = ("Status Jakarta saat ini Waspada. Pos Cengkareng Drain di Jakarta Barat berada di Siaga 3. "
         "Pantau kabar terbaru dari RT/RW setempat.")


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_looks_degenerate_flags_a_repeated_sentence():
    assert chat._looks_degenerate(_LOOP)


@pytest.mark.parametrize("text", [_GOOD, "", "Aman. Aman.", "- Pantau air\n- Pantau air"])
def test_looks_degenerate_accepts_normal_and_short_text(text):
    assert not chat._looks_degenerate(text)


def test_complete_asks_the_fallback_model_after_a_loop(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    client = MagicMock()
    client.with_options.return_value.chat.completions.create.side_effect = [_reply(_LOOP), _reply(_GOOD)]
    with patch.object(chat, "_get_groq_client", return_value=client):
        assert chat._complete([{"role": "user", "content": "daerah mana yang rawan banjir"}]) == _GOOD
    calls = client.with_options.return_value.chat.completions.create.call_args_list
    assert [c.kwargs["model"] for c in calls] == [chat.DEFAULT_GROQ_MODEL, chat._FALLBACK_MODEL]
    assert all(c.kwargs["temperature"] == chat._TEMPERATURE for c in calls)


def test_complete_raises_when_every_model_loops():
    client = MagicMock()
    client.with_options.return_value.chat.completions.create.return_value = _reply(_LOOP)
    with patch.object(chat, "_get_groq_client", return_value=client):
        with pytest.raises(chat.DegenerateReplyError):
            chat._complete([{"role": "user", "content": "daerah mana yang rawan banjir"}])


def test_history_drops_a_looping_assistant_reply():
    history = [{"role": "user", "content": "daerah mana?"}, {"role": "assistant", "content": _LOOP},
               {"role": "assistant", "content": _GOOD}]
    assert [m["content"] for m in chat._sanitize_history(history)] == ["daerah mana?", _GOOD[:chat._MAX_HISTORY_CHARS]]


def test_top_stations_pass_the_wilayah_on():
    stations = [{"nama": "P.A. Cengkareng Drain", "lokasi": "Cengkareng", "wilayah": "Jakarta Barat", "ratio": 0.9}]
    assert chat._top_stations(stations)[0]["wilayah"] == "Jakarta Barat"
