#!/usr/bin/env python3
"""Soshyant voice chat (English-only): local LLM + Kokoro TTS.

Every answer the model generates is spoken aloud. Reasoning is shown as a
ticker (not spoken), code blocks are printed but not read.
Non-English text is shown on screen only.
"""
import argparse
import atexit
import os
import re
import subprocess
import sys
import threading
import time

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(ROOT, "models",
                     "Ternary-Bonsai-2-27B-Abliterated-PTQ1_0.gguf")
SERVER_EXE = os.path.join(ROOT, "bin", "cuda", "llama-server.exe")
TTS_ONNX = os.path.join(ROOT, "tts", "kokoro-fp32.onnx")
TTS_VOICES = os.path.join(ROOT, "tts", "voices-v1.0.bin")
WHISPER_EN = os.path.join(ROOT, "tts", "whisper-base-en")
HOST = "127.0.0.1"
PORT = 8081
API = f"http://{HOST}:{PORT}/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a voice assistant; your replies are read aloud by text-to-speech. "
    "Answer in flowing conversational prose with short to medium sentences. "
    "Do not use markdown formatting, headings, bullet or numbered lists, tables, "
    "or code unless the user explicitly asks for code. Prefer plain words over "
    "symbols (say 'about twenty percent', not '~20%')."
)
SHOW_SPEECH = False

# ---------------------------------------------------------------- server mgmt

def server_up() -> bool:
    try:
        return requests.get(f"http://{HOST}:{PORT}/health", timeout=2).ok
    except requests.RequestException:
        return False


def ensure_server() -> subprocess.Popen | None:
    """Start llama-server if it isn't running; return Popen (owned by us) or None."""
    if server_up():
        return None
    print("[tts] starting LLM server (first load ~10-30 s)...")
    proc = subprocess.Popen([
        SERVER_EXE, "-m", MODEL, "--host", HOST, "--port", str(PORT),
        "-ngl", "99", "-fa", "on", "-c", "16384",
        "--temp", "1.0", "--top-p", "0.95", "--top-k", "20", "--jinja",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        if server_up():
            return proc
        if proc.poll() is not None:
            sys.exit("[tts] llama-server exited during startup")
        time.sleep(1)
    proc.terminate()
    sys.exit("[tts] server did not become healthy in 120 s")


# ---------------------------------------------------------------- speech text

FENCE = re.compile(r"```")

# Ordered regex passes turning markdown-flavored LLM output into speakable prose
MD_IMAGES = re.compile(r"!\[[^\]]*\]\([^)]*\)")          # ![alt](url) -> gone
MD_LINKS = re.compile(r"\[([^\]]*)\]\([^)]*\)")          # [text](url) -> text
MD_INLINE_CODE = re.compile(r"`[^`\n]*`")                # `x = 1` -> gone
MD_LINE_PREFIX = re.compile(                             # line-start markers
    r"^\s{0,3}(?:#{1,6}\s*|[-*+•]\s+|\d+[.)]\s+|>\s?)", re.MULTILINE)
MD_TABLE_ROW = re.compile(r"^[^\n|]*\|[^\n|]*\|.*$", re.MULTILINE)  # rows w/ pipes
MD_FENCE_LEFTOVER = re.compile(r"```[^\n]*")
# Symbols spoken as words (before the generic noise strip)
SYMBOL_WORDS = [
    (r"(?<=\d)\s*[–—~-]\s*(?=\d)", " to "),   # 30-60 -> 30 to 60
    (r"\s*[–—]\s*", ", "),                    # em-dash -> pause
    (r"\s*<=\s*", " less than or equal to "), (r"\s*>=\s*", " greater than or equal to "),
    (r"\s*==\s*", " equals "), (r"\s*!=\s*", " is not equal to "),
    (r"\s*=>\s*", " leads to "), (r"\s*->\s*", " to "), (r"\s*→\s*", " to "),
    (r"\s*⇒\s*", " leads to "), (r"\s*≤\s*", " less than or equal to "),
    (r"\s*≥\s*", " greater than or equal to "), (r"\s*±\s*", " plus or minus "),
    (r"(?<=\d)\s*[x×]\s*(?=\d)", " times "), (r"\s*·\s*", " times "),
    (r"\s*&\s*", " and "), (r"\s*@\s*", " at "), (r"\s*~\s*", " about "),
    (r"\s*<\s*", " less than "), (r"\s*>\s*", " greater than "),
    (r"\s*%\s*", " percent "), (r"\s*=\s*", " equals "),
]
MD_NOISE_CHARS = re.compile(r"[#*`~^|_<>{}\[\]\\$+=]")


def _clean(text: str) -> str:
    """Shared markdown/symbol cleaning."""
    t = text
    t = MD_FENCE_LEFTOVER.sub(" ", t)
    t = re.sub(r"\s*\[\d+\]", "", t)   # citation markers like [1] stay silent
    t = MD_IMAGES.sub(" ", t)
    t = MD_LINKS.sub(r" \1 ", t)
    t = MD_INLINE_CODE.sub(" ", t)
    t = MD_TABLE_ROW.sub(" ", t)
    t = MD_LINE_PREFIX.sub("", t)
    for pat, word in SYMBOL_WORDS:
        t = re.sub(pat, word, t)
    t = MD_NOISE_CHARS.sub(" ", t)
    # quotes: announce nothing. Drop double quotes outright; drop single
    # quotes only when they delimit ('word'), keeping apostrophes (don't, boys')
    t = re.sub(r"[“”\"]", "", t)
    t = re.sub(r"(?<!\w)'|'(?!\w)", "", t)
    t = re.sub(r"[‘’]", "'", t)
    # keep normal punctuation pauses, drop leftover brackets/parens' twins
    t = re.sub(r"[()\[\]{}]", ",", t)
    t = re.sub(r",\s*,+", ",", t)
    t = re.sub(r"\s+", " ", t).strip(" ,;")
    return t


def speakable(text: str) -> str:
    """English speech text; non-English scripts come back empty (silent)."""
    t = _clean(text)
    if not t:
        return ""
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isascii() for c in letters) / len(letters) < 0.7:
        return ""      # no English voice can read non-Latin scripts
    if t and t[-1] not in ".!?:;":
        t += "."       # closed prosody: sentence-final intonation
    return t


class SpeechSplitter:
    """Accumulates streamed text, emits sentence-sized chunks for TTS."""

    def __init__(self, min_len=40, max_len=350):
        self.buf = ""
        self.in_code = False
        self.min_len = min_len
        self.max_len = max_len

    def feed(self, delta: str) -> list[str]:
        out = []
        self.buf += delta
        while True:
            if FENCE.search(self.buf):
                pre, _, rest = FENCE.partition(self.buf)
                if pre.strip() and not self.in_code:
                    out.append(pre)
                self.buf = rest
                self.in_code = not self.in_code
                continue
            if self.in_code:
                if "\n" in self.buf:  # swallow code lines
                    self.buf = self.buf.split("\n", 1)[1]
                    continue
                return out
            # first sentence boundary far enough into the buffer; shorter
            # sentences stay glued to the one that crosses min_len
            m = next((m for m in re.finditer(r"[.!?](?=\s|$)", self.buf)
                      if m.end() >= self.min_len), None)
            if m:
                out.append(self.buf[: m.end()])
                self.buf = self.buf[m.end():]
                continue
            if len(self.buf) > self.max_len:  # safety split on long run-ons
                cut = self.buf.rfind(",", 0, self.max_len)
                cut = cut if cut > self.min_len else self.max_len
                out.append(self.buf[:cut])
                self.buf = self.buf[cut:].lstrip(", ")
                continue
            return out

    def flush(self) -> list[str]:
        rest, self.buf = self.buf, ""
        if rest.strip() and not self.in_code:
            out = [rest]
        else:
            out = []
        self.in_code = False
        return out


# ---------------------------------------------------------------- audio path

class Speaker(threading.Thread):
    """Synthesizes queued sentences with Kokoro and plays them sequentially."""

    def __init__(self, kokoro, voice, speed, enabled=True):
        super().__init__(daemon=True)
        self.kokoro = kokoro
        self.voice = voice
        self.speed = speed
        self.enabled = enabled
        self.text_q = []
        self.playing = False
        self.lock = threading.Condition()
        self.stop_flag = False

    def say(self, text: str):
        t = speakable(text)
        if not t:
            return
        if SHOW_SPEECH:
            print(f"\n[speech] {t}")
        if not self.enabled:
            return
        with self.lock:
            self.text_q.append(t)
            self.lock.notify_all()

    def interrupt(self):
        """Drop queued sentences and stop current playback (new user turn)."""
        with self.lock:
            self.text_q.clear()
        import sounddevice as sd
        try:
            sd.stop()
        except Exception:
            pass

    def shutdown(self):
        with self.lock:
            self.stop_flag = True
            self.lock.notify_all()

    def wait_done(self, timeout=300):
        """Block until the queue is empty and playback has finished."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                idle = not self.text_q and not self.playing
            if idle:
                return True
            time.sleep(0.1)
        return False

    def run(self):
        import sounddevice as sd
        while True:
            with self.lock:
                while not self.text_q and not self.stop_flag:
                    self.lock.wait()
                if self.stop_flag:
                    return
                text = self.text_q.pop(0)
            try:
                audio, sr = self.kokoro.create(
                    text, voice=self.voice, speed=self.speed, lang="en-us")
                if audio is not None and len(audio):
                    self.playing = True
                    sd.play(audio, sr)
                    sd.wait()
                    self.playing = False
            except Exception as e:
                print(f"\n[tts] skipped a sentence ({e.__class__.__name__}: {e})")
                self.playing = False


# ---------------------------------------------------------------- chat loop

def stream_answer(messages, speaker, max_tokens, model_name):
    payload = {"messages": messages, "stream": True,
               "max_tokens": max_tokens, "temperature": 0.7}
    splitter = SpeechSplitter()
    think_chars = 0
    full = []
    with requests.post(API, json=payload, stream=True, timeout=600) as r:
        r.raise_for_status()
        r.encoding = "utf-8"  # SSE lacks a charset header; avoid latin-1 mojibake
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            data = raw[6:]
            if data == "[DONE]":
                break
            import json
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = chunk["choices"][0].get("delta", {})
            think = delta.get("reasoning_content") or ""
            if think:
                think_chars += len(think)
                print(f"\r    \x1b[2m…thinking ({think_chars} chars)\x1b[0m",
                      end="", flush=True)
            piece = delta.get("content") or ""
            if piece:
                print(f"\r{' ' * 40}\r{piece}", end="", flush=True)
                full.append(piece)
                for sent in splitter.feed(piece):
                    speaker.say(sent)
    print()
    for sent in splitter.flush():
        speaker.say(sent)
    if "".join(full).strip():
        messages.append({"role": "assistant", "content": "".join(full)})


def main():
    global PORT, API, SHOW_SPEECH
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--voice", default="af_heart",
                    help="Kokoro voice, e.g. af_heart af_bella am_adam bm_george")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--once", metavar="PROMPT", help="ask one question and exit")
    ap.add_argument("--mute", action="store_true", help="print answers, no audio")
    ap.add_argument("--raw-prompt", action="store_true",
                    help="don't inject the voice-friendly system prompt")
    ap.add_argument("--show-speech", action="store_true",
                    help="print the exact text sent to TTS")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()
    SHOW_SPEECH = args.show_speech
    PORT, API = args.port, f"http://{HOST}:{PORT}/v1/chat/completions"

    from kokoro_onnx import Kokoro
    print("[tts] loading Kokoro (CPU)...")
    kokoro = Kokoro(TTS_ONNX, TTS_VOICES)
    if args.list_voices:
        names = [v for v in kokoro.get_voices()
                 if v.startswith(("af_", "am_", "bf_", "bm_"))]
        print("English voices:", " ".join(sorted(names)))
        return

    server = ensure_server()
    if server is not None:
        atexit.register(server.terminate)

    speaker = Speaker(kokoro, args.voice, args.speed, enabled=not args.mute)
    speaker.start()

    if args.once:
        print(f"\x1b[1massistant>\x1b[0m ", end="", flush=True)
        stream_answer([{"role": "user", "content": args.once}],
                      speaker, args.max_tokens, "llm")
        speaker.wait_done()
        speaker.shutdown()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        return

    print(f"[tts] voice chat ready — model speaks as '{args.voice}'. "
          "Commands: /exit  /interrupt  /voice <name>  /mute")

    history = [] if args.raw_prompt else [{"role": "system",
                                           "content": SYSTEM_PROMPT}]
    try:
        while True:
            try:
                user = input("\n\x1b[1myou>\x1b[0m ").strip()
            except EOFError:
                break
            if not user:
                continue
            if user == "/exit":
                break
            if user == "/mute":
                speaker.enabled = not speaker.enabled
                print(f"[tts] audio {'on' if speaker.enabled else 'muted'}")
                continue
            if user.startswith("/voice "):
                speaker.voice = user.split(None, 1)[1].strip()
                print(f"[tts] voice set to {speaker.voice}")
                continue
            if user == "/interrupt":
                speaker.interrupt()
                continue
            speaker.interrupt()  # barge-in on the old answer
            history.append({"role": "user", "content": user})
            print("\x1b[1massistant>\x1b[0m ", end="", flush=True)
            stream_answer(history, speaker, args.max_tokens, "llm")
    except KeyboardInterrupt:
        pass
    finally:
        speaker.shutdown()
        import sounddevice as sd
        try:
            sd.stop()
        except Exception:
            pass
        print("\n[tts] bye")


if __name__ == "__main__":
    main()
