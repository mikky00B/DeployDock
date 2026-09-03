package client

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRegisterSendsRegistrationTokenAndDecodesResponse(t *testing.T) {
	var gotAuth string
	var gotPath string
	var gotBody RegisterRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		if err := json.NewDecoder(r.Body).Decode(&gotBody); err != nil {
			t.Errorf("bad request body: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(RegisterResponse{
			AgentID:                  "agent-1",
			AgentToken:               "dck_at_secret",
			HeartbeatIntervalSeconds: 30,
		})
	}))
	defer server.Close()

	api := New(server.URL)
	resp, err := api.Register(context.Background(), "dck_rt_token", RegisterRequest{
		Name: "nyc-1.vps", AgentVersion: "dev", OS: "linux", Arch: "amd64",
	})
	if err != nil {
		t.Fatalf("Register returned error: %v", err)
	}

	if gotPath != "/api/v1/agents/register" {
		t.Errorf("path = %q, want /api/v1/agents/register", gotPath)
	}
	if gotAuth != "Bearer dck_rt_token" {
		t.Errorf("Authorization = %q, want registration token bearer", gotAuth)
	}
	if gotBody.Name != "nyc-1.vps" || gotBody.OS != "linux" {
		t.Errorf("request body = %+v", gotBody)
	}
	if resp.AgentID != "agent-1" || resp.AgentToken != "dck_at_secret" {
		t.Errorf("response = %+v", resp)
	}
}

func TestHeartbeatTargetsAgentSpecificPath(t *testing.T) {
	var gotPath, gotAuth string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(HeartbeatResponse{Status: "ok", HeartbeatIntervalSeconds: 45})
	}))
	defer server.Close()

	api := New(server.URL)
	resp, err := api.Heartbeat(context.Background(), "agent-1", "dck_at_secret", HeartbeatRequest{
		AgentVersion: "dev",
		Metrics:      &MetricsSnapshot{MemoryPercent: ptr(43.5)},
	})
	if err != nil {
		t.Fatalf("Heartbeat returned error: %v", err)
	}

	want := "/api/v1/agents/agent-1/heartbeat"
	if gotPath != want {
		t.Errorf("path = %q, want %q", gotPath, want)
	}
	if gotAuth != "Bearer dck_at_secret" {
		t.Errorf("Authorization = %q, want agent token bearer", gotAuth)
	}
	if resp.HeartbeatIntervalSeconds != 45 {
		t.Errorf("interval = %d, want 45", resp.HeartbeatIntervalSeconds)
	}
}

func TestRegisterRejectsInvalidToken(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, `{"detail":"Registration token is unknown, expired, or already used"}`, http.StatusUnauthorized)
	}))
	defer server.Close()

	_, err := New(server.URL).Register(context.Background(), "dck_rt_bad", RegisterRequest{})
	if err == nil {
		t.Fatal("expected error for 401, got nil")
	}
}

func TestPingRequiresHealthyEndpoint(t *testing.T) {
	ok := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer ok.Close()
	if err := New(ok.URL).Ping(context.Background()); err != nil {
		t.Fatalf("Ping against healthy server failed: %v", err)
	}

	broken := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer broken.Close()
	if err := New(broken.URL).Ping(context.Background()); err == nil {
		t.Fatal("expected Ping error against unhealthy server, got nil")
	}
}

func ptr(f float64) *float64 { return &f }
