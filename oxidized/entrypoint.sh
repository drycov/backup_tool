#!/bin/sh
set -e

# Named volume /var/lib/oxidized is owned by root on first start;
# oxidized runs as UID 30000 and cannot create logs or git repo there.
mkdir -p /var/lib/oxidized
# log: in config is a file path; remove legacy directory if present
if [ -d /var/lib/oxidized/logs ] && [ ! -f /var/lib/oxidized/logs ]; then
  rm -rf /var/lib/oxidized/logs
fi
chown -R oxidized:oxidized /var/lib/oxidized
chmod -R a+rwX /var/lib/oxidized 2>/dev/null || true
git config --global --add safe.directory /var/lib/oxidized 2>/dev/null || true

# log: paths must be files, not directories
for logfile in /var/lib/oxidized/oxidized.log /var/lib/oxidized/oxidized-python.log; do
  if [ -d "$logfile" ]; then
    rm -rf "$logfile"
  fi
  touch "$logfile" 2>/dev/null || true
  chmod a+rw "$logfile" 2>/dev/null || true
done

# SSH keys for git push (githubrepo hook)
if [ -d /home/oxidized/.ssh ]; then
  chown -R oxidized:oxidized /home/oxidized/.ssh
  chmod 700 /home/oxidized/.ssh
  if [ -f /home/oxidized/.ssh/id_rsa ]; then
    chmod 600 /home/oxidized/.ssh/id_rsa
  else
    echo "WARN: /home/oxidized/.ssh/id_rsa not found — git push will fail until keys are added"
  fi
  if [ -f /home/oxidized/.ssh/id_rsa.pub ]; then
    chmod 644 /home/oxidized/.ssh/id_rsa.pub
  fi
  if [ -f /home/oxidized/.ssh/known_hosts ]; then
    # Windows bind-mount may inject CRLF; libssh2 rejects malformed known_hosts
    sed -i 's/\r$//' /home/oxidized/.ssh/known_hosts
    chmod 644 /home/oxidized/.ssh/known_hosts
  else
    echo "WARN: /home/oxidized/.ssh/known_hosts missing — add host key via: ssh-keyscan 10.216.40.65 >> oxidized-ssh/known_hosts"
  fi
fi

export HOME=/home/oxidized

CONFIG=/home/oxidized/.config/oxidized/config
if [ -n "$GITEA_TOKEN" ] && [ -f "$CONFIG" ]; then
  sed -i "/username: oauth2/{n;s/^    password: .*/    password: ${GITEA_TOKEN}/;}" "$CONFIG"
fi

exec /usr/bin/dumb-init -- runsvdir -P /etc/service
