# Kubernetes CICD Tutorial

This repo contains all the code needed to follow along with our **[YouTube Tutorial](https://youtu.be/GlhK7mz5IJo)** or **[Written Article](https://kubernetestraining.io/blog/kubernetes-ci-cd-build-a-pipeline-with-argocd-ghcr)**.

## Prerequisites

To follow along with this tutorial, you'll need:

- kubectl installed and configured ([https://youtu.be/IBkU4dghY0Y](https://youtu.be/IBkU4dghY0Y))
- Helm installed: ([https://kubernetestraining.io/blog/installing-helm-on-mac-and-windows](https://kubernetestraining.io/blog/installing-helm-on-mac-and-windows))
- A GitHub account: ([https://github.com/](https://github.com/))

## Install ArgoCD

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
kubectl create namespace argocd
helm install argocd argo/argo-cd --namespace argocd
```

## Access ArgoCD UI

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:80
```

## Retrieve Credentials

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```
## ArgoCD Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: grade-submission-api
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/YOUR_USERNAME/grade-api-gitops.git
    targetRevision: HEAD
    path: .
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## Creating Image Pull Secrets

To allow Kubernetes to pull images from GitHub Container Registry:

```yaml
kubectl create secret docker-registry ghcr-secret \\
  --docker-server=ghcr.io \\
  --docker-username=YOUR_USERNAME \\
  --docker-password=YOUR_PAT \\
  --namespace=default
```

## Kubernetes Training

If you found this guide helpful, check out our [Kubernetes Training course](https://kubernetestraining.io/)
