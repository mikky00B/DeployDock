package cli

import (
	"os"
	"path/filepath"
	"testing"
)

func TestResolveCredentialsEnvFallbacks(t *testing.T) {
	t.Setenv("DEPLOYDOCK_URL", "https://dock.example.com")
	t.Setenv("DEPLOYDOCK_TOKEN", "tok-env")

	// Empty config fields fall back to the mcp-setup environment.
	url, token := ResolveCredentials("", "")
	if url != "https://dock.example.com" || token != "tok-env" {
		t.Errorf("ResolveCredentials() = %q, %q; want env values", url, token)
	}

	// Stored config wins over the environment.
	url, token = ResolveCredentials("http://127.0.0.1:8000", "tok-file")
	if url != "http://127.0.0.1:8000" || token != "tok-file" {
		t.Errorf("ResolveCredentials() = %q, %q; want stored config values", url, token)
	}

	// URL-only fallback also applies the default address.
	os.Unsetenv("DEPLOYDOCK_TOKEN")
	url, token = ResolveCredentials("", "")
	if url != "https://dock.example.com" || token != "" {
		t.Errorf("ResolveCredentials() = %q, %q; want env url and empty token", url, token)
	}

	os.Unsetenv("DEPLOYDOCK_URL")
	url, _ = ResolveCredentials("", "")
	if url != "http://127.0.0.1:8000" {
		t.Errorf("ResolveCredentials() url = %q; want the default control-plane address", url)
	}
}

func TestLoadProjectConfigSectionsAndValidation(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "deploydock.yaml")

	valid := `# project config
name: my-app # inline comment

deploy:
  port: 8080 # app port

health:
  path: /healthz

env:
  path: /usr/local/bin
`
	if err := os.WriteFile(path, []byte(valid), 0o644); err != nil {
		t.Fatal(err)
	}
	project, err := LoadProjectConfig(path)
	if err != nil {
		t.Fatalf("LoadProjectConfig() unexpected error: %v", err)
	}
	if project.Name != "my-app" || project.Port != 8080 || project.Health != "/healthz" {
		t.Fatalf("LoadProjectConfig() = %+v, want {Name:my-app Port:8080 Health:/healthz}", project)
	}

	// Invalid port
	if err := os.WriteFile(path, []byte("name: my-app\ndeploy:\n  port: 99999\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadProjectConfig(path); err == nil {
		t.Fatal("expected error for out-of-range port 99999")
	}

	// Invalid health path
	if err := os.WriteFile(path, []byte("name: my-app\nhealth:\n  path: healthz\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadProjectConfig(path); err == nil {
		t.Fatal("expected error for health.path without leading slash")
	}
}
