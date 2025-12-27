# ui/chat_store.py
from __future__ import annotations
import os
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, Any

DEFAULT_CHAT_DIR = os.path.join("ui", "chats")
DEFAULT_CHAT_FILE = os.path.join(DEFAULT_CHAT_DIR, "temp.json")


class ChatStore:
    """
    Bufor konwersacji w postaci pliku JSON.
    Każdy rekord to dict z polami:
      - id (uuid str)
      - timestamp (ISO8601 timezone-aware)
      - role ('user' / 'bot')
      - outgoing (bool)
      - text (str)
      - extra (optional dict)
    """

    def __init__(self, path: Optional[str] = None, clear_on_start: bool = True):
        self.path = path or DEFAULT_CHAT_FILE
        self.dir = os.path.dirname(self.path) or "."
        self._lock = threading.Lock()
        os.makedirs(self.dir, exist_ok=True)
        if clear_on_start:
            self._clear_file()
        else:
            if not os.path.exists(self.path):
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False)

    def _clear_file(self) -> None:
        with self._lock:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    # ----------------------
    # Serializacja specjalnych obiektów (ChatCompletion-like)
    # ----------------------
    def _serialize_choice(self, choice: Any) -> dict:
        """
        Serializuje obiekt choice (może być dict lub obiekt).
        Zwraca dict z najszerszym zakresem pól z message (content, role, refusal, annotations,
        function_call, tool_calls, reasoning, reasoning_details) oraz finish_reason, index, logprobs.
        """
        # dict-friendly path
        if isinstance(choice, dict):
            msg = choice.get("message") or {}
            # message może być dict lub obiekt wewnętrzny -> normalizuj
            if isinstance(msg, dict):
                message_out = {
                    "content": msg.get("content"),
                    "role": msg.get("role"),
                    "refusal": msg.get("refusal"),
                    "annotations": msg.get("annotations"),
                    "function_call": msg.get("function_call"),
                    "tool_calls": msg.get("tool_calls"),
                    "reasoning": msg.get("reasoning"),
                    "reasoning_details": msg.get("reasoning_details"),
                }
            else:
                # nieznany format -> rzutuj na string
                message_out = {"content": str(msg)}

            return {
                "finish_reason": choice.get("finish_reason"),
                "index": choice.get("index"),
                "logprobs": choice.get("logprobs"),
                "message": message_out,
                "native_finish_reason": choice.get("native_finish_reason"),
            }

        # obiektowy path
        out = {}
        try:
            out["finish_reason"] = getattr(choice, "finish_reason", None)
            out["index"] = getattr(choice, "index", None)
            out["logprobs"] = getattr(choice, "logprobs", None)
            # message
            msg = getattr(choice, "message", None)
            if msg is not None:
                msg_content = getattr(msg, "content", None)
                msg_role = getattr(msg, "role", None)
                msg_refusal = getattr(msg, "refusal", None)
                msg_annotations = getattr(msg, "annotations", None)
                msg_function_call = getattr(msg, "function_call", None)
                msg_tool_calls = getattr(msg, "tool_calls", None)
                msg_reasoning = getattr(msg, "reasoning", None)
                msg_reasoning_details = getattr(msg, "reasoning_details", None)
                out["message"] = {
                    "content": msg_content,
                    "role": msg_role,
                    "refusal": msg_refusal,
                    "annotations": msg_annotations,
                    "function_call": msg_function_call,
                    "tool_calls": msg_tool_calls,
                    "reasoning": msg_reasoning,
                    "reasoning_details": msg_reasoning_details,
                }
            else:
                out["message"] = None
            out["native_finish_reason"] = getattr(choice, "native_finish_reason", None)
        except Exception:
            return {"repr": str(choice)}
        return out

    def _serialize_usage(self, usage: Any) -> dict:
        """
        Serializuje pole usage (może być obiektem lub dict).
        Staramy się wydobyć:
          - completion_tokens, prompt_tokens, total_tokens
          - completion_tokens_details (np. audio_tokens, accepted_prediction_tokens, ...)
          - prompt_tokens_details (np. audio_tokens, cached_tokens, ...)
        """
        if usage is None:
            return {}
        if isinstance(usage, dict):
            # zwróć dict, ale upewnij się, że zawiera kluczowe pola
            out = dict(usage)
            # nie zmieniamy struktury głębiej niż konieczne
            return out

        # obiektowy usage - próbuj czytać pola
        try:
            out = {
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
            # szczegóły
            comp_details = getattr(usage, "completion_tokens_details", None)
            prompt_details = getattr(usage, "prompt_tokens_details", None)
            # jeśli istnieją, przekształć na proste dicty
            if comp_details is not None:
                if isinstance(comp_details, dict):
                    out["completion_tokens_details"] = comp_details
                else:
                    # spróbuj zebrać typowe pola
                    out["completion_tokens_details"] = {
                        "accepted_prediction_tokens": getattr(comp_details, "accepted_prediction_tokens", None),
                        "audio_tokens": getattr(comp_details, "audio_tokens", None),
                        "reasoning_tokens": getattr(comp_details, "reasoning_tokens", None),
                    }
            if prompt_details is not None:
                if isinstance(prompt_details, dict):
                    out["prompt_tokens_details"] = prompt_details
                else:
                    out["prompt_tokens_details"] = {
                        "audio_tokens": getattr(prompt_details, "audio_tokens", None),
                        "cached_tokens": getattr(prompt_details, "cached_tokens", None),
                    }
            return out
        except Exception:
            return {"repr": str(usage)}

    def _serialize_chatcompletion(self, obj: Any) -> dict:
        """
        Próbuje wyciągnąć istotne pola z obiektu typu ChatCompletion (lub podobnego).
        Zwraca dict z polami: id, choices (lista z message.content i reasoning_details), created, model, object,
        service_tier, system_fingerprint, usage (z tokenami i szczegółami), provider, time.
        """
        if isinstance(obj, dict):
            out = dict(obj)
            # normalize choices
            if "choices" in out and isinstance(out["choices"], list):
                out["choices"] = [self._serialize_choice(c) for c in out["choices"]]
            if "usage" in out:
                out["usage"] = self._serialize_usage(out.get("usage"))
            return out

        out = {}
        try:
            out["id"] = getattr(obj, "id", None)
            # choices
            raw_choices = getattr(obj, "choices", None)
            if raw_choices is not None:
                out["choices"] = [self._serialize_choice(c) for c in raw_choices]
            # podstawowe
            out["created"] = getattr(obj, "created", None)
            out["model"] = getattr(obj, "model", None)
            out["object"] = getattr(obj, "object", None)
            out["service_tier"] = getattr(obj, "service_tier", None)
            out["system_fingerprint"] = getattr(obj, "system_fingerprint", None)
            out["provider"] = getattr(obj, "provider", None)
            out["time"] = getattr(obj, "time", None)
            # usage
            out["usage"] = self._serialize_usage(getattr(obj, "usage", None))
        except Exception:
            return {"repr": str(obj)}
        return out

    # ----------------------
    # Bezpieczna rekurencyjna konwersja
    # ----------------------
    def _make_json_safe(self, value: Any) -> Any:
        """
        Rekurencyjnie konwertuje wartość na postać bezpieczną do zapisania w JSON.
        - Typy proste (str, int, float, bool, None) są zostawiane
        - Dicty/listy są przetwarzane rekurencyjnie
        - Obiekty typu ChatCompletion (lub podobne) są specjalnie serializowane
        - Inne obiekty: próbujemy to_dict/__dict__ lub cast do str()
        """
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, dict):
            return {str(k): self._make_json_safe(v) for k, v in value.items()}

        if isinstance(value, (list, tuple, set)):
            return [self._make_json_safe(v) for v in value]

        # heurystyka: obiekt z choices lub z model+created
        if hasattr(value, "choices") or (hasattr(value, "model") and hasattr(value, "created")):
            try:
                return self._make_json_safe(self._serialize_chatcompletion(value))
            except Exception:
                pass

        if hasattr(value, "to_dict") and callable(value.to_dict):
            try:
                return self._make_json_safe(value.to_dict())
            except Exception:
                pass
        if hasattr(value, "__dict__"):
            try:
                return self._make_json_safe(vars(value))
            except Exception:
                pass

        return str(value)

    # ----------------------
    # Normalizacja pola extra (parsowanie content jeśli string JSON)
    # ----------------------
    def _normalize_extra(self, extra: Any) -> Any:
        """
        Ujednolica strukturę extra:
          - jeśli extra jest dict -> rekurencyjnie parsuje
          - próbuje sparsować pola 'content' będące stringiem JSON -> dict
          - jeśli raw_json jest obiektem -> serializuje go dedykowaną funkcją
        """
        if extra is None:
            return None
        if not isinstance(extra, dict):
            return self._make_json_safe(extra)

        out = {}
        for k, v in extra.items():
            if k == "raw_json" and (not isinstance(v, (dict, list))):
                try:
                    out[k] = self._make_json_safe(self._serialize_chatcompletion(v))
                    continue
                except Exception:
                    out[k] = self._make_json_safe(v)
                    continue

            if k == "content" and isinstance(v, str):
                s = v.strip()
                if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                    try:
                        parsed = json.loads(s)
                        out[k] = self._make_json_safe(parsed)
                        out["content_raw"] = v
                        continue
                    except Exception:
                        out[k] = v
                        continue

            if isinstance(v, dict):
                out[k] = self._normalize_extra(v)
            elif isinstance(v, (list, tuple, set)):
                out[k] = [self._normalize_extra(x) if isinstance(x, dict) else self._make_json_safe(x) for x in v]
            else:
                out[k] = self._make_json_safe(v)
        return out

    # ----------------------
    # Główna metoda do dopisywania wiadomości
    # ----------------------
    def append_message(self, role: str, text: str, outgoing: bool = False, extra: Optional[dict] = None, thought: Optional[str] = None) -> dict:
        # Tworzymy podstawowy rekord wiadomości
        rec = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "outgoing": bool(outgoing),
            "text": text,
            "thought": thought, # Nowe pole: przechowuje proces myślowy lub statusy pośrednie
        }

        if extra is not None:
            # Normalizacja i zabezpieczenie danych JSON przed zapisem
            try:
                norm = self._normalize_extra(extra)
                rec["extra"] = self._make_json_safe(norm)
            except Exception:
                rec["extra"] = self._make_json_safe(extra)

        with self._lock:
            # Zapis do pliku z użyciem blokady (lock)
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = []

            data.append(rec)
            # Bezpieczny zapis do pliku tymczasowego
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)

        return rec

    def update_message(self, message_id: str, text: Optional[str] = None, thought: Optional[str] = None,
                       extra: Optional[dict] = None):
        """Aktualizuje istniejącą wiadomość o podanym ID."""
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return None

            found = False
            for rec in data:
                if rec.get("id") == message_id:
                    if text is not None: rec["text"] = text
                    if thought is not None: rec["thought"] = thought
                    if extra is not None:
                        # Łączymy stare extra z nowym
                        existing_extra = rec.get("extra", {})
                        norm_new = self._normalize_extra(extra)
                        existing_extra.update(self._make_json_safe(norm_new))
                        rec["extra"] = existing_extra
                    found = True
                    break

            if found:
                tmp_path = self.path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.path)

            return found
    # ----------------------
    # Wczytywanie
    # ----------------------
    def load_all(self) -> list:
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        return []
                    return data
            except Exception:
                return []
