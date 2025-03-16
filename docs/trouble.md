# Trouble List

## Killed flux
Made 

► installing components in "flux-system" namespace
✗ timeout waiting for: [CustomResourceDefinition/helmrepositories.source.toolkit.fluxcd.io status: 'Terminating', CustomResourceDefinition/helmcharts.source.toolkit.fluxcd.io status: 'Terminating', CustomResourceDefinition/helmreleases.helm.toolkit.fluxcd.io status: 'Terminating']


so: 
kubectl delete all --all -n cert-manager                                                                                                                !+? 🅒 nvim2🐍 v3.13.1

No resources found

  …/pyhk3❮ kubectl get crds | grep cert-manager                                                                                                                    !+? 🅒 nvim2🐍 v3.13.1

certificaterequests.cert-manager.io          2025-02-24T17:44:24Z
certificates.cert-manager.io                 2025-02-24T17:44:24Z
challenges.acme.cert-manager.io              2025-02-24T17:44:24Z
clusterissuers.cert-manager.io               2025-02-24T17:44:24Z
issuers.cert-manager.io                      2025-02-24T17:44:24Z
orders.acme.cert-manager.io                  2025-02-24T17:44:24Z

  …/pyhk3❯ kubectl get crds | grep nginx                                                                                                                           !+? 🅒 nvim2🐍 v3.13.1


  …/pyhk3❯ kubectl get crds | grep podinf                                                                                                                          !+? 🅒 nvim2🐍 v3.13.1

  …/pyhk3❯ kubectl get crds | grep cert                                                                                                                            !+? 🅒 nvim2🐍 v3.13.1
certificaterequests.cert-manager.io          2025-02-24T17:44:24Z
certificates.cert-manager.io                 2025-02-24T17:44:24Z
challenges.acme.cert-manager.io              2025-02-24T17:44:24Z
clusterissuers.cert-manager.io               2025-02-24T17:44:24Z
issuers.cert-manager.io                      2025-02-24T17:44:24Z
orders.acme.cert-manager.io                  2025-02-24T17:44:24Z

  …/pyhk3❯ kubectl delete crd certificates.cert-manager.io                                                                                                         !+? 🅒 nvim2🐍 v3.13.1
kubectl delete crd certificaterequests.cert-manager.io
kubectl delete crd challenges.acme.cert-manager.io
kubectl delete crd clusterissuers.cert-manager.io
kubectl delete crd issuers.cert-manager.io
kubectl delete crd orders.acme.cert-manager.io
