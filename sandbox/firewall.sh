#!/usr/bin/env bash
# Outbound firewall for a worker container. Default deny; allow only what a worker needs:
#   - loopback, and replies to connections the container opened
#   - DNS, to the resolvers this container was given
#   - the container's own Docker network (that is where the local model's proxy lives)
#   - the hosts in OFFLOAD_ALLOW_HOSTS (default: api.anthropic.com), resolved once, now
# It ends by proving both halves: a host that is not on the list must be unreachable, and with
# OFFLOAD_VERIFY_HOST set, that host must be reachable. Any failure exits non-zero, and the engine
# then refuses to start the worker.
set -euo pipefail

allow_hosts="${OFFLOAD_ALLOW_HOSTS-api.anthropic.com}"

for table in iptables ip6tables; do
  "$table" -F OUTPUT
  "$table" -P OUTPUT DROP
  "$table" -A OUTPUT -o lo -j ACCEPT
  "$table" -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
done

# DNS, only to the configured resolvers.
while read -r keyword resolver _; do
  if [ "$keyword" = "nameserver" ] && [[ "$resolver" != *:* ]]; then
    iptables -A OUTPUT -d "$resolver" -p udp --dport 53 -j ACCEPT
    iptables -A OUTPUT -d "$resolver" -p tcp --dport 53 -j ACCEPT
  fi
done < /etc/resolv.conf

# The container's own network: every directly connected IPv4 subnet.
ip -4 -o route show scope link | while read -r subnet _; do
  iptables -A OUTPUT -d "$subnet" -j ACCEPT
done

# Allowlisted hosts, by address. A set, so a host with many addresses costs one rule.
ipset create -exist offload-allow hash:ip
ipset flush offload-allow
for host in $allow_hosts; do
  addresses="$(getent ahostsv4 "$host" | awk '{print $1}' | sort -u)"
  if [ -z "$addresses" ]; then
    echo "offload-firewall: cannot resolve $host" >&2
    exit 1
  fi
  for address in $addresses; do
    ipset add -exist offload-allow "$address"
  done
done
iptables -A OUTPUT -m set --match-set offload-allow dst -p tcp --dport 443 -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

# Prove it.
if curl -s -o /dev/null --max-time 4 https://example.com; then
  echo "offload-firewall: example.com is reachable; the firewall is not working" >&2
  exit 1
fi
if [ -n "${OFFLOAD_VERIFY_HOST:-}" ] && ! curl -s -o /dev/null --max-time 8 "https://${OFFLOAD_VERIFY_HOST}"; then
  echo "offload-firewall: ${OFFLOAD_VERIFY_HOST} is on the allowlist but unreachable" >&2
  exit 1
fi
echo "offload-firewall: up; allowed: ${allow_hosts:-nothing beyond the local network}"
