# Security

PaperGuard is a single-user local application bound to 127.0.0.1. It is not designed as a public or multi-tenant service. Do not expose it through an untrusted reverse proxy.

Keys belong in an ignored local .env or environment variables. Downloaded papers and task files stay local and must not be committed. Configure an LLM endpoint only if you trust it; semantic mode sends necessary citation context and extracted evidence to that endpoint.

For a suspected vulnerability, use GitHub private vulnerability reporting if the repository owner has enabled it. Otherwise, ask the maintainer for a private reporting channel without posting secrets, private papers or exploit details in public issues. Do not publish a working exploit against users' machines.

The source-only release check performs filename, size and common secret-pattern checks. It is a useful guard, not a guarantee that arbitrary private data cannot appear in source files.
