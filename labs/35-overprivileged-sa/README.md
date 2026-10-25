# Lab 35 · Overprivileged Service Accounts in K8s

**Time:** ~40 min · **Needs:** Docker, `kind`, `kubectl` · **Cost:** free, all local

## The incident

A penetration tester found a path-traversal bug in the `reporter` service, the
kind that lets you read any file in the container. Their report had one line
that made everyone sit up: *"With the file at
`/var/run/secrets/kubernetes.io/serviceaccount/token` we listed every Secret in
the cluster, including the billing database password."*

Nobody had noticed, because the reporter never used those permissions itself.
It only reads one ConfigMap. Someone bound its service account to
`cluster-admin` months ago "to get things working", and it did.

## Setup

```bash
./setup.sh                                                  # kind cluster "opz-lab35" + the shop (~1 min first time)
kubectl -n shop exec deploy/reporter -- python /app/peek.py # what the reporter's token can do
kubectl -n shop exec deploy/web -- python /app/peek.py      # and the storefront's
```

`peek.py` makes **read-only** requests to the Kubernetes API with whatever token
is mounted in the pod, exactly as the tester did. Every value it prints is FAKE.

`setup.sh` switches kubectl to `kind-opz-lab35`. Re-running it resets everything,
including RBAC objects you created.

## Your job

1. **See the blast radius.** Before changing anything, answer: what can the
   reporter's token do, and what does the reporter actually need? Hints, one at a time:
   - `kubectl auth can-i --list --as=system:serviceaccount:shop:reporter -n shop`
   - `kubectl get clusterrolebindings -o wide | grep reporter`
   - Read `app/reporter.py`. Which single API call does it make?
   - The storefront (`web`) never calls the API. Does it still have a token? Why?
2. **Fix it with least privilege** by editing `k8s/` and applying it.
   - A `ClusterRoleBinding` grants a role **everywhere**. A `RoleBinding` grants
     it in one namespace. Which does the reporter need?
   - Rules can name individual objects (`resourceNames`), not just resource types.
   - Look up `automountServiceAccountToken`.
   - `kubectl apply` adds and changes objects but never deletes ones you removed
     from the file. Delete the old binding yourself, or re-run `./setup.sh`.
3. **Prove it.** `./check.sh` runs the probes **from inside the reporter pod with
   its own token**, asks `kubectl auth can-i` the same questions, confirms the
   reporter is still reading its config, and checks the web pod has no token.
4. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- How a pod authenticates to the API, and where the credential lives:
- What the reporter could do before, and what it needed:
- Role vs ClusterRole, RoleBinding vs ClusterRoleBinding:
- Why the web pod had a token at all, and the one-line fix:
- What least privilege doesn't stop (the bug is still there):
