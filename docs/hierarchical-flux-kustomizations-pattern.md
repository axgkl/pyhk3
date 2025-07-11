# Hierarchical Flux Kustomizations Pattern

A scalable GitOps architecture pattern for managing complex infrastructure components with self-contained dependency orchestration.

## Problem Statement

Traditional GitOps approaches often face challenges when deploying complex components with internal dependencies:

- **Centralized orchestration** becomes unwieldy as complexity grows
- **Dependency ordering** requires careful manual coordination
- **Team ownership** is unclear when orchestration logic is centralized
- **Scalability** suffers when all orchestration lives in cluster-level files

## Solution: Hierarchical Flux Kustomizations

Each complex component manages its own internal dependencies using Flux Kustomizations within its directory structure.

## Architecture Pattern

### Directory Structure
```
infrastructure/production/
├── clusters/production/infrastructure.yaml    # Only major phases
├── database-stack/
│   ├── flux-kustomizations.yaml              # Internal orchestration
│   ├── postgres/
│   ├── redis/
│   └── migrations/
├── monitoring-stack/
│   ├── flux-kustomizations.yaml              # Internal orchestration  
│   ├── prometheus/
│   ├── grafana/
│   └── alerts/
└── tekton-config/
    ├── flux-kustomizations.yaml              # Internal orchestration
    ├── base/
    ├── tasks/
    ├── triggers/
    └── rbac/
```

### Component Template

Each complex component follows this pattern:

```yaml
# component/flux-kustomizations.yaml
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: component-base
  namespace: flux-system
spec:
  interval: 5m
  retryInterval: 1m
  timeout: 10m
  sourceRef:
    kind: GitRepository
    name: flux-system
  path: ./infrastructure/production/component/base
  prune: true
  wait: true
  healthChecks:
    - apiVersion: apps/v1
      kind: Deployment
      name: component-controller
      namespace: component-system

---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: component-addons
  namespace: flux-system
spec:
  dependsOn:
    - name: component-base
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: flux-system
  path: ./infrastructure/production/component/addons
  prune: true
```

### Parent Kustomization

The component's main kustomization only references the orchestration file:

```yaml
# component/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- flux-kustomizations.yaml
```

## Real-World Example: Tekton

### Problem
Tekton has internal dependencies:
1. **Tekton Operator** → installs CRDs
2. **TektonConfig** → installs Tekton Pipelines (creates ClusterTask CRDs)  
3. **ClusterTasks** → require Tekton Pipelines CRDs to exist

### Solution Implementation

```
tekton-config/
├── flux-kustomizations.yaml    # Orchestration logic
├── kustomization.yaml          # References flux-kustomizations.yaml
├── base/
│   ├── tektonconfig.yaml       # Phase 1: Install TektonConfig
│   └── kustomization.yaml
├── tasks/                      # Phase 2: ClusterTasks (depends on base)
├── triggers/                   # Phase 2: Triggers (depends on base)
└── rbac/                       # Phase 2: RBAC (depends on base)
```

### Deployment Flow
1. Parent `infra-configs` creates Tekton Flux Kustomizations
2. `tekton-base` deploys → Installs TektonConfig → Waits for Ready
3. `tekton-tasks`, `tekton-triggers`, `tekton-rbac` deploy in parallel
4. ClusterTasks succeed because Tekton Pipeline CRDs now exist

## Key Benefits

### 1. **Component Self-Containment**
- All orchestration logic stays within the component directory
- Teams own their component's complexity entirely
- No changes needed to cluster-level infrastructure files

### 2. **Apply-Time Orchestration**  
- Real dependency checking with health checks
- Retry logic and failure handling
- Unlike Kustomize (build-time), Flux orchestrates at apply-time

### 3. **Scalability**
- No centralized orchestration bottleneck
- Each component can have arbitrarily complex internal dependencies  
- Clean separation of concerns

### 4. **Team Ownership**
- Database team owns `database-stack/flux-kustomizations.yaml`
- Monitoring team owns `monitoring-stack/flux-kustomizations.yaml`
- Platform team only manages high-level phases

### 5. **Flexibility**
- Simple components use regular `kustomization.yaml`
- Complex components use `flux-kustomizations.yaml`
- Mix and match as needed

## Best Practices

### 1. **Health Checks**
Always include health checks for base components:
```yaml
healthChecks:
  - apiVersion: operator.tekton.dev/v1alpha1
    kind: TektonConfig
    name: config
    namespace: ""
```

### 2. **Wait Conditions**
Use `wait: true` for base components to ensure readiness:
```yaml
spec:
  wait: true  # Wait for all resources to be ready
```

### 3. **Timeout Management**
Set appropriate timeouts for complex deployments:
```yaml
spec:
  timeout: 10m  # Allow time for complex installations
  retryInterval: 1m
```

### 4. **Naming Conventions**
Use consistent naming for internal Kustomizations:
- `{component}-base` for foundational components
- `{component}-{feature}` for dependent features

## When to Use This Pattern

### ✅ Use for:
- Components with internal dependencies (databases, monitoring stacks, CI/CD)
- Multi-phase deployments requiring readiness checks
- Components owned by specific teams
- Complex installations with custom resources

### ❌ Don't use for:
- Simple, single-resource deployments
- Components with no internal dependencies
- Static configuration that never changes

## Migration Strategy

1. **Identify complex components** with dependency issues
2. **Create base/ directory** with foundational resources
3. **Create flux-kustomizations.yaml** with dependency logic
4. **Update main kustomization.yaml** to reference orchestration file
5. **Test deployment flow** in development environment
6. **Apply to production** with monitoring

## Conclusion

The Hierarchical Flux Kustomizations pattern enables scalable GitOps architectures where complexity is managed locally within each component. This approach maintains clean separation of concerns while providing powerful apply-time orchestration capabilities.

Teams can own their component's orchestration logic without affecting cluster-level infrastructure, creating a truly scalable and maintainable GitOps architecture.
