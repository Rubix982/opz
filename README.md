# opz

Deployment, security and systems, learned one small broken system at a time.

Each lab shrinks a real incident to something that runs on a laptop in under an
hour, and every lab follows the same steps:

```
break → diagnose → fix → prove → retro
```

The proof is a `check.sh` that passes only when the problem is actually gone,
not when it's hidden.

## Layout

- [`labs/`](labs/): the labs, one folder each. Start with [`labs/README.md`](labs/README.md).
- [`labs/CHECKLIST.md`](labs/CHECKLIST.md): every scenario, in four tracks:
  **A** DevOps & security, **B** distributed systems, **C** AI systems & security,
  **D** cloud. The [Labs page](https://rubix982.github.io/open-concept-lab/labs)
  on my site is generated from it.
- [`plan.md`](plan.md): where things stand.
- The scenario lists the checklist was built from: `devops_scenarios.md`,
  `system_design_scenarios.md`, `ai-devsecops.md`.
- [What each solved lab taught me](https://rubix982.github.io/open-concept-lab/notebook/opz/)

Everything runs locally and costs nothing. Track D's labs use local AWS
emulators instead of a real account. Every credential in this repo is fake and
says so.

This repo started as `projects/opz` inside
[open-concept-lab](https://github.com/Rubix982/open-concept-lab), with its
history kept, and is still included there as a submodule.
