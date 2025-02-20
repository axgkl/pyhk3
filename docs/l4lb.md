# Layer 4 Load Balancer

You don't necessarily need to use hetzner's layer 4 load balancer. 

Below we describe the mechanics of 'rolling your own', on the proxy server in front of your cluster. We use [mholt/caddy-l4][cl4] here. Nginx, haproxy or traefik would work as well.

## Why

- **Transferability**: NOT using the hetzner ccm to auto provision cluster external loadbalancers means in turn: The setup, incl. service "yamls" is hetzner ccm annotion free, i.e. not specific to Hetzner => can be used on premise, behind a given (customer) load balancer - but also at any other cloud provider.
- **Security**: No public IPs on the nodes, only the bastion node has one.
- **Cost**: Hetzner Load balancers are expensive, compared to the cost of a single node. Pub IPs also cost money.

Downside clearly is HA - the bastion node is a single point of failure, if (and only if) it is also the load balancer. BUT: It is trivial to replace, even w/o any kubernetes skills, since not part of the actual k8s cluster.

Also: Like hetzner's lbs, ours works on  layer 4, supporting proxy protocol, but unlike with hetzner lbs, there is no hetzner ccm style machinery in place within kubernetes, which would automatically update the loadbalancer, when a new ingress port comes up. 

Therefore, the loadbalancer we create on the proxy is currently forwarding only http and https to node ports, _statically_ configured for the (nginx) ingress, on 30080 and 30443. 

Let me know if you are aware of something like a ccm, which could fire e.g.
configurable http requests, when another port should be served for the
internet, so that we could provide a reconfig handler for such requests, on the
proxy lb. For now, if you all the time have such requirements, use hetzner's lb
or add the new port to the proxy lb manually, e.g. using the functions within
this repo.

## How

We install caddy with the l4 extension and configures it to forward traffic to the cluster nodes, adding the [proxy protocol](https://www.haproxy.com/blog/use-the-proxy-protocol-to-preserve-a-clients-ip-address) header.

Below is a sample caddy config, for the private network on `10.1.0.0/16` and 3 master nodes:


```json
root@citest-proxy:~# cat /opt/caddy/config.json
{
  "logging": {
    "sink": {
      "writer": {
        "output": "stdout"
      }
    },
    "logs": {
      "default": {
        "level": "DEBUG"
      }
    }
  },
  "apps": {
    "layer4": {
      "servers": {
        "port80": {
          "listen": [
            ":80",
            "[::]:80"
          ],
          "routes": [
            {
              "handle": [
                {
                  "handler": "proxy",
                  "proxy_protocol": "v2",
                  "upstreams": [
                    {
                      "dial": [
                        "10.1.0.3:30080"
                        "10.1.0.4:30080"
                        "10.1.0.5:30080"
                      ]
                    }
                  ]
                }
              ]
            }
          ]
        },
        "port443": {
          "listen": [
            ":443",
            "[::]:443"
          ],
          "routes": [
            {
              "handle": [
                {
                  "handler": "proxy",
                  "proxy_protocol": "v2",
                  "upstreams": [
                    {
                      "dial": [
                        "10.1.0.3:30443"
                        "10.1.0.4:30443"
                        "10.1.0.5:30443"
                      ]
                    }
                  ]
                }
              ]
            }
          ]
        }
      }
    }
  }
}

```

## 📝 Note

This is forwarding http and https traffic to static Node Ports within the cluster, acting solely on layer 4. We provide the IPs of our 3 master nodes. 

## 💡 Node Port

> A NodePort is a feature in Kubernetes that exposes a service to external traffic. It's one of the ways you can access the service within the cluster from outside.
> When a service is created with NodePort type, Kubernetes allocates a port from a predefined range (default is 30000-32767), and each Node will proxy that port (the same port number on every Node) into your service.
> External traffic that comes to the Node on the allocated port is forwarded to the service. Even if a service is running on a specific node, using NodePort allows the service to be accessible from other nodes in the cluster.

So: This works, when we configure our ingress within the cluster, with Node Ports 30080 and 30443.

In turn we do _not_ need to provide annotations for the hetzner ccm, which would automatically update the hetzner loadbalancer, when a new ingress port comes up.

=> If you have rather dynamic requirements, regarding open ports on the Internet, then use use hetzner's lb - or add the new port to the proxy lb manually, in such occasions.

Again, I'm not aware of some ccm, which could e.g. run http config requests on new ingress ports, so that we could provide a reconfig handler for such requests, on the proxy lb. Let me know via an issue, if you are.

---

Further reading: 

- https://medium.com/@panda1100/how-to-setup-layer-4-reverse-proxy-to-multiplex-tls-traffic-with-sni-routing-a226c8168826

[cl4]: https://github.com/mholt/caddy-l4
