from __future__ import annotations

import asyncio
import logging
import time
from enum import StrEnum, auto

import numpy as np

from agent.client.connection import DaemonUnavailable, connect
from agent.client.errors import RpcError
from agent.ipc.constants import SOCKET_PATH
from agent.ipc.protocol import RpcMethod
from agent.voice.audio import Recorder
from agent.voice.ring_buffer import RingBuffer
from agent.voice.stt import FasterWhisperEngine
from agent.voice.vad import SileroVad
from agent.voice.wakeword import WakeWordDetector

log = logging.getLogger(__name__)

BLOCK_DURATION = 0.08  # 80 ms per chunk


class PipelineState(StrEnum):
    LISTENING = auto()
    WAKING = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    SUBMITTING = auto()


class HandsfreePipeline:
    """Continuous wake-word → VAD → STT → submit pipeline.

    Runs on an async event loop with audio capture on a background
    thread.  Supports barge-in: if the TTS engine is speaking and the
    wake word fires, the pipeline signals the engine to stop.

    Wake word detection uses ASR spotting: when VAD detects speech,
    the pipeline transcribes the first ~1.5 s segment and checks for
    the configured wake word.  This avoids extra ML dependencies.
    """

    def __init__(
        self,
        wakeword: WakeWordDetector,
        vad: SileroVad,
        stt: FasterWhisperEngine,
        recorder: Recorder,
        record_timeout: float = 10.0,
        brain: str = "auto",
        samplerate: int = 16000,
        ring_duration: float = 2.0,
        tts_stop_callback: asyncio.Event | None = None,
    ) -> None:
        self._wakeword = wakeword
        self._vad = vad
        self._stt = stt
        self._recorder = recorder
        self._record_timeout = record_timeout
        self._brain = brain
        self._samplerate = samplerate
        self._ring = RingBuffer(samplerate, ring_duration)
        self._tts_stop = tts_stop_callback or asyncio.Event()

        self._state = PipelineState.LISTENING
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.AbstractEventLoop | None = None
        self._recording_frames: list[np.ndarray] = []
        self._speech_end_time: float = 0.0
        self._wake_chunk: np.ndarray | None = None
        self._silence_blocks: int = 0

    @property
    def state(self) -> PipelineState:
        return self._state

    async def start(self) -> None:
        log.info("Handsfree pipeline starting — listening for wake word")
        self._loop_task = asyncio.get_running_loop()
        self._state = PipelineState.LISTENING
        self._recorder.start_stream(
            on_chunk=self._on_chunk,
            ring_buffer=self._ring,
        )
        while not self._stop_event.is_set():
            await asyncio.sleep(0.1)
        log.info("Handsfree pipeline stopped")

    async def stop(self) -> None:
        self._stop_event.set()
        self._recorder.stop_stream()

    def _on_chunk(self, chunk: np.ndarray) -> None:
        mono = chunk.flatten()
        if self._state == PipelineState.LISTENING:
            if self._vad.is_speech(mono):
                self._state = PipelineState.WAKING
                self._wake_chunk = mono.copy()
                self._speech_end_time = time.monotonic() + 2.0
        elif self._state == PipelineState.WAKING:
            self._wake_chunk = np.concatenate([self._wake_chunk, mono])
            if not self._vad.is_speech(mono) or time.monotonic() > self._speech_end_time:
                audio = self._wake_chunk
                self._wake_chunk = None
                self._state = PipelineState.LISTENING
                asyncio.run_coroutine_threadsafe(self._check_wake_word(audio), self._loop_task)  # type: ignore[arg-type]
        elif self._state == PipelineState.RECORDING:
            self._recording_frames.append(mono.copy())
            is_speech = self._vad.is_speech(mono)
            if not is_speech:
                self._silence_blocks += 1
                silence_s = self._silence_blocks * BLOCK_DURATION
                if silence_s >= 1.0 and len(self._recording_frames) > 20:
                    self._trigger_transcribe()
            else:
                self._silence_blocks = 0
            if (
                time.monotonic() > self._speech_end_time
                and len(self._recording_frames) > 5
                or time.monotonic() > self._speech_end_time
            ):
                self._trigger_transcribe()

    async def _check_wake_word(self, audio: np.ndarray) -> None:
        result = await self._wakeword.detect_async(self._stt, audio, self._samplerate)
        if result is not None:
            word, score = result
            log.info("Wake word '%s' detected (score=%.3f)", word, score)
            self._tts_stop.set()
            self._state = PipelineState.RECORDING
            self._recording_frames = [audio.copy()]
            self._silence_blocks = 0
            self._speech_end_time = time.monotonic() + self._record_timeout

    def _trigger_transcribe(self) -> None:
        self._state = PipelineState.TRANSCRIBING
        audio = np.concatenate(self._recording_frames)
        pcm = (audio * 32767).astype(np.int16).tobytes()
        self._recording_frames.clear()
        asyncio.run_coroutine_threadsafe(self._transcribe_and_submit(pcm), self._loop_task)  # type: ignore[arg-type]

    async def _transcribe_and_submit(self, pcm: bytes) -> None:
        try:
            text = await self._stt.transcribe(pcm)
            if not text:
                log.info("Transcription empty — returning to listening")
                self._state = PipelineState.LISTENING
                return
            log.info("Transcribed: %s", text)
            self._state = PipelineState.SUBMITTING
            await self._submit(text)
        except Exception:
            log.exception("Transcribe/submit error")
        finally:
            self._state = PipelineState.LISTENING

    async def _submit(self, text: str) -> None:
        try:
            async with connect(SOCKET_PATH) as conn:
                result = await conn.request(
                    RpcMethod.run_task,
                    {"task": text, "brain": self._brain},
                )
                log.info("Submitted run_task, run_id=%s", result.get("run_id", "?"))
        except DaemonUnavailable:
            log.warning("Daemon unavailable — cannot submit transcription")
        except RpcError as exc:
            log.warning("RPC error submitting transcription: %s", exc)
