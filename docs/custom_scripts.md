# TODO: Try custom scripts with flux:

https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/configmapgenerator/#configmap-from-file

## Q: Explain 5. more. Lets say my app server ships with a filesystem, containing '/opt/superapp/custom' directory. Possible to get custom scripts into that filesystem, at container start with that approach?

### A: Yes, absolutely! Here's a detailed implementation:

1. **Base Structure**:
```
apps/
  superapp/
    base/
      deployment.yaml
      kustomization.yaml
    overlays/
      customer1/
        kustomization.yaml
        scripts/
          custom_script1.py
          custom_script2.py
      customer2/
        kustomization.yaml
        scripts/
          custom_script3.py
```

2. **Base Deployment**:
```yaml
# apps/superapp/base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: superapp
spec:
  template:
    spec:
      containers:
      - name: superapp
        image: your-registry/superapp:latest
        volumeMounts:
        - name: custom-scripts
          mountPath: /opt/superapp/custom
      volumes:
      - name: custom-scripts
        emptyDir: {}  # This will be populated by the init container
      initContainers:
      - name: copy-scripts
        image: busybox
        command: ['sh', '-c', 'cp /scripts/* /custom/']
        volumeMounts:
        - name: custom-scripts
          mountPath: /custom
        - name: scripts-volume
          mountPath: /scripts
      volumes:
      - name: scripts-volume
        configMap:
          name: custom-scripts
```

3. **Base Kustomization**:
```yaml
# apps/superapp/base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- deployment.yaml
```

4. **Customer Overlay**:
```yaml
# apps/superapp/overlays/customer1/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../../base
configMapGenerator:
- name: custom-scripts
  files:
  - scripts/custom_script1.py
  - scripts/custom_script2.py
```

5. **Flux Kustomization**:
```yaml
# clusters/production/apps/superapp.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: superapp
  namespace: superapp
spec:
  interval: 1m
  path: ./apps/superapp/overlays/customer1
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
```

### How it works:

1. **At Build Time**:
   - Kustomize reads the scripts from the customer's overlay
   - Creates a ConfigMap containing all the scripts
   - The ConfigMap is mounted as a volume in the pod

2. **At Container Start**:
   - The init container runs first
   - Copies all scripts from the ConfigMap volume to the emptyDir volume
   - The main container starts with the scripts already in place
   - The scripts are available at `/opt/superapp/custom`

3. **When Scripts Change**:
   - Flux detects changes in the Git repository
   - Updates the ConfigMap
   - Pods are restarted (or you can implement a more sophisticated update strategy)

### Benefits of this approach:

1. **Separation of Concerns**:
   - Base app configuration is separate from customer scripts
   - Each customer has their own overlay
   - Easy to manage multiple customers

2. **Version Control**:
   - All scripts are version controlled
   - Changes are tracked
   - Easy to rollback

3. **Flexibility**:
   - Can add/remove scripts per customer
   - Can have different scripts for different environments
   - Easy to update scripts

4. **Security**:
   - Scripts are stored in ConfigMaps
   - Can use Secrets for sensitive scripts
   - Access control through Git

5. **Maintenance**:
   - Easy to update scripts
   - Clear structure
   - Good for GitOps workflow 
