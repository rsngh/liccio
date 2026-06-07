"""Harness-arena package — routing across AGENT HARNESSES (not just LLM models).

Where the hetero arena varied the *model* (haiku/sonnet/opus/gemini single-shot API calls), this
varies the *harness*: a single-shot model call vs an in-process tool-loop harness vs a real vendor
CLI agent (Gemini CLI) that autonomously explores the repo. Same tasks, same held-out verifier.
"""
