# feat(mvp): scaffold + setup + risk manager + client (paper-mode)

## Executive summary
This PR introduces the initial MVP: project scaffold, setup, RiskManager implementation, and a Client with a FakeAdapter for paper-mode testing. Sprints 1-3 are implemented locally and this draft aggregates the changes for review.

## Files changed (summary)
- polymarket_bot/adapters/base.py
- polymarket_bot/adapters/fake.py
- polymarket_bot/client.py
- polymarket_bot/risk/risk_manager.py
- .env.example
- .gitignore
- setup.py
- tests/*
- (plus scaffold and config files)

## Tests
- All tests passing locally: 11 passed

### How to run tests
1. Install dependencies: `pip install -e .` (or your preferred environment setup)
2. Run: `python -m pytest -q`

## Checklist
- [x] Paper-mode enforced via FakeAdapter and Client behavior
- [x] .env.example included
- [x] .gitignore updated
- [x] RiskManager implemented
- [x] Client and FakeAdapter implemented

## Suggested reviewers


## Recent commits (local)
- 15621bd feat(client): add ExchangeAdapter base and FakeAdapter (paper-mode safe)
- 73b09e5 test(risk): ensure RiskManager tests pass and time mocking deterministic
- 4b74203 test(risk): add unit tests for RiskManager
- 756d90b feat(risk): implement RiskManager core logic
- ebdc3fe chore(scaffold): add package scaffold and setup.py