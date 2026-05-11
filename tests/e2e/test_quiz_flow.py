"""
End-to-end tests for the full quiz loop.

TODO: Write these before public deployment.
These tests hit real or stubbed Claude and verify the full round-trip works.
Run in CI only on merge to main -- they are slow and incur API costs.

What to test:
- Happy path: fetch item -> submit correct guess -> get ExplainResponse with explanation
- Miss path: fetch item -> submit wrong guess -> closeness is 'off' -> explanation references mistake
- PATTERN tag is parsed correctly and stripped from explanation text
- Hint endpoint returns a string that does not contain the correct reading
- Upload -> fetch -> explain works end to end with custom CSV

Note: Mock Claude responses where possible to avoid costs. Keep one real
Claude call test to verify the actual prompt produces sensible output.
"""
