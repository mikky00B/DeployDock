package caddy

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/deploydock/deploydock/go/internal/engine"
)

func TestConfigureValidationFailureRestoresPreviousBlock(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "app.caddy")
	previous := "# last good block\n:80 {\n    reverse_proxy 127.0.0.1:4000\n}\n"
	if err := os.WriteFile(path, []byte(previous), 0o644); err != nil {
		t.Fatalf("seed previous block: %v", err)
	}

	// A caddy binary that cannot run makes Validate fail deterministically,
	// exercising the restore path without a real Caddy install.
	m := &Manager{ConfDir: dir, Bin: "deploydock-no-such-caddy"}
	err := m.Configure(context.Background(), engine.ProxyConfig{AppName: "app", Port: 45671})
	if err == nil || !strings.Contains(err.Error(), "validation failed") {
		t.Fatalf("Configure error = %v, want a validation failure", err)
	}

	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("previous block was deleted, want it restored: %v", err)
	}
	if string(got) != previous {
		t.Errorf("block = %q, want the previous content restored", got)
	}
}

func TestConfigureValidationFailureRemovesBlockWhenNoneExisted(t *testing.T) {
	dir := t.TempDir()
	m := &Manager{ConfDir: dir, Bin: "deploydock-no-such-caddy"}

	err := m.Configure(context.Background(), engine.ProxyConfig{AppName: "app", Port: 45671})
	if err == nil || !strings.Contains(err.Error(), "validation failed") {
		t.Fatalf("Configure error = %v, want a validation failure", err)
	}
	if _, statErr := os.Stat(filepath.Join(dir, "app.caddy")); !os.IsNotExist(statErr) {
		t.Errorf("newly-written bad block must be removed on rollback, stat error = %v", statErr)
	}
}

func TestRenderBlock(t *testing.T) {
	withDomains := renderBlock(engine.ProxyConfig{AppName: "app", Port: 45671, Domains: []string{"app.example.com", "www.example.com"}})
	if !strings.HasPrefix(withDomains, "# Managed by DeployDock") {
		t.Errorf("block must be marked as managed:\n%s", withDomains)
	}
	if !strings.Contains(withDomains, "app.example.com, www.example.com {") {
		t.Errorf("domains must become site addresses:\n%s", withDomains)
	}
	if !strings.Contains(withDomains, "reverse_proxy 127.0.0.1:45671") {
		t.Errorf("block must target the published loopback port:\n%s", withDomains)
	}

	catchAll := renderBlock(engine.ProxyConfig{AppName: "app", Port: 4000})
	if !strings.Contains(catchAll, ":80 {") {
		t.Errorf("domainless app must bind the HTTP catch-all:\n%s", catchAll)
	}
}
