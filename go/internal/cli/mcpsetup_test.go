// MCP setup registration tests: Claude Code, Cursor, Codex config writing.
package cli

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func testEntry() MCPEntry {
	return MCPEntry{
		Command: "/usr/local/bin/deploydock",
		Args:    []string{"mcp", "serve"},
		Env:     map[string]string{"DEPLOYDOCK_URL": "http://127.0.0.1:8000", "DEPLOYDOCK_TOKEN": "tok-1"},
	}
}

func TestSetupAgentsRegistersAllThree(t *testing.T) {
	home := t.TempDir()

	results, err := SetupAgents(home, []string{"claude", "cursor", "codex"}, testEntry())
	if err != nil {
		t.Fatalf("SetupAgents failed: %v", err)
	}
	if len(results) != 3 {
		t.Fatalf("results = %v", results)
	}

	// Claude Code: merged into ~/.claude.json under mcpServers.
	claudeRaw, err := os.ReadFile(filepath.Join(home, ".claude.json"))
	if err != nil {
		t.Fatal(err)
	}
	var claude map[string]any
	if err := json.Unmarshal(claudeRaw, &claude); err != nil {
		t.Fatal(err)
	}
	servers := claude["mcpServers"].(map[string]any)
	entry := servers["deploydock"].(map[string]any)
	if entry["command"] != "/usr/local/bin/deploydock" {
		t.Errorf("claude entry = %v", entry)
	}
	if claude["someOtherKey"] != nil {
		t.Log("other keys preserved") // asserted below with a pre-seeded file
	}

	// Cursor: ~/.cursor/mcp.json.
	cursorRaw, err := os.ReadFile(filepath.Join(home, ".cursor", "mcp.json"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(cursorRaw), `"deploydock"`) {
		t.Errorf("cursor config missing deploydock: %s", cursorRaw)
	}

	// Codex: ~/.codex/config.toml with a TOML section.
	codexRaw, err := os.ReadFile(filepath.Join(home, ".codex", "config.toml"))
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"[mcp_servers.deploydock]", "DEPLOYDOCK_TOKEN", "mcp\", \"serve"} {
		if !strings.Contains(string(codexRaw), want) {
			t.Errorf("codex config missing %q: %s", want, codexRaw)
		}
	}
}

func TestSetupAgentsPreservesExistingClaudeConfig(t *testing.T) {
	home := t.TempDir()
	claudePath := filepath.Join(home, ".claude.json")
	existing := `{"theme":"dark","mcpServers":{"other":{"command":"x"}},"num":3}`
	if err := os.WriteFile(claudePath, []byte(existing), 0o600); err != nil {
		t.Fatal(err)
	}

	if _, err := SetupAgents(home, []string{"claude"}, testEntry()); err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(claudePath)
	var config map[string]any
	if err := json.Unmarshal(raw, &config); err != nil {
		t.Fatal(err)
	}
	if config["theme"] != "dark" || config["num"] != float64(3) {
		t.Errorf("existing keys lost: %v", config)
	}
	servers := config["mcpServers"].(map[string]any)
	if _, ok := servers["other"]; !ok {
		t.Error("pre-existing mcpServers entry lost")
	}
	if _, ok := servers["deploydock"]; !ok {
		t.Error("deploydock entry missing")
	}
}

func TestSetupAgentsReplacesStaleCodexSection(t *testing.T) {
	home := t.TempDir()
	codexPath := filepath.Join(home, ".codex", "config.toml")
	if err := os.MkdirAll(filepath.Dir(codexPath), 0o700); err != nil {
		t.Fatal(err)
	}
	stale := "model = \"gpt\"\n\n[mcp_servers.deploydock]\ncommand = \"/old/path\"\n\n[mcp_servers.other]\ncommand = \"keep\"\n"
	if err := os.WriteFile(codexPath, []byte(stale), 0o600); err != nil {
		t.Fatal(err)
	}

	if _, err := SetupAgents(home, []string{"codex"}, testEntry()); err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(codexPath)
	content := string(raw)
	if strings.Contains(content, "/old/path") {
		t.Errorf("stale command survived: %s", content)
	}
	if !strings.Contains(content, "/usr/local/bin/deploydock") {
		t.Errorf("new command missing: %s", content)
	}
	// The neighboring section must survive the splice.
	if !strings.Contains(content, "[mcp_servers.other]") {
		t.Errorf("neighboring section lost: %s", content)
	}
}

func TestSetupAgentsRejectsUnknownAgent(t *testing.T) {
	home := t.TempDir()
	if _, err := SetupAgents(home, []string{"hal"}, testEntry()); err == nil {
		t.Fatal("expected error for unknown agent")
	}
}
