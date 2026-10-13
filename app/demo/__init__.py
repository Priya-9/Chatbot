"""Sales-demo mode: the visitor picks their business niche and the bot role-plays a sample business in it.

Everything niche-specific lives in data files (see `demo/README.md`):
  demo/niches.yaml              niche list, sample business names, booking wording, example questions
  demo/knowledge/<niche>/*.md   each niche's knowledge base (retrieval is scoped to the chosen niche)
"""

# Settings that switch a deployment into demo mode. `scripts/chat_cli.py --demo` applies these;
# for the server put the same values in `.env` (see `.env.demo.example`).
DEMO_ENV = {
    "NICHES_FILE": "demo/niches.yaml",
    "KNOWLEDGE_DIR": "demo/knowledge",
    "JOURNEY_FILE": "app/journeys/flows/demo.yaml",
    "SYSTEM_PROMPT_FILE": "demo/system_prompt.md",
    "RAG_REINDEX_ON_STARTUP": "true",
    "DATABASE_URL": "sqlite:///./data/demo.db",
}
