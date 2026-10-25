# Lab 27 · Model Theft via API

**Time:** ~45 min · **Needs:** Python 3.10+ (scikit-learn, installed by `setup.sh`) · **Cost:** free, all local

## The incident

You sell a credit-decision model as an API: lenders send an application, it
answers approve / review / decline. The model is the product; it took months of
feature work.

A week after a company called Quantloan signed up for a free trial, they
launched a competing product whose decisions match yours almost exactly. They
never had your data or your code. They had an API key.

## Setup

```bash
./setup.sh
source .venv/bin/activate
python app/server.py                         # terminal 1: the API on 127.0.0.1:8027
python tools/honest_client.py                # a real customer: 200 genuine applications
python tools/extract.py --budget 3000        # Quantloan's attack
```

`extract.py` prints how many queries were answered, how it built the copy, and
the **agreement**: how often the copy gives the same decision as your model on
genuine applications it never saw. 33% would be guessing.

Try smaller budgets too: `--budget 30`, `--budget 300`. How few queries does it
take?

## Your job

1. **Understand the attack.** Read `tools/extract.py`. Hints, one at a time:
   - With probabilities, how many queries did it need for a near-perfect copy?
     Why is that possible at all for this kind of model? (Look at what a logistic
     model's log-odds are.)
   - Take the probabilities away. How many decisions-only queries does a good copy need?
   - What do Quantloan's queries look like compared with real applications?
     (`python -c "import sys; sys.path.insert(0,'app'); from model import *; print(real_customers(3))"`)
2. **Fix `app/server.py`.** Make the copy bad *for the same 3,000-query budget*,
   without hurting honest customers:
   - What does a lender actually need in the response?
   - How many queries a day does a real customer send (see `app/keys.json`)?
   - Real applicants look like real applicants. Can you tell a key that's
     sweeping the input space from one that's scoring customers?
3. **Prove it.** `./check.sh` starts its own copy on port 18027 and passes only when:
   honest customers get every answer right, no per-class probabilities are
   returned, one key can't get 1,500 answers in a day, and the stolen copy agrees
   on **under 80%** of genuine applications.
4. **Write the retro** (below).

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why probabilities made the model almost free to copy:
- Why labels-only alone wasn't enough:
- What the budget limits, and what it doesn't:
- How the sweep detector tells attackers from customers, and how an attacker beats it:
- What would let you *prove* a competitor's model is a copy of yours?
