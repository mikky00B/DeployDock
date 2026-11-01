// Package caddy implements engine.ProxyManager by writing managed per-app
// Caddyfile blocks and reloading Caddy (v3 spec §4.2).
//
// It mirrors the nginx manager's safety model: managed blocks live in their
// own include directory, the block is validated with `caddy validate` before
// any reload, and a failed validation restores the previous file instead of
// deleting it. Caddy provisions and renews TLS automatically for site
// addresses whose DNS points at the host; blocks without domains bind to the
// plain HTTP catch-all port.
package caddy

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/deploydock/deploydock/go/internal/confwrite"
	"github.com/deploydock/deploydock/go/internal/engine"
)

// Manager is a CLI-backed ProxyManager.
type Manager struct {
	// ConfDir holds managed per-app blocks, imported by the host's main
	// Caddyfile; defaults to /etc/caddy/deploydock.
	ConfDir string
	// Bin overrides the caddy binary (tests); default "caddy".
	Bin string
	// ReloadCommand reloads Caddy; defaults to systemctl reload caddy.
	ReloadCommand string
}

func (m *Manager) confDir() string {
	if m.ConfDir != "" {
		return m.ConfDir
	}
	return "/etc/caddy/deploydock"
}

func (m *Manager) binary() string {
	if m.Bin != "" {
		return m.Bin
	}
	return "caddy"
}

func (m *Manager) reloadCommand() string {
	if m.ReloadCommand != "" {
		return m.ReloadCommand
	}
	return "systemctl reload caddy"
}

// Configure writes one managed Caddyfile block, validates it, and reloads
// only when validation passes.
func (m *Manager) Configure(ctx context.Context, cfg engine.ProxyConfig) error {
	if err := os.MkdirAll(m.confDir(), 0o755); err != nil {
		return fmt.Errorf("create managed config dir: %w", err)
	}
	path := filepath.Join(m.confDir(), cfg.AppName+".caddy")
	config := renderBlock(cfg)

	previous, hadPrevious, err := confwrite.ReadIfExists(path)
	if err != nil {
		return fmt.Errorf("read previous config %s: %w", path, err)
	}

	if err := confwrite.WriteAtomic(path, []byte(config), 0o644); err != nil {
		return fmt.Errorf("write %s: %w", path, err)
	}
	if err := m.Validate(ctx, path); err != nil {
		// Keep the file on disk consistent with the running server: restore
		// the last good block rather than deleting it.
		if restoreErr := confwrite.Restore(path, previous, hadPrevious); restoreErr != nil {
			return fmt.Errorf("validation failed (restore previous config: %v): %w", restoreErr, err)
		}
		return fmt.Errorf("validation failed (config rolled back): %w", err)
	}
	return m.Reload(ctx)
}

// Validate runs `caddy validate` against one managed block.
func (m *Manager) Validate(ctx context.Context, path string) error {
	cmd := exec.CommandContext(ctx, m.binary(), "validate", "--config", path, "--adapter", "caddyfile")
	var stderr strings.Builder
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("caddy validate: %w: %s", err, strings.TrimSpace(stderr.String()))
	}
	return nil
}

// Reload runs the reload command.
func (m *Manager) Reload(ctx context.Context) error {
	parts := strings.Fields(m.reloadCommand())
	cmd := exec.CommandContext(ctx, parts[0], parts[1:]...)
	var stderr strings.Builder
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("%s: %w: %s", m.reloadCommand(), err, strings.TrimSpace(stderr.String()))
	}
	return nil
}

// renderBlock renders one managed site block. Site addresses without domains
// fall back to the plain HTTP catch-all port; with domains, Caddy manages
// TLS issuance and renewal for them.
func renderBlock(cfg engine.ProxyConfig) string {
	var b strings.Builder
	siteAddresses := ":80"
	if len(cfg.Domains) > 0 {
		siteAddresses = strings.Join(cfg.Domains, ", ")
	}
	b.WriteString("# Managed by DeployDock — edits will be overwritten.\n")
	fmt.Fprintf(&b, "%s {\n", siteAddresses)
	fmt.Fprintf(&b, "    reverse_proxy 127.0.0.1:%d\n", cfg.Port)
	b.WriteString("}\n")
	return b.String()
}
