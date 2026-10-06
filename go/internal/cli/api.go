// Thin JSON API client for the user-facing control plane endpoints.
package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// API is a minimal authenticated client for /api/v1.
type API struct {
	BaseURL string
	Token   string
	HTTP    *http.Client
}

// Version is reported by the MCP server handshake; overridden at build time.
var Version = "dev"

func NewAPI(baseURL, token string) *API {
	return &API{BaseURL: strings.TrimRight(baseURL, "/"), Token: token, HTTP: &http.Client{Timeout: 30 * time.Second}}
}

// DoJSON performs one authenticated request and decodes the JSON response.
func (a *API) DoJSON(ctx context.Context, method, path string, body, out any) error {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("encode request: %w", err)
		}
		reader = bytes.NewReader(encoded)
	}
	req, err := http.NewRequestWithContext(ctx, method, a.BaseURL+path, reader)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if a.Token != "" {
		req.Header.Set("Authorization", "Bearer "+a.Token)
	}

	resp, err := a.HTTP.Do(req)
	if err != nil {
		return fmt.Errorf("could not reach %s: %w", a.BaseURL, err)
	}
	defer resp.Body.Close()

	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode >= 400 {
		return apiError(resp.StatusCode, raw)
	}
	if out == nil || len(raw) == 0 {
		return nil
	}
	if err := json.Unmarshal(raw, out); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	return nil
}

func apiError(status int, raw []byte) error {
	var body struct {
		Detail string `json:"detail"`
	}
	if err := json.Unmarshal(raw, &body); err == nil && body.Detail != "" {
		return fmt.Errorf("API error (%d): %s", status, body.Detail)
	}
	return fmt.Errorf("API error (%d): %s", status, strings.TrimSpace(string(raw)))
}

// httpGet builds an authenticated GET request for streaming endpoints.
func httpGet(ctx context.Context, api *API, path string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, api.BaseURL+path, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "text/event-stream")
	if api.Token != "" {
		req.Header.Set("Authorization", "Bearer "+api.Token)
	}
	resp, err := api.HTTP.Do(req)
	if err != nil {
		return nil, fmt.Errorf("could not reach %s: %w", api.BaseURL, err)
	}
	if resp.StatusCode >= 400 {
		defer resp.Body.Close()
		return nil, fmt.Errorf("API error (%d) on %s", resp.StatusCode, path)
	}
	return resp, nil
}

// ---- wire types (subset of the control-plane API) ----

type LoginResponse struct {
	Token struct {
		AccessToken string `json:"access_token"`
		TokenType   string `json:"token_type"`
	} `json:"token"`
	User struct {
		Email    string `json:"email"`
		FullName string `json:"full_name"`
	} `json:"user"`
}

type User struct {
	Email    string  `json:"email"`
	FullName string  `json:"full_name"`
	ID       *string `json:"id,omitempty"`
}

type App struct {
	ID                   string  `json:"id"`
	Name                 string  `json:"name"`
	ServerID             string  `json:"server_id"`
	RepositoryURL        string  `json:"repository_url"`
	Branch               string  `json:"branch"`
	AppPath              string  `json:"app_path"`
	ServiceName          *string `json:"service_name"`
	CurrentCommit        *string `json:"current_commit"`
	LastSuccessfulCommit *string `json:"last_successful_commit"`
	Port                 *int    `json:"port"`
}

type Server struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Username string `json:"username"`
	Status   string `json:"status"`
}

type Deployment struct {
	ID              string  `json:"id"`
	AppID           string  `json:"app_id"`
	Status          string  `json:"status"`
	Kind            string  `json:"kind"`
	CommitSHA       *string `json:"commit_sha"`
	StartedAt       *string `json:"started_at"`
	FinishedAt      *string `json:"finished_at"`
	DurationSeconds *int    `json:"duration_seconds"`
	Error           *string `json:"error_message"`
}

type DeploymentLog struct {
	Stream   string `json:"stream"`
	Line     string `json:"line"`
	Sequence int    `json:"sequence"`
}

type DashboardSummary struct {
	TotalServers           int     `json:"total_servers"`
	ConnectedServers       int     `json:"connected_servers"`
	TotalApps              int     `json:"total_apps"`
	DeployedApps           int     `json:"deployed_apps"`
	RecentFailures         int     `json:"recent_failures"`
	LatestDeploymentStatus *string `json:"latest_deployment_status"`
}

type Dashboard struct {
	Summary DashboardSummary `json:"summary"`
}

// AppPayload is a project-create body.
type AppPayload struct {
	Name           string `json:"name"`
	ServerID       string `json:"server_id"`
	RepositoryURL  string `json:"repository_url"`
	Branch         string `json:"branch"`
	AppPath        string `json:"app_path"`
	ServiceName    string `json:"service_name,omitempty"`
	DeployCommand  string `json:"deploy_command"`
	HealthcheckURL string `json:"healthcheck_url,omitempty"`
	Port           int    `json:"port,omitempty"`
}
