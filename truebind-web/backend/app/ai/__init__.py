"""AI behind one interface (non-negotiable 9): EU/UK-hosted providers only
(Azure OpenAI in an EU/UK region, Amazon Bedrock in eu-*), zero retention,
and only column headers plus a few masked samples ever leave the server.
Tests use the deterministic FakeProvider."""
