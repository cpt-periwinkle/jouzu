"""
Unit tests for backend/prompts/quiz.py and backend/prompts/templates.py.

TODO: Write these when prompt structure stabilizes further.

What to test:
- build_explain_prompt fills all placeholders without KeyError
- build_hint_prompt fills all placeholders without KeyError
- PATTERN tag instruction is present in EXPLAIN_TEMPLATE
- Mnemonic section is included when mnemonic is provided
- Mnemonic section is absent when mnemonic is None
- Vocabulary section is included when known_vocabulary is provided
- Vocab list is capped at 50 items
"""
