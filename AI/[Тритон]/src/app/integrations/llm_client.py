class DisabledLLMClient:
    """A deterministic no-op client kept as a safe extension point for future tasks."""

    def complete(self, prompt: str) -> str:
        del prompt
        return "LLM integrations are disabled in this isolated CTF service."


llm_client = DisabledLLMClient()

