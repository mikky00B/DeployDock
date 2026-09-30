// CLI tests against a stub control plane (spec §61: CLI → FastAPI).
package cli

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// stubControlPlane is a fake FastAPI covering the endpoints the CLI uses.
type stubControlPlane struct {
	server    *httptest.Server
	loginHits int
	deployID  string
}

func newStubControlPlane(t *testing.T) *stubControlPlane {
	t.Helper()
	stub := &stubControlPlane{deployID: "d-1"}
	mux := http.NewServeMux()

	mux.HandleFunc("/api/v1/auth/login", func(w http.ResponseWriter, r *http.Request) {
		stub.loginHits++
		var body map[string]string
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["email"] != "dev@example.com" || body["password"] != "hunter2" {
			http.Error(w, `{"detail":"Incorrect email or password"}`, http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"token":{"access_token":"jwt-1","token_type":"bearer"},"user":{"email":"dev@example.com","full_name":"Dev"}}`))
	})
	mux.HandleFunc("/api/v1/auth/me", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer jwt-1" {
			http.Error(w, `{"detail":"Not authenticated"}`, http.StatusUnauthorized)
			return
		}
		_, _ = w.Write([]byte(`{"email":"dev@example.com","full_name":"Dev"}`))
	})
	mux.HandleFunc("/api/v1/apps", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer jwt-1" {
			http.Error(w, `{"detail":"Not authenticated"}`, http.StatusUnauthorized)
			return
		}
		switch r.Method {
		case http.MethodGet:
			_, _ = w.Write([]byte(`[{"id":"a-1","name":"watchdog","server_id":"s-1","repository_url":"https://github.com/example/watchdog.git","branch":"main","app_path":"/opt/watchdog","current_commit":"a81f92cdeadbeef","deploy_command":"make build"}]`))
		case http.MethodPost:
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"id":"a-2","name":"new-project","server_id":"s-1","repository_url":"r","branch":"main","app_path":"/opt/new","deploy_command":"make"}`))
		}
	})
	mux.HandleFunc("/api/v1/servers", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`[{"id":"s-1","name":"prod","host":"203.0.113.10","status":"connected"}]`))
	})
	mux.HandleFunc("/api/v1/apps/a-1/deploy", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"id":"d-1","app_id":"a-1","status":"pending","kind":"deploy"}`))
	})
	mux.HandleFunc("/api/v1/deployments/d-1/stream", func(w http.ResponseWriter, r *http.Request) {
		streamDeployment(w, []string{
			"event: log\ndata: {\"stream\":\"system\",\"line\":\"Stage started: clone\"}\n\n",
			"event: log\ndata: {\"stream\":\"stdout\",\"line\":\"Cloned in 1.2s\"}\n\n",
			"event: status\ndata: {\"status\":\"success\"}\n\n",
		})
	})
	mux.HandleFunc("/api/v1/deployments/d-2/stream", func(w http.ResponseWriter, r *http.Request) {
		streamDeployment(w, []string{
			"event: log\ndata: {\"stream\":\"system\",\"line\":\"Restoring deployment\"}\n\n",
			"event: status\ndata: {\"status\":\"success\"}\n\n",
		})
	})
	mux.HandleFunc("/api/v1/apps/a-1/deployments", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`[{"id":"d-1","app_id":"a-1","status":"success","kind":"deploy","commit_sha":"a81f92c"}]`))
	})
	mux.HandleFunc("/api/v1/deployments/d-1/rollback", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"id":"d-2","app_id":"a-1","status":"pending","kind":"rollback"}`))
	})
	mux.HandleFunc("/api/v1/deployments/d-1/logs", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`[{"stream":"system","line":"Deployment succeeded","sequence":1}]`))
	})
	mux.HandleFunc("/api/v1/dashboard", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"summary":{"total_servers":2,"connected_servers":1,"total_apps":1,"deployed_apps":1,"recent_failures":0,"latest_deployment_status":"success"}}`))
	})

	stub.server = httptest.NewServer(mux)
	t.Cleanup(stub.server.Close)
	return stub
}

func streamDeployment(w http.ResponseWriter, events []string) {
	w.Header().Set("Content-Type", "text/event-stream")
	flusher := w.(http.Flusher)
	for _, event := range events {
		_, _ = fmt.Fprint(w, event)
		flusher.Flush()
	}
}

func withConfig(t *testing.T, apiURL, token string) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "config.yaml")
	if err := os.WriteFile(path, []byte(fmt.Sprintf("api_url: %s\ntoken: %s\n", apiURL, token)), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("DEPLOYDOCK_CONFIG", path)
}

func TestLoginStoresTokenAndWhoamiReadsIt(t *testing.T) {
	stub := newStubControlPlane(t)
	withConfig(t, stub.server.URL, "")

	// Wrong credentials fail.
	if err := CmdLogin(context.Background(), stub.server.URL, "dev@example.com", "wrong"); err == nil {
		t.Fatal("expected login with wrong password to fail")
	}
	if err := CmdLogin(context.Background(), stub.server.URL, "dev@example.com", "hunter2"); err != nil {
		t.Fatalf("login failed: %v", err)
	}

	config, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if config.Token != "jwt-1" || config.APIURL != stub.server.URL {
		t.Errorf("stored config = %+v", config)
	}

	if err := CmdWhoami(context.Background()); err != nil {
		t.Fatalf("whoami failed: %v", err)
	}
}

func TestProjectsListAndCreate(t *testing.T) {
	stub := newStubControlPlane(t)
	withConfig(t, stub.server.URL, "jwt-1")

	if err := CmdProjects(context.Background(), false); err != nil {
		t.Fatalf("projects failed: %v", err)
	}
	// Create with no --server uses the single registered server.
	if err := CmdProjectCreate(context.Background(), "new-project", "", "r", "", "", "make", "", "", 0); err != nil {
		t.Fatalf("project create failed: %v", err)
	}
}

func TestDeployFollowsStreamToSuccess(t *testing.T) {
	stub := newStubControlPlane(t)
	withConfig(t, stub.server.URL, "jwt-1")

	// Project name from deploydock.yaml in the working directory.
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "deploydock.yaml"), []byte("name: watchdog\ndeploy:\n  port: 8080\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	original, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(original) })

	if err := CmdDeploy(context.Background(), "", ""); err != nil {
		t.Fatalf("deploy failed: %v", err)
	}
}

func TestRollbackDefaultsToLatestDeployment(t *testing.T) {
	stub := newStubControlPlane(t)
	withConfig(t, stub.server.URL, "jwt-1")

	if err := CmdRollback(context.Background(), "watchdog", ""); err != nil {
		t.Fatalf("rollback failed: %v", err)
	}
}

func TestLogsPrintsLines(t *testing.T) {
	stub := newStubControlPlane(t)
	withConfig(t, stub.server.URL, "jwt-1")

	if err := CmdLogs(context.Background(), "watchdog", ""); err != nil {
		t.Fatalf("logs failed: %v", err)
	}
}

func TestStatusPrintsSummary(t *testing.T) {
	stub := newStubControlPlane(t)
	withConfig(t, stub.server.URL, "jwt-1")

	if err := CmdStatus(context.Background(), false); err != nil {
		t.Fatalf("status failed: %v", err)
	}
}

func TestRequireAuthRejectsWhenNotSignedIn(t *testing.T) {
	stub := newStubControlPlane(t)
	withConfig(t, stub.server.URL, "")

	err := CmdWhoami(context.Background())
	if err == nil || !strings.Contains(err.Error(), "not signed in") {
		t.Fatalf("err = %v, want not-signed-in error", err)
	}
}

func TestProjectConfigParsing(t *testing.T) {
	path := filepath.Join(t.TempDir(), "deploydock.yaml")
	content := "name: watchdog\n\nbuild:\n  type: docker\n\ndeploy:\n  port: 8080\n\nhealth:\n  path: /health\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	project, err := LoadProjectConfig(path)
	if err != nil {
		t.Fatal(err)
	}
	if project.Name != "watchdog" || project.Port != 8080 {
		t.Errorf("project = %+v", project)
	}
}
