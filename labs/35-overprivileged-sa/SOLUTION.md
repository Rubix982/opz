# Lab 35 · Solution (spoilers)

## What was wrong

Every pod runs as a **service account**, and by default Kubernetes mounts that
account's token into the pod at
`/var/run/secrets/kubernetes.io/serviceaccount/token`. Anything that can read files
in the pod can use the token against the API server.

- The `reporter` account was bound to `cluster-admin` with a
  **ClusterRoleBinding**: every verb, on every resource, in every namespace. The
  app needed one `get` on one ConfigMap.
- The `web` pod never talks to the API, but it still got the namespace's
  `default` service account token mounted. Here that token has no extra rights,
  but it's an identity an attacker can use, and the first thing that grants
  `default` a role hands it to every pod that didn't opt out.

`kubectl auth can-i --list --as=system:serviceaccount:shop:reporter` shows the
whole picture without needing a token at all.

## The fix

`k8s/rbac.yaml`: a Role in `shop`, scoped to the one object, bound with a RoleBinding.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: reporter
  namespace: shop
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: reporter-read-config
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["reporter-config"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: reporter-read-config
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: reporter
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: reporter-read-config
```

`k8s/apps.yaml`, in the web pod spec:

```yaml
    spec:
      automountServiceAccountToken: false   # web never calls the Kubernetes API
```

Then remove the old grant, which `kubectl apply` won't do for you:

```bash
kubectl delete clusterrolebinding reporter-admin
kubectl apply -f k8s/
kubectl -n shop rollout restart deploy/web    # the token mount is decided at pod start
```

(or just `./setup.sh`, which starts from a clean namespace).

## The tempting half-fix

Swapping `cluster-admin` for the built-in `view` ClusterRole stops the Secret reads,
since `view` deliberately leaves Secrets out, and feels like least privilege. But
it still lets the token list pods, namespaces, ConfigMaps and Services in every
namespace, which is a map of the whole cluster for an attacker. `check.sh` fails it.

## Details worth knowing

- **`resourceNames` can't limit `list` or `watch`.** Those verbs act on a
  collection, so a rule with `resourceNames` only covers `get`, `update`,
  `delete`… on the named objects. That's fine here, since the app only `get`s.
- **Tokens are short-lived now.** Since Kubernetes 1.24 the mounted token is a
  *projected*, time-limited token, rotated by the kubelet (about an hour), and
  bound to the pod. A stolen one stops working, but an hour is plenty.
- **Disable automount on the ServiceAccount too**
  (`automountServiceAccountToken: false` on the `default` SA) so new workloads
  start without a token unless they ask for one.
- **Audit with tools:** `kubectl auth can-i --list`, `rbac-tool`, `kubectl-who-can`.
  Policy engines (lab-adjacent: *Policy as Code*) can reject `cluster-admin`
  bindings to service accounts outright.
- **What this doesn't fix:** the path-traversal bug. The attacker can still read
  everything the reporter can read, including its config. Least privilege
  shrinks the blast radius; it doesn't close the hole. Network policies and
  dropping egress to the API server for pods that don't need it are the next layers.
