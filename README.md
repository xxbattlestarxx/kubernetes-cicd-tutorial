# Kubernetes CICD Tutorial (Actions, JFrog, Argocd)

This repo contains all the code needed to follow along with our **[YouTube Tutorial](https://)** or **[Written Article](https://)**.

## Prerequisites

To follow along with this tutorial, you'll need:

- kubectl installed and configured ([https://youtu.be/IBkU4dghY0Y](https://youtu.be/IBkU4dghY0Y))
- Helm installed: ([https://kubernetestraining.io/blog/installing-helm-on-mac-and-windows](https://kubernetestraining.io/blog/installing-helm-on-mac-and-windows))
- A GitHub account: ([https://github.com/](https://github.com/))

## Install JFrog Artifactory in your cluster:

```bash
helm repo add jfrog https://charts.jfrog.io
helm repo update

kubectl create namespace jfrog

helm install artifactory jfrog/artifactory \
  --namespace jfrog \
  --set artifactory.postgresql.postgresqlPassword=password \
  --set artifactory.adminPassword=password
```
## Access JFrog

```
kubectl port-forward -n jfrog svc/artifactory-nginx 8082:80
```

## Install ArgoCD

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
kubectl create namespace argocd
helm install argocd argo/argo-cd --namespace argocd
```

## Access ArgoCD UI

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

## Retrieve Credentials

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

## Kubernetes Training

If you found this guide helpful, check out our [Kubernetes Training course](https://kubernetestraining.io/)
