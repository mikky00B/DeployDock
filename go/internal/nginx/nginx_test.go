package nginx

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/deploydock/deploydock/go/internal/engine"
)

// failingValidate returns a Manager whose validate command cannot run, so
// Configure always fails validation and exercises the rollback path.
func failingValidate(t *testing.T, dir string) *Manager {
	t.Helper()
	return &Manager{
		ConfDir: dir,
		Bin:     "deploydock-no-such-nginx-binary",
	}
}

func TestConfigureValidationFailureRestoresPreviousConfig(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "app.conf")
	previous := "# last good config\nserver { listen 80; }\n"
	if err := os.WriteFile(path, []byte(previous), 0o644); err != nil {
		t.Fatalf("seed previous config: %v", err)
	}

	m := failingValidate(t, dir)
	err := m.Configure(context.Background(), engine.ProxyConfig{AppName: "app", Port: 45671})
	if err == nil || !strings.Contains(err.Error(), "validation failed") {
		t.Fatalf("Configure error = %v, want a validation failure", err)
	}

	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("previous config was deleted, want it restored: %v", err)
	}
	if string(got) != previous {
		t.Errorf("config = %q, want the previous content restored", got)
	}
	assertNoTempFiles(t, dir)
}

func TestConfigureValidationFailureRemovesConfigWhenNoneExisted(t *testing.T) {
	dir := t.TempDir()
	m := failingValidate(t, dir)

	err := m.Configure(context.Background(), engine.ProxyConfig{AppName: "app", Port: 45671})
	if err == nil || !strings.Contains(err.Error(), "validation failed") {
		t.Fatalf("Configure error = %v, want a validation failure", err)
	}

	if _, statErr := os.Stat(filepath.Join(dir, "app.conf")); !os.IsNotExist(statErr) {
		t.Errorf("newly-written bad config must be removed on rollback, stat error = %v", statErr)
	}
	assertNoTempFiles(t, dir)
}

func assertNoTempFiles(t *testing.T, dir string) {
	t.Helper()
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("read config dir: %v", err)
	}
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), ".deploydock-") {
			t.Errorf("temp file %s leaked in %s", entry.Name(), dir)
		}
	}
}
