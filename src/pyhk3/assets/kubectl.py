T_NS = """
---
apiVersion: v1
kind: Namespace
metadata:
  name: "%(namespace)s"
"""


T_SECRET = """
---
apiVersion: v1
kind: Secret
metadata:
  name: "%(name)s"
  namespace: "%(namespace)s"
data:
%(data)s
"""
