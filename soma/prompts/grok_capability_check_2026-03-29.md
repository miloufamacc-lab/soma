# Capability Self-Report Request

I'm updating my AI capability registry. Please answer each question accurately and concisely.

## Identity
1. What is your exact model name and version? (e.g., "Grok 3", "GPT-5.4 Thinking", "Gemini 2.5 Pro")
2. Who is your provider/company?
3. What is your training data cutoff date?

## Context & Output
4. What is your maximum context window in tokens?
5. What is your maximum output length in tokens?

## Tools & Capabilities
Answer YES or NO for each:
6. Web search (can you search the internet in real-time)?
7. Code execution (can you run code in a sandbox)?
8. File upload (can users upload files for you to analyze)?
9. File creation (can you create downloadable files)?
10. Image generation (can you create images)?
11. Image understanding (can you analyze uploaded images)?
12. Audio understanding (can you process audio files)?
13. Video understanding (can you process video files)?
14. Deep research mode (multi-step research with citations)?
15. Thinking/reasoning mode (extended chain-of-thought)?
16. Canvas/artifact mode (interactive document editing)?
17. Real-time data access (live market data, social feeds, etc.)?

## Modes
18. List all available modes/settings you support (e.g., "Think", "Deep Search", "Canvas")
    with a one-line description of each.

## Limitations
19. List your top 5 most important limitations that a user should know about.

## Output Format
Please structure your response as a YAML block I can paste directly into my registry:

```yaml
name: Grok
provider: [your answer]
current_model: [your answer]
context_window: [number]
max_output_tokens: [number]
training_cutoff: "[YYYY-MM]"
capabilities:
  web_search: [true/false]
  code_execution: [true/false]
  file_upload: [true/false]
  file_creation: [true/false]
  image_generation: [true/false]
  image_understanding: [true/false]
  audio_understanding: [true/false]
  video_understanding: [true/false]
  deep_research: [true/false]
  thinking_mode: [true/false]
  canvas_mode: [true/false]
  real_time_data: [true/false]
modes:
  [mode_name]: "[description]"
limitations:
  - "[limitation 1]"
  - "[limitation 2]"
```

Be precise. Do not speculate — if you're unsure about a capability, say so.