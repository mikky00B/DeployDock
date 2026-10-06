// Registration of the DeployDock MCP server with installed coding agents.
//
// Each agent has its own config format; we merge a "deploydock" entry into
// the existing file rather than replacing it, and never write secrets
// anywhere except the agent's own config file (0600 where the format allows).
package cli

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// MCPEntry is one mcpServers registration.
type MCPEntry struct {
	Command string            `json:"command"`
	Args    []string          `json:"args"`
	Env     map[string]string `json:"env"`
}

// BuildMCPEntry assembles the registration from the current executable and
// the stored control-plane credentials.
func BuildMCPEntry(apiURL, token string) (MCPEntry, error) {
	executable, err := os.Executable()
	if err != nil {
		return MCPEntry{}, fmt.Errorf("could not locate the deploydock binary: %w", err)
	}
	return MCPEntry{
		Command: executable,
		Args:    []string{"mcp", "serve"},
		Env:     map[string]string{"DEPLOYDOCK_URL": apiURL, "DEPLOYDOCK_TOKEN": token},
	}, nil
}

// SetupAgents registers the MCP entry with the requested agents and returns a
// per-agent result line. baseDir is the user's home directory (injected for
// testability). Unknown agents are reported as errors, not silently skipped.
func SetupAgents(baseDir string, agents []string, entry MCPEntry) ([]string, error) {
	results := make([]string, 0, len(agents))
	for _, agent := range agents {
		var err error
		var result string
		switch strings.ToLower(strings.TrimSpace(agent)) {
		case "claude":
			err = registerJSON(filepath.Join(baseDir, ".claude.json"), entry)
			result = "claude code"
		case "cursor":
			err = registerJSON(filepath.Join(baseDir, ".cursor", "mcp.json"), entry)
			result = "cursor"
		case "codex":
			err = registerCodex(filepath.Join(baseDir, ".codex", "config.toml"), entry)
			result = "codex"
		default:
			return results, fmt.Errorf("unknown agent %q (supported: claude, cursor, codex)", agent)
		}
		if err != nil {
			return results, fmt.Errorf("%s: %w", result, err)
		}
		results = append(results, result)
	}
	return results, nil
}

// registerJSON merges {"mcpServers": {"deploydock": entry}} into a JSON file,
// preserving every other top-level key.
func registerJSON(path string, entry MCPEntry) error {
	config := map[string]json.RawMessage{}
	if raw, err := os.ReadFile(path); err == nil { //nolint:gosec // path from the caller
		if err := json.Unmarshal(raw, &config); err != nil {
			return fmt.Errorf("%s is not valid JSON: %w", path, err)
		}
	}

	var servers map[string]MCPEntry
	if existing, ok := config["mcpServers"]; ok && len(existing) > 0 {
		if err := json.Unmarshal(existing, &servers); err != nil {
			return fmt.Errorf("%s has a malformed mcpServers section: %w", path, err)
		}
	}
	if servers == nil {
		servers = map[string]MCPEntry{}
	}
	servers["deploydock"] = entry
	updated, err := json.MarshalIndent(servers, "", "  ")
	if err != nil {
		return err
	}
	config["mcpServers"] = json.RawMessage(updated)

	output, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	return os.WriteFile(path, output, 0o600) //nolint:gosec // contains the credential by design
}

const codexSectionMarker = "[mcp_servers.deploydock]"

// registerCodex writes the [mcp_servers.deploydock] TOML section, replacing
// an existing section if present. Codex configs are small; a textual splice
// avoids a TOML dependency.
func registerCodex(path string, entry MCPEntry) error {
	section := fmt.Sprintf(
		"%s\ncommand = %q\nargs = [%q, %q]\n\n[mcp_servers.deploydock.env]\nDEPLOYDOCK_URL = %q\nDEPLOYDOCK_TOKEN = %q\n",
		codexSectionMarker, entry.Command, entry.Args[0], entry.Args[1],
		entry.Env["DEPLOYDOCK_URL"], entry.Env["DEPLOYDOCK_TOKEN"],
	)

	var updated string
	raw, err := os.ReadFile(path) //nolint:gosec // path from the caller
	if err != nil {
		updated = section
	} else {
		content := string(raw)
		start := strings.Index(content, codexSectionMarker)
		if start < 0 {
			updated = strings.TrimRight(content, "\n") + "\n\n" + section
		} else {
			end := len(content)
			if next := strings.Index(content[start+1:], "\n[mcp_servers."); next >= 0 {
				end = start + 1 + next + 1 // keep the newline before the next section
			}
			updated = content[:start] + section + content[end:]
		}
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	return os.WriteFile(path, []byte(updated), 0o600) //nolint:gosec // contains the credential by design
}
