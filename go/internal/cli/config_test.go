package cli

import (
	"os"
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
