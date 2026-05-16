"""agent-voice — voice sidecar.

M4 (handsfree + PTT + TTS): connects to the daemon, subscribes to
``Topic.runs`` for TTS announcements, listens on a PTT Unix socket for
voice commands, and/or runs a continuous wake-word / VAD / STT pipeline
for hands-free operation.  Transcribed text is submitted to the daemon
as ``run_task`` RPCs.

Usage::

    agent-voice              # foreground, INFO level
    agent-voice -v           # verbose debug logging
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from pathlib import Path

from agent.client.connection import DaemonUnavailable, connect
from agent.client.errors import RpcError
from agent.ipc.constants import SOCKET_PATH
from agent.ipc.protocol import Topic
from agent.voice.audio import Recorder
from agent.voice.config import (
    TemplateConfig,
    VoiceConfig,
    load_voice_config,
)
from agent.voice.engines.piper import SubprocessPiperEngine
from agent.voice.pipeline import HandsfreePipeline
from agent.voice.ptt import PttServer
from agent.voice.redact import redact_for_tts
from agent.voice.stt import FasterWhisperEngine
from agent.voice.vad import SileroVad
from agent.voice.wakeword import WakeWordDetector

log = logging.getLogger(__name__)

_MUTED_FLAG = (
    Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    / "hyprland-agent-voice.muted"
)


def _is_muted() -> bool:
    return _MUTED_FLAG.exists()


def _render(template: str, **kw: str) -> str:
    try:
        return template.format(**kw)
    except KeyError:
        return template


def _template_text(kind: str, templates: TemplateConfig, payload: dict) -> str | None:
    if kind == "run_started":
        return _render(
            templates.run_started,
            task=str(payload.get("task", "")),
            brain=str(payload.get("brain", "")),
        )
    if kind == "run_completed":
        return templates.run_completed
    if kind == "run_errored":
        error = str(payload.get("error", ""))
        return _render(templates.run_errored, error_short=error[:80] if error else "")
    if kind == "run_aborted":
        return templates.run_aborted
    return None


async def _watch(cfg: VoiceConfig, barge_in: asyncio.Event | None = None) -> None:
    engine = SubprocessPiperEngine(voice=cfg.tts.voice, speed=cfg.tts.speed)
    backoff = 1.0

    while True:
        try:
            async with connect(SOCKET_PATH) as conn:
                await conn.subscribe(Topic.runs)
                log.info("Connected to daemon, subscribed to Topic.runs")
                backoff = 1.0

                async for topic, payload in conn.events():
                    if topic != Topic.runs:
                        continue
                    if barge_in and barge_in.is_set():
                        log.debug("Barge-in signalled — skipping TTS")
                        barge_in.clear()
                        await engine.stop()
                        continue
                    text = _template_text(payload.get("kind", ""), cfg.templates, payload)
                    if text is None:
                        continue
                    if _is_muted():
                        log.debug("Muted — skipping TTS: %s", text)
                        continue
                    safe = redact_for_tts(text, cfg.privacy.redact_patterns)
                    log.info("TTS: %s", safe)
                    await engine.say(safe)

        except DaemonUnavailable:
            log.warning("Daemon unavailable, reconnecting in %.1fs", backoff)
        except RpcError:
            log.warning("RPC error, reconnecting in %.1fs", backoff)
        except Exception:
            log.exception("Sidecar error, reconnecting in %.1fs", backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


async def _run_sidecar(verbose: bool) -> None:
    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=logging.DEBUG if verbose else logging.INFO,
    )
    cfg = load_voice_config()

    tasks: list[asyncio.Task] = []
    barge_in = asyncio.Event()

    if cfg.tts.engine:
        tasks.append(asyncio.create_task(_watch(cfg, barge_in)))
    else:
        log.warning("No TTS engine configured — skipping TTS watch")

    if cfg.ptt.enabled:
        if not cfg.stt.engine:
            log.warning("PTT enabled but no STT engine configured — skipping PTT server")
        else:
            ptt_server = await _start_ptt(cfg)
            tasks.append(asyncio.create_task(_ptt_waiter(ptt_server)))

    if cfg.handsfree.enabled:
        if not cfg.stt.engine or not cfg.wakeword.engine or not cfg.vad.engine:
            log.warning("Handsfree enabled but missing STT/wakeword/VAD engine — skipping")
        else:
            pipeline = await _start_handsfree(cfg, barge_in)
            tasks.append(asyncio.create_task(pipeline.start()))

    if not tasks:
        log.warning("No TTS, PTT, or handsfree enabled — nothing to do")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    for t in tasks:
        t.cancel()
    for t in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await t


async def _start_ptt(cfg: VoiceConfig) -> PttServer:
    recorder = Recorder(
        samplerate=16000,
        silence_threshold=0.02,
        silence_seconds=cfg.ptt.silence_seconds,
    )
    stt = FasterWhisperEngine(
        model=cfg.stt.model,
        language=cfg.stt.language,
        device=cfg.stt.device,
        compute_type=cfg.stt.compute_type,
    )
    server = PttServer(
        socket_path=Path(cfg.ptt.socket),
        stt=stt,
        recorder=recorder,
        record_timeout=cfg.ptt.record_timeout,
        brain=cfg.ptt.brain,
    )
    await server.start()
    return server


async def _ptt_waiter(server: PttServer) -> None:
    await asyncio.Event().wait()


async def _start_handsfree(cfg: VoiceConfig, barge_in: asyncio.Event) -> HandsfreePipeline:
    wakeword = WakeWordDetector(
        wake_words=cfg.wakeword.wake_words,
        sensitivity=cfg.wakeword.sensitivity,
    )
    vad = SileroVad(threshold=cfg.vad.threshold)
    stt = FasterWhisperEngine(
        model=cfg.stt.model,
        language=cfg.stt.language,
        device=cfg.stt.device,
        compute_type=cfg.stt.compute_type,
    )
    recorder = Recorder(samplerate=16000, silence_seconds=cfg.handsfree.record_timeout)
    pipeline = HandsfreePipeline(
        wakeword=wakeword,
        vad=vad,
        stt=stt,
        recorder=recorder,
        record_timeout=cfg.handsfree.record_timeout,
        brain=cfg.handsfree.brain,
        tts_stop_callback=barge_in,
    )
    return pipeline


def main() -> None:
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    asyncio.run(_run_sidecar(verbose))


if __name__ == "__main__":
    main()
