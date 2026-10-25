// MCP stdio server tests: protocol handshake, tools/list, tools/call against
// a stub control plane.
package mcp

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/deploydock/deploydock/go/internal/cli"
)

// runServer feeds lines into a Server bound to a stub API and returns one
// parsed response per input line that expects one.
func runServer(t *testing.T, api *cli.API, lines []string) []map[string]any {
	t.Helper()
	var in bytes.Buffer
	for _, line := range lines {
		in.WriteString(line + "\n")
	}
	var out bytes.Buffer
	server := &Server{API: api, In: &in, Out: &out}
	if err := server.Run(context.Background()); err != nil {
		t.Fatalf("server run failed: %v", err)
	}

	responses := []map[string]any{}
	for _, line := range strings.Split(out.String(), "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var parsed map[string]any
		if err := json.Unmarshal([]byte(line), &parsed); err != nil {
			t.Fatalf("response is not valid JSON (%q): %v", line, err)
		}
		responses = append(responses, parsed)
	}
	return responses
}

func newStubAPI(t *testing.T, handler http.HandlerFunc) *cli.API {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	return NewTestAPI(server.URL)
}

func TestInitializeReturnsProtocolVersionAndCapabilities(t *testing.T) {
	api := newStubAPI(t, func(w http.ResponseWriter, _ *http.Request) {})
	responses := runServer(t, api, []string{
		`{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}`,
	})
	if len(responses) != 1 {
		t.Fatalf("responses = %d, want 1", len(responses))
	}
	result, ok := responses[0]["result"].(map[string]any)
	if !ok {
		t.Fatalf("missing result: %v", responses[0])
	}
	if result["protocolVersion"] != protocolVersion {
		t.Errorf("protocolVersion = %v", result["protocolVersion"])
	}
	if _, ok := result["serverInfo"]; !ok {
		t.Error("missing serverInfo")
	}
}

func TestNotificationsProduceNoResponse(t *testing.T) {
	api := newStubAPI(t, func(w http.ResponseWriter, _ *http.Request) {})
	responses := runServer(t, api, []string{
		`{"jsonrpc":"2.0","method":"notifications/initialized"}`,
		`{"jsonrpc":"2.0","id":2,"method":"ping"}`,
	})
	if len(responses) != 1 {
		t.Fatalf("notification produced a response (%d responses), want exactly one ping answer", len(responses))
	}
}

func TestToolsListReturnsEightTools(t *testing.T) {
	api := newStubAPI(t, func(w http.ResponseWriter, _ *http.Request) {})
	responses := runServer(t, api, []string{
		`{"jsonrpc":"2.0","id":3,"method":"tools/list"}`,
	})
	result := responses[0]["result"].(map[string]any)
	tools := result["tools"].([]any)
	if len(tools) != 8 {
		t.Fatalf("tools count = %d, want 8", len(tools))
	}
	names := map[string]bool{}
	for _, tool := range tools {
		names[tool.(map[string]any)["name"].(string)] = true
	}
	for _, want := range []string{"list_servers", "list_apps", "get_dashboard", "deploy_app", "get_deployment", "get_latest_deployment_logs", "rollback", "cancel_deployment"} {
		if !names[want] {
			t.Errorf("missing tool %q", want)
		}
	}
}

func TestToolCallDeployAppHitsControlPlane(t *testing.T) {
	var gotPath, gotMethod string
	api := newStubAPI(t, func(w http.ResponseWriter, r *http.Request) {
		gotPath, gotMethod = r.URL.Path, r.Method
		switch {
		case r.URL.Path == "/api/v1/apps" && r.Method == http.MethodGet:
			_, _ = w.Write([]byte(`[{"id":"a-1","name":"watchdog","server_id":"s-1","repository_url":"r","branch":"main","app_path":"/opt/watchdog"}]`))
		case r.URL.Path == "/api/v1/apps/a-1/deploy" && r.Method == http.MethodPost:
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"id":"d-9","app_id":"a-1","status":"pending","kind":"deploy"}`))
		default:
			http.Error(w, "unexpected", http.StatusNotFound)
		}
	})
	responses := runServer(t, api, []string{
		`{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"deploy_app","arguments":{"app":"watchdog"}}}`,
	})
	if gotPath != "/api/v1/apps/a-1/deploy" || gotMethod != http.MethodPost {
		t.Fatalf("control plane got %s %s", gotMethod, gotPath)
	}
	result := responses[0]["result"].(map[string]any)
	if result["isError"] == true {
		t.Fatalf("tool call errored: %v", result["content"])
	}
	content := result["content"].([]any)[0].(map[string]any)
	if !strings.Contains(content["text"].(string), "watchdog") || !strings.Contains(content["text"].(string), "d-9") {
		t.Errorf("tool text = %v", content["text"])
	}
}

func TestToolCallSurfacesAPIErrorsAsIsErrorContent(t *testing.T) {
	api := newStubAPI(t, func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"detail":"app \"nope\" not found"}`, http.StatusNotFound)
	})
	responses := runServer(t, api, []string{
		`{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"deploy_app","arguments":{"app":"nope"}}}`,
	})
	result := responses[0]["result"].(map[string]any)
	if result["isError"] != true {
		t.Fatalf("expected isError content, got %v", result)
	}
}

func TestUnknownToolReturnsIsErrorNotCrash(t *testing.T) {
	api := newStubAPI(t, func(w http.ResponseWriter, _ *http.Request) {})
	responses := runServer(t, api, []string{
		`{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"no_such_tool","arguments":{}}}`,
	})
	result := responses[0]["result"].(map[string]any)
	if result["isError"] != true {
		t.Fatalf("expected isError for unknown tool, got %v", result)
	}
}

func TestMalformedLineGetsParseErrorAndLoopContinues(t *testing.T) {
	api := newStubAPI(t, func(w http.ResponseWriter, _ *http.Request) {})
	responses := runServer(t, api, []string{
		`not json at all`,
		`{"jsonrpc":"2.0","id":8,"method":"ping"}`,
	})
	if len(responses) != 2 {
		t.Fatalf("responses = %d, want 2 (parse error + ping)", len(responses))
	}
	errObj := responses[0]["error"].(map[string]any)
	if errObj["code"] != float64(-32700) {
		t.Errorf("parse error code = %v", errObj["code"])
	}
}
