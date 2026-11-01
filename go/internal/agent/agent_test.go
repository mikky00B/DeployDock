package agent

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/deploydock/deploydock/go/internal/config"
)

// writeState stores agent state in a temp file and points the config loader
// at it for the duration of the test.
func writeState(t *testing.T, controlPlaneURL string) *config.State {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")
	t.Setenv("DEPLOYDOCK_AGENT_CONFIG", path)

	state := &config.State{
		ControlPlaneURL:          controlPlaneURL,
		AgentID:                  "agent-1",
		AgentToken:               "tok",
		HeartbeatIntervalSeconds: 3600, // no tick during the test; the first beat is immediate
	}
	if err := config.Save(state); err != nil {
		t.Fatalf("save state: %v", err)
	}
	return state
}

// fakeControlPlane answers the two endpoints the agent loop hits: an
// immediately-OK heartbeat and an empty command queue. It counts requests so
// tests can assert on loop behavior.
type fakeControlPlane struct {
	mu         sync.Mutex
	heartbeats int
	polls      int
	nextPoll   int // polls remaining that answer 409 before going back to empty
}

func (f *fakeControlPlane) handler(t *testing.T) http.Handler {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/v1/agents/agent-1/heartbeat", func(w http.ResponseWriter, _ *http.Request) {
		f.mu.Lock()
		f.heartbeats++
		f.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "ok", "heartbeat_interval_seconds": 3600})
	})
	mux.HandleFunc("GET /api/v1/agents/agent-1/commands", func(w http.ResponseWriter, _ *http.Request) {
		f.mu.Lock()
		f.polls++
		conflict := f.nextPoll > 0
		if conflict {
			f.nextPoll--
		}
		f.mu.Unlock()
		if conflict {
			w.WriteHeader(http.StatusConflict)
			_, _ = w.Write([]byte(`{"detail":"conflict"}`))
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[]`))
	})
	return mux
}

func TestRunSendsInitialHeartbeatAndStopsOnCancel(t *testing.T) {
	fake := &fakeControlPlane{}
	server := httptest.NewServer(fake.handler(t))
	defer server.Close()
	writeState(t, server.URL)
	prevInterval := commandPollInterval
	commandPollInterval = 5 * time.Millisecond
	defer func() { commandPollInterval = prevInterval }()

	ctx, cancel := context.WithCancel(t.Context())
	done := make(chan error, 1)
	go func() { done <- Run(ctx, slog.Default()) }()

	deadline := time.After(5 * time.Second)
	for {
		fake.mu.Lock()
		beats, polls := fake.heartbeats, fake.polls
		fake.mu.Unlock()
		if beats >= 1 && polls >= 3 {
			break
		}
		select {
		case <-deadline:
			t.Fatalf("agent loop did not progress: heartbeats=%d polls=%d", beats, polls)
		case <-time.After(5 * time.Millisecond):
		}
	}

	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("Run() error = %v; want clean stop", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("Run() did not return after context cancellation")
	}
}

func TestPollLoopSurvivesControlPlaneErrors(t *testing.T) {
	fake := &fakeControlPlane{nextPoll: 2} // two 409s, then empty answers again
	server := httptest.NewServer(fake.handler(t))
	defer server.Close()
	writeState(t, server.URL)
	prevInterval := commandPollInterval
	commandPollInterval = 5 * time.Millisecond
	defer func() { commandPollInterval = prevInterval }()

	ctx, cancel := context.WithCancel(t.Context())
	done := make(chan error, 1)
	go func() { done <- Run(ctx, slog.Default()) }()

	deadline := time.After(5 * time.Second)
	for {
		fake.mu.Lock()
		polls := fake.polls
		fake.mu.Unlock()
		if polls >= 4 { // 2 conflicts + at least 2 successful empty polls
			break
		}
		select {
		case <-deadline:
			t.Fatalf("poll loop stopped early after conflicts: polls=%d", polls)
		case <-time.After(5 * time.Millisecond):
		}
	}

	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("Run() error = %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("Run() did not return after cancellation")
	}
}

func TestRunFailsWithoutState(t *testing.T) {
	t.Setenv("DEPLOYDOCK_AGENT_CONFIG", filepath.Join(t.TempDir(), "missing.json"))
	err := Run(t.Context(), slog.Default())
	if !errors.Is(err, config.ErrNotRegistered) {
		t.Fatalf("Run() error = %v; want ErrNotRegistered for a missing state file", err)
	}
}
