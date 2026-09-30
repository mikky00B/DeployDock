// Package nginx implements engine.ProxyManager by writing managed config
// files and reloading nginx (spec §35).
//
// Managed configs live in their own include directory and are clearly
// separated from user-managed configuration; unrelated configs are never
// touched. A failed validation aborts the reload so a bad config can never
// take nginx down.
package nginx

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/deploydock/deploydock/go/internal/engine"
)

// Manager is a CLI-backed ProxyManager.
type Manager struct {
	// ConfDir holds managed configs; defaults to /etc/nginx/deploydock.
	ConfDir string
	// Bin overrides binaries (tests); default "nginx".
	Bin string
	// ReloadCommand reloads nginx; defaults to systemctl reload nginx.
	ReloadCommand string
}

func (m *Manager) confDir() string {
	if m.ConfDir != "" {
		return m.ConfDir
	}
	return "/etc/nginx/deploydock"
}

func (m *Manager) binary() string {
	if m.Bin != "" {
		return m.Bin
	}
	return "nginx"
}

func (m *Manager) reloadCommand() string {
	if m.ReloadCommand != "" {
		return m.ReloadCommand
	}
	return "systemctl reload nginx"
}

// Configure writes one managed server block, validates the whole nginx
// configuration, and reloads only when validation passes.
func (m *Manager) Configure(ctx context.Context, cfg engine.ProxyConfig) error {
	if err := os.MkdirAll(m.confDir(), 0o755); err != nil {
		return fmt.Errorf("create managed config dir: %w", err)
	}
	path := filepath.Join(m.confDir(), cfg.AppName+".conf")
	config := renderConfig(cfg)
	if err := os.WriteFile(path, []byte(config), 0o644); err != nil { //nolint:gosec // world-readable nginx config is fine
		return fmt.Errorf("write %s: %w", path, err)
	}
	if err := m.Validate(ctx); err != nil {
		// Roll the bad config back so nginx keeps its last good state.
		_ = os.Remove(path)
		return fmt.Errorf("validation failed (config rolled back): %w", err)
	}
	return m.Reload(ctx)
}

// Validate runs `nginx -t`.
func (m *Manager) Validate(ctx context.Context) error {
	cmd := exec.CommandContext(ctx, m.binary(), "-t")
	var stderr strings.Builder
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("nginx -t: %w: %s", err, strings.TrimSpace(stderr.String()))
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

// renderConfig renders one managed server block. Upstreams always bind to the
// loopback published port of the current release container.
func renderConfig(cfg engine.ProxyConfig) string {
	var b strings.Builder
	serverNames := "_"
	if len(cfg.Domains) > 0 {
		serverNames = strings.Join(cfg.Domains, " ")
	}
	b.WriteString("# Managed by DeployDock — edits will be overwritten.\n")
	b.WriteString("server {\n")
	b.WriteString("    listen 80;\n")
	fmt.Fprintf(&b, "    server_name %s;\n\n", serverNames)
	fmt.Fprintf(&b, "    location / {\n")
	fmt.Fprintf(&b, "        proxy_pass http://127.0.0.1:%d;\n", cfg.Port)
	b.WriteString("        proxy_set_header Host $host;\n")
	b.WriteString("        proxy_set_header X-Real-IP $remote_addr;\n")
	b.WriteString("        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n")
	b.WriteString("        proxy_set_header X-Forwarded-Proto $scheme;\n")
	b.WriteString("    }\n")
	b.WriteString("}\n")
	return b.String()
}
