"""CLI commands for the voice subsystem.

Usage::

    agent voice status
    agent voice mute
    agent voice unmute
    agent voice toggle-mute
    agent voice ptt
    agent voice models list
    agent voice models pull --tts [voice] --stt [model]
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from agent.cli._common import ExitCode

voice_app = typer.Typer(no_args_is_help=True, help="Voice subsystem")

_MUTED_FLAG = (
    Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    / "hyprland-agent-voice.muted"
)


@voice_app.command("status")
def cmd_status() -> None:
    """Show voice subsystem status."""
    muted = _MUTED_FLAG.exists()
    typer.echo(f"muted: {'yes' if muted else 'no'}")
    if muted:
        typer.echo("Voice output is muted — run `agent voice unmute` to re-enable.")


@voice_app.command("mute")
def cmd_mute() -> None:
    """Mute voice output immediately."""
    _MUTED_FLAG.parent.mkdir(parents=True, exist_ok=True)
    _MUTED_FLAG.touch()
    typer.echo("Voice output muted")


@voice_app.command("unmute")
def cmd_unmute() -> None:
    """Unmute voice output."""
    _MUTED_FLAG.unlink(missing_ok=True)
    typer.echo("Voice output unmuted")


@voice_app.command("toggle-mute")
def cmd_toggle_mute() -> None:
    """Toggle voice mute state."""
    if _MUTED_FLAG.exists():
        _MUTED_FLAG.unlink(missing_ok=True)
        typer.echo("unmuted")
    else:
        _MUTED_FLAG.parent.mkdir(parents=True, exist_ok=True)
        _MUTED_FLAG.touch()
        typer.echo("muted")


@voice_app.command("ptt")
def cmd_ptt() -> None:
    """Send a push-to-talk trigger to the voice sidecar.

    Connect to the PTT Unix socket and send a ``record`` command.
    The sidecar will capture microphone audio, transcribe it, and
    submit the result to the daemon as a task.

    Bind this to a Hyprland key::

        bind = ,<code>, exec, agent voice ptt
    """
    from agent.voice.config import load_voice_config

    cfg = load_voice_config()
    socket_path = Path(cfg.ptt.socket) if cfg.ptt.socket else _default_ptt_socket()
    if not socket_path.exists():
        typer.echo(f"PTT socket not found at {socket_path}", err=True)
        typer.echo("Is the voice sidecar (agent-voice) running with PTT enabled?", err=True)
        raise typer.Exit(ExitCode.daemon_unavailable)

    try:
        import socket as sock_mod

        s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
        s.connect(str(socket_path))
        s.sendall(b"record\n")
        s.close()
    except OSError as exc:
        typer.echo(f"Failed to send PTT trigger: {exc}", err=True)
        raise typer.Exit(ExitCode.daemon_unavailable) from exc


def _default_ptt_socket() -> Path:
    return (
        Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        / "hyprland-agent-voice-ptt.sock"
    )


@voice_app.command("models")
def cmd_models(
    subcommand: str = typer.Argument("list", help="Subcommand: list | pull"),
    tts: str | None = typer.Option(None, "--tts", help="Piper voice to download"),
    stt: str | None = typer.Option(
        None, "--stt", help="STT model to download (tiny/base/small/medium)"
    ),
) -> None:
    """Manage voice models (list / pull)."""
    sub = subcommand.lower()
    if sub == "list":
        typer.echo("Voice models (M4: handsfree + TTS + STT):")
        typer.echo("  TTS (Piper):")
        typer.echo("    - it_IT-paola-medium  (~60 MB, Italian female)")
        typer.echo("  STT (faster-whisper):")
        typer.echo("    - tiny   (~75 MB, multilingual)")
        typer.echo("    - base   (~150 MB, multilingual)")
        typer.echo("    - small  (~500 MB, multilingual)")
        typer.echo("    - medium (~1.5 GB, multilingual)")
        typer.echo("  Wake word (openWakeWord):")
        typer.echo("    - hey_computer  (built-in, ~2 MB)")
        typer.echo("  VAD (Silero):")
        typer.echo("    - built-in (shipped with silero-vad)")
        typer.echo("")
        typer.echo("Install:")
        typer.echo("  agent voice models pull --tts it_IT-paola-medium")
        typer.echo("  agent voice models pull --stt tiny")
    elif sub == "pull":
        from agent.voice.download import download_piper, download_stt

        if tts:
            typer.echo(f"Downloading Piper TTS model: {tts}")
            path = download_piper(tts)
            typer.echo(f"Done: {path}")
        if stt:
            typer.echo(f"Downloading STT model: {stt}")
            path = download_stt(stt)
            typer.echo(f"Done: {path}")
        if not tts and not stt:
            typer.echo("Specify --tts <voice> and/or --stt <model>")
            raise typer.Exit(ExitCode.misuse)
    else:
        typer.echo(f"Unknown subcommand: {subcommand!r}", err=True)
        raise typer.Exit(ExitCode.misuse)
