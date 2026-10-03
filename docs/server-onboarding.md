# Server onboarding

Use one dedicated non-root deploy user per target server. Do not SSH as root.

## 1. Create the deploy user

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo mkdir -p /home/deploy/.ssh
sudo chown deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
```

## 2. Add the server in DeployDock

Enter the name, host, SSH port, and deploy username. **Leave the private key
field blank.** DeployDock generates a unique ed25519 keypair for this server and
shows you the public half. Keys are never reused across servers, so revoking one
server's access never affects another.

## 3. Authorise the generated key

```bash
echo '<generated-public-key>' | sudo tee -a /home/deploy/.ssh/authorized_keys
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

Pasting your own existing private key is still available as an advanced option,
but generated per-server keys are the default for a reason: a key DeployDock
generated has never existed anywhere else.

## 4. Pin the host key

Press **Test connection**. On the first successful connection DeployDock pins
the SSH host key the server presented and shows its fingerprint.

**Verify that fingerprint before you trust it.** On a machine you trust:

```bash
ssh-keyscan -t ed25519 your-server.example.com | ssh-keygen -lf -
```

Or on the server's own console:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

The fingerprint shown in DeployDock must match. First-use pinning is
trust-on-first-use — the same model as your own `~/.ssh/known_hosts` — so this
one comparison is what turns it into real verification.

Every connection after that is verified against the pinned key. If the server
presents a different key, DeployDock aborts the connection and reports the
mismatch instead of handing over the decrypted private key.

### When the host key legitimately changes

Rebuilding a server, reinstalling the OS, or rotating host keys on purpose all
change the fingerprint. In that case, on the server detail page:

1. Confirm the change was expected.
2. Verify the new fingerprint out of band, exactly as above.
3. Press **Re-pin host key**.

Re-pinning is deliberate and never automatic, because an unexpected host key
change is indistinguishable from an interception attempt. Every re-pin is
written to the audit log with the old and new fingerprints.

Changing a server's host or port clears the pinned key automatically: a
different address is a different machine as far as trust goes.

## 5. Grant narrow sudo permissions

Give the deploy user sudo only for the specific commands the app needs:

```text
deploy ALL=(root) NOPASSWD: /bin/systemctl restart watchdog
deploy ALL=(root) NOPASSWD: /bin/systemctl reload nginx
deploy ALL=(root) NOPASSWD: /usr/sbin/nginx -t
```

Edit with `sudo visudo -f /etc/sudoers.d/deploy`. Avoid
`deploy ALL=(ALL) NOPASSWD: ALL` — it makes the deploy key equivalent to root,
which undoes the point of a dedicated user.

Note the honest limit here: the deploy command itself is arbitrary shell run as
the deploy user. Narrow sudo bounds what that shell can escalate to; it does not
bound the shell. See [Security model](security.md).

## 6. Recommended sshd hardening

On the target server, in `/etc/ssh/sshd_config`:

```text
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
```

Reload with `sudo systemctl reload sshd`. Keep an existing session open while
you test, so a mistake does not lock you out.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `Could not read a host key from host:port` | The server is unreachable, SSH is on another port, or a firewall is dropping the connection |
| `Host key ... does not match the pinned key` | The server changed, or the connection is being intercepted. Verify out of band before re-pinning |
| `No host key is pinned for this server` | Run a connection test first; it pins the key |
| `authentication failed` | The generated public key is not in `authorized_keys`, or its permissions are wrong (`700` on `.ssh`, `600` on the file) |
| Deploy fails only on `sudo systemctl` | The sudoers entry is missing or does not match the command exactly, including the full binary path |

## Alternative: install the agent

The steps above set up the SSH bridge, which needs no software on the server.
If you prefer agent-driven deployments (Docker builds, health-gated
zero-downtime switching, heartbeats with CPU/memory/disk metrics), mint a
registration token with the **Agent** button on the server row and follow
[Agent protocol](agent-protocol.md). The SSH bridge keeps working either way —
deploys use the agent whenever one is registered for the server.
