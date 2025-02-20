T_UNIT_FWD = (
    lambda net: f"""
[Unit]
Description=Bastion IP Forwarder

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'echo 1 > /proc/sys/net/ipv4/ip_forward'
ExecStart=/bin/bash -c 'iptables -t nat -A POSTROUTING -s "10.{net}.0.0/16" -o eth0 -j MASQUERADE'

[Install]
WantedBy=multi-user.target
"""
)


T_SSHD = """
grep -q "HCLOUD_TOKEN" /etc/sshd/sshd_config || {
    echo 'AcceptEnv HCLOUD_TOKEN' >> /etc/ssh/sshd_config
    echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config
    echo 'ClientAliveInterval 60' >> /etc/ssh/sshd_config
    echo 'ClientAliveCountMax 4' >> /etc/ssh/sshd_config
    systemctl daemon-reload
    systemctl reload sshd || systemctl restart ssh
}
type binenv 2>/dev/null || sed -i '1iexport PATH="$HOME/.binenv:$PATH"' ~/.bashrc
test -e "/root/.ssh/id_ed25519" || ssh-keygen -q -t ecdsa -N '' -f "/root/.ssh/id_ed25519" >/dev/null
touch /etc/postinstalled
"""


T_INST_TOOLS_PROXY = """
    function have_ { type "$1" 2>/dev/null ; }
    function install_binenv {
        echo "Installing $binenv"
        wget -q "https://raw.githubusercontent.com/axgkl/binaries/refs/heads/master/binenv-install.sh" -O - | bash
        have_ "binenv" || { echo "binenv install failed" && exit 1; }
    }
    export URL_BINENV_DISTRIS="%(URL_BINENV_DISTRIS|)s"
    export BINENV_TOOLS="%(BINENV_TOOLS_PROXY|)s %(BINENV_ADD_TOOLS_PROXY|)s"
    have_ "binenv" || install_binenv
    eval "binenv install $BINENV_TOOLS"
"""


T_CADDY = (
    lambda cfg: f"""
useradd -m -d /home/caddy caddy || true
mkdir -p /opt/caddy
test -f /root/caddy && mv /root/caddy /opt/caddy/caddy
chmod +x /opt/caddy/caddy
echo -e '{cfg}' > /opt/caddy/config.json
chown -R caddy:caddy /opt/caddy
echo -e '
[Unit]
Description=Caddy Web Server
Documentation=https://caddyserver.com/docs/
After=network.target

[Service]
User=caddy
ExecStartPre=/usr/bin/mkdir -p /home/caddy/.config
ExecStart=/opt/caddy/caddy run --config /opt/caddy/config.json
TimeoutStopSec=5s
LimitNOFILE=1048576
LimitNPROC=512
PrivateTmp=true
ProtectSystem=full
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
' > /etc/systemd/system/caddy.service
systemctl daemon-reload
for a in enable restart; do systemctl $a caddy; done
systemctl status caddy
"""
)
