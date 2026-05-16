# Privacy & Data Handling

hyprland-agent is a **local-first** tool. No data is collected by the project itself. However, to function, it sends data to external LLM providers of your choosing.

## What leaves your machine

On every action step, the following is transmitted to the configured LLM provider:

| Data | Notes |
|------|-------|
| Desktop screenshot | Downscaled to 50% (0.5×) before sending. Contains whatever is visible on your screen at that moment. |
| Task prompt | The natural-language instruction you gave. |
| Action history | The sequence of actions taken so far in the current run (window names, click coords, typed text). |
| Episodic context | Up to 3 summaries of past runs retrieved by semantic similarity (task text only, no screenshots). |
| System metadata | Active window list, focused window title, OS/compositor info injected into `BrainContext`. |

## Provider-specific notes

| Provider | Key env var | Data policy |
|----------|-------------|-------------|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | [Anthropic Privacy Policy](https://www.anthropic.com/legal/privacy) |
| OpenAI | `OPENAI_API_KEY` | [OpenAI Privacy Policy](https://openai.com/policies/privacy-policy) |
| Groq | `GROQ_API_KEY` | [Groq Privacy Policy](https://groq.com/privacy-policy/) |
| Together AI | `TOGETHER_API_KEY` | [Together Privacy Policy](https://www.together.ai/privacy) |
| Moonshot | `MOONSHOT_API_KEY` | Provider policy applies |
| ZAI / Qwen | `ZAI_API_KEY` / `QWEN_API_KEY` | Provider policy applies |

**Provider API keys are stored in `~/.config/hyprland-agent/env` and read only by the daemon process. They never cross the IPC socket.**

## Local storage

| Location | Contents |
|----------|----------|
| `~/.cache/hyprland-agent/runs.db` | SQLite WAL: run history, action outcomes, episodic embeddings, learned rules, allowlist proposals. |
| `~/.cache/fastembed/` | `intfloat/multilingual-e5-large` model (~1.3 GB), downloaded on first use. License: MIT. Source: [Hugging Face](https://huggingface.co/intfloat/multilingual-e5-large). |
| `~/.config/hyprland-agent/` | `allowlist.yaml`, `rules.yaml`, `learned_rules.yaml`, `env`, `config.yaml`. |

## Screenshots

Screenshots are captured with `grim`, downscaled in memory with Pillow, and transmitted directly to the provider. They are **not written to disk** by hyprland-agent (only held in RAM during the step).

## Minimising data exposure

- Use `--brain auto` with only local-compatible providers enabled in `config.yaml` to avoid sending data externally (note: no local provider is bundled; you would need a self-hosted OpenAI-compatible endpoint).
- Set a tight allowlist (`allowlist.yaml`) to limit which windows the agent can interact with and therefore what ends up in screenshots.
- Use `agent stop` / the killswitch to halt runs immediately.
